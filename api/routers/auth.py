"""
认证路由
"""
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.orm import Session

from api.core.database import get_db
from api.core.security import (
    get_password_hash, verify_password, create_access_token, 
    create_refresh_token, decode_token, get_current_user
)
from api.core.responses import success_response, error_response
from api.models.schemas import (
    LoginRequest, LoginResponse, TokenRefreshRequest,
    UserCreate, UserResponse, ApiKeyCreate, ApiKeyResponse
)
from api.services.user_service import UserService
from api.services.api_key_service import ApiKeyService

router = APIRouter(prefix="/auth", tags=["Auth"])


@router.post("/login", response_model=LoginResponse)
async def login(
    request: Request,
    login_data: LoginRequest,
    db: Session = Depends(get_db)
):
    user_service = UserService(db)
    
    result = user_service.authenticate(
        username=login_data.username,
        password=login_data.password,
        tenant_id=login_data.tenant_id or 1
    )
    
    if not result:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码错误"
        )
    
    user_service.update_last_login(result["user"]["id"], request.client.host)
    
    return LoginResponse(**result)


@router.post("/logout")
async def logout(current_user: dict = Depends(get_current_user)):
    return success_response(message="登出成功")


@router.post("/refresh")
async def refresh_token(
    refresh_data: TokenRefreshRequest,
    db: Session = Depends(get_db)
):
    payload = decode_token(refresh_data.refresh_token)
    
    if not payload or payload.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无效的刷新令牌"
        )
    
    user_id = payload.get("sub")
    tenant_id = payload.get("tenant_id")
    
    user_service = UserService(db)
    user = user_service.get_by_id(user_id)
    
    if not user or user.status != "active":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户不存在或已禁用"
        )
    
    access_token = create_access_token(data={"sub": user_id, "tenant_id": tenant_id})
    refresh_token = create_refresh_token(data={"sub": user_id, "tenant_id": tenant_id})
    
    return success_response(data={
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "expires_in": 7200
    })


@router.get("/api-keys", response_model=dict)
async def list_api_keys(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    api_key_service = ApiKeyService(db)
    keys = api_key_service.list_by_user(current_user["id"])
    
    return success_response(data=[
        {
            "id": k.id,
            "name": k.name,
            "key_prefix": k.key_prefix,
            "permissions": k.permissions,
            "rate_limit": k.rate_limit,
            "last_used_at": k.last_used_at.isoformat() if k.last_used_at else None,
            "usage_count": k.usage_count,
            "status": k.status,
            "expire_at": k.expire_at.isoformat() if k.expire_at else None,
            "created_at": k.created_at.isoformat()
        }
        for k in keys
    ])


@router.post("/api-keys", response_model=dict)
async def create_api_key(
    key_data: ApiKeyCreate,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    api_key_service = ApiKeyService(db)
    
    result = api_key_service.create(
        user_id=current_user["id"],
        tenant_id=current_user["tenant_id"],
        name=key_data.name,
        permissions=key_data.permissions,
        ip_whitelist=key_data.ip_whitelist,
        rate_limit=key_data.rate_limit,
        expire_days=key_data.expire_days
    )
    
    return success_response(data=result, message="API密钥创建成功，请妥善保管")


@router.delete("/api-keys/{key_id}")
async def revoke_api_key(
    key_id: int,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    api_key_service = ApiKeyService(db)
    
    if api_key_service.revoke(key_id, current_user["id"]):
        return success_response(message="API密钥已撤销")
    
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="API密钥不存在"
    )
