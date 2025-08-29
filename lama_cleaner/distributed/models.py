"""
分布式处理的核心数据模型

定义了任务、节点、队列等核心数据结构和枚举类型。
"""

from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List
from enum import Enum
import uuid
from datetime import datetime
import json


class TaskType(Enum):
    """任务类型枚举"""
    INPAINT = "inpaint"          # 图像修复任务
    PLUGIN = "plugin"            # 插件处理任务
    UPSCALE = "upscale"          # 图像放大任务
    SEGMENT = "segment"          # 图像分割任务


class TaskStatus(Enum):
    """任务状态枚举"""
    PENDING = "pending"          # 等待中
    QUEUED = "queued"           # 已入队
    PROCESSING = "processing"    # 处理中
    COMPLETED = "completed"      # 已完成
    FAILED = "failed"           # 失败
    CANCELLED = "cancelled"      # 已取消


class TaskPriority(Enum):
    """任务优先级枚举"""
    LOW = 1                     # 低优先级
    NORMAL = 2                  # 普通优先级
    HIGH = 3                    # 高优先级
    URGENT = 4                  # 紧急优先级


class NodeType(Enum):
    """节点类型枚举"""
    LOCAL = "local"             # 本地节点
    REMOTE = "remote"           # 远程节点
    SERVERLESS = "serverless"   # Serverless 节点


class NodeStatus(Enum):
    """节点状态枚举"""
    ONLINE = "online"           # 在线
    OFFLINE = "offline"         # 离线
    BUSY = "busy"              # 忙碌
    ERROR = "error"            # 错误状态


@dataclass
class Task:
    """任务数据模型"""
    task_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    task_type: TaskType = TaskType.INPAINT
    status: TaskStatus = TaskStatus.PENDING
    priority: TaskPriority = TaskPriority.NORMAL
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    
    # 输入数据
    image_path: Optional[str] = None
    mask_path: Optional[str] = None
    config: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        """初始化后处理"""
        # 确保 config 始终是字典
        if self.config is None:
            self.config = {}
    
    # 处理信息
    assigned_node: Optional[str] = None
    queue_name: Optional[str] = None
    retry_count: int = 0
    max_retries: int = 3
    
    # 结果数据
    result_path: Optional[str] = None
    error_message: Optional[str] = None
    processing_time: Optional[float] = None
    
    # 元数据
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            'task_id': self.task_id,
            'task_type': self.task_type.value,
            'status': self.status.value,
            'priority': self.priority.value,
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat(),
            'image_path': self.image_path,
            'mask_path': self.mask_path,
            'config': self.config,
            'assigned_node': self.assigned_node,
            'queue_name': self.queue_name,
            'retry_count': self.retry_count,
            'max_retries': self.max_retries,
            'result_path': self.result_path,
            'error_message': self.error_message,
            'processing_time': self.processing_time,
            'user_id': self.user_id,
            'session_id': self.session_id,
            'metadata': self.metadata
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Task':
        """从字典创建任务对象"""
        task = cls()
        task.task_id = data.get('task_id', task.task_id)
        task.task_type = TaskType(data.get('task_type', TaskType.INPAINT.value))
        task.status = TaskStatus(data.get('status', TaskStatus.PENDING.value))
        task.priority = TaskPriority(data.get('priority', TaskPriority.NORMAL.value))
        
        if 'created_at' in data:
            task.created_at = datetime.fromisoformat(data['created_at'])
        if 'updated_at' in data:
            task.updated_at = datetime.fromisoformat(data['updated_at'])
            
        task.image_path = data.get('image_path')
        task.mask_path = data.get('mask_path')
        task.config = data.get('config', {})
        task.assigned_node = data.get('assigned_node')
        task.queue_name = data.get('queue_name')
        task.retry_count = data.get('retry_count', 0)
        task.max_retries = data.get('max_retries', 3)
        task.result_path = data.get('result_path')
        task.error_message = data.get('error_message')
        task.processing_time = data.get('processing_time')
        task.user_id = data.get('user_id')
        task.session_id = data.get('session_id')
        task.metadata = data.get('metadata', {})
        
        return task
    
    def to_json(self) -> str:
        """转换为 JSON 字符串"""
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)
    
    @classmethod
    def from_json(cls, json_str: str) -> 'Task':
        """从 JSON 字符串创建任务对象"""
        data = json.loads(json_str)
        return cls.from_dict(data)


