"""
后台管理与系统配置模块
"""
import os
import json
import hashlib
import secrets
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
import uuid


class UserRole(str, Enum):
    ADMIN = "admin"
    OPERATOR = "operator"
    USER = "user"
    GUEST = "guest"


class SystemStatus(str, Enum):
    RUNNING = "running"
    MAINTENANCE = "maintenance"
    ERROR = "error"


@dataclass
class User:
    user_id: str
    username: str
    email: str
    password_hash: str
    role: UserRole
    is_active: bool = True
    created_at: str = ""
    last_login: str = ""
    login_count: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SystemConfig:
    config_key: str
    config_value: Any
    description: str
    category: str
    is_editable: bool = True
    updated_at: str = ""
    updated_by: str = ""


@dataclass
class AuditLog:
    log_id: str
    user_id: str
    action: str
    resource: str
    details: Dict[str, Any]
    ip_address: str
    timestamp: str
    status: str = "success"


class UserManager:
    """
    用户管理器
    """
    
    def __init__(self, storage_path: str = "data/users"):
        self.storage_path = storage_path
        self.users: Dict[str, User] = {}
        self.username_index: Dict[str, str] = {}
        self.email_index: Dict[str, str] = {}
        self.session_tokens: Dict[str, Dict[str, Any]] = {}
        
        os.makedirs(storage_path, exist_ok=True)
        self._load_users()
    
    def _load_users(self):
        """
        加载用户数据
        """
        filepath = os.path.join(self.storage_path, "users.json")
        if os.path.exists(filepath):
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    for item in data.get("users", []):
                        user = User(
                            user_id=item["user_id"],
                            username=item["username"],
                            email=item["email"],
                            password_hash=item["password_hash"],
                            role=UserRole(item["role"]),
                            is_active=item.get("is_active", True),
                            created_at=item.get("created_at", ""),
                            last_login=item.get("last_login", ""),
                            login_count=item.get("login_count", 0),
                            metadata=item.get("metadata", {})
                        )
                        self.users[user.user_id] = user
                        self.username_index[user.username] = user.user_id
                        self.email_index[user.email] = user.user_id
            except Exception as e:
                pass
        
        if not self.users:
            self._create_default_admin()
    
    def _create_default_admin(self):
        """
        创建默认管理员账户
        """
        admin_id = str(uuid.uuid4())
        password_hash = self._hash_password("admin123")
        
        admin = User(
            user_id=admin_id,
            username="admin",
            email="admin@geo-detection.local",
            password_hash=password_hash,
            role=UserRole.ADMIN,
            is_active=True,
            created_at=datetime.now().isoformat()
        )
        
        self.users[admin_id] = admin
        self.username_index["admin"] = admin_id
        self.email_index["admin@geo-detection.local"] = admin_id
        
        self._save_users()
    
    def _save_users(self):
        """
        保存用户数据
        """
        filepath = os.path.join(self.storage_path, "users.json")
        data = {
            "users": [
                {
                    "user_id": u.user_id,
                    "username": u.username,
                    "email": u.email,
                    "password_hash": u.password_hash,
                    "role": u.role.value,
                    "is_active": u.is_active,
                    "created_at": u.created_at,
                    "last_login": u.last_login,
                    "login_count": u.login_count,
                    "metadata": u.metadata
                }
                for u in self.users.values()
            ],
            "updated_at": datetime.now().isoformat()
        }
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    
    def _hash_password(self, password: str) -> str:
        """
        密码哈希
        """
        return hashlib.sha256(password.encode()).hexdigest()
    
    def create_user(
        self,
        username: str,
        email: str,
        password: str,
        role: UserRole = UserRole.USER
    ) -> Dict[str, Any]:
        """
        创建用户
        """
        if username in self.username_index:
            return {"error": "用户名已存在"}
        
        if email in self.email_index:
            return {"error": "邮箱已被注册"}
        
        user_id = str(uuid.uuid4())
        password_hash = self._hash_password(password)
        
        user = User(
            user_id=user_id,
            username=username,
            email=email,
            password_hash=password_hash,
            role=role,
            is_active=True,
            created_at=datetime.now().isoformat()
        )
        
        self.users[user_id] = user
        self.username_index[username] = user_id
        self.email_index[email] = user_id
        
        self._save_users()
        
        return {
            "user_id": user_id,
            "username": username,
            "email": email,
            "role": role.value
        }
    
    def authenticate(self, username: str, password: str) -> Optional[Dict[str, Any]]:
        """
        用户认证
        """
        if username not in self.username_index:
            return None
        
        user_id = self.username_index[username]
        user = self.users[user_id]
        
        if not user.is_active:
            return None
        
        password_hash = self._hash_password(password)
        if user.password_hash != password_hash:
            return None
        
        user.last_login = datetime.now().isoformat()
        user.login_count += 1
        self._save_users()
        
        token = secrets.token_urlsafe(32)
        self.session_tokens[token] = {
            "user_id": user_id,
            "created_at": datetime.now().isoformat(),
            "expires_at": (datetime.now() + timedelta(hours=24)).isoformat()
        }
        
        return {
            "user_id": user_id,
            "username": user.username,
            "email": user.email,
            "role": user.role.value,
            "token": token
        }
    
    def validate_token(self, token: str) -> Optional[Dict[str, Any]]:
        """
        验证会话令牌
        """
        if token not in self.session_tokens:
            return None
        
        session = self.session_tokens[token]
        expires_at = datetime.fromisoformat(session["expires_at"])
        
        if datetime.now() > expires_at:
            del self.session_tokens[token]
            return None
        
        user_id = session["user_id"]
        if user_id not in self.users:
            return None
        
        user = self.users[user_id]
        return {
            "user_id": user_id,
            "username": user.username,
            "role": user.role.value
        }
    
    def logout(self, token: str) -> bool:
        """
        用户登出
        """
        if token in self.session_tokens:
            del self.session_tokens[token]
            return True
        return False
    
    def get_user(self, user_id: str) -> Optional[Dict[str, Any]]:
        """
        获取用户信息
        """
        if user_id not in self.users:
            return None
        
        user = self.users[user_id]
        return {
            "user_id": user.user_id,
            "username": user.username,
            "email": user.email,
            "role": user.role.value,
            "is_active": user.is_active,
            "created_at": user.created_at,
            "last_login": user.last_login,
            "login_count": user.login_count
        }
    
    def update_user(self, user_id: str, updates: Dict[str, Any]) -> bool:
        """
        更新用户信息
        """
        if user_id not in self.users:
            return False
        
        user = self.users[user_id]
        
        if "email" in updates and updates["email"] != user.email:
            if updates["email"] in self.email_index:
                return False
            del self.email_index[user.email]
            user.email = updates["email"]
            self.email_index[user.email] = user_id
        
        if "role" in updates:
            user.role = UserRole(updates["role"])
        
        if "is_active" in updates:
            user.is_active = updates["is_active"]
        
        if "password" in updates:
            user.password_hash = self._hash_password(updates["password"])
        
        self._save_users()
        return True
    
    def delete_user(self, user_id: str) -> bool:
        """
        删除用户
        """
        if user_id not in self.users:
            return False
        
        user = self.users[user_id]
        
        del self.username_index[user.username]
        del self.email_index[user.email]
        del self.users[user_id]
        
        self._save_users()
        return True
    
    def list_users(
        self,
        role: Optional[UserRole] = None,
        is_active: Optional[bool] = None
    ) -> List[Dict[str, Any]]:
        """
        列出用户
        """
        users = list(self.users.values())
        
        if role:
            users = [u for u in users if u.role == role]
        if is_active is not None:
            users = [u for u in users if u.is_active == is_active]
        
        return [
            {
                "user_id": u.user_id,
                "username": u.username,
                "email": u.email,
                "role": u.role.value,
                "is_active": u.is_active,
                "created_at": u.created_at,
                "last_login": u.last_login
            }
            for u in users
        ]


