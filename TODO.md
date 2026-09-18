# 未完成部分与完成思路

> 整理日期：2026-09-12 ｜ 配套文档：[PROGRESS.md](PROGRESS.md)（整体进度报告）
> 本文档只聚焦「还没做完的事」和「怎么把它做完」，按优先级排序。

---

## 优先级总览

| # | 事项 | 类型 | 预估工作量 | 价值 |
|---|------|------|-----------|------|
| 1 | 初始化 git 仓库 | 工程治理 | 10 分钟 | ⭐⭐⭐ 保命项 |
| 2 | 训练并落地检测模型（Phase 9） | 核心功能 | 半天 | ⭐⭐⭐ 项目核心卖点 |
| 3 | Kafka 实时流处理实测（Phase 8） | 核心功能 | 半天 | ⭐⭐⭐ README 承诺的最后一块 |
| 4 | ✅ 神经网络模型接入核心检测链路（2026-09-18 完成，见下） | 核心功能 | — | ⭐⭐⭐ 让训练成果真正生效 |
| 5 | ✅ API 正向路径测试补齐（2026-09-18 完成，+21 用例，全量 114 passed） | 质量保障 | — | ⭐⭐ 当前测试虚胖 |
| 6 | 更新 README 与文档同步 | 文档 | 1 小时 | ⭐⭐ 答辩/展示必看 |
| 7 | 小问题清理（依赖声明、弃用警告、表结构漂移） | 技术债 | 1-2 小时 | ⭐⭐ |
| 8 | 微服务空壳处置（rule/data-service） | 架构决策 | 补全 2-3 天 / 砍掉 10 分钟 | ⭐ 视目标而定 |

---

## 1️⃣ 初始化 git 仓库（最优先，10 分钟）

**现状**：项目完全没有版本控制，误删/改坏代码无法回退。

**完成思路**：
```bash
cd C:\Users\xu\Desktop\大创\geo-fake-detection
# 1. 创建 .gitignore（内容见下）
git init
git add .
git commit -m "init: 项目现状首次提交"
```

`.gitignore` 关键内容：
```gitignore
__pycache__/
*.pyc
*.db
logs/
models/saved/
data/models/
.env
.venv/
```

**验收**：`git log` 能看到首次提交；`git status` 干净。

---

## 2️⃣ 训练并落地检测模型（Phase 9 核心）

**现状**：
- `scripts/train_model.py` 完整可用：BERT 类模型（hfl/chinese-roberta-wwm-ext）+ 10 维地理特征，8:1:1 划分数据
- 训练数据已有：`data/training_data.json`（约 680KB，含模板生成的正/负样本）
- 本机环境已确认：**torch 2.5.1 + CUDA 可用**、transformers 5.3.0 已安装 ✅
- **缺口**：`models/saved/` 和 `data/models/` 均为空，从未跑过训练；`requirements.txt` 未声明 torch/transformers

**完成思路**：
1. **先跑通 CPU 小规模验证**（避免直接全量训练踩坑）：
   ```bash
   # 临时改 TrainingConfig: num_epochs=1, batch_size=32, use_cuda=False（或直接用 CUDA）
   python scripts/train_model.py
   ```
2. **确认产物路径**：脚本默认保存到 `data/models/fake_detection_model.pt`，训练成功后**复制一份到 `models/saved/`**，与 README 描述的目录对齐（二选一，统一即可）。
3. **跑评估**：`python scripts/evaluate_model.py`，记录 precision / recall / F1 / 混淆矩阵，留作答辩材料。
4. **接入线上推理**：通过已有的 `POST /api/v1/ai/models`（RegisterNeuralModelInput 支持 model_path）把训练好的模型注册进 ModelManager，让 `/api/v1/ai/predict` 用上真模型。
5. **补依赖声明**：requirements.txt 增加 `torch>=2.0`、`transformers>=4.30`（注明 GPU 版本按环境安装）。

