"""
GEO规则引擎
"""
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass, field, replace
from collections import OrderedDict, deque
import threading

import sys
sys.path.insert(0, '..')
from config import geo_config
from utils.geo_utils import (
    calculate_distance, is_in_china, validate_coordinate,
    calculate_speed, is_teleport, Coordinate
)
from utils.scoring import combine_severities
from models import InputRecord


class SharedFrequencyCache:
    """
    跨请求共享的设备上报频率缓存（有界、线程安全）。

    池化的 Scorer 在请求结束后会清空内部状态，如果频率检测只依赖
    实例内缓存，单条检测路径下永远无法累积到触发阈值。此缓存以
    device_id 为键保留最近的上报时间戳，使线上单条检测也能进行
    高频上报检测。
    """

    def __init__(self, max_devices: int = 5000, max_per_device: int = 200):
        self._devices: "OrderedDict[str, deque]" = OrderedDict()
        self._lock = threading.Lock()
        self._max_devices = max_devices
        self._max_per_device = max_per_device

    def add_and_count(self, device_id: str, timestamp: float) -> Tuple[int, int]:
        """记录一次上报，返回 (最近1小时次数, 最近1分钟次数)"""
        with self._lock:
            dq = self._devices.get(device_id)
            if dq is None:
                dq = deque(maxlen=self._max_per_device)
                self._devices[device_id] = dq
                if len(self._devices) > self._max_devices:
                    self._devices.popitem(last=False)
            else:
                self._devices.move_to_end(device_id)
            dq.append(timestamp)
            hour_count = sum(1 for t in dq if t > timestamp - 3600)
            minute_count = sum(1 for t in dq if t > timestamp - 60)
            return hour_count, minute_count

    def clear(self):
        with self._lock:
            self._devices.clear()


class SharedLocationCache:
    """
    跨请求共享的设备最近位置缓存（有界、线程安全）。

    使单条检测路径也能进行瞬移/超速检测：同一设备短时间内
    跨越长距离会被识别，无论两次上报是否在同一个请求/批次内。
    """

    def __init__(self, max_devices: int = 5000):
        self._locations: "OrderedDict[str, Tuple[float, float, float]]" = OrderedDict()
        self._lock = threading.Lock()
        self._max_devices = max_devices

    def get_and_set(self, device_id: str, lat: float, lon: float,
                    timestamp: float) -> Optional[Tuple[float, float, float]]:
        """记录当前位置并返回该设备的上一个位置（不存在时返回None）"""
        with self._lock:
            previous = self._locations.get(device_id)
            self._locations[device_id] = (lat, lon, timestamp)
            self._locations.move_to_end(device_id)
            if len(self._locations) > self._max_devices:
                self._locations.popitem(last=False)
            return previous

    def clear(self):
        with self._lock:
            self._locations.clear()


@dataclass
class GeoAnomaly:
    """GEO异常"""
    anomaly_type: str
    description: str
    severity: float  # 0-1
    details: Dict = field(default_factory=dict)


