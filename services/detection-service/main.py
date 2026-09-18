"""
检测服务 - 核心检测引擎
"""
from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
import time
import logging
from pydantic_settings import BaseSettings

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    """配置类"""
    APP_NAME: str = "Detection Service"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False
    
    # 数据库配置
    DATABASE_URL: str = "postgresql://postgres:postgres@db:5432/geo_fake_detection"
    DATABASE_POOL_SIZE: int = 20
    DATABASE_MAX_OVERFLOW: int = 10
    
    # 缓存配置
    REDIS_URL: str = "redis://redis:6379/0"
    
    # 认证配置
    SECRET_KEY: str = "your-secret-key-change-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 120
    
    # CORS
    CORS_ORIGINS: list = ["*"]
    
    class Config:
        env_file = ".env"
        case_sensitive = True
        extra = "ignore"


# 初始化配置
settings = Settings()

# 初始化数据库连接
from api.core.database import get_db, engine, Base

# 导入模型
from api.models.db_models import DetectionRecord
from api.models.schemas import (
    DetectionRequest, DetectionResponse, 
    BatchDetectionRequest, BatchDetectionResponse,
    DetectionResult
)

# 导入检测引擎
from engine.scorer import DetectionScorer
from engine.mock_data import MockDataGenerator

# 创建FastAPI应用
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="GEO虚假内容检测平台 - 检测服务"
)

# 配置CORS
from fastapi.middleware.cors import CORSMiddleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# 健康检查
@app.get("/health")
async def health_check():
    """健康检查"""
    from api.core.database import engine
    from sqlalchemy import text
    
    components = {}
    
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        components["database"] = "up"
    except Exception:
        components["database"] = "down"
    
    from api.core.cache import cache
    components["cache"] = "up" if cache.is_redis_available() else "up (memory fallback)"
    
    all_up = all("up" in v for v in components.values())
    
    return {
        "status": "healthy" if all_up else "unhealthy",
        "components": components,
        "timestamp": time.time()
    }


# 单条检测
@app.post("/api/v1/detect/single", response_model=DetectionResponse)
async def detect_single(
    request: DetectionRequest,
    db: Session = Depends(get_db)
):
    """单条检测"""
    try:
        start_time = time.time()
        
        # 初始化评分器
        scorer = DetectionScorer()
        
        # 执行检测
        result = scorer.analyze(
            text=request.content.text,
            latitude=request.location.latitude,
            longitude=request.location.longitude,
            device_id=request.device.device_id,
            user_id=request.device.user_id,
            timestamp=request.device.timestamp
        )
        
        processing_time = time.time() - start_time
        
        # 保存检测记录
        record = DetectionRecord(
            record_id=result.record_id,
            tenant_id=request.tenant_id or 1,
            device_id=request.device.device_id,
            user_id=request.device.user_id,
            session_id=request.device.session_id,
            timestamp=request.device.timestamp,
            latitude=request.location.latitude,
            longitude=request.location.longitude,
            accuracy=request.location.accuracy,
            geo_source=request.location.geo_source,
            content_text=request.content.text,
            content_type=request.content.content_type,
            content_hash=result.content_hash,
            ip_address=request.device.ip_address,
            app_version=request.device.app_version,
            user_agent=request.device.user_agent,
            platform=request.device.platform,
            suspicion_score=result.score,
            risk_level=result.risk_level,
            is_fake=result.is_fake,
            confidence=result.confidence,
            geo_score=result.geo_score,
            text_score=result.text_score,
            simhash_score=result.simhash_score,
            semantic_score=result.semantic_score,
            reasons=result.reasons,
            details=result.details,
            similar_record_ids=result.similar_record_ids,
            processing_time_ms=int(processing_time * 1000),
            model_version="1.0.0"
        )
        
        db.add(record)
        db.commit()
        db.refresh(record)
        
        # 构建响应
        response = DetectionResponse(
            record_id=result.record_id,
            score=result.score,
            risk_level=result.risk_level,
            is_fake=result.is_fake,
            confidence=result.confidence,
            reasons=result.reasons,
            details=result.details,
            processing_time_ms=int(processing_time * 1000),
            model_version="1.0.0"
        )
        
        logger.info(f"Single detection completed in {processing_time:.4f}s, score: {result.score}, is_fake: {result.is_fake}")
        
        return response
        
    except Exception as e:
        logger.error(f"Single detection failed: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"检测失败: {str(e)}"
        )


