"""
分布式处理配置管理系统

提供分层配置管理，支持默认配置、环境配置和用户配置的合并。
支持配置验证、热重载和版本控制。
"""

import os
import json
import yaml
from typing import Dict, Any, Optional, List
from pathlib import Path
from dataclasses import dataclass, field, asdict
import logging
from .models import QueueConfig, DEFAULT_QUEUE_CONFIGS

logger = logging.getLogger(__name__)


@dataclass
class ZeroMQConfig:
    """ZeroMQ 配置"""
    host: str = "localhost"
    base_port: int = 5555
    heartbeat_port: int = 5570
    control_port: int = 5571
    context_io_threads: int = 1
    socket_linger: int = 1000  # 毫秒
    socket_timeout: int = 5000  # 毫秒


@dataclass
class RedisConfig:
    """Redis 配置"""
    enabled: bool = True
    host: str = "localhost"
    port: int = 6379
    db: int = 0
    password: Optional[str] = None
    max_connections: int = 10
    socket_timeout: int = 5
    socket_connect_timeout: int = 5


@dataclass
class DatabaseConfig:
    """数据库配置"""
    type: str = "sqlite"  # sqlite, postgresql, mysql
    host: str = "localhost"
    port: int = 5432
    database: str = "lama_cleaner_distributed"
    username: Optional[str] = None
    password: Optional[str] = None
    sqlite_path: str = "data/distributed.db"
    pool_size: int = 5
    max_overflow: int = 10


@dataclass
class StorageConfig:
    """存储配置"""
    type: str = "local"  # local, s3, gcs
    base_path: str = "storage"
    temp_path: str = "temp"
    cache_path: str = "cache"
    
    # S3 配置
    s3_bucket: Optional[str] = None
    s3_region: Optional[str] = None
    s3_access_key: Optional[str] = None
    s3_secret_key: Optional[str] = None
    
    # 文件管理
    max_file_size: int = 100 * 1024 * 1024  # 100MB
    cleanup_interval: int = 3600  # 秒
    temp_file_ttl: int = 86400  # 24小时


@dataclass
class MonitoringConfig:
    """监控配置"""
    enabled: bool = True
    metrics_port: int = 8080
    log_level: str = "INFO"
    log_format: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    log_file: Optional[str] = "logs/distributed.log"
    log_max_size: int = 10 * 1024 * 1024  # 10MB
    log_backup_count: int = 5
    
    # 指标收集
    collect_system_metrics: bool = True
    collect_queue_metrics: bool = True
    collect_task_metrics: bool = True
    metrics_interval: int = 60  # 秒


@dataclass
class ServerlessConfig:
    """Serverless 配置"""
    enabled: bool = False
    provider: str = "aws"  # aws, gcp, azure
    
    # AWS Lambda 配置
    aws_region: str = "us-east-1"
    aws_access_key: Optional[str] = None
    aws_secret_key: Optional[str] = None
    lambda_function_name: str = "lama-cleaner-worker"
    lambda_timeout: int = 300  # 秒
    lambda_memory: int = 1024  # MB
    
    # 自动扩缩容
    auto_scaling: bool = True
    min_instances: int = 0
    max_instances: int = 10
    scale_up_threshold: int = 5  # 队列长度阈值
    scale_down_threshold: int = 1
    cooldown_period: int = 300  # 秒


