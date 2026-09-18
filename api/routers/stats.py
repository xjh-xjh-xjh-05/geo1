"""
统计报表路由
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func, and_
from datetime import datetime, timedelta, timezone

from api.core.database import get_db
from api.core.security import get_current_user
from api.core.responses import success_response
from api.models.db_models import DetectionRecord, StatisticsDaily, ApiLog

router = APIRouter(prefix="/stats", tags=["Stats"])


@router.get("/summary")
async def stats_summary(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """检测统计摘要（前端使用的路径）"""
    tenant_id = current_user["tenant_id"]
    
    # 今日统计
    today_start = datetime.now(timezone.utc).replace(tzinfo=None).replace(hour=0, minute=0, second=0, microsecond=0)
    today_records = db.query(DetectionRecord).filter(
        DetectionRecord.tenant_id == tenant_id,
        DetectionRecord.created_at >= today_start
    ).all()
    
    today_count = len(today_records)
    today_fake = sum(1 for r in today_records if r.is_fake)
    
    # 昨日统计
    yesterday_start = (datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    yesterday_end = today_start
    yesterday_records = db.query(DetectionRecord).filter(
        DetectionRecord.tenant_id == tenant_id,
        DetectionRecord.created_at >= yesterday_start,
        DetectionRecord.created_at < yesterday_end
    ).all()
    
    yesterday_count = len(yesterday_records)
    
    # 总计
    total_records = db.query(DetectionRecord).filter(
        DetectionRecord.tenant_id == tenant_id
    ).count()
    
    total_fake = db.query(DetectionRecord).filter(
        DetectionRecord.tenant_id == tenant_id,
        DetectionRecord.is_fake == True
    ).count()
    
    # 待审核
    pending_count = db.query(DetectionRecord).filter(
        DetectionRecord.tenant_id == tenant_id,
        DetectionRecord.review_status == "pending"
    ).count()
    
    return success_response(data={
        "today_count": today_count,
        "today_fake": today_fake,
        "today_delta": today_count - yesterday_count,
        "total_count": total_records,
        "total_fake": total_fake,
        "pending_count": pending_count,
        "fake_rate": round(today_fake / today_count, 4) if today_count > 0 else 0
    })


@router.get("/overview")
async def stats_overview(
    period: str = "today",
    start_date: str = None,
    end_date: str = None,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    tenant_id = current_user["tenant_id"]
    
    if period == "today":
        start = datetime.now(timezone.utc).replace(tzinfo=None).replace(hour=0, minute=0, second=0, microsecond=0)
        end = datetime.now(timezone.utc).replace(tzinfo=None)
    elif period == "yesterday":
        start = (datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        end = datetime.now(timezone.utc).replace(tzinfo=None).replace(hour=0, minute=0, second=0, microsecond=0)
    elif period == "week":
        start = (datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=7)).replace(hour=0, minute=0, second=0, microsecond=0)
        end = datetime.now(timezone.utc).replace(tzinfo=None)
    elif period == "month":
        start = (datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=30)).replace(hour=0, minute=0, second=0, microsecond=0)
        end = datetime.now(timezone.utc).replace(tzinfo=None)
    else:
        if start_date:
            start = datetime.fromisoformat(start_date)
        else:
            start = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=7)
        if end_date:
            end = datetime.fromisoformat(end_date)
        else:
            end = datetime.now(timezone.utc).replace(tzinfo=None)
    
    records = db.query(DetectionRecord).filter(
        DetectionRecord.tenant_id == tenant_id,
        DetectionRecord.created_at >= start,
        DetectionRecord.created_at <= end
    ).all()
    
    total_records = len(records)
    fake_records = sum(1 for r in records if r.is_fake)
    normal_records = total_records - fake_records
    fake_rate = fake_records / total_records if total_records > 0 else 0
    
    high_risk_count = sum(1 for r in records if r.risk_level == "high")
    medium_risk_count = sum(1 for r in records if r.risk_level == "medium")
    low_risk_count = sum(1 for r in records if r.risk_level == "low")
    
    avg_score = sum(float(r.suspicion_score) for r in records) / total_records if total_records > 0 else 0
    
    api_calls = db.query(ApiLog).filter(
        ApiLog.tenant_id == tenant_id,
        ApiLog.created_at >= start,
        ApiLog.created_at <= end
    ).count()
    
    pending_reviews = sum(1 for r in records if r.review_status == "pending")
    completed_reviews = sum(1 for r in records if r.review_status in ["approved", "rejected"])
    
    return success_response(data={
        "total_records": total_records,
        "fake_records": fake_records,
        "normal_records": normal_records,
        "fake_rate": round(fake_rate, 4),
        "high_risk_count": high_risk_count,
        "medium_risk_count": medium_risk_count,
        "low_risk_count": low_risk_count,
        "avg_suspicion_score": round(avg_score, 2),
        "api_calls": api_calls,
        "review_pending": pending_reviews,
        "review_completed": completed_reviews,
        "period": {
            "start": start.isoformat(),
            "end": end.isoformat()
        }
    })


@router.get("/trend")
async def stats_trend(
    metric: str = "total",
    granularity: str = "day",
    start_date: str = None,
    end_date: str = None,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    tenant_id = current_user["tenant_id"]
    
    if start_date:
        start = datetime.fromisoformat(start_date)
    else:
        start = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=7)
    
    if end_date:
        end = datetime.fromisoformat(end_date)
    else:
        end = datetime.now(timezone.utc).replace(tzinfo=None)
    
    if granularity == "hour":
        date_trunc = func.date_trunc('hour', DetectionRecord.created_at)
    elif granularity == "week":
        date_trunc = func.date_trunc('week', DetectionRecord.created_at)
    elif granularity == "month":
        date_trunc = func.date_trunc('month', DetectionRecord.created_at)
    else:
        date_trunc = func.date_trunc('day', DetectionRecord.created_at)
    
    query = db.query(
        date_trunc.label('time'),
        func.count(DetectionRecord.id).label('total'),
        func.sum(func.case((DetectionRecord.is_fake == True, 1), else_=0)).label('fake_count')
    ).filter(
        DetectionRecord.tenant_id == tenant_id,
        DetectionRecord.created_at >= start,
        DetectionRecord.created_at <= end
    ).group_by(date_trunc).order_by(date_trunc)
    
    results = query.all()
    
    data = []
    for r in results:
        if metric == "total":
            value = r.total
        elif metric == "fake_rate":
            value = r.fake_count / r.total if r.total > 0 else 0
        elif metric == "fake_count":
            value = r.fake_count
        else:
            value = r.total
        
        data.append({
            "time": r.time.isoformat() if r.time else None,
            "value": value
        })
    
    return success_response(data=data)


@router.get("/distribution")
async def stats_distribution(
    dimension: str = "risk_level",
    start_date: str = None,
    end_date: str = None,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    tenant_id = current_user["tenant_id"]
    
    if start_date:
        start = datetime.fromisoformat(start_date)
    else:
        start = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=30)
    
    if end_date:
        end = datetime.fromisoformat(end_date)
    else:
        end = datetime.now(timezone.utc).replace(tzinfo=None)
    
    query = db.query(DetectionRecord).filter(
        DetectionRecord.tenant_id == tenant_id,
        DetectionRecord.created_at >= start,
        DetectionRecord.created_at <= end
    )
    
    records = query.all()
    
    distribution = {}
    
    if dimension == "risk_level":
        for r in records:
            key = r.risk_level or "unknown"
            distribution[key] = distribution.get(key, 0) + 1
    elif dimension == "content_type":
        for r in records:
            key = r.content_type or "unknown"
            distribution[key] = distribution.get(key, 0) + 1
    elif dimension == "geo_source":
        for r in records:
            key = r.geo_source or "unknown"
            distribution[key] = distribution.get(key, 0) + 1
    elif dimension == "device":
        device_counts = {}
        for r in records:
            device_id = r.device_id or "unknown"
            device_counts[device_id] = device_counts.get(device_id, 0) + 1
        
        sorted_devices = sorted(device_counts.items(), key=lambda x: x[1], reverse=True)[:10]
        distribution = dict(sorted_devices)
    
    total = sum(distribution.values())
    data = [
        {
            "name": k,
            "count": v,
            "percentage": round(v / total, 4) if total > 0 else 0
        }
        for k, v in distribution.items()
    ]
    
    return success_response(data=data)


@router.get("/risk")
async def stats_risk(
    start_date: str = None,
    end_date: str = None,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    tenant_id = current_user["tenant_id"]
    
    if start_date:
        start = datetime.fromisoformat(start_date)
    else:
        start = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=30)
    
    if end_date:
        end = datetime.fromisoformat(end_date)
    else:
        end = datetime.now(timezone.utc).replace(tzinfo=None)
    
    records = db.query(DetectionRecord).filter(
        DetectionRecord.tenant_id == tenant_id,
        DetectionRecord.created_at >= start,
        DetectionRecord.created_at <= end
    ).all()
    
    risk_distribution = {
        "high": sum(1 for r in records if r.risk_level == "high"),
        "medium": sum(1 for r in records if r.risk_level == "medium"),
        "low": sum(1 for r in records if r.risk_level == "low")
    }
    
    device_fake_counts = {}
    for r in records:
        if r.is_fake and r.device_id:
            device_fake_counts[r.device_id] = device_fake_counts.get(r.device_id, 0) + 1
    
    top_risk_devices = sorted(device_fake_counts.items(), key=lambda x: x[1], reverse=True)[:10]
    
    user_fake_counts = {}
    for r in records:
        if r.is_fake and r.user_id:
            user_fake_counts[r.user_id] = user_fake_counts.get(r.user_id, 0) + 1
    
    top_risk_users = sorted(user_fake_counts.items(), key=lambda x: x[1], reverse=True)[:10]
    
    anomaly_types = {
        "geo_anomaly": sum(1 for r in records if float(r.geo_score) > 0),
        "text_anomaly": sum(1 for r in records if float(r.text_score) > 0),
        "duplicate": sum(1 for r in records if float(r.simhash_score) > 0),
        "cluster_anomaly": sum(1 for r in records if float(r.semantic_score) > 0)
    }
    
    return success_response(data={
        "risk_distribution": risk_distribution,
        "top_risk_devices": [
            {"device_id": d[0], "fake_count": d[1]}
            for d in top_risk_devices
        ],
        "top_risk_users": [
            {"user_id": u[0], "fake_count": u[1]}
            for u in top_risk_users
        ],
        "anomaly_types": anomaly_types
    })
