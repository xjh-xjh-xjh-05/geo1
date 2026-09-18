"""
数据管理与特征库模块
"""
import os
import json
import hashlib
from typing import Optional, Dict, Any, List, Tuple
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import uuid


class FeatureType(str, Enum):
    SPATIAL = "spatial"
    TEXT = "text"
    BEHAVIOR = "behavior"
    CONSISTENCY = "consistency"


class SampleLabel(str, Enum):
    REAL = "real"
    FAKE = "fake"
    SUSPICIOUS = "suspicious"


@dataclass
class FakeFeature:
    feature_id: str
    feature_type: FeatureType
    name: str
    description: str
    patterns: List[str]
    weight: float
    is_active: bool = True
    created_at: str = ""
    updated_at: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SampleData:
    sample_id: str
    poi_data: Dict[str, Any]
    label: SampleLabel
    features: Dict[str, Any]
    source: str
    annotator: str
    created_at: str
    verified: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class DetectionLog:
    log_id: str
    poi_id: str
    poi_name: str
    result: str
    confidence: float
    violations: List[str]
    detection_time: str
    user_id: str
    processing_time_ms: float
    metadata: Dict[str, Any] = field(default_factory=dict)


class FeatureLibrary:
    """
    GEO虚假信息特征库
    """
    
    def __init__(self, storage_path: str = "data/features"):
        self.storage_path = storage_path
        self.features: Dict[str, FakeFeature] = {}
        self.type_index: Dict[FeatureType, List[str]] = {
            ft: [] for ft in FeatureType
        }
        
        os.makedirs(storage_path, exist_ok=True)
        self._load_features()
    
    def _load_features(self):
        """
        加载已保存的特征
        """
        filepath = os.path.join(self.storage_path, "features.json")
        if os.path.exists(filepath):
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    for item in data.get("features", []):
                        feature = FakeFeature(
                            feature_id=item["feature_id"],
                            feature_type=FeatureType(item["feature_type"]),
                            name=item["name"],
                            description=item["description"],
                            patterns=item["patterns"],
                            weight=item["weight"],
                            is_active=item.get("is_active", True),
                            created_at=item.get("created_at", ""),
                            updated_at=item.get("updated_at", ""),
                            metadata=item.get("metadata", {})
                        )
                        self.features[feature.feature_id] = feature
                        self.type_index[feature.feature_type].append(feature.feature_id)
            except Exception as e:
                pass
        
        if not self.features:
            self._initialize_default_features()
    
    def _initialize_default_features(self):
        """
        初始化默认特征
        """
        default_features = [
            FakeFeature(
                feature_id=str(uuid.uuid4()),
                feature_type=FeatureType.SPATIAL,
                name="坐标异常偏移",
                description="POI坐标与实际位置存在明显偏移",
                patterns=[
                    "坐标偏移超过500米",
                    "坐标落在水域或禁区",
                    "坐标与地址不匹配"
                ],
                weight=0.8,
                created_at=datetime.now().isoformat()
            ),
            FakeFeature(
                feature_id=str(uuid.uuid4()),
                feature_type=FeatureType.SPATIAL,
                name="网格状分布",
                description="多个POI呈现规律性网格分布",
                patterns=[
                    "POI间距高度一致",
                    "坐标小数位规律",
                    "批量投喂特征"
                ],
                weight=0.9,
                created_at=datetime.now().isoformat()
            ),
            FakeFeature(
                feature_id=str(uuid.uuid4()),
                feature_type=FeatureType.TEXT,
                name="营销词堆砌",
                description="名称或描述中包含大量营销词汇",
                patterns=[
                    "全网第一", "全国最好", "顶级", "极致",
                    "免费", "赠送", "限时优惠"
                ],
                weight=0.7,
                created_at=datetime.now().isoformat()
            ),
            FakeFeature(
                feature_id=str(uuid.uuid4()),
                feature_type=FeatureType.TEXT,
                name="模板化内容",
                description="内容高度相似，疑似模板生成",
                patterns=[
                    "名称高度相似",
                    "地址格式完全一致",
                    "描述文本重复"
                ],
                weight=0.85,
                created_at=datetime.now().isoformat()
            ),
            FakeFeature(
                feature_id=str(uuid.uuid4()),
                feature_type=FeatureType.BEHAVIOR,
                name="批量上传",
                description="短时间内大量上传相似POI",
                patterns=[
                    "1小时内上传超过50条",
                    "同一账号高频操作",
                    "IP地址集中"
                ],
                weight=0.9,
                created_at=datetime.now().isoformat()
            ),
            FakeFeature(
                feature_id=str(uuid.uuid4()),
                feature_type=FeatureType.CONSISTENCY,
                name="单平台独有",
                description="仅单个平台存在，其他平台无记录",
                patterns=[
                    "高德无记录",
                    "百度无记录",
                    "OSM无记录",
                    "天地图无记录"
                ],
                weight=0.75,
                created_at=datetime.now().isoformat()
            ),
            FakeFeature(
                feature_id=str(uuid.uuid4()),
                feature_type=FeatureType.CONSISTENCY,
                name="信息矛盾",
                description="不同平台信息存在明显矛盾",
                patterns=[
                    "类别完全不符",
                    "地址差异过大",
                    "名称不匹配"
                ],
                weight=0.8,
                created_at=datetime.now().isoformat()
            )
        ]
        
        for feature in default_features:
            self.features[feature.feature_id] = feature
            self.type_index[feature.feature_type].append(feature.feature_id)
        
        self._save_features()
    
    def _save_features(self):
        """
        保存特征到文件
        """
        filepath = os.path.join(self.storage_path, "features.json")
        data = {
            "features": [
                {
                    "feature_id": f.feature_id,
                    "feature_type": f.feature_type.value,
                    "name": f.name,
                    "description": f.description,
                    "patterns": f.patterns,
                    "weight": f.weight,
                    "is_active": f.is_active,
                    "created_at": f.created_at,
                    "updated_at": f.updated_at,
                    "metadata": f.metadata
                }
                for f in self.features.values()
            ],
            "updated_at": datetime.now().isoformat()
        }
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    
    def add_feature(self, feature: FakeFeature) -> str:
        """
        添加新特征
        """
        if not feature.feature_id:
            feature.feature_id = str(uuid.uuid4())
        
        feature.created_at = datetime.now().isoformat()
        feature.updated_at = feature.created_at
        
        self.features[feature.feature_id] = feature
        self.type_index[feature.feature_type].append(feature.feature_id)
        
        self._save_features()
        return feature.feature_id
    
    def update_feature(self, feature_id: str, updates: Dict[str, Any]) -> bool:
        """
        更新特征
        """
        if feature_id not in self.features:
            return False
        
        feature = self.features[feature_id]
        
        if "name" in updates:
            feature.name = updates["name"]
        if "description" in updates:
            feature.description = updates["description"]
        if "patterns" in updates:
            feature.patterns = updates["patterns"]
        if "weight" in updates:
            feature.weight = updates["weight"]
        if "is_active" in updates:
            feature.is_active = updates["is_active"]
        if "metadata" in updates:
            feature.metadata.update(updates["metadata"])
        
        feature.updated_at = datetime.now().isoformat()
        
        self._save_features()
        return True
    
    def delete_feature(self, feature_id: str) -> bool:
        """
        删除特征
        """
        if feature_id not in self.features:
            return False
        
        feature = self.features[feature_id]
        self.type_index[feature.feature_type].remove(feature_id)
        del self.features[feature_id]
        
        self._save_features()
        return True
    
    def get_feature(self, feature_id: str) -> Optional[FakeFeature]:
        """
        获取单个特征
        """
        return self.features.get(feature_id)
    
    def get_features_by_type(self, feature_type: FeatureType) -> List[FakeFeature]:
        """
        按类型获取特征
        """
        return [
            self.features[fid] 
            for fid in self.type_index[feature_type]
            if fid in self.features
        ]
    
    def get_all_features(self, active_only: bool = True) -> List[FakeFeature]:
        """
        获取所有特征
        """
        features = list(self.features.values())
        if active_only:
            features = [f for f in features if f.is_active]
        return features
    
    def match_patterns(self, text: str) -> List[Dict[str, Any]]:
        """
        匹配文本中的特征模式
        """
        matches = []
        
        for feature in self.features.values():
            if not feature.is_active:
                continue
            
            for pattern in feature.patterns:
                if pattern.lower() in text.lower():
                    matches.append({
                        "feature_id": feature.feature_id,
                        "feature_name": feature.name,
                        "feature_type": feature.feature_type.value,
                        "matched_pattern": pattern,
                        "weight": feature.weight
                    })
        
        return matches


