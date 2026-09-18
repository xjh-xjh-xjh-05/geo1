"""
AI智能检测模型模块
"""
import os
import json
import math
from typing import Optional, Dict, Any, List, Tuple
from dataclasses import dataclass, field
from datetime import datetime
import numpy as np


HYBRID_FEATURE_SCHEMA_VERSION = "hybrid-v1"

try:
    from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
    from sklearn.model_selection import train_test_split
    from sklearn.preprocessing import StandardScaler
    from sklearn.metrics import accuracy_score, classification_report
    import joblib
    HAS_SKLEARN = True
except ImportError:
    HAS_SKLEARN = False
    RandomForestClassifier = None
    GradientBoostingClassifier = None
    train_test_split = None
    StandardScaler = None
    accuracy_score = None
    classification_report = None
    joblib = None


@dataclass
class FeatureVector:
    spatial_density: float = 0.0
    category_clustering: float = 0.0
    coordinate_offset: float = 0.0
    name_length: int = 0
    address_completeness: float = 0.0
    marketing_ratio: float = 0.0
    upload_frequency: float = 0.0
    multi_platform_consistency: float = 0.0
    authoritative_match: float = 0.0
    text_similarity: float = 0.0


@dataclass
class DetectionResult:
    label: str
    confidence: float
    probabilities: Dict[str, float]
    feature_importance: Dict[str, float]
    risk_factors: List[str]


