"""
用户服务测试
"""
import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime

from api.services.user_service import UserService
from api.models.db_models import User


class TestUserService:
    
    @pytest.fixture
    def mock_db(self):
        return MagicMock()
    
    @pytest.fixture
    def mock_user(self):
        user = User()
        user.id = 1
        user.username = "testuser"
        user.email = "test@example.com"
        user.password_hash = "$2b$12$test_hash"
        user.tenant_id = 1
        user.role = "user"
        user.status = "active"
        user.permissions = []
        return user
    
    def test_get_by_id(self, mock_db, mock_user):
        mock_db.query.return_value.filter.return_value.first.return_value = mock_user
        
        service = UserService(mock_db)
        result = service.get_by_id(1)
        
        assert result is not None
        assert result.username == "testuser"
    
    def test_get_by_username(self, mock_db, mock_user):
        mock_db.query.return_value.filter.return_value.first.return_value = mock_user
        
        service = UserService(mock_db)
        result = service.get_by_username("testuser", 1)
        
        assert result is not None
        assert result.username == "testuser"
    
    def test_authenticate_success(self, mock_db, mock_user):
        mock_db.query.return_value.filter.return_value.first.return_value = mock_user
        
        with patch("api.services.user_service.verify_password", return_value=True):
            service = UserService(mock_db)
            result = service.authenticate("testuser", "password", 1)
            
            assert result is not None
            assert "access_token" in result
            assert "refresh_token" in result
    
    def test_authenticate_wrong_password(self, mock_db, mock_user):
        mock_db.query.return_value.filter.return_value.first.return_value = mock_user
        
        with patch("api.services.user_service.verify_password", return_value=False):
            service = UserService(mock_db)
            result = service.authenticate("testuser", "wrongpassword", 1)
            
            assert result is None
    
    def test_authenticate_user_not_found(self, mock_db):
        mock_db.query.return_value.filter.return_value.first.return_value = None
        
        service = UserService(mock_db)
        result = service.authenticate("nonexistent", "password", 1)
        
        assert result is None
