# 语义后端对比记录（2026-09-18）

同一训练配置（seed=42、按文本模板分组切分防泄漏、混合 10 维特征、random_forest）下，
仅切换语义聚类编码后端的对比：

| 后端 | Accuracy | Precision | Recall | F1 | 混淆矩阵 (normal/fake) |
|------|----------|-----------|--------|-----|------------------------|
| character-frequency-fallback（字符频率降级） | 0.9428 | 1.0000 | 0.8487 | **0.9181** | [[250,0],[23,129]] |
| sentence-transformer（paraphrase-multilingual-MiniLM-L12-v2） | 0.9378 | 0.9847 | 0.8487 | 0.9117 | [[248,2],[23,129]] |

**当前保留产物**：`latest_model.joblib` + `latest_model_metrics.json`（sentence-transformer 后端）。

## 结论与解读

1. **在合成数据上，降级后端反而略优**（F1 差 0.006）。原因很直观：合成数据由模板生成，
   字符频率特征足以精确匹配模板；真实语义向量在这种"同模板即同标签"的数据上没有额外信息增量。
2. **仍然保留 sentence-transformer 版本作为线上模型**：真实线上数据不存在模板对齐，
   语义向量的泛化能力只在真实分布上才能体现；字符频率后端仅作为模型加载失败时的兜底。
3. 两个后端的 recall 完全一致（0.8487），主要差异在 precision——ST 版把 2 条正常文本误判为虚假。
4. ⚠️ 再次强调 metrics 中的 `synthetic_data_warning`：以上数字来自合成数据，
   **不能代表真实线上泛化能力**。拿到真实标注数据后需要重新评估。

## 复现方式

```bash
# 真实语义后端（模型已在 models/cache，离线可跑）
HF_HUB_OFFLINE=1 python scripts/train_rf_model.py --use-sentence-transformer

# 降级后端基线
python scripts/train_rf_model.py
```
