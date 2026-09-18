# 优化筛选逻辑与模型训练 Spec

## Why
当前检测系统的筛选逻辑过于简单粗暴（硬编码阈值、固定权重、缺乏置信度融合），且模型训练使用模板合成数据、神经网络未真正利用文本特征，导致误判率高、检测精度不足。需要优化筛选决策逻辑并建立真实数据驱动的模型训练流程。

## What Changes
- 重构 `Scorer._is_fake()` 决策逻辑，引入多因子加权判断和置信度评估
- 优化 `_calculate_total_score()` 支持动态权重调整
- 增强 `TextRuleEngine` 筛选逻辑，支持上下文感知和严重度分级
- 重构 `FakeDetectionModel` 融合文本语义特征与地理特征
- 改进训练数据生成，增加多样性真实场景模拟
- 统一 `neural_model.py` 和 `modules/ai_model` 两套模型系统
- 优化 `OptimizedDetectionService._merge_results()` 的结果融合逻辑
- 增加模型评估指标和验证框架

## Impact
- Affected specs: 核心检测引擎、AI模型模块、检测服务
- Affected code:
  - `engine/scorer.py` - 评分与筛选逻辑
  - `engine/text_rules.py` - 文本规则引擎
  - `engine/geo_rules.py` - GEO规则引擎
  - `engine/neural_model.py` - 神经网络模型
  - `scripts/train_model.py` - 模型训练脚本
  - `modules/ai_model/__init__.py` - AI模型模块
  - `api/services/detection_service.py` - 检测服务
  - `config.py` - 配置参数

## ADDED Requirements

### Requirement: 智能筛选决策
系统 SHALL 提供多因子加权筛选决策，替代当前的硬编码阈值判断。

#### Scenario: 综合评分低于低风险阈值
- **WHEN** 记录的综合评分低于 `low_risk_threshold` 且无任何异常
- **THEN** 判定为正常内容，`is_fake=False`，`risk_level="low"`

#### Scenario: 综合评分达到中风险但异常严重度低
- **WHEN** 记录综合评分在 `medium_risk_threshold` 到 `high_risk_threshold` 之间，且所有异常严重度均低于0.5
- **THEN** 判定为可疑内容，`is_fake=False`，`risk_level="medium"`

#### Scenario: 存在高严重度异常
- **WHEN** 记录存在严重度 >= 0.8 的异常（如瞬移、无效坐标）
- **THEN** 无论综合评分如何，`is_fake=True`，`risk_level="high"`

#### Scenario: 营销词触发但上下文正常
- **WHEN** 营销词数量 >= 3 但 GEO 完全正常且无重复/聚类异常
- **THEN** 判定为可疑而非虚假，`is_fake=False`，`risk_level="medium"`

### Requirement: 动态权重评分
系统 SHALL 支持根据数据特征动态调整各维度评分权重。

#### Scenario: 文本内容为空
- **WHEN** 记录的文本内容为空或过短
- **THEN** 自动将 `text_rule_weight` 降为0，将权重重新分配给其他维度

#### Scenario: 无地理坐标
- **WHEN** 记录的经纬度均为0
- **THEN** 自动将 `geo_weight` 降为0，将权重重新分配给其他维度

#### Scenario: 批量检测模式
- **WHEN** 批量检测记录数 > 10 且启用聚类
- **THEN** 提升 `semantic_weight` 至0.25，降低其他权重以突出批量刷量特征

### Requirement: 增强文本筛选
系统 SHALL 提供上下文感知的文本筛选，支持严重度分级而非二元判断。

#### Scenario: 营销词密度高
- **WHEN** 文本中营销词占比超过5%
- **THEN** 标记为 `high_severity_marketing`，严重度0.8

#### Scenario: 营销词密度中等
- **WHEN** 文本中营销词占比在2%-5%之间
- **THEN** 标记为 `moderate_marketing`，严重度0.5

#### Scenario: 模板匹配与营销词同时命中
- **WHEN** 文本同时命中模板匹配和营销词检测
- **THEN** 严重度叠加，最高不超过1.0

### Requirement: 融合特征神经网络模型
系统 SHALL 提供融合文本语义特征和地理特征的神经网络模型。

#### Scenario: 模型推理
- **WHEN** 对记录进行模型推理
- **THEN** 模型同时接收文本特征向量（通过字符级编码或预训练模型）和地理特征向量，输出虚假概率

#### Scenario: 模型不可用
- **WHEN** PyTorch未安装或模型文件不存在
- **THEN** 降级为纯规则评分，不影响系统正常运行

### Requirement: 改进训练数据
系统 SHALL 提供更多样化的训练数据生成，覆盖真实场景。

#### Scenario: 训练数据生成
- **WHEN** 运行训练脚本
- **THEN** 生成包含以下类别的训练数据：
  - 正常评论（多种风格：简洁、详细、中性评价）
  - 营销刷量（不同密度：轻度、中度、重度）
  - 地理异常（坐标异常、瞬移、高频上报）
  - 混合型（同时存在文本和地理异常）
  - 边界案例（似是而非的内容）

#### Scenario: 训练数据规模
- **WHEN** 生成默认训练数据
- **THEN** 至少生成5000条记录，正负样本比例约6:4

### Requirement: 统一模型系统
系统 SHALL 统一 `engine/neural_model.py` 和 `modules/ai_model` 两套模型系统。

#### Scenario: 模型调用
- **WHEN** 检测服务需要AI模型预测
- **THEN** 通过统一的 `ModelManager` 接口调用，支持 sklearn 模型和神经网络模型的统一管理

#### Scenario: 模型切换
- **WHEN** 管理员切换活跃模型
- **THEN** 无需重启服务即可生效

### Requirement: 结果融合优化
系统 SHALL 提供基于置信度的结果融合，替代硬编码分数调整。

#### Scenario: 多源结果融合
- **WHEN** 规则引擎、交叉验证、AI模型三个来源均有结果
- **THEN** 使用加权置信度融合，权重由各来源的历史准确率决定

#### Scenario: 单一来源结果
- **WHEN** 仅有规则引擎结果
- **THEN** 直接使用规则引擎结果，置信度基于评分与阈值的距离计算

### Requirement: 模型评估框架
系统 SHALL 提供模型评估指标和验证框架。

#### Scenario: 训练后评估
- **WHEN** 模型训练完成
- **THEN** 输出准确率、精确率、召回率、F1分数、混淆矩阵等指标

#### Scenario: 模型对比
- **WHEN** 存在多个已训练模型
- **THEN** 支持对比不同模型的评估指标

## MODIFIED Requirements

### Requirement: Scorer评分逻辑
原逻辑：固定权重加权 + 硬编码阈值判断 `is_fake`
修改为：动态权重加权 + 多因子决策 + 置信度评估

### Requirement: TextRuleEngine关键词检测
原逻辑：简单子串匹配，阈值固定为3
修改为：密度计算 + 严重度分级 + 上下文感知

### Requirement: FakeDetectionModel前向传播
原逻辑：仅使用10维地理特征，忽略文本输入
修改为：融合文本特征向量和地理特征向量

## REMOVED Requirements

### Requirement: 硬编码分数调整
**Reason**: `_merge_results()` 中的硬编码分数调整（+20, +10, +15, -10）缺乏理论依据，替换为基于置信度的融合
**Migration**: 使用加权置信度融合替代
