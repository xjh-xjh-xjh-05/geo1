"""
坐标验证与校准模块
==================

提供坐标合法性检查、坐标系统转换、边界验证等功能。
"""

import math
import re
import logging
from typing import Tuple, Optional, Dict, List, Union
from dataclasses import dataclass, field
from enum import Enum

import numpy as np
import sys
sys.path.insert(0, '..')

from config import geo_config
from utils.geo_utils import validate_coordinate


class CoordinateSystem(Enum):
    """坐标系统类型"""
    WGS84 = "wgs84"  # GPS坐标
    GCJ02 = "gcj02"  # 国测局加密坐标
    BD09 = "bd09"    # 百度加密坐标
    MapBar = "mapbar"  # 图吧地图坐标


class CoordinateType(Enum):
    """坐标类型"""
    POINT = "point"      # 普通点
    ROAD = "road"       # 道路
    WATER = "water"      # 水域
    FORBIDDEN = "forbidden"  # 禁区
    NORMAL = "normal"    # 正常


@dataclass
class ValidationResult:
    """坐标验证结果"""
    is_valid: bool
    coordinate_type: CoordinateType
    warnings: List[str] = field(default_factory=list)
    corrected_lat: Optional[float] = None
    corrected_lon: Optional[float] = None
    distance_error: float = 0.0  # 与参考点的距离误差


@dataclass
class BoundaryCheck:
    """边界检查结果"""
    within_china: bool
    in_province: Optional[str] = None
    in_city: Optional[str] = None
    in_district: Optional[str] = None
    warnings: List[str] = field(default_factory=list)


