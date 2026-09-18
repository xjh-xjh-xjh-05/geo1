"""
AI模型管理API路由
"""
from fastapi import APIRouter, HTTPException, UploadFile, File, Query
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
import sys
import os
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from modules.ai_model import (
    AIDetectionModel, FeatureExtractor, ModelManager,
    create_sample_training_data
)

router = APIRouter(prefix="/ai", tags=["AI模型管理"])

model_manager = ModelManager()


class PredictionInput(BaseModel):
    """预测输入"""
    poi_data: Dict[str, Any] = Field(..., description="POI数据")
    context: Optional[Dict[str, Any]] = Field(None, description="上下文信息")


class BatchPredictionInput(BaseModel):
    """批量预测输入"""
    poi_list: List[Dict[str, Any]] = Field(..., description="POI列表")
    contexts: Optional[List[Dict[str, Any]]] = Field(None, description="上下文列表")


class TrainRequest(BaseModel):
    """训练请求"""
    model_type: Optional[str] = Field("random_forest", description="模型类型")
    n_samples: Optional[int] = Field(1000, description="样本数量")


class RegisterModelInput(BaseModel):
    """注册模型输入"""
    name: str = Field(..., description="模型名称")
    model_type: str = Field("random_forest", description="模型类型")


class RegisterNeuralModelInput(BaseModel):
    """神经网络模型注册输入"""
    name: str = Field(..., description="模型名称")
    model_path: Optional[str] = Field(None, description="预训练模型路径")


@router.get("/models", summary="获取模型列表")
async def list_models():
    """
    获取所有已注册的模型
    """
    models = model_manager.list_models()
    return {
        "success": True,
        "data": models
    }


@router.post("/models/register", summary="注册模型")
async def register_model(input_data: RegisterModelInput):
    """
    注册新模型
    """
    try:
        model = AIDetectionModel(model_type=input_data.model_type)
        model_manager.register_model(input_data.name, model)
        return {
            "success": True,
            "data": {
                "name": input_data.name,
                "model_type": input_data.model_type,
                "message": "模型注册成功"
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"模型注册失败: {str(e)}")


@router.post("/models/register-neural", summary="注册神经网络模型")
async def register_neural_model(input_data: RegisterNeuralModelInput):
    """注册神经网络模型"""
    try:
        from engine.neural_model import NeuralScorer, NeuralConfig
        scorer = NeuralScorer(NeuralConfig())
        
        if input_data.model_path and os.path.exists(input_data.model_path):
            try:
                import torch
                scorer.model.load_state_dict(torch.load(input_data.model_path, map_location=scorer.model.device))
                scorer.model.using_fallback = False
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"加载模型权重失败: {str(e)}")
        
        model_manager.register_neural_model(input_data.name, scorer)
        return {
            "success": True,
            "data": {
                "name": input_data.name,
                "model_type": "neural",
                "message": "神经网络模型注册成功"
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"神经网络模型注册失败: {str(e)}")


@router.post("/models/{name}/train", summary="训练模型")
async def train_model(name: str, request: TrainRequest):
    """训练模型"""
    try:
        model = model_manager.models.get(name)
        if not model:
            raise HTTPException(status_code=404, detail=f"模型不存在: {name}")
        
        model_type = model_manager.model_types.get(name, "sklearn")
        
        if model_type == "sklearn":
            X, y = create_sample_training_data(request.n_samples)
            metrics = model.train(X, y)
            return {
                "success": True,
                "data": {
                    "model_name": name,
                    "model_type": "sklearn",
                    "metrics": metrics
                }
            }
        elif model_type == "neural":
            # 神经网络模型训练需要调用训练脚本
            return {
                "success": True,
                "data": {
                    "model_name": name,
                    "model_type": "neural",
                    "message": "神经网络模型请使用 scripts/train_model.py 进行训练"
                }
            }
        else:
            raise HTTPException(status_code=400, detail=f"不支持的模型类型: {model_type}")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"模型训练失败: {str(e)}")


@router.post("/models/{name}/set-active", summary="设置活跃模型")
async def set_active_model(name: str):
    """
    设置当前使用的活跃模型
    """
    try:
        model_manager.set_active_model(name)
        return {
            "success": True,
            "data": {
                "active_model": name
            }
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"设置活跃模型失败: {str(e)}")


@router.post("/predict", summary="单条预测")
async def predict(input_data: PredictionInput):
    """使用AI模型进行单条预测"""
    result = model_manager.predict_with_active(input_data.poi_data, input_data.context)
    
    if result is None:
        raise HTTPException(status_code=400, detail="没有可用的活跃模型或模型未训练")
    
    return {
        "success": True,
        "data": result
    }


