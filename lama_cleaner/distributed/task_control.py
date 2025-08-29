"""
任务控制模块

实现任务取消、重试机制，包括指数退避算法和超时检测。
支持队列中和处理中的任务取消。
"""

import logging
import time
import threading
from typing import Dict, List, Optional, Callable
from datetime import datetime, timedelta
from enum import Enum
import math

from .models import Task, TaskStatus, TaskType
from .task_manager import TaskManager
from .queue_manager import QueueManager
from .node_manager import NodeManager
from .config import get_config

logger = logging.getLogger(__name__)


class RetryStrategy(Enum):
    """重试策略枚举"""
    IMMEDIATE = "immediate"          # 立即重试
    LINEAR = "linear"               # 线性退避
    EXPONENTIAL = "exponential"     # 指数退避
    FIXED_DELAY = "fixed_delay"     # 固定延迟


class TaskCancellationReason(Enum):
    """任务取消原因枚举"""
    USER_REQUEST = "user_request"           # 用户请求
    TIMEOUT = "timeout"                     # 超时
    NODE_FAILURE = "node_failure"           # 节点故障
    SYSTEM_SHUTDOWN = "system_shutdown"     # 系统关闭
    RESOURCE_LIMIT = "resource_limit"       # 资源限制


class RetryConfig:
    """重试配置"""
    
    def __init__(self,
                 strategy: RetryStrategy = RetryStrategy.EXPONENTIAL,
                 max_retries: int = 3,
                 base_delay: float = 1.0,
                 max_delay: float = 300.0,
                 backoff_multiplier: float = 2.0,
                 jitter: bool = True):
        self.strategy = strategy
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.backoff_multiplier = backoff_multiplier
        self.jitter = jitter
    
    def calculate_delay(self, retry_count: int) -> float:
        """计算重试延迟"""
        if self.strategy == RetryStrategy.IMMEDIATE:
            return 0.0
        
        elif self.strategy == RetryStrategy.LINEAR:
            delay = self.base_delay * retry_count
        
        elif self.strategy == RetryStrategy.EXPONENTIAL:
            delay = self.base_delay * (self.backoff_multiplier ** retry_count)
        
        elif self.strategy == RetryStrategy.FIXED_DELAY:
            delay = self.base_delay
        
        else:
            delay = self.base_delay
        
        # 限制最大延迟
        delay = min(delay, self.max_delay)
        
        # 添加抖动
        if self.jitter and delay > 0:
            import random
            jitter_amount = delay * 0.1  # 10% 抖动
            delay += random.uniform(-jitter_amount, jitter_amount)
            delay = max(0, delay)
        
        return delay


class TaskTimeoutManager:
    """任务超时管理器"""
    
    def __init__(self, task_manager: TaskManager):
        self.task_manager = task_manager
        self.config = get_config()
        
        # 超时配置
        self.default_timeout = self.config.default_task_timeout
        self.check_interval = 30  # 检查间隔（秒）
        
        # 运行状态
        self._running = False
        self._timeout_thread = None
        
        # 任务超时配置
        self.task_timeouts: Dict[str, datetime] = {}
        self.timeout_lock = threading.RLock()
    
    def start(self):
        """启动超时管理器"""
        if self._running:
            return
        
        self._running = True
        self._start_timeout_thread()
        logger.info("任务超时管理器已启动")
    
    def stop(self):
        """停止超时管理器"""
        if not self._running:
            return
        
        self._running = False
        if self._timeout_thread and self._timeout_thread.is_alive():
            self._timeout_thread.join(timeout=5)
        
        logger.info("任务超时管理器已停止")
    
    def set_task_timeout(self, task_id: str, timeout_seconds: Optional[int] = None):
        """设置任务超时"""
        timeout = timeout_seconds or self.default_timeout
        timeout_time = datetime.now() + timedelta(seconds=timeout)
        
        with self.timeout_lock:
            self.task_timeouts[task_id] = timeout_time
        
        logger.debug(f"设置任务超时: {task_id}, 超时时间: {timeout_time}")
    
    def remove_task_timeout(self, task_id: str):
        """移除任务超时"""
        with self.timeout_lock:
            self.task_timeouts.pop(task_id, None)
    
    def _start_timeout_thread(self):
        """启动超时检查线程"""
        def timeout_worker():
            while self._running:
                try:
                    self._check_timeouts()
                    time.sleep(self.check_interval)
                except Exception as e:
                    logger.error(f"超时检查线程错误: {e}")
                    time.sleep(self.check_interval)
        
        self._timeout_thread = threading.Thread(target=timeout_worker, daemon=True)
        self._timeout_thread.start()
        logger.info("超时检查线程已启动")
    
    def _check_timeouts(self):
        """检查任务超时"""
        now = datetime.now()
        timed_out_tasks = []
        
        with self.timeout_lock:
            for task_id, timeout_time in list(self.task_timeouts.items()):
                if now > timeout_time:
                    timed_out_tasks.append(task_id)
                    del self.task_timeouts[task_id]
        
        # 处理超时任务
        for task_id in timed_out_tasks:
            self._handle_task_timeout(task_id)
    
    def _handle_task_timeout(self, task_id: str):
        """处理任务超时"""
        try:
            task = self.task_manager.get_task(task_id)
            if not task:
                return
            
            if task.status in [TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED]:
                return
            
            logger.warning(f"任务超时: {task_id}, 状态: {task.status.value}")
            
            # 使用任务管理器的 fail_task 方法
            self.task_manager.fail_task(
                task_id,
                f"任务超时 ({self.default_timeout}秒)"
            )
            
        except Exception as e:
            logger.error(f"处理任务超时失败 {task_id}: {e}")