class SampleDataset:
    """
    样本数据集管理
    """
    
    def __init__(self, storage_path: str = "data/samples"):
        self.storage_path = storage_path
        self.samples: Dict[str, SampleData] = {}
        self.label_index: Dict[SampleLabel, List[str]] = {
            sl: [] for sl in SampleLabel
        }
        
        os.makedirs(storage_path, exist_ok=True)
        self._load_samples()
    
    def _load_samples(self):
        """
        加载已保存的样本
        """
        filepath = os.path.join(self.storage_path, "samples.json")
        if os.path.exists(filepath):
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    for item in data.get("samples", []):
                        sample = SampleData(
                            sample_id=item["sample_id"],
                            poi_data=item["poi_data"],
                            label=SampleLabel(item["label"]),
                            features=item.get("features", {}),
                            source=item.get("source", "unknown"),
                            annotator=item.get("annotator", "system"),
                            created_at=item.get("created_at", ""),
                            verified=item.get("verified", False),
                            metadata=item.get("metadata", {})
                        )
                        self.samples[sample.sample_id] = sample
                        self.label_index[sample.label].append(sample.sample_id)
            except Exception as e:
                pass
    
    def _save_samples(self):
        """
        保存样本到文件
        """
        filepath = os.path.join(self.storage_path, "samples.json")
        data = {
            "samples": [
                {
                    "sample_id": s.sample_id,
                    "poi_data": s.poi_data,
                    "label": s.label.value,
                    "features": s.features,
                    "source": s.source,
                    "annotator": s.annotator,
                    "created_at": s.created_at,
                    "verified": s.verified,
                    "metadata": s.metadata
                }
                for s in self.samples.values()
            ],
            "updated_at": datetime.now().isoformat()
        }
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    
    def add_sample(
        self,
        poi_data: Dict[str, Any],
        label: SampleLabel,
        features: Optional[Dict[str, Any]] = None,
        source: str = "manual",
        annotator: str = "user"
    ) -> str:
        """
        添加样本
        """
        sample_id = str(uuid.uuid4())
        
        sample = SampleData(
            sample_id=sample_id,
            poi_data=poi_data,
            label=label,
            features=features or {},
            source=source,
            annotator=annotator,
            created_at=datetime.now().isoformat()
        )
        
        self.samples[sample_id] = sample
        self.label_index[label].append(sample_id)
        
        self._save_samples()
        return sample_id
    
    def update_sample_label(self, sample_id: str, new_label: SampleLabel) -> bool:
        """
        更新样本标签
        """
        if sample_id not in self.samples:
            return False
        
        sample = self.samples[sample_id]
        old_label = sample.label
        
        self.label_index[old_label].remove(sample_id)
        
        sample.label = new_label
        self.label_index[new_label].append(sample_id)
        
        self._save_samples()
        return True
    
    def delete_sample(self, sample_id: str) -> bool:
        """
        删除样本
        """
        if sample_id not in self.samples:
            return False
        
        sample = self.samples[sample_id]
        self.label_index[sample.label].remove(sample_id)
        del self.samples[sample_id]
        
        self._save_samples()
        return True
    
    def get_sample(self, sample_id: str) -> Optional[SampleData]:
        """
        获取单个样本
        """
        return self.samples.get(sample_id)
    
    def get_samples_by_label(self, label: SampleLabel) -> List[SampleData]:
        """
        按标签获取样本
        """
        return [
            self.samples[sid] 
            for sid in self.label_index[label]
            if sid in self.samples
        ]
    
    def get_training_data(self) -> Tuple[List[Dict[str, Any]], List[str]]:
        """
        获取训练数据
        """
        X = []
        y = []
        
        for sample in self.samples.values():
            if sample.verified:
                X.append(sample.features)
                y.append(sample.label.value)
        
        return X, y
    
    def get_statistics(self) -> Dict[str, Any]:
        """
        获取样本统计信息
        """
        total = len(self.samples)
        if total == 0:
            return {"total": 0}
        
        verified = sum(1 for s in self.samples.values() if s.verified)
        
        return {
            "total": total,
            "verified": verified,
            "unverified": total - verified,
            "by_label": {
                label.value: len(ids) 
                for label, ids in self.label_index.items()
            },
            "by_source": self._count_by_source()
        }
    
    def _count_by_source(self) -> Dict[str, int]:
        counts = {}
        for sample in self.samples.values():
            counts[sample.source] = counts.get(sample.source, 0) + 1
        return counts