@dataclass
class NodeCapability:
    """节点能力配置"""
    node_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    node_type: NodeType = NodeType.LOCAL
    
    # 硬件信息
    gpu_count: int = 0
    gpu_memory: int = 0  # MB
    gpu_models: List[str] = field(default_factory=list)
    cpu_cores: int = 0
    memory_total: int = 0  # MB
    
    # 支持的模型和功能
    supported_models: List[str] = field(default_factory=list)
    supported_tasks: List[TaskType] = field(default_factory=list)
    max_concurrent_tasks: int = 1
    
    # 网络信息
    host: str = "localhost"
    port: int = 0
    
    # 状态信息
    status: NodeStatus = NodeStatus.OFFLINE
    last_heartbeat: Optional[datetime] = None
    current_load: int = 0
    total_processed: int = 0
    
    def has_gpu(self) -> bool:
        """检查是否有 GPU"""
        return self.gpu_count > 0 and self.gpu_memory > 0
    
    def can_handle_task(self, task: Task) -> bool:
        """检查是否能处理指定任务"""
        # 检查任务类型支持
        if task.task_type not in self.supported_tasks:
            return False
        
        # 检查模型支持
        required_model = task.config.get('model', '')
        if required_model and required_model not in self.supported_models:
            return False
        
        # 检查 GPU 需求
        if task.config.get('gpu_required', False) and not self.has_gpu():
            return False
        
        # 检查内存需求
        required_memory = task.config.get('min_memory', 0)
        if required_memory > self.memory_total:
            return False
        
        return True
    
    def get_queue_subscriptions(self) -> List[str]:
        """根据节点能力返回可订阅的队列列表"""
        subscriptions = []
        
        if self.has_gpu():
            if self.gpu_memory >= 8192:  # 8GB+
                subscriptions.append("gpu-high")
            elif self.gpu_memory >= 4096:  # 4GB+
                subscriptions.append("gpu-medium")
            else:
                subscriptions.append("gpu-low")
        
        if self.cpu_cores >= 8:
            subscriptions.append("cpu-intensive")
        elif self.cpu_cores >= 4:
            subscriptions.append("cpu-light")
        
        # Serverless 节点通常订阅轻量级队列
        if self.node_type == NodeType.SERVERLESS:
            subscriptions.append("serverless")
        
        return subscriptions
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            'node_id': self.node_id,
            'node_type': self.node_type.value,
            'gpu_count': self.gpu_count,
            'gpu_memory': self.gpu_memory,
            'gpu_models': self.gpu_models,
            'cpu_cores': self.cpu_cores,
            'memory_total': self.memory_total,
            'supported_models': self.supported_models,
            'supported_tasks': [t.value for t in self.supported_tasks],
            'max_concurrent_tasks': self.max_concurrent_tasks,
            'host': self.host,
            'port': self.port,
            'status': self.status.value,
            'last_heartbeat': self.last_heartbeat.isoformat() if self.last_heartbeat else None,
            'current_load': self.current_load,
            'total_processed': self.total_processed
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'NodeCapability':
        """从字典创建节点能力对象"""
        capability = cls()
        capability.node_id = data.get('node_id', capability.node_id)
        capability.node_type = NodeType(data.get('node_type', NodeType.LOCAL.value))
        capability.gpu_count = data.get('gpu_count', 0)
        capability.gpu_memory = data.get('gpu_memory', 0)
        capability.gpu_models = data.get('gpu_models', [])
        capability.cpu_cores = data.get('cpu_cores', 0)
        capability.memory_total = data.get('memory_total', 0)
        capability.supported_models = data.get('supported_models', [])
        capability.supported_tasks = [TaskType(t) for t in data.get('supported_tasks', [])]
        capability.max_concurrent_tasks = data.get('max_concurrent_tasks', 1)
        capability.host = data.get('host', 'localhost')
        capability.port = data.get('port', 0)
        capability.status = NodeStatus(data.get('status', NodeStatus.OFFLINE.value))
        
        if data.get('last_heartbeat'):
            capability.last_heartbeat = datetime.fromisoformat(data['last_heartbeat'])
        
        capability.current_load = data.get('current_load', 0)
        capability.total_processed = data.get('total_processed', 0)
        
        return capability


@dataclass
class QueueConfig:
    """队列配置"""
    name: str
    port: int
    pattern: str = "PUSH/PULL"  # ZeroMQ 模式
    requirements: Dict[str, Any] = field(default_factory=dict)
    max_size: int = 1000
    priority_enabled: bool = True
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            'name': self.name,
            'port': self.port,
            'pattern': self.pattern,
            'requirements': self.requirements,
            'max_size': self.max_size,
            'priority_enabled': self.priority_enabled
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'QueueConfig':
        """从字典创建队列配置对象"""
        return cls(
            name=data['name'],
            port=data['port'],
            pattern=data.get('pattern', 'PUSH/PULL'),
            requirements=data.get('requirements', {}),
            max_size=data.get('max_size', 1000),
            priority_enabled=data.get('priority_enabled', True)
        )


# 预定义的队列配置
DEFAULT_QUEUE_CONFIGS = {
    "gpu-high": QueueConfig(
        name="gpu-high",
        port=5555,
        requirements={
            "gpu": True,
            "gpu_memory": 8192,
            "models": ["sd15", "sd21", "sdxl", "lama"]
        }
    ),
    "gpu-medium": QueueConfig(
        name="gpu-medium", 
        port=5556,
        requirements={
            "gpu": True,
            "gpu_memory": 4096,
            "models": ["lama", "mat", "fcf"]
        }
    ),
    "gpu-low": QueueConfig(
        name="gpu-low",
        port=5557,
        requirements={
            "gpu": True,
            "gpu_memory": 2048,
            "models": ["lama", "opencv"]
        }
    ),
    "cpu-intensive": QueueConfig(
        name="cpu-intensive",
        port=5558,
        requirements={
            "cpu_cores": 8,
            "memory": 16384,
            "models": ["opencv", "zits"]
        }
    ),
    "cpu-light": QueueConfig(
        name="cpu-light",
        port=5559,
        requirements={
            "cpu_cores": 4,
            "memory": 8192,
            "models": ["opencv", "lama"]
        }
    ),
    "serverless": QueueConfig(
        name="serverless",
        port=5560,
        requirements={
            "serverless": True,
            "models": ["lama", "opencv"]
        }
    )
}