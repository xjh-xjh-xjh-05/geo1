"""本地混合随机森林模型测试。"""
import os

import numpy as np
import pytest

from models import DetectionResult
from modules.ai_model import (
    AIDetectionModel,
    FeatureExtractor,
    HAS_SKLEARN,
    HYBRID_FEATURE_SCHEMA_VERSION,
)


pytestmark = pytest.mark.skipif(not HAS_SKLEARN, reason="scikit-learn 未安装")


def _rule_result(**overrides):
    data = {
        "record_id": "r1",
        "suspicion_score": 70,
        "is_fake": True,
        "risk_level": "high",
        "geo_score": 80,
        "text_score": 60,
        "simhash_score": 40,
        "semantic_score": 20,
        "reasons": ["测试风险"],
        "details": {
            "confidence": 0.9,
            "high_severity_hit": True,
            "similar_record_count": 3,
        },
    }
    data.update(overrides)
    return DetectionResult(**data)


def test_hybrid_feature_contract_is_stable():
    model = AIDetectionModel()
    result = _rule_result()
    context = FeatureExtractor.context_from_rule_result(result)
    vector = model.feature_array(
        {"description": "超级优惠，强烈推荐", "latitude": 39.9, "longitude": 116.4},
        context,
    )

    assert vector.shape == (10,)
    assert model.feature_names == FeatureExtractor.feature_schema()["names"]
    assert vector[0] == pytest.approx(0.8)
    assert vector[7] == 1.0
    assert vector[8] == pytest.approx(0.9)
    assert vector[9] == pytest.approx(0.3)


def test_semantic_backend_mismatch_is_rejected():
    model = AIDetectionModel()
    model.semantic_backend = "character-frequency-fallback"
    with pytest.raises(ValueError, match="语义特征后端不匹配"):
        model.feature_array(
            {"description": "测试", "latitude": 39.9, "longitude": 116.4},
            {"semantic_backend": "sentence-transformer"},
        )


def test_model_round_trip(tmp_path):
    model = AIDetectionModel()
    X = np.asarray([
        [0.05, 0.05, 0, 0, 0.1, 0, 1, 0, 0.8, 0],
        [0.1, 0.1, 0, 0, 0.2, 0, 1, 0, 0.7, 0],
        [0.9, 0.8, 0.7, 0.6, 0.2, 0.5, 0, 1, 0.9, 0.5],
        [0.8, 0.7, 0.6, 0.5, 0.3, 0.4, 0, 1, 0.8, 0.4],
        [0.15, 0.05, 0, 0, 0.2, 0, 1, 0, 0.7, 0],
        [0.85, 0.75, 0.5, 0.4, 0.3, 0.3, 0, 1, 0.85, 0.4],
    ], dtype=np.float32)
    y = np.asarray([0, 0, 1, 1, 0, 1], dtype=np.int64)
    model.train(X, y, test_size=0.33)
    model.semantic_backend = "character-frequency-fallback"

    path = os.path.join(str(tmp_path), "model.joblib")
    model.save(path)
    loaded = AIDetectionModel()
    loaded.load(path)

    assert loaded.is_trained
    assert loaded.feature_schema_version == HYBRID_FEATURE_SCHEMA_VERSION
    assert loaded.semantic_backend == "character-frequency-fallback"
    assert loaded.label_mapping == {0: "real", 1: "fake"}
