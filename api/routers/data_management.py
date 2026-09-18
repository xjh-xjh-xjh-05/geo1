"""
数据管理与特征库API路由
"""
from fastapi import APIRouter, HTTPException, Query
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from modules.data_management import (
    FeatureLibrary, SampleDataset, DetectionLogger,
    DataManagementModule, FeatureType, SampleLabel
)

router = APIRouter(prefix="/data", tags=["数据管理"])

data_module = DataManagementModule()


class FeatureInput(BaseModel):
    """特征输入"""
    feature_type: str = Field(..., description="特征类型")
    name: str = Field(..., description="特征名称")
    description: str = Field(..., description="特征描述")
    patterns: List[str] = Field(..., description="匹配模式")
    weight: float = Field(0.5, description="权重")


class SampleInput(BaseModel):
    """样本输入"""
    poi_data: Dict[str, Any] = Field(..., description="POI数据")
    label: str = Field(..., description="标签: real/fake/suspicious")
    source: Optional[str] = Field("manual", description="来源")
    annotator: Optional[str] = Field("user", description="标注者")


class FeedbackInput(BaseModel):
    """反馈输入"""
    poi_data: Dict[str, Any] = Field(..., description="POI数据")
    user_label: str = Field(..., description="用户标签")
    feedback_type: str = Field("correction", description="反馈类型")


