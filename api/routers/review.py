"""
审核路由
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from datetime import datetime, timezone

from api.core.database import get_db
from api.core.security import get_current_user
from api.core.responses import success_response, paginated_response
from api.models.schemas import (
    ReviewApproveRequest, ReviewRejectRequest, ReviewEscalateRequest
)
from api.models.db_models import DetectionRecord, ReviewLog

router = APIRouter(prefix="/review", tags=["Review"])


@router.get("/pending")
async def list_pending(
    page: int = 1,
    page_size: int = 20,
    risk_level: str = None,
    priority: str = None,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    query = db.query(DetectionRecord).filter(
        DetectionRecord.tenant_id == current_user["tenant_id"],
        DetectionRecord.review_status == "pending"
    )
    
    if risk_level:
        query = query.filter(DetectionRecord.risk_level == risk_level)
    
    query = query.order_by(DetectionRecord.suspicion_score.desc())
    
    total = query.count()
    records = query.offset((page - 1) * page_size).limit(page_size).all()
    
    return paginated_response(
        data=[
            {
                "id": r.id,
                "record_id": r.record_id,
                "device_id": r.device_id,
                "user_id": r.user_id,
                "content_text": r.content_text[:200] if r.content_text else "",
                "suspicion_score": float(r.suspicion_score),
                "risk_level": r.risk_level,
                "reasons": r.reasons[:3],
                "created_at": r.created_at.isoformat()
            }
            for r in records
        ],
        page=page,
        page_size=page_size,
        total=total
    )


@router.post("/approve/{record_id}")
async def approve_record(
    record_id: str,
    approve_data: ReviewApproveRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    record = db.query(DetectionRecord).filter(
        DetectionRecord.record_id == record_id,
        DetectionRecord.tenant_id == current_user["tenant_id"]
    ).first()
    
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="记录不存在"
        )
    
    old_status = record.review_status
    
    record.review_status = "approved"
    record.reviewer_id = current_user["id"]
    record.review_comment = approve_data.comment
    record.reviewed_at = datetime.now(timezone.utc).replace(tzinfo=None)
    
    if approve_data.ground_truth is not None:
        record.ground_truth = approve_data.ground_truth
    
    review_log = ReviewLog(
        record_id=record.id,
        tenant_id=current_user["tenant_id"],
        reviewer_id=current_user["id"],
        action="approve",
        old_status=old_status,
        new_status="approved",
        new_ground_truth=approve_data.ground_truth,
        comment=approve_data.comment
    )
    
    db.add(review_log)
    db.commit()
    
    return success_response(message="审核通过")


@router.post("/reject/{record_id}")
async def reject_record(
    record_id: str,
    reject_data: ReviewRejectRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    record = db.query(DetectionRecord).filter(
        DetectionRecord.record_id == record_id,
        DetectionRecord.tenant_id == current_user["tenant_id"]
    ).first()
    
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="记录不存在"
        )
    
    old_status = record.review_status
    
    record.review_status = "rejected"
    record.reviewer_id = current_user["id"]
    record.review_comment = reject_data.reason
    record.reviewed_at = datetime.now(timezone.utc).replace(tzinfo=None)
    
    if reject_data.ground_truth is not None:
        record.ground_truth = reject_data.ground_truth
    
    review_log = ReviewLog(
        record_id=record.id,
        tenant_id=current_user["tenant_id"],
        reviewer_id=current_user["id"],
        action="reject",
        old_status=old_status,
        new_status="rejected",
        new_ground_truth=reject_data.ground_truth,
        comment=reject_data.reason
    )
    
    db.add(review_log)
    db.commit()
    
    return success_response(message="审核拒绝")


@router.post("/escalate/{record_id}")
async def escalate_record(
    record_id: str,
    escalate_data: ReviewEscalateRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    record = db.query(DetectionRecord).filter(
        DetectionRecord.record_id == record_id,
        DetectionRecord.tenant_id == current_user["tenant_id"]
    ).first()
    
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="记录不存在"
        )
    
    old_status = record.review_status
    
    record.review_status = "escalated"
    record.reviewer_id = current_user["id"]
    record.review_comment = escalate_data.reason
    
    review_log = ReviewLog(
        record_id=record.id,
        tenant_id=current_user["tenant_id"],
        reviewer_id=current_user["id"],
        action="escalate",
        old_status=old_status,
        new_status="escalated",
        comment=f"升级到: {escalate_data.escalate_to}, 原因: {escalate_data.reason}"
    )
    
    db.add(review_log)
    db.commit()
    
    return success_response(message="已升级处理")


@router.get("/history")
async def review_history(
    page: int = 1,
    page_size: int = 20,
    reviewer_id: int = None,
    action: str = None,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    query = db.query(ReviewLog).filter(
        ReviewLog.tenant_id == current_user["tenant_id"]
    )
    
    if reviewer_id:
        query = query.filter(ReviewLog.reviewer_id == reviewer_id)
    if action:
        query = query.filter(ReviewLog.action == action)
    
    query = query.order_by(ReviewLog.created_at.desc())
    
    total = query.count()
    logs = query.offset((page - 1) * page_size).limit(page_size).all()
    
    return paginated_response(
        data=[
            {
                "id": log.id,
                "record_id": log.record_id,
                "action": log.action,
                "old_status": log.old_status,
                "new_status": log.new_status,
                "comment": log.comment,
                "created_at": log.created_at.isoformat()
            }
            for log in logs
        ],
        page=page,
        page_size=page_size,
        total=total
    )
