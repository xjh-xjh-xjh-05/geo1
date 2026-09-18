"""
记录管理路由
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from datetime import datetime

from api.core.database import get_db
from api.core.security import get_current_user
from api.core.responses import success_response, paginated_response
from api.models.schemas import LabelRequest, RecordDetail
from api.models.db_models import DetectionRecord, ReviewLog
from api.services.detection_service import DetectionService

router = APIRouter(prefix="/records", tags=["Records"])


@router.get("")
async def list_records(
    page: int = 1,
    page_size: int = 20,
    device_id: str = None,
    user_id: str = None,
    risk_level: str = None,
    review_status: str = None,
    start_date: datetime = None,
    end_date: datetime = None,
    keyword: str = None,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    detection_service = DetectionService(db, current_user["tenant_id"])
    
    filters = {
        "device_id": device_id,
        "user_id": user_id,
        "risk_level": risk_level,
        "review_status": review_status,
        "start_date": start_date,
        "end_date": end_date,
        "keyword": keyword
    }
    
    records, total = detection_service.get_records(page, page_size, filters)
    
    return paginated_response(
        data=[
            {
                "id": r.id,
                "record_id": r.record_id,
                "device_id": r.device_id,
                "user_id": r.user_id,
                "timestamp": r.timestamp,
                "latitude": float(r.latitude) if r.latitude else None,
                "longitude": float(r.longitude) if r.longitude else None,
                "content_text": r.content_text[:100] + "..." if len(r.content_text or "") > 100 else r.content_text,
                "content_type": r.content_type,
                "suspicion_score": float(r.suspicion_score),
                "risk_level": r.risk_level,
                "is_fake": r.is_fake,
                "review_status": r.review_status,
                "created_at": r.created_at.isoformat()
            }
            for r in records
        ],
        page=page,
        page_size=page_size,
        total=total
    )


@router.get("/{record_id}")
async def get_record(
    record_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    detection_service = DetectionService(db, current_user["tenant_id"])
    record = detection_service.get_record(record_id)
    
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
        "timestamp": record.timestamp,
        "latitude": float(record.latitude) if record.latitude else None,
        "longitude": float(record.longitude) if record.longitude else None,
        "accuracy": float(record.accuracy) if record.accuracy else None,
        "geo_source": record.geo_source,
        "content_text": record.content_text,
        "content_type": record.content_type,
        "ip_address": record.ip_address,
        "suspicion_score": float(record.suspicion_score),
        "risk_level": record.risk_level,
        "is_fake": record.is_fake,
        "geo_score": float(record.geo_score),
        "text_score": float(record.text_score),
        "simhash_score": float(record.simhash_score),
        "semantic_score": float(record.semantic_score),
        "reasons": record.reasons,
        "details": record.details,
        "review_status": record.review_status,
        "reviewer_id": record.reviewer_id,
        "review_comment": record.review_comment,
        "reviewed_at": record.reviewed_at.isoformat() if record.reviewed_at else None,
        "ground_truth": record.ground_truth,
        "created_at": record.created_at.isoformat()
    })


@router.put("/{record_id}/label")
async def label_record(
    record_id: str,
    label_data: LabelRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    detection_service = DetectionService(db, current_user["tenant_id"])
    record = detection_service.get_record(record_id)
    
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="记录不存在"
        )
    
    record.ground_truth = label_data.ground_truth
    record.feedback_type = label_data.feedback_type
    record.feedback_comment = label_data.feedback_comment
    
    review_log = ReviewLog(
        record_id=record.id,
        tenant_id=current_user["tenant_id"],
        reviewer_id=current_user["id"],
        action="label",
        new_ground_truth=label_data.ground_truth,
        comment=label_data.feedback_comment
    )
    
    db.add(review_log)
    db.commit()
    
    return success_response(message="标注成功")


@router.delete("/{record_id}")
async def delete_record(
    record_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if current_user.get("role") not in ["admin", "super_admin"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="权限不足"
        )
    
    detection_service = DetectionService(db, current_user["tenant_id"])
    record = detection_service.get_record(record_id)
    
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="记录不存在"
        )
    
    db.delete(record)
    db.commit()
    
    return success_response(message="删除成功")


@router.post("/export")
async def export_records(
    export_data: dict,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    from fastapi.responses import StreamingResponse
    import io
    import csv
    
    detection_service = DetectionService(db, current_user["tenant_id"])
    
    filters = export_data.get("filters", {})
    records, _ = detection_service.get_records(1, 10000, filters)
    
    output = io.StringIO()
    writer = csv.writer(output)
    
    headers = ["记录ID", "设备ID", "用户ID", "可疑分数", "风险等级", "是否虚假", "审核状态", "创建时间"]
    writer.writerow(headers)
    
    for r in records:
        writer.writerow([
            r.record_id,
            r.device_id,
            r.user_id,
            float(r.suspicion_score),
            r.risk_level,
            r.is_fake,
            r.review_status,
            r.created_at.isoformat()
        ])
    
    output.seek(0)
    
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={
            "Content-Disposition": f"attachment; filename=detection_records_{datetime.now().strftime('%Y%m%d')}.csv"
        }
    )
