"""
优化版检测服务 - 集成缓存和性能优化
"""
import sys
import os
import time
import uuid
import hashlib
import asyncio
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from functools import lru_cache
import threading

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from api.models.db_models import DetectionRecord, RuleConfig, KeywordLibrary
from api.models.schemas import DetectionRequest, DetectionResultData, DetectionScores, RiskLevel
from api.core.config import settings
from api.core.cache import cache, DetectionCache, CacheManager
from engine.scorer import Scorer
from models import InputRecord, GeoData, ContentData, Metadata
from config import scorer_config, geo_config as default_geo_config, text_config as default_text_config

from modules.preprocessing import DataPreprocessor, PreprocessResult
from modules.cross_validation import MultiSourceValidator, CrossValidationResult
from modules.ai_model import AIDetectionModel, ModelManager, FeatureExtractor
from modules.result_output import ResultOutputModule, ResultFormatter, AlertManager
from modules.data_management import DataManagementModule, FeatureLibrary
from modules.backend_management import SystemConfigManager


class ScorerPool:
    """
    Scorer对象池 - 避免重复创建
    """
    
    _instance = None
    _lock = threading.Lock()
    _scorers: List[Scorer] = []
    _max_pool_size = 10
    
    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance
    
    def get_scorer(self) -> Scorer:
        with self._lock:
            if self._scorers:
                return self._scorers.pop()
            # 检测服务场景启用跨请求共享状态（频率/查重/聚类）
            return Scorer(persist_state=True)
    
    def return_scorer(self, scorer: Scorer):
        with self._lock:
            if len(self._scorers) < self._max_pool_size:
                scorer.clear_history()
                self._scorers.append(scorer)