class TaskCancellationManager:
    """任务取消管理器"""
    
    def __init__(self, 
                 task_manager: TaskManager,
                 queue_manager: QueueManager,
                 node_manager: NodeManager):
        self.task_manager = task_manager
        self.queue_manager = queue_manager
        self.node_manager = node_manager
        
        # 取消回调
        self.cancellation_callbacks: List[Callable[[str, TaskCancellationReason], None]] = []
    
    def cancel_task(self, task_id: str, reason: TaskCancellationReason = TaskCancellationReason.USER_REQUEST) -> bool:
        """取消任务"""
        try:
            task = self.task_manager.get_task(task_id)
            if not task:
                logger.warning(f"取消任务失败，任务不存在: {task_id}")
                return False
            
            # 检查任务状态
            if task.status in [TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED]:
                logger.warning(f"任务已完成或已取消，无法取消: {task_id}, 状态: {task.status.value}")
                return False
            
            logger.info(f"取消任务: {task_id}, 状态: {task.status.value}, 原因: {reason.value}")
            
            # 根据任务状态执行不同的取消逻辑
            if task.status == TaskStatus.PENDING:
                return self._cancel_pending_task(task, reason)
            elif task.status == TaskStatus.QUEUED:
                return self._cancel_queued_task(task, reason)
            elif task.status == TaskStatus.PROCESSING:
                return self._cancel_processing_task(task, reason)
            
            return False
            
        except Exception as e:
            logger.error(f"取消任务失败 {task_id}: {e}")
            return False
    
    def cancel_user_tasks(self, user_id: str, reason: TaskCancellationReason = TaskCancellationReason.USER_REQUEST) -> int:
        """取消用户的所有任务"""
        tasks = self.task_manager.get_tasks_by_user(user_id)
        cancelled_count = 0
        
        for task in tasks:
            if task.status not in [TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED]:
                if self.cancel_task(task.task_id, reason):
                    cancelled_count += 1
        
        logger.info(f"取消用户任务: {user_id}, 取消数量: {cancelled_count}")
        return cancelled_count
    
    def cancel_node_tasks(self, node_id: str, reason: TaskCancellationReason = TaskCancellationReason.NODE_FAILURE) -> int:
        """取消节点的所有任务"""
        tasks = self.task_manager.get_tasks_by_node(node_id)
        cancelled_count = 0
        
        for task in tasks:
            if task.status not in [TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED]:
                if self.cancel_task(task.task_id, reason):
                    cancelled_count += 1
        
        logger.info(f"取消节点任务: {node_id}, 取消数量: {cancelled_count}")
        return cancelled_count
    
    def add_cancellation_callback(self, callback: Callable[[str, TaskCancellationReason], None]):
        """添加取消回调"""
        self.cancellation_callbacks.append(callback)
    
    def remove_cancellation_callback(self, callback: Callable[[str, TaskCancellationReason], None]):
        """移除取消回调"""
        if callback in self.cancellation_callbacks:
            self.cancellation_callbacks.remove(callback)
    
    def _cancel_pending_task(self, task: Task, reason: TaskCancellationReason) -> bool:
        """取消待处理任务"""
        # 直接更新任务状态
        success = self.task_manager.update_task_status(
            task.task_id,
            TaskStatus.CANCELLED,
            error_message=f"任务已取消: {reason.value}"
        )
        
        if success:
            self._notify_cancellation(task.task_id, reason)
        
        return success
    
    def _cancel_queued_task(self, task: Task, reason: TaskCancellationReason) -> bool:
        """取消队列中的任务"""
        # 从队列中移除任务
        if task.queue_name:
            try:
                self.queue_manager.remove_task_from_queue(task.queue_name, task.task_id)
            except Exception as e:
                logger.warning(f"从队列移除任务失败 {task.task_id}: {e}")
        
        # 更新任务状态
        success = self.task_manager.update_task_status(
            task.task_id,
            TaskStatus.CANCELLED,
            error_message=f"任务已取消: {reason.value}"
        )
        
        if success:
            self._notify_cancellation(task.task_id, reason)
        
        return success
    
    def _cancel_processing_task(self, task: Task, reason: TaskCancellationReason) -> bool:
        """取消处理中的任务"""
        # 发送取消指令给处理节点
        if task.assigned_node:
            try:
                self.node_manager.send_cancel_command(task.assigned_node, task.task_id)
            except Exception as e:
                logger.warning(f"发送取消指令失败 {task.task_id}: {e}")
        
        # 更新任务状态
        success = self.task_manager.update_task_status(
            task.task_id,
            TaskStatus.CANCELLED,
            error_message=f"任务已取消: {reason.value}"
        )
        
        if success:
            self._notify_cancellation(task.task_id, reason)
        
        return success
    
    def _notify_cancellation(self, task_id: str, reason: TaskCancellationReason):
        """通知任务取消"""
        for callback in self.cancellation_callbacks:
            try:
                callback(task_id, reason)
            except Exception as e:
                logger.error(f"取消回调执行失败: {e}")


