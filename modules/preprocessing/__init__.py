"""
数据预处理与标准化模块
"""
import re
import json
from typing import Optional, Dict, Any, List, Tuple
from dataclasses import dataclass
import hashlib


@dataclass
class StandardizedAddress:
    province: str = ""
    city: str = ""
    district: str = ""
    street: str = ""
    number: str = ""
    full_address: str = ""
    confidence: float = 0.0


@dataclass
class PreprocessResult:
    is_valid: bool
    cleaned_data: Dict[str, Any]
    warnings: List[str]
    errors: List[str]
    standardized_address: Optional[StandardizedAddress] = None


class DataPreprocessor:
    """
    数据预处理与标准化处理器
    """
    
    def __init__(self):
        self.provinces = self._load_administrative_divisions()
        self.coordinate_bounds = {
            "china": {
                "lat_min": 18.0, "lat_max": 54.0,
                "lon_min": 73.0, "lon_max": 135.0
            }
        }
    
    def _load_administrative_divisions(self) -> Dict[str, List[str]]:
        return {
            "北京市": ["东城区", "西城区", "朝阳区", "丰台区", "石景山区", "海淀区", "门头沟区", "房山区", "通州区", "顺义区", "昌平区", "大兴区", "怀柔区", "平谷区", "密云区", "延庆区"],
            "上海市": ["黄浦区", "徐汇区", "长宁区", "静安区", "普陀区", "虹口区", "杨浦区", "闵行区", "宝山区", "嘉定区", "浦东新区", "金山区", "松江区", "青浦区", "奉贤区", "崇明区"],
            "广东省": ["广州市", "深圳市", "珠海市", "汕头市", "佛山市", "韶关市", "湛江市", "肇庆市", "江门市", "茂名市", "惠州市", "梅州市", "汕尾市", "河源市", "阳江市", "清远市", "东莞市", "中山市", "潮州市", "揭阳市", "云浮市"],
            "浙江省": ["杭州市", "宁波市", "温州市", "嘉兴市", "湖州市", "绍兴市", "金华市", "衢州市", "舟山市", "台州市", "丽水市"],
            "江苏省": ["南京市", "无锡市", "徐州市", "常州市", "苏州市", "南通市", "连云港市", "淮安市", "盐城市", "扬州市", "镇江市", "泰州市", "宿迁市"],
        }
    
    def preprocess(self, data: Dict[str, Any]) -> PreprocessResult:
        """
        完整的数据预处理流程
        """
        result = PreprocessResult(
            is_valid=True,
            cleaned_data={},
            warnings=[],
            errors=[]
        )
        
        cleaned = data.copy()
        
        if "name" in data:
            name_result = self._clean_name(data["name"])
            cleaned["name"] = name_result["name"]
            result.warnings.extend(name_result.get("warnings", []))
        
        if "address" in data:
            addr_result = self._standardize_address(data["address"])
            cleaned["address"] = addr_result.full_address
            result.standardized_address = addr_result
            if addr_result.confidence < 0.5:
                result.warnings.append(f"地址标准化置信度较低: {addr_result.confidence}")
        
        if "latitude" in data and "longitude" in data:
            coord_result = self._validate_and_correct_coordinates(
                data["latitude"], data["longitude"]
            )
            if coord_result["valid"]:
                cleaned["latitude"] = coord_result["latitude"]
                cleaned["longitude"] = coord_result["longitude"]
                if coord_result.get("corrected"):
                    result.warnings.append("坐标已自动纠偏")
            else:
                result.errors.append(coord_result["error"])
                result.is_valid = False
        
        if "phone" in data:
            phone_result = self._validate_phone(data["phone"])
            cleaned["phone"] = phone_result["phone"]
            if not phone_result["valid"]:
                result.warnings.append(f"电话格式异常: {data['phone']}")
        
        if "business_hours" in data:
            hours_result = self._validate_business_hours(data["business_hours"])
            if not hours_result["valid"]:
                result.warnings.append(f"营业时间逻辑异常: {hours_result.get('error', '')}")
        
        cleaned = self._remove_duplicates(cleaned)
        cleaned = self._remove_noise(cleaned)
        
        result.cleaned_data = cleaned
        return result
    
    def _clean_name(self, name: str) -> Dict[str, Any]:
        """
        清理POI名称
        """
        result = {"name": name, "warnings": []}
        
        if not name or not name.strip():
            result["warnings"].append("名称为空")
            return result
        
        cleaned = name.strip()
        
        marketing_patterns = [
            r'(全网|全国|世界|全球)(第一|最好|最大|最强|最优惠)',
            r'(顶级|极致|完美|绝佳)',
            r'(免费|赠送|优惠|折扣).{0,5}(活动|促销)',
        ]
        
        for pattern in marketing_patterns:
            if re.search(pattern, cleaned):
                result["warnings"].append(f"检测到营销词汇: {re.search(pattern, cleaned).group()}")
        
        special_chars = r'[【】《》\[\]{}|\\\/@#$%^&*()_=+<>?]'
        cleaned = re.sub(special_chars, '', cleaned)
        
        cleaned = re.sub(r'\s+', ' ', cleaned).strip()
        
        result["name"] = cleaned
        return result
    
    def _standardize_address(self, address: str) -> StandardizedAddress:
        """
        地址标准化与结构化
        """
        result = StandardizedAddress(full_address=address)
        
        if not address:
            result.confidence = 0.0
            return result
        
        addr = address.strip()
        
        province_patterns = [
            (r'(北京市|上海市|天津市|重庆市)', '直辖市'),
            (r'(.+省)', '省'),
        ]
        
        for pattern, _ in province_patterns:
            match = re.search(pattern, addr)
            if match:
                result.province = match.group(1)
                break
        
        city_patterns = [
            r'(.+市)',
            r'(.+自治州)',
        ]
        
        for pattern in city_patterns:
            match = re.search(pattern, addr)
            if match:
                city = match.group(1)
                if city != result.province:
                    result.city = city
                break
        
        district_patterns = [
            r'(.+区)',
            r'(.+县)',
            r'(.+市)',
        ]
        
        for pattern in district_patterns:
            match = re.search(pattern, addr)
            if match:
                district = match.group(1)
                if district not in [result.province, result.city]:
                    result.district = district
                break
        
        street_match = re.search(r'(.+路|.+街|.+道|.+巷)', addr)
        if street_match:
            result.street = street_match.group(1)
        
        number_match = re.search(r'(\d+号)', addr)
        if number_match:
            result.number = number_match.group(1)
        
        result.full_address = f"{result.province}{result.city}{result.district}{result.street}{result.number}".strip()
        
        if result.province:
            result.confidence += 0.3
        if result.city:
            result.confidence += 0.2
        if result.district:
            result.confidence += 0.2
        if result.street:
            result.confidence += 0.2
        if result.number:
            result.confidence += 0.1
        
        return result
    
    def _validate_and_correct_coordinates(self, lat: float, lon: float) -> Dict[str, Any]:
        """
        坐标校验与纠偏
        """
        result = {
            "valid": True,
            "latitude": lat,
            "longitude": lon,
            "corrected": False,
            "error": None
        }
        
        try:
            lat = float(lat)
            lon = float(lon)
        except (ValueError, TypeError):
            result["valid"] = False
            result["error"] = "坐标格式错误"
            return result
        
        if lat < -90 or lat > 90:
            result["valid"] = False
            result["error"] = f"纬度超出范围: {lat}"
            return result
        
        if lon < -180 or lon > 180:
            result["valid"] = False
            result["error"] = f"经度超出范围: {lon}"
            return result
        
        bounds = self.coordinate_bounds["china"]
        if not (bounds["lat_min"] <= lat <= bounds["lat_max"] and
                bounds["lon_min"] <= lon <= bounds["lon_max"]):
            result["error"] = "坐标不在中国境内"
            result["valid"] = True
        
        return result
    
    def _validate_phone(self, phone: str) -> Dict[str, Any]:
        """
        电话格式校验
        """
        result = {"phone": phone, "valid": True}
        
        if not phone:
            return result
        
        cleaned = re.sub(r'[^\d\-+]', '', phone)
        
        mobile_pattern = r'^1[3-9]\d{9}$'
        landline_pattern = r'^0\d{2,3}-?\d{7,8}$'
        service_pattern = r'^400-?\d{3}-?\d{4}$'
        
        if re.match(mobile_pattern, cleaned):
            result["type"] = "mobile"
        elif re.match(landline_pattern, cleaned):
            result["type"] = "landline"
        elif re.match(service_pattern, cleaned):
            result["type"] = "service"
        else:
            result["valid"] = False
        
        result["phone"] = cleaned
        return result
    
    def _validate_business_hours(self, hours: str) -> Dict[str, Any]:
        """
        营业时间逻辑校验
        """
        result = {"valid": True, "error": None}
        
        if not hours:
            return result
        
        time_pattern = r'(\d{1,2}):?(\d{2})?'
        times = re.findall(time_pattern, hours)
        
        if len(times) >= 2:
            try:
                start_hour = int(times[0][0])
                end_hour = int(times[1][0])
                
                if start_hour >= 24 or end_hour >= 24:
                    result["valid"] = False
                    result["error"] = "时间超出24小时制范围"
                elif start_hour > end_hour and end_hour != 0:
                    result["valid"] = False
                    result["error"] = f"开始时间({start_hour}:00)晚于结束时间({end_hour}:00)"
            except (ValueError, IndexError):
                pass
        
        return result
    
    def _remove_duplicates(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        去除重复数据
        """
        cleaned = data.copy()
        
        if "name" in cleaned and "address" in cleaned:
            unique_key = hashlib.md5(
                f"{cleaned.get('name', '')}{cleaned.get('address', '')}".encode()
            ).hexdigest()
            cleaned["_dedup_key"] = unique_key
        
        return cleaned
    
    def _remove_noise(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        去除噪声数据
        """
        cleaned = data.copy()
        
        for key, value in list(cleaned.items()):
            if value is None or value == "" or value == "null":
                del cleaned[key]
        
        for key, value in cleaned.items():
            if isinstance(value, str):
                value = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', value)
                cleaned[key] = value.strip()
        
        return cleaned
    
    def batch_preprocess(self, data_list: List[Dict[str, Any]]) -> List[PreprocessResult]:
        """
        批量预处理
        """
        return [self.preprocess(data) for data in data_list]


class CoordinateTransformer:
    """
    坐标转换工具
    支持 GCJ-02 (国测局坐标) 和 WGS-84 (GPS坐标) 互转
    """
    
    PI = 3.1415926535897932384626
    A = 6378245.0
    EE = 0.00669342162296594323
    
    @classmethod
    def wgs84_to_gcj02(cls, lat: float, lon: float) -> Tuple[float, float]:
        """
        WGS-84 转 GCJ-02
        """
        if cls._out_of_china(lat, lon):
            return lat, lon
        
        dlat = cls._transform_lat(lon - 105.0, lat - 35.0)
        dlon = cls._transform_lon(lon - 105.0, lat - 35.0)
        
        radlat = lat / 180.0 * cls.PI
        magic = math.sin(radlat)
        magic = 1 - cls.EE * magic * magic
        sqrtmagic = math.sqrt(magic)
        
        dlat = (dlat * 180.0) / ((cls.A * (1 - cls.EE)) / (magic * sqrtmagic) * cls.PI)
        dlon = (dlon * 180.0) / (cls.A / sqrtmagic * math.cos(radlat) * cls.PI)
        
        mglat = lat + dlat
        mglon = lon + dlon
        
        return mglat, mglon
    
    @classmethod
    def gcj02_to_wgs84(cls, lat: float, lon: float) -> Tuple[float, float]:
        """
        GCJ-02 转 WGS-84
        """
        if cls._out_of_china(lat, lon):
            return lat, lon
        
        dlat = cls._transform_lat(lon - 105.0, lat - 35.0)
        dlon = cls._transform_lon(lon - 105.0, lat - 35.0)
        
        radlat = lat / 180.0 * cls.PI
        magic = math.sin(radlat)
        magic = 1 - cls.EE * magic * magic
        sqrtmagic = math.sqrt(magic)
        
        dlat = (dlat * 180.0) / ((cls.A * (1 - cls.EE)) / (magic * sqrtmagic) * cls.PI)
        dlon = (dlon * 180.0) / (cls.A / sqrtmagic * math.cos(radlat) * cls.PI)
        
        mglat = lat + dlat
        mglon = lon + dlon
        
        return lat * 2 - mglat, lon * 2 - mglon
    
    @classmethod
    def _transform_lat(cls, x: float, y: float) -> float:
        ret = -100.0 + 2.0 * x + 3.0 * y + 0.2 * y * y + 0.1 * x * y + 0.2 * math.sqrt(abs(x))
        ret += (20.0 * math.sin(6.0 * x * cls.PI) + 20.0 * math.sin(2.0 * x * cls.PI)) * 2.0 / 3.0
        ret += (20.0 * math.sin(y * cls.PI) + 40.0 * math.sin(y / 3.0 * cls.PI)) * 2.0 / 3.0
        ret += (160.0 * math.sin(y / 12.0 * cls.PI) + 320 * math.sin(y * cls.PI / 30.0)) * 2.0 / 3.0
        return ret
    
    @classmethod
    def _transform_lon(cls, x: float, y: float) -> float:
        ret = 300.0 + x + 2.0 * y + 0.1 * x * x + 0.1 * x * y + 0.1 * math.sqrt(abs(x))
        ret += (20.0 * math.sin(6.0 * x * cls.PI) + 20.0 * math.sin(2.0 * x * cls.PI)) * 2.0 / 3.0
        ret += (20.0 * math.sin(x * cls.PI) + 40.0 * math.sin(x / 3.0 * cls.PI)) * 2.0 / 3.0
        ret += (150.0 * math.sin(x / 12.0 * cls.PI) + 300.0 * math.sin(x / 30.0 * cls.PI)) * 2.0 / 3.0
        return ret
    
    @classmethod
    def _out_of_china(cls, lat: float, lon: float) -> bool:
        if lon < 72.004 or lon > 137.8347:
            return True
        if lat < 0.8293 or lat > 55.8271:
            return True
        return False


import math
