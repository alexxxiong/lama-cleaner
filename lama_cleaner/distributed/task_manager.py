"""
任务管理器

负责任务的创建、路由、状态管理和生命周期控制。
集成持久化存储和状态转换验证。
"""

from typing import Dict, List, Optional, Callable, Set, Any
from datetime import datetime, timedelta
import threading
import time
from .models import Task, TaskStatus, TaskType, TaskPriority
from .config import get_config
from .storage import get_task_storage
from .logging import get_task_manager_logger


class TaskLifecycleManager:
    """任务生命周期管理器"""
    
    # 定义有效的状态转换
    VALID_TRANSITIONS = {
        TaskStatus.PENDING: {TaskStatus.QUEUED, TaskStatus.CANCELLED},
        TaskStatus.QUEUED: {TaskStatus.PROCESSING, TaskStatus.CANCELLED, TaskStatus.PENDING},
        TaskStatus.PROCESSING: {TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED},
        TaskStatus.COMPLETED: set(),  # 完成状态不能转换
        TaskStatus.FAILED: {TaskStatus.PENDING},  # 失败可以重试
        TaskStatus.CANCELLED: set()  # 取消状态不能转换
    }
    
    @classmethod
    def can_transition(cls, from_status: TaskStatus, to_status: TaskStatus) -> bool:
        """检查状态转换是否有效"""
        return to_status in cls.VALID_TRANSITIONS.get(from_status, set())
    
    @classmethod
    def validate_transition(cls, task: Task, new_status: TaskStatus) -> bool:
        """验证任务状态转换"""
        if not cls.can_transition(task.status, new_status):
            logger.warning(f"无效的状态转换: {task.task_id} {task.status.value} -> {new_status.value}")
            return False
        return True
    
    @classmethod
    def get_next_valid_statuses(cls, current_status: TaskStatus) -> Set[TaskStatus]:
        """获取当前状态可以转换到的状态列表"""
        return cls.VALID_TRANSITIONS.get(current_status, set())


