"""
分布式处理模块

该模块实现了基于 ZeroMQ 的分布式图像处理架构，支持多个处理节点并行处理任务。
主要组件包括：
- 任务管理器：负责任务的创建、路由和状态管理
- 队列管理器：管理不同类型的任务队列
- 节点管理器：管理处理节点的注册和监控
- 状态管理器：维护任务和节点的状态信息
"""

__version__ = "1.0.0"
__author__ = "Lama Cleaner Team"

# 定义公开的 API
__all__ = [
    "Task",
    "TaskType", 
    "TaskStatus",
    "TaskPriority",
    "NodeCapability",
    "QueueConfig",
    "TaskManager",
    "QueueManager", 
    "NodeManager",
    "StateManager",
    "DistributedConfig"
]

# 导入公开的组件
from .models import Task, TaskType, TaskStatus, TaskPriority, NodeCapability, QueueConfig
from .task_manager import TaskManager
from .queue_manager import QueueManager
from .node_manager import NodeManager
from .state_manager import StateManager
from .config import DistributedConfig