"""
综合评分模块
"""
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass

import sys
sys.path.insert(0, '..')
from config import scorer_config, text_config
from models import InputRecord, DetectionResult, BatchDetectionResult
from engine.geo_rules import GeoRuleEngine, GeoAnomaly, SharedFrequencyCache, SharedLocationCache
from engine.text_rules import TextRuleEngine, TextAnomaly
from engine.simhash_dup import SimHashDetector, SimilarityResult, SharedFingerprintStore
from engine.semantic_cluster import SemanticCluster, ClusterResult, SharedEmbeddingStore
from engine.neural_model import NeuralScorer

# 跨请求共享状态：使单条检测路径下的频率/移动/查重/聚类检测真正生效
_SHARED_FREQUENCY_CACHE = SharedFrequencyCache()
_SHARED_LOCATION_CACHE = SharedLocationCache()
_SHARED_FINGERPRINTS = SharedFingerprintStore()
_SHARED_EMBEDDINGS = SharedEmbeddingStore()


class Scorer:
    """综合评分器"""

    def __init__(self, config=None, persist_state: bool = False):
        """
        Args:
            config: 评分配置
            persist_state: 是否使用跨请求共享状态（线上服务场景开启；
                批次隔离场景如训练/评测保持关闭）
        """
        self.config = config or scorer_config
        self.geo_engine = GeoRuleEngine(
            persist_frequency=persist_state,
            shared_frequency_cache=_SHARED_FREQUENCY_CACHE if persist_state else None,
            shared_location_cache=_SHARED_LOCATION_CACHE if persist_state else None,
        )
        self.text_engine = TextRuleEngine()
        self.simhash_detector = SimHashDetector(
            shared_store=_SHARED_FINGERPRINTS if persist_state else None
        )
        self.semantic_cluster = SemanticCluster(
            shared_store=_SHARED_EMBEDDINGS if persist_state else None
        )
        # 神经网络评分器懒加载：避免无 torch / 无模型文件环境下的
        # 启动开销与告警噪音，首次真正需要评分时才构造。
        self._neural_scorer = None

        self.history_records: List[InputRecord] = []

    @property
    def neural_scorer(self) -> NeuralScorer:
        """懒加载神经网络评分器（保持旧属性名兼容）"""
        if self._neural_scorer is None:
            self._neural_scorer = NeuralScorer()
        return self._neural_scorer

    def _neural_score(self, record: InputRecord,
                      geo_score: Optional[float] = None,
                      geo_anomalies: Optional[List] = None) -> Optional[float]:
        """神经网络维度的虚假概率（0-100）。

        模型未加载 / 无 torch / 推理异常时返回 None，
        上层据此将 neural_weight 置零，保证向后兼容。

        Args:
            record: 输入记录
            geo_score: 预计算的 GEO 分数（避免重复调用规则引擎）
            geo_anomalies: 预计算的 GEO 异常列表
        """
        try:
            if not self.neural_scorer.is_trained:
                return None
            import torch
            features = self.neural_scorer.extract_geo_features(
                record, geo_score=geo_score, geo_anomalies=geo_anomalies
            )
            geo_tensor = torch.tensor([features], dtype=torch.float32)
            _, scores = self.neural_scorer.model.predict(
                [record.content.text or ""], geo_tensor
            )
            return float(scores[0]) * 100.0
        except Exception:
            return None

    def _calculate_total_score(self, geo_score: float, text_score: float,
                               simhash_score: float, semantic_score: float,
                               has_text: bool = True, has_geo: bool = True,
                               is_batch_mode: bool = False,
                               neural_score: Optional[float] = None) -> float:
        """计算加权综合分数，支持动态权重调整"""
        geo_w = self.config.geo_weight
        text_w = self.config.text_rule_weight
        simhash_w = self.config.simhash_weight
        semantic_w = self.config.semantic_weight
        # 神经网络维度：模型不可用时权重为 0，等价于四维融合
        neural_w = self.config.neural_weight if neural_score is not None else 0.0
        neural_score_val = neural_score if neural_score is not None else 0.0

        # 批量模式使用不同的语义权重
        if is_batch_mode:
            semantic_w = self.config.batch_semantic_weight

        # 无文本时，文本权重置零并重分配
        if not has_text:
            text_w = 0.0

        # 无地理坐标时，地理权重置零并重分配
        if not has_geo:
            geo_w = 0.0

        # 按比例重分配权重使其总和为1.0
        total_weight = geo_w + text_w + simhash_w + semantic_w + neural_w
        if total_weight > 0:
            scale = 1.0 / total_weight
            geo_w *= scale
            text_w *= scale
            simhash_w *= scale
            semantic_w *= scale
            neural_w *= scale

        return (
            geo_score * geo_w +
            text_score * text_w +
            simhash_score * simhash_w +
            semantic_score * semantic_w +
            neural_score_val * neural_w
        )

    def _determine_risk_level(self, total_score: float) -> str:
        """根据总分判断风险等级"""
        if total_score >= self.config.high_risk_threshold:
            return "high"
        elif total_score >= self.config.medium_risk_threshold:
            return "medium"
        return "low"

    def _decide(self, total_score: float, geo_anomalies: List,
                text_anomalies: List, marketing_keyword_count: int = 0,
                simhash_score: float = 0, semantic_score: float = 0) -> Tuple[bool, bool]:
        """
        多因子加权决策。

        佐证（corroboration）指来自不同维度的独立信号：GEO异常、
        重复内容、聚类异常。营销词数量不能作为自身推高评分后的佐证，
        否则纯营销文本会因"分数过阈值+营销词多"而自我判定为虚假，
        违反"营销词触发但上下文正常 -> 可疑而非虚假"的保护场景。

        Returns:
            (is_fake, forced_high) forced_high 表示由高严重度异常强制判定，
            此时无论综合评分如何 risk_level 都应为 high。
        """
        high_severity = self.config.high_severity_threshold
        corroborated = len(geo_anomalies) > 0 or simhash_score > 0 or semantic_score > 0

        # 1. GEO高严重度异常（瞬移、无效坐标等硬证据）直接判定为虚假
        for anomaly in geo_anomalies:
            if anomaly.severity >= high_severity:
                return True, True

        # 2. 文本高严重度异常（关键词堆砌、高密度营销词）需要旁证，
        #    避免"哈哈哈""简直完美"这类正常热情内容被直接误判
        if corroborated:
            for anomaly in text_anomalies:
                if anomaly.severity >= high_severity:
                    return True, True

        # 3. 高风险阈值直接判定
        if total_score >= self.config.high_risk_threshold:
            return True, False

        # 4. 中风险 + 独立维度佐证
        if total_score >= self.config.medium_risk_threshold and corroborated:
            return True, False

        # 5. 营销词达到高阈值 + 佐证
        if marketing_keyword_count >= self.config.marketing_only_fake_threshold and corroborated:
            return True, False

        return False, False

    def _is_fake(self, total_score: float, geo_anomalies: List,
                 marketing_keyword_count: int = 0, simhash_score: float = 0,
                 semantic_score: float = 0, text_anomalies: List = None) -> bool:
        """多因子加权决策判断是否为虚假内容（兼容旧接口）"""
        is_fake, _ = self._decide(
            total_score, geo_anomalies, text_anomalies or [],
            marketing_keyword_count, simhash_score, semantic_score
        )
        return is_fake

    def _determine_risk_level(self, total_score: float, is_fake: bool = False,
                              forced_high: bool = False,
                              marketing_keyword_count: int = 0,
                              geo_anomalies: List = None) -> str:
        """根据总分和决策结果判断风险等级

        保证 risk_level 与 is_fake 的一致性：
        - 高严重度强制判定 -> high
        - 判定为虚假但评分低 -> 至少 medium
        - 有营销词但不足以判虚假 -> 至少 medium（进入人工复核）
        - 存在GEO异常但不足以判虚假 -> 至少 medium
        """
        if forced_high:
            return "high"

        if total_score >= self.config.high_risk_threshold:
            return "high"
        elif total_score >= self.config.medium_risk_threshold:
            return "medium"

        if is_fake or marketing_keyword_count >= 3 or geo_anomalies:
            return "medium"
        return "low"

    def _calculate_confidence(self, total_score: float, risk_level: str,
                              forced_high: bool = False) -> float:
        """基于评分与阈值距离计算置信度"""
        if risk_level == "high":
            distance = total_score - self.config.high_risk_threshold
        elif risk_level == "medium":
            distance = min(
                abs(total_score - self.config.medium_risk_threshold),
                abs(total_score - self.config.high_risk_threshold)
            )
        else:
            distance = self.config.medium_risk_threshold - total_score

        confidence = min(0.5 + distance * self.config.confidence_distance_factor, 0.99)
        confidence = max(confidence, 0.5)
        # 高严重度异常强制判定属于强证据，置信度下限提高
        if forced_high:
            confidence = max(confidence, 0.85)
        return confidence

    def _extract_marketing_keyword_count(self, text_anomalies: List[TextAnomaly]) -> int:
        """从文本异常中提取营销词数量（兼容高/中/低密度三种异常类型）"""
        marketing_types = {"suspicious_keywords", "moderate_marketing", "high_severity_marketing"}
        for anomaly in text_anomalies:
            if anomaly.anomaly_type in marketing_types:
                return anomaly.details.get('count', 0)
        return 0

    def analyze(self, record: InputRecord) -> DetectionResult:
        """
        分析单条记录

        Args:
            record: 输入记录

        Returns:
            检测结果
        """
        reasons = []
        details = {}

        # 1. GEO规则检测
        geo_score, geo_anomalies = self.geo_engine.analyze(record)
        geo_anomaly_names = [a.anomaly_type for a in geo_anomalies]
        if geo_anomalies:
            reasons.extend([f"[GEO] {a.description}" for a in geo_anomalies])
        details['geo_anomalies'] = geo_anomaly_names

        # 2. 文本规则检测
        text_score, text_anomalies = self.text_engine.analyze(record)
        text_anomaly_names = [a.anomaly_type for a in text_anomalies]
        if text_anomalies:
            reasons.extend([f"[文本] {a.description}" for a in text_anomalies])
        details['text_anomalies'] = text_anomaly_names

        # 3. SimHash重复检测
        simhash_result = self.simhash_detector.check(record)
        simhash_score = simhash_result.similarity * 100 if simhash_result.is_duplicate else 0
        if simhash_result.is_duplicate:
            reasons.append(f"[重复] 与{len(simhash_result.similar_records)}条记录相似度{simhash_result.similarity*100:.1f}%")
        details['simhash_similarity'] = simhash_result.similarity
        details['similar_record_count'] = len(simhash_result.similar_records)

        # 4. 语义聚类检测
        semantic_result = self.semantic_cluster.check(record, self.history_records)
        semantic_score = semantic_result.anomaly_score * 100
        if semantic_result.is_anomaly:
            reasons.append(f"[聚类] 检测到批量相似内容({semantic_result.cluster_size}条)")
        details['cluster_size'] = semantic_result.cluster_size
        details['semantic_backend'] = self.semantic_cluster.backend_name

        # 提取营销词数量
        marketing_keyword_count = self._extract_marketing_keyword_count(text_anomalies)

        # 判断是否有有效文本和地理坐标
        has_text = bool(record.content.text and len(record.content.text.strip()) >= text_config.min_text_length)
        has_geo = not (record.geo.latitude == 0 and record.geo.longitude == 0)

        # 5. 神经网络模型评分（模型不可用时返回 None，权重自动归零）
        neural_score = self._neural_score(
            record, geo_score=geo_score, geo_anomalies=geo_anomalies
        )
        if neural_score is not None:
            details['neural_score'] = round(neural_score, 2)
            details['model_used'] = 'neural'
            if neural_score >= 50:
                reasons.append(f"[AI] 模型预测倾向虚假 (虚假概率: {neural_score:.1f}%)")
        else:
            details['model_used'] = 'rules'

        # 计算综合分数
        total_score = self._calculate_total_score(
            geo_score, text_score, simhash_score, semantic_score,
            has_text=has_text, has_geo=has_geo, neural_score=neural_score
        )

        # 判断风险等级和是否为虚假
        is_fake, forced_high = self._decide(
            total_score, geo_anomalies, text_anomalies, marketing_keyword_count,
            simhash_score=simhash_score, semantic_score=semantic_score
        )
        risk_level = self._determine_risk_level(
            total_score, is_fake=is_fake, forced_high=forced_high,
            marketing_keyword_count=marketing_keyword_count,
            geo_anomalies=geo_anomalies,
        )

        # 计算置信度
        confidence = self._calculate_confidence(total_score, risk_level, forced_high)
        details['confidence'] = round(confidence, 2)
        details['high_severity_hit'] = forced_high
        details['marketing_keyword_count'] = marketing_keyword_count

        # 添加到历史记录（有上限，防止长期运行内存无限增长）
        self.history_records.append(record)
        max_history = getattr(self.config, 'max_history_records', 10000)
        if len(self.history_records) > max_history * 2:
            self.history_records[:] = self.history_records[-max_history:]

        return DetectionResult(
            record_id=record.record_id,
            suspicion_score=round(total_score, 2),
            is_fake=is_fake,
            risk_level=risk_level,
            geo_score=round(geo_score, 2),
            text_score=round(text_score, 2),
            simhash_score=round(simhash_score, 2),
            semantic_score=round(semantic_score, 2),
            reasons=reasons,
            details=details,
            similar_records=len(simhash_result.similar_records)
        )

    def analyze_batch(self, records: List[InputRecord]) -> BatchDetectionResult:
        """
        批量分析记录

        Args:
            records: 记录列表

        Returns:
            批量检测结果
        """
        # 清空历史
        self.clear_history()

        # 确保所有记录都是InputRecord对象
        records = [self._ensure_input_record(r) for r in records]

        results = []
        for record in records:
            result = self.analyze(record)
            results.append(result)

        # 统计
        fake_count = sum(1 for r in results if r.is_fake)
        normal_count = len(results) - fake_count
        high_risk_count = sum(1 for r in results if r.risk_level == "high")
        medium_risk_count = sum(1 for r in results if r.risk_level == "medium")

        # 详细统计
        statistics = {
            "avg_suspicion_score": sum(r.suspicion_score for r in results) / len(results) if results else 0,
            "high_risk_count": high_risk_count,
            "medium_risk_count": medium_risk_count,
            "geo_anomaly_count": sum(1 for r in results if r.geo_score > 0),
            "text_anomaly_count": sum(1 for r in results if r.text_score > 0),
            "duplicate_count": sum(1 for r in results if r.simhash_score > 0),
        }

        # 可疑记录：不是虚假但风险等级为medium的记录
        suspicious_count = sum(1 for r in results if not r.is_fake and r.risk_level == "medium")

        return BatchDetectionResult(
            total_count=len(results),
            fake_count=fake_count,
            normal_count=normal_count,
            suspicious_count=suspicious_count,
            results=results,
            statistics=statistics
        )

    def _ensure_input_record(self, record) -> InputRecord:
        """确保记录是InputRecord对象"""
        if isinstance(record, InputRecord):
            return record
        if isinstance(record, dict):
            from models import GeoData, ContentData, Metadata
            return InputRecord(
                record_id=record.get("record_id", record.get("id", "")),
                device_id=record.get("device_id", ""),
                user_id=record.get("user_id", ""),
                timestamp=record.get("timestamp", 0),
                geo=GeoData(
                    latitude=record.get("latitude", record.get("geo", {}).get("latitude", 0) if isinstance(record.get("geo"), dict) else 0),
                    longitude=record.get("longitude", record.get("geo", {}).get("longitude", 0) if isinstance(record.get("geo"), dict) else 0)
                ),
                content=ContentData(
                    text=record.get("text", record.get("content", {}).get("text", "") if isinstance(record.get("content"), dict) else ""),
                    content_type=record.get("content_type", "poi")
                ),
                metadata=Metadata(),
                label=record.get("label")
            )
        return record

    def analyze_batch_with_clustering(self, records: List[InputRecord]) -> BatchDetectionResult:
        """
        批量分析（带预聚类）

        先对所有记录进行聚类，然后再逐条分析

        Args:
            records: 记录列表

        Returns:
            批量检测结果
        """
        # 清空历史
        self.clear_history()

        # 确保所有记录都是InputRecord对象
        records = [self._ensure_input_record(r) for r in records]

        # 先进行聚类分析
        cluster_results = self.semantic_cluster.fit_predict(records)

        # 存储聚类结果
        cluster_info = {r.record_id: cluster_results[r.record_id] for r in records}

        # 逐条分析
        results = []
        for record in records:
            # 基础分析
            result = self._analyze_single_with_cluster(record, cluster_info[record.record_id])
            results.append(result)
            self.history_records.append(record)

        # 统计
        fake_count = sum(1 for r in results if r.is_fake)
        normal_count = len(results) - fake_count
        high_risk_count = sum(1 for r in results if r.risk_level == "high")
        medium_risk_count = sum(1 for r in results if r.risk_level == "medium")

        statistics = {
            "avg_suspicion_score": sum(r.suspicion_score for r in results) / len(results) if results else 0,
            "high_risk_count": high_risk_count,
            "medium_risk_count": medium_risk_count,
            "geo_anomaly_count": sum(1 for r in results if r.geo_score > 0),
            "text_anomaly_count": sum(1 for r in results if r.text_score > 0),
            "duplicate_count": sum(1 for r in results if r.simhash_score > 0),
            "cluster_anomaly_count": sum(1 for r in results if r.semantic_score > 0),
        }

        # 可疑记录：不是虚假但风险等级为medium的记录
        suspicious_count = sum(1 for r in results if not r.is_fake and r.risk_level == "medium")

        return BatchDetectionResult(
            total_count=len(results),
            fake_count=fake_count,
            normal_count=normal_count,
            suspicious_count=suspicious_count,
            results=results,
            statistics=statistics
        )

    def _analyze_single_with_cluster(self, record: InputRecord,
                                     cluster_result: ClusterResult) -> DetectionResult:
        """分析单条记录（带聚类信息）"""
        reasons = []
        details = {}

        # GEO检测
        geo_score, geo_anomalies = self.geo_engine.analyze(record)
        if geo_anomalies:
            reasons.extend([f"[GEO] {a.description}" for a in geo_anomalies])
        details['geo_anomalies'] = [a.anomaly_type for a in geo_anomalies]

        # 文本检测
        text_score, text_anomalies = self.text_engine.analyze(record)
        if text_anomalies:
            reasons.extend([f"[文本] {a.description}" for a in text_anomalies])
        details['text_anomalies'] = [a.anomaly_type for a in text_anomalies]

        # 提取营销词数量
        marketing_keyword_count = self._extract_marketing_keyword_count(text_anomalies)

        # SimHash检测
        simhash_result = self.simhash_detector.check(record)
        simhash_score = simhash_result.similarity * 100 if simhash_result.is_duplicate else 0
        if simhash_result.is_duplicate:
            reasons.append(f"[重复] 相似度{simhash_result.similarity*100:.1f}%")
        details['simhash_similarity'] = simhash_result.similarity
        details['similar_record_count'] = len(simhash_result.similar_records)

        # 聚类结果
        semantic_score = cluster_result.anomaly_score * 100
        if cluster_result.is_anomaly:
            reasons.append(f"[聚类] 批量相似内容({cluster_result.cluster_size}条)")
        details['cluster_size'] = cluster_result.cluster_size

        # 计算综合分数和风险等级
        has_text = bool(record.content.text and len(record.content.text.strip()) >= text_config.min_text_length)
        has_geo = not (record.geo.latitude == 0 and record.geo.longitude == 0)

        # 神经网络模型评分（模型不可用时返回 None，权重自动归零）
        neural_score = self._neural_score(
            record, geo_score=geo_score, geo_anomalies=geo_anomalies
        )
        if neural_score is not None:
            details['neural_score'] = round(neural_score, 2)
            details['model_used'] = 'neural'
            if neural_score >= 50:
                reasons.append(f"[AI] 模型预测倾向虚假 (虚假概率: {neural_score:.1f}%)")
        else:
            details['model_used'] = 'rules'

        total_score = self._calculate_total_score(
            geo_score, text_score, simhash_score, semantic_score,
            has_text=has_text, has_geo=has_geo, is_batch_mode=True,
            neural_score=neural_score
        )
        is_fake, forced_high = self._decide(
            total_score, geo_anomalies, text_anomalies, marketing_keyword_count,
            simhash_score=simhash_score, semantic_score=semantic_score
        )
        risk_level = self._determine_risk_level(
            total_score, is_fake=is_fake, forced_high=forced_high,
            marketing_keyword_count=marketing_keyword_count,
            geo_anomalies=geo_anomalies,
        )

        # 计算置信度
        confidence = self._calculate_confidence(total_score, risk_level, forced_high)
        details['confidence'] = round(confidence, 2)
        details['high_severity_hit'] = forced_high
        details['marketing_keyword_count'] = marketing_keyword_count

        return DetectionResult(
            record_id=record.record_id,
            suspicion_score=round(total_score, 2),
            is_fake=is_fake,
            risk_level=risk_level,
            geo_score=round(geo_score, 2),
            text_score=round(text_score, 2),
            simhash_score=round(simhash_score, 2),
            semantic_score=round(semantic_score, 2),
            reasons=reasons,
            details=details,
            similar_records=len(simhash_result.similar_records)
        )

    def clear_history(self):
        """清空历史记录"""
        self.history_records.clear()
        self.geo_engine.clear_cache()
        self.simhash_detector.clear()
        self.semantic_cluster.clear()
