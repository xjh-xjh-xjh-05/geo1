# Tasks

- [ ] Task 1: 重构 Scorer 筛选决策逻辑
  - [ ] 1.1: 重写 `_is_fake()` 方法，实现多因子加权判断（综合评分 + 异常严重度 + 营销词上下文）
  - [ ] 1.2: 重写 `_calculate_total_score()` 支持动态权重调整（文本为空时降权、无坐标时降权、批量模式提升语义权重）
  - [ ] 1.3: 新增 `_calculate_confidence()` 方法，基于评分与阈值距离计算置信度
  - [ ] 1.4: 更新 `config.py` 的 `ScorerConfig`，新增动态权重配置参数

- [ ] Task 2: 增强文本规则引擎筛选
  - [ ] 2.1: 重写 `_check_suspicious_keywords()` 支持营销词密度计算和严重度分级（high_severity_marketing / moderate_marketing）
  - [ ] 2.2: 优化 `_check_template()` 支持与营销词检测的严重度叠加
  - [ ] 2.3: 新增 `_calculate_marketing_density()` 方法计算营销词占比

- [ ] Task 3: 重构神经网络模型融合特征
  - [ ] 3.1: 重写 `FakeDetectionModel.forward()` 融合文本特征向量（字符级编码）和地理特征向量
  - [ ] 3.2: 新增 `_encode_text()` 方法实现字符级文本编码（无需预训练模型依赖）
  - [ ] 3.3: 更新 `NeuralScorer.analyze()` 使用融合模型输出，避免重复调用规则引擎
  - [ ] 3.4: 确保 PyTorch 不可用时降级为纯规则评分

- [ ] Task 4: 改进训练数据生成
  - [ ] 4.1: 扩展 `create_training_data()` 增加多样化模板（正常评论多风格、营销刷量分密度、地理异常、混合型、边界案例）
  - [ ] 4.2: 将默认样本量从2000提升至5000，正负比例约6:4
  - [ ] 4.3: 新增地理异常数据生成（坐标异常、瞬移轨迹、高频上报设备）
  - [ ] 4.4: 更新 `FakeDetectionDataset` 适配融合特征（文本+地理）

- [ ] Task 5: 统一模型系统
  - [ ] 5.1: 扩展 `ModelManager` 支持同时管理 sklearn 模型和神经网络模型
  - [ ] 5.2: 在 `OptimizedDetectionService` 中统一通过 `ModelManager` 调用模型
  - [ ] 5.3: 更新 `api/routers/ai_models.py` 支持神经网络模型的注册和训练

- [ ] Task 6: 优化结果融合逻辑
  - [ ] 6.1: 重写 `_merge_results()` 使用基于置信度的加权融合替代硬编码分数调整
  - [ ] 6.2: 新增 `_calculate_source_weights()` 方法根据各来源可靠性计算融合权重
  - [ ] 6.3: 新增 `_fuse_confidence()` 方法融合多源置信度

- [ ] Task 7: 增加模型评估框架
  - [ ] 7.1: 在 `scripts/train_model.py` 中增加完整评估指标输出（精确率、召回率、F1、混淆矩阵）
  - [ ] 7.2: 新增 `scripts/evaluate_model.py` 独立评估脚本，支持模型对比
  - [ ] 7.3: 在 `api/routers/ai_models.py` 中增加模型评估 API 端点

# Task Dependencies
- [Task 2] depends on [Task 1] (文本严重度分级需被 Scorer 的多因子决策使用)
- [Task 3] depends on [Task 4] (模型结构变更需与训练数据同步)
- [Task 5] depends on [Task 3] (统一模型系统需先完成神经网络模型重构)
- [Task 6] depends on [Task 1, Task 5] (结果融合需依赖新的评分逻辑和统一模型接口)
- [Task 7] depends on [Task 4, Task 5] (评估框架需在训练和模型系统完成后验证)
