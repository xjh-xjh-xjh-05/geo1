"""
结构化日志配置 - 使用structlog
"""
import structlog
from structlog.processors import JSONRenderer
from typing import Optional
import logging


def configure_logging(log_level: str = "INFO", log_file: Optional[str] = None):
    """配置结构化日志"""
    
    structlog.configure(
        processors=[
            structlog.stdlib.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.BoundLogger,
        logger_factory=structlog.stdlib.LoggerFactory(),
    )
    
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level.upper())
    
    handlers = []
    
    console_handler = logging.StreamHandler()
    console_handler.setLevel(log_level.upper())
    handlers.append(console_handler)
    
    if log_file:
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setLevel(log_level.upper())
        handlers.append(file_handler)
    
    root_logger.handlers = handlers
    
    return structlog.get_logger()


def get_logger(name: str = None) -> structlog.BoundLogger:
    """获取结构化日志记录器"""
    if name:
        return structlog.get_logger(name)
    return structlog.get_logger()