"""
API核心配置
"""
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import field_validator, ValidationInfo
from typing import List, Optional
from functools import lru_cache


class Settings(BaseSettings):
    APP_NAME: str = "GEO虚假内容检测平台"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False
    
    # 敏感配置 - 必须从环境变量读取，无默认值
    DATABASE_URL: str
    REDIS_URL: str
    KAFKA_BOOTSTRAP_SERVERS: str
    SECRET_KEY: str
    
    # 基础配置
    DATABASE_POOL_SIZE: int = 20
    DATABASE_MAX_OVERFLOW: int = 10
    
    KAFKA_DETECTION_TOPIC: str = "geo-detection-requests"
    KAFKA_RESULT_TOPIC: str = "geo-detection-results"
    
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 120
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    
    API_KEY_HEADER: str = "X-API-Key"
    
    CORS_ORIGINS: List[str] = ["*"]
    
    LOG_LEVEL: str = "INFO"
    LOG_FILE: str = "logs/api.log"
    
    QUOTA_DEFAULT_DAILY: int = 10000
    QUOTA_DEFAULT_MONTHLY: int = 300000
    
    DETECTION_WEIGHTS: dict = {
        "geo": 0.3,
        "text": 0.3,
        "simhash": 0.2,
        "semantic": 0.2
    }
    
    RISK_THRESHOLDS: dict = {
        "high": 80,
        "medium": 60,
        "low": 30
    }
    
    RATE_LIMIT_ENABLED: bool = True
    RATE_LIMIT_DEFAULT: int = 100
    RATE_LIMIT_PERIOD: int = 60
    
    model_config = SettingsConfigDict(env_file=".env", case_sensitive=True)
    
    @field_validator("SECRET_KEY")
    def validate_secret_key(cls, v: str, info: ValidationInfo) -> str:
        if len(v) < 32:
            raise ValueError("SECRET_KEY must be at least 32 characters long for production security")
        return v


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
