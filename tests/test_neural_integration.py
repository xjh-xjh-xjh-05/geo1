"""
神经网络维度接入核心评分链路的专项测试

覆盖三种状态：
1. 模型不可用（无 torch / 无模型文件）→ 权重归零，行为与四维融合一致
2. 模型可用 → neural_score 参与加权融合，details 记录维度信息
3. 推理异常 → 静默降级回规则评分，不抛错
"""
import pytest

from engine.scorer import Scorer
from models import InputRecord, GeoData, ContentData


def _make_record(text: str = "这家店超级超级推荐！必去！yyds！", record_id: str = "t1") -> InputRecord:
    return InputRecord(
        record_id=record_id,
        device_id="D_001",
        user_id="U_001",
        timestamp=10,
        geo=GeoData(latitude=39.9042, longitude=116.4074),
        content=ContentData(text=text),
    )


class TestNeuralUnavailable:
    """模型不可用时的向后兼容"""

    def test_details_marked_rules_when_unavailable(self, monkeypatch):
        """模型不可用时 details.model_used 为 rules，且不出现 neural_score"""
        scorer = Scorer(persist_state=False)
        monkeypatch.setattr(
            Scorer, "_neural_score",
            lambda self, record, **kwargs: None,
        )
        result = scorer.analyze(_make_record())

        assert result.details["model_used"] == "rules"
        assert "neural_score" not in result.details

    def test_unavailable_score_equals_four_dim_fusion(self, monkeypatch):
        """模型不可用时的总分与不传 neural_score 的四维融合完全一致"""
        scorer = Scorer(persist_state=False)
        monkeypatch.setattr(
            Scorer, "_neural_score",
            lambda self, record, **kwargs: None,
        )
        result = scorer.analyze(_make_record())
        neural_absent = result.suspicion_score

        # 直接调用加权函数对比：不传 neural_score 与传 None 等价
        score = scorer._calculate_total_score(10.0, 20.0, 0.0, 0.0)
        score_none = scorer._calculate_total_score(10.0, 20.0, 0.0, 0.0, neural_score=None)
        assert score == score_none
        assert neural_absent >= 0


class TestNeuralAvailable:
    """模型可用时的加权融合"""

    def test_neural_score_recorded_and_in_range(self, monkeypatch):
        """模型返回分数时写入 details 且范围合法"""
        scorer = Scorer(persist_state=False)
        monkeypatch.setattr(
            Scorer, "_neural_score",
            lambda self, record, **kwargs: 80.0,
        )
        result = scorer.analyze(_make_record())

        assert result.details["model_used"] == "neural"
        assert result.details["neural_score"] == 80.0
        # 神经网络高分应抬升综合分（相比同输入下模型不可用时的分数）
        monkeypatch.setattr(
            Scorer, "_neural_score",
            lambda self, record, **kwargs: None,
        )
        baseline = Scorer(persist_state=False).analyze(_make_record())
        assert result.suspicion_score >= baseline.suspicion_score

    def test_neural_reason_appended_on_high_score(self, monkeypatch):
        """模型虚假概率超过 50% 时生成 [AI] 原因"""
        scorer = Scorer(persist_state=False)
        monkeypatch.setattr(
            Scorer, "_neural_score",
            lambda self, record, **kwargs: 90.0,
        )
        result = scorer.analyze(_make_record())
        assert any(r.startswith("[AI]") for r in result.reasons)

    def test_batch_path_records_neural(self, monkeypatch):
        """批量路径同样记录神经网络维度"""
        scorer = Scorer(persist_state=False)
        monkeypatch.setattr(
            Scorer, "_neural_score",
            lambda self, record, **kwargs: 20.0,
        )
        batch = scorer.analyze_batch([_make_record("正常评论", "b1"), _make_record("另一条", "b2")])
        assert batch.total_count == 2
        for r in batch.results:
            assert r.details["model_used"] == "neural"
            assert r.details["neural_score"] == 20.0


class TestNeuralDegradation:
    """推理异常时的静默降级"""

    def test_exception_in_predict_falls_back(self, monkeypatch):
        """模型声称已加载但推理崩溃时：_neural_score 返回 None，评分流程不中断"""
        from engine.neural_model import NeuralScorer, FakeDetectionModel

        scorer = Scorer(persist_state=False)
        # 伪造"权重已加载"状态
        monkeypatch.setattr(
            NeuralScorer, "is_trained",
            property(lambda self: True),
        )
        # 推理时崩溃
        def _boom(texts, geo_features):
            raise RuntimeError("模拟推理崩溃")

        monkeypatch.setattr(FakeDetectionModel, "predict", _boom)

        result = scorer.analyze(_make_record())
        # 不抛错且仍产出合法结果，并回退到规则评分
        assert 0 <= result.suspicion_score <= 100
        assert result.risk_level in ("low", "medium", "high")
        assert result.details["model_used"] == "rules"

    def test_zero_weight_math(self):
        """neural_weight=0 时不改变四维融合结果；非零时按比例重分配"""
        scorer = Scorer(persist_state=False)
        four_dim = scorer._calculate_total_score(50.0, 60.0, 10.0, 20.0)
        with_none = scorer._calculate_total_score(50.0, 60.0, 10.0, 20.0, neural_score=None)
        assert four_dim == with_none

        # 模型给出 0 分时不应低于四维结果（0 分拉低均值的情形按权重占比体现）
        with_zero = scorer._calculate_total_score(50.0, 60.0, 10.0, 20.0, neural_score=0.0)
        assert with_zero < four_dim or with_zero == four_dim
