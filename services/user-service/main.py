"""
用户服务 - 用户认证与管理
"""
from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
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
    APP_NAME: str = "User Service"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False
    
    # 数据库配置
    DATABASE_URL: str = "postgresql://postgres:postgres@db:5432/geo_fake_detection"
    DATABASE_POOL_SIZE: int = 20
    DATABASE_MAX_OVERFLOW: int = 10
    
    # 缓存配置
    REDIS_URL: str = "redis://redis:6379/0"
    
    # 认证配置
    SECRET_KEY: str = "your-secret-key-change-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 120
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    
    # CORS
    CORS_ORIGINS: list = ["*"]
    
    class Config:
        env_file = ".env"
        case_sensitive = True
        extra = "ignore"


# 初始化配置
settings = Settings()

# 初始化数据库连接
from api.core.database import get_db, engine, Base

# 导入模型
from api.models.db_models import User, Tenant, ApiKey
from api.models.schemas import (
    UserCreate, UserUpdate, UserResponse,
    LoginRequest as UserLogin,
    TokenResponse,
    ApiKeyCreate as APIKeyCreate, ApiKeyResponse as APIKeyResponse
)

# 导入服务
from api.services.user_service import UserService
from api.services.tenant_service import TenantService
from api.services.api_key_service import ApiKeyService as APIKeyService

# 导入安全工具
from api.core.security import create_access_token, create_refresh_token, decode_token as verify_token
from api.core.security import get_current_user

# 创建FastAPI应用
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="GEO虚假内容检测平台 - 用户服务"
)

# 配置CORS
from fastapi.middleware.cors import CORSMiddleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# 初始化服务
user_service = UserService()
tenant_service = TenantService()
api_key_service = APIKeyService()


# 健康检查
@app.get("/health")
async def health_check():
    """健康检查"""
    from api.core.database import engine
    from sqlalchemy import text
    
    components = {}
    
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        components["database"] = "up"
    except Exception:
        components["database"] = "down"
    
    from api.core.cache import cache
    components["cache"] = "up" if cache.is_redis_available() else "up (memory fallback)"
    
    all_up = all("up" in v for v in components.values())
    
    return {
        "status": "healthy" if all_up else "unhealthy",
        "components": components,
        "timestamp": time.time()
    }


# 登录
@app.post("/api/v1/auth/login", response_model=TokenResponse)
async def login(
    login_data: UserLogin,
    db: Session = Depends(get_db)
):
    """用户登录"""
    try:
        # 验证用户
        user = user_service.authenticate_user(
            db=db,
            username=login_data.username,
            password=login_data.password
        )
        
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="用户名或密码错误",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        # 生成令牌
        access_token = create_access_token(
            data={
                "sub": str(user.id),
                "tenant_id": str(user.tenant_id),
                "username": user.username,
                "role": user.role
            }
        )
        
        refresh_token = create_refresh_token(
            data={
                "sub": str(user.id),
                "tenant_id": str(user.tenant_id)
            }
        )
        
        # 更新最后登录时间
        user_service.update_last_login(
            db=db,
            user_id=user.id,
            ip_address="127.0.0.1"  # 实际应该从请求中获取
        )
        
        logger.info(f"User {user.username} logged in successfully")
        
        return TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            token_type="bearer",
            expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
            user={
                "id": user.id,
                "username": user.username,
                "email": user.email,
                "role": user.role,
                "tenant_id": user.tenant_id
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Login failed: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"登录失败: {str(e)}"
        )


