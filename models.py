"""
数据模型定义
"""
from dataclasses import dataclass, field
from typing import Optional, List, Dict
from datetime import datetime
import json


@dataclass
class GeoData:
    """地理数据"""
    latitude: float
    longitude: float
    accuracy: float = 10.0  # 精度（米）
    source: str = "GPS"     # GPS/WIFI/CELL

    def to_dict(self) -> Dict:
        return {
            'latitude': self.latitude,
            'longitude': self.longitude,
            'accuracy': self.accuracy,
            'source': self.source
        }


@dataclass
class ContentData:
    """内容数据"""
    text: str
    content_type: str = "review"  # review/checkin/poi

    def to_dict(self) -> Dict:
        return {
            'text': self.text,
            'type': self.content_type
        }


@dataclass
class Metadata:
    """元数据"""
    ip: str = ""
    app_version: str = "1.0.0"
    user_agent: str = ""

    def to_dict(self) -> Dict:
        return {
            'ip': self.ip,
            'app_version': self.app_version,
            'user_agent': self.user_agent
        }


@dataclass
class InputRecord:
    """输入记录"""
    record_id: str
    device_id: str
    user_id: str
    timestamp: float
    geo: GeoData
    content: ContentData
    metadata: Metadata = field(default_factory=Metadata)
    label: Optional[str] = None  # 用于标注：normal/fake

    def to_dict(self) -> Dict:
        return {
            'record_id': self.record_id,
            'device_id': self.device_id,
            'user_id': self.user_id,
            'timestamp': self.timestamp,
            'geo': self.geo.to_dict(),
            'content': self.content.to_dict(),
            'metadata': self.metadata.to_dict(),
            'label': self.label
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)


@dataclass
class DetectionResult:
    """检测结果"""
    record_id: str
    suspicion_score: float      # 0-100
    is_fake: bool
    risk_level: str             # low/medium/high

    # 各维度分数
    geo_score: float = 0.0
    text_score: float = 0.0
    simhash_score: float = 0.0
    semantic_score: float = 0.0

    # 异常原因
    reasons: List[str] = field(default_factory=list)

    # 详细信息
    details: Dict = field(default_factory=dict)

    # 相似记录数
    similar_records: int = 0

    def to_dict(self) -> Dict:
        return {
            'record_id': self.record_id,
            'suspicion_score': self.suspicion_score,
            'is_fake': self.is_fake,
            'risk_level': self.risk_level,
            'reasons': self.reasons,
            'details': {
                'geo_score': self.geo_score,
                'text_score': self.text_score,
                'simhash_score': self.simhash_score,
                'semantic_score': self.semantic_score,
                'similar_records': self.similar_records
            }
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)


@dataclass
class BatchDetectionResult:
    """批量检测结果"""
    total_count: int
    fake_count: int
    normal_count: int
    suspicious_count: int
    results: List[DetectionResult]

    # 统计信息
    statistics: Dict = field(default_factory=dict)

    def to_dict(self) -> Dict:
        return {
            'summary': {
                'total': self.total_count,
                'fake': self.fake_count,
                'normal': self.normal_count,
                'suspicious': self.suspicious_count
            },
            'statistics': self.statistics,
            'results': [r.to_dict() for r in self.results]
        }