class DetectionLogger:
    """
    检测日志管理
    """
    
    def __init__(self, storage_path: str = "data/logs"):
        self.storage_path = storage_path
        self.logs: List[DetectionLog] = []
        self.max_memory_logs = 10000
        
        os.makedirs(storage_path, exist_ok=True)
    
    def log_detection(
        self,
        poi_id: str,
        poi_name: str,
        result: str,
        confidence: float,
        violations: List[str],
        user_id: str = "anonymous",
        processing_time_ms: float = 0.0,
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        记录检测结果
        """
        log_id = str(uuid.uuid4())
        
        log = DetectionLog(
            log_id=log_id,
            poi_id=poi_id,
            poi_name=poi_name,
            result=result,
            confidence=confidence,
            violations=violations,
            detection_time=datetime.now().isoformat(),
            user_id=user_id,
            processing_time_ms=processing_time_ms,
            metadata=metadata or {}
        )
        
        self.logs.append(log)
        
        if len(self.logs) > self.max_memory_logs:
            self._flush_to_disk()
        
        return log_id
    
    def _flush_to_disk(self):
        """
        将日志刷新到磁盘
        """
        if not self.logs:
            return
        
        filename = f"detection_logs_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        filepath = os.path.join(self.storage_path, filename)
        
        data = {
            "logs": [
                {
                    "log_id": log.log_id,
                    "poi_id": log.poi_id,
                    "poi_name": log.poi_name,
                    "result": log.result,
                    "confidence": log.confidence,
                    "violations": log.violations,
                    "detection_time": log.detection_time,
                    "user_id": log.user_id,
                    "processing_time_ms": log.processing_time_ms,
                    "metadata": log.metadata
                }
                for log in self.logs
            ]
        }
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        self.logs = []
    
    def get_logs(
        self,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        result: Optional[str] = None,
        user_id: Optional[str] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        获取日志
        """
        filtered = self.logs
        
        if start_time:
            filtered = [l for l in filtered if l.detection_time >= start_time]
        if end_time:
            filtered = [l for l in filtered if l.detection_time <= end_time]
        if result:
            filtered = [l for l in filtered if l.result == result]
        if user_id:
            filtered = [l for l in filtered if l.user_id == user_id]
        
        return [
            {
                "log_id": log.log_id,
                "poi_id": log.poi_id,
                "poi_name": log.poi_name,
                "result": log.result,
                "confidence": log.confidence,
                "violations": log.violations,
                "detection_time": log.detection_time,
                "user_id": log.user_id,
                "processing_time_ms": log.processing_time_ms
            }
            for log in filtered[:limit]
        ]
    
    def get_statistics(
        self,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        获取统计信息
        """
        logs = self.logs
        
        if start_time:
            logs = [l for l in logs if l.detection_time >= start_time]
        if end_time:
            logs = [l for l in logs if l.detection_time <= end_time]
        
        total = len(logs)
        if total == 0:
            return {"total": 0}
        
        result_counts = {}
        for log in logs:
            result_counts[log.result] = result_counts.get(log.result, 0) + 1
        
        avg_confidence = sum(l.confidence for l in logs) / total
        avg_processing_time = sum(l.processing_time_ms for l in logs) / total
        
        return {
            "total": total,
            "result_distribution": result_counts,
            "average_confidence": avg_confidence,
            "average_processing_time_ms": avg_processing_time,
            "fake_ratio": result_counts.get("fake", 0) / total,
            "suspicious_ratio": result_counts.get("suspicious", 0) / total
        }


class DataManagementModule:
    """
    数据管理模块主类
    """
    
    def __init__(self, data_path: str = "data"):
        self.feature_library = FeatureLibrary(os.path.join(data_path, "features"))
        self.sample_dataset = SampleDataset(os.path.join(data_path, "samples"))
        self.detection_logger = DetectionLogger(os.path.join(data_path, "logs"))
    
    def get_overview(self) -> Dict[str, Any]:
        """
        获取数据概览
        """
        return {
            "features": {
                "total": len(self.feature_library.features),
                "by_type": {
                    ft.value: len(ids) 
                    for ft, ids in self.feature_library.type_index.items()
                }
            },
            "samples": self.sample_dataset.get_statistics(),
            "logs": self.detection_logger.get_statistics()
        }
    
    def add_feedback(
        self,
        poi_data: Dict[str, Any],
        user_label: str,
        feedback_type: str = "correction",
        annotator: str = "user"
    ) -> Dict[str, Any]:
        """
        添加用户反馈
        """
        label = SampleLabel(user_label) if user_label in [s.value for s in SampleLabel] else SampleLabel.SUSPICIOUS
        
        sample_id = self.sample_dataset.add_sample(
            poi_data=poi_data,
            label=label,
            source=feedback_type,
            annotator=annotator
        )
        
        return {
            "sample_id": sample_id,
            "label": label.value,
            "status": "added"
        }
    
    def export_training_data(self, filepath: str) -> bool:
        """
        导出训练数据
        """
        try:
            X, y = self.sample_dataset.get_training_data()
            
            data = {
                "features": X,
                "labels": y,
                "exported_at": datetime.now().isoformat(),
                "total_samples": len(X)
            }
            
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            
            return True
        except Exception as e:
            return False