**风险与对策**：
- 首次运行会下载中文 RoBERTa 权重（约 400MB），需网络畅通；下载慢可换镜像 `HF_ENDPOINT=https://hf-mirror.com`。
- 训练数据是**模板生成的合成数据**，指标会虚高——报告里要如实说明，别当真实效果宣传。
- 显存不足时：batch_size 降到 8、max_length 降到 64。

**验收**：`models/saved/`（或 data/models/）有 `.pt` 文件；evaluate 输出 F1 报告；API 预测接口调用的是训练后的模型。

---

## 3️⃣ Kafka 实时流处理实测（Phase 8）

**现状**：
- `api/services/kafka_service.py` 完整实现了 topic 自动创建（geo-detection-requests / geo-detection-results）、producer/consumer、后台消费线程，并挂载在应用 lifespan
- **单体 `docker-compose.yml` 里没有 Kafka 服务**（只有 postgres + redis）——这就是 Phase 8 一直"实现未验证"的直接原因
- Kafka 基础设施只存在于 `docker-compose-microservices.yml`（confluentinc/cp-kafka + zookeeper），但微服务编排本身因空壳服务跑不起来

**完成思路**（最小代价路线：只补 Kafka，不动微服务）：
1. **给单体 compose 补 Kafka**（约 15 行）：
   ```yaml
   zookeeper:
     image: confluentinc/cp-zookeeper:7.5.0
     environment:
       ZOOKEEPER_CLIENT_PORT: 2181
   kafka:
     image: confluentinc/cp-kafka:7.5.0
     depends_on: [zookeeper]
     ports: ["9092:9092"]
     environment:
       KAFKA_BROKER_ID: 1
       KAFKA_ZOOKEEPER_CONNECT: zookeeper:2181
       KAFKA_ADVERTISED_LISTENERS: PLAINTEXT://kafka:9092,PLAINTEXT_HOST://localhost:9092
       KAFKA_LISTENER_SECURITY_PROTOCOL_MAP: PLAINTEXT:PLAINTEXT,PLAINTEXT_HOST:PLAINTEXT
       KAFKA_OFFSETS_TOPIC_REPLICATION_FACTOR: 1
   ```
2. **容器内验证连通**：`docker compose up -d` 后看 api 日志应出现 "Kafka realtime detection service started"，且自动建 topic。
3. **写一个端到端集成测试**（放进 tests/）：向 `geo-detection-requests` topic 发一条检测请求 → 轮询 `geo-detection-results` topic 断言收到结果。可以参考 `tests/test_api.py` 的写法。
4. **验证业务端点**：`POST /api/v1/detect/stream` 全链路跑通。
5. **更新 README**：Phase 8 打勾，并补充 Kafka 部署说明。

**降级方案**：如果不想引入 Kafka 依赖，也可以把 Phase 8 的范围改为"进程内异步队列（asyncio.Queue）实现流式接口"，但价值打折，不推荐。

**验收**：集成测试通过；`detect/stream` 发一条消息能在 5 秒内拿到检测结果。

---

## 4️⃣ 神经网络模型接入核心检测链路 ✅ 已完成（2026-09-18）

> 实施记录：Scorer 新增懒加载 `_neural_score` 辅助方法 + 第五维度 `neural_score` 参与
> `_calculate_total_score` 加权融合（`neural_weight=0.15`，模型不可用时自动归零，
> 行为与原四维融合完全一致）；单条与批量两条路径均已接入；
> `DetectionScores` schema 新增可选 `neural_score` 字段并贯通 API 响应。
> 附带修复：`train_model.py` 学习率 2e-5（BERT 微调值）不适配本模型的字符编码 MLP，
> 调整为 1e-3 / 30 epochs 后收敛（测试 F1=1.0，合成数据）；模型产物
> `data/models/fake_detection_model.pt` 已生成。测试：`tests/test_neural_integration.py`。

