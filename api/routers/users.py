"""
用户管理路由
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from datetime import datetime

from api.core.database import get_db
from api.core.security import get_current_user, get_password_hash
from api.core.responses import success_response, paginated_response
from api.models.schemas import UserCreate, UserUpdate, UserResponse
from api.models.db_models import User, Tenant
from api.services.user_service import UserService

router = APIRouter(prefix="/users", tags=["Users"])


@router.get("")
async def list_users(
    page: int = 1,
    page_size: int = 20,
    role: str = None,
    status: str = None,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if current_user.get("role") not in ["admin", "super_admin"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="权限不足"
        )
    
    query = db.query(User).filter(
        User.tenant_id == current_user["tenant_id"]
    )
    
    if role:
        query = query.filter(User.role == role)
    if status:
        query = query.filter(User.status == status)
    
    query = query.order_by(User.created_at.desc())
    
    total = query.count()
    users = query.offset((page - 1) * page_size).limit(page_size).all()
    
    return paginated_response(
        data=[
            {
                "id": u.id,
                "username": u.username,
                "email": u.email,
                "phone": u.phone,
                "role": u.role,
                "permissions": u.permissions,
                "status": u.status,
                "last_login_at": u.last_login_at.isoformat() if u.last_login_at else None,
                "created_at": u.created_at.isoformat()
            }
            for u in users
        ],
        page=page,
        page_size=page_size,
        total=total
    )


@router.post("")
async def create_user(
    user_data: UserCreate,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if current_user.get("role") not in ["admin", "super_admin"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="权限不足"
        )
    
    user_service = UserService(db)
    
    existing = user_service.get_by_username(user_data.username, current_user["tenant_id"])
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="用户名已存在"
        )
    
    existing = user_service.get_by_email(user_data.email, current_user["tenant_id"])
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="邮箱已存在"
        )
    
    user = user_service.create(
        username=user_data.username,
        email=user_data.email,
        password=user_data.password,
        tenant_id=current_user["tenant_id"],
        role=user_data.role,
        permissions=user_data.permissions
    )
    
    return success_response(data={
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "role": user.role,
        "created_at": user.created_at.isoformat()
    }, message="用户创建成功")


@router.get("/{user_id}")
async def get_user(
    user_id: int,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    user = db.query(User).filter(
        User.id == user_id,
        User.tenant_id == current_user["tenant_id"]
    ).first()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="用户不存在"
        )
    
    return success_response(data={
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "phone": user.phone,
        "role": user.role,
        "permissions": user.permissions,
        "status": user.status,
        "avatar_url": user.avatar_url,
        "display_name": user.display_name,
        "last_login_at": user.last_login_at.isoformat() if user.last_login_at else None,
        "last_login_ip": user.last_login_ip,
        "created_at": user.created_at.isoformat()
    })


@router.put("/{user_id}")
async def update_user(
    user_id: int,
    user_data: UserUpdate,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if current_user.get("role") not in ["admin", "super_admin"] and current_user["id"] != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="权限不足"
        )
    
    user = db.query(User).filter(
        User.id == user_id,
        User.tenant_id == current_user["tenant_id"]
    ).first()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="用户不存在"
        )
    
    update_data = user_data.dict(exclude_unset=True)
    
    if "password" in update_data:
        update_data["password_hash"] = get_password_hash(update_data.pop("password"))
    
    for key, value in update_data.items():
        if hasattr(user, key):
            setattr(user, key, value)
    
    db.commit()
    db.refresh(user)
    
    return success_response(data={
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "role": user.role,
        "status": user.status,
        "updated_at": user.updated_at.isoformat()
    }, message="用户更新成功")


@router.delete("/{user_id}")
async def delete_user(
    user_id: int,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if current_user.get("role") not in ["admin", "super_admin"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="权限不足"
        )
    
    if current_user["id"] == user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="不能删除自己"
        )
    
    user = db.query(User).filter(
        User.id == user_id,
        User.tenant_id == current_user["tenant_id"]
    ).first()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="用户不存在"
        )
    
    user.status = "deleted"
    db.commit()
    
    return success_response(message="用户已删除")


@router.put("/{user_id}/reset-password")
async def reset_user_password(
    user_id: int,
    new_password: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if current_user.get("role") not in ["admin", "super_admin"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="权限不足"
        )
    
    user = db.query(User).filter(
        User.id == user_id,
        User.tenant_id == current_user["tenant_id"]
    ).first()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="用户不存在"
        )
    
    user.password_hash = get_password_hash(new_password)
    db.commit()
    
    return success_response(message="密码重置成功")
