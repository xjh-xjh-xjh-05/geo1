"""
监控指标模块 - Prometheus集成
"""
from prometheus_client import (
    Counter, Gauge, Histogram, Summary,
    CollectorRegistry, push_to_gateway
)
import time

registry = CollectorRegistry()

REQUEST_COUNT = Counter(
    'api_requests_total',
    'Total number of API requests',
    ['method', 'endpoint', 'status'],
    registry=registry
)

REQUEST_DURATION = Histogram(
    'api_request_duration_seconds',
    'Request processing time in seconds',
    ['method', 'endpoint'],
    registry=registry
)

DETECTION_COUNT = Counter(
    'detection_total',
    'Total number of detections',
    ['is_fake', 'risk_level'],
    registry=registry
)

DETECTION_DURATION = Summary(
    'detection_duration_seconds',
    'Detection processing time in seconds',
    registry=registry
)

CACHE_HIT_RATE = Gauge(
    'cache_hit_rate',
    'Cache hit rate',
    ['cache_type'],
    registry=registry
)

DB_CONNECTIONS = Gauge(
    'db_connections',
    'Number of database connections',
    registry=registry
)

DB_POOL_SIZE = Gauge(
    'db_pool_size',
    'SQLAlchemy connection pool size',
    registry=registry
)

DB_POOL_CHECKED_OUT = Gauge(
    'db_pool_checked_out',
    'SQLAlchemy connections currently in use',
    registry=registry
)

DB_POOL_OVERFLOW = Gauge(
    'db_pool_overflow',
    'SQLAlchemy connections beyond pool_size',
    registry=registry
)

DB_POOL_CHECKED_IN = Gauge(
    'db_pool_checked_in',
    'SQLAlchemy connections available in pool',
    registry=registry
)

SYSTEM_CPU_USAGE = Gauge(
    'system_cpu_usage',
    'System CPU usage percentage',
    registry=registry
)

SYSTEM_MEMORY_USAGE = Gauge(
    'system_memory_usage',
    'System memory usage percentage',
    registry=registry
)

BATCH_DETECTION_DURATION = Summary(
    'batch_detection_duration_seconds',
    'Batch detection processing time in seconds',
    registry=registry
)

MODEL_LOAD_DURATION = Gauge(
    'model_load_duration_seconds',
    'Model load time in seconds',
    ['model_name'],
    registry=registry
)


def update_pool_stats():
    """从SQLAlchemy引擎获取并更新连接池指标"""
    try:
        from api.core.database import engine
        pool = engine.pool
        DB_POOL_SIZE.set(pool.size())
        DB_POOL_CHECKED_OUT.set(pool.checkedout())
        DB_POOL_OVERFLOW.set(pool.overflow())
        DB_POOL_CHECKED_IN.set(pool.checkedin())
        DB_CONNECTIONS.set(pool.checkedout() + pool.checkedin())
    except Exception:
        pass


def track_request(func):
    """跟踪请求装饰器"""
    def wrapper(*args, **kwargs):
        from fastapi import Request
        request: Request = kwargs.get('request')
        if request:
            method = request.method
            endpoint = request.url.path
        else:
            method = "UNKNOWN"
            endpoint = "UNKNOWN"

        start_time = time.time()

        try:
            response = func(*args, **kwargs)
            status_code = 200
        except Exception as e:
            status_code = 500
            raise
        finally:
            duration = time.time() - start_time
            REQUEST_COUNT.labels(method=method, endpoint=endpoint, status=status_code).inc()
            REQUEST_DURATION.labels(method=method, endpoint=endpoint).observe(duration)

        return response
    return wrapper


def track_detection(func):
    """跟踪检测装饰器"""
    def wrapper(*args, **kwargs):
        start_time = time.time()

        try:
            result = func(*args, **kwargs)

            DETECTION_COUNT.labels(
                is_fake=result.is_fake,
                risk_level=result.risk_level
            ).inc()

            return result
        finally:
            duration = time.time() - start_time
            DETECTION_DURATION.observe(duration)
    return wrapper


def track_batch_detection(func):
    """跟踪批量检测装饰器"""
    def wrapper(*args, **kwargs):
        start_time = time.time()

        try:
            result = func(*args, **kwargs)

            for detection in result.results:
                DETECTION_COUNT.labels(
                    is_fake=detection.is_fake,
                    risk_level=detection.risk_level
                ).inc()

            return result
        finally:
            duration = time.time() - start_time
            BATCH_DETECTION_DURATION.observe(duration)
    return wrapper


def update_cache_stats(hit_rate, cache_type="redis"):
    """更新缓存统计"""
    CACHE_HIT_RATE.labels(cache_type=cache_type).set(hit_rate)


def update_system_stats(cpu_usage, memory_usage):
    """更新系统统计"""
    SYSTEM_CPU_USAGE.set(cpu_usage)
    SYSTEM_MEMORY_USAGE.set(memory_usage)


def record_model_load_time(model_name, duration):
    """记录模型加载时间"""
    MODEL_LOAD_DURATION.labels(model_name=model_name).set(duration)


def get_metrics():
    """获取所有指标（包含连接池实时数据）"""
    update_pool_stats()
    from prometheus_client import generate_latest
    return generate_latest(registry)