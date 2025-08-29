"""
任务调度器

负责任务的提交、路由、调度和批量处理。
集成现有的 Flask API 端点，支持任务优先级处理。
"""

import logging
from typing import Dict, List, Optional, Callable, Any
from datetime import datetime
import threading
import time
import queue
from concurrent.futures import ThreadPoolExecutor

from .models import Task, TaskStatus, TaskType, TaskPriority, NodeCapability
from .task_manager import TaskManager
from .queue_manager import QueueManager
from .node_manager import NodeManager
from .config import get_config

logger = logging.getLogger(__name__)


class TaskSubmissionRequest:
    """任务提交请求"""
    
    def __init__(self, 
                 task_type: TaskType,
                 image_path: str,
                 config: Dict[str, Any],
                 mask_path: Optional[str] = None,
                 priority: TaskPriority = TaskPriority.NORMAL,
                 user_id: Optional[str] = None,
                 session_id: Optional[str] = None,
                 callback: Optional[Callable[[Task], None]] = None):
        self.task_type = task_type
        self.image_path = image_path
        self.mask_path = mask_path
        self.config = config
        self.priority = priority
        self.user_id = user_id
        self.session_id = session_id
        self.callback = callback
        self.submitted_at = datetime.now()


class TaskScheduler:
    """任务调度器"""
    
    def __init__(self):
        self.config = get_config()
        self.task_manager = TaskManager()
        self.queue_manager = QueueManager()
        self.node_manager = NodeManager()
        
        # 调度队列
        self.submission_queue = queue.Queue()
        self.scheduling_queue = queue.PriorityQueue()
        
        # 线程池
        self.submission_executor = ThreadPoolExecutor(
            max_workers=self.config.max_concurrent_tasks_per_node,
            thread_name_prefix="task-submission"
        )
        self.scheduling_executor = ThreadPoolExecutor(
            max_workers=2,
            thread_name_prefix="task-scheduling"
        )
        
        # 状态管理
        self._running = False
        self._submission_thread = None
        self._scheduling_thread = None
        
        # 统计信息
        self.stats = {
            'submitted_tasks': 0,
            'scheduled_tasks': 0,
            'failed_submissions': 0,
            'failed_scheduling': 0
        }
        
        # 注册任务状态回调
        self.task_manager.add_status_callback(self._on_task_status_change)
    
    def start(self):
        """启动调度器"""
        if self._running:
            return
        
        self._running = True
        
        # 启动组件
        self.task_manager.start()
        self.queue_manager.start()
        self.node_manager.start()
        
        # 启动调度线程
        self._start_submission_thread()
        self._start_scheduling_thread()
        
        logger.info("任务调度器已启动")
    
    def stop(self):
        """停止调度器"""
        if not self._running:
            return
        
        self._running = False
        
        # 停止线程
        if self._submission_thread and self._submission_thread.is_alive():
            self._submission_thread.join(timeout=5)
        if self._scheduling_thread and self._scheduling_thread.is_alive():
            self._scheduling_thread.join(timeout=5)
        
        # 关闭线程池
        self.submission_executor.shutdown(wait=True)
        self.scheduling_executor.shutdown(wait=True)
        
        # 停止组件
        self.task_manager.stop()
        self.queue_manager.stop()
        self.node_manager.stop()
        
        logger.info("任务调度器已停止")
    
    def submit_task(self, request: TaskSubmissionRequest) -> str:
        """提交任务"""
        try:
            # 创建任务
            task = self.task_manager.create_task(
                task_type=request.task_type,
                image_path=request.image_path,
                config=request.config,
                mask_path=request.mask_path,
                priority=request.priority,
                user_id=request.user_id,
                session_id=request.session_id
            )
            
            # 添加到调度队列（使用负优先级实现高优先级优先）
            priority_value = -request.priority.value
            self.scheduling_queue.put((priority_value, task.created_at, task.task_id, request.callback))
            
            self.stats['submitted_tasks'] += 1
            logger.info(f"任务已提交: {task.task_id}, 优先级: {request.priority.value}")
            
            return task.task_id
            
        except Exception as e:
            self.stats['failed_submissions'] += 1
            logger.error(f"任务提交失败: {e}")
            raise
    
    def submit_inpaint_task(self, 
                           image_path: str,
                           mask_path: str,
                           config: Dict[str, Any],
                           priority: TaskPriority = TaskPriority.NORMAL,
                           user_id: Optional[str] = None,
                           session_id: Optional[str] = None,
                           callback: Optional[Callable[[Task], None]] = None) -> str:
        """提交图像修复任务（兼容现有 API）"""
        request = TaskSubmissionRequest(
            task_type=TaskType.INPAINT,
            image_path=image_path,
            mask_path=mask_path,
            config=config,
            priority=priority,
            user_id=user_id,
            session_id=session_id,
            callback=callback
        )
        return self.submit_task(request)
    
    def submit_plugin_task(self,
                          image_path: str,
                          plugin_name: str,
                          config: Dict[str, Any],
                          priority: TaskPriority = TaskPriority.NORMAL,
                          user_id: Optional[str] = None,
                          session_id: Optional[str] = None,
                          callback: Optional[Callable[[Task], None]] = None) -> str:
        """提交插件处理任务"""
        plugin_config = config.copy()
        plugin_config['plugin_name'] = plugin_name
        
        request = TaskSubmissionRequest(
            task_type=TaskType.PLUGIN,
            image_path=image_path,
            config=plugin_config,
            priority=priority,
            user_id=user_id,
            session_id=session_id,
            callback=callback
        )
        return self.submit_task(request)
    
    def submit_batch_tasks(self, requests: List[TaskSubmissionRequest]) -> List[str]:
        """批量提交任务"""
        task_ids = []
        
        for request in requests:
            try:
                task_id = self.submit_task(request)
                task_ids.append(task_id)
            except Exception as e:
                logger.error(f"批量任务提交失败: {e}")
                # 继续处理其他任务
                continue
        
        logger.info(f"批量提交完成: {len(task_ids)}/{len(requests)} 个任务成功")
        return task_ids
    
    def cancel_task(self, task_id: str) -> bool:
        """取消任务"""
        return self.task_manager.cancel_task(task_id)
    
    def get_task_status(self, task_id: str) -> Optional[Dict[str, Any]]:
        """获取任务状态"""
        return self.task_manager.get_task_progress(task_id)
    
    def get_user_tasks(self, user_id: str, limit: Optional[int] = None) -> List[Task]:
        """获取用户任务"""
        return self.task_manager.get_tasks_by_user(user_id, limit)
    
    def get_session_tasks(self, session_id: str) -> List[Task]:
        """获取会话任务"""
        return self.task_manager.get_tasks_by_session(session_id)
    
    def get_queue_status(self) -> Dict[str, Any]:
        """获取队列状态"""
        return {
            'submission_queue_size': self.submission_queue.qsize(),
            'scheduling_queue_size': self.scheduling_queue.qsize(),
            'queue_stats': self.queue_manager.get_queue_statistics(),
            'node_stats': self.node_manager.get_node_statistics(),
            'task_stats': self.task_manager.get_task_statistics()
        }
    
    def get_scheduler_statistics(self) -> Dict[str, Any]:
        """获取调度器统计信息"""
        return {
            **self.stats,
            'queue_status': self.get_queue_status(),
            'active_nodes': len(self.node_manager.get_online_nodes()),
            'total_tasks': self.task_manager.get_task_statistics().get('total', 0)
        }
    
    def _start_submission_thread(self):
        """启动任务提交线程"""
        def submission_worker():
            while self._running:
                try:
                    # 处理提交队列中的任务
                    if not self.submission_queue.empty():
                        request = self.submission_queue.get(timeout=1)
                        self.submission_executor.submit(self._process_submission, request)
                    else:
                        time.sleep(0.1)
                except queue.Empty:
                    continue
                except Exception as e:
                    logger.error(f"任务提交线程错误: {e}")
                    time.sleep(1)
        
        self._submission_thread = threading.Thread(target=submission_worker, daemon=True)
        self._submission_thread.start()
        logger.info("任务提交线程已启动")
    
    def _start_scheduling_thread(self):
        """启动任务调度线程"""
        def scheduling_worker():
            while self._running:
                try:
                    # 处理调度队列中的任务
                    if not self.scheduling_queue.empty():
                        priority, created_at, task_id, callback = self.scheduling_queue.get(timeout=1)
                        self.scheduling_executor.submit(self._process_scheduling, task_id, callback)
                    else:
                        time.sleep(0.1)
                except queue.Empty:
                    continue
                except Exception as e:
                    logger.error(f"任务调度线程错误: {e}")
                    time.sleep(1)
        
        self._scheduling_thread = threading.Thread(target=scheduling_worker, daemon=True)
        self._scheduling_thread.start()
        logger.info("任务调度线程已启动")
    
    def _process_submission(self, request: TaskSubmissionRequest):
        """处理任务提交"""
        try:
            # 这里可以添加额外的提交前处理逻辑
            # 比如文件验证、权限检查等
            pass
        except Exception as e:
            logger.error(f"任务提交处理失败: {e}")
    
    def _process_scheduling(self, task_id: str, callback: Optional[Callable[[Task], None]]):
        """处理任务调度"""
        try:
            task = self.task_manager.get_task(task_id)
            if not task:
                logger.warning(f"调度任务不存在: {task_id}")
                return
            
            if task.status != TaskStatus.PENDING:
                logger.warning(f"任务状态不是待处理: {task_id}, 状态: {task.status.value}")
                return
            
            # 分析任务需求
            task_requirements = self._analyze_task_requirements(task)
            
            # 查找合适的节点
            suitable_nodes = self._find_suitable_nodes(task_requirements)
            
            if not suitable_nodes:
                logger.warning(f"没有找到合适的节点处理任务: {task_id}")
                # 任务保持在待处理状态，等待合适的节点上线
                return
            
            # 选择最佳节点
            best_node = self._select_best_node(suitable_nodes, task)
            
            # 获取合适的队列
            queue_name = self._select_queue_for_task(task, best_node)
            
            if not queue_name:
                logger.warning(f"没有找到合适的队列处理任务: {task_id}")
                return
            
            # 分配任务给节点
            if self.task_manager.assign_task_to_node(task_id, best_node.node_id, queue_name):
                # 发送任务到队列
                self.queue_manager.send_task_to_queue(queue_name, task)
                
                self.stats['scheduled_tasks'] += 1
                logger.info(f"任务已调度: {task_id} -> 节点: {best_node.node_id}, 队列: {queue_name}")
                
                # 执行回调
                if callback:
                    try:
                        callback(task)
                    except Exception as e:
                        logger.error(f"任务回调执行失败: {e}")
            else:
                logger.error(f"任务分配失败: {task_id}")
                self.stats['failed_scheduling'] += 1
                
        except Exception as e:
            logger.error(f"任务调度处理失败 {task_id}: {e}")
            self.stats['failed_scheduling'] += 1
    
    def _analyze_task_requirements(self, task: Task) -> Dict[str, Any]:
        """分析任务需求"""
        requirements = {
            'task_type': task.task_type,
            'gpu_required': False,
            'min_memory': 1024,  # MB
            'min_cpu_cores': 1,
            'required_models': [],
            'estimated_processing_time': 30  # 秒
        }
        
        # 根据任务类型和配置分析需求
        if task.task_type == TaskType.INPAINT:
            model = task.config.get('model', 'lama')
            
            if model in ['sd15', 'sd21', 'sdxl']:
                requirements['gpu_required'] = True
                requirements['min_memory'] = 8192
                requirements['estimated_processing_time'] = 60
            elif model in ['lama', 'mat', 'fcf']:
                requirements['gpu_required'] = task.config.get('use_gpu', True)
                requirements['min_memory'] = 4096 if requirements['gpu_required'] else 2048
                requirements['estimated_processing_time'] = 30
            
            requirements['required_models'] = [model]
            
        elif task.task_type == TaskType.PLUGIN:
            plugin_name = task.config.get('plugin_name', '')
            
            if plugin_name in ['realesrgan', 'gfpgan']:
                requirements['gpu_required'] = True
                requirements['min_memory'] = 4096
            elif plugin_name in ['remove_bg', 'interactive_seg']:
                requirements['gpu_required'] = task.config.get('use_gpu', False)
                requirements['min_memory'] = 2048
        
        return requirements
    
    def _find_suitable_nodes(self, requirements: Dict[str, Any]) -> List[NodeCapability]:
        """查找合适的节点"""
        online_nodes = self.node_manager.get_online_nodes()
        suitable_nodes = []
        
        for node in online_nodes:
            if self._node_meets_requirements(node, requirements):
                suitable_nodes.append(node)
        
        return suitable_nodes
    
    def _node_meets_requirements(self, node: NodeCapability, requirements: Dict[str, Any]) -> bool:
        """检查节点是否满足需求"""
        # 检查 GPU 需求
        if requirements.get('gpu_required', False) and not node.has_gpu():
            return False
        
        # 检查内存需求
        if node.memory_total < requirements.get('min_memory', 0):
            return False
        
        # 检查 CPU 核心数
        if node.cpu_cores < requirements.get('min_cpu_cores', 1):
            return False
        
        # 检查模型支持
        required_models = requirements.get('required_models', [])
        for model in required_models:
            if model not in node.supported_models:
                return False
        
        # 检查任务类型支持
        task_type = requirements['task_type']
        if task_type not in node.supported_tasks:
            return False
        
        # 检查节点负载
        if not self.task_manager.can_assign_task_to_node(
            node.node_id, node.max_concurrent_tasks
        ):
            return False
        
        return True
    
    def _select_best_node(self, nodes: List[NodeCapability], task: Task) -> NodeCapability:
        """选择最佳节点"""
        if not nodes:
            return None
        
        # 计算节点评分
        node_scores = []
        for node in nodes:
            score = self._calculate_node_score(node, task)
            node_scores.append((score, node))
        
        # 按评分排序，选择最高分的节点
        node_scores.sort(key=lambda x: x[0], reverse=True)
        return node_scores[0][1]
    
    def _calculate_node_score(self, node: NodeCapability, task: Task) -> float:
        """计算节点评分"""
        score = 0.0
        
        # 基础分数
        score += 10.0
        
        # 负载评分（负载越低分数越高）
        current_load = self.task_manager.get_node_task_count(node.node_id)
        load_ratio = current_load / node.max_concurrent_tasks
        score += (1.0 - load_ratio) * 20.0
        
        # 硬件评分
        if node.has_gpu():
            score += 15.0
            score += min(node.gpu_memory / 1024, 10.0)  # GPU 内存评分
        
        score += min(node.cpu_cores, 10.0)  # CPU 核心数评分
        score += min(node.memory_total / 1024, 10.0)  # 内存评分
        
        # 历史性能评分
        score += min(node.total_processed / 100, 5.0)
        
        return score
    
    def _select_queue_for_task(self, task: Task, node: NodeCapability) -> Optional[str]:
        """为任务选择队列"""
        # 获取节点可订阅的队列
        available_queues = node.get_queue_subscriptions()
        
        if not available_queues:
            return None
        
        # 根据任务需求选择最合适的队列
        task_requirements = self._analyze_task_requirements(task)
        
        if task_requirements.get('gpu_required', False):
            min_memory = task_requirements.get('min_memory', 0)
            if min_memory >= 8192 and 'gpu-high' in available_queues:
                return 'gpu-high'
            elif min_memory >= 4096 and 'gpu-medium' in available_queues:
                return 'gpu-medium'
            elif 'gpu-low' in available_queues:
                return 'gpu-low'
        else:
            min_cpu_cores = task_requirements.get('min_cpu_cores', 1)
            if min_cpu_cores >= 8 and 'cpu-intensive' in available_queues:
                return 'cpu-intensive'
            elif 'cpu-light' in available_queues:
                return 'cpu-light'
        
        # 如果没有找到合适的队列，返回第一个可用队列
        return available_queues[0] if available_queues else None
    
    def _on_task_status_change(self, task: Task):
        """任务状态变更回调"""
        # 这里可以添加状态变更的处理逻辑
        # 比如通知前端、更新统计信息等
        pass


# 全局调度器实例
_scheduler_instance = None


def get_scheduler() -> TaskScheduler:
    """获取全局调度器实例"""
    global _scheduler_instance
    if _scheduler_instance is None:
        _scheduler_instance = TaskScheduler()
    return _scheduler_instance