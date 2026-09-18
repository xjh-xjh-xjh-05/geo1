"""
GEO虚假内容检测平台 - 核心模块
================================

模块一：用户交互与入口模块 - 由 app.py (Streamlit UI) 和 api/ 目录实现
模块二：数据预处理与标准化模块 - modules/preprocessing
模块三：基础规则引擎检测模块 - engine/ 目录
模块四：多源交叉核验模块 - modules/cross_validation
模块五：AI智能检测模型模块 - modules/ai_model
模块六：结果输出与预警模块 - modules/result_output
模块七：数据管理与特征库模块 - modules/data_management
模块八：后台管理与系统配置模块 - modules/backend_management
"""

from .preprocessing import (
    DataPreprocessor,
    PreprocessResult,
    StandardizedAddress,
    CoordinateTransformer
)

from .cross_validation import (
    MultiSourceValidator,
    AuthorityDataValidator,
    CrossValidationResult,
    PlatformMatch,
    validate_poi,
    validate_poi_async
)

from .ai_model import (
    FeatureExtractor,
    AIDetectionModel,
    ModelManager,
    FeatureVector,
    DetectionResult,
    create_sample_training_data
)

from .result_output import (
    ResultFormatter,
    AlertManager,
    ReportGenerator,
    ResultOutputModule,
    DetectionOutput,
    Alert,
    RiskLevel,
    AlertLevel
)

from .data_management import (
    FeatureLibrary,
    SampleDataset,
    DetectionLogger,
    DataManagementModule,
    FakeFeature,
    SampleData,
    DetectionLog,
    FeatureType,
    SampleLabel
)

from .backend_management import (
    UserManager,
    SystemConfigManager,
    AuditLogger,
    SystemMonitor,
    BackendManagementModule,
    User,
    SystemConfig,
    AuditLog,
    UserRole,
    SystemStatus
)


__all__ = [
    "DataPreprocessor",
    "PreprocessResult",
    "StandardizedAddress",
    "CoordinateTransformer",
    "MultiSourceValidator",
    "AuthorityDataValidator",
    "CrossValidationResult",
    "PlatformMatch",
    "validate_poi",
    "validate_poi_async",
    "FeatureExtractor",
    "AIDetectionModel",
    "ModelManager",
    "FeatureVector",
    "DetectionResult",
    "create_sample_training_data",
    "ResultFormatter",
    "AlertManager",
    "ReportGenerator",
    "ResultOutputModule",
    "DetectionOutput",
    "Alert",
    "RiskLevel",
    "AlertLevel",
    "FeatureLibrary",
    "SampleDataset",
    "DetectionLogger",
    "DataManagementModule",
    "FakeFeature",
    "SampleData",
    "DetectionLog",
    "FeatureType",
    "SampleLabel",
    "UserManager",
    "SystemConfigManager",
    "AuditLogger",
    "SystemMonitor",
    "BackendManagementModule",
    "User",
    "SystemConfig",
    "AuditLog",
    "UserRole",
    "SystemStatus"
]
