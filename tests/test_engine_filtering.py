"""
核心过滤引擎测试

覆盖：文本规则误判修复、严重度合并、多因子决策、
风险等级一致性、跨请求状态、结果融合。
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models import InputRecord, GeoData, ContentData, Metadata
from engine.text_rules import TextRuleEngine
from engine.geo_rules import GeoRuleEngine, SharedFrequencyCache
from engine.scorer import Scorer
from utils.scoring import combine_severities


def make_record(text="", lat=39.9, lon=116.4, device_id="dev_1",
                timestamp=1700000000, record_id="r1"):
    return InputRecord(
        record_id=record_id,
        device_id=device_id,
        user_id="user_1",
        timestamp=timestamp,
        geo=GeoData(latitude=lat, longitude=lon),
        content=ContentData(text=text),
        metadata=Metadata(),
    )


class TestCombineSeverities:
    def test_single_severity_unchanged(self):
        assert combine_severities([0.6]) == 60.0

    def test_more_anomalies_score_higher(self):
        single = combine_severities([0.3])
        double = combine_severities([0.3, 0.3])
        triple = combine_severities([0.3, 0.3, 0.3])
        assert single < double < triple

    def test_bounded_by_100(self):
        assert combine_severities([1.0, 1.0, 1.0]) == 100.0

    def test_empty(self):
        assert combine_severities([]) == 0.0


class TestTextRules:
    """文本规则误判修复"""

    @pytest.fixture
    def engine(self):
        return TextRuleEngine()

    @pytest.mark.parametrize("text", [
        "第一次来这里玩，整体体验不错，值得一去。",
        "在故宫吃了个饭，味道一般，环境还行。",
        "周末和朋友去了颐和园，环境干净整洁，服务人员态度友好。",
        "今天闲着没事去了趟北海公园，消磨时间还行。",
    ])
    def test_normal_text_not_flagged_as_template(self, engine, text):
        """正常中文表述不应被误判为模板化营销内容"""
        score, anomalies = engine.analyze(make_record(text=text))
        types = [a.anomaly_type for a in anomalies]
        assert "template_content" not in types, f"正常文本被误判: {text}, {types}"
        assert score < 50

    @pytest.mark.parametrize("text", [
        "强烈推荐这家网红店！绝绝子！必去打卡！",
        "超级推荐故宫！宝藏店铺！yyds！必去打卡！绝了！强烈推荐！",
        "这家店最好吃了，No.1，无敌！",
    ])
    def test_marketing_text_flagged(self, engine, text):
        score, anomalies = engine.analyze(make_record(text=text))
        assert score > 0
        assert len(anomalies) > 0

    def test_marketing_density_grading(self, engine):
        # 高密度
        heavy = "超级推荐！宝藏店铺！yyds！必去打卡！绝了！强烈推荐！"
        _, anomalies_heavy = engine.analyze(make_record(text=heavy))
        heavy_types = [a.anomaly_type for a in anomalies_heavy]
        assert "high_severity_marketing" in heavy_types

        # 低密度但数量达到阈值
        light = "去了故宫，还不错，推荐一下，值得一去。"
        _, anomalies_light = engine.analyze(make_record(text=light))
        light_types = [a.anomaly_type for a in anomalies_light]
        assert "template_content" not in light_types

    def test_tenant_keywords_take_effect(self, engine):
        """租户配置的自定义关键词必须参与密度检测"""
        from config import TextConfig
        custom = TextConfig(suspicious_keywords=["超值优惠"])
        engine_custom = TextRuleEngine(config=custom)
        score, anomalies = engine_custom.analyze(make_record(text="这家店超值优惠限时特价！"))
        types = [a.anomaly_type for a in anomalies]
        assert any("marketing" in t or t == "suspicious_keywords" for t in types)


class TestGeoRules:
    def test_invalid_coordinate(self):
        engine = GeoRuleEngine()
        score, anomalies = engine.analyze(make_record(lat=200.0, lon=500.0))
        assert any(a.anomaly_type == "invalid_coordinate" for a in anomalies)
        assert score >= 100

    def test_out_of_range_coordinate(self):
        engine = GeoRuleEngine()
        score, anomalies = engine.analyze(make_record(lat=45.0, lon=-100.0))
        assert any(a.anomaly_type == "out_of_range" for a in anomalies)

    def test_multiple_anomalies_not_averaged_down(self):
        """多个GEO异常并存时分数不应低于单异常"""
        engine = GeoRuleEngine()
        s1, a1 = engine.analyze(make_record(lat=200.0, lon=500.0))
        engine2 = GeoRuleEngine()
        s2, a2 = engine2.analyze(make_record(lat=45.0, lon=-100.0))
        # 无效坐标(1.0) 单独就应为最高分
        assert s1 >= s2

    def test_shared_frequency_cache(self):
        """共享频率缓存跨实例累积，触发高频检测"""
        cache = SharedFrequencyCache()
        engine = GeoRuleEngine(shared_frequency_cache=cache)

        # 同一设备每分钟上报超过阈值
        base_ts = 1700000000
        last_anomaly = None
        for i in range(15):
            _, anomalies = engine.analyze(make_record(
                device_id="dev_hf",
                timestamp=base_ts + i,  # 1秒一条
                record_id=f"hf_{i}",
            ))
            if anomalies:
                last_anomaly = anomalies[-1]
        assert last_anomaly is not None
        assert "high_frequency" in last_anomaly.anomaly_type


class TestScorerDecision:
    @pytest.fixture
    def scorer(self):
        return Scorer(persist_state=False)

    def test_normal_record_clean(self, scorer):
        record = make_record(
            text="周末和朋友去了颐和园，环境干净整洁，服务人员态度友好，价格也合理，玩得很开心。",
            record_id="normal_1",
        )
        result = scorer.analyze(record)
        assert not result.is_fake
        assert result.risk_level == "low"

    def test_invalid_coordinate_forced_fake_high_risk(self, scorer):
        """无效坐标（严重度1.0）必须强制 is_fake 且 risk_level=high"""
        record = make_record(
            text="周末和朋友去了颐和园，环境干净整洁，服务人员态度友好，价格也合理。",
            lat=200.0, lon=500.0,
            record_id="invalid_1",
        )
        result = scorer.analyze(record)
        assert result.is_fake
        assert result.risk_level == "high"
        assert result.details.get("high_severity_hit") is True

    def test_heavy_marketing_clean_geo_is_suspicious_not_fake(self, scorer):
        """重度营销但GEO完全正常且无重复/聚类：按规格场景A判定为可疑而非虚假，
        风险等级medium（营销词数量不能作为自身推高评分后的佐证）"""
        record = make_record(
            text="超级推荐这家宝藏店铺！yyds！必去打卡！绝了！强烈推荐大家去！",
            record_id="mkt_heavy_1",
        )
        result = scorer.analyze(record)
        assert not result.is_fake
        assert result.risk_level == "medium"

    def test_heavy_marketing_with_corroboration_is_fake(self, scorer):
        """重度营销 + GEO异常佐证 -> 判定虚假"""
        record = make_record(
            text="超级推荐这家宝藏店铺！yyds！必去打卡！绝了！强烈推荐大家去！",
            lat=45.0, lon=-100.0,  # out_of_range佐证
            record_id="mkt_heavy_2",
        )
        result = scorer.analyze(record)
        assert result.is_fake

    def test_light_marketing_clean_geo_is_suspicious_not_fake(self, scorer):
        """轻度营销（数量≥3但密度低、严重度<0.8）+ GEO完全正常且无重复聚类
        -> 按规格判定为可疑而非虚假，风险等级medium（进入人工复核）"""
        long_text = (
            "这家店藏在老城区的一条小巷子里，第一次来的时候差点没找到。"
            "老板人很实在，看我们是生面孔还主动介绍了周边的玩法。"
            "点的几个菜都挺有锅气，分量足，价格也实在。店里收拾得干干净净，"
            "吃饭的人不少，人气挺旺。走的时候老板还说欢迎朋友来打卡，"
            "感觉是家用心做味道的宝藏小店，值得再来。"
        )
        record = make_record(text=long_text, record_id="mkt_light_1")
        result = scorer.analyze(record)
        assert not result.is_fake
        assert result.risk_level == "medium"

    def test_marketing_with_corroboration_is_fake(self, scorer):
        """营销内容 + 无效坐标旁证 -> 判定虚假"""
        record = make_record(
            text="超级推荐这家宝藏店铺！yyds！必去打卡！绝了！强烈推荐大家去！",
            lat=200.0, lon=500.0,
            record_id="mkt_geo_1",
        )
        result = scorer.analyze(record)
        assert result.is_fake
        assert result.risk_level == "high"

    def test_risk_level_consistent_with_is_fake(self, scorer):
        """is_fake=True 时 risk_level 不能是 low"""
        record = make_record(
            text="必去必买必吃！第一No.1顶级极致完美无敌！",
            lat=45.0, lon=-100.0,  # out_of_range (0.8) 强制fake
            record_id="consistency_1",
        )
        result = scorer.analyze(record)
        if result.is_fake:
            assert result.risk_level != "low"

    def test_history_capped(self, scorer):
        """历史记录应有上限，防止内存无限增长"""
        max_history = scorer.config.max_history_records
        for i in range(50):
            scorer.analyze(make_record(text="普通评论内容，还行。", record_id=f"h_{i}"))
        assert len(scorer.history_records) <= max_history * 2

    def test_batch_duplicate_detection(self, scorer):
        """批量模式下重复文本应被检出"""
        records = [
            make_record(
                text="这家店超级推荐！宝藏店铺！yyds！必去打卡！",
                record_id=f"dup_{i}",
                device_id=f"dev_{i}",
            )
            for i in range(8)
        ]
        batch = scorer.analyze_batch(records)
        dup_scores = [r.simhash_score for r in batch.results]
        # 第2条起应能发现与第1条重复
        assert any(s > 0 for s in dup_scores[1:])


class TestNeuralModel:
    def test_untrained_model_falls_back_to_rules(self):
        """未加载权重的神经网络模型必须降级为规则评分"""
        from engine.neural_model import NeuralScorer
        scorer = NeuralScorer()
        assert not scorer.is_trained
        result = scorer.analyze(make_record(
            text="强烈推荐这家网红店！绝绝子！必去打卡！",
            record_id="nn_1",
        ))
        assert result.details.get("model_used") == "rules_fallback"

    def test_device_hash_stable_across_instances(self):
        """设备特征哈希必须跨实例/跨进程稳定"""
        from engine.neural_model import NeuralScorer
        record = make_record(device_id="device_abc", record_id="nn_2")
        s1 = NeuralScorer()
        s2 = NeuralScorer()
        f1 = s1.extract_geo_features(record)
        f2 = s2.extract_geo_features(record)
        assert f1 == f2


class TestResultFusion:
    def _service(self):
        """构造不走数据库的服务实例（仅测试融合逻辑）"""
        from api.services.detection_service import OptimizedDetectionService
        service = object.__new__(OptimizedDetectionService)
        service.db = None
        service.tenant_id = 1
        service._tenant_geo_config = {}
        service._tenant_text_config = {}
        service._tenant_keywords = []
        return service

    def _base_result(self, is_fake=False, score=50.0, risk="medium", high_severity=False):
        from engine.scorer import Scorer
        result = type("R", (), {})()
        result.suspicion_score = score
        result.is_fake = is_fake
        result.risk_level = risk
        result.reasons = ["[GEO] 测试"]
        result.details = {"confidence": 0.7, "high_severity_hit": high_severity}
        return result

    class _CV:
        risk_level = "high"
        confidence = 0.8
        risk_reasons = ["[交叉] 多平台信息不一致"]

    class _Pre:
        warnings = []

    def test_high_severity_cannot_be_outvoted(self):
        """硬证据（高严重度异常）不允许被其他来源投票推翻"""
        service = self._service()
        merged = service._merge_results(
            self._base_result(is_fake=True, score=80.0, risk="high", high_severity=True),
            None,
            {"label": "real", "confidence": 0.9, "risk_factors": []},
            self._Pre(),
        )
        assert merged["is_fake"] is True

    def test_conflicting_sources_reduce_confidence(self):
        """来源结论分歧时置信度应衰减"""
        service = self._service()
        merged = service._merge_results(
            self._base_result(is_fake=False, score=20.0, risk="low"),
            self._CV(),
            {"label": "real", "confidence": 0.9, "risk_factors": []},
            self._Pre(),
        )
        # 各来源置信度均值在0.7~0.8之间，分歧后应低于该值
        assert merged["confidence"] < 0.75

    def test_fusion_no_hardcoded_jump(self):
        """单来源高分交叉验证不应再出现硬编码+20的跳变"""
        service = self._service()
        merged = service._merge_results(
            self._base_result(is_fake=False, score=40.0, risk="medium"),
            self._CV(),
            None,
            self._Pre(),
        )
        # 加权分数应介于规则分数与交叉验证分数(85)之间
        assert 40.0 <= merged["suspicion_score"] <= 85.0

    def test_source_weights_normalized(self):
        service = self._service()
        sources = [
            {"name": "rules", "score": 50, "confidence": 0.7, "is_fake": False},
            {"name": "cross_validation", "score": 80, "confidence": 0.8, "is_fake": True},
        ]
        weights = service._calculate_source_weights(sources)
        assert abs(sum(weights) - 1.0) < 1e-9
        # 规则可靠性1.0*0.7=0.7，交叉验证0.8*0.8=0.64 -> 规则权重更高
        assert weights[0] > weights[1]

    def test_tenant_config_no_leakage(self):
        """租户关键词在池化Scorer上应用后，空租户必须恢复默认词库"""
        from config import text_config as default_text_config
        service = self._service()
        service._tenant_keywords = ["自定义词ABC"]
        scorer = Scorer(persist_state=False)
        service._apply_tenant_config(scorer)
        assert "自定义词ABC" in scorer.text_engine.config.suspicious_keywords

        # 切换到无关键词的租户，应恢复默认
        service._tenant_keywords = []
        service._tenant_text_config = {}
        service._tenant_geo_config = {}
        service._apply_tenant_config(scorer)
        assert "自定义词ABC" not in scorer.text_engine.config.suspicious_keywords
        assert scorer.text_engine.config.suspicious_keywords == list(
            default_text_config.suspicious_keywords
        )
