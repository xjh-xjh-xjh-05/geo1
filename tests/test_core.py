import pytest
import time
from unittest.mock import patch, MagicMock

from api.core.errors import (
    ErrorCode, AppException, ErrorCategory,
    ERROR_CODE_MAP, get_error_info
)
from api.core.responses import (
    success_response, error_response, app_exception_response,
    paginated_response, ResponseModel, ErrorResponseModel, PaginatedResponse
)
from api.core.cache import MemoryCache


class TestErrorCode:
    def test_error_code_values_are_unique(self):
        values = [e.value for e in ErrorCode]
        assert len(values) == len(set(values))

    def test_error_code_map_covers_all_codes(self):
        for code in ErrorCode:
            assert code in ERROR_CODE_MAP, f"Missing mapping for {code}"

    def test_error_code_map_has_required_fields(self):
        required_keys = {"http_status", "message", "category", "retryable"}
        for code, info in ERROR_CODE_MAP.items():
            assert required_keys.issubset(info.keys()), f"Missing keys for {code}"

    def test_system_errors_in_500_range(self):
        system_codes = [
            ErrorCode.SYSTEM_ERROR, ErrorCode.DATABASE_ERROR,
            ErrorCode.CACHE_ERROR
        ]
        for code in system_codes:
            assert ERROR_CODE_MAP[code]["http_status"] >= 500

    def test_auth_errors_in_401_403_range(self):
        auth_codes = [ErrorCode.UNAUTHORIZED, ErrorCode.PERMISSION_DENIED]
        for code in auth_codes:
            status = ERROR_CODE_MAP[code]["http_status"]
            assert status in (401, 403)

    def test_validation_errors_in_400_range(self):
        validation_codes = [
            ErrorCode.VALIDATION_ERROR, ErrorCode.MISSING_REQUIRED_FIELD,
            ErrorCode.INVALID_FORMAT
        ]
        for code in validation_codes:
            assert ERROR_CODE_MAP[code]["http_status"] == 400


class TestAppException:
    def test_basic_creation(self):
        exc = AppException(ErrorCode.SYSTEM_ERROR)
        assert exc.error_code == ErrorCode.SYSTEM_ERROR
        assert exc.http_status == 500
        assert exc.message == "系统内部错误"
        assert exc.retryable is False

    def test_custom_message(self):
        exc = AppException(ErrorCode.RESOURCE_NOT_FOUND, message="用户不存在")
        assert exc.message == "用户不存在"
        assert exc.http_status == 404

    def test_details_preserved(self):
        details = {"field": "username", "value": "test"}
        exc = AppException(ErrorCode.VALIDATION_ERROR, details=details)
        assert exc.details == details

    def test_to_dict(self):
        exc = AppException(ErrorCode.TOKEN_EXPIRED)
        d = exc.to_dict()
        assert d["code"] == "200-003"
        assert "message" in d
        assert "retryable" in d

    def test_original_exception_stored(self):
        original = ValueError("original")
        exc = AppException(ErrorCode.SYSTEM_ERROR, original_exception=original)
        assert exc.original_exception is original


class TestGetErrorInfo:
    def test_known_code(self):
        info = get_error_info(ErrorCode.DATABASE_ERROR)
        assert info["http_status"] == 500
        assert info["retryable"] is True

    def test_returns_default_for_unknown(self):
        info = get_error_info("unknown-code")
        assert info["http_status"] == 500


class TestSuccessResponse:
    def test_basic_response(self):
        resp = success_response(data={"key": "value"})
        assert resp.code == 200
        assert resp.message == "success"
        assert resp.data == {"key": "value"}

    def test_custom_message(self):
        resp = success_response(message="操作成功")
        assert resp.message == "操作成功"

    def test_none_data(self):
        resp = success_response()
        assert resp.data is None

    def test_has_request_id_and_timestamp(self):
        resp = success_response(data="test")
        assert resp.request_id
        assert resp.timestamp


