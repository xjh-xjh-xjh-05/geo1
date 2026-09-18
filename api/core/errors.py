"""
统一错误码体系
错误码结构：XXX-YYY
- XXX: 错误类别（100-199: 系统错误, 200-299: 认证错误, 300-399: 业务错误, 400-499: 参数错误）
- YYY: 具体错误编号
"""
from enum import Enum
from typing import Optional, Dict, Any


class ErrorCode(str, Enum):
    """错误码枚举"""
    
    # ==================== 系统错误 (100-199) ====================
    SYSTEM_ERROR = "100-001"
    DATABASE_ERROR = "100-002"
    CACHE_ERROR = "100-003"
    SERVICE_UNAVAILABLE = "100-004"
    TIMEOUT_ERROR = "100-005"
    
    # ==================== 认证错误 (200-299) ====================
    UNAUTHORIZED = "200-001"
    INVALID_TOKEN = "200-002"
    TOKEN_EXPIRED = "200-003"
    INVALID_CREDENTIALS = "200-004"
    USER_DISABLED = "200-005"
    PERMISSION_DENIED = "200-006"
    API_KEY_INVALID = "200-007"
    API_KEY_EXPIRED = "200-008"
    QUOTA_EXCEEDED = "200-009"
    RATE_LIMIT_EXCEEDED = "200-010"
    
    # ==================== 业务错误 (300-399) ====================
    RESOURCE_NOT_FOUND = "300-001"
    RESOURCE_ALREADY_EXISTS = "300-002"
    OPERATION_NOT_ALLOWED = "300-003"
    INVALID_STATE = "300-004"
    DETECTION_FAILED = "300-005"
    MODEL_NOT_FOUND = "300-006"
    RULE_VALIDATION_FAILED = "300-007"
    
    # ==================== 参数错误 (400-499) ====================
    VALIDATION_ERROR = "400-001"
    MISSING_REQUIRED_FIELD = "400-002"
    INVALID_FORMAT = "400-003"
    OUT_OF_RANGE = "400-004"
    INVALID_ENUM_VALUE = "400-005"


class ErrorCategory(str, Enum):
    """错误类别"""
    SYSTEM = "system"
    AUTH = "auth"
    BUSINESS = "business"
    VALIDATION = "validation"