class SystemConfigManager:
    """
    系统配置管理器
    """
    
    def __init__(self, storage_path: str = "data/config"):
        self.storage_path = storage_path
        self.configs: Dict[str, SystemConfig] = {}
        
        os.makedirs(storage_path, exist_ok=True)
        self._load_configs()
    
    def _load_configs(self):
        """
        加载配置
        """
        filepath = os.path.join(self.storage_path, "system_config.json")
        if os.path.exists(filepath):
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    for item in data.get("configs", []):
                        config = SystemConfig(
                            config_key=item["config_key"],
                            config_value=item["config_value"],
                            description=item.get("description", ""),
                            category=item.get("category", "general"),
                            is_editable=item.get("is_editable", True),
                            updated_at=item.get("updated_at", ""),
                            updated_by=item.get("updated_by", "")
                        )
                        self.configs[config.config_key] = config
            except Exception as e:
                pass
        
        if not self.configs:
            self._initialize_default_configs()
    
    def _initialize_default_configs(self):
        """
        初始化默认配置
        """
        default_configs = [
            SystemConfig(
                config_key="detection.confidence_threshold",
                config_value=0.7,
                description="检测置信度阈值",
                category="detection"
            ),
            SystemConfig(
                config_key="detection.coordinate_offset_threshold",
                config_value=500,
                description="坐标偏移阈值（米）",
                category="detection"
            ),
            SystemConfig(
                config_key="detection.marketing_keyword_threshold",
                config_value=0.3,
                description="营销词占比阈值",
                category="detection"
            ),
            SystemConfig(
                config_key="cross_validation.enabled_platforms",
                config_value=["amap", "baidu", "osm"],
                description="启用的交叉验证平台",
                category="cross_validation"
            ),
            SystemConfig(
                config_key="cross_validation.similarity_threshold",
                config_value=0.7,
                description="相似度阈值",
                category="cross_validation"
            ),
            SystemConfig(
                config_key="alert.fake_threshold",
                config_value=0.8,
                description="虚假数据预警阈值",
                category="alert"
            ),
            SystemConfig(
                config_key="alert.email_notification",
                config_value=False,
                description="是否启用邮件通知",
                category="alert"
            ),
            SystemConfig(
                config_key="system.max_batch_size",
                config_value=1000,
                description="批量检测最大数量",
                category="system"
            ),
            SystemConfig(
                config_key="system.log_retention_days",
                config_value=30,
                description="日志保留天数",
                category="system"
            ),
            SystemConfig(
                config_key="api.rate_limit_per_minute",
                config_value=60,
                description="API每分钟请求限制",
                category="api"
            ),
            SystemConfig(
                config_key="api.key_required",
                config_value=True,
                description="是否需要API Key",
                category="api"
            )
        ]
        
        for config in default_configs:
            config.updated_at = datetime.now().isoformat()
            self.configs[config.config_key] = config
        
        self._save_configs()
    
    def _save_configs(self):
        """
        保存配置
        """
        filepath = os.path.join(self.storage_path, "system_config.json")
        data = {
            "configs": [
                {
                    "config_key": c.config_key,
                    "config_value": c.config_value,
                    "description": c.description,
                    "category": c.category,
                    "is_editable": c.is_editable,
                    "updated_at": c.updated_at,
                    "updated_by": c.updated_by
                }
                for c in self.configs.values()
            ],
            "updated_at": datetime.now().isoformat()
        }
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    
    def get_config(self, key: str, default: Any = None) -> Any:
        """
        获取配置值
        """
        if key in self.configs:
            return self.configs[key].config_value
        return default
    
    def set_config(
        self,
        key: str,
        value: Any,
        updated_by: str = "system"
    ) -> bool:
        """
        设置配置值
        """
        if key not in self.configs:
            return False
        
        config = self.configs[key]
        if not config.is_editable:
            return False
        
        config.config_value = value
        config.updated_at = datetime.now().isoformat()
        config.updated_by = updated_by
        
        self._save_configs()
        return True
    
    def get_configs_by_category(self, category: str) -> List[Dict[str, Any]]:
        """
        按类别获取配置
        """
        return [
            {
                "key": c.config_key,
                "value": c.config_value,
                "description": c.description,
                "is_editable": c.is_editable,
                "updated_at": c.updated_at
            }
            for c in self.configs.values()
            if c.category == category
        ]
    
    def get_all_configs(self) -> Dict[str, List[Dict[str, Any]]]:
        """
        获取所有配置（按类别分组）
        """
        result = {}
        for config in self.configs.values():
            if config.category not in result:
                result[config.category] = []
            result[config.category].append({
                "key": config.config_key,
                "value": config.config_value,
                "description": config.description,
                "is_editable": config.is_editable
            })
        return result