class TestErrorResponse:
    def test_basic_error(self):
        resp = error_response(ErrorCode.VALIDATION_ERROR, message="字段错误")
        assert resp.error_code == "400-001"
        assert resp.message == "字段错误"

    def test_with_details(self):
        details = {"field": "email"}
        resp = error_response(ErrorCode.INVALID_FORMAT, details=details)
        assert resp.details == details

    def test_retryable_flag(self):
        resp = error_response(ErrorCode.RATE_LIMIT_EXCEEDED, retryable=True)
        assert resp.retryable is True


class TestAppExceptionResponse:
    def test_from_exception(self):
        exc = AppException(ErrorCode.RESOURCE_NOT_FOUND, message="记录不存在")
        resp = app_exception_response(exc)
        assert resp.error_code == "300-001"
        assert resp.message == "记录不存在"


class TestPaginatedResponse:
    def test_basic_pagination(self):
        resp = paginated_response(
            data=[1, 2, 3],
            page=1,
            page_size=10,
            total=25
        )
        assert resp.pagination["page"] == 1
        assert resp.pagination["total"] == 25
        assert resp.pagination["total_pages"] == 3

    def test_empty_data(self):
        resp = paginated_response(data=[], page=1, page_size=10, total=0)
        assert resp.data == []
        assert resp.pagination["total_pages"] == 0

    def test_single_page(self):
        resp = paginated_response(data=[1], page=1, page_size=10, total=1)
        assert resp.pagination["total_pages"] == 1


class TestMemoryCache:
    @pytest.fixture
    def cache(self):
        return MemoryCache(max_size=100, default_ttl=60)

    def test_set_and_get(self, cache):
        cache.set("key1", "value1")
        assert cache.get("key1") == "value1"

    def test_get_missing_key(self, cache):
        assert cache.get("nonexistent") is None

    def test_delete(self, cache):
        cache.set("key1", "value1")
        assert cache.delete("key1") is True
        assert cache.get("key1") is None

    def test_delete_nonexistent(self, cache):
        assert cache.delete("nonexistent") is False

    def test_exists(self, cache):
        cache.set("key1", "value1")
        assert cache.exists("key1") is True
        assert cache.exists("nonexistent") is False

    def test_ttl_expiration(self, cache):
        cache.set("key1", "value1", expire=1)
        assert cache.get("key1") == "value1"
        time.sleep(1.1)
        assert cache.get("key1") is None

    def test_default_ttl(self, cache):
        cache.set("key1", "value1")
        ttl = cache.ttl("key1")
        assert 0 < ttl <= 60

    def test_lru_eviction(self):
        small_cache = MemoryCache(max_size=3, default_ttl=60)
        small_cache.set("a", 1)
        small_cache.set("b", 2)
        small_cache.set("c", 3)
        small_cache.set("d", 4)
        assert small_cache.get("a") is None
        assert small_cache.get("d") == 4

    def test_incr(self, cache):
        assert cache.incr("counter") == 1
        assert cache.incr("counter") == 2
        assert cache.incr("counter") == 3

    def test_clear(self, cache):
        cache.set("key1", "value1")
        cache.set("key2", "value2")
        cache.clear()
        assert cache.get("key1") is None
        assert cache.get("key2") is None

    def test_get_stats(self, cache):
        cache.set("key1", "value1")
        cache.get("key1")
        cache.get("nonexistent")
        stats = cache.get_stats()
        assert stats["size"] == 1
        assert stats["hits"] == 1
        assert stats["misses"] == 1
        assert stats["hit_rate"] == 0.5

    def test_expire_existing_key(self, cache):
        cache.set("key1", "value1")
        assert cache.expire("key1", 120) is True
        ttl = cache.ttl("key1")
        assert ttl > 60

    def test_expire_nonexistent_key(self, cache):
        assert cache.expire("nonexistent", 120) is False

    def test_update_existing_key(self, cache):
        cache.set("key1", "old")
        cache.set("key1", "new")
        assert cache.get("key1") == "new"
