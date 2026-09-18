"""
API密钥服务
"""
import secrets
import hashlib
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta, timezone
from sqlalchemy.orm import Session
from sqlalchemy import and_

from api.models.db_models import ApiKey
from api.core.cache import CacheManager


class ApiKeyService:
    def __init__(self, db: Session):
        self.db = db
    
    def generate_api_key(self) -> tuple:
        raw_key = secrets.token_urlsafe(32)
        key_prefix = "gfd_" + raw_key[:8]
        key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
        return raw_key, key_prefix, key_hash
    
    def create(self, user_id: int, tenant_id: int, name: str,
               permissions: List[str] = None, ip_whitelist: List[str] = None,
               rate_limit: int = 1000, expire_days: int = 365) -> Dict[str, Any]:
        raw_key, key_prefix, key_hash = self.generate_api_key()
        
        api_key = ApiKey(
            tenant_id=tenant_id,
            user_id=user_id,
            key_hash=key_hash,
            key_prefix=key_prefix,
            name=name,
            permissions=permissions or [],
            ip_whitelist=ip_whitelist or [],
            rate_limit=rate_limit,
            status="active"
        )
        
        if expire_days:
            api_key.expire_at = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=expire_days)
        
        self.db.add(api_key)
        self.db.commit()
        self.db.refresh(api_key)
        
        return {
            "id": api_key.id,
            "name": api_key.name,
            "key_prefix": api_key.key_prefix,
            "api_key": raw_key,
            "permissions": api_key.permissions,
            "rate_limit": api_key.rate_limit,
            "expire_at": api_key.expire_at,
            "created_at": api_key.created_at
        }
    
    def verify(self, raw_key: str) -> Optional[Dict[str, Any]]:
        if not raw_key or not raw_key.startswith("gfd_"):
            return None
        
        key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
        key_prefix = raw_key[:12]
        
        api_key = self.db.query(ApiKey).filter(
            and_(
                ApiKey.key_prefix == key_prefix,
                ApiKey.key_hash == key_hash,
                ApiKey.status == "active"
            )
        ).first()
        
        if not api_key:
            return None
        
        if api_key.expire_at and api_key.expire_at < datetime.now(timezone.utc).replace(tzinfo=None):
            return None
        
        api_key.last_used_at = datetime.now(timezone.utc).replace(tzinfo=None)
        api_key.usage_count += 1
        self.db.commit()
        
        return {
            "id": api_key.id,
            "user_id": api_key.user_id,
            "tenant_id": api_key.tenant_id,
            "permissions": api_key.permissions,
            "rate_limit": api_key.rate_limit
        }
    
    def list_by_user(self, user_id: int) -> List[ApiKey]:
        return self.db.query(ApiKey).filter(ApiKey.user_id == user_id).all()
    
    def revoke(self, key_id: int, user_id: int) -> bool:
        api_key = self.db.query(ApiKey).filter(
            and_(ApiKey.id == key_id, ApiKey.user_id == user_id)
        ).first()
        
        if not api_key:
            return False
        
        api_key.status = "revoked"
        self.db.commit()
        return True
    
    def check_rate_limit(self, api_key_id: int, rate_limit: int) -> tuple:
        key = f"rate_limit:{api_key_id}"
        return CacheManager.check_rate_limit(key, rate_limit)
