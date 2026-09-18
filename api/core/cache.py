"""
缓存管理模块 - 支持Redis和内存缓存降级
"""
import json
import time
import threading
from typing import Optional, Any, List, Dict
from datetime import timedelta
from collections import OrderedDict
import hashlib

try:
    import redis
    from redis import Redis
    HAS_REDIS = True
except ImportError:
    HAS_REDIS = False
    Redis = None

from api.core.config import settings


class MemoryCache:
    """
    内存缓存实现 (LRU策略)
    用于无Redis时的降级方案
    """
    
    def __init__(self, max_size: int = 10000, default_ttl: int = 3600):
        self._cache: OrderedDict = OrderedDict()
        self._ttl: Dict[str, float] = {}
        self._max_size = max_size
        self._default_ttl = default_ttl
        self._lock = threading.RLock()
        self._hits = 0
        self._misses = 0
    
    def get(self, key: str) -> Optional[Any]:
        with self._lock:
            if key not in self._cache:
                self._misses += 1
                return None
            
            if key in self._ttl and self._ttl[key] < time.time():
                del self._cache[key]
                del self._ttl[key]
                self._misses += 1
                return None
            
            self._cache.move_to_end(key)
            self._hits += 1
            return self._cache[key]
    
    def set(self, key: str, value: Any, expire: Optional[int] = None) -> bool:
        with self._lock:
            if key in self._cache:
                del self._cache[key]
            
            self._cache[key] = value
            
            if expire:
                self._ttl[key] = time.time() + expire
            else:
                self._ttl[key] = time.time() + self._default_ttl
            
            while len(self._cache) > self._max_size:
                oldest_key = next(iter(self._cache))
                del self._cache[oldest_key]
                if oldest_key in self._ttl:
                    del self._ttl[oldest_key]
            
            return True
    
    def delete(self, key: str) -> bool:
        with self._lock:
            if key in self._cache:
                del self._cache[key]
                if key in self._ttl:
                    del self._ttl[key]
                return True
            return False
    
    def exists(self, key: str) -> bool:
        with self._lock:
            if key not in self._cache:
                return False
            if key in self._ttl and self._ttl[key] < time.time():
                del self._cache[key]
                del self._ttl[key]
                return False
            return True
    
    def incr(self, key: str) -> int:
        with self._lock:
            value = self._cache.get(key, 0)
            if isinstance(value, int):
                value += 1
            else:
                value = 1
            self._cache[key] = value
            return value
    
    def expire(self, key: str, seconds: int) -> bool:
        with self._lock:
            if key in self._cache:
                self._ttl[key] = time.time() + seconds
                return True
            return False
    
    def ttl(self, key: str) -> int:
        with self._lock:
            if key not in self._ttl:
                return -1
            remaining = self._ttl[key] - time.time()
            return max(0, int(remaining))
    
    def clear(self):
        with self._lock:
            self._cache.clear()
            self._ttl.clear()
    
    def get_stats(self) -> Dict[str, Any]:
        with self._lock:
            total = self._hits + self._misses
            hit_rate = self._hits / total if total > 0 else 0
            return {
                "size": len(self._cache),
                "max_size": self._max_size,
                "hits": self._hits,
                "misses": self._misses,
                "hit_rate": hit_rate
            }


class HybridCache:
    """
    混合缓存 - Redis优先，内存缓存降级
    """
    
    def __init__(self):
        self._redis_client = None
        self._memory_cache = MemoryCache()
        self._use_redis = False
        
        if HAS_REDIS:
            try:
                self._redis_client = redis.from_url(
                    settings.REDIS_URL,
                    decode_responses=True,
                    socket_connect_timeout=2,
                    socket_timeout=2
                )
                self._redis_client.ping()
                self._use_redis = True
            except Exception as e:
                self._use_redis = False
    
    def get(self, key: str) -> Optional[Any]:
        if self._use_redis:
            try:
                value = self._redis_client.get(key)
                if value:
                    try:
                        return json.loads(value)
                    except json.JSONDecodeError:
                        return value
                return None
            except Exception:
                return self._memory_cache.get(key)
        return self._memory_cache.get(key)
    
    def set(self, key: str, value: Any, expire: Optional[int] = None) -> bool:
        if self._use_redis:
            try:
                if isinstance(value, (dict, list)):
                    value = json.dumps(value, ensure_ascii=False)
                return self._redis_client.set(key, value, ex=expire)
            except Exception:
                return self._memory_cache.set(key, value, expire)
        return self._memory_cache.set(key, value, expire)
    
    def delete(self, key: str) -> bool:
        if self._use_redis:
            try:
                return bool(self._redis_client.delete(key))
            except Exception:
                return self._memory_cache.delete(key)
        return self._memory_cache.delete(key)
    
    def exists(self, key: str) -> bool:
        if self._use_redis:
            try:
                return bool(self._redis_client.exists(key))
            except Exception:
                return self._memory_cache.exists(key)
        return self._memory_cache.exists(key)
    
    def incr(self, key: str) -> int:
        if self._use_redis:
            try:
                return self._redis_client.incr(key)
            except Exception:
                return self._memory_cache.incr(key)
        return self._memory_cache.incr(key)
    
    def expire(self, key: str, seconds: int) -> bool:
        if self._use_redis:
            try:
                return self._redis_client.expire(key, seconds)
            except Exception:
                return self._memory_cache.expire(key, seconds)
        return self._memory_cache.expire(key, seconds)
    
    def ttl(self, key: str) -> int:
        if self._use_redis:
            try:
                return self._redis_client.ttl(key)
            except Exception:
                return self._memory_cache.ttl(key)
        return self._memory_cache.ttl(key)
    
    def hset(self, name: str, key: str, value: Any) -> int:
        if self._use_redis:
            try:
                if isinstance(value, (dict, list)):
                    value = json.dumps(value, ensure_ascii=False)
                return self._redis_client.hset(name, key, value)
            except Exception:
                pass
        return 0
    
    def hget(self, name: str, key: str) -> Optional[Any]:
        if self._use_redis:
            try:
                value = self._redis_client.hget(name, key)
                if value:
                    try:
                        return json.loads(value)
                    except json.JSONDecodeError:
                        return value
            except Exception:
                pass
        return None
    
    def hgetall(self, name: str) -> dict:
        if self._use_redis:
            try:
                return self._redis_client.hgetall(name)
            except Exception:
                pass
        return {}
    
    def is_redis_available(self) -> bool:
        return self._use_redis
    
    def get_stats(self) -> Dict[str, Any]:
        return {
            "redis_enabled": self._use_redis,
            "memory_cache_stats": self._memory_cache.get_stats()
        }