class TaskManager:
    """任务管理器"""
    
    def __init__(self):
        self.config = get_config()
        self.storage = get_task_storage()
        self.lifecycle_manager = TaskLifecycleManager()
        
        # 使用专用的任务管理器日志器
        self.logger = get_task_manager_logger()
        
        # 内存缓存，用于快速访问
        self.task_cache: Dict[str, Task] = {}
        self.cache_lock = threading.RLock()
        
        # 状态回调
        self.status_callbacks: List[Callable[[Task], None]] = []
        
        # 后台线程
        self._cleanup_thread = None
        self._running = False
        
        # 加载现有任务到缓存
        self._load_active_tasks()
    
    def start(self):
        """启动任务管理器"""
        self._running = True
        self._start_cleanup_thread()
        self.logger.info("任务管理器已启动", action="task_manager_started")
    
    def stop(self):
        """停止任务管理器"""
        self._running = False
        if self._cleanup_thread and self._cleanup_thread.is_alive():
            self._cleanup_thread.join(timeout=5)
        self.logger.info("任务管理器已停止", action="task_manager_stopped")
    
    def _load_active_tasks(self):
        """加载活跃任务到内存缓存"""
        try:
            # 加载未完成的任务
            active_statuses = [
                TaskStatus.PENDING,
                TaskStatus.QUEUED,
                TaskStatus.PROCESSING
            ]
            
            for status in active_statuses:
                tasks = self.storage.get_tasks_by_status(status)
                with self.cache_lock:
                    for task in tasks:
                        self.task_cache[task.task_id] = task
            
            self.logger.info(f"已加载 {len(self.task_cache)} 个活跃任务到缓存", 
                            action="active_tasks_loaded", 
                            task_count=len(self.task_cache))
            
        except Exception as e:
            self.logger.error(f"加载活跃任务失败: {e}", action="load_tasks_error", error=str(e))
    
    def create_task(self, 
                   task_type: TaskType,
                   image_path: str,
                   config: Dict,
                   mask_path: Optional[str] = None,
                   priority: TaskPriority = TaskPriority.NORMAL,
                   user_id: Optional[str] = None,
                   session_id: Optional[str] = None) -> Task:
        """创建新任务"""
        task = Task(
            task_type=task_type,
            image_path=image_path,
            mask_path=mask_path,
            config=config,
            priority=priority,
            user_id=user_id,
            session_id=session_id,
            max_retries=self.config.max_task_retries
        )
        
        # 保存到存储
        if not self.storage.save_task(task):
            raise RuntimeError(f"保存任务失败: {task.task_id}")
        
        # 添加到缓存
        with self.cache_lock:
            self.task_cache[task.task_id] = task
        
        # 记录任务创建
        self.logger.log_task_created(task)
        self._notify_status_change(task)
        
        return task
    
    def get_task(self, task_id: str) -> Optional[Task]:
        """获取任务"""
        # 先从缓存获取
        with self.cache_lock:
            if task_id in self.task_cache:
                return self.task_cache[task_id]
        
        # 从存储获取
        task = self.storage.get_task(task_id)
        if task:
            # 如果是活跃任务，添加到缓存
            if task.status in [TaskStatus.PENDING, TaskStatus.QUEUED, TaskStatus.PROCESSING]:
                with self.cache_lock:
                    self.task_cache[task_id] = task
        
        return task
    
    def update_task_status(self, task_id: str, status: TaskStatus, 
                          error_message: Optional[str] = None,
                          result_path: Optional[str] = None,
                          processing_time: Optional[float] = None,
                          assigned_node: Optional[str] = None) -> bool:
        """更新任务状态"""
        task = self.get_task(task_id)
        if not task:
            self.logger.warning(f"任务不存在: {task_id}", action="task_not_found", task_id=task_id)
            return False
        
        # 验证状态转换
        if not self.lifecycle_manager.validate_transition(task, status):
            return False
        
        # 更新任务信息
        old_status = task.status
        task.status = status
        task.updated_at = datetime.now()
        
        if error_message:
            task.error_message = error_message
        if result_path:
            task.result_path = result_path
        if processing_time:
            task.processing_time = processing_time
        if assigned_node:
            task.assigned_node = assigned_node
        
        # 保存到存储
        if not self.storage.update_task(task):
            self.logger.error(f"更新任务存储失败: {task_id}", action="update_task_storage_error", task_id=task_id)
            return False
        
        # 更新缓存
        with self.cache_lock:
            if status in [TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED]:
                # 移除非活跃任务从缓存
                self.task_cache.pop(task_id, None)
            else:
                # 更新缓存中的任务
                self.task_cache[task_id] = task
        
        # 记录任务状态变更
        self.logger.log_task_status_change(task_id, old_status, status)
        self._notify_status_change(task)
        return True
    
    def cancel_task(self, task_id: str) -> bool:
        """取消任务"""
        task = self.get_task(task_id)
        if not task:
            return False
        
        # 检查是否可以取消
        if not self.lifecycle_manager.can_transition(task.status, TaskStatus.CANCELLED):
            self.logger.warning(f"任务无法取消: {task_id}, 当前状态: {task.status.value}",
                              action="task_cancel_invalid",
                              task_id=task_id,
                              current_status=task.status.value)
            return False
        
        return self.update_task_status(task_id, TaskStatus.CANCELLED)
    
    def retry_task(self, task_id: str) -> bool:
        """重试任务"""
        task = self.get_task(task_id)
        if not task:
            return False
        
        if task.retry_count >= task.max_retries:
            self.logger.warning(f"任务重试次数已达上限: {task_id}",
                              action="task_retry_limit_exceeded",
                              task_id=task_id,
                              retry_count=task.retry_count,
                              max_retries=task.max_retries)
            return False
        
        # 检查是否可以重试（只有失败的任务可以重试）
        if not self.lifecycle_manager.can_transition(task.status, TaskStatus.PENDING):
            self.logger.warning(f"任务无法重试: {task_id}, 当前状态: {task.status.value}",
                              action="task_retry_invalid",
                              task_id=task_id,
                              current_status=task.status.value)
            return False
        
        # 更新重试信息
        task.retry_count += 1
        task.assigned_node = None
        task.queue_name = None
        task.error_message = None
        task.status = TaskStatus.PENDING
        task.updated_at = datetime.now()
        
        # 保存到存储
        if not self.storage.update_task(task):
            self.logger.error(f"更新重试任务存储失败: {task_id}",
                            action="retry_task_storage_error",
                            task_id=task_id)
            return False
        
        # 更新缓存
        with self.cache_lock:
            self.task_cache[task_id] = task
        
        # 记录任务重试
        self.logger.log_task_retry(task_id, task.retry_count, task.max_retries)
        self._notify_status_change(task)
        return True
    
    def get_tasks_by_status(self, status: TaskStatus, limit: Optional[int] = None) -> List[Task]:
        """根据状态获取任务列表"""
        return self.storage.get_tasks_by_status(status, limit)
    
    def get_tasks_by_node(self, node_id: str) -> List[Task]:
        """获取指定节点的任务"""
        return self.storage.get_tasks_by_node(node_id)
    
    def get_pending_tasks(self, limit: Optional[int] = None) -> List[Task]:
        """获取待处理任务"""
        return self.storage.get_pending_tasks(limit)
    
    def assign_task_to_node(self, task_id: str, node_id: str, queue_name: str) -> bool:
        """将任务分配给节点"""
        task = self.get_task(task_id)
        if not task:
            return False
        
        # 检查是否可以分配（只有待处理的任务可以分配）
        if not self.lifecycle_manager.can_transition(task.status, TaskStatus.QUEUED):
            logger.warning(f"任务无法分配: {task_id}, 当前状态: {task.status.value}")
            return False
        
        # 更新任务信息
        task.assigned_node = node_id
        task.queue_name = queue_name
        
        logger.info(f"任务分配: {task_id} -> 节点: {node_id}, 队列: {queue_name}")
        return self.update_task_status(task_id, TaskStatus.QUEUED, assigned_node=node_id)
    
    def get_task_statistics(self) -> Dict[str, int]:
        """获取任务统计信息"""
        return self.storage.get_task_statistics()
    
    def cleanup_completed_tasks(self, older_than_hours: int = 24) -> int:
        """清理已完成的任务"""
        cutoff_time = datetime.now() - timedelta(hours=older_than_hours)
        
        # 从存储中清理
        cleaned_count = self.storage.cleanup_old_tasks(cutoff_time)
        
        # 从缓存中清理
        with self.cache_lock:
            cache_tasks_to_remove = []
            for task_id, task in self.task_cache.items():
                if (task.status in [TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED] and
                    task.updated_at < cutoff_time):
                    cache_tasks_to_remove.append(task_id)
            
            for task_id in cache_tasks_to_remove:
                del self.task_cache[task_id]
        
        if cleaned_count > 0:
            logger.info(f"清理了 {cleaned_count} 个已完成的任务")
        
        return cleaned_count
    
    def add_status_callback(self, callback: Callable[[Task], None]):
        """添加状态变更回调"""
        self.status_callbacks.append(callback)
    
    def remove_status_callback(self, callback: Callable[[Task], None]):
        """移除状态变更回调"""
        if callback in self.status_callbacks:
            self.status_callbacks.remove(callback)
    
    def _notify_status_change(self, task: Task):
        """通知状态变更"""
        for callback in self.status_callbacks:
            try:
                callback(task)
            except Exception as e:
                logger.error(f"状态回调执行失败: {e}")
    
    def _start_cleanup_thread(self):
        """启动清理线程"""
        def cleanup_worker():
            while self._running:
                try:
                    self.cleanup_completed_tasks(
                        older_than_hours=self.config.completed_task_ttl // 3600
                    )
                    time.sleep(self.config.task_cleanup_interval)
                except Exception as e:
                    logger.error(f"任务清理失败: {e}")
                    time.sleep(60)  # 出错时等待1分钟再重试
        
        self._cleanup_thread = threading.Thread(target=cleanup_worker, daemon=True)
        self._cleanup_thread.start()
        logger.info("任务清理线程已启动")
    
    def get_tasks_by_user(self, user_id: str, limit: Optional[int] = None) -> List[Task]:
        """获取用户的任务"""
        return self.storage.get_tasks_by_user(user_id, limit)
    
    def get_tasks_by_session(self, session_id: str) -> List[Task]:
        """获取会话的任务"""
        return self.storage.get_tasks_by_session(session_id)
    
    def get_task_progress(self, task_id: str) -> Dict[str, Any]:
        """获取任务进度信息"""
        task = self.get_task(task_id)
        if not task:
            return {}
        
        progress = {
            'task_id': task.task_id,
            'status': task.status.value,
            'progress_percent': self._calculate_progress_percent(task),
            'created_at': task.created_at.isoformat(),
            'updated_at': task.updated_at.isoformat(),
            'processing_time': task.processing_time,
            'retry_count': task.retry_count,
            'max_retries': task.max_retries,
            'assigned_node': task.assigned_node,
            'queue_name': task.queue_name,
            'error_message': task.error_message
        }
        
        return progress
    
    def _calculate_progress_percent(self, task: Task) -> int:
        """计算任务进度百分比"""
        if task.status == TaskStatus.PENDING:
            return 0
        elif task.status == TaskStatus.QUEUED:
            return 10
        elif task.status == TaskStatus.PROCESSING:
            return 50  # 处理中默认50%，实际进度需要处理节点报告
        elif task.status == TaskStatus.COMPLETED:
            return 100
        elif task.status in [TaskStatus.FAILED, TaskStatus.CANCELLED]:
            return 0
        else:
            return 0
    
    def get_active_tasks_count(self) -> int:
        """获取活跃任务数量"""
        with self.cache_lock:
            return len(self.task_cache)
    
    def get_queue_tasks(self, queue_name: str) -> List[Task]:
        """获取指定队列的任务"""
        with self.cache_lock:
            return [task for task in self.task_cache.values() 
                   if task.queue_name == queue_name and task.status == TaskStatus.QUEUED]
    
    def mark_task_processing(self, task_id: str, node_id: str) -> bool:
        """标记任务为处理中"""
        task = self.get_task(task_id)
        if not task:
            return False
        
        # 如果任务是 PENDING 状态，先转换到 QUEUED
        if task.status == TaskStatus.PENDING:
            if not self.update_task_status(task_id, TaskStatus.QUEUED, assigned_node=node_id):
                return False
        
        return self.update_task_status(
            task_id, 
            TaskStatus.PROCESSING, 
            assigned_node=node_id
        )
    
    def complete_task(self, task_id: str, result_path: str, processing_time: float) -> bool:
        """完成任务"""
        task = self.get_task(task_id)
        if not task:
            return False
        
        # 如果任务不是 PROCESSING 状态，先转换到 PROCESSING
        if task.status == TaskStatus.PENDING:
            if not self.update_task_status(task_id, TaskStatus.QUEUED):
                return False
            if not self.update_task_status(task_id, TaskStatus.PROCESSING):
                return False
        elif task.status == TaskStatus.QUEUED:
            if not self.update_task_status(task_id, TaskStatus.PROCESSING):
                return False
        
        return self.update_task_status(
            task_id,
            TaskStatus.COMPLETED,
            result_path=result_path,
            processing_time=processing_time
        )
    
    def fail_task(self, task_id: str, error_message: str) -> bool:
        """标记任务失败"""
        task = self.get_task(task_id)
        if not task:
            return False
        
        # 如果任务是 PENDING 状态，先转换到 PROCESSING 再转换到 FAILED
        if task.status == TaskStatus.PENDING:
            if not self.update_task_status(task_id, TaskStatus.QUEUED):
                return False
            if not self.update_task_status(task_id, TaskStatus.PROCESSING):
                return False
        elif task.status == TaskStatus.QUEUED:
            if not self.update_task_status(task_id, TaskStatus.PROCESSING):
                return False
        
        return self.update_task_status(
            task_id,
            TaskStatus.FAILED,
            error_message=error_message
        )
    
    def requeue_task(self, task_id: str) -> bool:
        """重新排队任务（用于节点故障恢复）"""
        task = self.get_task(task_id)
        if not task:
            return False
        
        # 重置分配信息
        task.assigned_node = None
        task.queue_name = None
        
        return self.update_task_status(task_id, TaskStatus.PENDING)
    
    def get_node_task_count(self, node_id: str) -> int:
        """获取节点当前任务数量"""
        with self.cache_lock:
            return sum(1 for task in self.task_cache.values() 
                      if task.assigned_node == node_id and task.status == TaskStatus.PROCESSING)
    
    def can_assign_task_to_node(self, node_id: str, max_concurrent: int) -> bool:
        """检查是否可以向节点分配任务"""
        current_count = self.get_node_task_count(node_id)
        return current_count < max_concurrent