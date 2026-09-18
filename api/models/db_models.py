"""
数据库ORM模型
"""
from sqlalchemy import Column, BigInteger, String, Boolean, Integer, Numeric, Text, DateTime, JSON, ForeignKey, Index
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

try:
    from geoalchemy2 import Geometry
    HAS_GEOALCHEMY = True
except ImportError:
    HAS_GEOALCHEMY = False
    Geometry = None

from api.core.database import Base


class Tenant(Base):
    __tablename__ = "tenants"
    
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    name = Column(String(255), nullable=False)
    code = Column(String(50), unique=True, nullable=False)
    
    plan = Column(String(50), default="basic")
    quota_daily = Column(Integer, default=10000)
    quota_monthly = Column(Integer, default=300000)
    quota_used_daily = Column(Integer, default=0)
    quota_used_monthly = Column(Integer, default=0)
    
    features = Column(JSON, default=dict)
    settings = Column(JSON, default=dict)
    
    contact_name = Column(String(100))
    contact_email = Column(String(255))
    contact_phone = Column(String(50))
    
    status = Column(String(20), default="active")
    expire_at = Column(DateTime)
    
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    
    users = relationship("User", back_populates="tenant")
    records = relationship("DetectionRecord", back_populates="tenant")
    rules = relationship("RuleConfig", back_populates="tenant")
    keywords = relationship("KeywordLibrary", back_populates="tenant")


class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    tenant_id = Column(BigInteger, ForeignKey("tenants.id"))
    
    username = Column(String(100), nullable=False)
    email = Column(String(255), nullable=False)
    phone = Column(String(50))
    password_hash = Column(String(255), nullable=False)
    
    role = Column(String(50), default="user")
    permissions = Column(JSON, default=list)
    
    avatar_url = Column(String(500))
    display_name = Column(String(100))
    
    status = Column(String(20), default="active")
    last_login_at = Column(DateTime)
    last_login_ip = Column(String(45))
    
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    
    tenant = relationship("Tenant", back_populates="users")
    api_keys = relationship("ApiKey", back_populates="user")
    
    __table_args__ = (
        Index("ix_users_tenant_username", "tenant_id", "username", unique=True),
        Index("ix_users_tenant_email", "tenant_id", "email", unique=True),
    )


class ApiKey(Base):
    __tablename__ = "api_keys"
    
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    tenant_id = Column(BigInteger, ForeignKey("tenants.id"))
    user_id = Column(BigInteger, ForeignKey("users.id"))
    
    key_hash = Column(String(255), nullable=False)
    key_prefix = Column(String(20), nullable=False)
    name = Column(String(100))
    
    permissions = Column(JSON, default=list)
    ip_whitelist = Column(JSON, default=list)
    rate_limit = Column(Integer, default=1000)
    
    last_used_at = Column(DateTime)
    usage_count = Column(BigInteger, default=0)
    
    status = Column(String(20), default="active")
    expire_at = Column(DateTime)
    
    created_at = Column(DateTime, server_default=func.now())
    
    user = relationship("User", back_populates="api_keys")


