"""
FastAPI主应用入口
"""
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
from datetime import datetime
import time

from api.core.config import settings
from api.core.database import engine, Base
from api.core.middleware import MetricsMiddleware, register_metrics_endpoint
from api.core.logging import configure_logging, get_logger
from api.routers import auth, detect, records, review, rules, keywords, stats, alerts, users, system, alert_rules, logs
from api.routers import preprocessing, ai_models, data_management, backend_management
from api.services.kafka_service import realtime_service

logger = configure_logging(settings.LOG_LEVEL, settings.LOG_FILE)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting up GEO Fake Detection API...")
    try:
        Base.metadata.create_all(bind=engine)
        logger.info("Database tables created/verified")
        
        # 启动Kafka实时检测服务
        realtime_service.start()
        logger.info("Kafka realtime detection service started")
    except Exception as e:
        logger.warning(f"Initialization skipped: {e}")
    yield
    logger.info("Shutting down GEO Fake Detection API...")
    try:
        # 停止Kafka实时检测服务
        realtime_service.stop()
        logger.info("Kafka realtime detection service stopped")
    except Exception as e:
        logger.warning(f"Failed to stop Kafka service: {e}")


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="""
    ## 商用地理信息虚假内容检查与反投喂平台 API
    
    ### 功能模块
    - **认证授权**: 用户登录、Token管理、API密钥管理
    - **检测服务**: 单条/批量检测、检测历史
    - **记录管理**: 记录查询、标注、导出
    - **审核管理**: 审核流程、审核历史
    - **规则管理**: 规则配置、测试
    - **关键词管理**: 关键词库管理、导入导出
    - **统计报表**: 数据统计、趋势分析
    - **告警管理**: 告警规则、告警历史
    - **用户管理**: 用户CRUD、权限管理
    - **系统管理**: 系统配置、健康检查、监控
    
    ### 认证方式
    - JWT Token: `Authorization: Bearer <token>`
    - API Key: `X-API-Key: <api_key>`
    
    ### 限流说明
    - 默认限制: 100次/分钟
    - 响应头包含限流信息:
      - X-RateLimit-Limit: 限制次数
      - X-RateLimit-Remaining: 剩余次数
    """,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc"
)

app.add_middleware(MetricsMiddleware)

# 注册指标端点
register_metrics_endpoint(app)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


from api.core.errors import AppException, ErrorCode
from api.core.responses import app_exception_response, ErrorResponseModel


@app.exception_handler(AppException)
async def app_exception_handler(request: Request, exc: AppException):
    logger.error(f"App exception: {exc.error_code} - {exc.message}", exc_info=True)
    response = app_exception_response(exc)
    return JSONResponse(
        status_code=exc.http_status,
        content=response.dict()
    )


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Global exception: {exc}", exc_info=True)
    response = ErrorResponseModel(
        error_code=ErrorCode.SYSTEM_ERROR.value,
        message="服务器内部错误",
        details={"detail": str(exc) if settings.DEBUG else "Internal Server Error"},
        retryable=False,
        request_id=str(time.time_ns())[-8:],
        timestamp=datetime.utcnow().isoformat() + "Z"
    )
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=response.dict()
    )


app.include_router(auth.router, prefix="/api/v1")
app.include_router(detect.router, prefix="/api/v1")
app.include_router(records.router, prefix="/api/v1")
app.include_router(review.router, prefix="/api/v1")
app.include_router(rules.router, prefix="/api/v1")
app.include_router(keywords.router, prefix="/api/v1")
app.include_router(stats.router, prefix="/api/v1")
app.include_router(alerts.router, prefix="/api/v1")
app.include_router(alert_rules.router, prefix="/api/v1")
app.include_router(users.router, prefix="/api/v1")
app.include_router(system.router, prefix="/api/v1")
app.include_router(logs.router, prefix="/api/v1")
app.include_router(preprocessing.router, prefix="/api/v1")
app.include_router(ai_models.router, prefix="/api/v1")
app.include_router(data_management.router, prefix="/api/v1")
app.include_router(backend_management.router, prefix="/api/v1")


@app.get("/", tags=["Root"])
async def root():
    return {
        "name": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "docs": "/docs",
        "redoc": "/redoc",
        "endpoints": {
            "auth": "/api/v1/auth",
            "detect": "/api/v1/detect",
            "records": "/api/v1/records",
            "review": "/api/v1/review",
            "rules": "/api/v1/rules",
            "keywords": "/api/v1/keywords",
            "stats": "/api/v1/stats",
            "alerts": "/api/v1/alerts",
            "users": "/api/v1/users",
            "system": "/api/v1/system",
            "preprocessing": "/api/v1/preprocessing",
            "ai": "/api/v1/ai",
            "data": "/api/v1/data",
            "admin": "/api/v1/admin"
        }
    }


@app.get("/health", tags=["System"])
async def health_check():
    from sqlalchemy import text
    from api.core.database import engine

    db_ok = False
    pool_info = {}
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
            conn.commit()
        db_ok = True
        pool = engine.pool
        pool_info = {
            "pool_size": pool.size(),
            "checked_out": pool.checkedout(),
            "overflow": pool.overflow(),
            "checkedin": pool.checkedin()
        }
    except Exception as e:
        logger.warning("Health check: database unreachable", error=str(e))

    status_code = 200 if db_ok else 503
    from fastapi.responses import JSONResponse
    return JSONResponse(
        status_code=status_code,
        content={
            "status": "healthy" if db_ok else "unhealthy",
            "checks": {"database": "up" if db_ok else "down"},
            "pool": pool_info,
            "version": settings.APP_VERSION,
            "timestamp": time.time()
        }
    )


@app.get("/health/ready", tags=["System"])
async def readiness_check():
    from sqlalchemy import text
    from api.core.database import engine
    from api.core.cache import cache

    checks = {}

    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
            conn.commit()
        checks["database"] = "up"
    except Exception:
        checks["database"] = "down"

    checks["cache"] = "up" if cache.is_redis_available() else "up (memory fallback)"

    all_up = checks["database"] == "up"
    status_code = 200 if all_up else 503
    from fastapi.responses import JSONResponse
    return JSONResponse(
        status_code=status_code,
        content={
            "status": "ready" if all_up else "not_ready",
            "checks": checks,
            "timestamp": time.time()
        }
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.DEBUG
    )
