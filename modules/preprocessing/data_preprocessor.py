"""
数据预处理与标准化模块
======================

提供数据清洗、地址标准化、坐标校验等预处理功能，确保输入数据质量。
"""

import re
import json
import logging
from typing import List, Dict, Optional, Union, Tuple
from dataclasses import dataclass, field
from datetime import datetime
import pandas as pd
import numpy as np
import sys
sys.path.insert(0, '..')

from config import geo_config, text_config
from utils.geo_utils import validate_coordinate
from utils.text_utils import normalize_text as clean_text


@dataclass
class CleanResult:
    """清洗结果"""
    is_valid: bool
    cleaned_text: str
    removed_count: int = 0
    warnings: List[str] = field(default_factory=list)


@dataclass
class StandardizedAddress:
    """标准化地址"""
    raw_text: str
    province: Optional[str] = None
    city: Optional[str] = None
    district: Optional[str] = None
    street: Optional[str] = None
    number: Optional[str] = None
    full_address: Optional[str] = None
    confidence: float = 0.0
    warnings: List[str] = field(default_factory=list)


@dataclass
class CoordinateCorrection:
    """坐标校正结果"""
    original_lat: float
    original_lon: float
    corrected_lat: Optional[float] = None
    corrected_lon: Optional[float] = None
    correction_type: Optional[str] = None
    is_valid: bool = True
    warnings: List[str] = field(default_factory=list)


@dataclass
class PreprocessResult:
    """预处理结果"""
    record_id: str
    cleaned_data: Dict
    standardized_address: Optional[StandardizedAddress] = None
    coordinate_correction: Optional[CoordinateCorrection] = None
    is_processed: bool = True
    processing_time_ms: int = 0
    errors: List[str] = field(default_factory=list)