class DetectionRecord(Base):
    __tablename__ = "detection_records"
    
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    record_id = Column(String(100), unique=True, nullable=False)
    tenant_id = Column(BigInteger, ForeignKey("tenants.id"), nullable=False)
    
    device_id = Column(String(100), index=True)
    user_id = Column(String(100), index=True)
    session_id = Column(String(100))
    timestamp = Column(BigInteger, index=True)
    
    latitude = Column(Numeric(10, 7))
    longitude = Column(Numeric(10, 7))
    accuracy = Column(Numeric(10, 2))
    geo_source = Column(String(20))
    
    content_text = Column(Text)
    content_type = Column(String(50))
    content_hash = Column(String(64), index=True)
    
    ip_address = Column(String(45))
    app_version = Column(String(50))
    user_agent = Column(Text)
    platform = Column(String(50))
    
    suspicion_score = Column(Numeric(5, 2))
    risk_level = Column(String(20), index=True)
    is_fake = Column(Boolean, default=False)
    confidence = Column(Numeric(5, 2), default=0.0)
    
    geo_score = Column(Numeric(5, 2), default=0)
    text_score = Column(Numeric(5, 2), default=0)
    simhash_score = Column(Numeric(5, 2), default=0)
    semantic_score = Column(Numeric(5, 2), default=0)
    
    reasons = Column(JSON, default=list)
    details = Column(JSON, default=dict)
    similar_record_ids = Column(JSON, default=list)
    
    review_status = Column(String(50), default="pending", index=True)
    reviewer_id = Column(BigInteger, ForeignKey("users.id"))
    review_comment = Column(Text)
    reviewed_at = Column(DateTime)
    
    ground_truth = Column(Boolean)
    feedback_type = Column(String(50))
    feedback_comment = Column(Text)
    
    processing_time_ms = Column(Integer)
    model_version = Column(String(50))
    
    created_at = Column(DateTime, server_default=func.now(), index=True)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    
    tenant = relationship("Tenant", back_populates="records")
    review_logs = relationship("ReviewLog", back_populates="record")


class RuleConfig(Base):
    __tablename__ = "rule_configs"
    
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    tenant_id = Column(BigInteger, ForeignKey("tenants.id"))
    
    rule_type = Column(String(50), nullable=False, index=True)
    rule_name = Column(String(100), nullable=False)
    rule_code = Column(String(100))
    
    rule_config = Column(JSON, nullable=False)
    description = Column(Text)
    
    enabled = Column(Boolean, default=True, index=True)
    priority = Column(Integer, default=100)
    
    hit_count = Column(BigInteger, default=0)
    last_hit_at = Column(DateTime)
    
    created_by = Column(BigInteger, ForeignKey("users.id"))
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    
    tenant = relationship("Tenant", back_populates="rules")
    
    __table_args__ = (
        Index("ix_rules_tenant_code", "tenant_id", "rule_code", unique=True),
    )


class KeywordLibrary(Base):
    __tablename__ = "keyword_libraries"
    
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    tenant_id = Column(BigInteger, ForeignKey("tenants.id"))
    
    category = Column(String(100), nullable=False, index=True)
    keyword = Column(String(255), nullable=False)
    
    weight = Column(Numeric(3, 2), default=1.0)
    risk_level = Column(String(20), default="medium")
    
    source = Column(String(100), default="manual")
    description = Column(Text)
    
    hit_count = Column(BigInteger, default=0)
    last_hit_at = Column(DateTime)
    
    enabled = Column(Boolean, default=True, index=True)
    created_by = Column(BigInteger, ForeignKey("users.id"))
    created_at = Column(DateTime, server_default=func.now())
    
    tenant = relationship("Tenant", back_populates="keywords")
    
    __table_args__ = (
        Index("ix_keywords_tenant_category_keyword", "tenant_id", "category", "keyword", unique=True),
    )


class ReviewLog(Base):
    __tablename__ = "review_logs"
    
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    record_id = Column(BigInteger, ForeignKey("detection_records.id"))
    tenant_id = Column(BigInteger, ForeignKey("tenants.id"))
    reviewer_id = Column(BigInteger, ForeignKey("users.id"))
    
    action = Column(String(50), nullable=False)
    old_status = Column(String(50))
    new_status = Column(String(50))
    
    old_ground_truth = Column(Boolean)
    new_ground_truth = Column(Boolean)
    
    comment = Column(Text)
    extra_data = Column(JSON, default=dict)
    
    created_at = Column(DateTime, server_default=func.now())
    
    record = relationship("DetectionRecord", back_populates="review_logs")


