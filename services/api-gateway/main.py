"""
API Gateway - 服务网关
"""
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import httpx
import time
import logging
from pydantic_settings import BaseSettings

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    """配置类"""
    APP_NAME: str = "API Gateway"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False
    
    # 服务地址
    DETECTION_SERVICE_URL: str = "http://detection-service:8000"
    USER_SERVICE_URL: str = "http://user-service:8000"
    RULE_SERVICE_URL: str = "http://rule-service:8000"
    DATA_SERVICE_URL: str = "http://data-service:8000"
    
    # 认证配置
    SECRET_KEY: str = "your-secret-key-change-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 120
    
    # CORS
    CORS_ORIGINS: list = ["*"]
    
    class Config:
        env_file = ".env"
        case_sensitive = True
        extra = "ignore"


# 初始化配置
settings = Settings()

# 初始化HTTP客户端
http_client = httpx.AsyncClient(timeout=30.0)

# 创建FastAPI应用
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="GEO虚假内容检测平台 - API Gateway"
)

# 配置CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 集成Prometheus指标
try:
    from api.core.middleware import MetricsMiddleware, register_metrics_endpoint
    app.add_middleware(MetricsMiddleware)
    register_metrics_endpoint(app)
    logger.info("Prometheus metrics enabled")
except ImportError:
    logger.warning("Prometheus metrics not available")


async def proxy_request(service_url: str, request: Request) -> JSONResponse:
    """代理请求到微服务"""
    try:
        # 构建请求URL
        url = f"{service_url}{request.url.path}"
        
        # 构建请求头
        headers = dict(request.headers)
        headers.pop("host", None)
        
        # 构建请求体
        if request.method in ["POST", "PUT", "PATCH"]:
            body = await request.json()
        else:
            body = None
        
        # 发送请求
        start_time = time.time()
        response = await http_client.request(
            method=request.method,
            url=url,
            headers=headers,
            json=body,
            params=request.query_params
        )
        response_time = time.time() - start_time
        
        logger.info(f"Proxy request to {url} took {response_time:.4f}s, status: {response.status_code}")
        
        # 返回响应
        return JSONResponse(
            status_code=response.status_code,
            content=response.json()
        )
    except httpx.ConnectError:
        logger.error(f"Service {service_url} is unavailable")
        raise HTTPException(
            status_code=503,
            detail=f"服务 {service_url} 不可用"
        )
    except Exception as e:
        logger.error(f"Proxy request failed: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"代理请求失败: {str(e)}"
        )


# 健康检查
@app.get("/health")
async def health_check():
    """健康检查"""
    services = [
        {"name": "detection-service", "url": settings.DETECTION_SERVICE_URL},
        {"name": "user-service", "url": settings.USER_SERVICE_URL},
        {"name": "rule-service", "url": settings.RULE_SERVICE_URL},
        {"name": "data-service", "url": settings.DATA_SERVICE_URL}
    ]
    
    status = "healthy"
    components = {}
    
    for service in services:
        try:
            response = await http_client.get(f"{service['url']}/health")
            if response.status_code == 200:
                components[service['name']] = "up"
            else:
                components[service['name']] = "down"
                status = "unhealthy"
        except Exception:
            components[service['name']] = "down"
            status = "unhealthy"
    
    return {
        "status": status,
        "components": components,
        "timestamp": time.time()
    }


# 检测服务路由
@app.api_route("/api/v1/detect/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
async def proxy_detection(request: Request, path: str):
    """代理到检测服务"""
    return await proxy_request(
        f"{settings.DETECTION_SERVICE_URL}/api/v1/detect",
        request
    )


# 用户服务路由
@app.api_route("/api/v1/auth/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
async def proxy_auth(request: Request, path: str):
    """代理到认证服务"""
    return await proxy_request(
        f"{settings.USER_SERVICE_URL}/api/v1/auth",
        request
    )


@app.api_route("/api/v1/users/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
async def proxy_users(request: Request, path: str):
    """代理到用户服务"""
    return await proxy_request(
        f"{settings.USER_SERVICE_URL}/api/v1/users",
        request
    )


# 规则服务路由
@app.api_route("/api/v1/rules/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
async def proxy_rules(request: Request, path: str):
    """代理到规则服务"""
    return await proxy_request(
        f"{settings.RULE_SERVICE_URL}/api/v1/rules",
        request
    )


@app.api_route("/api/v1/keywords/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
async def proxy_keywords(request: Request, path: str):
    """代理到关键词服务"""
    return await proxy_request(
        f"{settings.RULE_SERVICE_URL}/api/v1/keywords",
        request
    )


# 数据服务路由
@app.api_route("/api/v1/records/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
async def proxy_records(request: Request, path: str):
    """代理到记录服务"""
    return await proxy_request(
        f"{settings.DATA_SERVICE_URL}/api/v1/records",
        request
    )


@app.api_route("/api/v1/stats/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
async def proxy_stats(request: Request, path: str):
    """代理到统计服务"""
    return await proxy_request(
        f"{settings.DATA_SERVICE_URL}/api/v1/stats",
        request
    )


@app.api_route("/api/v1/alerts/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
async def proxy_alerts(request: Request, path: str):
    """代理到告警服务"""
    return await proxy_request(
        f"{settings.DATA_SERVICE_URL}/api/v1/alerts",
        request
    )


@app.api_route("/api/v1/system/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
async def proxy_system(request: Request, path: str):
    """代理到系统服务"""
    return await proxy_request(
        f"{settings.DATA_SERVICE_URL}/api/v1/system",
        request
    )


# 根路径
@app.get("/")
async def root():
    """根路径"""
    return {
        "message": "API Gateway",
        "version": settings.APP_VERSION,
        "services": {
            "detection": settings.DETECTION_SERVICE_URL,
            "user": settings.USER_SERVICE_URL,
            "rule": settings.RULE_SERVICE_URL,
            "data": settings.DATA_SERVICE_URL
        }
    }


# 启动事件
@app.on_event("startup")
async def startup_event():
    """启动事件"""
    logger.info(f"Starting API Gateway v{settings.APP_VERSION}")
    logger.info(f"Detection service: {settings.DETECTION_SERVICE_URL}")
    logger.info(f"User service: {settings.USER_SERVICE_URL}")
    logger.info(f"Rule service: {settings.RULE_SERVICE_URL}")
    logger.info(f"Data service: {settings.DATA_SERVICE_URL}")


# 关闭事件
@app.on_event("shutdown")
async def shutdown_event():
    """关闭事件"""
    await http_client.aclose()
    logger.info("API Gateway shutdown")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.DEBUG
    )