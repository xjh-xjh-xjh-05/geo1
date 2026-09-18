"""
Pydantic请求/响应模型
"""
from pydantic import BaseModel, Field, validator
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class ContentType(str, Enum):
    REVIEW = "review"
    CHECKIN = "checkin"
    POI = "poi"
    COMMENT = "comment"


class GeoSource(str, Enum):
    GPS = "GPS"
    WIFI = "WIFI"
    CELL = "CELL"
    IP = "IP"


class ReviewStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    ESCALATED = "escalated"


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=100)
    password: str = Field(..., min_length=6)
    tenant_id: Optional[int] = 1


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    expires_in: int
    token_type: str = "bearer"


class UserBase(BaseModel):
    username: str
    email: str
    role: str = "user"
    permissions: List[str] = []


class UserCreate(UserBase):
    password: str = Field(..., min_length=6)


class UserUpdate(BaseModel):
    email: Optional[str] = None
    phone: Optional[str] = None
    role: Optional[str] = None
    permissions: Optional[List[str]] = None
    status: Optional[str] = None
    password: Optional[str] = None


class UserResponse(UserBase):
    id: int
    tenant_id: int
    status: str
    created_at: datetime
    
    class Config:
        from_attributes = True


class ApiKeyCreate(BaseModel):
    name: str
    permissions: List[str] = []
    ip_whitelist: List[str] = []
    rate_limit: int = 1000
    expire_days: Optional[int] = 365


class ApiKeyResponse(BaseModel):
    id: int
    name: str
    key_prefix: str
    permissions: List[str]
    rate_limit: int
    status: str
    created_at: datetime
    
    class Config:
        from_attributes = True


class ApiKeyCreateResponse(ApiKeyResponse):
    api_key: str


class GeoDataInput(BaseModel):
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)
    accuracy: Optional[float] = 10.0
    source: Optional[GeoSource] = GeoSource.GPS


class ContentDataInput(BaseModel):
    text: str = Field(..., min_length=1, max_length=5000)
    type: Optional[ContentType] = ContentType.REVIEW


class MetadataInput(BaseModel):
    ip: Optional[str] = None
    app_version: Optional[str] = None
    user_agent: Optional[str] = None
    platform: Optional[str] = None


class DetectionRequest(BaseModel):
    device_id: str = Field(..., min_length=1, max_length=100)
    user_id: str = Field(..., min_length=1, max_length=100)
    session_id: Optional[str] = None
    timestamp: int
    geo: GeoDataInput
    content: ContentDataInput
    metadata: Optional[MetadataInput] = None
    
    @validator('timestamp')
    def validate_timestamp(cls, v):
        if v < 0:
            raise ValueError('时间戳不能为负数')
        return v


class BatchDetectionRequest(BaseModel):
    records: List[DetectionRequest] = Field(..., max_length=1000)
    options: Optional[Dict[str, Any]] = None


class DetectionScores(BaseModel):
    geo_score: float = 0
    text_score: float = 0
    simhash_score: float = 0
    semantic_score: float = 0
    # 神经网络维度（0-100 虚假概率）。模型不可用时为 None，
    # 不参与总分计算，保证旧客户端兼容。
    neural_score: Optional[float] = None


class DetectionResultData(BaseModel):
    record_id: str
    suspicion_score: float
    risk_level: RiskLevel
    is_fake: bool
    confidence: Optional[float] = None
    scores: DetectionScores
    reasons: List[str] = []
    recommendation: Optional[str] = None
    processing_time_ms: int


class DetectionResponse(BaseModel):
    code: int = 200
    message: str = "success"
    data: DetectionResultData
    request_id: str
    timestamp: str


class BatchDetectionSummary(BaseModel):
    total: int
    fake_count: int
    normal_count: int
    high_risk_count: int
    medium_risk_count: int
    low_risk_count: int


class BatchDetectionResponse(BaseModel):
    code: int = 200
    message: str = "success"
    data: Dict[str, Any]
    request_id: str
    timestamp: str


class RecordQueryParams(BaseModel):
    page: int = 1
    page_size: int = 20
    device_id: Optional[str] = None
    user_id: Optional[str] = None
    risk_level: Optional[RiskLevel] = None
    review_status: Optional[ReviewStatus] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    keyword: Optional[str] = None


class RecordDetail(BaseModel):
    id: int
    record_id: str
    device_id: str
    user_id: str
    timestamp: int
    latitude: float
    longitude: float
    content_text: str
    content_type: str
    suspicion_score: float
    risk_level: str
    is_fake: bool
    geo_score: float
    text_score: float
    simhash_score: float
    semantic_score: float
    reasons: List[str]
    review_status: str
    ground_truth: Optional[bool]
    created_at: datetime
    
    class Config:
        from_attributes = True


