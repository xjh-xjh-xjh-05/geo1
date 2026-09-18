"""
模型评估工具

提供统一的评估指标计算和模型评测入口，供训练脚本、
独立评估脚本（scripts/evaluate_model.py）和评估 API 共用。
"""
import os
import sys
import json
from typing import List, Dict, Any, Optional, Callable

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from models import InputRecord, ContentData, GeoData

try:
    from sklearn.metrics import (
        precision_score, recall_score, f1_score,
        confusion_matrix, classification_report, accuracy_score
    )
    HAS_SKLEARN = True
except ImportError:
    HAS_SKLEARN = False


def compute_metrics(y_true: List[int], y_pred: List[int]) -> Dict[str, Any]:
    """计算二分类评估指标：准确率、精确率、召回率、F1、混淆矩阵"""
    if HAS_SKLEARN:
        cm = confusion_matrix(y_true, y_pred, labels=[0, 1])
        return {
            "accuracy": float(accuracy_score(y_true, y_pred)),
            "precision": float(precision_score(y_true, y_pred, zero_division=0)),
            "recall": float(recall_score(y_true, y_pred, zero_division=0)),
            "f1": float(f1_score(y_true, y_pred, zero_division=0)),
            "confusion_matrix": {
                "labels": ["normal", "fake"],
                "matrix": cm.tolist(),
            },
            "classification_report": classification_report(
                y_true, y_pred, target_names=["normal", "fake"],
                output_dict=True, zero_division=0
            ),
        }

    # sklearn 不可用时的手动计算
    tp = sum(1 for t, p in zip(y_true, y_pred) if t == 1 and p == 1)
    fp = sum(1 for t, p in zip(y_true, y_pred) if t == 0 and p == 1)
    fn = sum(1 for t, p in zip(y_true, y_pred) if t == 1 and p == 0)
    tn = sum(1 for t, p in zip(y_true, y_pred) if t == 0 and p == 0)
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = (
        2 * precision * recall / (precision + recall)
        if precision + recall else 0.0
    )
    accuracy = (tp + tn) / len(y_true) if y_true else 0.0
    return {
        "accuracy": accuracy,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "confusion_matrix": {
            "labels": ["normal", "fake"],
            "matrix": [[tn, fp], [fn, tp]],
        },
    }


def load_records(items: List[Dict[str, Any]]) -> List[InputRecord]:
    """将 dict 列表转换为 InputRecord 列表"""
    records = []
    for item in items:
        geo = item.get("geo") or {}
        content = item.get("content") or {}
        records.append(InputRecord(
            record_id=item.get("record_id", ""),
            device_id=item.get("device_id", ""),
            user_id=item.get("user_id", ""),
            timestamp=item.get("timestamp", 0),
            geo=GeoData(
                latitude=geo.get("latitude", item.get("latitude", 0)),
                longitude=geo.get("longitude", item.get("longitude", 0)),
            ),
            content=ContentData(
                text=content.get("text", item.get("text", "")),
            ),
            label=item.get("label"),
        ))
    return records


def load_default_test_data(data_path: str = None, max_records: int = 2000) -> List[InputRecord]:
    """加载默认测试数据（data/training_data.json），不存在时返回空列表"""
    if data_path is None:
        data_path = os.path.join('data', 'training_data.json')
    if not os.path.exists(data_path):
        return []
    with open(data_path, 'r', encoding='utf-8') as f:
        items = json.load(f)
    records = load_records(items)
    if max_records and len(records) > max_records:
        records = records[-max_records:]
    return records


