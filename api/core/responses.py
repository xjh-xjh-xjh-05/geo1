"""
统一响应格式
"""
from typing import Any, Dict, Optional, List, Generic, TypeVar
from pydantic import BaseModel, Field
from datetime import datetime, timezone
import uuid

from api.core.errors import ErrorCode, AppException


T = TypeVar('T')


class ResponseModel(BaseModel, Generic[T]):
    code: int = Field(200, description="HTTP状态码")
    message: str = Field("success", description="响应消息")
    data: Optional[T] = Field(None, description="响应数据")
    request_id: str = Field("", description="请求ID")
    timestamp: str = Field("", description="时间戳")
    
    def __init__(self, **data):
        if "request_id" not in data or not data["request_id"]:
            data["request_id"] = str(uuid.uuid4())[:8]
        if "timestamp" not in data or not data["timestamp"]:
            data["timestamp"] = datetime.now(timezone.utc).replace(tzinfo=None).isoformat() + "Z"
        super().__init__(**data)


class ErrorResponseModel(BaseModel):
    error_code: str = Field(..., description="错误码")
    message: str = Field(..., description="错误消息")
    details: Optional[Dict[str, Any]] = Field(None, description="详细信息")
    retryable: bool = Field(False, description="是否可重试")
    request_id: str = Field("", description="请求ID")
    timestamp: str = Field("", description="时间戳")
    
    def __init__(self, **data):
        if "request_id" not in data or not data["request_id"]:
            data["request_id"] = str(uuid.uuid4())[:8]
        if "timestamp" not in data or not data["timestamp"]:
            data["timestamp"] = datetime.now(timezone.utc).replace(tzinfo=None).isoformat() + "Z"
        super().__init__(**data)


class PaginatedResponse(BaseModel, Generic[T]):
    code: int = Field(200, description="HTTP状态码")
    message: str = Field("success", description="响应消息")
    data: List[T] = Field([], description="响应数据列表")
    pagination: dict = Field({}, description="分页信息")
    request_id: str = Field("", description="请求ID")
    timestamp: str = Field("", description="时间戳")
    
    def __init__(self, **data):
        if "request_id" not in data or not data["request_id"]:
            data["request_id"] = str(uuid.uuid4())[:8]
        if "timestamp" not in data or not data["timestamp"]:
            data["timestamp"] = datetime.now(timezone.utc).replace(tzinfo=None).isoformat() + "Z"
        super().__init__(**data)


class PaginationInfo(BaseModel):
    page: int = 1
    page_size: int = 20
    total: int = 0
    total_pages: int = 0


def success_response(data: Any = None, message: str = "success") -> ResponseModel:
    return ResponseModel(code=200, message=message, data=data)


def error_response(
    error_code: ErrorCode,
    message: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None,
    retryable: bool = False
) -> ErrorResponseModel:
    return ErrorResponseModel(
        error_code=error_code.value,
        message=message or "",
        details=details,
        retryable=retryable
    )


def app_exception_response(exc: AppException) -> ErrorResponseModel:
    return ErrorResponseModel(
        error_code=exc.error_code.value,
        message=exc.message,
        details=exc.details,
        retryable=exc.retryable
    )


def paginated_response(
    data: List[Any],
    page: int,
    page_size: int,
    total: int
) -> PaginatedResponse:
    total_pages = (total + page_size - 1) // page_size if page_size > 0 else 0
    return PaginatedResponse(
        data=data,
        pagination={
            "page": page,
            "page_size": page_size,
            "total": total,
            "total_pages": total_pages
        }
    )