class CoordinateValidator:
    """坐标验证器"""

    def __init__(self):
        self.logger = logging.getLogger(__name__)

        # 中国主要城市中心坐标（用于城市边界检查）
        self.city_centers = {
            '北京': (39.9042, 116.4074),
            '上海': (31.2304, 121.4737),
            '广州': (23.1291, 113.2644),
            '深圳': (22.5431, 114.0579),
            '杭州': (30.2741, 120.1551),
            '南京': (32.0603, 118.7969),
            '成都': (30.5728, 104.0668),
            '武汉': (30.5928, 114.3055),
            '西安': (34.3416, 108.9398),
            '重庆': (29.5630, 106.5516),
        }

        # 城市半径（公里）
        self.city_radius = {
            '北京': 50,
            '上海': 50,
            '广州': 40,
            '深圳': 40,
            '杭州': 30,
            '南京': 30,
            '成都': 30,
            '武汉': 30,
            '西安': 30,
            '重庆': 30,
        }

        # 水域坐标（简化）
        self.water_areas = [
            # 主要湖泊
            (31.2304, 120.1551),  # 太湖
            (30.2741, 120.1551),  # 西湖
            (29.5630, 106.5516),  # 重庆周边水域

            # 主要海岸线
            # 东海岸
            (22.3, 114.2),  # 深圳
            (23.1, 113.3),  # 广州
            (30.2, 121.5),  # 上海

            # 南海岸
            (20.0, 110.0),  # 海南
            (22.0, 113.5),  # 广东
        ]

        # 禁区坐标（简化）
        self.forbidden_areas = [
            # 军事禁区
            (39.9, 116.4),  # 北京周边
            (31.2, 121.5),  # 上海周边

            # 重要设施
            (39.9042, 116.4074),  # 天安门
            (40.4319, 116.5704),  # 奥运村
            (31.2304, 121.4737),  # 上海外滩
        ]

    def validate_coordinate(self, lat: float, lon: float,
                          coord_system: CoordinateSystem = CoordinateSystem.WGS84) -> ValidationResult:
        """
        验证坐标合法性

        Args:
            lat: 纬度
            lon: 经度
            coord_system: 坐标系统

        Returns:
            ValidationResult: 验证结果
        """
        result = ValidationResult(is_valid=True, coordinate_type=CoordinateType.NORMAL)

        # 1. 基础坐标范围验证
        if not self._validate_coordinate_bounds(lat, lon):
            result.is_valid = False
            result.warnings.append("坐标超出中国范围")
            return result

        # 2. 坐标系统转换
        if coord_system == CoordinateSystem.GCJ02:
            lat, lon = self.gcj02_to_wgs84(lat, lon)
        elif coord_system == CoordinateSystem.BD09:
            lat, lon = self.bd09_to_wgs84(lat, lon)

        # 3. 边界检查
        boundary_check = self.check_boundary(lat, lon)
        if boundary_check.warnings:
            result.warnings.extend(boundary_check.warnings)

        # 4. 坐标类型检查
        coord_type = self._determine_coordinate_type(lat, lon)
        result.coordinate_type = coord_type

        if coord_type == CoordinateType.WATER:
            result.warnings.append("坐标位于水域附近")
        elif coord_type == CoordinateType.FORBIDDEN:
            result.warnings.append("坐标位于禁区附近")
            result.is_valid = False

        # 5. 精度检查
        precision_check = self._check_coordinate_precision(lat, lon)
        if precision_check['warnings']:
            result.warnings.extend(precision_check['warnings'])

        # 6. 转换回原始坐标系统
        if coord_system != CoordinateSystem.WGS84:
            result.corrected_lat = lat
            result.corrected_lon = lon

        return result

    def batch_validate_coordinates(self, coordinates: List[Tuple[float, float]],
                                 coord_system: CoordinateSystem = CoordinateSystem.WGS84) -> List[ValidationResult]:
        """
        批量验证坐标

        Args:
            coordinates: 坐标列表 [(lat, lon), ...]
            coord_system: 坐标系统

        Returns:
            List[ValidationResult]: 验证结果列表
        """
        results = []

        for lat, lon in coordinates:
            try:
                result = self.validate_coordinate(lat, lon, coord_system)
                results.append(result)
            except Exception as e:
                self.logger.error(f"验证坐标 ({lat}, {lon}) 时出错: {str(e)}")
                error_result = ValidationResult(
                    is_valid=False,
                    coordinate_type=CoordinateType.POINT,
                    warnings=[f"验证错误: {str(e)}"]
                )
                results.append(error_result)

        return results

    def convert_coordinates(self, lat: float, lon: float,
                          from_system: CoordinateSystem,
                          to_system: CoordinateSystem) -> Tuple[float, float]:
        """
        坐标系统转换

        Args:
            lat: 纬度
            lon: 经度
            from_system: 源坐标系统
            to_system: 目标坐标系统

        Returns:
            Tuple[float, float]: 转换后的坐标
        """
        if from_system == to_system:
            return lat, lon

        # 先转换到WGS84
        if from_system == CoordinateSystem.GCJ02:
            lat, lon = self.gcj02_to_wgs84(lat, lon)
        elif from_system == CoordinateSystem.BD09:
            lat, lon = self.bd09_to_wgs84(lat, lon)

        # 再从WGS84转换到目标系统
        if to_system == CoordinateSystem.GCJ02:
            lat, lon = self.wgs84_to_gcj02(lat, lon)
        elif to_system == CoordinateSystem.BD09:
            lat, lon = self.wgs84_to_bd09(lat, lon)

        return lat, lon

    def check_boundary(self, lat: float, lon: float) -> BoundaryCheck:
        """
        检查坐标边界

        Args:
            lat: 纬度
            lon: 经度

        Returns:
            BoundaryCheck: 边界检查结果
        """
        boundary_check = BoundaryCheck(within_china=True)

        # 检查是否在中国范围内
        if not geo_config.latitude_min <= lat <= geo_config.latitude_max:
            boundary_check.within_china = False
            boundary_check.warnings.append("纬度超出中国范围")
            return boundary_check

        if not geo_config.longitude_min <= lon <= geo_config.longitude_max:
            boundary_check.within_china = False
            boundary_check.warnings.append("经度超出中国范围")
            return boundary_check

        # 检查所在省市（简化版本）
        for city_name, (city_lat, city_lon) in self.city_centers.items():
            distance = self.calculate_distance(lat, lon, city_lat, city_lon)
            if distance <= self.city_radius[city_name]:
                boundary_check.in_city = city_name
                break

        return boundary_check

    def calculate_distance(self, lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """
        计算两点间距离（单位：公里）

        Args:
            lat1, lon1: 第一个点的坐标
            lat2, lon2: 第二个点的坐标

        Returns:
            float: 距离（公里）
        """
        R = 6371  # 地球半径（公里）

        # 转换为弧度
        lat1_rad = math.radians(lat1)
        lon1_rad = math.radians(lon1)
        lat2_rad = math.radians(lat2)
        lon2_rad = math.radians(lon2)

        # 计算差值
        dlat = lat2_rad - lat1_rad
        dlon = lon2_rad - lon1_rad

        # Haversine公式
        a = math.sin(dlat/2)**2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(dlon/2)**2
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))

        distance = R * c
        return distance

    def detect_teleport(self, coordinates: List[Tuple[float, float]],
                       time_stamps: List[int]) -> List[Dict]:
        """
        检测瞬移行为

        Args:
            coordinates: 坐标列表 [(lat, lon), ...]
            time_stamps: 时间戳列表 [timestamp, ...]

        Returns:
            List[Dict]: 瞬移检测结果
        """
        if len(coordinates) < 2:
            return []

        teleport_events = []

        for i in range(1, len(coordinates)):
            lat1, lon1 = coordinates[i-1]
            lat2, lon2 = coordinates[i]

            # 计算距离
            distance = self.calculate_distance(lat1, lon1, lat2, lon2)

            # 计算时间差
            time_diff = time_stamps[i] - time_stamps[i-1]

            # 判断是否为瞬移
            if distance > geo_config.teleport_distance and time_diff < geo_config.teleport_time:
                teleport_events.append({
                    'from_coord': (lat1, lon1),
                    'to_coord': (lat2, lon2),
                    'distance': distance,
                    'time_diff': time_diff,
                    'speed': distance / (time_diff / 3600),  # km/h
                    'index': i
                })

        return teleport_events

    def get_coordinate_info(self, lat: float, lon: float) -> Dict:
        """
        获取坐标信息

        Args:
            lat: 纬度
            lon: 经度

        Returns:
            Dict: 坐标信息
        """
        info = {
            'lat': lat,
            'lon': lon,
            'coordinate_system': 'WGS84',
            'is_valid': self._validate_coordinate_bounds(lat, lon),
            'type': self._determine_coordinate_type(lat, lon).value,
            'boundary': self.check_boundary(lat, lon).__dict__,
            'nearest_city': self._find_nearest_city(lat, lon),
            'water_nearby': self._is_near_water(lat, lon),
            'forbidden_nearby': self._is_near_forbidden(lat, lon),
            'precision': self._check_coordinate_precision(lat, lon)
        }

        return info

    # 坐标系统转换方法
    def wgs84_to_gcj02(self, lat: float, lon: float) -> Tuple[float, float]:
        """WGS84转GCJ-02"""
        # Krasovsky 1940 ellipsoid
        a = 6378245.0
        ee = 0.00669342162296594323

        dlat = self._transform_lat(lon - 105.0, lat - 35.0)
        dlon = self._transform_lon(lon - 105.0, lat - 35.0)

        radlat = lat / 180.0 * math.pi
        magic = math.sin(radlat)
        magic = 1 - ee * magic * magic
        sqrtmagic = math.sqrt(magic)

        dlat = (dlat * 180.0) / ((a * (1 - ee)) / (magic * sqrtmagic) * math.pi)
        dlon = (dlon * 180.0) / (a / sqrtmagic * math.cos(radlat) * math.pi)

        mglat = lat + dlat
        mglon = lon + dlon

        return mglat, mglon

    def gcj02_to_wgs84(self, lat: float, lon: float) -> Tuple[float, float]:
        """GCJ-02转WGS84"""
        # 先使用WGS84转GCJ-02的逆变换
        temp_lon, temp_lat = self.wgs84_to_gcj02(lat, lon)

        return lat * 2 - temp_lat, lon * 2 - temp_lon

    def wgs84_to_bd09(self, lat: float, lon: float) -> Tuple[float, float]:
        """WGS84转BD-09"""
        # 先转为GCJ-02
        gcj_lat, gcj_lon = self.wgs84_to_gcj02(lat, lon)

        # 再转为BD-09
        return self.gcj02_to_bd09(gcj_lat, gcj_lon)

    def bd09_to_wgs84(self, lat: float, lon: float) -> Tuple[float, float]:
        """BD-09转WGS84"""
        # 先转为GCJ-02
        gcj_lat, gcj_lon = self.bd09_to_gcj09(lat, lon)

        # 再转为WGS84
        return self.gcj02_to_wgs84(gcj_lat, gcj_lon)

    def gcj02_to_bd09(self, lat: float, lon: float) -> Tuple[float, float]:
        """GCJ-02转BD-09"""
        x = lon
        y = lat

        z = math.sqrt(x * x + y * y) + 0.00002 * math.sin(y * math.pi * 3000.0 / 180.0)
        theta = math.atan2(y, x) + 0.000003 * math.cos(x * math.pi * 3000.0 / 180.0)

        bd_lon = z * math.cos(theta) + 0.0065
        bd_lat = z * math.sin(theta) + 0.006

        return bd_lat, bd_lon

    def bd09_to_gcj09(self, lat: float, lon: float) -> Tuple[float, float]:
        """BD-09转GCJ-09"""
        x = lon - 0.0065
        y = lat - 0.006

        z = math.sqrt(x * x + y * y) - 0.00002 * math.sin(y * math.pi * 3000.0 / 180.0)
        theta = math.atan2(y, x) - 0.000003 * math.cos(x * math.pi * 3000.0 / 180.0)

        gcj_lon = z * math.cos(theta)
        gcj_lat = z * math.sin(theta)

        return gcj_lat, gcj_lon

    # 私有方法
    def _validate_coordinate_bounds(self, lat: float, lon: float) -> bool:
        """验证坐标范围"""
        return (geo_config.latitude_min <= lat <= geo_config.latitude_max and
                geo_config.longitude_min <= lon <= geo_config.longitude_max)

    def _determine_coordinate_type(self, lat: float, lon: float) -> CoordinateType:
        """确定坐标类型"""
        # 检查是否在水域
        if self._is_in_water(lat, lon):
            return CoordinateType.WATER

        # 检查是否在禁区
        if self._is_in_forbidden_area(lat, lon):
            return CoordinateType.FORBIDDEN

        # 检查是否在道路上（简化处理）
        if self._is_on_road(lat, lon):
            return CoordinateType.ROAD

        return CoordinateType.NORMAL

    def _is_in_water(self, lat: float, lon: float) -> bool:
        """检查是否在水域"""
        for water_lat, water_lon in self.water_areas:
            distance = self.calculate_distance(lat, lon, water_lat, water_lon)
            if distance < 1.0:  # 1公里内
                return True
        return False

    def _is_in_forbidden_area(self, lat: float, lon: float) -> bool:
        """检查是否在禁区"""
        for forbidden_lat, forbidden_lon in self.forbidden_areas:
            distance = self.calculate_distance(lat, lon, forbidden_lat, forbidden_lon)
            if distance < 0.5:  # 500米内
                return True
        return False

    def _is_near_water(self, lat: float, lon: float) -> bool:
        """检查是否接近水域"""
        for water_lat, water_lon in self.water_areas:
            distance = self.calculate_distance(lat, lon, water_lat, water_lon)
            if distance < 2.0:  # 2公里内
                return True
        return False

    def _is_near_forbidden(self, lat: float, lon: float) -> bool:
        """检查是否接近禁区"""
        for forbidden_lat, forbidden_lon in self.forbidden_areas:
            distance = self.calculate_distance(lat, lon, forbidden_lat, forbidden_lon)
            if distance < 1.0:  # 1公里内
                return True
        return False

    def _is_on_road(self, lat: float, lon: float) -> bool:
        """检查是否在道路上（简化处理）"""
        # 这里简化处理，实际应用中应该使用路网数据
        return False

    def _find_nearest_city(self, lat: float, lon: float) -> Optional[str]:
        """查找最近的城市"""
        min_distance = float('inf')
        nearest_city = None

        for city_name, (city_lat, city_lon) in self.city_centers.items():
            distance = self.calculate_distance(lat, lon, city_lat, city_lon)
            if distance < min_distance:
                min_distance = distance
                nearest_city = city_name

        # 如果距离在合理范围内，返回最近城市
        if min_distance < 100:  # 100公里内
            return nearest_city

        return None

    def _check_coordinate_precision(self, lat: float, lon: float) -> Dict:
        """检查坐标精度"""
        result = {
            'warnings': [],
            'precision_level': 'high'
        }

        # 检查小数位数
        lat_str = str(lat)
        lon_str = str(lon)

        lat_decimals = len(lat_str.split('.')[-1]) if '.' in lat_str else 0
        lon_decimals = len(lon_str.split('.')[-1]) if '.' in lon_str else 0

        # 计算精度（米）
        lat_precision = lat_decimals * 111000  # 纬度1度约111公里
        lon_precision = lon_decimals * 111000 * math.cos(math.radians(lat))

        # 判断精度级别
        if lat_precision < 1 and lon_precision < 1:
            result['precision_level'] = 'very_high'
            result['warnings'].append('坐标精度非常高，可能为模拟数据')
        elif lat_precision < 10 and lon_precision < 10:
            result['precision_level'] = 'high'
        elif lat_precision < 100 and lon_precision < 100:
            result['precision_level'] = 'medium'
            result['warnings'].append('坐标精度较低，建议使用更高精度的定位')
        else:
            result['precision_level'] = 'low'
            result['warnings'].append('坐标精度很低，可能存在定位错误')

        result['lat_precision_meters'] = lat_precision
        result['lon_precision_meters'] = lon_precision

        return result

    def _transform_lat(self, lon: float, lat: float) -> float:
        """纬度变换参数"""
        ret = -100.0 + 2.0 * lon + 3.0 * lat + 0.2 * lat * lat + \
              0.1 * lon * lat + 0.2 * math.sqrt(math.fabs(lon))
        ret += (20.0 * math.sin(6.0 * lon * math.pi) + 20.0 * math.sin(2.0 * lon * math.pi)) * 2.0 / 3.0
        ret += (20.0 * math.sin(lat * math.pi) + 40.0 * math.sin(lat / 3.0 * math.pi)) * 2.0 / 3.0
        ret += (160.0 * math.sin(lat / 12.0 * math.pi) + 320 * math.sin(lat * math.pi / 30.0)) * 2.0 / 3.0
        return ret

    def _transform_lon(self, lon: float, lat: float) -> float:
        """经度变换参数"""
        ret = 300.0 + lon + 2.0 * lat + 0.1 * lon * lat + \
              0.1 * math.sqrt(math.fabs(lon)) + 0.1 * math.sqrt(math.fabs(lat))
        ret += (20.0 * math.sin(6.0 * lon * math.pi) + 20.0 * math.sin(2.0 * lon * math.pi)) * 2.0 / 3.0
        ret += (20.0 * math.sin(lon * math.pi) + 40.0 * math.sin(lon / 3.0 * math.pi)) * 2.0 / 3.0
        ret += (150.0 * math.sin(lon / 12.0 * math.pi) + 300.0 * math.sin(lon * math.pi / 30.0)) * 2.0 / 3.0
        return ret


