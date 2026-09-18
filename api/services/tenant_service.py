"""
租户服务
"""
from typing import Optional, Dict, Any
from datetime import datetime, timezone
from sqlalchemy.orm import Session

from api.models.db_models import Tenant
from api.core.cache import CacheManager


class TenantService:
    def __init__(self, db: Session):
        self.db = db
    
    def get_by_id(self, tenant_id: int) -> Optional[Tenant]:
        cached = CacheManager.get_cached_tenant(tenant_id)
        if cached:
            return Tenant(**cached)
        
        tenant = self.db.query(Tenant).filter(Tenant.id == tenant_id).first()
        if tenant:
            CacheManager.cache_tenant(tenant_id, {
                "id": tenant.id,
                "name": tenant.name,
                "code": tenant.code,
                "plan": tenant.plan,
                "quota_daily": tenant.quota_daily,
                "quota_monthly": tenant.quota_monthly,
                "status": tenant.status
            })
        return tenant
    
    def get_by_code(self, code: str) -> Optional[Tenant]:
        return self.db.query(Tenant).filter(Tenant.code == code).first()
    
    def create(self, name: str, code: str, plan: str = "basic", **kwargs) -> Tenant:
        tenant = Tenant(
            name=name,
            code=code,
            plan=plan,
            **kwargs
        )
        self.db.add(tenant)
        self.db.commit()
        self.db.refresh(tenant)
        return tenant
    
    def check_quota(self, tenant_id: int) -> Dict[str, Any]:
        tenant = self.get_by_id(tenant_id)
        if not tenant:
            return {"valid": False, "reason": "租户不存在"}
        
        if tenant.status != "active":
            return {"valid": False, "reason": "租户已禁用"}
        
        if tenant.expire_at and tenant.expire_at < datetime.now(timezone.utc).replace(tzinfo=None):
            return {"valid": False, "reason": "租户已过期"}
        
        today = datetime.now(timezone.utc).replace(tzinfo=None).strftime("%Y-%m-%d")
        daily_used, monthly_used = CacheManager.increment_quota(tenant_id, today)
        
        if daily_used > tenant.quota_daily:
            return {"valid": False, "reason": "日配额已用尽"}
        
        if monthly_used > tenant.quota_monthly:
            return {"valid": False, "reason": "月配额已用尽"}
        
        return {
            "valid": True,
            "daily_used": daily_used,
            "monthly_used": monthly_used,
            "daily_limit": tenant.quota_daily,
            "monthly_limit": tenant.quota_monthly
        }
