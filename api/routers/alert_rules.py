"""
告警规则管理路由
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from datetime import datetime

from api.core.database import get_db
from api.core.security import get_current_user
from api.core.responses import success_response
from api.models.db_models import AlertRule, AlertHistory
from api.models.schemas import AlertRuleCreate, AlertRuleUpdate, AlertRuleResponse

router = APIRouter(prefix="/alert-rules", tags=["AlertRules"])


@router.get("")
async def list_alert_rules(
    page: int = 1,
    page_size: int = 20,
    enabled: bool = None,
    alert_type: str = None,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """获取告警规则列表"""
    tenant_id = current_user["tenant_id"]
    
    query = db.query(AlertRule).filter(
        AlertRule.tenant_id == tenant_id
    )
    
    if enabled is not None:
        query = query.filter(AlertRule.enabled == enabled)
    if alert_type:
        query = query.filter(AlertRule.alert_type == alert_type)
    
    query = query.order_by(AlertRule.created_at.desc())
    
    total = query.count()
    rules = query.offset((page - 1) * page_size).limit(page_size).all()
    
    return success_response(data={
        "list": [
            {
                "id": r.id,
                "name": r.name,
                "description": r.description,
                "alert_type": r.alert_type,
                "severity": r.severity,
                "enabled": r.enabled,
                "cooldown_minutes": r.cooldown_minutes,
                "trigger_count": r.trigger_count,
                "last_triggered_at": r.last_triggered_at.isoformat() if r.last_triggered_at else None,
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "updated_at": r.updated_at.isoformat() if r.updated_at else None
            }
            for r in rules
        ],
        "total": total,
        "page": page,
        "page_size": page_size
    })


@router.post("")
async def create_alert_rule(
    rule_data: AlertRuleCreate,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """创建告警规则"""
    tenant_id = current_user["tenant_id"]
    
    new_rule = AlertRule(
        tenant_id=tenant_id,
        name=rule_data.name,
        description=rule_data.description,
        alert_type=rule_data.alert_type,
        condition_config=rule_data.condition_config,
        notification_config=rule_data.notification_config,
        severity=rule_data.severity,
        enabled=rule_data.enabled,
        cooldown_minutes=rule_data.cooldown_minutes,
        created_by=current_user["id"]
    )
    
    db.add(new_rule)
    db.commit()
    db.refresh(new_rule)
    
    return success_response(data={
        "id": new_rule.id,
        "name": new_rule.name,
        "alert_type": new_rule.alert_type
    }, message="告警规则创建成功")


@router.get("/{rule_id}")
async def get_alert_rule(
    rule_id: int,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """获取告警规则详情"""
    tenant_id = current_user["tenant_id"]
    
    rule = db.query(AlertRule).filter(
        AlertRule.id == rule_id,
        AlertRule.tenant_id == tenant_id
    ).first()
    
    if not rule:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="告警规则不存在"
        )
    
    return success_response(data={
        "id": rule.id,
        "name": rule.name,
        "description": rule.description,
        "alert_type": rule.alert_type,
        "condition_config": rule.condition_config,
        "notification_config": rule.notification_config,
        "severity": rule.severity,
        "enabled": rule.enabled,
        "cooldown_minutes": rule.cooldown_minutes,
        "trigger_count": rule.trigger_count,
        "last_triggered_at": rule.last_triggered_at.isoformat() if rule.last_triggered_at else None,
        "created_at": rule.created_at.isoformat() if rule.created_at else None,
        "updated_at": rule.updated_at.isoformat() if rule.updated_at else None
    })


@router.put("/{rule_id}")
async def update_alert_rule(
    rule_id: int,
    rule_data: AlertRuleUpdate,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """更新告警规则"""
    tenant_id = current_user["tenant_id"]
    
    rule = db.query(AlertRule).filter(
        AlertRule.id == rule_id,
        AlertRule.tenant_id == tenant_id
    ).first()
    
    if not rule:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="告警规则不存在"
        )
    
    if rule_data.name is not None:
        rule.name = rule_data.name
    if rule_data.description is not None:
        rule.description = rule_data.description
    if rule_data.condition_config is not None:
        rule.condition_config = rule_data.condition_config
    if rule_data.notification_config is not None:
        rule.notification_config = rule_data.notification_config
    if rule_data.severity is not None:
        rule.severity = rule_data.severity
    if rule_data.enabled is not None:
        rule.enabled = rule_data.enabled
    if rule_data.cooldown_minutes is not None:
        rule.cooldown_minutes = rule_data.cooldown_minutes
    
    rule.updated_by = current_user["id"]
    
    db.commit()
    db.refresh(rule)
    
    return success_response(message="告警规则更新成功")


@router.delete("/{rule_id}")
async def delete_alert_rule(
    rule_id: int,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """删除告警规则"""
    tenant_id = current_user["tenant_id"]
    
    rule = db.query(AlertRule).filter(
        AlertRule.id == rule_id,
        AlertRule.tenant_id == tenant_id
    ).first()
    
    if not rule:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="告警规则不存在"
        )
    
    db.delete(rule)
    db.commit()
    
    return success_response(message="告警规则删除成功")


@router.post("/{rule_id}/test")
async def test_alert_rule(
    rule_id: int,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """测试告警规则"""
    tenant_id = current_user["tenant_id"]
    
    rule = db.query(AlertRule).filter(
        AlertRule.id == rule_id,
        AlertRule.tenant_id == tenant_id
    ).first()
    
    if not rule:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="告警规则不存在"
        )
    
    # TODO: 实现告警规则测试逻辑
    # 这里可以根据 condition_config 模拟测试数据
    
    return success_response(data={
        "result": "success",
        "message": "告警规则测试通过（模拟）"
    })
