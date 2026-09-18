"""
检测路由
"""
import time
from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.orm import Session

from api.core.database import get_db
from api.core.security import get_current_user
from api.core.responses import success_response, error_response, paginated_response
from api.models.schemas import (
    DetectionRequest, DetectionResponse, BatchDetectionRequest,
    BatchDetectionResponse, RecordQueryParams, RecordDetail
)
from api.services.detection_service import DetectionService
from api.services.tenant_service import TenantService
from api.services.kafka_service import kafka_service

router = APIRouter(prefix="/detect", tags=["Detect"])


@router.post("/single", response_model=DetectionResponse)
async def detect_single(
    request: Request,
    detection_request: DetectionRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    tenant_service = TenantService(db)
    quota_check = tenant_service.check_quota(current_user["tenant_id"])
    
    if not quota_check["valid"]:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=quota_check["reason"]
        )
    
    detection_service = DetectionService(db, current_user["tenant_id"])
    
    result = detection_service.detect_single(detection_request)
    
    return success_response(data=result)


@router.post("/batch", response_model=BatchDetectionResponse)
async def detect_batch(
    request: Request,
    batch_request: BatchDetectionRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    tenant_service = TenantService(db)
    quota_check = tenant_service.check_quota(current_user["tenant_id"])
    
    if not quota_check["valid"]:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=quota_check["reason"]
        )
    
    if len(batch_request.records) > 1000:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="批量检测最多支持1000条记录"
        )
    
    detection_service = DetectionService(db, current_user["tenant_id"])
    
    options = batch_request.options or {}
    enable_clustering = options.get("enable_clustering", True)
    
    result = detection_service.detect_batch(
        batch_request.records,
        enable_clustering=enable_clustering
    )
    
    return success_response(data=result)


@router.post("/stream")
async def detect_stream(
    request: Request,
    detection_request: DetectionRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    tenant_service = TenantService(db)
    quota_check = tenant_service.check_quota(current_user["tenant_id"])
    
    if not quota_check["valid"]:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=quota_check["reason"]
        )
    
    # 发送到Kafka进行实时处理
    success = kafka_service.send_detection_request(detection_request)
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Kafka服务不可用，请稍后重试"
        )
    
    return success_response(
        data={
            "message": "检测请求已提交到实时处理队列",
            "status": "processing",
            "timestamp": time.time()
        }
    )


@router.get("/result/{record_id}")
async def get_result(
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
        "record_id": record.record_id,
        "suspicion_score": float(record.suspicion_score),
        "risk_level": record.risk_level,
        "is_fake": record.is_fake,
        "scores": {
            "geo_score": float(record.geo_score),
            "text_score": float(record.text_score),
            "simhash_score": float(record.simhash_score),
            "semantic_score": float(record.semantic_score)
        },
        "reasons": record.reasons,
        "review_status": record.review_status,
        "created_at": record.created_at.isoformat()
    })


@router.get("/history")
async def get_history(
    page: int = 1,
    page_size: int = 20,
    start_date: str = None,
    end_date: str = None,
    risk_level: str = None,
    is_fake: bool = None,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    detection_service = DetectionService(db, current_user["tenant_id"])
    
    filters = {}
    if start_date:
        filters["start_date"] = start_date
    if end_date:
        filters["end_date"] = end_date
    if risk_level:
        filters["risk_level"] = risk_level
    if is_fake is not None:
        filters["is_fake"] = is_fake
    
    records, total = detection_service.get_records(page, page_size, filters)
    
    return paginated_response(
        data=[
            {
                "record_id": r.record_id,
                "device_id": r.device_id,
                "user_id": r.user_id,
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