cache = HybridCache()


class DetectionCache:
    """
    检测结果缓存
    """
    
    CACHE_PREFIX = "det:"
    RESULT_TTL = 3600
    
    @staticmethod
    def _generate_cache_key(poi_data: Dict[str, Any]) -> str:
        key_data = {
            "name": poi_data.get("name", ""),
            "address": poi_data.get("address", ""),
            "lat": round(float(poi_data.get("latitude", 0)), 6),
            "lon": round(float(poi_data.get("longitude", 0)), 6),
        }
        key_str = json.dumps(key_data, sort_keys=True)
        return f"{DetectionCache.CACHE_PREFIX}{hashlib.md5(key_str.encode()).hexdigest()}"
    
    @staticmethod
    def get_result(poi_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        key = DetectionCache._generate_cache_key(poi_data)
        return cache.get(key)
    
    @staticmethod
    def set_result(poi_data: Dict[str, Any], result: Dict[str, Any], ttl: int = None):
        key = DetectionCache._generate_cache_key(poi_data)
        cache.set(key, result, expire=ttl or DetectionCache.RESULT_TTL)
    
    @staticmethod
    def invalidate(poi_data: Dict[str, Any]):
        key = DetectionCache._generate_cache_key(poi_data)
        cache.delete(key)


class CacheManager:
    """
    缓存管理器
    """
    
    USER_PREFIX = "user:"
    TENANT_PREFIX = "tenant:"
    RULE_PREFIX = "rule:"
    KEYWORD_PREFIX = "keyword:"
    QUOTA_PREFIX = "quota:"
    
    @staticmethod
    def cache_user(user_id: int, user_data: dict, expire: int = 3600):
        key = f"{CacheManager.USER_PREFIX}{user_id}"
        cache.set(key, user_data, expire)
    
    @staticmethod
    def get_cached_user(user_id: int) -> Optional[dict]:
        key = f"{CacheManager.USER_PREFIX}{user_id}"
        return cache.get(key)
    
    @staticmethod
    def invalidate_user(user_id: int):
        key = f"{CacheManager.USER_PREFIX}{user_id}"
        cache.delete(key)
    
    @staticmethod
    def cache_tenant(tenant_id: int, tenant_data: dict, expire: int = 3600):
        key = f"{CacheManager.TENANT_PREFIX}{tenant_id}"
        cache.set(key, tenant_data, expire)
    
    @staticmethod
    def get_cached_tenant(tenant_id: int) -> Optional[dict]:
        key = f"{CacheManager.TENANT_PREFIX}{tenant_id}"
        return cache.get(key)
    
    @staticmethod
    def check_rate_limit(api_key: str, limit: int, window: int = 60) -> tuple:
        key = f"rate_limit:{api_key}"
        current = cache.incr(key)
        if current == 1:
            cache.expire(key, window)
        ttl = cache.ttl(key)
        return current <= limit, current, ttl
    
    @staticmethod
    def increment_quota(tenant_id: int, date_str: str) -> tuple:
        daily_key = f"{CacheManager.QUOTA_PREFIX}daily:{tenant_id}:{date_str}"
        monthly_key = f"{CacheManager.QUOTA_PREFIX}monthly:{tenant_id}:{date_str[:7]}"
        
        daily_count = cache.incr(daily_key)
        monthly_count = cache.incr(monthly_key)
        
        if daily_count == 1:
            cache.expire(daily_key, 86400)
        if monthly_count == 1:
            cache.expire(monthly_key, 2592000)
        
        return daily_count, monthly_count
