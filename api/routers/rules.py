"""
规则管理路由
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from datetime import datetime

from api.core.database import get_db
from api.core.security import get_current_user
from api.core.responses import success_response
from api.models.schemas import (
    RuleConfigCreate, RuleConfigUpdate, RuleConfigResponse, RuleTestRequest, RuleTestResult
)
from api.models.db_models import RuleConfig

router = APIRouter(prefix="/rules", tags=["Rules"])


@router.get("")
async def list_rules(
    rule_type: str = None,
    enabled: bool = None,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    query = db.query(RuleConfig).filter(
        RuleConfig.tenant_id == current_user["tenant_id"]
    )
    
    if rule_type:
        query = query.filter(RuleConfig.rule_type == rule_type)
    if enabled is not None:
        query = query.filter(RuleConfig.enabled == enabled)
    
    rules = query.order_by(RuleConfig.priority.desc()).all()
    
    return success_response(data=[
        {
            "id": r.id,
            "rule_type": r.rule_type,
            "rule_name": r.rule_name,
            "rule_code": r.rule_code,
            "rule_config": r.rule_config,
            "description": r.description,
            "enabled": r.enabled,
            "priority": r.priority,
            "hit_count": r.hit_count,
            "last_hit_at": r.last_hit_at.isoformat() if r.last_hit_at else None,
            "created_at": r.created_at.isoformat()
        }
        for r in rules
    ])


@router.post("")
async def create_rule(
    rule_data: RuleConfigCreate,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if current_user.get("role") not in ["admin", "super_admin"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="权限不足"
        )
    
    existing = db.query(RuleConfig).filter(
        RuleConfig.tenant_id == current_user["tenant_id"],
        RuleConfig.rule_code == rule_data.rule_code
    ).first()
    
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="规则代码已存在"
        )
    
    rule = RuleConfig(
        tenant_id=current_user["tenant_id"],
        rule_type=rule_data.rule_type,
        rule_name=rule_data.rule_name,
        rule_code=rule_data.rule_code,
        rule_config=rule_data.rule_config,
        description=rule_data.description,
        enabled=rule_data.enabled,
        priority=rule_data.priority,
        created_by=current_user["id"]
    )
    
    db.add(rule)
    db.commit()
    db.refresh(rule)
    
    return success_response(data={
        "id": rule.id,
        "rule_type": rule.rule_type,
        "rule_name": rule.rule_name,
        "rule_code": rule.rule_code,
        "rule_config": rule.rule_config,
        "enabled": rule.enabled,
        "created_at": rule.created_at.isoformat()
    }, message="规则创建成功")


@router.get("/{rule_id}")
async def get_rule(
    rule_id: int,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    rule = db.query(RuleConfig).filter(
        RuleConfig.id == rule_id,
        RuleConfig.tenant_id == current_user["tenant_id"]
    ).first()
    
    if not rule:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="规则不存在"
        )
    
    return success_response(data={
        "id": rule.id,
        "rule_type": rule.rule_type,
        "rule_name": rule.rule_name,
        "rule_code": rule.rule_code,
        "rule_config": rule.rule_config,
        "description": rule.description,
        "enabled": rule.enabled,
        "priority": rule.priority,
        "hit_count": rule.hit_count,
        "last_hit_at": rule.last_hit_at.isoformat() if rule.last_hit_at else None,
        "created_at": rule.created_at.isoformat()
    })


@router.put("/{rule_id}")
async def update_rule(
    rule_id: int,
    rule_data: RuleConfigUpdate,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if current_user.get("role") not in ["admin", "super_admin"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="权限不足"
        )
    
    rule = db.query(RuleConfig).filter(
        RuleConfig.id == rule_id,
        RuleConfig.tenant_id == current_user["tenant_id"]
    ).first()
    
    if not rule:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="规则不存在"
        )
    
    update_data = rule_data.dict(exclude_unset=True)
    for key, value in update_data.items():
        setattr(rule, key, value)
    
    db.commit()
    db.refresh(rule)
    
    return success_response(data={
        "id": rule.id,
        "rule_type": rule.rule_type,
        "rule_name": rule.rule_name,
        "rule_config": rule.rule_config,
        "enabled": rule.enabled,
        "updated_at": rule.updated_at.isoformat()
    }, message="规则更新成功")


@router.delete("/{rule_id}")
async def delete_rule(
    rule_id: int,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if current_user.get("role") not in ["admin", "super_admin"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="权限不足"
        )
    
    rule = db.query(RuleConfig).filter(
        RuleConfig.id == rule_id,
        RuleConfig.tenant_id == current_user["tenant_id"]
    ).first()
    
    if not rule:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="规则不存在"
        )
    
    db.delete(rule)
    db.commit()
    
    return success_response(message="规则删除成功")


@router.post("/test")
async def test_rule(
    test_data: RuleTestRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    import sys
    import os
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    
    from models import InputRecord, GeoData, ContentData, Metadata
    from engine.geo_rules import GeoRuleEngine
    from engine.text_rules import TextRuleEngine
    
    hit_count = 0
    examples = []
    
    rule_type = test_data.rule.rule_type
    rule_config = test_data.rule.rule_config
    
    if rule_type == "geo":
        engine = GeoRuleEngine()
        # 支持试跑的GEO参数
        geo_param_types = {
            "teleport_distance": float,
            "teleport_time": float,
            "max_reports_per_minute": int,
            "max_reports_per_hour": int,
            "max_high_speed": float,
        }
        for key, cast in geo_param_types.items():
            if key in rule_config:
                try:
                    setattr(engine.config, key, cast(rule_config[key]))
                except (TypeError, ValueError):
                    pass
        
        for test_req in test_data.test_data:
            record = InputRecord(
                record_id="test",
                device_id=test_req.device_id,
                user_id=test_req.user_id,
                timestamp=test_req.timestamp,
                geo=GeoData(
                    latitude=test_req.geo.latitude,
                    longitude=test_req.geo.longitude
                ),
                content=ContentData(text=test_req.content.text),
                metadata=Metadata()
            )
            
            score, anomalies = engine.analyze(record)
            if score > 0:
                hit_count += 1
                if len(examples) < 5:
                    examples.append({
                        "record_id": record.record_id,
                        "score": score,
                        "anomalies": [a.anomaly_type for a in anomalies]
                    })
    
    elif rule_type == "text":
        engine = TextRuleEngine()
        # 支持试跑的文本参数
        text_param_types = {
            "min_text_length": int,
            "max_text_length": int,
            "max_keyword_repeat": int,
        }
        for key, cast in text_param_types.items():
            if key in rule_config:
                try:
                    setattr(engine.config, key, cast(rule_config[key]))
                except (TypeError, ValueError):
                    pass
        # 支持试跑自定义营销词库
        if isinstance(rule_config.get("suspicious_keywords"), list):
            engine.config.suspicious_keywords = [
                kw for kw in rule_config["suspicious_keywords"]
                if isinstance(kw, str) and kw
            ]
        
        for test_req in test_data.test_data:
            record = InputRecord(
                record_id="test",
                device_id=test_req.device_id,
                user_id=test_req.user_id,
                timestamp=test_req.timestamp,
                geo=GeoData(latitude=0, longitude=0),
                content=ContentData(text=test_req.content.text),
                metadata=Metadata()
            )
            
            score, anomalies = engine.analyze(record)
            if score > 0:
                hit_count += 1
                if len(examples) < 5:
                    examples.append({
                        "record_id": record.record_id,
                        "score": score,
                        "anomalies": [a.anomaly_type for a in anomalies]
                    })
    
    total_count = len(test_data.test_data)
    hit_rate = hit_count / total_count if total_count > 0 else 0
    
    return success_response(data={
        "hit_count": hit_count,
        "total_count": total_count,
        "hit_rate": round(hit_rate, 4),
        "examples": examples
    })