ERROR_CODE_MAP: Dict[str, Dict[str, Any]] = {
    ErrorCode.SYSTEM_ERROR: {
        "http_status": 500,
        "message": "系统内部错误",
        "category": ErrorCategory.SYSTEM,
        "retryable": False
    },
    ErrorCode.DATABASE_ERROR: {
        "http_status": 500,
        "message": "数据库操作失败",
        "category": ErrorCategory.SYSTEM,
        "retryable": True
    },
    ErrorCode.CACHE_ERROR: {
        "http_status": 500,
        "message": "缓存操作失败",
        "category": ErrorCategory.SYSTEM,
        "retryable": True
    },
    ErrorCode.SERVICE_UNAVAILABLE: {
        "http_status": 503,
        "message": "服务暂时不可用",
        "category": ErrorCategory.SYSTEM,
        "retryable": True
    },
    ErrorCode.TIMEOUT_ERROR: {
        "http_status": 504,
        "message": "请求超时",
        "category": ErrorCategory.SYSTEM,
        "retryable": True
    },
    ErrorCode.UNAUTHORIZED: {
        "http_status": 401,
        "message": "未授权访问",
        "category": ErrorCategory.AUTH,
        "retryable": False
    },
    ErrorCode.INVALID_TOKEN: {
        "http_status": 401,
        "message": "无效的访问令牌",
        "category": ErrorCategory.AUTH,
        "retryable": False
    },
    ErrorCode.TOKEN_EXPIRED: {
        "http_status": 401,
        "message": "访问令牌已过期",
        "category": ErrorCategory.AUTH,
        "retryable": False
    },
    ErrorCode.INVALID_CREDENTIALS: {
        "http_status": 401,
        "message": "用户名或密码错误",
        "category": ErrorCategory.AUTH,
        "retryable": False
    },
    ErrorCode.USER_DISABLED: {
        "http_status": 403,
        "message": "用户已被禁用",
        "category": ErrorCategory.AUTH,
        "retryable": False
    },
    ErrorCode.PERMISSION_DENIED: {
        "http_status": 403,
        "message": "缺少必要权限",
        "category": ErrorCategory.AUTH,
        "retryable": False
    },
    ErrorCode.API_KEY_INVALID: {
        "http_status": 401,
        "message": "无效的API密钥",
        "category": ErrorCategory.AUTH,
        "retryable": False
    },
    ErrorCode.API_KEY_EXPIRED: {
        "http_status": 401,
        "message": "API密钥已过期",
        "category": ErrorCategory.AUTH,
        "retryable": False
    },
    ErrorCode.QUOTA_EXCEEDED: {
        "http_status": 429,
        "message": "超出配额限制",
        "category": ErrorCategory.AUTH,
        "retryable": False
    },
    ErrorCode.RATE_LIMIT_EXCEEDED: {
        "http_status": 429,
        "message": "请求过于频繁",
        "category": ErrorCategory.AUTH,
        "retryable": True
    },
    ErrorCode.RESOURCE_NOT_FOUND: {
        "http_status": 404,
        "message": "资源不存在",
        "category": ErrorCategory.BUSINESS,
        "retryable": False
    },
    ErrorCode.RESOURCE_ALREADY_EXISTS: {
        "http_status": 409,
        "message": "资源已存在",
        "category": ErrorCategory.BUSINESS,
        "retryable": False
    },
    ErrorCode.OPERATION_NOT_ALLOWED: {
        "http_status": 403,
        "message": "操作不允许",
        "category": ErrorCategory.BUSINESS,
        "retryable": False
    },
    ErrorCode.INVALID_STATE: {
        "http_status": 400,
        "message": "无效状态",
        "category": ErrorCategory.BUSINESS,
        "retryable": False
    },
    ErrorCode.DETECTION_FAILED: {
        "http_status": 500,
        "message": "检测失败",
        "category": ErrorCategory.BUSINESS,
        "retryable": True
    },
    ErrorCode.MODEL_NOT_FOUND: {
        "http_status": 404,
        "message": "模型不存在",
        "category": ErrorCategory.BUSINESS,
        "retryable": False
    },
    ErrorCode.RULE_VALIDATION_FAILED: {
        "http_status": 400,
        "message": "规则验证失败",
        "category": ErrorCategory.BUSINESS,
        "retryable": False
    },
    ErrorCode.VALIDATION_ERROR: {
        "http_status": 400,
        "message": "参数验证失败",
        "category": ErrorCategory.VALIDATION,
        "retryable": False
    },
    ErrorCode.MISSING_REQUIRED_FIELD: {
        "http_status": 400,
        "message": "缺少必填字段",
        "category": ErrorCategory.VALIDATION,
        "retryable": False
    },
    ErrorCode.INVALID_FORMAT: {
        "http_status": 400,
        "message": "无效格式",
        "category": ErrorCategory.VALIDATION,
        "retryable": False
    },
    ErrorCode.OUT_OF_RANGE: {
        "http_status": 400,
        "message": "参数超出范围",
        "category": ErrorCategory.VALIDATION,
        "retryable": False
    },
    ErrorCode.INVALID_ENUM_VALUE: {
        "http_status": 400,
        "message": "无效的枚举值",
        "category": ErrorCategory.VALIDATION,
        "retryable": False
    }
}


class AppException(Exception):
    """应用自定义异常"""
    
    def __init__(
        self,
        error_code: ErrorCode,
        message: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        original_exception: Optional[Exception] = None
    ):
        self.error_code = error_code
        self.details = details or {}
        self.original_exception = original_exception
        
        error_info = ERROR_CODE_MAP.get(error_code)
        self.http_status = error_info["http_status"] if error_info else 500
        self.message = message or (error_info["message"] if error_info else "未知错误")
        self.retryable = error_info["retryable"] if error_info else False
        
        super().__init__(self.message)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "code": self.error_code.value,
            "message": self.message,
            "details": self.details,
            "retryable": self.retryable
        }


def get_error_info(error_code: ErrorCode) -> Dict[str, Any]:
    """获取错误码信息"""
    return ERROR_CODE_MAP.get(error_code, {
        "http_status": 500,
        "message": "未知错误",
        "category": ErrorCategory.SYSTEM,
        "retryable": False
    })