class TaskRetryManager:
    """任务重试管理器"""
    
    def __init__(self, task_manager: TaskManager):
        self.task_manager = task_manager
        self.config = get_config()
        
        # 默认重试配置
        self.default_retry_config = RetryConfig(
            strategy=RetryStrategy.EXPONENTIAL,
            max_retries=self.config.max_task_retries,
            base_delay=1.0,
            max_delay=300.0
        )
        
        # 任务特定的重试配置
        self.task_retry_configs: Dict[str, RetryConfig] = {}
        
        # 延迟重试队列
        self.delayed_retries: List[tuple] = []  # (retry_time, task_id, retry_config)
        self.retry_lock = threading.RLock()
        
        # 运行状态
        self._running = False
        self._retry_thread = None
    
    def start(self):
        """启动重试管理器"""
        if self._running:
            return
        
        self._running = True
        self._start_retry_thread()
        logger.info("任务重试管理器已启动")
    
    def stop(self):
        """停止重试管理器"""
        if not self._running:
            return
        
        self._running = False
        if self._retry_thread and self._retry_thread.is_alive():
            self._retry_thread.join(timeout=5)
        
        logger.info("任务重试管理器已停止")
    
    def set_task_retry_config(self, task_id: str, retry_config: RetryConfig):
        """设置任务重试配置"""
        self.task_retry_configs[task_id] = retry_config
    
    def retry_task(self, task_id: str, delay: Optional[float] = None) -> bool:
        """重试任务"""
        try:
            task = self.task_manager.get_task(task_id)
            if not task:
                logger.warning(f"重试任务失败，任务不存在: {task_id}")
                return False
            
            # 检查重试次数
            retry_config = self.task_retry_configs.get(task_id, self.default_retry_config)
            if task.retry_count >= retry_config.max_retries:
                logger.warning(f"任务重试次数已达上限: {task_id}")
                return False
            
            # 计算延迟
            if delay is None:
                delay = retry_config.calculate_delay(task.retry_count)
            
            if delay > 0:
                # 延迟重试
                retry_time = datetime.now() + timedelta(seconds=delay)
                with self.retry_lock:
                    self.delayed_retries.append((retry_time, task_id, retry_config))
                
                logger.info(f"任务将在 {delay:.1f} 秒后重试: {task_id}")
                return True
            else:
                # 立即重试
                return self._execute_retry(task_id)
                
        except Exception as e:
            logger.error(f"重试任务失败 {task_id}: {e}")
            return False
    
    def retry_failed_tasks(self, limit: Optional[int] = None) -> int:
        """重试失败的任务"""
        failed_tasks = self.task_manager.get_tasks_by_status(TaskStatus.FAILED, limit)
        retry_count = 0
        
        for task in failed_tasks:
            if self.retry_task(task.task_id):
                retry_count += 1
        
        logger.info(f"批量重试失败任务: {retry_count} 个任务")
        return retry_count
    
    def _start_retry_thread(self):
        """启动重试线程"""
        def retry_worker():
            while self._running:
                try:
                    self._process_delayed_retries()
                    time.sleep(1)  # 每秒检查一次
                except Exception as e:
                    logger.error(f"重试线程错误: {e}")
                    time.sleep(5)
        
        self._retry_thread = threading.Thread(target=retry_worker, daemon=True)
        self._retry_thread.start()
        logger.info("重试线程已启动")
    
    def _process_delayed_retries(self):
        """处理延迟重试"""
        now = datetime.now()
        ready_retries = []
        
        with self.retry_lock:
            remaining_retries = []
            for retry_time, task_id, retry_config in self.delayed_retries:
                if now >= retry_time:
                    ready_retries.append(task_id)
                else:
                    remaining_retries.append((retry_time, task_id, retry_config))
            
            self.delayed_retries = remaining_retries
        
        # 执行准备好的重试
        for task_id in ready_retries:
            try:
                self._execute_retry(task_id)
            except Exception as e:
                logger.error(f"执行延迟重试失败 {task_id}: {e}")
    
    def _execute_retry(self, task_id: str) -> bool:
        """执行重试"""
        success = self.task_manager.retry_task(task_id)
        if success:
            logger.info(f"任务重试成功: {task_id}")
        else:
            logger.warning(f"任务重试失败: {task_id}")
        
        return success


