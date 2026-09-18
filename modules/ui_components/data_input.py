"""
数据输入组件
===========

提供多种数据输入方式，包括手动录入、Excel/CSV上传、地图选点等。
"""

import os
import json
import pandas as pd
from typing import Dict, Any, List, Optional, Tuple, Union
from dataclasses import dataclass, field
from datetime import datetime
import uuid


@dataclass
class POIInputData:
    """POI输入数据"""
    name: str
    address: str = ""
    latitude: float = 0.0
    longitude: float = 0.0
    category: str = ""
    description: str = ""
    phone: str = ""
    source: str = "manual"
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ValidationResult:
    """验证结果"""
    is_valid: bool
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    cleaned_data: Optional[Dict[str, Any]] = None


class DataInputManager:
    """
    数据输入管理器
    """

    def __init__(self):
        self.supported_formats = ['.csv', '.xlsx', '.xls', '.json']
        self.required_fields = ['name']
        self.optional_fields = [
            'address', 'latitude', 'longitude', 'category',
            'description', 'phone', 'source'
        ]

    def validate_poi_data(self, data: Dict[str, Any]) -> ValidationResult:
        """
        验证POI数据

        Args:
            data: POI数据

        Returns:
            验证结果
        """
        errors = []
        warnings = []
        cleaned_data = data.copy()

        # 检查必填字段
        for field_name in self.required_fields:
            if field_name not in data or not data[field_name]:
                errors.append(f"缺少必填字段: {field_name}")

        # 验证名称
        if 'name' in data:
            name = data['name']
            if len(name) > 100:
                warnings.append("名称过长，建议不超过100字符")
                cleaned_data['name'] = name[:100]
            if len(name) < 2:
                errors.append("名称过短，至少需要2个字符")

        # 验证坐标
        if 'latitude' in data and 'longitude' in data:
            lat = data['latitude']
            lon = data['longitude']

            if lat == 0 and lon == 0:
                warnings.append("坐标为(0,0)，可能未正确设置")
            elif not (-90 <= lat <= 90):
                errors.append(f"纬度超出范围: {lat}")
            elif not (-180 <= lon <= 180):
                errors.append(f"经度超出范围: {lon}")
            elif not (18 <= lat <= 54 and 73 <= lon <= 135):
                warnings.append("坐标不在中国范围内")

        # 验证地址
        if 'address' in data:
            address = data['address']
            if len(address) > 200:
                warnings.append("地址过长，建议不超过200字符")
                cleaned_data['address'] = address[:200]

        # 验证电话
        if 'phone' in data:
            phone = data['phone']
            if phone and not self._validate_phone(phone):
                warnings.append("电话格式可能不正确")

        is_valid = len(errors) == 0

        return ValidationResult(
            is_valid=is_valid,
            errors=errors,
            warnings=warnings,
            cleaned_data=cleaned_data if is_valid else None
        )

    def parse_csv_file(self, file_path: str) -> Tuple[List[Dict[str, Any]], List[str]]:
        """
        解析CSV文件

        Args:
            file_path: 文件路径

        Returns:
            (数据列表, 错误列表)
        """
        errors = []
        data_list = []

        try:
            df = pd.read_csv(file_path, encoding='utf-8')
            data_list = df.to_dict('records')
        except UnicodeDecodeError:
            try:
                df = pd.read_csv(file_path, encoding='gbk')
                data_list = df.to_dict('records')
            except Exception as e:
                errors.append(f"CSV文件解析失败: {str(e)}")
        except Exception as e:
            errors.append(f"CSV文件读取失败: {str(e)}")

        return data_list, errors

    def parse_excel_file(self, file_path: str) -> Tuple[List[Dict[str, Any]], List[str]]:
        """
        解析Excel文件

        Args:
            file_path: 文件路径

        Returns:
            (数据列表, 错误列表)
        """
        errors = []
        data_list = []

        try:
            df = pd.read_excel(file_path)
            data_list = df.to_dict('records')
        except Exception as e:
            errors.append(f"Excel文件解析失败: {str(e)}")

        return data_list, errors

    def parse_json_file(self, file_path: str) -> Tuple[List[Dict[str, Any]], List[str]]:
        """
        解析JSON文件

        Args:
            file_path: 文件路径

        Returns:
            (数据列表, 错误列表)
        """
        errors = []
        data_list = []

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            if isinstance(data, list):
                data_list = data
            elif isinstance(data, dict):
                if 'data' in data:
                    data_list = data['data'] if isinstance(data['data'], list) else [data['data']]
                else:
                    data_list = [data]
            else:
                errors.append("JSON格式不正确")
        except Exception as e:
            errors.append(f"JSON文件解析失败: {str(e)}")

        return data_list, errors

    def parse_uploaded_file(
        self,
        file_path: str,
        file_type: Optional[str] = None
    ) -> Tuple[List[Dict[str, Any]], List[str]]:
        """
        解析上传的文件

        Args:
            file_path: 文件路径
            file_type: 文件类型

        Returns:
            (数据列表, 错误列表)
        """
        if file_type is None:
            _, file_type = os.path.splitext(file_path)

        file_type = file_type.lower()

        if file_type == '.csv':
            return self.parse_csv_file(file_path)
        elif file_type in ['.xlsx', '.xls']:
            return self.parse_excel_file(file_path)
        elif file_type == '.json':
            return self.parse_json_file(file_path)
        else:
            return [], [f"不支持的文件格式: {file_type}"]

    def batch_validate(
        self,
        data_list: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        批量验证数据

        Args:
            data_list: 数据列表

        Returns:
            验证结果汇总
        """
        results = {
            "total": len(data_list),
            "valid": 0,
            "invalid": 0,
            "warnings": 0,
            "details": []
        }

        for i, data in enumerate(data_list):
            validation = self.validate_poi_data(data)

            detail = {
                "index": i,
                "name": data.get("name", "未知"),
                "is_valid": validation.is_valid,
                "errors": validation.errors,
                "warnings": validation.warnings
            }
            results["details"].append(detail)

            if validation.is_valid:
                results["valid"] += 1
            else:
                results["invalid"] += 1

            if validation.warnings:
                results["warnings"] += 1

        return results

    def prepare_for_detection(
        self,
        data_list: List[Dict[str, Any]]
    ) -> List[Any]:
        """
        准备检测数据

        Args:
            data_list: 原始数据列表

        Returns:
            InputRecord对象列表
        """
        import sys
        import os
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
        from models import InputRecord, GeoData, ContentData, Metadata

        prepared = []

        for data in data_list:
            record = InputRecord(
                record_id=data.get("id", str(uuid.uuid4())),
                device_id=data.get("device_id", f"D_{uuid.uuid4().hex[:8].upper()}"),
                user_id=data.get("user_id", f"U_{uuid.uuid4().hex[:8].upper()}"),
                timestamp=data.get("timestamp", int(datetime.now().timestamp())),
                geo=GeoData(
                    latitude=float(data.get("latitude", 0)),
                    longitude=float(data.get("longitude", 0))
                ),
                content=ContentData(
                    text=data.get("description", "") or data.get("text", "") or data.get("name", ""),
                    content_type=data.get("category", "poi")
                ),
                metadata=Metadata(),
                label=data.get("label")
            )
            prepared.append(record)

        return prepared

    def generate_sample_data(
        self,
        count: int = 10,
        include_fake: bool = True
    ) -> List[Dict[str, Any]]:
        """
        生成示例数据

        Args:
            count: 生成数量
            include_fake: 是否包含虚假数据

        Returns:
            示例数据列表
        """
        import random
        import time

        sample_pois = [
            {"name": "星巴克(三里屯店)", "address": "北京市朝阳区三里屯路19号", "category": "餐饮"},
            {"name": "麦当劳(国贸店)", "address": "北京市朝阳区建国门外大街1号", "category": "餐饮"},
            {"name": "肯德基(王府井店)", "address": "北京市东城区王府井大街138号", "category": "餐饮"},
            {"name": "全聚德(前门店)", "address": "北京市东城区前门大街30号", "category": "餐饮"},
            {"name": "海底捞(望京店)", "address": "北京市朝阳区望京西路甲50号", "category": "餐饮"},
        ]

        fake_pois = [
            {"name": "全网第一网红奶茶店", "address": "北京市朝阳区某某路123号", "category": "餐饮", "label": "fake"},
            {"name": "顶级spa会所", "address": "北京市海淀区某某街456号", "category": "休闲", "label": "fake"},
            {"name": "免费体验中心", "address": "北京市西城区某某巷789号", "category": "服务", "label": "fake"},
        ]

        data_list = []
        for i in range(count):
            if include_fake and i < 3:
                poi = random.choice(fake_pois)
                lat = 39.9 + random.uniform(-0.1, 0.1)
                lon = 116.4 + random.uniform(-0.1, 0.1)
                label = "fake"
            else:
                poi = random.choice(sample_pois)
                lat = 39.9 + random.uniform(-0.1, 0.1)
                lon = 116.4 + random.uniform(-0.1, 0.1)
                label = "normal"

            data_list.append({
                "id": str(uuid.uuid4()),
                "device_id": f"D_SAMPLE_{uuid.uuid4().hex[:8].upper()}",
                "user_id": f"U_SAMPLE_{uuid.uuid4().hex[:8].upper()}",
                "timestamp": int(time.time()) + i,
                "name": poi["name"],
                "address": poi["address"],
                "latitude": round(lat, 6),
                "longitude": round(lon, 6),
                "category": poi["category"],
                "description": f"这是{poi['name']}的描述信息",
                "text": f"这是{poi['name']}的描述信息",
                "phone": f"010-{random.randint(10000000, 99999999)}",
                "source": "sample",
                "label": label
            })

        return data_list

    def _validate_phone(self, phone: str) -> bool:
        """验证电话格式"""
        import re
        phone_pattern = r'^1[3-9]\d{9}$|^0\d{2,3}-?\d{7,8}$'
        return bool(re.match(phone_pattern, phone))


def get_input_form_fields() -> List[Dict[str, Any]]:
    """
    获取输入表单字段定义

    Returns:
        表单字段列表
    """
    return [
        {
            "name": "name",
            "label": "POI名称",
            "type": "text",
            "required": True,
            "placeholder": "请输入POI名称",
            "max_length": 100
        },
        {
            "name": "address",
            "label": "详细地址",
            "type": "text",
            "required": False,
            "placeholder": "请输入详细地址",
            "max_length": 200
        },
        {
            "name": "latitude",
            "label": "纬度",
            "type": "number",
            "required": False,
            "min": -90,
            "max": 90,
            "step": 0.000001
        },
        {
            "name": "longitude",
            "label": "经度",
            "type": "number",
            "required": False,
            "min": -180,
            "max": 180,
            "step": 0.000001
        },
        {
            "name": "category",
            "label": "分类",
            "type": "select",
            "required": False,
            "options": [
                {"value": "餐饮", "label": "餐饮"},
                {"value": "购物", "label": "购物"},
                {"value": "休闲", "label": "休闲"},
                {"value": "服务", "label": "服务"},
                {"value": "交通", "label": "交通"},
                {"value": "其他", "label": "其他"}
            ]
        },
        {
            "name": "description",
            "label": "描述",
            "type": "textarea",
            "required": False,
            "placeholder": "请输入POI描述",
            "max_length": 500
        },
        {
            "name": "phone",
            "label": "联系电话",
            "type": "tel",
            "required": False,
            "placeholder": "请输入联系电话"
        }
    ]
