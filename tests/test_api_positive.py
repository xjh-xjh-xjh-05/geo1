"""
API 正向路径测试（登录态端到端）

补齐此前缺失的正向用例：登录成功、带认证的检测/记录/审核/规则/关键词/统计查询。
使用内存 SQLite + FastAPI dependency_overrides，测试之间互不干扰、不污染数据文件。
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from api.main import app
from api.core.database import Base, get_db
from api.core.security import get_current_user, get_password_hash
from api.models.db_models import Tenant, User

TEST_PASSWORD = "test-password-123"


@pytest.fixture(scope="module")
def db_session():
    """模块级内存数据库：建表 + 种子数据（租户/管理员用户）"""
    # 显式导入 db_models 确保所有表注册到 Base.metadata
    import api.models.db_models  # noqa: F401

    # check_same_thread=False：TestClient 在工作线程中执行请求，
    # 内存 SQLite 需允许跨线程复用连接
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()

    session.add(Tenant(id=1, name="测试租户", code="test-tenant"))
    session.add(User(
        id=1,
        tenant_id=1,
        username="testuser",
        email="test@example.com",
        password_hash=get_password_hash(TEST_PASSWORD),
        role="admin",
        permissions=["detect:read", "detect:write"],
        status="active",
    ))
    session.commit()

    yield session

    session.close()
    engine.dispose()


@pytest.fixture
def client(db_session):
    """带认证与数据库覆盖的测试客户端"""
    def _override_get_db():
        yield db_session

    def _fake_current_user():
        return {
            "id": 1,
            "username": "testuser",
            "email": "test@example.com",
            "role": "admin",
            "tenant_id": 1,
            "permissions": ["detect:read", "detect:write"],
        }

    app.dependency_overrides[get_current_user] = _fake_current_user
    app.dependency_overrides[get_db] = _override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


def _detection_payload(text: str = "今天去了天坛，环境不错，服务也很好。", device: str = "D_001") -> dict:
    return {
        "device_id": device,
        "user_id": "U_001",
        "timestamp": 1709500800,
        "geo": {"latitude": 39.9042, "longitude": 116.4074},
        "content": {"text": text},
    }


class TestAuthLoginSuccess:
    def test_login_success(self, client):
        """正确凭证登录返回双 token 与用户信息"""
        response = client.post("/api/v1/auth/login", json={
            "username": "testuser",
            "password": TEST_PASSWORD,
            "tenant_id": 1,
        })
        assert response.status_code == 200
        data = response.json()
        assert data["access_token"]
        assert data["refresh_token"]
        assert data["token_type"] == "bearer"
        assert data["expires_in"] > 0
        assert data["user"]["username"] == "testuser"
        assert data["user"]["role"] == "admin"

    def test_login_wrong_password(self, client):
        """错误密码返回 401"""
        response = client.post("/api/v1/auth/login", json={
            "username": "testuser",
            "password": "definitely-wrong",
            "tenant_id": 1,
        })
        assert response.status_code == 401

    def test_logout_with_auth(self, client):
        """登录态登出成功"""
        response = client.post("/api/v1/auth/logout")
        assert response.status_code == 200


class TestDetectionPositive:
    def test_detect_single_success(self, client):
        """带认证的单条检测返回完整评分结构"""
        response = client.post("/api/v1/detect/single", json=_detection_payload())
        assert response.status_code == 200
        data = response.json()["data"]

        assert data["record_id"]
        assert 0 <= data["suspicion_score"] <= 100
        assert data["risk_level"] in ("low", "medium", "high")
        assert isinstance(data["is_fake"], bool)

        scores = data["scores"]
        for key in ("geo_score", "text_score", "simhash_score", "semantic_score"):
            assert key in scores
            assert 0 <= scores[key] <= 100

    def test_detect_single_neural_dimension_contract(self, client):
        """神经网络维度契约：模型可用时为 0-100 数值，不可用时为 null，均不报错"""
        response = client.post(
            "/api/v1/detect/single",
            json=_detection_payload(text="超级超级推荐！必去必买！绝绝子！yyds！"),
        )
        assert response.status_code == 200
        neural_score = response.json()["data"]["scores"]["neural_score"]
        if neural_score is not None:
            assert 0 <= neural_score <= 100

    def test_detect_batch_success(self, client):
        """带认证的批量检测返回汇总与逐条结果"""
        payload = {
            "records": [
                _detection_payload("环境不错，值得推荐。", device="D_001"),
                _detection_payload("超级超级推荐！绝绝子！", device="D_002"),
            ]
        }
        response = client.post("/api/v1/detect/batch", json=payload)
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["summary"]["total"] == 2
        assert len(data["results"]) == 2


class TestQueryEndpointsPositive:
    def test_list_records(self, client):
        response = client.get("/api/v1/records")
        assert response.status_code == 200

    def test_list_review_pending(self, client):
        response = client.get("/api/v1/review/pending")
        assert response.status_code == 200

    def test_list_rules(self, client):
        response = client.get("/api/v1/rules")
        assert response.status_code == 200

    def test_list_keywords(self, client):
        response = client.get("/api/v1/keywords")
        assert response.status_code == 200

    def test_stats_overview(self, client):
        response = client.get("/api/v1/stats/overview")
        assert response.status_code == 200