class GeoRuleEngine:
    """GEO规则引擎"""

    def __init__(self, config=None, persist_frequency: bool = False,
                 shared_frequency_cache: Optional[SharedFrequencyCache] = None,
                 shared_location_cache: Optional[SharedLocationCache] = None):
        # 每个引擎实例持有配置副本，避免修改实例配置时污染全局单例
        self.config = config if config is not None else replace(geo_config)
        self.records_cache = {}  # 实例内缓存（批次内频率检测）
        self._last_positions: Dict[str, Tuple[float, float, float]] = {}  # 实例内最近位置
        self.persist_frequency = persist_frequency
        # 共享缓存：池化/长生命周期场景下跨请求保留设备上报历史与位置
        self.shared_frequency_cache = shared_frequency_cache
        self.shared_location_cache = shared_location_cache

    def analyze(self, record: InputRecord) -> Tuple[float, List[GeoAnomaly]]:
        """
        分析单条记录

        Args:
            record: 输入记录

        Returns:
            (异常分数, 异常列表)
        """
        anomalies = []

        # 1. 坐标合法性检测
        anomaly = self._check_coordinate_validity(record)
        if anomaly:
            anomalies.append(anomaly)

        # 2. 坐标范围检测
        anomaly = self._check_coordinate_range(record)
        if anomaly:
            anomalies.append(anomaly)

        # 3. 高频检测
        anomaly = self._check_frequency(record)
        if anomaly:
            anomalies.append(anomaly)

        # 4. 设备移动检测（瞬移/超速，基于该设备上一次上报位置）
        anomaly = self._check_device_movement(record)
        if anomaly:
            anomalies.append(anomaly)

        # 计算异常分数：概率并集合并，异常越多分数越高
        if anomalies:
            score = combine_severities([a.severity for a in anomalies])
        else:
            score = 0.0

        return score, anomalies

    def analyze_trajectory(self, records: List[InputRecord]) -> List[Tuple[str, float, List[GeoAnomaly]]]:
        """
        分析轨迹（多记录）

        移动检测已内置于 analyze()（基于设备的上一次上报位置），
        按时间排序逐条调用即可得到轨迹级检测。

        Args:
            records: 输入记录列表（按时间排序）

        Returns:
            [(record_id, 异常分数, 异常列表)]
        """
        results = []

        # 按时间排序
        sorted_records = sorted(records, key=lambda r: r.timestamp)

        for record in sorted_records:
            score, anomalies = self.analyze(record)
            results.append((record.record_id, score, anomalies))

        return results

    def _get_and_set_last_position(self, record: InputRecord) -> Optional[Tuple[float, float, float]]:
        """取回并更新设备的最近位置；坐标无效时不参与移动检测也不污染位置链"""
        lat, lon = record.geo.latitude, record.geo.longitude
        is_valid, _ = validate_coordinate(lat, lon)
        if not is_valid or (lat == 0 and lon == 0):
            return None

        if self.shared_location_cache is not None:
            return self.shared_location_cache.get_and_set(
                record.device_id, lat, lon, record.timestamp
            )

        previous = self._last_positions.get(record.device_id)
        self._last_positions[record.device_id] = (lat, lon, record.timestamp)
        return previous

    def _check_device_movement(self, record: InputRecord) -> Optional[GeoAnomaly]:
        """检测设备移动异常（瞬移/超速），与该设备上一次上报位置比较"""
        if not record.device_id:
            return None

        previous = self._get_and_set_last_position(record)
        if previous is None:
            return None

        return self._check_movement_between(previous, record)

    def _check_movement_between(self, previous: Tuple[float, float, float],
                                record: InputRecord) -> Optional[GeoAnomaly]:
        """比较上一位置与当前位置，检测瞬移或超速"""
        prev_coord = Coordinate(previous[0], previous[1], previous[2])
        curr_coord = Coordinate(
            record.geo.latitude, record.geo.longitude, record.timestamp
        )

        if is_teleport(
            prev_coord, curr_coord,
            max_distance=self.config.teleport_distance,
            max_time=self.config.teleport_time
        ):
            distance = calculate_distance(prev_coord, curr_coord)
            time_diff = abs(record.timestamp - previous[2])

            return GeoAnomaly(
                anomaly_type="teleport",
                description=f"检测到瞬移: {distance:.1f}公里/{time_diff:.0f}秒",
                severity=0.9,
                details={
                    "distance_km": distance,
                    "time_seconds": time_diff,
                    "speed_kmh": calculate_speed(prev_coord, curr_coord)
                }
            )

        speed = calculate_speed(prev_coord, curr_coord)
        if speed > self.config.max_high_speed:
            return GeoAnomaly(
                anomaly_type="excessive_speed",
                description=f"移动速度异常: {speed:.1f}km/h",
                severity=0.6,
                details={"speed_kmh": speed, "threshold": self.config.max_high_speed}
            )

        return None

    def _check_teleport(self, prev_record: InputRecord, curr_record: InputRecord) -> Optional[GeoAnomaly]:
        """检测瞬移（保留旧接口，内部走统一的移动检测逻辑）"""
        return self._check_movement_between(
            (prev_record.geo.latitude, prev_record.geo.longitude, prev_record.timestamp),
            curr_record,
        )

    def _check_coordinate_validity(self, record: InputRecord) -> GeoAnomaly:
        """检测坐标合法性"""
        is_valid, error = validate_coordinate(
            record.geo.latitude,
            record.geo.longitude
        )

        if not is_valid:
            return GeoAnomaly(
                anomaly_type="invalid_coordinate",
                description=error,
                severity=1.0,
                details={"latitude": record.geo.latitude, "longitude": record.geo.longitude}
            )
        return None

    def _check_coordinate_range(self, record: InputRecord) -> GeoAnomaly:
        """检测坐标是否在合理范围内（中国境内）"""
        lat, lon = record.geo.latitude, record.geo.longitude

        # 检查是否在中国境内
        if not is_in_china(lat, lon):
            # 判断是否在国内边界附近（允许一定误差）
            lat_diff = min(abs(lat - self.config.latitude_min),
                          abs(lat - self.config.latitude_max))
            lon_diff = min(abs(lon - self.config.longitude_min),
                          abs(lon - self.config.longitude_max))

            # 如果差距很大，说明确实是境外坐标
            if lat_diff > 5 and lon_diff > 5:
                return GeoAnomaly(
                    anomaly_type="out_of_range",
                    description=f"坐标超出中国境内范围: ({lat}, {lon})",
                    severity=0.8,
                    details={"latitude": lat, "longitude": lon}
                )
        return None

    def _check_frequency(self, record: InputRecord) -> Optional[GeoAnomaly]:
        """检测上报频率"""
        device_id = record.device_id
        current_time = record.timestamp

        # 优先使用共享缓存（跨请求生效），否则使用实例内缓存（批次内生效）
        if self.shared_frequency_cache is not None:
            recent_count, recent_minute_count = self.shared_frequency_cache.add_and_count(
                device_id, current_time
            )
        else:
            if device_id not in self.records_cache:
                self.records_cache[device_id] = []

            # 添加当前记录，只保留最近1小时的记录
            self.records_cache[device_id].append(current_time)
            one_hour_ago = current_time - 3600
            self.records_cache[device_id] = [
                t for t in self.records_cache[device_id] if t > one_hour_ago
            ]

            recent_count = len(self.records_cache[device_id])
            one_minute_ago = current_time - 60
            recent_minute_count = sum(
                1 for t in self.records_cache[device_id] if t > one_minute_ago
            )

        if recent_minute_count > self.config.max_reports_per_minute:
            return GeoAnomaly(
                anomaly_type="high_frequency_minute",
                description=f"设备每分钟上报次数异常: {recent_minute_count}次",
                severity=0.7,
                details={"count": recent_minute_count, "threshold": self.config.max_reports_per_minute}
            )

        if recent_count > self.config.max_reports_per_hour:
            return GeoAnomaly(
                anomaly_type="high_frequency_hour",
                description=f"设备每小时上报次数异常: {recent_count}次",
                severity=0.5,
                details={"count": recent_count, "threshold": self.config.max_reports_per_hour}
            )

        return None

    def clear_cache(self):
        """清空实例内缓存（共享缓存的清理需显式调用 clear_shared）"""
        self.records_cache.clear()
        self._last_positions.clear()

    def clear_shared(self):
        """清空共享频率与位置缓存"""
        if self.shared_frequency_cache is not None:
            self.shared_frequency_cache.clear()
        if self.shared_location_cache is not None:
            self.shared_location_cache.clear()
