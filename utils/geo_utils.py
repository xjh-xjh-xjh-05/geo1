"""
地理计算工具函数
"""
import math
from typing import Tuple, Optional
from dataclasses import dataclass


@dataclass
class Coordinate:
    """坐标点"""
    latitude: float
    longitude: float
    timestamp: Optional[float] = None


def calculate_distance(coord1: Coordinate, coord2: Coordinate) -> float:
    """
    计算两个坐标点之间的距离（公里）
    使用Haversine公式

    Args:
        coord1: 第一个坐标点
        coord2: 第二个坐标点

    Returns:
        距离（公里）
    """
    lat1, lon1 = math.radians(coord1.latitude), math.radians(coord1.longitude)
    lat2, lon2 = math.radians(coord2.latitude), math.radians(coord2.longitude)

    dlat = lat2 - lat1
    dlon = lon2 - lon1

    a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    c = 2 * math.asin(math.sqrt(a))

    # 地球半径（公里）
    R = 6371.0

    return R * c


def is_in_china(latitude: float, longitude: float) -> bool:
    """
    判断坐标是否在中国境内

    Args:
        latitude: 纬度
        longitude: 经度

    Returns:
        是否在中国境内
    """
    # 简化判断，使用矩形范围
    # 实际应用中可使用更精确的边界数据
    return (18.0 <= latitude <= 54.0 and
            73.0 <= longitude <= 135.0)


def validate_coordinate(latitude: float, longitude: float) -> Tuple[bool, str]:
    """
    验证坐标是否合法

    Args:
        latitude: 纬度
        longitude: 经度

    Returns:
        (是否合法, 错误信息)
    """
    if not (-90 <= latitude <= 90):
        return False, f"纬度超出范围: {latitude}"

    if not (-180 <= longitude <= 180):
        return False, f"经度超出范围: {longitude}"

    return True, ""


def calculate_speed(coord1: Coordinate, coord2: Coordinate) -> float:
    """
    计算两点间的移动速度（km/h）

    Args:
        coord1: 起点坐标（需包含timestamp）
        coord2: 终点坐标（需包含timestamp）

    Returns:
        速度（km/h），如果无法计算返回0
    """
    if coord1.timestamp is None or coord2.timestamp is None:
        return 0.0

    distance = calculate_distance(coord1, coord2)
    time_diff = abs(coord2.timestamp - coord1.timestamp)

    if time_diff == 0:
        return float('inf') if distance > 0 else 0.0

    # 转换为小时
    time_hours = time_diff / 3600.0

    if time_hours == 0:
        return float('inf')

    return distance / time_hours


def is_teleport(coord1: Coordinate, coord2: Coordinate,
                max_distance: float = 100.0, max_time: float = 60.0) -> bool:
    """
    判断是否为瞬移（短时间内跨越长距离）

    Args:
        coord1: 起点坐标
        coord2: 终点坐标
        max_distance: 最大合理距离（公里）
        max_time: 最大合理时间（秒）

    Returns:
        是否为瞬移
    """
    if coord1.timestamp is None or coord2.timestamp is None:
        return False

    distance = calculate_distance(coord1, coord2)
    time_diff = abs(coord2.timestamp - coord1.timestamp)

    # 短时间内跨越长距离
    if distance > max_distance and time_diff < max_time:
        return True

    return False
