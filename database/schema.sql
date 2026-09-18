-- ============================================
-- 商用地理信息虚假内容检查与反投喂平台
-- 数据库Schema设计
-- 数据库: PostgreSQL 15+
-- ============================================

-- 启用必要扩展
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "postgis";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";

-- ============================================
-- 1. 租户管理
-- ============================================

CREATE TABLE tenants (
    id BIGSERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    code VARCHAR(50) UNIQUE NOT NULL,
    
    plan VARCHAR(50) DEFAULT 'basic',
    quota_daily INT DEFAULT 10000,
    quota_monthly INT DEFAULT 300000,
    quota_used_daily INT DEFAULT 0,
    quota_used_monthly INT DEFAULT 0,
    
    features JSONB DEFAULT '{}',
    settings JSONB DEFAULT '{}',
    
    contact_name VARCHAR(100),
    contact_email VARCHAR(255),
    contact_phone VARCHAR(50),
    
    status VARCHAR(20) DEFAULT 'active',
    expire_at TIMESTAMP,
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_tenants_code ON tenants(code);
CREATE INDEX idx_tenants_status ON tenants(status);

-- ============================================
-- 2. 用户管理
-- ============================================

CREATE TABLE users (
    id BIGSERIAL PRIMARY KEY,
    tenant_id BIGINT REFERENCES tenants(id),
    
    username VARCHAR(100) NOT NULL,
    email VARCHAR(255) NOT NULL,
    phone VARCHAR(50),
    password_hash VARCHAR(255) NOT NULL,
    
    role VARCHAR(50) DEFAULT 'user',
    permissions JSONB DEFAULT '[]',
    
    avatar_url VARCHAR(500),
    display_name VARCHAR(100),
    
    status VARCHAR(20) DEFAULT 'active',
    last_login_at TIMESTAMP,
    last_login_ip VARCHAR(45),
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    UNIQUE(tenant_id, username),
    UNIQUE(tenant_id, email)
);

CREATE INDEX idx_users_tenant ON users(tenant_id);
CREATE INDEX idx_users_email ON users(email);
CREATE INDEX idx_users_status ON users(status);

-- API密钥表
CREATE TABLE api_keys (
    id BIGSERIAL PRIMARY KEY,
    tenant_id BIGINT REFERENCES tenants(id),
    user_id BIGINT REFERENCES users(id),
    
    key_hash VARCHAR(255) NOT NULL,
    key_prefix VARCHAR(20) NOT NULL,
    name VARCHAR(100),
    
    permissions JSONB DEFAULT '[]',
    ip_whitelist JSONB DEFAULT '[]',
    rate_limit INT DEFAULT 1000,
    
    last_used_at TIMESTAMP,
    usage_count BIGINT DEFAULT 0,
    
    status VARCHAR(20) DEFAULT 'active',
    expire_at TIMESTAMP,
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_api_keys_tenant ON api_keys(tenant_id);
CREATE INDEX idx_api_keys_prefix ON api_keys(key_prefix);

-- ============================================
-- 3. 检测记录表
-- ============================================

CREATE TABLE detection_records (
    id BIGSERIAL PRIMARY KEY,
    record_id VARCHAR(100) UNIQUE NOT NULL,
    tenant_id BIGINT NOT NULL REFERENCES tenants(id),
    
    device_id VARCHAR(100),
    user_id VARCHAR(100),
    session_id VARCHAR(100),
    timestamp BIGINT,
    
    latitude DECIMAL(10, 7),
    longitude DECIMAL(10, 7),
    accuracy DECIMAL(10, 2),
    geo_source VARCHAR(20),
    geo_point GEOMETRY(Point, 4326),
    
    content_text TEXT,
    content_type VARCHAR(50),
    content_hash VARCHAR(64),
    
    ip_address VARCHAR(45),
    app_version VARCHAR(50),
    user_agent TEXT,
    platform VARCHAR(50),
    
    suspicion_score DECIMAL(5, 2),
    risk_level VARCHAR(20),
    is_fake BOOLEAN DEFAULT FALSE,
    confidence DECIMAL(5, 2) DEFAULT 0.0,
    
    geo_score DECIMAL(5, 2) DEFAULT 0,
    text_score DECIMAL(5, 2) DEFAULT 0,
    simhash_score DECIMAL(5, 2) DEFAULT 0,
    semantic_score DECIMAL(5, 2) DEFAULT 0,
    
    reasons JSONB DEFAULT '[]',
    details JSONB DEFAULT '{}',
    similar_record_ids JSONB DEFAULT '[]',
    
    review_status VARCHAR(50) DEFAULT 'pending',
    reviewer_id BIGINT REFERENCES users(id),
    review_comment TEXT,
    reviewed_at TIMESTAMP,
    
    ground_truth BOOLEAN,
    feedback_type VARCHAR(50),
    feedback_comment TEXT,
    
    processing_time_ms INT,
    model_version VARCHAR(50),
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_records_tenant ON detection_records(tenant_id);
CREATE INDEX idx_records_record_id ON detection_records(record_id);
CREATE INDEX idx_records_device ON detection_records(device_id);
CREATE INDEX idx_records_user ON detection_records(user_id);
CREATE INDEX idx_records_timestamp ON detection_records(timestamp);
CREATE INDEX idx_records_risk ON detection_records(risk_level);
CREATE INDEX idx_records_review ON detection_records(review_status);
CREATE INDEX idx_records_created ON detection_records(created_at);
CREATE INDEX idx_records_geo_point ON detection_records USING GIST (geo_point);
CREATE INDEX idx_records_content_text ON detection_records USING GIN (to_tsvector('simple', content_text));
CREATE INDEX idx_records_content_hash ON detection_records(content_hash);

-- ============================================
-- 4. 规则配置表
-- ============================================

CREATE TABLE rule_configs (
    id BIGSERIAL PRIMARY KEY,
    tenant_id BIGINT REFERENCES tenants(id),
    
    rule_type VARCHAR(50) NOT NULL,
    rule_name VARCHAR(100) NOT NULL,
    rule_code VARCHAR(100),
    
    rule_config JSONB NOT NULL,
    description TEXT,
    
    enabled BOOLEAN DEFAULT TRUE,
    priority INT DEFAULT 100,
    
    hit_count BIGINT DEFAULT 0,
    last_hit_at TIMESTAMP,
    
    created_by BIGINT REFERENCES users(id),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    UNIQUE(tenant_id, rule_code)
);

CREATE INDEX idx_rules_tenant ON rule_configs(tenant_id);
CREATE INDEX idx_rules_type ON rule_configs(rule_type);
CREATE INDEX idx_rules_enabled ON rule_configs(enabled);

-- ============================================
-- 5. 关键词库表
-- ============================================

CREATE TABLE keyword_libraries (
    id BIGSERIAL PRIMARY KEY,
    tenant_id BIGINT REFERENCES tenants(id),
    
    category VARCHAR(100) NOT NULL,
    keyword VARCHAR(255) NOT NULL,
    
    weight DECIMAL(3, 2) DEFAULT 1.0,
    risk_level VARCHAR(20) DEFAULT 'medium',
    
    source VARCHAR(100) DEFAULT 'manual',
    description TEXT,
    
    hit_count BIGINT DEFAULT 0,
    last_hit_at TIMESTAMP,
    
    enabled BOOLEAN DEFAULT TRUE,
    created_by BIGINT REFERENCES users(id),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    UNIQUE(tenant_id, category, keyword)
);

CREATE INDEX idx_keywords_tenant ON keyword_libraries(tenant_id);
CREATE INDEX idx_keywords_category ON keyword_libraries(category);
CREATE INDEX idx_keywords_enabled ON keyword_libraries(enabled);

-- ============================================
-- 6. 审核记录表
-- ============================================

CREATE TABLE review_logs (
    id BIGSERIAL PRIMARY KEY,
    record_id BIGINT REFERENCES detection_records(id),
    tenant_id BIGINT REFERENCES tenants(id),
    reviewer_id BIGINT REFERENCES users(id),
    
    action VARCHAR(50) NOT NULL,
    old_status VARCHAR(50),
    new_status VARCHAR(50),
    
    old_ground_truth BOOLEAN,
    new_ground_truth BOOLEAN,
    
    comment TEXT,
    metadata JSONB DEFAULT '{}',
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_review_logs_record ON review_logs(record_id);
CREATE INDEX idx_review_logs_tenant ON review_logs(tenant_id);
CREATE INDEX idx_review_logs_reviewer ON review_logs(reviewer_id);

-- ============================================
-- 7. API调用日志表
-- ============================================

CREATE TABLE api_logs (
    id BIGSERIAL PRIMARY KEY,
    tenant_id BIGINT REFERENCES tenants(id),
    user_id BIGINT REFERENCES users(id),
    api_key_id BIGINT REFERENCES api_keys(id),
    
    request_id VARCHAR(100),
    endpoint VARCHAR(255),
    method VARCHAR(10),
    
    request_headers JSONB DEFAULT '{}',
    request_body JSONB,
    request_size INT,
    
    response_code INT,
    response_body JSONB,
    response_size INT,
    response_time_ms INT,
    
    ip_address VARCHAR(45),
    user_agent TEXT,
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_api_logs_tenant ON api_logs(tenant_id);
CREATE INDEX idx_api_logs_created ON api_logs(created_at);
CREATE INDEX idx_api_logs_endpoint ON api_logs(endpoint);

-- 分区表（按月分区）
CREATE TABLE api_logs_archive (LIKE api_logs INCLUDING ALL);

-- ============================================
-- 8. 统计汇总表
-- ============================================

CREATE TABLE statistics_daily (
    id BIGSERIAL PRIMARY KEY,
    tenant_id BIGINT REFERENCES tenants(id),
    stat_date DATE NOT NULL,
    
    total_records INT DEFAULT 0,
    fake_records INT DEFAULT 0,
    normal_records INT DEFAULT 0,
    pending_records INT DEFAULT 0,
    
    high_risk_count INT DEFAULT 0,
    medium_risk_count INT DEFAULT 0,
    low_risk_count INT DEFAULT 0,
    
    avg_suspicion_score DECIMAL(5, 2),
    avg_processing_time_ms INT,
    
    geo_anomaly_count INT DEFAULT 0,
    text_anomaly_count INT DEFAULT 0,
    duplicate_count INT DEFAULT 0,
    cluster_anomaly_count INT DEFAULT 0,
    
    api_calls INT DEFAULT 0,
    api_errors INT DEFAULT 0,
    
    review_count INT DEFAULT 0,
    review_approved INT DEFAULT 0,
    review_rejected INT DEFAULT 0,
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    UNIQUE(tenant_id, stat_date)
);

CREATE INDEX idx_stats_daily_tenant ON statistics_daily(tenant_id);
CREATE INDEX idx_stats_daily_date ON statistics_daily(stat_date);

CREATE TABLE statistics_hourly (
    id BIGSERIAL PRIMARY KEY,
    tenant_id BIGINT REFERENCES tenants(id),
    stat_time TIMESTAMP NOT NULL,
    
    total_records INT DEFAULT 0,
    fake_records INT DEFAULT 0,
    high_risk_count INT DEFAULT 0,
    medium_risk_count INT DEFAULT 0,
    
    api_calls INT DEFAULT 0,
    avg_response_time_ms INT,
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    UNIQUE(tenant_id, stat_time)
);

-- ============================================
-- 9. 告警规则表
-- ============================================

CREATE TABLE alert_rules (
    id BIGSERIAL PRIMARY KEY,
    tenant_id BIGINT REFERENCES tenants(id),
    
    name VARCHAR(255) NOT NULL,
    description TEXT,
    alert_type VARCHAR(50) NOT NULL,
    
    condition_config JSONB NOT NULL,
    notification_config JSONB NOT NULL,
    
    severity VARCHAR(20) DEFAULT 'warning',
    
    enabled BOOLEAN DEFAULT TRUE,
    cooldown_minutes INT DEFAULT 60,
    last_triggered_at TIMESTAMP,
    trigger_count BIGINT DEFAULT 0,
    
    created_by BIGINT REFERENCES users(id),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_alert_rules_tenant ON alert_rules(tenant_id);
CREATE INDEX idx_alert_rules_type ON alert_rules(alert_type);
CREATE INDEX idx_alert_rules_enabled ON alert_rules(enabled);

CREATE TABLE alert_history (
    id BIGSERIAL PRIMARY KEY,
    rule_id BIGINT REFERENCES alert_rules(id),
    tenant_id BIGINT REFERENCES tenants(id),
    
    alert_level VARCHAR(20),
    title VARCHAR(500),
    message TEXT,
    details JSONB DEFAULT '{}',
    
    status VARCHAR(20) DEFAULT 'pending',
    acknowledged_by BIGINT REFERENCES users(id),
    acknowledged_at TIMESTAMP,
    resolved_by BIGINT REFERENCES users(id),
    resolved_at TIMESTAMP,
    resolution_note TEXT,
    
    notification_sent BOOLEAN DEFAULT FALSE,
    notification_channels JSONB DEFAULT '[]',
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_alert_history_tenant ON alert_history(tenant_id);
CREATE INDEX idx_alert_history_status ON alert_history(status);
CREATE INDEX idx_alert_history_created ON alert_history(created_at);

-- ============================================
-- 10. 模型版本表
-- ============================================

CREATE TABLE model_versions (
    id BIGSERIAL PRIMARY KEY,
    tenant_id BIGINT REFERENCES tenants(id),
    
    model_type VARCHAR(50) NOT NULL,
    version VARCHAR(50) NOT NULL,
    description TEXT,
    
    model_path VARCHAR(500),
    config JSONB DEFAULT '{}',
    metrics JSONB DEFAULT '{}',
    
    status VARCHAR(20) DEFAULT 'staging',
    is_active BOOLEAN DEFAULT FALSE,
    
    training_data_count INT,
    training_time_seconds INT,
    
    created_by BIGINT REFERENCES users(id),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    deployed_at TIMESTAMP,
    
    UNIQUE(tenant_id, model_type, version)
);

CREATE INDEX idx_model_versions_tenant ON model_versions(tenant_id);
CREATE INDEX idx_model_versions_active ON model_versions(is_active);

-- ============================================
-- 11. 系统配置表
-- ============================================

CREATE TABLE system_configs (
    id BIGSERIAL PRIMARY KEY,
    config_key VARCHAR(100) UNIQUE NOT NULL,
    config_value JSONB NOT NULL,
    description TEXT,
    
    is_public BOOLEAN DEFAULT FALSE,
    
    updated_by BIGINT REFERENCES users(id),
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ============================================
-- 12. 操作日志表
-- ============================================

CREATE TABLE operation_logs (
    id BIGSERIAL PRIMARY KEY,
    tenant_id BIGINT REFERENCES tenants(id),
    user_id BIGINT REFERENCES users(id),
    
    action VARCHAR(100) NOT NULL,
    resource_type VARCHAR(50),
    resource_id VARCHAR(100),
    
    old_value JSONB,
    new_value JSONB,
    
    ip_address VARCHAR(45),
    user_agent TEXT,
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_operation_logs_tenant ON operation_logs(tenant_id);
CREATE INDEX idx_operation_logs_user ON operation_logs(user_id);
CREATE INDEX idx_operation_logs_action ON operation_logs(action);
CREATE INDEX idx_operation_logs_created ON operation_logs(created_at);

-- ============================================
-- 触发器：自动更新 updated_at
-- ============================================

CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER update_tenants_updated_at BEFORE UPDATE ON tenants
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_users_updated_at BEFORE UPDATE ON users
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_records_updated_at BEFORE UPDATE ON detection_records
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_rules_updated_at BEFORE UPDATE ON rule_configs
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_alert_rules_updated_at BEFORE UPDATE ON alert_rules
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- ============================================
-- 触发器：自动设置地理点
-- ============================================

CREATE OR REPLACE FUNCTION set_geo_point()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.latitude IS NOT NULL AND NEW.longitude IS NOT NULL THEN
        NEW.geo_point = ST_SetSRID(ST_MakePoint(NEW.longitude, NEW.latitude), 4326);
    END IF;
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER set_detection_record_geo_point BEFORE INSERT OR UPDATE ON detection_records
    FOR EACH ROW EXECUTE FUNCTION set_geo_point();

-- ============================================
-- 视图：检测记录统计视图
-- ============================================

CREATE VIEW v_detection_stats AS
SELECT 
    tenant_id,
    DATE(created_at) as stat_date,
    COUNT(*) as total_count,
    SUM(CASE WHEN is_fake = TRUE THEN 1 ELSE 0 END) as fake_count,
    SUM(CASE WHEN is_fake = FALSE THEN 1 ELSE 0 END) as normal_count,
    SUM(CASE WHEN risk_level = 'high' THEN 1 ELSE 0 END) as high_risk_count,
    SUM(CASE WHEN risk_level = 'medium' THEN 1 ELSE 0 END) as medium_risk_count,
    SUM(CASE WHEN risk_level = 'low' THEN 1 ELSE 0 END) as low_risk_count,
    AVG(suspicion_score) as avg_score,
    AVG(processing_time_ms) as avg_processing_time
FROM detection_records
GROUP BY tenant_id, DATE(created_at);

-- ============================================
-- 初始数据
-- ============================================

INSERT INTO system_configs (config_key, config_value, description, is_public) VALUES
('geo.latitude_min', '18.0', '中国南端纬度', TRUE),
('geo.latitude_max', '54.0', '中国北端纬度', TRUE),
('geo.longitude_min', '73.0', '中国西端经度', TRUE),
('geo.longitude_max', '135.0', '中国东端经度', TRUE),
('geo.teleport_distance', '100.0', '瞬移距离阈值(km)', TRUE),
('geo.max_reports_per_minute', '10', '每分钟最大上报次数', TRUE),
('text.min_length', '5', '最小文本长度', TRUE),
('text.max_length', '500', '最大文本长度', TRUE),
('text.max_keyword_repeat', '3', '关键词最大重复次数', TRUE),
('text.simhash_threshold', '3', 'SimHash汉明距离阈值', TRUE),
('scorer.geo_weight', '0.3', 'GEO检测权重', TRUE),
('scorer.text_weight', '0.3', '文本检测权重', TRUE),
('scorer.simhash_weight', '0.2', 'SimHash权重', TRUE),
('scorer.semantic_weight', '0.2', '语义聚类权重', TRUE),
('scorer.high_risk_threshold', '80', '高风险阈值', TRUE),
('scorer.medium_risk_threshold', '60', '中风险阈值', TRUE);