@router.post("/predict/batch", summary="批量预测")
async def predict_batch(input_data: BatchPredictionInput):
    """
    批量预测
    """
    model = model_manager.get_active_model()
    if not model:
        raise HTTPException(status_code=400, detail="没有可用的活跃模型")

    model_type = model_manager.get_active_model_type()

    try:
        if model_type == "neural":
            # 神经网络模型逐条走统一接口
            if not getattr(model, "is_trained", False):
                raise HTTPException(status_code=400, detail="神经网络模型未加载有效权重")
            from engine.neural_model import NeuralScorer
            results = []
            for poi in input_data.poi_list:
                result = model_manager.predict_with_active(poi)
                if result:
                    results.append(result)
            return {
                "success": True,
                "data": {
                    "total": len(results),
                    "results": [
                        {
                            "label": r["label"],
                            "confidence": r["confidence"],
                            "risk_factors": r["risk_factors"]
                        }
                        for r in results
                    ]
                }
            }

        if not getattr(model, "is_trained", False):
            raise HTTPException(status_code=400, detail="模型未训练")

        results = model.predict_batch(input_data.poi_list, input_data.contexts)
        return {
            "success": True,
            "data": {
                "total": len(results),
                "results": [
                    {
                        "label": r.label,
                        "confidence": r.confidence,
                        "risk_factors": r.risk_factors
                    }
                    for r in results
                ]
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"批量预测失败: {str(e)}")


class EvaluateRequest(BaseModel):
    """模型评估请求"""
    records: Optional[List[Dict[str, Any]]] = Field(
        None, description="带标注的测试数据列表（text/latitude/longitude/label）；"
                          "不传时使用 data/training_data.json"
    )
    max_records: int = Field(2000, description="最多评估的样本数")


@router.post("/models/{name}/evaluate", summary="评估模型")
async def evaluate_model(name: str, request: EvaluateRequest):
    """
    评估指定模型：输出准确率、精确率、召回率、F1、混淆矩阵。

    - name=rules 或 scorer: 评估规则引擎
    - 其他名称: 评估已注册的同名模型
    """
    from modules.ai_model.evaluation import (
        evaluate_rule_scorer, evaluate_neural_model, load_records,
        load_default_test_data,
    )

    records_items = request.records
    if not records_items:
        default_records = load_default_test_data(max_records=request.max_records)
        if not default_records:
            raise HTTPException(
                status_code=400,
                detail="未提供测试数据且 data/training_data.json 不存在，"
                       "请先运行 scripts/train_model.py 或在请求中传入 records"
            )
        records_items_count = len(default_records)
        records = default_records
    else:
        records = load_records(records_items)
        records_items_count = len(records)

    records = [r for r in records if r.label in ("normal", "fake")]
    if not records:
        raise HTTPException(status_code=400, detail="测试数据中没有带 label(normal/fake) 的样本")

    if name in ("rules", "scorer"):
        metrics = evaluate_rule_scorer(records)
    else:
        model = model_manager.models.get(name)
        if not model:
            raise HTTPException(status_code=404, detail=f"模型不存在: {name}")

        if model_manager.model_types.get(name) == "neural":
            # 神经网络模型使用已加载的权重
            metrics = evaluate_neural_model(records)
        else:
            # sklearn 模型逐条预测
            from modules.ai_model.evaluation import evaluate_predictor
            metrics = evaluate_predictor(
                records, lambda r: model.predict({
                    "name": r.content.text[:100],
                    "description": r.content.text,
                    "latitude": r.geo.latitude,
                    "longitude": r.geo.longitude,
                }).label == "fake"
            )

    return {
        "success": True,
        "data": {
            "model_name": name,
            "input_records": records_items_count,
            "evaluated_samples": metrics.get("sample_count", 0),
            "metrics": metrics
        }
    }


@router.post("/features/extract", summary="特征提取")
async def extract_features(poi_data: Dict[str, Any]):
    """
    从POI数据中提取特征
    """
    try:
        extractor = FeatureExtractor()
        features = extractor.extract_features(poi_data)
        return {
            "success": True,
            "data": {
                "spatial_density": features.spatial_density,
                "category_clustering": features.category_clustering,
                "coordinate_offset": features.coordinate_offset,
                "name_length": features.name_length,
                "address_completeness": features.address_completeness,
                "marketing_ratio": features.marketing_ratio,
                "upload_frequency": features.upload_frequency,
                "multi_platform_consistency": features.multi_platform_consistency,
                "authoritative_match": features.authoritative_match,
                "text_similarity": features.text_similarity
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"特征提取失败: {str(e)}")


@router.post("/models/{name}/save", summary="保存模型")
async def save_model(name: str):
    """
    保存模型到磁盘
    """
    try:
        filepath = model_manager.save_model(name)
        return {
            "success": True,
            "data": {
                "model_name": name,
                "filepath": filepath
            }
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"模型保存失败: {str(e)}")


@router.post("/models/{name}/load", summary="加载模型")
async def load_model(name: str, filepath: str = Query(..., description="模型文件路径")):
    """
    从磁盘加载模型
    """
    try:
        model_manager.load_model(name, filepath)
        return {
            "success": True,
            "data": {
                "model_name": name,
                "message": "模型加载成功"
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"模型加载失败: {str(e)}")