class AuditLogger:
    """
    审计日志管理器
    """
    
    def __init__(self, storage_path: str = "data/audit"):
        self.storage_path = storage_path
        self.logs: List[AuditLog] = []
        self.max_memory_logs = 5000
        
        os.makedirs(storage_path, exist_ok=True)
    
    def log(
        self,
        user_id: str,
        action: str,
        resource: str,
        details: Dict[str, Any],
        ip_address: str = "unknown",
        status: str = "success"
    ) -> str:
        """
        记录审计日志
        """
        log_id = str(uuid.uuid4())
        
        log = AuditLog(
            log_id=log_id,
            user_id=user_id,
            action=action,
            resource=resource,
            details=details,
            ip_address=ip_address,
            timestamp=datetime.now().isoformat(),
            status=status
        )
        
        self.logs.append(log)
        
        if len(self.logs) > self.max_memory_logs:
            self._flush_to_disk()
        
        return log_id
    
    def _flush_to_disk(self):
        """
        刷新到磁盘
        """
        if not self.logs:
            return
        
        filename = f"audit_logs_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        filepath = os.path.join(self.storage_path, filename)
        
        data = {
            "logs": [
                {
                    "log_id": log.log_id,
                    "user_id": log.user_id,
                    "action": log.action,
                    "resource": log.resource,
                    "details": log.details,
                    "ip_address": log.ip_address,
                    "timestamp": log.timestamp,
                    "status": log.status
                }
                for log in self.logs
            ]
        }
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        self.logs = []
    
    def get_logs(
        self,
        user_id: Optional[str] = None,
        action: Optional[str] = None,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        获取审计日志
        """
        filtered = self.logs
        
        if user_id:
            filtered = [l for l in filtered if l.user_id == user_id]
        if action:
            filtered = [l for l in filtered if l.action == action]
        if start_time:
            filtered = [l for l in filtered if l.timestamp >= start_time]
        if end_time:
            filtered = [l for l in filtered if l.timestamp <= end_time]
        
        return [
            {
                "log_id": log.log_id,
                "user_id": log.user_id,
                "action": log.action,
                "resource": log.resource,
                "details": log.details,
                "ip_address": log.ip_address,
                "timestamp": log.timestamp,
                "status": log.status
            }
            for log in filtered[:limit]
        ]


class SystemMonitor:
    """
    系统监控器
    """
    
    def __init__(self):
        self.start_time = datetime.now()
        self.metrics: Dict[str, List[Dict[str, Any]]] = {
            "detection_count": [],
            "api_requests": [],
            "errors": []
        }
    
    def record_metric(self, metric_type: str, value: Any, metadata: Optional[Dict[str, Any]] = None):
        """
        记录指标
        """
        if metric_type not in self.metrics:
            self.metrics[metric_type] = []
        
        self.metrics[metric_type].append({
            "value": value,
            "timestamp": datetime.now().isoformat(),
            "metadata": metadata or {}
        })
        
        if len(self.metrics[metric_type]) > 10000:
            self.metrics[metric_type] = self.metrics[metric_type][-5000:]
    
    def get_system_status(self) -> Dict[str, Any]:
        """
        获取系统状态
        """
        uptime = datetime.now() - self.start_time
        
        return {
            "status": SystemStatus.RUNNING.value,
            "uptime_seconds": uptime.total_seconds(),
            "uptime_human": str(uptime).split('.')[0],
            "start_time": self.start_time.isoformat(),
            "metrics_summary": {
                metric: len(records) 
                for metric, records in self.metrics.items()
            }
        }
    
    def get_performance_metrics(self) -> Dict[str, Any]:
        """
        获取性能指标
        """
        try:
            import psutil
            
            return {
                "cpu_percent": psutil.cpu_percent(interval=1),
                "memory_percent": psutil.virtual_memory().percent,
                "disk_percent": psutil.disk_usage('/').percent if os.name != 'nt' else psutil.disk_usage('C:\\').percent,
                "available_memory_mb": psutil.virtual_memory().available / (1024 * 1024)
            }
        except ImportError:
            return {
                "cpu_percent": "N/A",
                "memory_percent": "N/A",
                "disk_percent": "N/A",
                "available_memory_mb": "N/A",
                "note": "psutil未安装，无法获取系统性能指标"
            }
    
    def get_detection_stats(self, hours: int = 24) -> Dict[str, Any]:
        """
        获取检测统计
        """
        detection_records = self.metrics.get("detection_count", [])
        
        cutoff = (datetime.now() - timedelta(hours=hours)).isoformat()
        recent_records = [
            r for r in detection_records
            if r["timestamp"] >= cutoff
        ]
        
        total = len(recent_records)
        
        return {
            "period_hours": hours,
            "total_detections": total,
            "average_per_hour": total / hours if hours > 0 else 0
        }


class BackendManagementModule:
    """
    后台管理模块主类
    """
    
    def __init__(self, data_path: str = "data"):
        self.user_manager = UserManager(os.path.join(data_path, "users"))
        self.config_manager = SystemConfigManager(os.path.join(data_path, "config"))
        self.audit_logger = AuditLogger(os.path.join(data_path, "audit"))
        self.system_monitor = SystemMonitor()
    
    def login(self, username: str, password: str, ip_address: str = "unknown") -> Dict[str, Any]:
        """
        用户登录
        """
        result = self.user_manager.authenticate(username, password)
        
        if result:
            self.audit_logger.log(
                user_id=result["user_id"],
                action="login",
                resource="auth",
                details={"method": "password"},
                ip_address=ip_address,
                status="success"
            )
        else:
            self.audit_logger.log(
                user_id="unknown",
                action="login_failed",
                resource="auth",
                details={"username": username},
                ip_address=ip_address,
                status="failed"
            )
        
        return result or {"error": "用户名或密码错误"}
    
    def logout(self, token: str, user_id: str, ip_address: str = "unknown") -> bool:
        """
        用户登出
        """
        result = self.user_manager.logout(token)
        
        self.audit_logger.log(
            user_id=user_id,
            action="logout",
            resource="auth",
            details={},
            ip_address=ip_address
        )
        
        return result
    
    def check_permission(self, user_id: str, action: str) -> bool:
        """
        检查用户权限
        """
        user_info = self.user_manager.get_user(user_id)
        if not user_info:
            return False
        
        role = UserRole(user_info["role"])
        
        admin_actions = [
            "user.create", "user.delete", "user.update_role",
            "config.update", "system.maintenance"
        ]
        
        operator_actions = [
            "detection.batch", "report.export",
            "sample.manage", "feature.manage"
        ]
        
        if role == UserRole.ADMIN:
            return True
        elif role == UserRole.OPERATOR:
            return action not in admin_actions
        elif role == UserRole.USER:
            return action not in admin_actions and action not in operator_actions
        else:
            return action == "detection.single"
    
    def get_dashboard_data(self) -> Dict[str, Any]:
        """
        获取仪表板数据
        """
        return {
            "system_status": self.system_monitor.get_system_status(),
            "performance": self.system_monitor.get_performance_metrics(),
            "detection_stats": self.system_monitor.get_detection_stats(),
            "user_count": len(self.user_manager.users),
            "config_categories": list(self.config_manager.get_all_configs().keys())
        }
