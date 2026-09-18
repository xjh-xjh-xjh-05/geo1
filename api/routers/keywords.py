"""
关键词管理路由
"""
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File
from sqlalchemy.orm import Session
from fastapi.responses import StreamingResponse
import csv
import io

from api.core.database import get_db
from api.core.security import get_current_user
from api.core.responses import success_response
from api.models.schemas import KeywordCreate, KeywordUpdate, KeywordResponse
from api.models.db_models import KeywordLibrary

router = APIRouter(prefix="/keywords", tags=["Keywords"])


@router.get("")
async def list_keywords(
    category: str = None,
    enabled: bool = None,
    keyword: str = None,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    query = db.query(KeywordLibrary).filter(
        KeywordLibrary.tenant_id == current_user["tenant_id"]
    )
    
    if category:
        query = query.filter(KeywordLibrary.category == category)
    if enabled is not None:
        query = query.filter(KeywordLibrary.enabled == enabled)
    if keyword:
        query = query.filter(KeywordLibrary.keyword.ilike(f"%{keyword}%"))
    
    keywords = query.order_by(KeywordLibrary.hit_count.desc()).all()
    
    return success_response(data=[
        {
            "id": k.id,
            "category": k.category,
            "keyword": k.keyword,
            "weight": float(k.weight),
            "risk_level": k.risk_level,
            "source": k.source,
            "hit_count": k.hit_count,
            "enabled": k.enabled,
            "created_at": k.created_at.isoformat()
        }
        for k in keywords
    ])


@router.post("")
async def create_keyword(
    keyword_data: KeywordCreate,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    existing = db.query(KeywordLibrary).filter(
        KeywordLibrary.tenant_id == current_user["tenant_id"],
        KeywordLibrary.category == keyword_data.category,
        KeywordLibrary.keyword == keyword_data.keyword
    ).first()
    
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="关键词已存在"
        )
    
    keyword = KeywordLibrary(
        tenant_id=current_user["tenant_id"],
        category=keyword_data.category,
        keyword=keyword_data.keyword,
        weight=keyword_data.weight,
        risk_level=keyword_data.risk_level,
        description=keyword_data.description,
        source="manual",
        created_by=current_user["id"]
    )
    
    db.add(keyword)
    db.commit()
    db.refresh(keyword)
    
    return success_response(data={
        "id": keyword.id,
        "category": keyword.category,
        "keyword": keyword.keyword,
        "weight": float(keyword.weight),
        "risk_level": keyword.risk_level,
        "created_at": keyword.created_at.isoformat()
    }, message="关键词添加成功")


@router.put("/{keyword_id}")
async def update_keyword(
    keyword_id: int,
    keyword_data: KeywordUpdate,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    keyword = db.query(KeywordLibrary).filter(
        KeywordLibrary.id == keyword_id,
        KeywordLibrary.tenant_id == current_user["tenant_id"]
    ).first()
    
    if not keyword:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="关键词不存在"
        )
    
    update_data = keyword_data.dict(exclude_unset=True)
    for key, value in update_data.items():
        setattr(keyword, key, value)
    
    db.commit()
    db.refresh(keyword)
    
    return success_response(data={
        "id": keyword.id,
        "category": keyword.category,
        "keyword": keyword.keyword,
        "weight": float(keyword.weight),
        "risk_level": keyword.risk_level,
        "enabled": keyword.enabled
    }, message="关键词更新成功")


@router.delete("/{keyword_id}")
async def delete_keyword(
    keyword_id: int,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    keyword = db.query(KeywordLibrary).filter(
        KeywordLibrary.id == keyword_id,
        KeywordLibrary.tenant_id == current_user["tenant_id"]
    ).first()
    
    if not keyword:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="关键词不存在"
        )
    
    db.delete(keyword)
    db.commit()
    
    return success_response(message="关键词删除成功")


@router.post("/import")
async def import_keywords(
    file: UploadFile = File(...),
    category: str = "suspicious",
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if not file.filename.endswith('.csv'):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="只支持CSV格式文件"
        )
    
    content = await file.read()
    decoded = content.decode('utf-8')
    reader = csv.DictReader(io.StringIO(decoded))
    
    imported_count = 0
    skipped_count = 0
    
    for row in reader:
        keyword_text = row.get('keyword', '').strip()
        if not keyword_text:
            continue
        
        existing = db.query(KeywordLibrary).filter(
            KeywordLibrary.tenant_id == current_user["tenant_id"],
            KeywordLibrary.category == category,
            KeywordLibrary.keyword == keyword_text
        ).first()
        
        if existing:
            skipped_count += 1
            continue
        
        keyword = KeywordLibrary(
            tenant_id=current_user["tenant_id"],
            category=category,
            keyword=keyword_text,
            weight=float(row.get('weight', 1.0)),
            risk_level=row.get('risk_level', 'medium'),
            source="import",
            created_by=current_user["id"]
        )
        
        db.add(keyword)
        imported_count += 1
    
    db.commit()
    
    return success_response(data={
        "imported_count": imported_count,
        "skipped_count": skipped_count
    }, message=f"导入完成: 成功{imported_count}条, 跳过{skipped_count}条")


@router.get("/export")
async def export_keywords(
    category: str = None,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    query = db.query(KeywordLibrary).filter(
        KeywordLibrary.tenant_id == current_user["tenant_id"]
    )
    
    if category:
        query = query.filter(KeywordLibrary.category == category)
    
    keywords = query.all()
    
    output = io.StringIO()
    writer = csv.writer(output)
    
    writer.writerow(['keyword', 'category', 'weight', 'risk_level', 'hit_count'])
    
    for k in keywords:
        writer.writerow([
            k.keyword,
            k.category,
            float(k.weight),
            k.risk_level,
            k.hit_count
        ])
    
    output.seek(0)
    
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={
            "Content-Disposition": "attachment; filename=keywords_export.csv"
        }
    )