class LabelRequest(BaseModel):
    ground_truth: bool
    feedback_type: Optional[str] = None
    feedback_comment: Optional[str] = None


class ReviewApproveRequest(BaseModel):
    comment: Optional[str] = None
    ground_truth: Optional[bool] = None


class ReviewRejectRequest(BaseModel):
    reason: str
    ground_truth: Optional[bool] = None


class ReviewEscalateRequest(BaseModel):
    reason: str
    escalate_to: str = "senior"


class RuleConfigBase(BaseModel):
    rule_type: str
    rule_name: str
    rule_code: Optional[str] = None
    rule_config: Dict[str, Any]
    description: Optional[str] = None
    enabled: bool = True
    priority: int = 100


class RuleConfigCreate(RuleConfigBase):
    pass


class RuleConfigUpdate(BaseModel):
    rule_name: Optional[str] = None
    rule_config: Optional[Dict[str, Any]] = None
    description: Optional[str] = None
    enabled: Optional[bool] = None
    priority: Optional[int] = None


class RuleConfigResponse(RuleConfigBase):
    id: int
    tenant_id: Optional[int]
    hit_count: int
    created_at: datetime
    
    class Config:
        from_attributes = True


class RuleTestRequest(BaseModel):
    rule: RuleConfigCreate
    test_data: List[DetectionRequest]


class RuleTestResult(BaseModel):
    hit_count: int
    total_count: int
    hit_rate: float
    examples: List[Dict[str, Any]]


class KeywordBase(BaseModel):
    category: str
    keyword: str
    weight: float = 1.0
    risk_level: str = "medium"
    description: Optional[str] = None


class KeywordCreate(KeywordBase):
    pass


class KeywordUpdate(BaseModel):
    weight: Optional[float] = None
    risk_level: Optional[str] = None
    enabled: Optional[bool] = None


class KeywordResponse(KeywordBase):
    id: int
    tenant_id: Optional[int]
    source: str
    hit_count: int
    enabled: bool
    created_at: datetime
    
    class Config:
        from_attributes = True


class StatsOverview(BaseModel):
    total_records: int
    fake_records: int
    normal_records: int
    fake_rate: float
    high_risk_count: int
    medium_risk_count: int
    low_risk_count: int
    avg_suspicion_score: float
    api_calls: int
    review_pending: int
    review_completed: int


class StatsTrendPoint(BaseModel):
    time: str
    value: float


class StatsDistribution(BaseModel):
    name: str
    count: int
    percentage: float


class AlertConditionConfig(BaseModel):
    metric: str
    operator: str
    threshold: float
    duration: Optional[str] = None


class AlertNotificationConfig(BaseModel):
    channels: List[str]
    emails: Optional[List[str]] = None
    webhook_url: Optional[str] = None


class AlertRuleBase(BaseModel):
    name: str
    description: Optional[str] = None
    alert_type: str
    condition_config: Dict[str, Any]
    notification_config: Dict[str, Any]
    severity: str = "warning"
    enabled: bool = True
    cooldown_minutes: int = 60


class AlertRuleCreate(AlertRuleBase):
    pass


class AlertRuleUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    condition_config: Optional[Dict[str, Any]] = None
    notification_config: Optional[Dict[str, Any]] = None
    severity: Optional[str] = None
    enabled: Optional[bool] = None
    cooldown_minutes: Optional[int] = None


class AlertRuleResponse(AlertRuleBase):
    id: int
    tenant_id: Optional[int]
    last_triggered_at: Optional[datetime]
    trigger_count: int
    created_at: datetime
    
    class Config:
        from_attributes = True


class AlertHistoryResponse(BaseModel):
    id: int
    rule_id: int
    alert_level: str
    title: str
    message: str
    status: str
    created_at: datetime
    
    class Config:
        from_attributes = True


class AlertAcknowledgeRequest(BaseModel):
    note: Optional[str] = None


class AlertResolveRequest(BaseModel):
    resolution: str


class HealthCheckResponse(BaseModel):
    status: str
    components: Dict[str, str]


class SystemMetrics(BaseModel):
    cpu_usage: float
    memory_usage: float
    disk_usage: float
    qps: float
    avg_response_time_ms: float
    active_connections: int


class SystemConfigItem(BaseModel):
    key: str
    value: str
    description: Optional[str] = None


class SystemConfigUpdate(BaseModel):
    configs: List[SystemConfigItem]


class TokenRefreshRequest(BaseModel):
    refresh_token: str


class LoginResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    user: Dict[str, Any]