**现状**（本轮深入检查新发现）：
- 核心检测链路 `api/services/detection_service.py` → `engine/scorer.py` **只融合四个维度**：GEO 规则、文本规则、SimHash、语义聚类
- `engine/neural_model.py`（神经网络）**没有被核心链路引用**，只能通过 `/api/v1/ai/*` 路由单独调用
- 也就是说：即使完成了第 2 项训练，主检测接口 `/api/v1/detect/single|batch|stream` 的结果**依然不含模型判断**——训练成果没有真正生效

**完成思路**：
1. **方案 A（推荐）——作为第五维度融入评分**：
   - `Scorer._calculate_total_score` 增加 `neural_w` 权重项（如初始 15%，相应下调其他权重）
   - 模型不可用（无 .pt 文件 / 无 torch）时权重自动置 0，保持向后兼容——参考 `neural_model.py` 已有的 `HAS_TORCH` 降级模式
   - Scorer 初始化时懒加载模型，避免拖慢 API 启动
2. **方案 B——双轨并行**：保持现状，把神经网络定位为「AI 辅助检测」独立能力，仅在文档中明确说明两条链路的分工（答辩时可能被问"模型怎么用的"，要能答上）
3. 无论哪种方案，训练完成后至少用真实样本对比「纯规则」vs「规则+模型」的 F1，作为融合收益的证据

**验收**：方案 A 下 `/api/v1/detect/single` 的响应 scores 中出现模型维度；删除模型文件后接口不报错。

---

## 5️⃣ API 正向路径测试补齐 ✅ 已完成（2026-09-18）

> 实施记录：新增 `tests/test_api_positive.py`（14 用例）+ `tests/test_neural_integration.py`（7 用例）。
> 采用内存 SQLite（StaticPool + check_same_thread=False）+ `app.dependency_overrides` 注入认证与数据库，
> 种子数据含租户与管理员用户。覆盖：登录成功/失败/登出、单条检测完整评分结构、
> 神经网络维度契约（数值或 null 均合法）、批量检测汇总、records/review/rules/keywords/stats 查询。
> 全量回归 114 passed（venv）与 18/18（anaconda，真实模型路径）双环境验证。

**现状**（本轮深入检查新发现）：
- 93 个测试中，`tests/test_api.py` 只有 9 个用例，且**基本都是断言 401 未授权**的负面路径
- 大量测试集中在引擎层（test_core 38 个、test_engine_filtering 28 个）——引擎扎实，但 **API 层的登录态正向用例几乎为零**
- 「登录 → 单条检测 → 查记录 → 审核」这条主业务链路没有任何测试保护

**完成思路**：
1. 在 `tests/conftest.py` 增加认证 fixture：初始化测试用户 → 登录拿 token → 提供带 `Authorization` 头的 client
2. 补 6-8 个关键正向用例：
   - 登录成功返回 token
   - 带认证的 `/detect/single` 返回完整评分结构
   - `/detect/batch` 批量结果条数正确
   - `/records` 查询、`/review/pending` 列表
   - `/rules`、`/keywords` 的 CRUD 闭环
   - `/stats/overview` 返回统计数据
3. 参考现有 `tests/test_user_service.py` 的用户初始化写法，避免重复造轮子

**验收**：pytest 总数从 93 → 100+，API 正向用例全部通过。

---

## 6️⃣ README 与文档同步

**现状**：README 缺少 modules/、services/、scripts/、ai_models 等 6 个新路由的说明；Phase 8/9 状态过时；微服务部署方式未提。

**完成思路**：
1. 项目结构图补充：`modules/`（预处理、AI模型、UI组件）、`services/`（微服务）、`scripts/`（训练/评估/迁移/初始化）
2. 功能列表补充：AI 模型管理、数据管理、后端管理、预处理、告警等新路由
3. 开发状态按实际更新（Phase 8/9 完成后一并改）
4. 部署章节补两种模式：单体 compose（含 Kafka）和微服务 compose，并注明后者尚不完整

**验收**：新人按 README 能一次跑通「启动 → 登录 → 单条检测 → 查看结果」。

---

## 7️⃣ 小问题清理（技术债）