class TaskControlManager:
    """任务控制管理器"""
    
    def __init__(self,
                 task_manager: TaskManager,
                 queue_manager: QueueManager,
                 node_manager: NodeManager):
        self.task_manager = task_manager
        self.queue_manager = queue_manager
        self.node_manager = node_manager
        
        # 子管理器
        self.timeout_manager = TaskTimeoutManager(task_manager)
        self.cancellation_manager = TaskCancellationManager(task_manager, queue_manager, node_manager)
        self.retry_manager = TaskRetryManager(task_manager)
        
        # 注册任务状态回调
        self.task_manager.add_status_callback(self._on_task_status_change)
    
    def start(self):
        """启动任务控制管理器"""
        self.timeout_manager.start()
        self.retry_manager.start()
        logger.info("任务控制管理器已启动")
    
    def stop(self):
        """停止任务控制管理器"""
        self.timeout_manager.stop()
        self.retry_manager.stop()
        logger.info("任务控制管理器已停止")
    
    def _on_task_status_change(self, task: Task):
        """任务状态变更回调"""
        # 处理任务开始处理时的超时设置
        if task.status == TaskStatus.PROCESSING:
            self.timeout_manager.set_task_timeout(task.task_id)
        
        # 处理任务完成时的超时移除
        elif task.status in [TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED]:
            self.timeout_manager.remove_task_timeout(task.task_id)
            
            # 如果任务失败且可以重试，自动重试
            if task.status == TaskStatus.FAILED and task.retry_count < task.max_retries:
                self.retry_manager.retry_task(task.task_id)


# 全局任务控制管理器实例
_task_control_manager = None


def get_task_control_manager(task_manager: TaskManager,
                           queue_manager: QueueManager,
                           node_manager: NodeManager) -> TaskControlManager:
    """获取全局任务控制管理器实例"""
    global _task_control_manager
    if _task_control_manager is None:
        _task_control_manager = TaskControlManager(task_manager, queue_manager, node_manager)
    return _task_control_manager