# 刷新令牌
@app.post("/api/v1/auth/refresh", response_model=TokenResponse)
async def refresh_token(
    refresh_token: str,
    db: Session = Depends(get_db)
):
    """刷新令牌"""
    try:
        # 验证刷新令牌
        payload = verify_token(refresh_token)
        user_id = int(payload.get("sub"))
        
        # 获取用户信息
        user = user_service.get_user_by_id(db, user_id)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="用户不存在",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        # 生成新的访问令牌
        access_token = create_access_token(
            data={
                "sub": str(user.id),
                "tenant_id": str(user.tenant_id),
                "username": user.username,
                "role": user.role
            }
        )
        
        logger.info(f"Token refreshed for user {user.username}")
        
        return TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,  # 保持原刷新令牌
            token_type="bearer",
            expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
            user={
                "id": user.id,
                "username": user.username,
                "email": user.email,
                "role": user.role,
                "tenant_id": user.tenant_id
            }
        )
        
    except Exception as e:
        logger.error(f"Token refresh failed: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="令牌无效或已过期",
            headers={"WWW-Authenticate": "Bearer"},
        )


# 获取当前用户信息
@app.get("/api/v1/auth/me", response_model=UserResponse)
async def get_current_user_info(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """获取当前用户信息"""
    try:
        user = user_service.get_user_by_id(db, current_user["id"])
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="用户不存在"
            )
        
        return UserResponse(
            id=user.id,
            username=user.username,
            email=user.email,
            phone=user.phone,
            role=user.role,
            status=user.status,
            tenant_id=user.tenant_id,
            created_at=user.created_at
        )
        
    except Exception as e:
        logger.error(f"Get user info failed: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取用户信息失败: {str(e)}"
        )


# 获取用户列表
@app.get("/api/v1/users")
async def get_users(
    page: int = 1,
    page_size: int = 20,
    role: str = None,
    status: str = None,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """获取用户列表"""
    try:
        # 权限检查
        if current_user.get("role") not in ["admin", "super_admin"]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="权限不足"
            )
        
        # 获取用户列表
        users, total = user_service.get_users(
            db=db,
            page=page,
            page_size=page_size,
            role=role,
            status=status,
            tenant_id=current_user.get("tenant_id")
        )
        
        # 构建响应
        results = []
        for user in users:
            results.append({
                "id": user.id,
                "username": user.username,
                "email": user.email,
                "phone": user.phone,
                "role": user.role,
                "status": user.status,
                "tenant_id": user.tenant_id,
                "created_at": user.created_at.isoformat() if user.created_at else None,
                "last_login_at": user.last_login_at.isoformat() if user.last_login_at else None
            })
        
        return {
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": (total + page_size - 1) // page_size,
            "results": results
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get users failed: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取用户列表失败: {str(e)}"
        )


# 创建用户
@app.post("/api/v1/users", response_model=UserResponse)
async def create_user(
    user_data: UserCreate,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """创建用户"""
    try:
        # 权限检查
        if current_user.get("role") not in ["admin", "super_admin"]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="权限不足"
            )
        
        # 创建用户
        user = user_service.create_user(
            db=db,
            user_data=user_data,
            tenant_id=current_user.get("tenant_id")
        )
        
        logger.info(f"User {user.username} created by {current_user.get('username')}")
        
        return UserResponse(
            id=user.id,
            username=user.username,
            email=user.email,
            phone=user.phone,
            role=user.role,
            status=user.status,
            tenant_id=user.tenant_id,
            created_at=user.created_at
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Create user failed: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"创建用户失败: {str(e)}"
        )


# 根路径
@app.get("/")
async def root():
    """根路径"""
    return {
        "message": "User Service",
        "version": settings.APP_VERSION,
        "endpoints": {
            "login": "/api/v1/auth/login",
            "refresh": "/api/v1/auth/refresh",
            "me": "/api/v1/auth/me",
            "users": "/api/v1/users"
        }
    }


# 启动事件
@app.on_event("startup")
async def startup_event():
    """启动事件"""
    logger.info(f"Starting User Service v{settings.APP_VERSION}")
    logger.info("Initializing user service...")


# 关闭事件
@app.on_event("shutdown")
async def shutdown_event():
    """关闭事件"""
    logger.info("User Service shutdown")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.DEBUG
    )