# 批量检测
@app.post("/api/v1/detect/batch", response_model=BatchDetectionResponse)
async def detect_batch(
    request: BatchDetectionRequest,
    db: Session = Depends(get_db)
):
    """批量检测"""
    try:
        start_time = time.time()
        
        # 初始化评分器
        scorer = DetectionScorer()
        
        # 准备检测数据
        records = []
        for item in request.items:
            record = {
                "text": item.content.text,
                "latitude": item.location.latitude,
                "longitude": item.location.longitude,
                "device_id": item.device.device_id,
                "user_id": item.device.user_id,
                "timestamp": item.device.timestamp
            }
            records.append(record)
        
        # 执行批量检测
        batch_result = scorer.analyze_batch(records)
        
        processing_time = time.time() - start_time
        
        # 保存检测记录
        results = []
        for item, result in zip(request.items, batch_result.results):
            record = DetectionRecord(
                record_id=result.record_id,
                tenant_id=request.tenant_id or 1,
                device_id=item.device.device_id,
                user_id=item.device.user_id,
                session_id=item.device.session_id,
                timestamp=item.device.timestamp,
                latitude=item.location.latitude,
                longitude=item.location.longitude,
                accuracy=item.location.accuracy,
                geo_source=item.location.geo_source,
                content_text=item.content.text,
                content_type=item.content.content_type,
                content_hash=result.content_hash,
                ip_address=item.device.ip_address,
                app_version=item.device.app_version,
                user_agent=item.device.user_agent,
                platform=item.device.platform,
                suspicion_score=result.score,
                risk_level=result.risk_level,
                is_fake=result.is_fake,
                confidence=result.confidence,
                geo_score=result.geo_score,
                text_score=result.text_score,
                simhash_score=result.simhash_score,
                semantic_score=result.semantic_score,
                reasons=result.reasons,
                details=result.details,
                similar_record_ids=result.similar_record_ids,
                processing_time_ms=int((processing_time / len(records)) * 1000),
                model_version="1.0.0"
            )
            
            db.add(record)
            
            # 构建响应结果
            results.append(DetectionResult(
                record_id=result.record_id,
                score=result.score,
                risk_level=result.risk_level,
                is_fake=result.is_fake,
                confidence=result.confidence,
                reasons=result.reasons,
                details=result.details
            ))
        
        db.commit()
        
        # 构建批量响应
        response = BatchDetectionResponse(
            total_count=len(results),
            fake_count=sum(1 for r in results if r.is_fake),
            normal_count=sum(1 for r in results if not r.is_fake),
            suspicious_count=sum(1 for r in results if r.risk_level in ["high", "medium"]),
            processing_time_ms=int(processing_time * 1000),
            results=results
        )
        
        logger.info(f"Batch detection completed in {processing_time:.4f}s, total: {len(results)}, fake: {response.fake_count}")
        
        return response
        
    except Exception as e:
        logger.error(f"Batch detection failed: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"批量检测失败: {str(e)}"
        )


# 模拟数据生成
@app.post("/api/v1/detect/generate")
async def generate_mock_data(
    normal_count: int = 50,
    fake_count: int = 50
):
    """生成模拟数据"""
    try:
        generator = MockDataGenerator(seed=42)
        records = generator.generate_batch(
            normal_count=normal_count,
            fake_count=fake_count
        )
        
        # 转换为响应格式
        results = []
        for record in records:
            results.append({
                "content": {
                    "text": record.text
                },
                "location": {
                    "latitude": record.latitude,
                    "longitude": record.longitude,
                    "accuracy": record.accuracy,
                    "geo_source": record.geo_source
                },
                "device": {
                    "device_id": record.device_id,
                    "user_id": record.user_id,
                    "session_id": record.session_id,
                    "timestamp": record.timestamp,
                    "ip_address": record.ip_address,
                    "app_version": record.app_version,
                    "user_agent": record.user_agent,
                    "platform": record.platform
                },
                "label": record.label
            })
        
        logger.info(f"Generated {len(results)} mock records: {normal_count} normal, {fake_count} fake")
        
        return {
            "total_count": len(results),
            "normal_count": normal_count,
            "fake_count": fake_count,
            "records": results
        }
        
    except Exception as e:
        logger.error(f"Generate mock data failed: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"生成模拟数据失败: {str(e)}"
        )


# 根路径
@app.get("/")
async def root():
    """根路径"""
    return {
        "message": "Detection Service",
        "version": settings.APP_VERSION,
        "endpoints": {
            "single_detection": "/api/v1/detect/single",
            "batch_detection": "/api/v1/detect/batch",
            "generate_data": "/api/v1/detect/generate"
        }
    }


# 启动事件
@app.on_event("startup")
async def startup_event():
    """启动事件"""
    logger.info(f"Starting Detection Service v{settings.APP_VERSION}")
    logger.info("Initializing detection engine...")
    
    # 预加载模型
    try:
        scorer = DetectionScorer()
        logger.info("Detection engine initialized successfully")
    except Exception as e:
        logger.warning(f"Failed to preload detection engine: {str(e)}")


# 关闭事件
@app.on_event("shutdown")
async def shutdown_event():
    """关闭事件"""
    logger.info("Detection Service shutdown")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.DEBUG
    )