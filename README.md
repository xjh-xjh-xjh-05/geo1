# AI驱动GEO虚假投喂检测系统

## 项目简介

本系统用于检测商用地图/GEO平台上的虚假投喂内容，包括：

- 虚假好评/刷单文案
- 虚假POI信息（地址、营业时间等）
- 虚假打卡/签到记录
- 夸大宣传、误导性描述

## 核心功能

### 1. GEO位置数据检测
- 坐标合法性校验
- 范围判断（是否在中国境内）
- 瞬移检测（短时间跨越长距离）
- 高频检测（异常上报频率）

### 2. 文本内容检测
- 关键词堆砌检测
- 模板化内容识别
- 长度/结构异常检测
- 可疑关键词过滤

### 3. 智能算法
- SimHash文本去重
- 语义向量聚类异常检测
- 综合评分融合

### 4. 商用化功能
- RESTful API服务
- 用户认证授权
- 多租户支持
- 审核标注系统
- 规则动态配置
- 统计报表分析
- 实时流处理（Kafka）

## 项目结构

```
geo-fake-detection/
├── api/                    # FastAPI服务
│   ├── core/               # 核心配置
│   │   ├── config.py       # 配置管理
│   │   ├── database.py     # 数据库连接
│   │   ├── security.py     # 安全认证
│   │   ├── cache.py        # Redis缓存
│   │   └── responses.py    # 响应格式
│   ├── models/             # 数据模型
│   │   ├── db_models.py    # ORM模型
│   │   └── schemas.py      # Pydantic模型
│   ├── routers/            # API路由
│   │   ├── auth.py         # 认证接口
│   │   ├── detect.py       # 检测接口
│   │   ├── records.py      # 记录管理
│   │   ├── review.py       # 审核管理
│   │   ├── rules.py        # 规则管理
│   │   ├── keywords.py     # 关键词管理
│   │   └── stats.py        # 统计报表
│   ├── services/           # 业务逻辑
│   │   ├── user_service.py
│   │   ├── tenant_service.py
│   │   ├── api_key_service.py
│   │   └── detection_service.py
│   └── main.py             # 应用入口
├── engine/                 # 检测引擎
│   ├── geo_rules.py        # GEO规则引擎
│   ├── text_rules.py       # 文本规则引擎
│   ├── simhash_dup.py      # SimHash去重
│   ├── semantic_cluster.py # 语义聚类
│   └── scorer.py           # 综合评分
├── utils/                  # 工具函数
│   ├── geo_utils.py        # 地理计算工具
│   └── text_utils.py       # 文本处理工具
├── generator/              # 数据生成
│   └── mock_data.py        # 模拟数据生成器
├── database/               # 数据库
│   └── schema.sql          # 数据库Schema
├── docs/                   # 文档
│   └── api_spec.yaml       # OpenAPI规范
├── tests/                  # 测试
│   ├── test_api.py
│   ├── test_detection_service.py
│   └── test_user_service.py
├── app.py                  # Streamlit界面
├── config.py               # 原有配置
├── models.py               # 原有模型
├── requirements.txt        # 依赖文件
├── Dockerfile              # Docker配置
├── docker-compose.yml      # Docker Compose
└── README.md               # 本文件
```

## 快速开始

### 方式一：Docker部署（推荐）

```bash
# 1. 克隆项目
git clone https://github.com/your-repo/geo-fake-detection.git
cd geo-fake-detection

# 2. 配置环境变量
cp .env.example .env
# 编辑 .env 文件，修改必要配置

# 3. 启动服务
docker-compose up -d

# 4. 访问服务
# API文档: http://localhost:8000/docs
# ReDoc: http://localhost:8000/redoc
```

### 方式二：本地开发

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 配置环境变量
cp .env.example .env
# 编辑 .env 文件

# 3. 初始化数据库
psql -U postgres -c "CREATE DATABASE geo_fake_detection;"
psql -U postgres -d geo_fake_detection -f database/schema.sql

# 4. 启动API服务
uvicorn api.main:app --reload --port 8000

# 5. 启动Streamlit界面（可选）
streamlit run app.py
```

## API使用示例

### 1. 用户登录

```bash
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "password": "password", "tenant_id": 1}'
```

### 2. 单条检测

```bash
curl -X POST http://localhost:8000/api/v1/detect/single \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "device_id": "D_001",
    "user_id": "U_001",
    "timestamp": 1709500800,
    "geo": {
      "latitude": 39.9042,
      "longitude": 116.4074
    },
    "content": {
      "text": "这家店超级超级推荐！环境很好！"
    }
  }'
```

### 3. 批量检测

```bash
curl -X POST http://localhost:8000/api/v1/detect/batch \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "records": [
      {
        "device_id": "D_001",
        "user_id": "U_001",
        "timestamp": 1709500800,
        "geo": {"latitude": 39.9042, "longitude": 116.4074},
        "content": {"text": "测试内容1"}
      },
      {
        "device_id": "D_002",
        "user_id": "U_002",
        "timestamp": 1709500801,
        "geo": {"latitude": 31.2304, "longitude": 121.4737},
        "content": {"text": "测试内容2"}
      }
    ]
  }'