class FeatureExtractor:
    """
    多维度特征提取器
    """
    
    def __init__(self):
        self.marketing_keywords = [
            "全网第一", "全国最好", "顶级", "极致", "完美",
            "绝佳", "免费", "赠送", "优惠", "折扣",
            "限时", "特价", "促销", "最低", "最高"
        ]
    
    def extract_features(
        self,
        poi_data: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> FeatureVector:
        """提取训练和线上推理共用的十维特征。

        ``context`` 可由规则评分器提供混合检测结果；缺失字段使用
        可解释的零值/默认值，确保训练和服务端输入维度始终一致。
        """
        features = FeatureVector()
        
        features.spatial_density = self._calculate_spatial_density(
            poi_data, context.get("nearby_pois", []) if context else []
        )
        
        features.category_clustering = self._calculate_category_clustering(
            poi_data, context.get("nearby_pois", []) if context else []
        )
        
        features.coordinate_offset = self._calculate_coordinate_offset(poi_data)
        
        features.name_length = len(poi_data.get("name", ""))
        
        features.address_completeness = self._calculate_address_completeness(
            poi_data.get("address", "")
        )
        
        features.marketing_ratio = self._calculate_marketing_ratio(
            poi_data.get("name", "") + " " + poi_data.get("description", "")
        )
        
        features.upload_frequency = self._calculate_upload_frequency(
            context.get("upload_history", []) if context else []
        )
        
        features.multi_platform_consistency = context.get("platform_consistency", 0.0) if context else 0.0
        
        features.authoritative_match = context.get("authoritative_match", 0.0) if context else 0.0
        
        features.text_similarity = self._calculate_text_similarity(
            poi_data, context.get("similar_pois", []) if context else []
        )
        
        return features

    def to_array(self, features: FeatureVector) -> np.ndarray:
        """按固定契约转换为模型输入数组。"""
        return np.asarray([
            features.spatial_density,
            features.category_clustering,
            features.coordinate_offset / 1000.0,
            features.name_length / 100.0,
            features.address_completeness,
            features.marketing_ratio,
            features.upload_frequency,
            features.multi_platform_consistency,
            features.authoritative_match,
            features.text_similarity,
        ], dtype=np.float32)

    def extract_array(
        self,
        poi_data: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None,
    ) -> np.ndarray:
        return self.to_array(self.extract_features(poi_data, context))

    @staticmethod
    def feature_schema() -> Dict[str, Any]:
        return {
            "version": HYBRID_FEATURE_SCHEMA_VERSION,
            "names": [
                "geo_score", "text_score", "simhash_score", "semantic_score",
                "text_length_norm", "marketing_ratio", "coordinate_valid",
                "high_severity_hit", "rule_confidence", "similar_record_count",
            ],
        }

    @staticmethod
    def context_from_rule_result(result, record: Any = None) -> Dict[str, Any]:
        """将 Scorer 结果转换为可供模型复用的上下文。"""
        details = getattr(result, "details", {}) or {}
        return {
            "rule_result": result,
            "geo_score": float(getattr(result, "geo_score", 0.0)),
            "text_score": float(getattr(result, "text_score", 0.0)),
            "simhash_score": float(getattr(result, "simhash_score", 0.0)),
            "semantic_score": float(getattr(result, "semantic_score", 0.0)),
            "rule_confidence": float(details.get("confidence", 0.5)),
            "semantic_backend": details.get("semantic_backend", "unknown"),
            "coordinate_offset": float(details.get("coordinate_offset", 0.0)),
            "text_similarity": float(details.get("text_similarity", 0.0)),
            "upload_history": details.get("upload_history", []),
            "platform_consistency": float(details.get("platform_consistency", 0.0)),
            "authoritative_match": float(details.get("authoritative_match", 0.0)),
            "nearby_pois": details.get("nearby_pois", []),
            "similar_pois": details.get("similar_pois", []),
        }

    def _calculate_spatial_density(self, poi_data: Dict[str, Any], nearby_pois: List[Dict[str, Any]]) -> float:
        if not nearby_pois:
            return 0.0
        
        lat = poi_data.get("latitude", 0)
        lon = poi_data.get("longitude", 0)
        
        if lat == 0 and lon == 0:
            return 0.0
        
        radius = 1000
        nearby_count = 0
        
        for poi in nearby_pois:
            poi_lat = poi.get("latitude", 0)
            poi_lon = poi.get("longitude", 0)
            
            if poi_lat and poi_lon:
                dist = self._haversine_distance(lat, lon, poi_lat, poi_lon)
                if dist <= radius:
                    nearby_count += 1
        
        density = nearby_count / (math.pi * (radius / 1000) ** 2)
        return min(density / 100, 1.0)
    
    def _calculate_category_clustering(self, poi_data: Dict[str, Any], nearby_pois: List[Dict[str, Any]]) -> float:
        if not nearby_pois:
            return 0.0
        
        category = poi_data.get("category", "")
        if not category:
            return 0.0
        
        same_category_count = sum(
            1 for poi in nearby_pois 
            if poi.get("category") == category
        )
        
        return same_category_count / len(nearby_pois)
    
    def _calculate_coordinate_offset(self, poi_data: Dict[str, Any]) -> float:
        if "cross_validation" in poi_data:
            return poi_data["cross_validation"].get("coordinate_offset", 0.0)
        return 0.0
    
    def _calculate_address_completeness(self, address: str) -> float:
        if not address:
            return 0.0
        
        components = {
            "province": any(p in address for p in ["省", "市", "自治区", "特别行政区"]),
            "city": "市" in address or "县" in address,
            "district": any(d in address for d in ["区", "县"]),
            "street": any(s in address for s in ["路", "街", "道", "巷"]),
            "number": any(n in address for n in ["号", "栋", "座", "层"])
        }
        
        return sum(components.values()) / len(components)
    
    def _calculate_marketing_ratio(self, text: str) -> float:
        if not text:
            return 0.0
        
        text_lower = text.lower()
        count = sum(1 for kw in self.marketing_keywords if kw in text_lower)
        
        return count / len(self.marketing_keywords)
    
    def _calculate_upload_frequency(self, upload_history: List[Dict[str, Any]]) -> float:
        if not upload_history:
            return 0.0
        
        if len(upload_history) < 2:
            return 0.0
        
        now = datetime.now()
        from datetime import timedelta
        one_hour_ago = now - timedelta(hours=1)
        
        recent_uploads = sum(
            1 for record in upload_history
            if record.get("timestamp", 0) > one_hour_ago.timestamp()
        )
        
        return min(recent_uploads / 100, 1.0)
    
    def _calculate_text_similarity(self, poi_data: Dict[str, Any], similar_pois: List[Dict[str, Any]]) -> float:
        if not similar_pois:
            return 0.0
        
        name = poi_data.get("name", "")
        if not name:
            return 0.0
        
        from difflib import SequenceMatcher
        
        similarities = []
        for poi in similar_pois:
            other_name = poi.get("name", "")
            if other_name:
                sim = SequenceMatcher(None, name, other_name).ratio()
                similarities.append(sim)
        
        return max(similarities) if similarities else 0.0
    
    def _haversine_distance(self, lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        R = 6371000
        
        phi1 = math.radians(lat1)
        phi2 = math.radians(lat2)
        delta_phi = math.radians(lat2 - lat1)
        delta_lambda = math.radians(lon2 - lon1)
        
        a = math.sin(delta_phi / 2) ** 2 + \
            math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        
        return R * c


class AIDetectionModel:
    """
    AI检测模型
    """
    
    def __init__(self, model_type: str = "random_forest"):
        self.model_type = model_type
        self.model = None
        self.scaler = StandardScaler() if HAS_SKLEARN else None
        self.feature_extractor = FeatureExtractor()
        self.feature_names = FeatureExtractor.feature_schema()["names"]
        self.label_mapping = {0: "real", 1: "fake"}
        self.is_trained = False
        self.last_metrics: Dict[str, Any] = {}
        self.feature_schema_version = HYBRID_FEATURE_SCHEMA_VERSION
        self.semantic_backend = "unknown"

    def _vectorize(self, poi_data: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> np.ndarray:
        return self.feature_array(poi_data, context).reshape(1, -1)

    def feature_array(self, poi_data: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> np.ndarray:
        """构造线上和训练共用的十维混合特征。"""
        context = context or {}
        actual_backend = context.get("semantic_backend", "unknown")
        if (
            self.semantic_backend not in ("unknown", actual_backend)
            and actual_backend != "unknown"
        ):
            raise ValueError(
                f"语义特征后端不匹配: 模型={self.semantic_backend}, 推理={actual_backend}"
            )
        rule_result = context.get("rule_result")
        details = getattr(rule_result, "details", {}) if rule_result is not None else {}
        text = str(poi_data.get("description", poi_data.get("name", "")) or "")
        geo_score = float(context.get("geo_score", getattr(rule_result, "geo_score", 0.0)))
        text_score = float(context.get("text_score", getattr(rule_result, "text_score", 0.0)))
        simhash_score = float(context.get("simhash_score", getattr(rule_result, "simhash_score", 0.0)))
        semantic_score = float(context.get("semantic_score", getattr(rule_result, "semantic_score", 0.0)))
        return np.asarray([
            geo_score / 100.0,
            text_score / 100.0,
            simhash_score / 100.0,
            semantic_score / 100.0,
            min(len(text) / 500.0, 1.0),
            self.feature_extractor._calculate_marketing_ratio(text),
            1.0 if self._valid_coordinate(poi_data) else 0.0,
            1.0 if details.get("high_severity_hit") else 0.0,
            min(float(context.get("rule_confidence", details.get("confidence", 0.5))), 1.0),
            min(float(details.get("similar_record_count", 0.0)) / 10.0, 1.0),
        ], dtype=np.float32)

    @staticmethod
    def _valid_coordinate(poi_data: Dict[str, Any]) -> bool:
        latitude = float(poi_data.get("latitude", 0.0) or 0.0)
        longitude = float(poi_data.get("longitude", 0.0) or 0.0)
        return 18.0 <= latitude <= 54.0 and 73.0 <= longitude <= 135.0

    def train(
        self,
        X: np.ndarray,
        y: np.ndarray,
        test_size: float = 0.2,
        random_state: int = 42,
    ) -> Dict[str, Any]:
        if not HAS_SKLEARN:
            return {"error": "sklearn未安装，无法训练模型"}
        
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=test_size, random_state=random_state,
            stratify=y if len(np.unique(y)) > 1 else None,
        )
        
        X_train_scaled = self.scaler.fit_transform(X_train)
        X_test_scaled = self.scaler.transform(X_test)
        
        if self.model_type == "random_forest":
            self.model = RandomForestClassifier(
                n_estimators=200,
                max_depth=10,
                class_weight="balanced",
                random_state=random_state,
                n_jobs=-1
            )
        elif self.model_type == "gradient_boosting":
            self.model = GradientBoostingClassifier(
                n_estimators=100,
                max_depth=5,
                random_state=42
            )
        else:
            raise ValueError(f"不支持的模型类型: {self.model_type}")
        
        self.model.fit(X_train_scaled, y_train)
        
        y_pred = self.model.predict(X_test_scaled)
        
        present_labels = sorted(np.unique(y_test).tolist())
        target_names = [self.label_mapping[int(label)] for label in present_labels]
        metrics = {
            "accuracy": accuracy_score(y_test, y_pred),
            "classification_report": classification_report(
                y_test, y_pred,
                labels=present_labels,
                target_names=target_names,
                output_dict=True,
                zero_division=0,
            )
        }
        
        self.is_trained = True
        self.last_metrics = metrics
        return metrics
    
    def predict(self, poi_data: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> DetectionResult:
        if not self.is_trained or not HAS_SKLEARN:
            return DetectionResult(
                label="unknown",
                confidence=0.0,
                probabilities={},
                feature_importance={},
                risk_factors=["模型未训练" if not self.is_trained else "sklearn未安装"]
            )
        
        feature_vector = self.feature_array(poi_data, context).reshape(1, -1)

        feature_vector_scaled = self.scaler.transform(feature_vector)
        
        prediction = self.model.predict(feature_vector_scaled)[0]
        probabilities = self.model.predict_proba(feature_vector_scaled)[0]
        
        label = self.label_mapping.get(prediction, "unknown")
        confidence = float(max(probabilities))
        
        prob_dict = {
            self.label_mapping[i]: float(prob) 
            for i, prob in enumerate(probabilities)
        }
        
        feature_importance = self._get_feature_importance()
        
        risk_factors = []
        if context:
            rule_result = context.get("rule_result")
            if rule_result is not None:
                risk_factors.extend(getattr(rule_result, "reasons", [])[:3])

        return DetectionResult(
            label=label,
            confidence=confidence,
            probabilities=prob_dict,
            feature_importance=feature_importance,
            risk_factors=risk_factors
        )
    
    def predict_batch(
        self, 
        poi_list: List[Dict[str, Any]],
        contexts: Optional[List[Dict[str, Any]]] = None
    ) -> List[DetectionResult]:
        results = []
        for i, poi in enumerate(poi_list):
            context = contexts[i] if contexts and i < len(contexts) else None
            result = self.predict(poi, context)
            results.append(result)
        return results
    
    def _get_feature_importance(self) -> Dict[str, float]:
        if not self.is_trained or not hasattr(self.model, 'feature_importances_'):
            return {}
        
        importances = self.model.feature_importances_
        return {
            name: float(importance) 
            for name, importance in zip(self.feature_names, importances)
        }
    
    def _identify_risk_factors(self, features: FeatureVector, probabilities: np.ndarray) -> List[str]:
        risk_factors = []
        
        if features.marketing_ratio > 0.3:
            risk_factors.append(f"营销词占比过高: {features.marketing_ratio:.1%}")
        
        if features.address_completeness < 0.4:
            risk_factors.append(f"地址信息不完整: {features.address_completeness:.1%}")
        
        if features.coordinate_offset > 500:
            risk_factors.append(f"坐标偏移过大: {features.coordinate_offset:.0f}米")
        
        if features.multi_platform_consistency < 0.3:
            risk_factors.append("多平台一致性低")
        
        if features.upload_frequency > 0.8:
            risk_factors.append("上传频率异常")
        
        if features.text_similarity > 0.9:
            risk_factors.append("与已知POI高度相似")
        
        return risk_factors
    
    def save(self, filepath: str):
        if not HAS_SKLEARN:
            raise RuntimeError("sklearn未安装，无法保存模型")
        
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        
        model_data = {
            "model": self.model,
            "scaler": self.scaler,
            "model_type": self.model_type,
            "feature_names": self.feature_names,
            "feature_schema": FeatureExtractor.feature_schema(),
            "feature_schema_version": self.feature_schema_version,
            "semantic_backend": self.semantic_backend,
            "label_mapping": self.label_mapping,
            "is_trained": self.is_trained,
            "last_metrics": self.last_metrics,
            "saved_at": datetime.now().isoformat()
        }
        
        joblib.dump(model_data, filepath)
    
    def load(self, filepath: str):
        if not HAS_SKLEARN:
            raise RuntimeError("sklearn未安装，无法加载模型")
        
        model_data = joblib.load(filepath)
        
        self.model = model_data["model"]
        self.scaler = model_data["scaler"]
        self.model_type = model_data["model_type"]
        self.feature_names = model_data["feature_names"]
        saved_schema = model_data.get("feature_schema_version")
        if saved_schema != HYBRID_FEATURE_SCHEMA_VERSION:
            raise ValueError(
                f"模型特征版本不兼容: {saved_schema} != {HYBRID_FEATURE_SCHEMA_VERSION}"
            )
        expected_names = FeatureExtractor.feature_schema()["names"]
        if model_data.get("feature_names") != expected_names:
            raise ValueError("模型特征顺序与当前代码不兼容")
        self.feature_schema_version = saved_schema
        self.semantic_backend = model_data.get("semantic_backend", "unknown")
        self.label_mapping = model_data["label_mapping"]
        self.is_trained = model_data["is_trained"]
        self.last_metrics = model_data.get("last_metrics", {})


class ModelManager:
    """
    模型管理器
    """
    
    def __init__(self, models_dir: str = "models/saved"):
        self.models_dir = models_dir
        self.models: Dict[str, Any] = {}  # Can be AIDetectionModel or NeuralScorer
        self.model_types: Dict[str, str] = {}  # "sklearn" or "neural"
        self.active_model: Optional[str] = None
        
        os.makedirs(models_dir, exist_ok=True)
    
    def register_model(self, name: str, model, model_type: str = "sklearn"):
        self.models[name] = model
        self.model_types[name] = model_type
    
    def register_neural_model(self, name: str, neural_scorer):
        """注册神经网络模型"""
        self.models[name] = neural_scorer
        self.model_types[name] = "neural"
    
    def set_active_model(self, name: str):
        if name in self.models:
            self.active_model = name
        else:
            raise ValueError(f"模型不存在: {name}")
    
    def get_active_model(self) -> Optional[Any]:
        if self.active_model:
            return self.models.get(self.active_model)
        return None
    
    def get_active_model_type(self) -> Optional[str]:
        """获取当前活跃模型的类型"""
        if self.active_model:
            return self.model_types.get(self.active_model)
        return None
    
    def save_model(self, name: str, filename: Optional[str] = None) -> str:
        if name not in self.models:
            raise ValueError(f"模型不存在: {name}")
        
        model = self.models[name]
        model_type = self.model_types.get(name, "sklearn")
        
        if not filename:
            filename = f"{name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.joblib"
        
        filepath = os.path.join(self.models_dir, filename)
        
        if model_type == "sklearn":
            model.save(filepath)
        elif model_type == "neural":
            # Neural model uses torch.save
            try:
                import torch
                os.makedirs(os.path.dirname(filepath), exist_ok=True)
                torch.save(model.model.state_dict(), filepath.replace('.joblib', '.pt'))
                filepath = filepath.replace('.joblib', '.pt')
            except ImportError:
                raise RuntimeError("PyTorch未安装，无法保存神经网络模型")
        
        return filepath
    
    def load_model(self, name: str, filepath: str, model_type: str = "sklearn"):
        if model_type == "sklearn":
            model = AIDetectionModel()
            model.load(filepath)
            self.models[name] = model
            self.model_types[name] = "sklearn"
        elif model_type == "neural":
            try:
                from engine.neural_model import NeuralScorer, NeuralConfig
                scorer = NeuralScorer(NeuralConfig())
                import torch
                scorer.model.load_state_dict(torch.load(filepath, map_location=scorer.model.device))
                scorer.model.using_fallback = False
                self.models[name] = scorer
                self.model_types[name] = "neural"
            except ImportError:
                raise RuntimeError("PyTorch未安装，无法加载神经网络模型")
    
    def list_models(self) -> List[Dict[str, Any]]:
        return [
            {
                "name": name,
                "is_trained": model.is_trained if hasattr(model, 'is_trained') else True,
                "model_type": self.model_types.get(name, "unknown"),
                "is_active": name == self.active_model
            }
            for name, model in self.models.items()
        ]
    
    def predict_with_active(self, poi_data: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        """使用活跃模型进行预测（统一接口）"""
        model = self.get_active_model()
        if not model:
            return None
        
        model_type = self.get_active_model_type()
        
        if model_type == "sklearn":
            if not model.is_trained:
                return None
            result = model.predict(poi_data, context)
            return {
                "label": result.label,
                "confidence": result.confidence,
                "risk_factors": result.risk_factors,
                "model_type": "sklearn"
            }
        elif model_type == "neural":
            # 未加载有效权重的神经网络模型不参与预测（内部会随机输出）
            if not getattr(model, "is_trained", False):
                return None
            # Neural model needs InputRecord
            try:
                from models import InputRecord, GeoData, ContentData
                record = InputRecord(
                    record_id=poi_data.get("record_id", ""),
                    device_id=poi_data.get("device_id", ""),
                    user_id=poi_data.get("user_id", ""),
                    timestamp=poi_data.get("timestamp", 0),
                    geo=GeoData(
                        latitude=poi_data.get("latitude", 0),
                        longitude=poi_data.get("longitude", 0)
                    ),
                    content=ContentData(
                        text=poi_data.get("description", poi_data.get("name", ""))
                    )
                )
                result = model.analyze(record)
                return {
                    "label": "fake" if result.is_fake else "real",
                    "confidence": result.suspicion_score / 100.0,
                    "risk_factors": result.reasons,
                    "model_type": "neural"
                }
            except Exception:
                return None
        
        return None


def create_sample_training_data(n_samples: int = 1000) -> Tuple[np.ndarray, np.ndarray]:
    """
    创建示例训练数据
    """
    np.random.seed(42)
    
    X = np.random.rand(n_samples, 10)
    
    y = np.zeros(n_samples, dtype=int)

    for i in range(n_samples):
        if X[i, 0] > 0.6 or X[i, 1] > 0.6 or X[i, 2] > 0.6:
            y[i] = 1

    return X, y