@router.get("/overview", summary="获取数据概览")
async def get_overview():
    """
    获取数据管理模块概览

    - 特征库统计
    - 样本统计
    - 日志统计
    """
    try:
        overview = data_module.get_overview()
        return {
            "success": True,
            "data": overview
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取概览失败: {str(e)}")


@router.get("/features", summary="获取特征列表")
async def list_features(
    feature_type: Optional[str] = Query(None, description="特征类型筛选"),
    active_only: bool = Query(True, description="仅显示活跃特征")
):
    """
    获取虚假信息特征库
    """
    try:
        if feature_type:
            ft = FeatureType(feature_type)
            features = data_module.feature_library.get_features_by_type(ft)
        else:
            features = data_module.feature_library.get_all_features(active_only)

        return {
            "success": True,
            "data": [
                {
                    "feature_id": f.feature_id,
                    "feature_type": f.feature_type.value,
                    "name": f.name,
                    "description": f.description,
                    "patterns": f.patterns,
                    "weight": f.weight,
                    "is_active": f.is_active,
                    "created_at": f.created_at
                }
                for f in features
            ]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取特征列表失败: {str(e)}")


@router.post("/features", summary="添加特征")
async def add_feature(input_data: FeatureInput):
    """
    添加新的虚假信息特征
    """
    try:
        from modules.data_management import FakeFeature
        import uuid
        from datetime import datetime

        feature = FakeFeature(
            feature_id=str(uuid.uuid4()),
            feature_type=FeatureType(input_data.feature_type),
            name=input_data.name,
            description=input_data.description,
            patterns=input_data.patterns,
            weight=input_data.weight,
            created_at=datetime.now().isoformat()
        )

        feature_id = data_module.feature_library.add_feature(feature)

        return {
            "success": True,
            "data": {
                "feature_id": feature_id,
                "message": "特征添加成功"
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"添加特征失败: {str(e)}")


@router.put("/features/{feature_id}", summary="更新特征")
async def update_feature(feature_id: str, updates: Dict[str, Any]):
    """
    更新特征信息
    """
    try:
        success = data_module.feature_library.update_feature(feature_id, updates)
        if not success:
            raise HTTPException(status_code=404, detail="特征不存在")

        return {
            "success": True,
            "data": {
                "feature_id": feature_id,
                "message": "特征更新成功"
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"更新特征失败: {str(e)}")


@router.delete("/features/{feature_id}", summary="删除特征")
async def delete_feature(feature_id: str):
    """
    删除特征
    """
    try:
        success = data_module.feature_library.delete_feature(feature_id)
        if not success:
            raise HTTPException(status_code=404, detail="特征不存在")

        return {
            "success": True,
            "data": {
                "feature_id": feature_id,
                "message": "特征删除成功"
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"删除特征失败: {str(e)}")


@router.post("/features/match", summary="匹配特征")
async def match_features(text: str = Query(..., description="待匹配文本")):
    """
    在文本中匹配虚假信息特征
    """
    try:
        matches = data_module.feature_library.match_patterns(text)
        return {
            "success": True,
            "data": {
                "match_count": len(matches),
                "matches": matches
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"特征匹配失败: {str(e)}")


@router.get("/samples", summary="获取样本列表")
async def list_samples(
    label: Optional[str] = Query(None, description="标签筛选")
):
    """
    获取样本数据集
    """
    try:
        if label:
            sl = SampleLabel(label)
            samples = data_module.sample_dataset.get_samples_by_label(sl)
        else:
            samples = list(data_module.sample_dataset.samples.values())

        return {
            "success": True,
            "data": [
                {
                    "sample_id": s.sample_id,
                    "poi_data": s.poi_data,
                    "label": s.label.value,
                    "source": s.source,
                    "annotator": s.annotator,
                    "created_at": s.created_at,
                    "verified": s.verified
                }
                for s in samples
            ]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取样本列表失败: {str(e)}")


@router.post("/samples", summary="添加样本")
async def add_sample(input_data: SampleInput):
    """
    添加标注样本
    """
    try:
        sample_id = data_module.sample_dataset.add_sample(
            poi_data=input_data.poi_data,
            label=SampleLabel(input_data.label),
            source=input_data.source,
            annotator=input_data.annotator
        )

        return {
            "success": True,
            "data": {
                "sample_id": sample_id,
                "message": "样本添加成功"
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"添加样本失败: {str(e)}")


@router.put("/samples/{sample_id}/label", summary="更新样本标签")
async def update_sample_label(sample_id: str, new_label: str = Query(..., description="新标签")):
    """
    更新样本标签
    """
    try:
        success = data_module.sample_dataset.update_sample_label(
            sample_id, SampleLabel(new_label)
        )
        if not success:
            raise HTTPException(status_code=404, detail="样本不存在")

        return {
            "success": True,
            "data": {
                "sample_id": sample_id,
                "new_label": new_label,
                "message": "标签更新成功"
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"更新标签失败: {str(e)}")


@router.get("/samples/statistics", summary="获取样本统计")
async def get_sample_statistics():
    """
    获取样本统计信息
    """
    try:
        stats = data_module.sample_dataset.get_statistics()
        return {
            "success": True,
            "data": stats
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取统计信息失败: {str(e)}")


@router.post("/feedback", summary="提交反馈")
async def submit_feedback(input_data: FeedbackInput):
    """
    提交用户反馈用于模型优化
    """
    try:
        result = data_module.add_feedback(
            poi_data=input_data.poi_data,
            user_label=input_data.user_label,
            feedback_type=input_data.feedback_type
        )

        return {
            "success": True,
            "data": result
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"提交反馈失败: {str(e)}")


@router.get("/logs", summary="获取检测日志")
async def list_logs(
    start_time: Optional[str] = Query(None, description="开始时间"),
    end_time: Optional[str] = Query(None, description="结束时间"),
    result: Optional[str] = Query(None, description="结果筛选"),
    limit: int = Query(100, description="返回数量")
):
    """
    获取检测日志
    """
    try:
        logs = data_module.detection_logger.get_logs(
            start_time=start_time,
            end_time=end_time,
            result=result,
            limit=limit
        )

        return {
            "success": True,
            "data": logs
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取日志失败: {str(e)}")


@router.get("/logs/statistics", summary="获取日志统计")
async def get_log_statistics(
    start_time: Optional[str] = Query(None, description="开始时间"),
    end_time: Optional[str] = Query(None, description="结束时间")
):
    """
    获取检测日志统计
    """
    try:
        stats = data_module.detection_logger.get_statistics(start_time, end_time)
        return {
            "success": True,
            "data": stats
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取日志统计失败: {str(e)}")


@router.post("/export/training-data", summary="导出训练数据")
async def export_training_data(filepath: str = Query(..., description="导出路径")):
    """
    导出训练数据
    """
    try:
        success = data_module.export_training_data(filepath)
        if not success:
            raise HTTPException(status_code=500, detail="导出失败")

        return {
            "success": True,
            "data": {
                "filepath": filepath,
                "message": "训练数据导出成功"
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"导出训练数据失败: {str(e)}")