@dataclass
class DistributedConfig:
    """分布式处理主配置"""
    # 基础配置
    enabled: bool = False
    scheduler_host: str = "localhost"
    scheduler_port: int = 8081
    
    # 组件配置
    zeromq: ZeroMQConfig = field(default_factory=ZeroMQConfig)
    redis: RedisConfig = field(default_factory=RedisConfig)
    database: DatabaseConfig = field(default_factory=DatabaseConfig)
    storage: StorageConfig = field(default_factory=StorageConfig)
    monitoring: MonitoringConfig = field(default_factory=MonitoringConfig)
    serverless: ServerlessConfig = field(default_factory=ServerlessConfig)
    
    # 队列配置
    queues: Dict[str, QueueConfig] = field(default_factory=lambda: DEFAULT_QUEUE_CONFIGS.copy())
    
    # 任务配置
    default_task_timeout: int = 300  # 秒
    max_task_retries: int = 3
    task_cleanup_interval: int = 3600  # 秒
    completed_task_ttl: int = 86400  # 24小时
    
    # 节点配置
    node_heartbeat_interval: int = 30  # 秒
    node_timeout: int = 90  # 秒
    max_concurrent_tasks_per_node: int = 4
    
    # 安全配置
    auth_enabled: bool = False
    auth_secret_key: Optional[str] = None
    allowed_hosts: List[str] = field(default_factory=lambda: ["localhost", "127.0.0.1"])
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'DistributedConfig':
        """从字典创建配置对象"""
        config = cls()
        
        # 基础配置
        config.enabled = data.get('enabled', False)
        config.scheduler_host = data.get('scheduler_host', 'localhost')
        config.scheduler_port = data.get('scheduler_port', 8081)
        
        # 组件配置
        if 'zeromq' in data:
            config.zeromq = ZeroMQConfig(**data['zeromq'])
        if 'redis' in data:
            config.redis = RedisConfig(**data['redis'])
        if 'database' in data:
            config.database = DatabaseConfig(**data['database'])
        if 'storage' in data:
            config.storage = StorageConfig(**data['storage'])
        if 'monitoring' in data:
            config.monitoring = MonitoringConfig(**data['monitoring'])
        if 'serverless' in data:
            config.serverless = ServerlessConfig(**data['serverless'])
        
        # 队列配置
        if 'queues' in data:
            config.queues = {
                name: QueueConfig.from_dict(queue_data)
                for name, queue_data in data['queues'].items()
            }
        
        # 其他配置
        config.default_task_timeout = data.get('default_task_timeout', 300)
        config.max_task_retries = data.get('max_task_retries', 3)
        config.task_cleanup_interval = data.get('task_cleanup_interval', 3600)
        config.completed_task_ttl = data.get('completed_task_ttl', 86400)
        config.node_heartbeat_interval = data.get('node_heartbeat_interval', 30)
        config.node_timeout = data.get('node_timeout', 90)
        config.max_concurrent_tasks_per_node = data.get('max_concurrent_tasks_per_node', 4)
        config.auth_enabled = data.get('auth_enabled', False)
        config.auth_secret_key = data.get('auth_secret_key')
        config.allowed_hosts = data.get('allowed_hosts', ['localhost', '127.0.0.1'])
        
        return config