class DataPreprocessor:
    """数据预处理器"""

    def __init__(self):
        self.logger = logging.getLogger(__name__)

        # 中国行政区划数据（简化版，实际应用中应使用完整数据）
        self.admin_divisions = {
            # 省级
            '北京市': ['北京'],
            '上海市': ['上海'],
            '天津市': ['天津'],
            '重庆市': ['重庆'],
            '广东省': ['广东', '粤'],
            '江苏省': ['江苏', '苏'],
            '浙江省': ['浙江', '浙'],
            '山东省': ['山东', '鲁'],
            '河南省': ['河南', '豫'],
            '四川省': ['四川', '川', '蜀'],
            '湖北省': ['湖北', '鄂'],
            '湖南省': ['湖南', '湘'],
            '河北省': ['河北', '冀'],
            '福建省': ['福建', '闽'],
            '安徽省': ['安徽', '皖'],
            '江西省': ['江西', '赣'],
            '辽宁省': ['辽宁', '辽'],
            '黑龙江省': ['黑龙江', '黑'],
            '吉林省': ['吉林', '吉'],
            '山西省': ['山西', '晋'],
            '陕西省': ['陕西', '陕', '秦'],
            '甘肃省': ['甘肃', '甘', '陇'],
            '青海省': ['青海', '青'],
            '新疆维吾尔自治区': ['新疆', '新'],
            '西藏自治区': ['西藏', '藏'],
            '宁夏回族自治区': ['宁夏', '宁'],
            '广西壮族自治区': ['广西', '桂'],
            '内蒙古自治区': ['内蒙古', '蒙'],
            '海南省': ['海南', '琼'],
            '台湾省': ['台湾', '台'],
            '香港特别行政区': ['香港', '港'],
            '澳门特别行政区': ['澳门', '澳'],
        }

        # 常见地址关键词
        self.address_keywords = [
            '省', '市', '区', '县', '镇', '乡', '街道', '路', '巷', '弄',
            '号', '栋', '层', '室', '楼', '院', '村', '小区', '大厦',
            '中心', '广场', '花园', '公寓', '城', '堡', '寨'
        ]

        # 坐标转换相关
        self.coord_converters = {
            'gcj02_to_wgs84': self._gcj02_to_wgs84,
            'wgs84_to_gcj02': self._wgs84_to_gcj02,
        }

    def clean_and_denoise(self, raw_data: Dict) -> CleanResult:
        """
        清洗和去噪数据

        Args:
            raw_data: 原始数据

        Returns:
            CleanResult: 清洗结果
        """
        start_time = datetime.now()

        cleaned_text = raw_data.get('text', '')
        original_length = len(cleaned_text)

        # 1. 基础文本清理
        cleaned_text = clean_text(cleaned_text)

        # 2. 移除特殊符号（保留中文、英文、数字、基本标点）
        cleaned_text = re.sub(r'[^一-龥a-zA-Z0-9\s，。！？、；：""''（）【】\-\+\.]', '', cleaned_text)

        # 3. 移除多余的空格和换行
        cleaned_text = re.sub(r'\s+', ' ', cleaned_text).strip()

        # 4. 过滤长度
        if len(cleaned_text) < text_config.min_text_length:
            cleaned_text = ""
        elif len(cleaned_text) > text_config.max_text_length:
            cleaned_text = cleaned_text[:text_config.max_text_length]

        removed_count = original_length - len(cleaned_text)
        warnings = []

        # 5. 检查营销词堆砌
        if self._has_keyword_stuffing(cleaned_text):
            warnings.append("检测到营销词堆砌")

        # 6. 检查模板内容
        if self._is_template_content(cleaned_text):
            warnings.append("检测到模板化内容")

        # 7. 检查可疑词
        suspicious_count = self._count_suspicious_keywords(cleaned_text)
        if suspicious_count >= 3:
            warnings.append(f"包含{suspicious_count}个可疑关键词")

        # 8. 去除重复内容
        cleaned_text = self._remove_duplicates(cleaned_text)

        is_valid = len(cleaned_text) >= text_config.min_text_length

        # 计算处理时间
        processing_time_ms = int((datetime.now() - start_time).total_seconds() * 1000)

        return CleanResult(
            is_valid=is_valid,
            cleaned_text=cleaned_text,
            removed_count=removed_count,
            warnings=warnings
        )

    def standardize_address(self, address_text: str) -> StandardizedAddress:
        """
        地址标准化

        Args:
            address_text: 原始地址文本

        Returns:
            StandardizedAddress: 标准化地址
        """
        standardized = StandardizedAddress(raw_text=address_text)

        if not address_text or len(address_text.strip()) < 2:
            standardized.warnings.append("地址文本为空或过短")
            return standardized

        # 1. 清理地址文本
        cleaned_address = clean_text(address_text)

        # 2. 识别行政区划
        standardized.province, standardized.city, standardized.district = self._parse_admin_division(cleaned_address)

        # 3. 提取街道和门牌号
        standardized.street, standardized.number = self._parse_street_and_number(cleaned_address, standardized.city, standardized.district)

        # 4. 构建完整地址
        standardized.full_address = self._build_full_address(
            standardized.province,
            standardized.city,
            standardized.district,
            standardized.street,
            standardized.number
        )

        # 5. 计算置信度
        standardized.confidence = self._calculate_address_confidence(
            cleaned_address,
            standardized.province,
            standardized.city,
            standardized.district
        )

        # 6. 检查警告
        if not standardized.province:
            standardized.warnings.append("无法识别省份")
        if not standardized.city:
            standardized.warnings.append("无法识别城市")
        if not standardized.full_address:
            standardized.warnings.append("地址解析失败")

        return standardized

    def validate_and_correct_coordinates(self, lat: float, lon: float,
                                       coord_system: str = 'wgs84') -> CoordinateCorrection:
        """
        坐标校验和修正

        Args:
            lat: 纬度
            lon: 经度
            coord_system: 坐标系统 ('wgs84' 或 'gcj02')

        Returns:
            CoordinateCorrection: 坐标校正结果
        """
        correction = CoordinateCorrection(
            original_lat=lat,
            original_lon=lon
        )

        # 1. 基础坐标验证
        if not validate_coordinate(lat, lon):
            correction.is_valid = False
            correction.warnings.append("坐标超出中国范围")
            return correction

        # 2. 坐标系统转换
        if coord_system == 'gcj02':
            corrected = self._gcj02_to_wgs84(lat, lon)
            if corrected and validate_coordinate(corrected[0], corrected[1]):
                correction.corrected_lat = corrected[0]
                correction.corrected_lon = corrected[1]
                correction.correction_type = "gcj02_to_wgs84"

        # 3. 检查坐标是否在水域或禁区
        if self._is_water_or_forbidden_area(correction.corrected_lat or lat, correction.corrected_lon or lon):
            correction.warnings.append("坐标可能在水域或禁区")

        # 4. 检查坐标精度
        accuracy = self._check_coordinate_precision(correction.corrected_lat or lat, correction.corrected_lon or lon)
        if accuracy < 0.00001:  # 小于1米精度
            correction.warnings.append("坐标精度过高，可能存在异常")

        return correction

    def batch_preprocess(self, records: List[Dict]) -> List[PreprocessResult]:
        """
        批量预处理

        Args:
            records: 记录列表

        Returns:
            List[PreprocessResult]: 批量预处理结果
        """
        results = []

        for record in records:
            try:
                result = self.preprocess_single_record(record)
                results.append(result)
            except Exception as e:
                self.logger.error(f"处理记录 {record.get('record_id', 'unknown')} 时出错: {str(e)}")
                error_result = PreprocessResult(
                    record_id=record.get('record_id', 'unknown'),
                    is_processed=False,
                    errors=[str(e)]
                )
                results.append(error_result)

        return results

    def preprocess_single_record(self, record: Dict) -> PreprocessResult:
        """
        预处理单条记录

        Args:
            record: 输入记录

        Returns:
            PreprocessResult: 预处理结果
        """
        start_time = datetime.now()
        result = PreprocessResult(
            record_id=record.get('record_id', str(datetime.now().timestamp()))
        )

        # 1. 清洗文本
        if 'text' in record:
            clean_result = self.clean_and_denoise(record)
            result.cleaned_data['text'] = clean_result.cleaned_text
            result.cleaned_data['clean_warnings'] = clean_result.warnings

        # 2. 地址标准化
        if 'address' in record:
            standardized = self.standardize_address(record['address'])
            result.standardized_address = standardized
            if standardized.warnings:
                result.cleaned_data['address_warnings'] = standardized.warnings

        # 3. 坐标校验
        if 'latitude' in record and 'longitude' in record:
            coord_correction = self.validate_and_correct_coordinates(
                record['latitude'],
                record['longitude'],
                record.get('coord_system', 'wgs84')
            )
            result.coordinate_correction = coord_correction
            if not coord_correction.is_valid or coord_correction.warnings:
                result.cleaned_data['coord_warnings'] = coord_correction.warnings

        # 4. 计算处理时间
        result.processing_time_ms = int((datetime.now() - start_time).total_seconds() * 1000)
        result.is_processed = True

        return result

    def export_preprocessed_data(self, results: List[PreprocessResult],
                                format: str = 'json') -> Union[str, Dict]:
        """
        导出预处理数据

        Args:
            results: 预处理结果列表
            format: 导出格式 ('json', 'csv', 'dict')

        Returns:
            导出的数据
        """
        if format == 'json':
            return json.dumps([{
                'record_id': r.record_id,
                'cleaned_data': r.cleaned_data,
                'processing_time_ms': r.processing_time_ms,
                'errors': r.errors
            } for r in results], ensure_ascii=False, indent=2)

        elif format == 'csv':
            df = pd.DataFrame([{
                'record_id': r.record_id,
                'cleaned_text': r.cleaned_data.get('text', ''),
                'province': r.standardized_address.province if r.standardized_address else '',
                'city': r.standardized_address.city if r.standardized_address else '',
                'district': r.standardized_address.district if r.standardized_address else '',
                'street': r.standardized_address.street if r.standardized_address else '',
                'number': r.standardized_address.number if r.standardized_address else '',
                'full_address': r.standardized_address.full_address if r.standardized_address else '',
                'latitude_corrected': r.coordinate_correction.corrected_lat if r.coordinate_correction else '',
                'longitude_corrected': r.coordinate_correction.corrected_lon if r.coordinate_correction else '',
                'processing_time_ms': r.processing_time_ms,
                'errors': ';'.join(r.errors) if r.errors else ''
            } for r in results])
            return df.to_csv(index=False)

        elif format == 'dict':
            return [{
                'record_id': r.record_id,
                'cleaned_data': r.cleaned_data,
                'standardized_address': {
                    'province': r.standardized_address.province,
                    'city': r.standardized_address.city,
                    'district': r.standardized_address.district,
                    'street': r.standardized_address.street,
                    'number': r.standardized_address.number,
                    'full_address': r.standardized_address.full_address,
                    'confidence': r.standardized_address.confidence
                } if r.standardized_address else None,
                'coordinate_correction': {
                    'original_lat': r.coordinate_correction.original_lat,
                    'original_lon': r.coordinate_correction.original_lon,
                    'corrected_lat': r.coordinate_correction.corrected_lat,
                    'corrected_lon': r.coordinate_correction.corrected_lon,
                    'correction_type': r.coordinate_correction.correction_type,
                    'is_valid': r.coordinate_correction.is_valid,
                    'warnings': r.coordinate_correction.warnings
                } if r.coordinate_correction else None,
                'processing_time_ms': r.processing_time_ms,
                'errors': r.errors
            } for r in results]

        else:
            raise ValueError(f"不支持的导出格式: {format}")

    # 私有方法
    def _parse_admin_division(self, address: str) -> Tuple[Optional[str], Optional[str], Optional[str]]:
        """解析行政区划"""
        province = None
        city = None
        district = None

        # 从大到小匹配
        for prov_name, aliases in self.admin_divisions.items():
            for alias in aliases:
                if alias in address:
                    province = prov_name
                    # 在地址中移除省份，继续匹配城市
                    address = address.replace(alias, '')
                    break
            if province:
                break

        # 简化的城市匹配（实际应用中需要更复杂的逻辑）
        if province:
            # 这里简化处理，实际需要根据省份匹配对应的城市列表
            if '市' in address:
                city = address.split('市')[0] + '市'

        # 区县匹配
        if '区' in address:
            district = address.split('区')[0] + '区'
        elif '县' in address:
            district = address.split('县')[0] + '县'

        return province, city, district

    def _parse_street_and_number(self, address: str, city: str = None, district: str = None) -> Tuple[Optional[str], Optional[str]]:
        """解析街道和门牌号"""
        street = None
        number = None

        # 移除行政区划信息
        if city:
            address = address.replace(city, '')
        if district:
            address = address.replace(district, '')

        # 匹配街道和门牌号
        # 简化处理：查找包含数字的街道部分
        street_parts = re.findall(r'[^\d]+', address)
        number_parts = re.findall(r'\d+', address)

        if street_parts:
            street = street_parts[-1].strip()
        if number_parts:
            number = number_parts[0]

        return street, number

    def _build_full_address(self, province: str, city: str, district: str, street: str, number: str) -> str:
        """构建完整地址"""
        parts = []
        if province:
            parts.append(province)
        if city:
            parts.append(city)
        if district:
            parts.append(district)
        if street:
            parts.append(street)
        if number:
            parts.append(number)

        return ''.join(parts) if parts else None

    def _calculate_address_confidence(self, address: str, province: str, city: str, district: str) -> float:
        """计算地址解析置信度"""
        confidence = 0.0

        if province:
            confidence += 0.4
        if city:
            confidence += 0.3
        if district:
            confidence += 0.2
        if len(address) > 10:
            confidence += 0.1

        return min(confidence, 1.0)

    def _has_keyword_stuffing(self, text: str) -> bool:
        """检查营销词堆砌"""
        # 检查连续出现的营销词
        keyword_pattern = r'(' + '|'.join(text_config.suspicious_keywords[:5]) + r'){3,}'
        if re.search(keyword_pattern, text):
            return True

        # 检查营销词密度
        total_words = len(re.findall(r'\w+', text))
        keyword_count = sum(1 for kw in text_config.suspicious_keywords if kw in text)

        if total_words > 0 and keyword_count / total_words > 0.3:
            return True

        return False

    def _is_template_content(self, text: str) -> bool:
        """检查模板化内容"""
        # 检查固定的模板句式
        templates = [
            r'.{5,}，.{5,}，.{5,}。',
            r'必去！.{3,}推荐！',
            r'强烈推荐.{3,}绝对.{3,}',
        ]

        for template in templates:
            if re.fullmatch(template, text):
                return True

        return False

    def _count_suspicious_keywords(self, text: str) -> int:
        """统计可疑关键词数量"""
        count = 0
        for keyword in text_config.suspicious_keywords:
            if keyword in text:
                count += 1
        return count

    def _remove_duplicates(self, text: str) -> str:
        """去除重复内容"""
        # 移除连续重复的字符
        text = re.sub(r'(.)\1{3,}', r'\1', text)

        # 移除重复的句子
        sentences = re.split(r'[。！？]', text)
        unique_sentences = []
        seen = set()

        for sentence in sentences:
            if sentence.strip() and sentence.strip() not in seen:
                unique_sentences.append(sentence.strip())
                seen.add(sentence.strip())

        return '。'.join(unique_sentences)

    def _gcj02_to_wgs84(self, lat: float, lon: float) -> Tuple[float, float]:
        """GCJ-02坐标转换为WGS84坐标（简化版本）"""
        # 实际应用中需要使用更精确的转换算法
        # 这里使用简化的转换方法
        delta_lat = (lat - 35.0) * 0.00001
        delta_lon = (lon - 105.0) * 0.00001

        wgs84_lat = lat - delta_lat
        wgs84_lon = lon - delta_lon

        return wgs84_lat, wgs84_lon

    def _wgs84_to_gcj02(self, lat: float, lon: float) -> Tuple[float, float]:
        """WGS84坐标转换为GCJ-02坐标（简化版本）"""
        # 实际应用中需要使用更精确的转换算法
        # 这里使用简化的转换方法
        delta_lat = (lat - 35.0) * 0.00001
        delta_lon = (lon - 105.0) * 0.00001

        gcj02_lat = lat + delta_lat
        gcj02_lon = lon + delta_lon

        return gcj02_lat, gcj02_lon

    def _is_water_or_forbidden_area(self, lat: float, lon: float) -> bool:
        """检查坐标是否在水域或禁区"""
        # 这里简化处理，实际应用中需要使用地理数据
        # 检查是否在主要水域附近
        water_areas = [
            (31.2, 121.5),  # 上海附近
            (22.3, 114.2),  # 香港附近
        ]

        for water_lat, water_lon in water_areas:
            distance = ((lat - water_lat) ** 2 + (lon - water_lon) ** 2) ** 0.5
            if distance < 0.1:  # 约11公里
                return True

        return False

    def _check_coordinate_precision(self, lat: float, lon: float) -> float:
        """检查坐标精度"""
        # 计算坐标的小数位数
        lat_precision = len(str(lat).split('.')[-1]) if '.' in str(lat) else 0
        lon_precision = len(str(lon).split('.')[-1]) if '.' in str(lon) else 0

        # 返回最小精度（米）
        return min(lat_precision, lon_precision) * 111000  # 粗略转换


# 使用示例
if __name__ == "__main__":
    # 创建预处理器实例
    preprocessor = DataPreprocessor()

    # 测试数据
    test_data = [
        {
            'record_id': '001',
            'text': '这家店太棒了！强烈推荐，必去！yyds！',
            'address': '北京市朝阳区三里屯路19号',
            'latitude': 39.9385,
            'longitude': 116.4544,
            'coord_system': 'wgs84'
        },
        {
            'record_id': '002',
            'text': '普通餐厅，味道还可以。',
            'address': '上海市浦东新区张江高科技园区',
            'latitude': 31.2064,
            'longitude': 121.6083,
            'coord_system': 'wgs84'
        }
    ]

    # 批量处理
    results = preprocessor.batch_preprocess(test_data)

    # 导出结果
    export_data = preprocessor.export_preprocessed_data(results, format='json')
    print("预处理结果:")
    print(export_data)