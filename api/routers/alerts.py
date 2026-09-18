"""
告警管理路由
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from datetime import datetime

from api.core.database import get_db
from api.core.security import get_current_user
from api.core.responses import success_response, paginated_response
from api.models.schemas import (
    AlertRuleCreate, AlertRuleUpdate, AlertRuleResponse,
    AlertHistoryResponse, AlertAcknowledgeRequest, AlertResolveRequest
)
from api.models.db_models import AlertRule, AlertHistory

router = APIRouter(prefix="/alerts", tags=["Alerts"])


@router.get("")
async def list_alerts(
    page: int = 1,
    page_size: int = 20,
    status: str = None,
    level: str = None,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    query = db.query(AlertHistory).filter(
        AlertHistory.tenant_id == current_user["tenant_id"]
    )
    
    if status:
        query = query.filter(AlertHistory.status == status)
    if level:
        query = query.filter(AlertHistory.alert_level == level)
    
    query = query.order_by(AlertHistory.created_at.desc())
    
    total = query.count()
    alerts = query.offset((page - 1) * page_size).limit(page_size).all()
    
    return paginated_response(
        data=[
            {
                "id": a.id,
                "rule_id": a.rule_id,
                "alert_level": a.alert_level,
                "title": a.title,
                "message": a.message,
                "status": a.status,
                "notification_sent": a.notification_sent,
                "created_at": a.created_at.isoformat(),
                "acknowledged_at": a.acknowledged_at.isoformat() if a.acknowledged_at else None,
                "resolved_at": a.resolved_at.isoformat() if a.resolved_at else None
            }
            for a in alerts
        ],
        page=page,
        page_size=page_size,
        total=total
    )


@router.get("/rules")
async def list_alert_rules(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    rules = db.query(AlertRule).filter(
        AlertRule.tenant_id == current_user["tenant_id"]
    ).order_by(AlertRule.created_at.desc()).all()
    
    return success_response(data=[
        {
            "id": r.id,
            "name": r.name,
            "description": r.description,
            "alert_type": r.alert_type,
            "condition_config": r.condition_config,
            "notification_config": r.notification_config,
            "severity": r.severity,
            "enabled": r.enabled,
            "cooldown_minutes": r.cooldown_minutes,
            "last_triggered_at": r.last_triggered_at.isoformat() if r.last_triggered_at else None,
            "trigger_count": r.trigger_count,
            "created_at": r.created_at.isoformat()
        }
        for r in rules
    ])


@router.post("/rules")
async def create_alert_rule(
    rule_data: AlertRuleCreate,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if current_user.get("role") not in ["admin", "super_admin"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="权限不足"
        )
    
    rule = AlertRule(
        tenant_id=current_user["tenant_id"],
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
    
    db.add(rule)
    db.commit()
    db.refresh(rule)
    
    return success_response(data={
        "id": rule.id,
        "name": rule.name,
        "alert_type": rule.alert_type,
        "severity": rule.severity,
        "enabled": rule.enabled,
        "created_at": rule.created_at.isoformat()
    }, message="告警规则创建成功")


@router.put("/rules/{rule_id}")
async def update_alert_rule(
    rule_id: int,
    rule_data: AlertRuleUpdate,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if current_user.get("role") not in ["admin", "super_admin"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="权限不足"
        )
    
    rule = db.query(AlertRule).filter(
        AlertRule.id == rule_id,
        AlertRule.tenant_id == current_user["tenant_id"]
    ).first()
    
    if not rule:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="告警规则不存在"
        )
    
    update_data = rule_data.dict(exclude_unset=True)
    for key, value in update_data.items():
        setattr(rule, key, value)
    
    db.commit()
    db.refresh(rule)
    
    return success_response(data={
        "id": rule.id,
        "name": rule.name,
        "enabled": rule.enabled,
        "updated_at": rule.updated_at.isoformat()
    }, message="告警规则更新成功")


@router.delete("/rules/{rule_id}")
async def delete_alert_rule(
    rule_id: int,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if current_user.get("role") not in ["admin", "super_admin"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="权限不足"
        )
    
    rule = db.query(AlertRule).filter(
        AlertRule.id == rule_id,
        AlertRule.tenant_id == current_user["tenant_id"]
    ).first()
    
    if not rule:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="告警规则不存在"
        )
    
    db.delete(rule)
    db.commit()
    
    return success_response(message="告警规则删除成功")


@router.post("/{alert_id}/acknowledge")
async def acknowledge_alert(
    alert_id: int,
    ack_data: AlertAcknowledgeRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    alert = db.query(AlertHistory).filter(
        AlertHistory.id == alert_id,
        AlertHistory.tenant_id == current_user["tenant_id"]
    ).first()
    
    if not alert:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="告警不存在"
        )
    
    if alert.status != "pending":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="告警已被处理"
        )
    
    alert.status = "acknowledged"
    alert.acknowledged_by = current_user["id"]
    alert.acknowledged_at = datetime.utcnow()
    
    db.commit()
    
    return success_response(message="告警已确认")


@router.post("/{alert_id}/resolve")
async def resolve_alert(
    alert_id: int,
    resolve_data: AlertResolveRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    alert = db.query(AlertHistory).filter(
        AlertHistory.id == alert_id,
        AlertHistory.tenant_id == current_user["tenant_id"]
    ).first()
    
    if not alert:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="告警不存在"
        )
    
    if alert.status == "resolved":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="告警已解决"
        )
    
    alert.status = "resolved"
    alert.resolved_by = current_user["id"]
    alert.resolved_at = datetime.utcnow()
    alert.resolution_note = resolve_data.resolution
    
    db.commit()
    
    return success_response(message="告警已解决")