class ConfigManager:
    """配置管理器"""
    
    def __init__(self, config_dir: str = "config"):
        self.config_dir = Path(config_dir)
        self.config_dir.mkdir(exist_ok=True)
        
        # 配置文件路径
        self.default_config_path = self.config_dir / "default.yaml"
        self.env_config_path = self.config_dir / "environment.yaml"
        self.user_config_path = self.config_dir / "user.yaml"
        
        self._config: Optional[DistributedConfig] = None
        self._config_version = 0
        
    def get_config(self) -> DistributedConfig:
        """获取合并后的配置"""
        if self._config is None:
            self._config = self._load_merged_config()
        return self._config
    
    def reload_config(self) -> DistributedConfig:
        """重新加载配置"""
        self._config = self._load_merged_config()
        self._config_version += 1
        logger.info(f"配置已重新加载，版本: {self._config_version}")
        return self._config
    
    def save_user_config(self, config: DistributedConfig):
        """保存用户配置"""
        config_dict = config.to_dict()
        with open(self.user_config_path, 'w', encoding='utf-8') as f:
            yaml.dump(config_dict, f, default_flow_style=False, allow_unicode=True)
        logger.info(f"用户配置已保存到: {self.user_config_path}")
    
    def create_default_config(self):
        """创建默认配置文件"""
        default_config = DistributedConfig()
        config_dict = default_config.to_dict()
        
        with open(self.default_config_path, 'w', encoding='utf-8') as f:
            yaml.dump(config_dict, f, default_flow_style=False, allow_unicode=True)
        
        logger.info(f"默认配置文件已创建: {self.default_config_path}")
    
    def _load_merged_config(self) -> DistributedConfig:
        """加载并合并配置"""
        # 创建默认配置
        if not self.default_config_path.exists():
            self.create_default_config()
        
        # 加载默认配置
        config_dict = self._load_config_file(self.default_config_path)
        
        # 合并环境配置
        if self.env_config_path.exists():
            env_config = self._load_config_file(self.env_config_path)
            config_dict = self._merge_config(config_dict, env_config)
        
        # 合并用户配置
        if self.user_config_path.exists():
            user_config = self._load_config_file(self.user_config_path)
            config_dict = self._merge_config(config_dict, user_config)
        
        # 合并环境变量
        env_overrides = self._load_env_overrides()
        if env_overrides:
            config_dict = self._merge_config(config_dict, env_overrides)
        
        return DistributedConfig.from_dict(config_dict)
    
    def _load_config_file(self, file_path: Path) -> Dict[str, Any]:
        """加载配置文件"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                if file_path.suffix.lower() in ['.yaml', '.yml']:
                    return yaml.safe_load(f) or {}
                elif file_path.suffix.lower() == '.json':
                    return json.load(f) or {}
                else:
                    logger.warning(f"不支持的配置文件格式: {file_path}")
                    return {}
        except Exception as e:
            logger.error(f"加载配置文件失败 {file_path}: {e}")
            return {}
    
    def _merge_config(self, base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
        """递归合并配置字典"""
        result = base.copy()
        
        for key, value in override.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self._merge_config(result[key], value)
            else:
                result[key] = value
        
        return result
    
    def _load_env_overrides(self) -> Dict[str, Any]:
        """从环境变量加载配置覆盖"""
        overrides = {}
        
        # 定义环境变量映射
        env_mappings = {
            'DISTRIBUTED_ENABLED': 'enabled',
            'SCHEDULER_HOST': 'scheduler_host',
            'SCHEDULER_PORT': 'scheduler_port',
            'REDIS_HOST': 'redis.host',
            'REDIS_PORT': 'redis.port',
            'REDIS_PASSWORD': 'redis.password',
            'ZEROMQ_HOST': 'zeromq.host',
            'ZEROMQ_BASE_PORT': 'zeromq.base_port',
            'LOG_LEVEL': 'monitoring.log_level',
            'SERVERLESS_ENABLED': 'serverless.enabled',
            'AWS_REGION': 'serverless.aws_region',
        }
        
        for env_key, config_path in env_mappings.items():
            env_value = os.getenv(env_key)
            if env_value is not None:
                # 解析配置路径并设置值
                self._set_nested_value(overrides, config_path, env_value)
        
        return overrides
    
    def _set_nested_value(self, config: Dict[str, Any], path: str, value: str):
        """设置嵌套配置值"""
        keys = path.split('.')
        current = config
        
        for key in keys[:-1]:
            if key not in current:
                current[key] = {}
            current = current[key]
        
        # 尝试转换值类型
        final_key = keys[-1]
        try:
            # 尝试转换为数字
            if value.isdigit():
                current[final_key] = int(value)
            elif value.replace('.', '').isdigit():
                current[final_key] = float(value)
            # 尝试转换为布尔值
            elif value.lower() in ['true', 'false']:
                current[final_key] = value.lower() == 'true'
            else:
                current[final_key] = value
        except ValueError:
            current[final_key] = value
    
    def validate_config(self, config: DistributedConfig) -> List[str]:
        """验证配置"""
        errors = []
        
        # 验证端口范围
        if not (1024 <= config.zeromq.base_port <= 65535):
            errors.append("ZeroMQ 基础端口必须在 1024-65535 范围内")
        
        if not (1024 <= config.scheduler_port <= 65535):
            errors.append("调度器端口必须在 1024-65535 范围内")
        
        # 验证队列配置
        used_ports = set()
        # 添加调度器端口到已使用端口集合
        used_ports.add(config.scheduler_port)
        used_ports.add(config.zeromq.heartbeat_port)
        used_ports.add(config.zeromq.control_port)
        
        for queue_name, queue_config in config.queues.items():
            if queue_config.port in used_ports:
                errors.append(f"队列 {queue_name} 的端口 {queue_config.port} 已被使用")
            used_ports.add(queue_config.port)
        
        # 验证存储配置
        if config.storage.type == "s3":
            if not config.storage.s3_bucket:
                errors.append("S3 存储需要配置 bucket 名称")
            if not config.storage.s3_region:
                errors.append("S3 存储需要配置 region")
        
        # 验证 Serverless 配置
        if config.serverless.enabled:
            if config.serverless.provider == "aws":
                if not config.serverless.aws_region:
                    errors.append("AWS Serverless 需要配置 region")
        
        return errors


# 全局配置管理器实例
config_manager = ConfigManager()


def get_config() -> DistributedConfig:
    """获取全局配置"""
    return config_manager.get_config()


def reload_config() -> DistributedConfig:
    """重新加载全局配置"""
    return config_manager.reload_config()