"""
神经网络模型检测模块
"""
import os
import sys
import json
import zlib
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass

import numpy as np

try:
    import torch
    import torch.nn as nn
    import torch.nn.functional as F
    from transformers import AutoTokenizer, AutoModel
    HAS_TORCH = True
except ImportError:
    HAS_TORCH = False
    torch = None
    nn = None
    F = None
    AutoTokenizer = None
    AutoModel = None

# 添加项目根目录到路径
sys.path.insert(0, '..')
from models import InputRecord, DetectionResult
from engine.geo_rules import GeoRuleEngine
from engine.text_rules import TextRuleEngine


@dataclass
class NeuralConfig:
    """神经网络配置"""
    model_name: str = "hfl/chinese-roberta-wwm-ext"
    max_length: int = 128
    batch_size: int = 16
    learning_rate: float = 2e-5
    num_epochs: int = 10
    hidden_dim: int = 256
    dropout_rate: float = 0.3
    use_cuda: bool = False  # Will be set in __post_init__ if torch is available

    def __post_init__(self):
        if HAS_TORCH and torch is not None:
            self.use_cuda = torch.cuda.is_available()


class FakeDetectionModel(nn.Module if HAS_TORCH else object):
    """虚假内容检测神经网络模型"""

    def __init__(self, config: NeuralConfig):
        if HAS_TORCH:
            super().__init__()
        self.config = config
        self.using_fallback = True  # 默认使用回退方案

        if HAS_TORCH:
            # 立即初始化基本结构，不阻塞启动
            self.device = torch.device('cuda' if config.use_cuda else 'cpu')

            # 简化的默认结构（用于回退方案）
            # 地理特征(10) + 文本特征(64) = 74
            self.fusion_layer = nn.Linear(74, config.hidden_dim)
            self.classifier = nn.Sequential(
                nn.Dropout(config.dropout_rate),
                nn.Linear(config.hidden_dim, config.hidden_dim // 2),
                nn.ReLU(),
                nn.Dropout(config.dropout_rate),
                nn.Linear(config.hidden_dim // 2, 2)  # 二分类：正常/虚假
            )

            self.to(self.device)
            print("[WARNING] 神经网络模型使用回退方案（离线模式）")
        else:
            self.device = 'cpu'
            print("[INFO] PyTorch未安装，神经网络模型不可用")

    def _encode_text(self, text: str) -> 'torch.Tensor':
        """字符级文本编码（无需预训练模型）"""
        if not HAS_TORCH:
            return None

        feature_size = 64
        features = torch.zeros(feature_size, device=self.device)

        if not text:
            return features

        for char in text:
            idx = ord(char) % feature_size
            features[idx] += 1

        # 归一化
        text_len = len(text)
        if text_len > 0:
            features = features / text_len

        return features

    def forward(self, texts: List[str], geo_features) -> 'torch.Tensor':
        """前向传播 - 融合文本和地理特征"""
        if not HAS_TORCH:
            raise RuntimeError("PyTorch未安装，无法执行前向传播")

        geo_features = geo_features.to(self.device)

        # 编码文本特征
        batch_text_features = []
        for text in texts:
            text_feat = self._encode_text(text)
            batch_text_features.append(text_feat)
        text_features = torch.stack(batch_text_features)

        # 融合特征
        combined = torch.cat([text_features, geo_features], dim=1)
        fused = F.relu(self.fusion_layer(combined))
        logits = self.classifier(fused)
        return logits

    def predict(self, texts: List[str], geo_features) -> Tuple[List[int], List[float]]:
        """预测"""
        if not HAS_TORCH:
            return [0] * len(texts), [0.0] * len(texts)
        self.eval()
        with torch.no_grad():
            logits = self.forward(texts, geo_features)
            probabilities = F.softmax(logits, dim=1)
            predictions = torch.argmax(probabilities, dim=1).cpu().tolist()
            scores = probabilities[:, 1].cpu().tolist()  # 虚假的概率
        return predictions, scores


class NeuralScorer:
    """基于神经网络的评分器"""
    
    def __init__(self, config: NeuralConfig = None):
        self.config = config or NeuralConfig()
        self.model = FakeDetectionModel(self.config)
        self.geo_engine = GeoRuleEngine()
        self.text_engine = TextRuleEngine()
        
        # 加载预训练模型
        self._load_model()
    
    def _load_model(self):
        """加载模型"""
        if not HAS_TORCH:
            # 无 torch 环境（如轻量服务测试 venv）：不尝试加载，直接走规则降级
            print("[INFO] PyTorch未安装，神经网络模型不可用")
            return
        model_path = os.path.join('data', 'models', 'fake_detection_model.pt')
        if os.path.exists(model_path):
            try:
                self.model.load_state_dict(torch.load(model_path, map_location=self.model.device))
                # 权重加载成功后才视为可用模型，否则继续走规则降级
                self.model.using_fallback = False
                print("[OK] 加载预训练模型成功")
            except Exception as e:
                print(f"[ERROR] 加载模型失败: {e}")
                print("[WARNING] 使用随机初始化模型")
        else:
            print("[WARNING] 未找到预训练模型，使用随机初始化模型")

    @property
    def is_trained(self) -> bool:
        """模型是否已加载有效权重（供 ModelManager 统一接口判断）"""
        return HAS_TORCH and not self.model.using_fallback

    def extract_geo_features(self, record: InputRecord,
                             geo_score: Optional[float] = None,
                             geo_anomalies: Optional[List] = None) -> List[float]:
        """提取地理特征

        Args:
            record: 输入记录
            geo_score: 预先计算的GEO异常分数（避免重复调用规则引擎）
            geo_anomalies: 预先计算的GEO异常列表
        """
        features = []

        # 基础坐标
        features.append(record.geo.latitude)
        features.append(record.geo.longitude)

        # 坐标范围归一化
        lat_norm = (record.geo.latitude - 35.0) / 20.0  # 中国纬度范围约18-54
        lon_norm = (record.geo.longitude - 104.0) / 30.0  # 中国经度范围约73-135
        features.append(lat_norm)
        features.append(lon_norm)

        # GEO异常检测（未预计算时才调用规则引擎）
        if geo_score is None or geo_anomalies is None:
            geo_score, geo_anomalies = self.geo_engine.analyze(record)
        features.append(geo_score / 100.0)
        features.append(len(geo_anomalies))

        # 设备ID哈希特征（使用CRC32保证跨进程稳定，Python内置hash每次启动随机化）
        device_hash = zlib.crc32(str(record.device_id).encode('utf-8')) % 100 / 100.0
        features.append(device_hash)

        # 时间特征
        hour = record.timestamp % 24
        features.append(hour / 24.0)

        # 补充特征
        features.extend([0.0] * (10 - len(features)))  # 确保特征维度一致

        return features

    def analyze(self, record: InputRecord) -> DetectionResult:
        """分析单条记录"""
        text = record.content.text

        reasons = []
        details = {}

        # 规则引擎只调用一次，结果同时用于特征提取和reasons生成
        geo_score, geo_anomalies = self.geo_engine.analyze(record)
        text_score, text_anomalies = self.text_engine.analyze(record)
        geo_features = self.extract_geo_features(
            record, geo_score=geo_score, geo_anomalies=geo_anomalies
        )

        # 尝试使用神经网络模型（仅有有效权重时可用）
        model_available = self.is_trained

        if model_available:
            try:
                geo_tensor = torch.tensor([geo_features], dtype=torch.float32)
                predictions, scores = self.model.predict([text], geo_tensor)

                is_fake = predictions[0] == 1
                suspicion_score = scores[0] * 100

                if geo_anomalies:
                    reasons.extend([f"[GEO] {a.description}" for a in geo_anomalies])
                if text_anomalies:
                    reasons.extend([f"[文本] {a.description}" for a in text_anomalies])
                if is_fake:
                    reasons.append(f"[AI] 模型预测为虚假内容 (置信度: {suspicion_score:.1f}%)")

                details = {
                    "neural_score": round(suspicion_score, 2),
                    "geo_score": round(geo_score, 2),
                    "text_score": round(text_score, 2),
                    "geo_anomalies": [a.anomaly_type for a in geo_anomalies],
                    "text_anomalies": [a.anomaly_type for a in text_anomalies],
                    "model_used": "neural"
                }
            except Exception:
                model_available = False

        if not model_available:
            # 降级为纯规则评分（权重取自统一配置，而不是硬编码）
            from config import scorer_config
            geo_w = scorer_config.geo_weight
            text_w = scorer_config.text_rule_weight
            weight_sum = geo_w + text_w
            geo_ratio = geo_w / weight_sum if weight_sum > 0 else 0.4
            suspicion_score = (geo_score * geo_ratio + text_score * (1 - geo_ratio))
            is_fake = suspicion_score >= scorer_config.medium_risk_threshold

            if geo_anomalies:
                reasons.extend([f"[GEO] {a.description}" for a in geo_anomalies])
            if text_anomalies:
                reasons.extend([f"[文本] {a.description}" for a in text_anomalies])
            if is_fake:
                reasons.append(f"[规则] 规则引擎判定为虚假内容 (评分: {suspicion_score:.1f})")

            details = {
                "neural_score": 0.0,
                "geo_score": round(geo_score, 2),
                "text_score": round(text_score, 2),
                "geo_anomalies": [a.anomaly_type for a in geo_anomalies],
                "text_anomalies": [a.anomaly_type for a in text_anomalies],
                "model_used": "rules_fallback"
            }
        
        # 风险等级
        if suspicion_score >= 70:
            risk_level = "high"
        elif suspicion_score >= 40:
            risk_level = "medium"
        else:
            risk_level = "low"
        
        return DetectionResult(
            record_id=record.record_id,
            suspicion_score=round(suspicion_score, 2),
            is_fake=is_fake,
            risk_level=risk_level,
            geo_score=round(geo_score, 2),
            text_score=round(text_score, 2),
            simhash_score=0.0,
            semantic_score=0.0,
            reasons=reasons,
            details=details,
            similar_records=0
        )
    
    def analyze_batch(self, records: List[InputRecord]) -> List[DetectionResult]:
        """批量分析"""
        results = []
        for record in records:
            result = self.analyze(record)
            results.append(result)
        return results


# 示例用法
if __name__ == "__main__":
    from models import InputRecord, ContentData, GeoData
    
    # 创建测试记录
    test_record = InputRecord(
        record_id="test_1",
        device_id="device_1",
        timestamp=1234567890,
        content=ContentData(text="超级推荐这家网红餐厅，味道绝绝子，必去打卡！"),
        geo=GeoData(latitude=39.9042, longitude=116.4074),
        label="fake"
    )
    
    # 测试模型
    scorer = NeuralScorer()
    result = scorer.analyze(test_record)
    
    print(f"预测结果: {'虚假' if result.is_fake else '正常'}")
    print(f"置信度: {result.suspicion_score:.1f}%")
    print(f"风险等级: {result.risk_level}")
    print(f"检测理由: {result.reasons}")