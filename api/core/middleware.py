"""
FastAPI中间件和工具
"""
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
import time
from api.core.metrics import (
    REQUEST_COUNT, REQUEST_DURATION,
    update_cache_stats, update_system_stats, update_pool_stats
)


class MetricsMiddleware(BaseHTTPMiddleware):
    """指标中间件"""
    _request_count = 0
    _POOL_UPDATE_INTERVAL = 50

    async def dispatch(self, request: Request, call_next):
        start_time = time.time()

        response = await call_next(request)

        duration = time.time() - start_time

        REQUEST_COUNT.labels(
            method=request.method,
            endpoint=request.url.path,
            status=response.status_code
        ).inc()

        REQUEST_DURATION.labels(
            method=request.method,
            endpoint=request.url.path
        ).observe(duration)

        MetricsMiddleware._request_count += 1
        if MetricsMiddleware._request_count % MetricsMiddleware._POOL_UPDATE_INTERVAL == 0:
            update_pool_stats()

        return response


def register_metrics_endpoint(app):
    """注册指标端点"""
    from fastapi import APIRouter
    from api.core.metrics import get_metrics
    
    router = APIRouter()
    
    @router.get("/metrics")
    async def metrics():
        """Prometheus指标端点"""
        return Response(
            content=get_metrics(),
            media_type="text/plain"
        )
    
    app.include_router(router)