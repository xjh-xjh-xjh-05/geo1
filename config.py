"""
AI驱动GEO虚假投喂检测系统 - 配置文件
"""
from dataclasses import dataclass, field
from typing import Dict, List
import os

@dataclass
class GeoConfig:
    """GEO规则配置"""
    # 中国境内经纬度范围
    latitude_min: float = 18.0      # 南端
    latitude_max: float = 54.0      # 北端
    longitude_min: float = 73.0     # 西端
    longitude_max: float = 135.0    # 东端

    # 速度阈值 (km/h)
    max_walking_speed: float = 8.0
    max_driving_speed: float = 120.0
    max_high_speed: float = 350.0   # 高铁

    # 瞬移检测阈值
    teleport_distance: float = 100.0  # km，超过此距离视为瞬移
    teleport_time: float = 60.0       # 秒，短时间内跨越大距离

    # 高频检测阈值
    max_reports_per_minute: int = 10  # 单设备每分钟最大上报次数
    max_reports_per_hour: int = 100   # 单设备每小时最大上报次数


@dataclass
class TextConfig:
    """文本规则配置"""
    # 关键词堆砌检测
    max_keyword_repeat: int = 3      # 单个关键词最大重复次数
    min_text_length: int = 5         # 最小文本长度
    max_text_length: int = 500       # 最大文本长度

    # 相似度阈值
    simhash_threshold: int = 3       # SimHash 汉明距离阈值（越小越严格）
    semantic_similarity_threshold: float = 0.85  # 语义相似度阈值
    
    # 是否启用 SentenceTransformer 本地模型。首次使用需要下载到 models/cache；
    # 无网络或加载失败时自动回退到字符频率向量。
    use_online_model: bool = field(
        default_factory=lambda: os.getenv("USE_SENTENCE_TRANSFORMER", "false").lower()
        in ("1", "true", "yes", "on")
    )

    # 关键词库（可扩展）
    suspicious_keywords: List[str] = None

    def __post_init__(self):
        if self.suspicious_keywords is None:
            self.suspicious_keywords = [
                "超级", "强烈推荐", "必去", "必买", "绝绝子",
                "yyds", "宝藏", "绝了", "太赞了", "太棒了"
            ]


@dataclass
class PreprocessingConfig:
    """预处理配置"""
    # 文本清洗配置
    min_text_length: int = 5
    max_text_length: int = 500
    remove_special_chars: bool = True
    preserve_chinese: bool = True
    preserve_english: bool = True
    preserve_numbers: bool = True

    # 地址解析配置
    admin_division_file: str = "data/admin_divisions.json"
    address_confidence_threshold: float = 0.7
    fuzzy_matching_threshold: float = 0.8

    # 坐标验证配置
    coordinate_system: str = "wgs84"  # wgs84, gcj02, bd09
    china_boundary_check: bool = True
    water_area_buffer: float = 1.0  # 水域缓冲区（公里）
    forbidden_area_buffer: float = 0.5  # 禁区缓冲区（公里）
    precision_threshold: float = 0.00001  # 精度阈值

    # 批量处理配置
    batch_size: int = 1000
    max_batch_size: int = 10000
    parallel_processing: bool = True
    max_workers: int = 4


@dataclass
class ScorerConfig:
    """评分配置"""
    # 各维度权重
    geo_weight: float = 0.30
    text_rule_weight: float = 0.40  # 增加文本规则权重
    simhash_weight: float = 0.15
    semantic_weight: float = 0.15
    # 神经网络模型权重：仅当 data/models/fake_detection_model.pt 存在且
    # 加载成功时参与加权融合；模型不可用时自动置零（权重按比例重分配），
    # 行为与未引入该维度前完全一致。
    neural_weight: float = 0.15

    # 风险等级阈值（降低阈值使检测更敏感）
    low_risk_threshold: float = 20.0
    medium_risk_threshold: float = 35.0  # 降低阈值，提高灵敏度
    high_risk_threshold: float = 60.0

    # 动态权重配置
    batch_semantic_weight: float = 0.25  # 批量模式下的语义权重
    high_severity_threshold: float = 0.8  # 高严重度异常覆盖阈值
    marketing_only_fake_threshold: int = 5  # 仅营销词触发虚假的阈值
    confidence_distance_factor: float = 0.02  # 置信度距离因子

    # 单条模式下保留的最大历史记录数（防止长期运行内存无限增长）
    max_history_records: int = 10000

    # 多源结果融合的来源可靠性（可按各来源历史准确率调整）
    source_reliability: Dict[str, float] = field(default_factory=lambda: {
        "rules": 1.0,            # 规则引擎：阈值经过校准，可靠度最高
        "cross_validation": 0.8,  # 多平台交叉验证
        "ai_model": 0.7,          # AI模型预测
    })


@dataclass
class AppConfig:
    """应用配置"""
    app_name: str = "AI驱动GEO虚假投喂检测系统"
    version: str = "1.0.0"
    description: str = "检测商用地图平台上的虚假投喂内容"

    # 数据存储
    data_dir: str = "data"
    sample_dir: str = "data/sample"
    model_dir: str = "data/models"


# 全局配置实例
geo_config = GeoConfig()
text_config = TextConfig()
scorer_config = ScorerConfig()
preprocessing_config = PreprocessingConfig()
app_config = AppConfig()
