"""
训练本地混合检测随机森林模型。

特征由 Scorer 计算的 GEO、文本、SimHash、语义结果和稳定元特征组成，
与 DetectionService 的线上推理契约保持一致。训练标签只来自数据集 label。
"""
import argparse
import json
import os
import random
import sys
from typing import List, Tuple

import numpy as np

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from engine.scorer import Scorer
from models import InputRecord
from modules.ai_model import AIDetectionModel, HAS_SKLEARN
from modules.ai_model.evaluation import compute_metrics, load_default_test_data
from config import text_config


def _parse_args():
    parser = argparse.ArgumentParser(description="训练 GEO 混合检测随机森林模型")
    parser.add_argument("--data-path", default="data/training_data.json")
    parser.add_argument("--output", default="models/saved/latest_model.joblib")
    parser.add_argument("--metrics-output", default=None)
    parser.add_argument("--test-size", type=float, default=0.2)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--max-records", type=int, default=0)
    parser.add_argument(
        "--use-sentence-transformer", action="store_true",
        help="启用 paraphrase-multilingual-MiniLM-L12-v2；首次运行需要下载模型",
    )
    return parser.parse_args()


def _load_records(path: str, max_records: int) -> List[InputRecord]:
    records = load_default_test_data(path, max_records=max_records or 0)
    records = [record for record in records if record.label in ("normal", "fake")]
    if not records:
        raise ValueError("数据集中没有可用的 normal/fake 标签")
    return records


def _group_key(record: InputRecord) -> str:
    """按完整文本模板分组，阻止重复模板跨训练/测试集合泄漏。"""
    normalized_text = "".join(record.content.text.lower().split())
    return normalized_text or record.record_id


def _split_grouped(records: List[InputRecord], test_size: float, seed: int) -> Tuple[List[InputRecord], List[InputRecord]]:
    groups = {}
    for record in records:
        groups.setdefault(_group_key(record), []).append(record)
    keys = list(groups)
    random.Random(seed).shuffle(keys)
    target = max(1, int(len(records) * test_size))
    test, train = [], []
    for key in keys:
        destination = test if len(test) < target else train
        destination.extend(groups[key])
    if not train or not test:
        raise ValueError("按设备分组切分失败：请提供更多设备或降低 test_size")
    return train, test


def _build_features(records: List[InputRecord]):
    scorer = Scorer(persist_state=False)
    results = scorer.analyze_batch_with_clustering(records).results
    model = AIDetectionModel()
    features = []
    labels = []
    for record, result in zip(records, results):
        poi_data = {
            "name": record.content.text[:100],
            "description": record.content.text,
            "latitude": record.geo.latitude,
            "longitude": record.geo.longitude,
            "record_id": record.record_id,
        }
        context = model.feature_extractor.context_from_rule_result(result, record)
        features.append(model.feature_array(poi_data, context))
        labels.append(1 if record.label == "fake" else 0)
    backend = (
        "sentence-transformer"
        if scorer.semantic_cluster.encoder not in (None, "simple")
        else "character-frequency-fallback"
    )
    return (
        np.asarray(features, dtype=np.float32),
        np.asarray(labels, dtype=np.int64),
        results,
        backend,
    )


def main():
    args = _parse_args()
    if not HAS_SKLEARN:
        raise SystemExit("缺少 scikit-learn/joblib，请先安装 requirements.txt")
    random.seed(args.seed)
    np.random.seed(args.seed)
    text_config.use_online_model = args.use_sentence_transformer

    records = _load_records(args.data_path, args.max_records)
    train_records, test_records = _split_grouped(records, args.test_size, args.seed)
    X_train, y_train, _, train_backend = _build_features(train_records)
    X_test, y_test, _, test_backend = _build_features(test_records)

    model = AIDetectionModel(model_type="random_forest")
    model.train(X_train, y_train, test_size=0.2, random_state=args.seed)
    model.scaler.fit(X_train)
    model.model.fit(model.scaler.transform(X_train), y_train)
    predictions = model.model.predict(model.scaler.transform(X_test))
    metrics = compute_metrics(y_test.tolist(), predictions.tolist())
    metrics.update({
        "available": True,
        "sample_count": len(y_test),
        "train_count": len(y_train),
        "test_count": len(y_test),
        "feature_schema": model.feature_extractor.feature_schema(),
        "data_path": args.data_path,
        "group_key": "normalized full text (prevents duplicate-template leakage)",
        "semantic_backend": train_backend if train_backend == test_backend else f"{train_backend}/{test_backend}",
        "seed": args.seed,
        "synthetic_data_warning": "合成数据指标不能代表真实线上泛化能力",
    })
    model.last_metrics = metrics
    model.semantic_backend = metrics["semantic_backend"]
    model.save(args.output)

    metrics_path = args.metrics_output or args.output.replace(".joblib", "_metrics.json")
    os.makedirs(os.path.dirname(metrics_path) or ".", exist_ok=True)
    with open(metrics_path, "w", encoding="utf-8") as output_file:
        json.dump(metrics, output_file, ensure_ascii=False, indent=2)

    print(json.dumps({"model": args.output, "metrics": metrics}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
