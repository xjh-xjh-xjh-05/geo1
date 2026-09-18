"""
数据预处理与交叉验证API路由
"""
from fastapi import APIRouter, HTTPException, Depends, Query
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from modules.preprocessing.data_preprocessor import DataPreprocessor
from modules.preprocessing.address_parser import AddressParser
from modules.preprocessing.coordinate_validator import CoordinateValidator, CoordinateSystem
from modules.cross_validation import MultiSourceValidator, validate_poi

router = APIRouter(prefix="/preprocessing", tags=["数据预处理"])


class POIInput(BaseModel):
    """POI输入数据"""
    name: str = Field(..., description="POI名称")
    address: Optional[str] = Field(None, description="地址")
    latitude: Optional[float] = Field(None, description="纬度")
    longitude: Optional[float] = Field(None, description="经度")
    text: Optional[str] = Field(None, description="文本内容")
    category: Optional[str] = Field(None, description="分类")
    coord_system: Optional[str] = Field("wgs84", description="坐标系统")


class AddressInput(BaseModel):
    """地址输入"""
    address: str = Field(..., description="地址文本")


class CoordinateInput(BaseModel):
    """坐标输入"""
    latitude: float = Field(..., description="纬度")
    longitude: float = Field(..., description="经度")
    coord_system: Optional[str] = Field("wgs84", description="坐标系统")


class BatchInput(BaseModel):
    """批量输入"""
    records: List[Dict[str, Any]] = Field(..., description="记录列表")


class TeleportInput(BaseModel):
    """瞬移检测输入"""
    coordinates: List[List[float]] = Field(..., description="坐标列表")
    timestamps: List[int] = Field(..., description="时间戳列表")


