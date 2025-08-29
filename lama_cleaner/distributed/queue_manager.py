"""
队列管理器

基于 ZeroMQ 的队列管理系统，负责任务路由和队列监控。
"""

import logging
import zmq
import json
import threading
import time
from typing import Dict, List, Optional, Any
from datetime import datetime
from .models import Task, QueueConfig, TaskPriority
from .config import get_config

logger = logging.getLogger(__name__)


class QueueManager:
    """队列管理器"""
    
    def __init__(self):
        self.config = get_config()
        self.context = zmq.Context(self.config.zeromq.context_io_threads)
        self.queues: Dict[str, Dict[str, Any]] = {}
        self.queue_stats: Dict[str, Dict[str, int]] = {}
        self._running = False
        self._stats_thread = None
        self._lock = threading.RLock()
    
    def start(self):
        """启动队列管理器"""
        self._setup_queues()
        self._running = True
        self._start_stats_thread()
        logger.info("队列管理器已启动")
    
    def stop(self):
        """停止队列管理器"""
        self._running = False
        
        if self._stats_thread and self._stats_thread.is_alive():
            self._stats_thread.join(timeout=5)
        
        # 关闭所有队列
        for queue_info in self.queues.values():
            if 'socket' in queue_info:
                queue_info['socket'].close()
        
        self.context.term()
        logger.info("队列管理器已停止")
    
    def send_task_to_queue(self, queue_name: str, task: Task) -> bool:
        """发送任务到队列（别名方法）"""
        return self.send_task(queue_name, task)
    
    def remove_task_from_queue(self, queue_name: str, task_id: str) -> bool:
        """从队列中移除任务"""
        try:
            if queue_name not in self.queues:
                logger.warning(f"队列不存在: {queue_name}")
                return False
            
            # 注意：ZeroMQ 的 PUSH/PULL 模式不支持直接移除特定消息
            # 这里只是一个占位实现，实际需要根据具体的队列实现来处理
            logger.info(f"从队列移除任务: {queue_name}, 任务: {task_id}")
            
            # 更新统计信息
            with self._lock:
                if self.queue_stats[queue_name]['pending_count'] > 0:
                    self.queue_stats[queue_name]['pending_count'] -= 1
                    self.queue_stats[queue_name]['last_updated'] = datetime.now()
            
            return True
            
        except Exception as e:
            logger.error(f"从队列移除任务失败 {queue_name}/{task_id}: {e}")
            return False
    
    def get_queue_statistics(self) -> Dict[str, Any]:
        """获取队列统计信息（别名方法）"""
        return self.get_queue_stats()
    
    def _setup_queues(self):
        """初始化所有队列"""
        for queue_name, queue_config in self.config.queues.items():
            try:
                socket = self.context.socket(zmq.PUSH)
                socket.setsockopt(zmq.LINGER, self.config.zeromq.socket_linger)
                socket.bind(f"tcp://*:{queue_config.port}")
                
                self.queues[queue_name] = {
                    'socket': socket,
                    'config': queue_config,
                    'created_at': datetime.now()
                }
                
                self.queue_stats[queue_name] = {
                    'pending_count': 0,
                    'processing_count': 0,
                    'completed_count': 0,
                    'failed_count': 0,
                    'total_sent': 0,
                    'last_updated': datetime.now()
                }
                
                logger.info(f"队列已创建: {queue_name} (端口: {queue_config.port})")
                
            except Exception as e:
                logger.error(f"创建队列失败 {queue_name}: {e}")
                raise
    
    def route_task(self, task: Task) -> Optional[str]:
        """根据任务需求路由到合适的队列"""
        required_resources = self._analyze_task_requirements(task)
        suitable_queues = self._find_suitable_queues(required_resources)
        
        if not suitable_queues:
            logger.warning(f"未找到适合的队列: 任务 {task.task_id}")
            return None
        
        # 选择负载最轻的队列
        selected_queue = min(suitable_queues, 
                           key=lambda q: self.queue_stats[q]['pending_count'])
        
        logger.debug(f"任务路由: {task.task_id} -> {selected_queue}")
        return selected_queue
    
    def send_task(self, queue_name: str, task: Task) -> bool:
        """发送任务到指定队列"""
        if queue_name not in self.queues:
            logger.error(f"队列不存在: {queue_name}")
            return False
        
        try:
            # 检查队列容量
            if not self._check_queue_capacity(queue_name):
                logger.warning(f"队列容量已满: {queue_name}")
                return False
            
            # 序列化任务数据
            task_data = self._serialize_task(task)
            
            # 发送任务
            socket = self.queues[queue_name]['socket']
            socket.send_multipart([
                queue_name.encode('utf-8'),
                task.task_id.encode('utf-8'),
                str(task.priority.value).encode('utf-8'),
                task_data
            ])
            
            # 更新统计信息
            with self._lock:
                self.queue_stats[queue_name]['pending_count'] += 1
                self.queue_stats[queue_name]['total_sent'] += 1
                self.queue_stats[queue_name]['last_updated'] = datetime.now()
            
            logger.info(f"任务已发送: {task.task_id} -> {queue_name}")
            return True
            
        except Exception as e:
            logger.error(f"发送任务失败: {task.task_id} -> {queue_name}: {e}")
            return False
    
    def update_queue_stats(self, queue_name: str, stat_type: str, delta: int = 1):
        """更新队列统计信息"""
        if queue_name not in self.queue_stats:
            return
        
        with self._lock:
            if stat_type in self.queue_stats[queue_name]:
                self.queue_stats[queue_name][stat_type] += delta
                self.queue_stats[queue_name]['last_updated'] = datetime.now()
    
    def get_queue_stats(self, queue_name: Optional[str] = None) -> Dict[str, Any]:
        """获取队列统计信息"""
        with self._lock:
            if queue_name:
                return self.queue_stats.get(queue_name, {}).copy()
            return {name: stats.copy() for name, stats in self.queue_stats.items()}
    
    def get_queue_info(self, queue_name: Optional[str] = None) -> Dict[str, Any]:
        """获取队列信息"""
        if queue_name:
            if queue_name in self.queues:
                queue_info = self.queues[queue_name].copy()
                queue_info['stats'] = self.get_queue_stats(queue_name)
                # 移除 socket 对象（不可序列化）
                queue_info.pop('socket', None)
                return queue_info
            return {}
        
        result = {}
        for name in self.queues:
            result[name] = self.get_queue_info(name)
        return result
    
    def _analyze_task_requirements(self, task: Task) -> Dict[str, Any]:
        """分析任务资源需求"""
        requirements = {}
        
        # 基于任务类型确定需求
        if task.task_type.value == "inpaint":
            model = task.config.get('model', 'lama')
            
            # GPU 需求分析
            if model in ['sd15', 'sd21', 'sdxl']:
                requirements['gpu'] = True
                requirements['gpu_memory'] = 8192 if model == 'sdxl' else 4096
            elif model in ['lama', 'mat', 'fcf']:
                requirements['gpu'] = task.config.get('device', 'cpu') == 'cuda'
                requirements['gpu_memory'] = 2048 if requirements.get('gpu') else 0
            else:
                requirements['gpu'] = False
                requirements['gpu_memory'] = 0
            
            # CPU 需求分析
            if not requirements.get('gpu'):
                requirements['cpu_cores'] = 4 if model in ['zits', 'mat'] else 2
                requirements['memory'] = 8192 if model in ['zits', 'mat'] else 4096
            
            requirements['models'] = [model]
            
        elif task.task_type.value == "plugin":
            plugin_name = task.config.get('name', '')
            
            if plugin_name in ['realesrgan', 'gfpgan']:
                requirements['gpu'] = True
                requirements['gpu_memory'] = 2048
            else:
                requirements['gpu'] = False
                requirements['cpu_cores'] = 2
                requirements['memory'] = 4096
        
        # 优先级影响
        if task.priority == TaskPriority.URGENT:
            requirements['priority_boost'] = True
        
        return requirements
    
    def _find_suitable_queues(self, requirements: Dict[str, Any]) -> List[str]:
        """查找适合的队列"""
        suitable_queues = []
        
        for queue_name, queue_config in self.config.queues.items():
            if self._queue_matches_requirements(queue_config, requirements):
                suitable_queues.append(queue_name)
        
        return suitable_queues
    
    def _queue_matches_requirements(self, queue_config: QueueConfig, requirements: Dict[str, Any]) -> bool:
        """检查队列是否满足需求"""
        queue_reqs = queue_config.requirements
        
        # 检查 GPU 需求
        if requirements.get('gpu', False):
            # 任务需要 GPU，队列必须支持 GPU
            if not queue_reqs.get('gpu', False):
                return False
            
            required_gpu_memory = requirements.get('gpu_memory', 0)
            queue_gpu_memory = queue_reqs.get('gpu_memory', 0)
            if required_gpu_memory > queue_gpu_memory:
                return False
        else:
            # 任务不需要 GPU，但如果队列要求 GPU，则不匹配
            if queue_reqs.get('gpu', False):
                return False
        
        # 检查 CPU 需求（仅当任务不需要 GPU 时）
        if not requirements.get('gpu', False):
            required_cpu_cores = requirements.get('cpu_cores', 0)
            queue_cpu_cores = queue_reqs.get('cpu_cores', 0)
            if required_cpu_cores > queue_cpu_cores:
                return False
            
            required_memory = requirements.get('memory', 0)
            queue_memory = queue_reqs.get('memory', 0)
            if required_memory > queue_memory:
                return False
        
        # 检查模型支持
        required_models = requirements.get('models', [])
        queue_models = queue_reqs.get('models', [])
        if required_models and queue_models and not any(model in queue_models for model in required_models):
            return False
        
        return True
    
    def _check_queue_capacity(self, queue_name: str) -> bool:
        """检查队列容量"""
        if queue_name not in self.config.queues:
            return False
        
        max_size = self.config.queues[queue_name].max_size
        current_size = self.queue_stats[queue_name]['pending_count']
        
        return current_size < max_size
    
    def _serialize_task(self, task: Task) -> bytes:
        """序列化任务数据"""
        task_dict = task.to_dict()
        return json.dumps(task_dict, ensure_ascii=False).encode('utf-8')
    
    def _start_stats_thread(self):
        """启动统计信息更新线程"""
        def stats_worker():
            while self._running:
                try:
                    self._update_queue_metrics()
                    time.sleep(self.config.monitoring.metrics_interval)
                except Exception as e:
                    logger.error(f"更新队列指标失败: {e}")
                    time.sleep(10)
        
        self._stats_thread = threading.Thread(target=stats_worker, daemon=True)
        self._stats_thread.start()
        logger.info("队列统计线程已启动")
    
    def _update_queue_metrics(self):
        """更新队列指标"""
        # 这里可以添加更多的指标收集逻辑
        # 例如：队列深度监控、吞吐量计算等
        pass