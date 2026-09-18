"""
用户服务
"""
from typing import Optional, Dict, Any
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import and_

from api.models.db_models import User, Tenant
from api.core.security import get_password_hash, verify_password, create_access_token, create_refresh_token
from api.core.cache import CacheManager


class UserService:
    def __init__(self, db: Session):
        self.db = db
    
    def get_by_id(self, user_id: int) -> Optional[User]:
        cached = CacheManager.get_cached_user(user_id)
        if cached:
            return User(**cached)
        
        user = self.db.query(User).filter(User.id == user_id).first()
        return user
    
    def get_by_username(self, username: str, tenant_id: int) -> Optional[User]:
        return self.db.query(User).filter(
            and_(User.username == username, User.tenant_id == tenant_id)
        ).first()
    
    def get_by_email(self, email: str, tenant_id: int) -> Optional[User]:
        return self.db.query(User).filter(
            and_(User.email == email, User.tenant_id == tenant_id)
        ).first()
    
    def create(self, username: str, email: str, password: str, tenant_id: int,
               role: str = "user", permissions: list = None) -> User:
        hashed_password = get_password_hash(password)
        user = User(
            username=username,
            email=email,
            password_hash=hashed_password,
            tenant_id=tenant_id,
            role=role,
            permissions=permissions or []
        )
        self.db.add(user)
        self.db.commit()
        self.db.refresh(user)
        return user
    
    def update(self, user_id: int, **kwargs) -> Optional[User]:
        user = self.get_by_id(user_id)
        if not user:
            return None
        
        if "password" in kwargs:
            kwargs["password_hash"] = get_password_hash(kwargs.pop("password"))
        
        for key, value in kwargs.items():
            if hasattr(user, key):
                setattr(user, key, value)
        
        self.db.commit()
        self.db.refresh(user)
        CacheManager.invalidate_user(user_id)
        return user
    
    def authenticate(self, username: str, password: str, tenant_id: int) -> Optional[Dict[str, Any]]:
        user = self.get_by_username(username, tenant_id)
        if not user:
            return None
        
        if not verify_password(password, user.password_hash):
            return None
        
        if user.status != "active":
            return None
        
        user.last_login_at = datetime.utcnow()
        self.db.commit()
        
        access_token = create_access_token(data={"sub": user.id, "tenant_id": user.tenant_id})
        refresh_token = create_refresh_token(data={"sub": user.id, "tenant_id": user.tenant_id})
        
        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer",
            "expires_in": 7200,
            "user": {
                "id": user.id,
                "username": user.username,
                "email": user.email,
                "role": user.role,
                "tenant_id": user.tenant_id
            }
        }
    
    def update_last_login(self, user_id: int, ip: str):
        self.db.query(User).filter(User.id == user_id).update({
            "last_login_at": datetime.utcnow(),
            "last_login_ip": ip
        })
        self.db.commit()