def evaluate_predictor(records: List[InputRecord],
                       predict_fn: Callable[[InputRecord], bool]) -> Dict[str, Any]:
    """
    用给定的预测函数评估一组带标注记录。

    Args:
        records: 带 label（normal/fake）的记录列表
        predict_fn: 输入 InputRecord，返回 is_fake 布尔值

    Returns:
        评估指标字典（含样本数）
    """
    y_true, y_pred = [], []
    errors = 0
    for record in records:
        if record.label not in ("normal", "fake"):
            continue
        try:
            pred = predict_fn(record)
        except Exception:
            errors += 1
            continue
        y_true.append(1 if record.label == "fake" else 0)
        y_pred.append(1 if pred else 0)

    metrics = compute_metrics(y_true, y_pred)
    metrics["sample_count"] = len(y_true)
    if errors:
        metrics["prediction_errors"] = errors
    return metrics


def evaluate_rule_scorer(records: List[InputRecord]) -> Dict[str, Any]:
    """评估规则引擎（Scorer），使用批次隔离模式保证可复现"""
    from engine.scorer import Scorer

    scorer = Scorer(persist_state=False)
    results = scorer.analyze_batch(records).results
    result_map = {r.record_id: r for r in results}

    y_true, y_pred = [], []
    for record in records:
        if record.label not in ("normal", "fake"):
            continue
        result = result_map.get(record.record_id)
        if result is None:
            continue
        y_true.append(1 if record.label == "fake" else 0)
        y_pred.append(1 if result.is_fake else 0)

    metrics = compute_metrics(y_true, y_pred)
    metrics["sample_count"] = len(y_true)
    return metrics


def evaluate_neural_model(records: List[InputRecord],
                          model_path: str = None) -> Dict[str, Any]:
    """评估神经网络模型（权重不可用时返回不可用说明）"""
    from engine.neural_model import NeuralScorer, NeuralConfig
    import torch

    scorer = NeuralScorer(NeuralConfig())
    if model_path and os.path.exists(model_path):
        scorer.model.load_state_dict(
            torch.load(model_path, map_location=scorer.model.device)
        )
        scorer.model.using_fallback = False

    if not scorer.is_trained:
        return {
            "available": False,
            "message": "神经网络模型权重不可用，请先运行 scripts/train_model.py",
            "sample_count": 0,
        }

    metrics = evaluate_predictor(records, lambda r: scorer.analyze(r).is_fake)
    metrics["available"] = True
    return metrics


def evaluate_sklearn_model(records: List[InputRecord], model_path: str) -> Dict[str, Any]:
    """评估已保存的随机森林模型。"""
    if not HAS_SKLEARN or not os.path.exists(model_path):
        return {
            "available": False,
            "message": "随机森林模型不可用，请先运行 scripts/train_rf_model.py",
            "sample_count": 0,
        }

    from engine.scorer import Scorer
    from modules.ai_model import AIDetectionModel, FeatureExtractor

    model = AIDetectionModel()
    model.load(model_path)
    scorer = Scorer(persist_state=False)
    rule_results = scorer.analyze_batch_with_clustering(records).results
    result_map = {result.record_id: result for result in rule_results}

    def predict(record: InputRecord) -> bool:
        rule_result = result_map[record.record_id]
        poi_data = {
            "name": record.content.text[:100],
            "description": record.content.text,
            "latitude": record.geo.latitude,
            "longitude": record.geo.longitude,
        }
        context = FeatureExtractor.context_from_rule_result(rule_result, record)
        return model.predict(poi_data, context).label == "fake"

    metrics = evaluate_predictor(records, predict)
    metrics["available"] = True
    metrics["feature_schema_version"] = model.feature_schema_version
    metrics["evaluation_warning"] = "若数据参与过训练，本结果会高估泛化能力；以训练脚本独立测试集指标为准"
    return metrics


def summarize_metrics_row(name: str, metrics: Dict[str, Any]) -> str:
    """格式化单行指标，用于模型对比表格"""
    if not metrics.get("sample_count"):
        return f"{name:<24} 样本不足，无法评估"
    return (
        f"{name:<24} "
        f"样本={metrics['sample_count']:<6} "
        f"Acc={metrics['accuracy']:.4f}  "
        f"P={metrics['precision']:.4f}  "
        f"R={metrics['recall']:.4f}  "
        f"F1={metrics['f1']:.4f}"
    )
