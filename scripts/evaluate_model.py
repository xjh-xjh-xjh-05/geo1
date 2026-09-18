"""
独立模型评估脚本

用法:
    python scripts/evaluate_model.py                     # 评估规则引擎 + 已训练神经网络
    python scripts/evaluate_model.py --compare           # 对比输出所有可用模型
    python scripts/evaluate_model.py --data-path <json>  # 指定测试数据
    python scripts/evaluate_model.py --neural-only       # 只评估神经网络模型
"""
import os
import sys
import argparse

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from modules.ai_model.evaluation import (
    evaluate_rule_scorer, evaluate_neural_model, evaluate_sklearn_model,
    load_default_test_data, summarize_metrics_row
)

NEURAL_MODEL_PATH = os.path.join('data', 'models', 'fake_detection_model.pt')
RF_MODEL_PATH = os.path.join('models', 'saved', 'latest_model.joblib')


def main():
    parser = argparse.ArgumentParser(description="模型评估脚本")
    parser.add_argument("--data-path", default=None, help="测试数据JSON路径（默认 data/training_data.json）")
    parser.add_argument("--max-records", type=int, default=2000, help="最多评估的样本数")
    parser.add_argument("--compare", action="store_true", help="对比所有可用模型")
    parser.add_argument("--neural-only", action="store_true", help="只评估神经网络模型")
    args = parser.parse_args()

    print("加载测试数据...")
    records = load_default_test_data(args.data_path, max_records=args.max_records)
    if not records:
        print("[ERROR] 未找到测试数据。请先运行 scripts/train_model.py 生成 data/training_data.json，"
              "或使用 --data-path 指定数据文件。")
        sys.exit(1)

    labeled = [r for r in records if r.label in ("normal", "fake")]
    print(f"共加载 {len(records)} 条记录，其中带标注样本 {len(labeled)} 条\n")

    results = {}

    if not args.neural_only:
        print("评估规则引擎（Scorer）...")
        results["规则引擎"] = evaluate_rule_scorer(labeled)
        if os.path.exists(RF_MODEL_PATH):
            print("评估随机森林模型...")
            results["随机森林模型"] = evaluate_sklearn_model(labeled, RF_MODEL_PATH)

    if args.compare or args.neural_only:
        print("评估神经网络模型...")
        results["神经网络模型"] = evaluate_neural_model(labeled, NEURAL_MODEL_PATH)
    elif os.path.exists(NEURAL_MODEL_PATH):
        print("评估神经网络模型...")
        results["神经网络模型"] = evaluate_neural_model(labeled, NEURAL_MODEL_PATH)

    print("\n========== 评估结果 ==========")
    for name, metrics in results.items():
        print(summarize_metrics_row(name, metrics))
        cm = metrics.get("confusion_matrix")
        if cm:
            print(f"{'':<24} 混淆矩阵(行=真实 normal/fake, 列=预测): {cm['matrix']}")
        if metrics.get("available") is False:
            print(f"{'':<24} 提示: {metrics.get('message', '')}")
    print("==============================\n")

    if args.compare and len(results) > 1:
        best = max(
            (m for m in results.values() if m.get("sample_count")),
            key=lambda m: m["f1"],
            default=None,
        )
        if best:
            print(f"F1 最优模型指标: Acc={best['accuracy']:.4f}, F1={best['f1']:.4f}")


if __name__ == "__main__":
    main()