@router.post("/clean", summary="数据清洗")
async def clean_data(data: Dict[str, Any]):
    """
    清洗和去噪数据

    - 移除无效字符
    - 过滤敏感词
    - 检测营销词堆砌
    """
    try:
        preprocessor = DataPreprocessor()
        result = preprocessor.clean_and_denoise(data)
        return {
            "success": True,
            "data": {
                "is_valid": result.is_valid,
                "cleaned_text": result.cleaned_text,
                "removed_count": result.removed_count,
                "warnings": result.warnings
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"清洗失败: {str(e)}")


@router.post("/address/parse", summary="地址解析")
async def parse_address(input_data: AddressInput):
    """
    解析和标准化地址

    - 识别省市区
    - 提取街道和门牌号
    - 计算解析置信度
    """
    try:
        parser = AddressParser()
        result = parser.parse_address(input_data.address)
        return {
            "success": True,
            "data": {
                "raw_text": result.raw_text,
                "full_address": result.full_address,
                "confidence": result.confidence,
                "is_complete": result.is_complete,
                "components": {
                    k: {"value": v.value, "confidence": v.confidence}
                    for k, v in result.components.items()
                },
                "warnings": result.warnings
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"地址解析失败: {str(e)}")


@router.post("/address/normalize", summary="地址标准化")
async def normalize_address(input_data: AddressInput):
    """
    标准化地址格式
    """
    try:
        parser = AddressParser()
        normalized = parser.normalize_address(input_data.address)
        return {
            "success": True,
            "data": {
                "original": input_data.address,
                "normalized": normalized
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"地址标准化失败: {str(e)}")


@router.post("/address/validate", summary="地址验证")
async def validate_address(input_data: AddressInput):
    """
    验证地址有效性
    """
    try:
        parser = AddressParser()
        is_valid = parser.is_valid_address(input_data.address)
        return {
            "success": True,
            "data": {
                "address": input_data.address,
                "is_valid": is_valid
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"地址验证失败: {str(e)}")


@router.post("/coordinate/validate", summary="坐标验证")
async def validate_coordinate(input_data: CoordinateInput):
    """
    验证坐标合法性

    - 检查坐标范围
    - 坐标系统转换
    - 边界检查
    """
    try:
        validator = CoordinateValidator()

        coord_system = CoordinateSystem(input_data.coord_system)
        result = validator.validate_coordinate(
            input_data.latitude,
            input_data.longitude,
            coord_system
        )

        return {
            "success": True,
            "data": {
                "is_valid": result.is_valid,
                "coordinate_type": result.coordinate_type.value,
                "warnings": result.warnings,
                "corrected_lat": result.corrected_lat,
                "corrected_lon": result.corrected_lon
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"坐标验证失败: {str(e)}")


@router.post("/coordinate/convert", summary="坐标转换")
async def convert_coordinate(
    lat: float = Query(..., description="纬度"),
    lon: float = Query(..., description="经度"),
    from_system: str = Query("wgs84", description="源坐标系统"),
    to_system: str = Query("gcj02", description="目标坐标系统")
):
    """
    坐标系统转换

    支持: WGS84, GCJ02, BD09
    """
    try:
        validator = CoordinateValidator()
        from_sys = CoordinateSystem(from_system)
        to_sys = CoordinateSystem(to_system)

        converted_lat, converted_lon = validator.convert_coordinates(
            lat, lon, from_sys, to_sys
        )

        return {
            "success": True,
            "data": {
                "original": {"lat": lat, "lon": lon, "system": from_system},
                "converted": {"lat": converted_lat, "lon": converted_lon, "system": to_system}
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"坐标转换失败: {str(e)}")


@router.post("/coordinate/teleport-detect", summary="瞬移检测")
async def detect_teleport(input_data: TeleportInput):
    """
    检测瞬移行为
    """
    try:
        if len(input_data.coordinates) != len(input_data.timestamps):
            raise HTTPException(status_code=400, detail="坐标和时间戳数量不匹配")

        coord_tuples = [(c[0], c[1]) for c in input_data.coordinates]
        validator = CoordinateValidator()
        teleports = validator.detect_teleport(coord_tuples, input_data.timestamps)

        return {
            "success": True,
            "data": {
                "teleport_count": len(teleports),
                "events": teleports
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"瞬移检测失败: {str(e)}")


@router.post("/batch/preprocess", summary="批量预处理")
async def batch_preprocess(input_data: BatchInput):
    """
    批量预处理数据

    - 清洗文本
    - 地址标准化
    - 坐标校验
    """
    try:
        preprocessor = DataPreprocessor()
        results = preprocessor.batch_preprocess(input_data.records)

        return {
            "success": True,
            "data": {
                "total": len(results),
                "processed": sum(1 for r in results if r.is_processed),
                "results": preprocessor.export_preprocessed_data(results, format='dict')
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"批量预处理失败: {str(e)}")


@router.post("/cross-validate", summary="多源交叉验证")
async def cross_validate_poi(poi_data: Dict[str, Any]):
    """
    多源交叉验证POI数据

    - 查询高德地图
    - 查询百度地图
    - 查询OpenStreetMap
    - 检查数据一致性
    """
    try:
        result = await validate_poi_async(poi_data)
        return {
            "success": True,
            "data": {
                "is_valid": result.is_valid,
                "confidence": result.confidence,
                "risk_level": result.risk_level,
                "risk_reasons": result.risk_reasons,
                "recommendations": result.recommendations,
                "platform_matches": result.platform_matches
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"交叉验证失败: {str(e)}")


async def validate_poi_async(poi_data: Dict[str, Any]):
    """异步验证POI"""
    validator = MultiSourceValidator()
    return await validator.validate(poi_data)


@router.get("/coordinate/info", summary="获取坐标信息")
async def get_coordinate_info(
    lat: float = Query(..., description="纬度"),
    lon: float = Query(..., description="经度")
):
    """
    获取坐标详细信息
    """
    try:
        validator = CoordinateValidator()
        info = validator.get_coordinate_info(lat, lon)
        return {
            "success": True,
            "data": info
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取坐标信息失败: {str(e)}")