| 问题 | 思路 |
|------|------|
| `requirements.txt` 缺 torch/transformers | 增加声明 + 注释说明 GPU 版安装方式 |
| 33 处 `datetime.utcnow()` 弃用警告 | 全局替换为 `datetime.now(timezone.utc)`；集中在 `api/core/security.py`、`api/services/user_service.py` 等，一次 sed/编辑可完成；改完跑 pytest 回归 |
| `database/schema.sql`（16 张表）与 ORM `db_models.py`（12 张表）**数量不一致**，存在表结构漂移 | 运行时实际以 `Base.metadata.create_all`（ORM）为准；建议以 ORM 为唯一事实来源，schema.sql 仅保留扩展性说明或标注过时，避免误导后来者 |
| `docs/api_spec.yaml` 手工维护的 38 个路径 vs 实际 16 个路由模块，两者已脱节 | FastAPI 自带 `/docs` 自动生成 OpenAPI；建议在 api_spec.yaml 头部标注「以 /docs 为准」，或直接删掉手写版 |
| `__pycache__` 散落各目录 | 已在 .gitignore 排除，git add 时自然不会提交 |
| 本地 SQLite 与文档声明的 PostgreSQL 并存 | .env 实际用 `sqlite:///./geo_fake_detection.db`；明确口径：本地开发默认 SQLite（零配置），生产用 PostgreSQL；在 README 配置说明里写清楚 |

---

## 8️⃣ 微服务空壳处置（rule-service / data-service）

**现状**：`services/` 下 6 个服务目录，其中 **api-gateway 是唯一真正可用的**（自包含 HTTP 代理，2026-09-18 已验证）。user-service 和 detection-service 的 main.py 是**针对不存在的旧接口编写的过期脚手架**（引用了 `authenticate_user`、`get_user_by_id(db,...)`、`DetectionScorer`、`engine.mock_data` 等主代码中不存在的方法/模块），导入级错误已修复（Settings extra=ignore、schema/service 类名别名），但端点逻辑需按现行接口重写才能运行；monitoring 仅 Prometheus 配置；rule-service 和 data-service 只有空目录。微服务 compose 依赖空壳服务，整套编排无法启动。

**思路 A（推荐，适合大创结题）——收缩范围**：
- 把 rule/data 相关能力已存在于单体 API 中（routers/rules.py、data_management.py）这一事实写进文档
- 从 `docker-compose-microservices.yml` 删除这两个服务的依赖，让已实现的 3 个服务能跑起来演示
- 在 README 中如实说明"微服务化为架构演进方向，当前以单体优先"

**思路 B（如果要冲架构分）——补全两个服务**：
- rule-service：把 `api/routers/rules.py` + `api/models/db_models.py` 中规则相关表抽成独立 FastAPI 服务，暴露 CRUD + 规则热加载接口，网关做路由转发
- data-service：把数据导入导出、记录查询迁出，独立数据库连接
- 每个服务约 2-3 天，且要补对应测试；**建议结题前只做思路 A**

---

## 建议的执行顺序（一条时间线）

```
第 1 步（10min）   git init + .gitignore + 首次提交
第 2 步（半天）    跑 train_model.py → 保存模型 → evaluate 出报告 → 注册进 API
第 3 步（半天-1天） 神经网络模型接入 scorer 融合（TODO 第 4 项，方案 A）
第 4 步（半天）    compose 补 Kafka → 集成测试 → detect/stream 实测
第 5 步（半天）    API 正向路径测试补齐（认证 fixture + 6-8 个用例）
第 6 步（1h）      更新 README（Phase 8/9 打勾、结构图、部署说明、api_spec 标注）
第 7 步（1-2h）    依赖声明 + utcnow 清理 + 表结构口径统一 + pytest 回归
第 8 步（10min）   微服务空壳按思路 A 收缩 + 再次提交
```

完成后项目即达到 README 承诺的全部 9 个 Phase，且神经网络模型真正参与线上检测，可作为结题/答辩状态。