class OptimizedDetectionService:
    """
    优化版检测服务
    - 结果缓存
    - 对象池
    - 异步处理
    - 批量优化
    """

    # 检测服务实例使用跨请求共享状态，使单条检测的查重/频率/聚类生效
    _persist_state = True

    _preprocessor = None
    _cross_validator = None
    _model_manager = None
    _result_module = None
    _data_manager = None
    _config_manager = None
    _feature_library = None

    def __init__(self, db: Session, tenant_id: int):
        self.db = db
        self.tenant_id = tenant_id
        self.scorer_pool = ScorerPool.get_instance()
        
        if OptimizedDetectionService._preprocessor is None:
            OptimizedDetectionService._preprocessor = DataPreprocessor()
        
        if OptimizedDetectionService._feature_library is None:
            OptimizedDetectionService._feature_library = FeatureLibrary()
        
        if OptimizedDetectionService._model_manager is None:
            OptimizedDetectionService._model_manager = ModelManager()
            self._load_ai_model()
        
        if OptimizedDetectionService._result_module is None:
            OptimizedDetectionService._result_module = ResultOutputModule()
        
        if OptimizedDetectionService._data_manager is None:
            OptimizedDetectionService._data_manager = DataManagementModule()
        
        if OptimizedDetectionService._config_manager is None:
            OptimizedDetectionService._config_manager = SystemConfigManager()
        
        self._load_tenant_rules()
    
    def _load_tenant_rules(self):
        rules = self.db.query(RuleConfig).filter(
            RuleConfig.tenant_id == self.tenant_id,
            RuleConfig.enabled == True
        ).all()

        self._tenant_geo_config = {}
        self._tenant_text_config = {}
        self._tenant_keywords = []

        for rule in rules:
            rule_cfg = rule.rule_config if isinstance(rule.rule_config, dict) else {}
            if rule.rule_type == "geo":
                self._tenant_geo_config = rule_cfg
            elif rule.rule_type == "text":
                self._tenant_text_config = rule_cfg
                # 文本规则中允许直接配置自定义关键词
                extra_keywords = rule_cfg.get("suspicious_keywords") or []
                if isinstance(extra_keywords, list):
                    self._tenant_keywords.extend(
                        kw for kw in extra_keywords if isinstance(kw, str) and kw
                    )

        keywords = self.db.query(KeywordLibrary).filter(
            KeywordLibrary.tenant_id == self.tenant_id,
            KeywordLibrary.enabled == True
        ).all()

        if keywords:
            self._tenant_keywords.extend(k.keyword for k in keywords)

    def _apply_tenant_config(self, scorer: Scorer):
        """将租户规则应用到评分器。

        池化的 Scorer 会被不同租户复用，因此每次都必须从默认配置出发
        重新赋值，防止上一个租户的关键词/阈值泄漏到下一个租户。
        """
        text_cfg = scorer.text_engine.config
        geo_cfg = scorer.geo_engine.config

        # --- 文本规则 ---
        if self._tenant_keywords:
            text_cfg.suspicious_keywords = list(self._tenant_keywords)
        else:
            text_cfg.suspicious_keywords = list(default_text_config.suspicious_keywords)

        t = self._tenant_text_config or {}
        text_cfg.min_text_length = self._coerce(
            t.get("min_text_length"), default_text_config.min_text_length, float
        )
        text_cfg.max_text_length = self._coerce(
            t.get("max_text_length"), default_text_config.max_text_length, float
        )
        text_cfg.max_keyword_repeat = self._coerce(
            t.get("max_keyword_repeat"), default_text_config.max_keyword_repeat, int
        )

        if "simhash_threshold" in t:
            threshold = self._coerce(t.get("simhash_threshold"), None, int)
            if threshold is not None:
                scorer.simhash_detector.threshold = threshold
        if "semantic_similarity_threshold" in t:
            sim = self._coerce(t.get("semantic_similarity_threshold"), None, float)
            if sim is not None:
                scorer.semantic_cluster.similarity_threshold = sim

        # --- GEO规则 ---
        g = self._tenant_geo_config or {}
        geo_params = (
            ("teleport_distance", default_geo_config.teleport_distance, float),
            ("teleport_time", default_geo_config.teleport_time, float),
            ("max_reports_per_minute", default_geo_config.max_reports_per_minute, int),
            ("max_reports_per_hour", default_geo_config.max_reports_per_hour, int),
            ("max_high_speed", default_geo_config.max_high_speed, float),
        )
        for key, default, cast in geo_params:
            value = self._coerce(g.get(key), default, cast)
            if value is not None:
                setattr(geo_cfg, key, value)

    @staticmethod
    def _coerce(value, default, cast):
        """类型安全地读取规则配置值，非法值回落到默认"""
        if value is None:
            return default
        try:
            return cast(value)
        except (TypeError, ValueError):
            return default
    
    def _load_ai_model(self):
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        model_path = os.path.join(project_root, "models", "saved", "latest_model.joblib")
        if os.path.exists(model_path):
            try:
                OptimizedDetectionService._model_manager.load_model("default", model_path)
                OptimizedDetectionService._model_manager.set_active_model("default")
            except Exception:
                pass
    
    def _convert_request(self, request: DetectionRequest) -> InputRecord:
        geo = GeoData(
            latitude=request.geo.latitude,
            longitude=request.geo.longitude,
            accuracy=request.geo.accuracy or 10.0,
            source=request.geo.source or "GPS"
        )
        
        content = ContentData(
            text=request.content.text,
            content_type=request.content.type or "review"
        )
        
        metadata = Metadata()
        if request.metadata:
            metadata.ip = request.metadata.ip or ""
            metadata.app_version = request.metadata.app_version or "1.0.0"
            metadata.user_agent = request.metadata.user_agent or ""
        
        record = InputRecord(
            record_id=f"R_{datetime.now(timezone.utc).replace(tzinfo=None).strftime('%Y%m%d%H%M%S')}_{uuid.uuid4().hex[:8]}",
            device_id=request.device_id,
            user_id=request.user_id,
            timestamp=request.timestamp,
            geo=geo,
            content=content,
            metadata=metadata
        )
        
        return record
    
    def _poi_data_from_request(self, request: DetectionRequest) -> Dict[str, Any]:
        return {
            "name": request.content.text[:100] if request.content.text else "未知POI",
            "address": getattr(request.content, 'address', ''),
            "latitude": request.geo.latitude,
            "longitude": request.geo.longitude,
            "category": getattr(request.content, 'category', ''),
            "phone": getattr(request.content, 'phone', ''),
            "description": request.content.text
        }
    
    def detect_single(self, request: DetectionRequest, use_cache: bool = True) -> DetectionResultData:
        """
        单条检测 - 带缓存优化
        """
        start_time = time.time()
        
        poi_data = self._poi_data_from_request(request)
        
        if use_cache:
            cached_result = DetectionCache.get_result(poi_data)
            if cached_result:
                cached_result["cached"] = True
                return DetectionResultData(**cached_result)
        
        preprocess_result = OptimizedDetectionService._preprocessor.preprocess(poi_data)
        
        if not preprocess_result.is_valid:
            return DetectionResultData(
                record_id="",
                suspicion_score=100,
                risk_level="high",
                is_fake=True,
                confidence=0.95,
                scores=DetectionScores(geo_score=100, text_score=0, simhash_score=0, semantic_score=0),
                reasons=["数据格式无效: " + ", ".join(preprocess_result.errors)],
                recommendation="数据格式错误，请检查输入",
                processing_time_ms=int((time.time() - start_time) * 1000)
            )
        
        input_record = self._convert_request(request)
        
        scorer = self.scorer_pool.get_scorer()
        try:
            self._apply_tenant_config(scorer)
            base_result = scorer.analyze(input_record)
        finally:
            self.scorer_pool.return_scorer(scorer)
        
        cross_validation_result = None
        if self._should_cross_validate(poi_data):
            try:
                if OptimizedDetectionService._cross_validator is None:
                    OptimizedDetectionService._cross_validator = MultiSourceValidator()
                
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                cross_validation_result = loop.run_until_complete(
                    OptimizedDetectionService._cross_validator.validate(preprocess_result.cleaned_data)
                )
                loop.close()
            except Exception:
                pass
        
        ai_result = None
        # 统一通过 ModelManager 接口调用模型（支持 sklearn 与神经网络模型）
        try:
            context = FeatureExtractor.context_from_rule_result(base_result, input_record)
            context["platform_consistency"] = (
                cross_validation_result.confidence if cross_validation_result else 0.0
            )
            ai_result = OptimizedDetectionService._model_manager.predict_with_active(
                preprocess_result.cleaned_data, context
            )
        except Exception:
            ai_result = None
        
        final_result = self._merge_results(
            base_result, 
            cross_validation_result, 
            ai_result,
            preprocess_result
        )
        
        final_result.update({
            "geo_score": base_result.geo_score,
            "text_score": base_result.text_score,
            "simhash_score": base_result.simhash_score,
            "semantic_score": base_result.semantic_score,
            "details": {
                **base_result.details,
                "fusion_sources": final_result.get("fusion_sources", {}),
            },
        })
        db_record = self._save_record(input_record, final_result)
        
        processing_time = int((time.time() - start_time) * 1000)
        
        result_data = {
            "record_id": db_record.record_id,
            "suspicion_score": final_result.get("suspicion_score", base_result.suspicion_score),
            "risk_level": final_result.get("risk_level", base_result.risk_level),
            "is_fake": final_result.get("is_fake", base_result.is_fake),
            "confidence": final_result.get("confidence", self._calculate_confidence(base_result)),
            "scores": {
                "geo_score": base_result.geo_score,
                "text_score": base_result.text_score,
                "simhash_score": base_result.simhash_score,
                "semantic_score": base_result.semantic_score,
                "neural_score": base_result.details.get("neural_score"),
            },
            "reasons": final_result.get("reasons", base_result.reasons),
            "recommendation": final_result.get("recommendation", self._get_recommendation(base_result.risk_level)),
            "processing_time_ms": processing_time
        }
        
        if use_cache:
            DetectionCache.set_result(poi_data, result_data, ttl=1800)
        
        return DetectionResultData(**result_data)
    
    def _should_cross_validate(self, poi_data: Dict[str, Any]) -> bool:
        """
        判断是否需要交叉验证
        """
        if poi_data.get("latitude") and poi_data.get("longitude"):
            return True
        return False
    
    # 交叉验证风险等级到分数的映射（用于置信度加权融合）
    _CV_SCORE_MAP = {"high": 85.0, "medium": 55.0, "low": 15.0}
    # AI模型标签到分数的映射
    _AI_SCORE_MAP = {"fake": 90.0, "suspicious": 55.0, "real": 10.0}

    def _calculate_source_weights(self, sources: List[Dict[str, Any]]) -> List[float]:
        """
        计算各来源的融合权重。

        权重 = 来源可靠性 × 来源置信度，归一化后返回。
        可靠性来自 scorer_config.source_reliability，可按各来源的
        历史准确率持续调整。
        """
        reliabilities = scorer_config.source_reliability
        raw_weights = []
        for source in sources:
            reliability = reliabilities.get(source["name"], 0.5)
            confidence = max(float(source["confidence"]), 0.1)
            raw_weights.append(reliability * confidence)

        total = sum(raw_weights)
        if total <= 0:
            return [1.0 / len(sources)] * len(sources)
        return [w / total for w in raw_weights]

    def _fuse_confidence(self, sources: List[Dict[str, Any]],
                         weights: List[float]) -> float:
        """
        融合多来源置信度。

        多来源结论一致时给予一致性加成，结论分歧时进行惩罚，
        避免在不一致的证据上输出过高的置信度。
        """
        fused = sum(w * s["confidence"] for w, s in zip(weights, sources))
        fused = min(max(fused, 0.0), 1.0)

        n = len(sources)
        if n > 1:
            if all(s["is_fake"] == sources[0]["is_fake"] for s in sources[1:]):
                # 全体一致：最多+20%加成
                fused = min(fused * (1 + 0.1 * (n - 1)), 0.99)
            else:
                # 存在分歧：衰减
                fused = fused * 0.85
        return round(fused, 4)

    def _merge_results(
        self,
        base_result,
        cross_validation: Optional[CrossValidationResult],
        ai_result: Optional[Dict[str, Any]],
        preprocess_result: PreprocessResult
    ) -> Dict[str, Any]:
        """基于置信度的多来源加权融合，替代硬编码分数调整。

        各来源提供 (分数, 置信度, 是否虚假投票)，按可靠性×置信度加权
        融合出最终分数与结论。规则引擎发现的高严重度异常（瞬移、无效
        坐标等硬证据）不允许被其他来源投票推翻。
        """
        base_confidence = base_result.details.get(
            "confidence", self._calculate_confidence(base_result)
        )
        sources = [{
            "name": "rules",
            "score": float(base_result.suspicion_score),
            "confidence": float(base_confidence),
            "is_fake": bool(base_result.is_fake),
        }]
        reasons = list(base_result.reasons)

        if cross_validation is not None:
            cv_score = self._CV_SCORE_MAP.get(cross_validation.risk_level, 30.0)
            sources.append({
                "name": "cross_validation",
                "score": cv_score,
                "confidence": float(cross_validation.confidence or 0.0),
                "is_fake": cross_validation.risk_level in ("high", "medium"),
            })
            reasons.extend(cross_validation.risk_reasons)

        if ai_result:
            ai_label = ai_result.get("label")
            sources.append({
                "name": "ai_model",
                "score": self._AI_SCORE_MAP.get(ai_label, 30.0),
                "confidence": float(ai_result.get("confidence") or 0.0),
                "is_fake": ai_label == "fake",
            })
            reasons.extend(ai_result.get("risk_factors") or [])

        weights = self._calculate_source_weights(sources)
        fused_score = sum(w * s["score"] for w, s in zip(weights, sources))

        # 高严重度异常属于硬证据，直接维持规则引擎的虚假判定
        hard_evidence = bool(base_result.details.get("high_severity_hit"))
        if hard_evidence:
            is_fake = True
        else:
            fake_weight = sum(w for w, s in zip(weights, sources) if s["is_fake"])
            # 加权多数投票；规则引擎之外无其他来源时维持规则结论
            is_fake = fake_weight >= 0.5

        risk_level = self._determine_risk_level_from_score(fused_score)
        if hard_evidence:
            risk_level = "high"
        elif is_fake and risk_level == "low":
            risk_level = "medium"

        confidence = self._fuse_confidence(sources, weights)

        if preprocess_result.warnings:
            reasons.extend(preprocess_result.warnings)

        # 去重并保持原始顺序
        reasons = list(dict.fromkeys(r for r in reasons if r))

        label = "fake" if is_fake else ("real" if fused_score < 30 else "suspicious")

        return {
            "suspicion_score": round(fused_score, 2),
            "risk_level": risk_level,
            "is_fake": is_fake,
            "confidence": confidence,
            "reasons": reasons,
            "label": label,
            "recommendation": self._get_recommendation(risk_level),
            "fusion_sources": {
                s["name"]: {"weight": round(w, 4), "score": s["score"]}
                for w, s in zip(weights, sources)
            },
        }

    def _determine_risk_level_from_score(self, score: float) -> str:
        if score >= scorer_config.high_risk_threshold:
            return "high"
        elif score >= scorer_config.medium_risk_threshold:
            return "medium"
        return "low"
    
    def detect_batch(self, requests: List[DetectionRequest], 
                     enable_clustering: bool = True,
                     use_cache: bool = True) -> Dict[str, Any]:
        """
        批量检测 - 优化版
        """
        start_time = time.time()
        
        cached_results = {}
        uncached_requests = []
        uncached_indices = []
        
        if use_cache:
            for i, req in enumerate(requests):
                poi_data = self._poi_data_from_request(req)
                cached = DetectionCache.get_result(poi_data)
                if cached:
                    cached_results[i] = cached
                else:
                    uncached_requests.append(req)
                    uncached_indices.append(i)
        else:
            uncached_requests = requests
            uncached_indices = list(range(len(requests)))
        
        input_records = [self._convert_request(req) for req in uncached_requests]
        
        scorer = self.scorer_pool.get_scorer()
        try:
            self._apply_tenant_config(scorer)

            if enable_clustering and len(input_records) > 10:
                batch_result = scorer.analyze_batch_with_clustering(input_records)
            else:
                batch_result = scorer.analyze_batch(input_records)
        finally:
            self.scorer_pool.return_scorer(scorer)
        
        db_records = []
        merged_results = []
        for input_record, request, result in zip(input_records, uncached_requests, batch_result.results):
            ai_result = None
            try:
                poi_data = self._poi_data_from_request(request)
                context = FeatureExtractor.context_from_rule_result(result, input_record)
                ai_result = OptimizedDetectionService._model_manager.predict_with_active(
                    poi_data, context
                )
            except Exception:
                ai_result = None
            preprocess_result = PreprocessResult(
                is_valid=True,
                cleaned_data=self._poi_data_from_request(request),
                warnings=[],
                errors=[],
            )
            merged = self._merge_results(result, None, ai_result, preprocess_result)
            merged.update({
                "geo_score": result.geo_score,
                "text_score": result.text_score,
                "simhash_score": result.simhash_score,
                "semantic_score": result.semantic_score,
                "details": result.details,
            })
            db_record = self._save_record(input_record, merged)
            db_records.append(db_record)
            merged_results.append(merged)
        
        all_results = [None] * len(requests)
        
        for i, cached in cached_results.items():
            all_results[i] = {
                "record_id": cached.get("record_id", ""),
                "suspicion_score": cached["suspicion_score"],
                "risk_level": cached["risk_level"],
                "is_fake": cached["is_fake"],
                "scores": cached["scores"],
                "reasons": cached["reasons"][:5],
                "cached": True
            }
        
        for idx, (db_record, result, merged) in enumerate(
            zip(db_records, batch_result.results, merged_results)
        ):
            original_idx = uncached_indices[idx]
            all_results[original_idx] = {
                "record_id": db_record.record_id,
                "suspicion_score": merged["suspicion_score"],
                "risk_level": merged["risk_level"],
                "is_fake": merged["is_fake"],
                "scores": {
                    "geo_score": result.geo_score,
                    "text_score": result.text_score,
                    "simhash_score": result.simhash_score,
                    "semantic_score": result.semantic_score,
                    "neural_score": result.details.get("neural_score") if isinstance(result.details, dict) else None,
                },
                "reasons": merged["reasons"][:5],
                "confidence": merged["confidence"],
            }
            
            if use_cache:
                poi_data = self._poi_data_from_request(requests[original_idx])
                DetectionCache.set_result(poi_data, all_results[original_idx], ttl=1800)
        
        processing_time = int((time.time() - start_time) * 1000)
        
        fake_count = sum(1 for r in all_results if r and r.get("is_fake"))
        high_risk = sum(1 for r in all_results if r and r.get("risk_level") == "high")
        medium_risk = sum(1 for r in all_results if r and r.get("risk_level") == "medium")
        
        return {
            "summary": {
                "total": len(all_results),
                "fake_count": fake_count,
                "normal_count": len(all_results) - fake_count,
                "high_risk_count": high_risk,
                "medium_risk_count": medium_risk,
                "low_risk_count": len(all_results) - high_risk - medium_risk,
                "cache_hits": len(cached_results)
            },
            "results": all_results,
            "processing_time_ms": processing_time
        }
    
    def _save_record(self, input_record: InputRecord, result) -> DetectionRecord:
        content_hash = hashlib.sha256(input_record.content.text.encode()).hexdigest()
        
        if isinstance(result, dict):
            suspicion_score = result.get("suspicion_score", 0)
            risk_level = result.get("risk_level", "low")
            is_fake = result.get("is_fake", False)
            geo_score = result.get("geo_score", 0)
            text_score = result.get("text_score", 0)
            simhash_score = result.get("simhash_score", 0)
            semantic_score = result.get("semantic_score", 0)
            reasons = result.get("reasons", [])
            details = result.get("details", {})
        else:
            suspicion_score = result.suspicion_score
            risk_level = result.risk_level
            is_fake = result.is_fake
            geo_score = result.geo_score
            text_score = result.text_score
            simhash_score = result.simhash_score
            semantic_score = result.semantic_score
            reasons = result.reasons
            details = result.details
        
        db_record = DetectionRecord(
            record_id=input_record.record_id,
            tenant_id=self.tenant_id,
            device_id=input_record.device_id,
            user_id=input_record.user_id,
            timestamp=input_record.timestamp,
            latitude=input_record.geo.latitude,
            longitude=input_record.geo.longitude,
            accuracy=input_record.geo.accuracy,
            geo_source=input_record.geo.source,
            content_text=input_record.content.text,
            content_type=input_record.content.content_type,
            content_hash=content_hash,
            ip_address=input_record.metadata.ip,
            app_version=input_record.metadata.app_version,
            user_agent=input_record.metadata.user_agent,
            suspicion_score=suspicion_score,
            risk_level=risk_level,
            is_fake=is_fake,
            geo_score=geo_score,
            text_score=text_score,
            simhash_score=simhash_score,
            semantic_score=semantic_score,
            reasons=reasons,
            details=details,
            review_status="pending"
        )
        
        self.db.add(db_record)
        self.db.commit()
        self.db.refresh(db_record)
        
        return db_record
    
    def _calculate_confidence(self, result) -> float:
        score = result.suspicion_score
        if score >= 90 or score <= 10:
            return 0.95
        elif score >= 80 or score <= 20:
            return 0.85
        elif score >= 70 or score <= 30:
            return 0.75
        else:
            return 0.65
    
    def _get_recommendation(self, risk_level: str) -> str:
        recommendations = {
            "high": "建议立即拦截，高风险虚假内容",
            "medium": "建议人工复核，可疑内容",
            "low": "正常内容，可放行"
        }
        return recommendations.get(risk_level, "需要进一步分析")
    
    def get_record(self, record_id: str) -> Optional[DetectionRecord]:
        return self.db.query(DetectionRecord).filter(
            DetectionRecord.record_id == record_id,
            DetectionRecord.tenant_id == self.tenant_id
        ).first()
    
    def get_records(self, page: int, page_size: int, filters: dict = None) -> tuple:
        query = self.db.query(DetectionRecord).filter(
            DetectionRecord.tenant_id == self.tenant_id
        )
        
        if filters:
            if filters.get("device_id"):
                query = query.filter(DetectionRecord.device_id == filters["device_id"])
            if filters.get("user_id"):
                query = query.filter(DetectionRecord.user_id == filters["user_id"])
            if filters.get("risk_level"):
                query = query.filter(DetectionRecord.risk_level == filters["risk_level"])
            if filters.get("review_status"):
                query = query.filter(DetectionRecord.review_status == filters["review_status"])
            if filters.get("start_date"):
                query = query.filter(DetectionRecord.created_at >= filters["start_date"])
            if filters.get("end_date"):
                query = query.filter(DetectionRecord.created_at <= filters["end_date"])
            if filters.get("keyword"):
                keyword = f"%{filters['keyword']}%"
                query = query.filter(DetectionRecord.content_text.ilike(keyword))
        
        total = query.count()
        records = query.order_by(DetectionRecord.created_at.desc()).offset(
            (page - 1) * page_size
        ).limit(page_size).all()
        
        return records, total
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """
        获取缓存统计
        """
        return cache.get_stats()


DetectionService = OptimizedDetectionService