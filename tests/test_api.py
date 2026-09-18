"""
API测试
"""
import pytest
from fastapi.testclient import TestClient
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime

from api.main import app


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def mock_db():
    with patch("api.core.database.SessionLocal") as mock:
        db = MagicMock()
        mock.return_value = db
        # 默认查询无结果：保证"无效凭证"等路径命中401而不是在
        # MagicMock属性上抛异常（MagicMock.user.password_hash不可验证）
        db.query.return_value.filter.return_value.first.return_value = None
        yield db


@pytest.fixture
def mock_user():
    return {
        "id": 1,
        "username": "testuser",
        "email": "test@example.com",
        "role": "admin",
        "tenant_id": 1,
        "permissions": ["detect:read", "detect:write"]
    }


@pytest.fixture
def auth_headers(mock_user):
    from api.core.security import create_access_token
    token = create_access_token(data={"sub": mock_user["id"], "tenant_id": mock_user["tenant_id"]})
    return {"Authorization": f"Bearer {token}"}


class TestHealthCheck:
    def test_health_check(self, client):
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"


class TestRootEndpoint:
    def test_root(self, client):
        response = client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert "name" in data
        assert "version" in data
        assert "endpoints" in data


class TestAuthEndpoints:
    def test_login_invalid_credentials(self, client, mock_db):
        response = client.post(
            "/api/v1/auth/login",
            json={
                "username": "invalid",
                "password": "wrongpwd",
                "tenant_id": 1
            }
        )
        assert response.status_code == 401


class TestDetectionEndpoints:
    def test_detect_single_unauthorized(self, client):
        response = client.post(
            "/api/v1/detect/single",
            json={
                "device_id": "D_001",
                "user_id": "U_001",
                "timestamp": 1709500800,
                "geo": {
                    "latitude": 39.9042,
                    "longitude": 116.4074
                },
                "content": {
                    "text": "测试内容"
                }
            }
        )
        assert response.status_code == 403 or response.status_code == 401


class TestRecordEndpoints:
    def test_list_records_unauthorized(self, client):
        response = client.get("/api/v1/records")
        assert response.status_code == 403 or response.status_code == 401


class TestReviewEndpoints:
    def test_list_pending_unauthorized(self, client):
        response = client.get("/api/v1/review/pending")
        assert response.status_code == 403 or response.status_code == 401


class TestRuleEndpoints:
    def test_list_rules_unauthorized(self, client):
        response = client.get("/api/v1/rules")
        assert response.status_code == 403 or response.status_code == 401


class TestKeywordEndpoints:
    def test_list_keywords_unauthorized(self, client):
        response = client.get("/api/v1/keywords")
        assert response.status_code == 403 or response.status_code == 401


class TestStatsEndpoints:
    def test_stats_overview_unauthorized(self, client):
        response = client.get("/api/v1/stats/overview")
        assert response.status_code == 403 or response.status_code == 401