```

### 4. 流式检测（实时处理）

```bash
curl -X POST http://localhost:8000/api/v1/detect/stream \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "device_id": "D_001",
    "user_id": "U_001",
    "timestamp": 1709500800,
    "geo": {
      "latitude": 39.9042,
      "longitude": 116.4074
    },
    "content": {
      "text": "这家店超级超级推荐！环境很好！"
    }
  }'
```

## 检测维度

| 维度 | 权重 | 检测内容 |
|------|------|----------|
| GEO规则 | 30% | 坐标合法性、范围、瞬移、频率 |
| 文本规则 | 40% | 关键词堆砌、模板化、长度异常 |
| SimHash | 15% | 文本相似度、重复检测 |
| 语义聚类 | 15%（批量25%） | SentenceTransformer/离线字符向量的批量相似内容检测 |
| 随机森林 | 融合来源 | 基于上述信号和稳定元特征给出辅助判定；GEO硬证据优先 |

## 风险等级

| 等级 | 分数范围 | 说明 |
|------|----------|------|
| 低风险 | 0-35 | 正常内容 |
| 中风险 | 35-60 | 可疑内容，需人工复核 |
| 高风险 | 60-100 | 虚假内容，建议拦截 |

## 配置说明

主要配置参数在 `.env` 文件中：

```env
# 数据库配置
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/geo_fake_detection

# Redis配置
REDIS_URL=redis://localhost:6379/0

# 安全配置
SECRET_KEY=your-secret-key-change-in-production
ACCESS_TOKEN_EXPIRE_MINUTES=120

# 配额配置
QUOTA_DEFAULT_DAILY=10000
QUOTA_DEFAULT_MONTHLY=300000

# 可选：启用本地 SentenceTransformer 语义向量
USE_SENTENCE_TRANSFORMER=false
```

### 训练本地混合模型

```bash
# 离线可运行：语义部分使用字符频率向量
python scripts/train_rf_model.py --data-path data/training_data.json

# 首次运行会下载 paraphrase-multilingual-MiniLM-L12-v2 到 models/cache
python scripts/train_rf_model.py --data-path data/training_data.json --use-sentence-transformer

# 对比规则引擎与已训练随机森林
python scripts/evaluate_model.py --data-path data/training_data.json
```

模型保存到 `models/saved/latest_model.joblib`，指标保存到
`models/saved/latest_model_metrics.json`。仓库内训练数据为模板化合成数据，
其测试指标只能用于验证训练和接入流程，不能代表真实线上泛化能力。

## 技术栈

### 后端
- **框架**: FastAPI + Uvicorn
- **数据库**: PostgreSQL + PostGIS
- **缓存**: Redis
- **ORM**: SQLAlchemy

### 检测引擎
- **地理计算**: geopy
- **文本处理**: jieba
- **SimHash**: simhash-py
- **语义向量**: sentence-transformers
- **机器学习**: scikit-learn

### 前端（可选）
- **Web界面**: Streamlit
- **可视化**: Plotly

## 开发状态

- [x] Phase 1: 基础框架 + 数据模拟
- [x] Phase 2: 规则引擎开发
- [x] Phase 3: 核心算法实现
- [x] Phase 4: API服务开发
- [x] Phase 5: 认证授权系统
- [x] Phase 6: 审核标注系统
- [x] Phase 7: 统计报表
- [ ] Phase 8: 实时流处理
- [ ] Phase 9: 模型训练平台

## 测试

```bash
# 运行所有测试
pytest

# 运行特定测试
pytest tests/test_api.py -v

# 生成覆盖率报告
pytest --cov=api tests/
```

## 部署

### Docker部署

```bash
# 构建镜像
docker build -t geo-fake-detection .

# 运行容器
docker run -d \
  -p 8000:8000 \
  -e DATABASE_URL=postgresql://... \
  -e REDIS_URL=redis://... \
  geo-fake-detection
```

### Kubernetes部署

```bash
# 应用配置
kubectl apply -f k8s/configmap.yaml
kubectl apply -f k8s/secret.yaml
kubectl apply -f k8s/deployment.yaml
kubectl apply -f k8s/service.yaml
```

## 商业价值

### 目标客户
- 地图平台: 高德、百度地图、腾讯地图
- 生活服务: 大众点评、美团、饿了么
- 社交平台: 小红书、微博、抖音
- 出行平台: 滴滴、携程、飞猪

### 收费模式
- SaaS订阅: ¥9,999 - ¥99,999/月
- API按次: ¥0.01 - ¥0.05/次
- 增值服务: 定制开发、专属模型

## 许可证

MIT License

## 联系方式

- 项目主页: https://github.com/your-repo/geo-fake-detection
- 问题反馈: https://github.com/your-repo/geo-fake-detection/issues
- 邮箱: support@geo-fake-detection.com