class ApiLog(Base):
    __tablename__ = "api_logs"
    
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    tenant_id = Column(BigInteger, ForeignKey("tenants.id"))
    user_id = Column(BigInteger, ForeignKey("users.id"))
    api_key_id = Column(BigInteger, ForeignKey("api_keys.id"))
    
    request_id = Column(String(100))
    endpoint = Column(String(255), index=True)
    method = Column(String(10))
    
    request_headers = Column(JSON, default=dict)
    request_body = Column(JSON)
    request_size = Column(Integer)
    
    response_code = Column(Integer)
    response_body = Column(JSON)
    response_size = Column(Integer)
    response_time_ms = Column(Integer)
    
    ip_address = Column(String(45))
    user_agent = Column(Text)
    
    created_at = Column(DateTime, server_default=func.now(), index=True)


class StatisticsDaily(Base):
    __tablename__ = "statistics_daily"
    
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    tenant_id = Column(BigInteger, ForeignKey("tenants.id"))
    stat_date = Column(DateTime, nullable=False)
    
    total_records = Column(Integer, default=0)
    fake_records = Column(Integer, default=0)
    normal_records = Column(Integer, default=0)
    pending_records = Column(Integer, default=0)
    
    high_risk_count = Column(Integer, default=0)
    medium_risk_count = Column(Integer, default=0)
    low_risk_count = Column(Integer, default=0)
    
    avg_suspicion_score = Column(Numeric(5, 2))
    avg_processing_time_ms = Column(Integer)
    
    geo_anomaly_count = Column(Integer, default=0)
    text_anomaly_count = Column(Integer, default=0)
    duplicate_count = Column(Integer, default=0)
    cluster_anomaly_count = Column(Integer, default=0)
    
    api_calls = Column(Integer, default=0)
    api_errors = Column(Integer, default=0)
    
    review_count = Column(Integer, default=0)
    review_approved = Column(Integer, default=0)
    review_rejected = Column(Integer, default=0)
    
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    
    __table_args__ = (
        Index("ix_stats_daily_tenant_date", "tenant_id", "stat_date", unique=True),
    )


class AlertRule(Base):
    __tablename__ = "alert_rules"
    
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    tenant_id = Column(BigInteger, ForeignKey("tenants.id"))
    
    name = Column(String(255), nullable=False)
    description = Column(Text)
    alert_type = Column(String(50), nullable=False)
    
    condition_config = Column(JSON, nullable=False)
    notification_config = Column(JSON, nullable=False)
    
    severity = Column(String(20), default="warning")
    
    enabled = Column(Boolean, default=True, index=True)
    cooldown_minutes = Column(Integer, default=60)
    last_triggered_at = Column(DateTime)
    trigger_count = Column(BigInteger, default=0)
    
    created_by = Column(BigInteger, ForeignKey("users.id"))
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class AlertHistory(Base):
    __tablename__ = "alert_history"
    
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    rule_id = Column(BigInteger, ForeignKey("alert_rules.id"))
    tenant_id = Column(BigInteger, ForeignKey("tenants.id"))
    
    alert_level = Column(String(20))
    title = Column(String(500))
    message = Column(Text)
    details = Column(JSON, default=dict)
    
    status = Column(String(20), default="pending", index=True)
    acknowledged_by = Column(BigInteger, ForeignKey("users.id"))
    acknowledged_at = Column(DateTime)
    resolved_by = Column(BigInteger, ForeignKey("users.id"))
    resolved_at = Column(DateTime)
    resolution_note = Column(Text)
    
    notification_sent = Column(Boolean, default=False)
    notification_channels = Column(JSON, default=list)
    
    created_at = Column(DateTime, server_default=func.now(), index=True)


class SystemConfig(Base):
    __tablename__ = "system_configs"
    
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    config_key = Column(String(100), unique=True, nullable=False)
    config_value = Column(JSON, nullable=False)
    description = Column(Text)
    
    is_public = Column(Boolean, default=False)
    
    updated_by = Column(BigInteger, ForeignKey("users.id"))
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
