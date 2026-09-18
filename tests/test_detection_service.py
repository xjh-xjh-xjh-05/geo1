"""
检测服务测试
"""
import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime

from api.services.detection_service import DetectionService
from api.models.schemas import DetectionRequest, GeoDataInput, ContentDataInput


class TestDetectionService:
    
    @pytest.fixture
    def mock_db(self):
        return MagicMock()
    
    @pytest.fixture
    def mock_scorer(self):
        with patch("api.services.detection_service.Scorer") as mock:
            scorer = MagicMock()
            mock.return_value = scorer
            yield scorer
    
    def test_convert_request(self, mock_db, mock_scorer):
        service = DetectionService(mock_db, tenant_id=1)
        
        request = DetectionRequest(
            device_id="D_001",
            user_id="U_001",
            timestamp=1709500800,
            geo=GeoDataInput(latitude=39.9042, longitude=116.4074),
            content=ContentDataInput(text="测试内容")
        )
        
        result = service._convert_request(request)
        
        assert result.device_id == "D_001"
        assert result.user_id == "U_001"
        assert result.geo.latitude == 39.9042
        assert result.geo.longitude == 116.4074
        assert result.content.text == "测试内容"
    
    def test_get_recommendation(self, mock_db, mock_scorer):
        service = DetectionService(mock_db, tenant_id=1)
        
        assert "高风险" in service._get_recommendation("high")
        assert "人工复核" in service._get_recommendation("medium")
        assert "正常" in service._get_recommendation("low")
    
    def test_calculate_confidence(self, mock_db, mock_scorer):
        service = DetectionService(mock_db, tenant_id=1)
        
        mock_result = MagicMock()
        
        mock_result.suspicion_score = 95
        assert service._calculate_confidence(mock_result) >= 0.9
        
        mock_result.suspicion_score = 50
        assert service._calculate_confidence(mock_result) >= 0.6
