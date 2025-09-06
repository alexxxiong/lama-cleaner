"""
状态管理器

负责维护任务和节点的状态信息，提供实时状态更新和查询功能。
集成 Redis 缓存和事件通知机制，支持分布式状态同步。
"""

import logging
import json
import threading
import time
from typing import Dict, List, Optional, Callable, Any, Union
from datetime import datetime, timedelta
from .models import Task, TaskStatus, NodeCapability, NodeStatus
from .config import get_config

logger = logging.getLogger(__name__)


class StateManager:
    """状态管理器
    
    提供分布式状态管理功能，包括：
    - 任务状态管理和同步
    - 节点状态监控
    - 系统指标收集
    - 事件通知机制
    - Redis 缓存集成
    """
    
    def __init__(self, redis_client=None, socketio=None):
        self.config = get_config()
        self.redis = redis_client
        self.socketio = socketio
        
        # 内存状态缓存
        self.task_states: Dict[str, Dict[str, Any]] = {}
        self.node_states: Dict[str, Dict[str, Any]] = {}
        self.system_metrics: Dict[str, Any] = {}
        
        # 线程锁
        self._lock = threading.RLock()
        
        # 状态变更回调
        self.task_callbacks: List[Callable[[str, Dict], None]] = []
        self.node_callbacks: List[Callable[[str, Dict], None]] = []
        self.metrics_callbacks: List[Callable[[Dict], None]] = []
        
        # 事件通知队列
        self._event_queue: List[Dict[str, Any]] = []
        self._event_lock = threading.Lock()
        
        # 启动后台任务
        self._running = True
        self._cleanup_thread = threading.Thread(target=self._cleanup_worker, daemon=True)
        self._event_thread = threading.Thread(target=self._event_worker, daemon=True)
        self._cleanup_thread.start()
        self._event_thread.start()
        
        logger.info("状态管理器已启动")
    
    def update_task_status(self, task: Task):
        """更新任务状态"""
        task_state = {
            'task_id': task.task_id,
            'status': task.status.value,
            'progress': self._calculate_task_progress(task),
            'updated_at': task.updated_at.isoformat(),
            'assigned_node': task.assigned_node,
            'queue_name': task.queue_name,
            'error_message': task.error_message,
            'processing_time': task.processing_time,
            'retry_count': task.retry_count
        }
        
        with self._lock:
            self.task_states[task.task_id] = task_state
        
        # 持久化到 Redis
        if self.redis:
            try:
                self.redis.hset(
                    f"task:{task.task_id}",
                    mapping=task_state
                )
                # 设置过期时间
                self.redis.expire(f"task:{task.task_id}", self.config.completed_task_ttl)
            except Exception as e:
                logger.error(f"Redis 状态更新失败: {e}")
        
        # 实时通知前端
        if self.socketio:
            try:
                self.socketio.emit('task_update', {
                    'task_id': task.task_id,
                    'status': task.status.value,
                    'progress': task_state['progress'],
                    'message': self._get_status_message(task),
                    'timestamp': task_state['updated_at']
                })
            except Exception as e:
                logger.error(f"WebSocket 通知失败: {e}")
        
        # 将事件加入队列进行异步处理
        self._queue_event({
            'type': 'task_status_changed',
            'task_id': task.task_id,
            'task_state': task_state,
            'timestamp': datetime.now().isoformat()
        })
        
        logger.debug(f"任务状态已更新: {task.task_id} -> {task.status.value}")
    
    def get_task_status(self, task_id: str) -> Optional[Dict[str, Any]]:
        """获取任务状态"""
        # 先从内存缓存获取
        with self._lock:
            if task_id in self.task_states:
                return self.task_states[task_id].copy()
        
        # 从 Redis 获取
        if self.redis:
            try:
                task_data = self.redis.hgetall(f"task:{task_id}")
                if task_data:
                    # Redis 返回的是字节，需要解码
                    decoded_data = {k.decode(): v.decode() for k, v in task_data.items()}
                    with self._lock:
                        self.task_states[task_id] = decoded_data
                    return decoded_data
            except Exception as e:
                logger.error(f"从 Redis 获取任务状态失败: {e}")
        
        return None
    
    def update_node_status(self, node: NodeCapability):
        """更新节点状态"""
        node_state = {
            'node_id': node.node_id,
            'node_type': node.node_type.value,
            'status': node.status.value,
            'current_load': node.current_load,
            'max_concurrent_tasks': node.max_concurrent_tasks,
            'total_processed': node.total_processed,
            'last_heartbeat': node.last_heartbeat.isoformat() if node.last_heartbeat else None,
            'gpu_count': node.gpu_count,
            'gpu_memory': node.gpu_memory,
            'cpu_cores': node.cpu_cores,
            'memory_total': node.memory_total,
            'host': node.host,
            'port': node.port
        }
        
        with self._lock:
            self.node_states[node.node_id] = node_state
        
        # 持久化到 Redis
        if self.redis:
            try:
                self.redis.hset(
                    f"node:{node.node_id}",
                    mapping=node_state
                )
                # 设置过期时间（比心跳超时时间长一些）
                self.redis.expire(f"node:{node.node_id}", self.config.node_timeout * 2)
            except Exception as e:
                logger.error(f"Redis 节点状态更新失败: {e}")
        
        # 实时通知前端
        if self.socketio:
            try:
                self.socketio.emit('node_update', node_state)
            except Exception as e:
                logger.error(f"WebSocket 节点通知失败: {e}")
        
        # 将事件加入队列进行异步处理
        self._queue_event({
            'type': 'node_status_changed',
            'node_id': node.node_id,
            'node_state': node_state,
            'timestamp': datetime.now().isoformat()
        })
    
    def get_node_status(self, node_id: str) -> Optional[Dict[str, Any]]:
        """获取节点状态"""
        with self._lock:
            if node_id in self.node_states:
                return self.node_states[node_id].copy()
        
        # 从 Redis 获取
        if self.redis:
            try:
                node_data = self.redis.hgetall(f"node:{node_id}")
                if node_data:
                    decoded_data = {k.decode(): v.decode() for k, v in node_data.items()}
                    with self._lock:
                        self.node_states[node_id] = decoded_data
                    return decoded_data
            except Exception as e:
                logger.error(f"从 Redis 获取节点状态失败: {e}")
        
        return None
    
    def get_all_task_states(self) -> Dict[str, Dict[str, Any]]:
        """获取所有任务状态"""
        with self._lock:
            return {task_id: state.copy() for task_id, state in self.task_states.items()}
    
    def get_all_node_states(self) -> Dict[str, Dict[str, Any]]:
        """获取所有节点状态"""
        with self._lock:
            return {node_id: state.copy() for node_id, state in self.node_states.items()}
    
    def get_tasks_by_status(self, status: TaskStatus) -> List[Dict[str, Any]]:
        """根据状态获取任务列表"""
        with self._lock:
            return [
                state.copy() for state in self.task_states.values()
                if state.get('status') == status.value
            ]
    
    def get_nodes_by_status(self, status: str) -> List[Dict[str, Any]]:
        """根据状态获取节点列表"""
        with self._lock:
            return [
                state.copy() for state in self.node_states.values()
                if state.get('status') == status
            ]
    
    def cancel_task(self, task_id: str) -> bool:
        """取消任务"""
        task_state = self.get_task_status(task_id)
        if not task_state:
            return False
        
        current_status = task_state.get('status')
        if current_status in ['completed', 'failed', 'cancelled']:
            return False
        
        # 更新状态为已取消
        with self._lock:
            if task_id in self.task_states:
                self.task_states[task_id]['status'] = TaskStatus.CANCELLED.value
                self.task_states[task_id]['updated_at'] = datetime.now().isoformat()
        
        # 持久化到 Redis
        if self.redis:
            try:
                self.redis.hset(f"task:{task_id}", "status", TaskStatus.CANCELLED.value)
                self.redis.hset(f"task:{task_id}", "updated_at", datetime.now().isoformat())
            except Exception as e:
                logger.error(f"Redis 取消任务状态更新失败: {e}")
        
        # 如果任务正在处理中，需要发送取消指令给处理节点
        if current_status == 'processing':
            assigned_node = task_state.get('assigned_node')
            if assigned_node:
                self._send_cancel_command(task_id, assigned_node)
        
        # 实时通知前端
        if self.socketio:
            try:
                self.socketio.emit('task_update', {
                    'task_id': task_id,
                    'status': TaskStatus.CANCELLED.value,
                    'message': '任务已取消',
                    'timestamp': datetime.now().isoformat()
                })
            except Exception as e:
                logger.error(f"WebSocket 取消通知失败: {e}")
        
        logger.info(f"任务已取消: {task_id}")
        return True
    
    def update_system_metrics(self, metrics: Dict[str, Any]):
        """更新系统指标"""
        with self._lock:
            self.system_metrics.update(metrics)
            self.system_metrics['updated_at'] = datetime.now().isoformat()
        
        # 持久化到 Redis
        if self.redis:
            try:
                self.redis.hset("system:metrics", mapping=metrics)
                self.redis.expire("system:metrics", 300)  # 5分钟过期
            except Exception as e:
                logger.error(f"Redis 系统指标更新失败: {e}")
        
        # 将事件加入队列进行异步处理
        self._queue_event({
            'type': 'system_metrics_updated',
            'metrics': metrics,
            'timestamp': datetime.now().isoformat()
        })
    
    def get_system_metrics(self) -> Dict[str, Any]:
        """获取系统指标"""
        with self._lock:
            return self.system_metrics.copy()
    
    def cleanup_expired_states(self):
        """清理过期状态"""
        current_time = datetime.now()
        expired_tasks = []
        
        with self._lock:
            for task_id, state in self.task_states.items():
                try:
                    updated_at = datetime.fromisoformat(state['updated_at'])
                    if (current_time - updated_at).total_seconds() > self.config.completed_task_ttl:
                        if state['status'] in ['completed', 'failed', 'cancelled']:
                            expired_tasks.append(task_id)
                except Exception as e:
                    logger.error(f"解析任务时间失败 {task_id}: {e}")
            
            for task_id in expired_tasks:
                del self.task_states[task_id]
        
        if expired_tasks:
            logger.info(f"清理了 {len(expired_tasks)} 个过期任务状态")
    
    def add_task_callback(self, callback: Callable[[str, Dict], None]):
        """添加任务状态变更回调"""
        self.task_callbacks.append(callback)
    
    def add_node_callback(self, callback: Callable[[str, Dict], None]):
        """添加节点状态变更回调"""
        self.node_callbacks.append(callback)
    
    def add_metrics_callback(self, callback: Callable[[Dict], None]):
        """添加系统指标回调"""
        self.metrics_callbacks.append(callback)
    
    def _calculate_task_progress(self, task: Task) -> float:
        """计算任务进度"""
        if task.status == TaskStatus.PENDING:
            return 0.0
        elif task.status == TaskStatus.QUEUED:
            return 10.0
        elif task.status == TaskStatus.PROCESSING:
            # 这里可以根据实际处理进度来计算
            # 目前简单返回50%
            return 50.0
        elif task.status in [TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED]:
            return 100.0
        else:
            return 0.0
    
    def _get_status_message(self, task: Task) -> str:
        """获取状态消息"""
        status_messages = {
            TaskStatus.PENDING: "等待处理",
            TaskStatus.QUEUED: "已加入队列",
            TaskStatus.PROCESSING: "正在处理",
            TaskStatus.COMPLETED: "处理完成",
            TaskStatus.FAILED: f"处理失败: {task.error_message or '未知错误'}",
            TaskStatus.CANCELLED: "已取消"
        }
        return status_messages.get(task.status, "未知状态")
    
    def _send_cancel_command(self, task_id: str, node_id: str):
        """发送取消命令给处理节点"""
        # 这里需要通过控制信道发送取消命令
        # 目前只是记录日志
        logger.info(f"发送取消命令: 任务 {task_id} -> 节点 {node_id}")
        # TODO: 实现实际的取消命令发送逻辑
    
    def shutdown(self):
        """关闭状态管理器"""
        logger.info("正在关闭状态管理器...")
        self._running = False
        
        # 等待后台线程结束
        if self._cleanup_thread.is_alive():
            self._cleanup_thread.join(timeout=5)
        if self._event_thread.is_alive():
            self._event_thread.join(timeout=5)
        
        logger.info("状态管理器已关闭")
    
    def _cleanup_worker(self):
        """后台清理任务"""
        while self._running:
            try:
                self.cleanup_expired_states()
                time.sleep(self.config.task_cleanup_interval)
            except Exception as e:
                logger.error(f"状态清理任务失败: {e}")
                time.sleep(60)  # 出错时等待1分钟再重试
    
    def _event_worker(self):
        """后台事件处理任务"""
        while self._running:
            try:
                self._process_event_queue()
                time.sleep(1)  # 每秒处理一次事件队列
            except Exception as e:
                logger.error(f"事件处理任务失败: {e}")
                time.sleep(5)  # 出错时等待5秒再重试
    
    def _process_event_queue(self):
        """处理事件队列"""
        events_to_process = []
        
        with self._event_lock:
            if self._event_queue:
                events_to_process = self._event_queue.copy()
                self._event_queue.clear()
        
        for event in events_to_process:
            try:
                self._handle_event(event)
            except Exception as e:
                logger.error(f"处理事件失败: {event}, 错误: {e}")
    
    def _handle_event(self, event: Dict[str, Any]):
        """处理单个事件"""
        event_type = event.get('type')
        
        if event_type == 'task_status_changed':
            self._notify_task_status_change(event)
        elif event_type == 'node_status_changed':
            self._notify_node_status_change(event)
        elif event_type == 'system_metrics_updated':
            self._notify_metrics_update(event)
        else:
            logger.warning(f"未知事件类型: {event_type}")
    
    def _notify_task_status_change(self, event: Dict[str, Any]):
        """通知任务状态变更"""
        task_id = event.get('task_id')
        task_state = event.get('task_state')
        
        # WebSocket 实时通知
        if self.socketio and task_state:
            try:
                self.socketio.emit('task_status_changed', {
                    'task_id': task_id,
                    'status': task_state.get('status'),
                    'progress': task_state.get('progress', 0),
                    'message': task_state.get('message', ''),
                    'timestamp': task_state.get('updated_at'),
                    'error_message': task_state.get('error_message')
                })
            except Exception as e:
                logger.error(f"WebSocket 任务状态通知失败: {e}")
        
        # 触发回调
        for callback in self.task_callbacks:
            try:
                callback(task_id, task_state)
            except Exception as e:
                logger.error(f"任务状态回调失败: {e}")
    
    def _notify_node_status_change(self, event: Dict[str, Any]):
        """通知节点状态变更"""
        node_id = event.get('node_id')
        node_state = event.get('node_state')
        
        # WebSocket 实时通知
        if self.socketio and node_state:
            try:
                self.socketio.emit('node_status_changed', {
                    'node_id': node_id,
                    'status': node_state.get('status'),
                    'current_load': node_state.get('current_load', 0),
                    'last_heartbeat': node_state.get('last_heartbeat'),
                    'timestamp': datetime.now().isoformat()
                })
            except Exception as e:
                logger.error(f"WebSocket 节点状态通知失败: {e}")
        
        # 触发回调
        for callback in self.node_callbacks:
            try:
                callback(node_id, node_state)
            except Exception as e:
                logger.error(f"节点状态回调失败: {e}")
    
    def _notify_metrics_update(self, event: Dict[str, Any]):
        """通知系统指标更新"""
        metrics = event.get('metrics')
        
        # WebSocket 实时通知
        if self.socketio and metrics:
            try:
                self.socketio.emit('system_metrics_updated', {
                    'metrics': metrics,
                    'timestamp': datetime.now().isoformat()
                })
            except Exception as e:
                logger.error(f"WebSocket 系统指标通知失败: {e}")
        
        # 触发回调
        for callback in self.metrics_callbacks:
            try:
                callback(metrics)
            except Exception as e:
                logger.error(f"系统指标回调失败: {e}")
    
    def _queue_event(self, event: Dict[str, Any]):
        """将事件加入队列"""
        with self._event_lock:
            self._event_queue.append(event)
    
    def get_task_statistics(self) -> Dict[str, int]:
        """获取任务统计信息"""
        stats = {
            'pending': 0,
            'queued': 0,
            'processing': 0,
            'completed': 0,
            'failed': 0,
            'cancelled': 0,
            'total': 0
        }
        
        with self._lock:
            for task_state in self.task_states.values():
                status = task_state.get('status', 'unknown')
                if status in stats:
                    stats[status] += 1
                stats['total'] += 1
        
        return stats
    
    def get_node_statistics(self) -> Dict[str, Any]:
        """获取节点统计信息"""
        stats = {
            'online': 0,
            'offline': 0,
            'busy': 0,
            'error': 0,
            'total': 0,
            'total_load': 0,
            'total_capacity': 0
        }
        
        with self._lock:
            for node_state in self.node_states.values():
                status = node_state.get('status', 'unknown')
                if status in stats:
                    stats[status] += 1
                stats['total'] += 1
                stats['total_load'] += node_state.get('current_load', 0)
                stats['total_capacity'] += node_state.get('max_concurrent_tasks', 0)
        
        return stats
    
    def get_queue_statistics(self) -> Dict[str, Dict[str, int]]:
        """获取队列统计信息"""
        queue_stats = {}
        
        with self._lock:
            # 按队列统计任务数量
            for task_state in self.task_states.values():
                queue_name = task_state.get('queue_name', 'unknown')
                status = task_state.get('status', 'unknown')
                
                if queue_name not in queue_stats:
                    queue_stats[queue_name] = {
                        'pending': 0,
                        'processing': 0,
                        'completed': 0,
                        'failed': 0,
                        'total': 0
                    }
                
                if status in queue_stats[queue_name]:
                    queue_stats[queue_name][status] += 1
                queue_stats[queue_name]['total'] += 1
        
        return queue_stats
    
    def get_system_status(self) -> Dict[str, Any]:
        """获取系统整体状态"""
        return {
            'task_statistics': self.get_task_statistics(),
            'node_statistics': self.get_node_statistics(),
            'queue_statistics': self.get_queue_statistics(),
            'system_metrics': self.get_system_metrics(),
            'timestamp': datetime.now().isoformat()
        }
    
    def subscribe_to_task_events(self, callback: Callable[[str, Dict], None]):
        """订阅任务事件"""
        self.add_task_callback(callback)
        logger.debug("已添加任务事件订阅")
    
    def subscribe_to_node_events(self, callback: Callable[[str, Dict], None]):
        """订阅节点事件"""
        self.add_node_callback(callback)
        logger.debug("已添加节点事件订阅")
    
    def subscribe_to_metrics_events(self, callback: Callable[[Dict], None]):
        """订阅系统指标事件"""
        self.add_metrics_callback(callback)
        logger.debug("已添加系统指标事件订阅")
    
    def unsubscribe_from_task_events(self, callback: Callable[[str, Dict], None]):
        """取消订阅任务事件"""
        if callback in self.task_callbacks:
            self.task_callbacks.remove(callback)
            logger.debug("已移除任务事件订阅")
    
    def unsubscribe_from_node_events(self, callback: Callable[[str, Dict], None]):
        """取消订阅节点事件"""
        if callback in self.node_callbacks:
            self.node_callbacks.remove(callback)
            logger.debug("已移除节点事件订阅")
    
    def unsubscribe_from_metrics_events(self, callback: Callable[[Dict], None]):
        """取消订阅系统指标事件"""
        if callback in self.metrics_callbacks:
            self.metrics_callbacks.remove(callback)
            logger.debug("已移除系统指标事件订阅")
    
    def batch_update_task_states(self, tasks: List[Task]):
        """批量更新任务状态"""
        updated_tasks = []
        
        for task in tasks:
            try:
                self.update_task_status(task)
                updated_tasks.append(task.task_id)
            except Exception as e:
                logger.error(f"批量更新任务状态失败 {task.task_id}: {e}")
        
        logger.info(f"批量更新了 {len(updated_tasks)} 个任务状态")
        return updated_tasks
    
    def batch_update_node_states(self, nodes: List[NodeCapability]):
        """批量更新节点状态"""
        updated_nodes = []
        
        for node in nodes:
            try:
                self.update_node_status(node)
                updated_nodes.append(node.node_id)
            except Exception as e:
                logger.error(f"批量更新节点状态失败 {node.node_id}: {e}")
        
        logger.info(f"批量更新了 {len(updated_nodes)} 个节点状态")
        return updated_nodes
    
    def get_tasks_by_node(self, node_id: str) -> List[Dict[str, Any]]:
        """获取指定节点的任务列表"""
        with self._lock:
            return [
                state.copy() for state in self.task_states.values()
                if state.get('assigned_node') == node_id
            ]
    
    def get_tasks_by_queue(self, queue_name: str) -> List[Dict[str, Any]]:
        """获取指定队列的任务列表"""
        with self._lock:
            return [
                state.copy() for state in self.task_states.values()
                if state.get('queue_name') == queue_name
            ]
    
    def get_active_tasks(self) -> List[Dict[str, Any]]:
        """获取活跃任务列表（排队中和处理中）"""
        active_statuses = [TaskStatus.QUEUED.value, TaskStatus.PROCESSING.value]
        with self._lock:
            return [
                state.copy() for state in self.task_states.values()
                if state.get('status') in active_statuses
            ]
    
    def get_completed_tasks(self, limit: int = 100) -> List[Dict[str, Any]]:
        """获取已完成任务列表"""
        completed_statuses = [TaskStatus.COMPLETED.value, TaskStatus.FAILED.value, TaskStatus.CANCELLED.value]
        with self._lock:
            completed_tasks = [
                state.copy() for state in self.task_states.values()
                if state.get('status') in completed_statuses
            ]
            
            # 按更新时间排序，最新的在前
            completed_tasks.sort(
                key=lambda x: x.get('updated_at', ''),
                reverse=True
            )
            
            return completed_tasks[:limit]