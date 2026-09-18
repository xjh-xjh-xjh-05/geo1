"""
检测日志查询路由
"""
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from sqlalchemy import desc
from datetime import datetime, timedelta
from typing import Optional

from api.core.database import get_db
from api.core.security import get_current_user
from api.core.responses import success_response
from api.models.db_models import DetectionRecord

router = APIRouter(prefix="/logs", tags=["Logs"])


@router.get("")
async def get_detection_logs(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    risk_level: Optional[str] = None,
    is_fake: Optional[bool] = None,
    review_status: Optional[str] = None,
    device_id: Optional[str] = None,
    user_id: Optional[str] = None,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """获取检测日志列表"""
    tenant_id = current_user["tenant_id"]
    
    query = db.query(DetectionRecord).filter(
        DetectionRecord.tenant_id == tenant_id
    )
    
    if start_date:
        start = datetime.fromisoformat(start_date)
        query = query.filter(DetectionRecord.created_at >= start)
    
    if end_date:
        end = datetime.fromisoformat(end_date)
        query = query.filter(DetectionRecord.created_at <= end)
    
    if risk_level:
        query = query.filter(DetectionRecord.risk_level == risk_level)
    
    if is_fake is not None:
        query = query.filter(DetectionRecord.is_fake == is_fake)
    
    if review_status:
        query = query.filter(DetectionRecord.review_status == review_status)
    
    if device_id:
        query = query.filter(DetectionRecord.device_id == device_id)
    
    if user_id:
        query = query.filter(DetectionRecord.user_id == user_id)
    
    total = query.count()
    
    records = query.order_by(
        desc(DetectionRecord.created_at)
    ).offset((page - 1) * page_size).limit(page_size).all()
    
    return success_response(data={
        "list": [
            {
                "id": r.id,
                "record_id": r.record_id,
                "device_id": r.device_id,
                "user_id": r.user_id,
                "timestamp": r.timestamp,
                "latitude": float(r.latitude) if r.latitude else None,
                "longitude": float(r.longitude) if r.longitude else None,
                "accuracy": float(r.accuracy) if r.accuracy else None,
                "geo_source": r.geo_source,
                "content_text": r.content_text[:100] if r.content_text else None,
                "content_type": r.content_type,
                "ip_address": r.ip_address,
                "platform": r.platform,
                "suspicion_score": float(r.suspicion_score) if r.suspicion_score else 0,
                "risk_level": r.risk_level,
                "is_fake": r.is_fake,
                "confidence": float(r.confidence) if r.confidence else 0,
                "geo_score": float(r.geo_score) if r.geo_score else 0,
                "text_score": float(r.text_score) if r.text_score else 0,
                "simhash_score": float(r.simhash_score) if r.simhash_score else 0,
                "semantic_score": float(r.semantic_score) if r.semantic_score else 0,
                "reasons": r.reasons or [],
                "review_status": r.review_status,
                "ground_truth": r.ground_truth,
                "created_at": r.created_at.isoformat() if r.created_at else None
            }
            for r in records
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": (total + page_size - 1) // page_size if page_size > 0 else 0
    })


@router.get("/{record_id}")
async def get_detection_log_detail(
    record_id: int,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """获取检测日志详情"""
    tenant_id = current_user["tenant_id"]
    
    record = db.query(DetectionRecord).filter(
        DetectionRecord.id == record_id,
        DetectionRecord.tenant_id == tenant_id
    ).first()
    
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="记录不存在"
        )
    
    return success_response(data={
        "id": record.id,
        "record_id": record.record_id,
        "device_id": record.device_id,
        "user_id": record.user_id,
        "session_id": record.session_id,
        "timestamp": record.timestamp,
        "latitude": float(record.latitude) if record.latitude else None,
        "longitude": float(record.longitude) if record.longitude else None,
        "accuracy": float(record.accuracy) if record.accuracy else None,
        "geo_source": record.geo_source,
        "content_text": record.content_text,
        "content_type": record.content_type,
        "content_hash": record.content_hash,
        "ip_address": record.ip_address,
        "app_version": record.app_version,
        "user_agent": record.user_agent,
        "platform": record.platform,
        "suspicion_score": float(record.suspicion_score) if record.suspicion_score else 0,
        "risk_level": record.risk_level,
        "is_fake": record.is_fake,
        "confidence": float(record.confidence) if record.confidence else 0,
        "geo_score": float(record.geo_score) if record.geo_score else 0,
        "text_score": float(record.text_score) if record.text_score else 0,
        "simhash_score": float(record.simhash_score) if record.simhash_score else 0,
        "semantic_score": float(record.semantic_score) if record.semantic_score else 0,
        "reasons": record.reasons or [],
        "details": record.details or {},
        "similar_record_ids": record.similar_record_ids or [],
        "review_status": record.review_status,
        "reviewer_id": record.reviewer_id,
        "review_comment": record.review_comment,
        "reviewed_at": record.reviewed_at.isoformat() if record.reviewed_at else None,
        "ground_truth": record.ground_truth,
        "feedback_type": record.feedback_type,
        "feedback_comment": record.feedback_comment,
        "processing_time_ms": record.processing_time_ms,
        "model_version": record.model_version,
        "created_at": record.created_at.isoformat() if record.created_at else None,
        "updated_at": record.updated_at.isoformat() if record.updated_at else None
    })
