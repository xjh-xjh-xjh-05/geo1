"""
系统管理路由
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
import time

try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False
    psutil = None

from api.core.database import get_db
from api.core.security import get_current_user
from api.core.responses import success_response
from api.core.cache import cache, DetectionCache, CacheManager
from api.core.logging import get_logger
from api.models.schemas import SystemConfigUpdate, SystemConfigItem
from api.models.db_models import SystemConfig

router = APIRouter(prefix="/system", tags=["System"])
logger = get_logger("system")


def _get_pool_stats() -> dict:
    from api.core.database import engine
    pool = engine.pool
    return {
        "pool_size": pool.size(),
        "checked_out": pool.checkedout(),
        "overflow": pool.overflow(),
        "checkedin": pool.checkedin()
    }


@router.get("/health")
async def health_check():
    from api.core.database import engine, SessionLocal
    from sqlalchemy import text
    from api.core.config import settings

    components = {}
    component_details = {}

    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
            conn.commit()
        components["database"] = "up"
        component_details["database"] = {
            "status": "up",
            "pool_size": settings.DATABASE_POOL_SIZE,
            "max_overflow": settings.DATABASE_MAX_OVERFLOW,
            "pool": _get_pool_stats()
        }
    except Exception as e:
        components["database"] = "down"
        component_details["database"] = {"status": "down", "error": str(e)[:100]}
        logger.warning("Health check: database down", error=str(e))

    try:
        db = SessionLocal()
        db.execute(text("SELECT 1"))
        db.close()
        components["database_connection"] = "up"
    except Exception as e:
        components["database_connection"] = "down"
        component_details["database_connection"] = {"status": "down", "error": str(e)[:100]}

    cache_status = cache.is_redis_available()
    components["cache"] = "up" if cache_status else "up (memory fallback)"
    component_details["cache"] = {
        "status": "redis" if cache_status else "memory",
        "stats": cache.get_stats()
    }

    try:
        import kafka
        from kafka import KafkaProducer
        producer = KafkaProducer(
            bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
            connection_timeout_ms=2000
        )
        producer.close()
        components["kafka"] = "up"
        component_details["kafka"] = {
            "status": "up",
            "bootstrap_servers": settings.KAFKA_BOOTSTRAP_SERVERS
        }
    except Exception as e:
        components["kafka"] = "down"
        component_details["kafka"] = {"status": "down", "error": str(e)[:100]}

    try:
        import socket
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(2)
        parts = settings.REDIS_URL.replace("redis://", "").split(":")
        host = parts[0]
        port = int(parts[1]) if len(parts) > 1 else 6379
        result = sock.connect_ex((host, port))
        sock.close()
        components["redis"] = "up" if result == 0 else "down"
        component_details["redis"] = {"status": "up" if result == 0 else "down", "host": host, "port": port}
    except Exception as e:
        components["redis"] = "unknown"
        component_details["redis"] = {"status": "unknown", "error": str(e)[:100]}

    all_up = all("up" in v for v in components.values())

    return {
        "status": "healthy" if all_up else "unhealthy",
        "components": components,
        "component_details": component_details,
        "timestamp": time.time(),
        "version": "1.0.0"
    }


@router.get("/metrics")
async def system_metrics(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if current_user.get("role") not in ["admin", "super_admin"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="权限不足"
        )

    if HAS_PSUTIL:
        cpu_usage = psutil.cpu_percent(interval=1)
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage('/')

        system_metrics = {
            "cpu_usage": cpu_usage,
            "memory_usage": memory.percent,
            "memory_used_gb": round(memory.used / (1024**3), 2),
            "memory_total_gb": round(memory.total / (1024**3), 2),
            "disk_usage": disk.percent,
            "disk_used_gb": round(disk.used / (1024**3), 2),
            "disk_total_gb": round(disk.total / (1024**3), 2)
        }
    else:
        system_metrics = {
            "cpu_usage": "N/A",
            "memory_usage": "N/A",
            "disk_usage": "N/A",
            "note": "psutil未安装"
        }

    cache_stats = cache.get_stats()
    pool_stats = _get_pool_stats()

    return success_response(data={
        **system_metrics,
        "connection_pool": pool_stats,
        "cache_stats": cache_stats
    })


@router.get("/configs")
async def get_all_configs(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """获取所有系统配置（前端使用的路径）"""
    if current_user.get("role") not in ["admin", "super_admin"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="权限不足"
        )
    
    configs = db.query(SystemConfig).all()
    
    return success_response(data={
        c.config_key: {
            "value": c.config_value,
            "description": c.description,
            "is_public": c.is_public,
            "updated_at": c.updated_at.isoformat() if c.updated_at else None
        }
        for c in configs
    })


@router.get("/config")
async def get_system_config(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if current_user.get("role") not in ["admin", "super_admin"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="权限不足"
        )
    
    configs = db.query(SystemConfig).all()
    
    return success_response(data=[
        {
            "key": c.config_key,
            "value": c.config_value,
            "description": c.description,
            "is_public": c.is_public,
            "updated_at": c.updated_at.isoformat() if c.updated_at else None
        }
        for c in configs
    ])


@router.put("/config")
async def update_system_config(
    config_data: SystemConfigUpdate,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if current_user.get("role") not in ["admin", "super_admin"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="权限不足"
        )
    
    updated_count = 0
    for item in config_data.configs:
        config = db.query(SystemConfig).filter(
            SystemConfig.config_key == item.key
        ).first()
        
        if config:
            config.config_value = item.value
            config.updated_by = current_user["id"]
            updated_count += 1
        else:
            new_config = SystemConfig(
                config_key=item.key,
                config_value=item.value,
                description=item.description,
                updated_by=current_user["id"]
            )
            db.add(new_config)
            updated_count += 1
    
    db.commit()
    
    return success_response(message=f"已更新 {updated_count} 项配置")


@router.get("/info")
async def system_info(
    current_user: dict = Depends(get_current_user)
):
    from api.core.config import settings
    
    return success_response(data={
        "app_name": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "debug": settings.DEBUG,
        "python_version": "3.11+",
        "features": {
            "geo_detection": True,
            "text_detection": True,
            "simhash": True,
            "semantic_cluster": True,
            "multi_tenant": True,
            "api_key_auth": True,
            "rate_limit": True
        }
    })


@router.post("/cache/clear")
async def clear_cache(
    current_user: dict = Depends(get_current_user)
):
    if current_user.get("role") not in ["admin", "super_admin"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="权限不足"
        )
    
    try:
        if cache.is_redis_available():
            cache._redis_client.flushdb()
        else:
            cache._memory_cache.clear()
        return success_response(message="缓存已清空")
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"清空缓存失败: {str(e)}"
        )


@router.get("/cache/stats")
async def get_cache_stats(
    current_user: dict = Depends(get_current_user)
):
    if current_user.get("role") not in ["admin", "super_admin"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="权限不足"
        )
    
    return success_response(data=cache.get_stats())


@router.get("/logs")
async def get_system_logs(
    lines: int = 100,
    level: str = None,
    current_user: dict = Depends(get_current_user)
):
    if current_user.get("role") not in ["admin", "super_admin"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="权限不足"
        )
    
    import os
    log_file = "logs/api.log"
    
    if not os.path.exists(log_file):
        return success_response(data=[])
    
    with open(log_file, 'r', encoding='utf-8') as f:
        all_lines = f.readlines()
        recent_lines = all_lines[-lines:] if len(all_lines) > lines else all_lines
    
    if level:
        recent_lines = [l for l in recent_lines if level.upper() in l]
    
    return success_response(data=[
        line.strip() for line in recent_lines
    ])