# 使用示例
if __name__ == "__main__":
    # 创建坐标验证器
    validator = CoordinateValidator()

    # 测试坐标
    test_coordinates = [
        (39.9042, 116.4074),  # 北京
        (31.2304, 121.4737),  # 上海
        (23.1291, 113.2644),  # 广州
        (40.4319, 116.5704),  # 奥运村（禁区）
        (31.2304, 120.1551),  # 太湖（水域）
        (35.0, 105.0),        # 中国境内
        (0.0, 0.0),           # 赤道（无效）
    ]

    print("坐标验证结果:")
    print("-" * 60)

    for lat, lon in test_coordinates:
        result = validator.validate_coordinate(lat, lon)

        print(f"坐标: ({lat}, {lon})")
        print(f"是否有效: {result.is_valid}")
        print(f"坐标类型: {result.coordinate_type.value}")

        if result.warnings:
            print("警告:")
            for warning in result.warnings:
                print(f"  - {warning}")

        print("-" * 60)

    # 测试坐标转换
    print("\n坐标转换测试:")
    print("-" * 60)

    # WGS84转GCJ02
    wgs_lat, wgs_lon = 39.9042, 116.4074
    gcj_lat, gcj_lon = validator.wgs84_to_gcj02(wgs_lat, wgs_lon)
    print(f"WGS84: ({wgs_lat}, {wgs_lon}) -> GCJ02: ({gcj_lat:.6f}, {gcj_lon:.6f})")

    # GCJ02转BD09
    bd_lat, bd_lon = validator.gcj02_to_bd09(gcj_lat, gcj_lon)
    print(f"GCJ02: ({gcj_lat:.6f}, {gcj_lon:.6f}) -> BD09: ({bd_lat:.6f}, {bd_lon:.6f})")

    # 测试瞬移检测
    print("\n瞬移检测测试:")
    print("-" * 60)

    coordinates = [
        (39.9042, 116.4074),  # 北京
        (31.2304, 121.4737),  # 上海（瞬移）
        (31.2304, 121.4737),  # 上海
    ]
    timestamps = [1609459200, 1609459230, 1609459260]  # 30秒间隔

    teleports = validator.detect_teleport(coordinates, timestamps)
    for teleport in teleports:
        print(f"瞬移事件: 从 {teleport['from_coord']} 到 {teleport['to_coord']}")
        print(f"  距离: {teleport['distance']:.2f} km")
        print(f"  时间差: {teleport['time_diff']} 秒")
        print(f"  速度: {teleport['speed']:.2f} km/h")
        print("-" * 60)