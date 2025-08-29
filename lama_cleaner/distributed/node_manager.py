"""
节点管理器

负责处理节点的注册、发现、监控和管理。
"""

import logging
import threading
import time
import zmq
from typing import Dict, List, Optional, Callable
from datetime import datetime, timedelta
from .models import NodeCapability, NodeStatus, Task
from .config import get_config

logger = logging.getLogger(__name__)


class NodeManager:
    """节点管理器"""
    
    def __init__(self):
        self.config = get_config()
        self.context = zmq.Context()
        self.nodes: Dict[str, NodeCapability] = {}
        self.node_lock = threading.RLock()
        self.heartbeat_callbacks: List[Callable[[str, Dict], None]] = []
        
        # ZeroMQ sockets
        self.control_socket = None
        self.heartbeat_socket = None
        
        # 线程
        self._control_thread = None
        self._heartbeat_thread = None
        self._monitor_thread = None
        self._running = False
    
    def start(self):
        """启动节点管理器"""
        self._setup_sockets()
        self._running = True
        self._start_threads()
        logger.info("节点管理器已启动")
    
    def stop(self):
        """停止节点管理器"""
        self._running = False
        
        # 等待线程结束
        for thread in [self._control_thread, self._heartbeat_thread, self._monitor_thread]:
            if thread and thread.is_alive():
                thread.join(timeout=5)
        
        # 关闭 sockets
        if self.control_socket:
            self.control_socket.close()
        if self.heartbeat_socket:
            self.heartbeat_socket.close()
        
        self.context.term()
        logger.info("节点管理器已停止")
    
    def _setup_sockets(self):
        """设置 ZeroMQ sockets"""
        # 控制信道 (REP socket)
        self.control_socket = self.context.socket(zmq.REP)
        self.control_socket.setsockopt(zmq.LINGER, self.config.zeromq.socket_linger)
        self.control_socket.bind(f"tcp://*:{self.config.zeromq.control_port}")
        
        # 心跳信道 (SUB socket)
        self.heartbeat_socket = self.context.socket(zmq.SUB)
        self.heartbeat_socket.setsockopt(zmq.LINGER, self.config.zeromq.socket_linger)
        self.heartbeat_socket.bind(f"tcp://*:{self.config.zeromq.heartbeat_port}")
        self.heartbeat_socket.setsockopt(zmq.SUBSCRIBE, b"heartbeat")
        
        logger.info(f"控制信道端口: {self.config.zeromq.control_port}")
        logger.info(f"心跳信道端口: {self.config.zeromq.heartbeat_port}")
    
    def register_node(self, capability: NodeCapability) -> Dict[str, any]:
        """注册节点"""
        with self.node_lock:
            # 检查节点是否已存在
            if capability.node_id in self.nodes:
                logger.warning(f"节点已存在，更新信息: {capability.node_id}")
            
            capability.status = NodeStatus.ONLINE
            capability.last_heartbeat = datetime.now()
            self.nodes[capability.node_id] = capability
        
        # 计算可订阅的队列
        subscriptions = capability.get_queue_subscriptions()
        
        logger.info(f"节点已注册: {capability.node_id}, 类型: {capability.node_type.value}")
        logger.info(f"节点能力: GPU={capability.gpu_count}, CPU={capability.cpu_cores}, 内存={capability.memory_total}MB")
        logger.info(f"可订阅队列: {subscriptions}")
        
        return {
            'status': 'success',
            'node_id': capability.node_id,
            'subscriptions': subscriptions,
            'heartbeat_interval': self.config.node_heartbeat_interval
        }
    
    def unregister_node(self, node_id: str) -> bool:
        """注销节点"""
        with self.node_lock:
            if node_id in self.nodes:
                del self.nodes[node_id]
                logger.info(f"节点已注销: {node_id}")
                return True
            return False
    
    def update_node_heartbeat(self, node_id: str, heartbeat_data: Dict):
        """更新节点心跳"""
        with self.node_lock:
            if node_id not in self.nodes:
                logger.warning(f"收到未知节点的心跳: {node_id}")
                return
            
            node = self.nodes[node_id]
            node.last_heartbeat = datetime.now()
            node.status = NodeStatus.ONLINE
            
            # 更新节点状态信息
            if 'current_load' in heartbeat_data:
                node.current_load = heartbeat_data['current_load']
            if 'total_processed' in heartbeat_data:
                node.total_processed = heartbeat_data['total_processed']
        
        # 通知心跳回调
        for callback in self.heartbeat_callbacks:
            try:
                callback(node_id, heartbeat_data)
            except Exception as e:
                logger.error(f"心跳回调执行失败: {e}")
    
    def get_node(self, node_id: str) -> Optional[NodeCapability]:
        """获取节点信息"""
        with self.node_lock:
            return self.nodes.get(node_id)
    
    def get_all_nodes(self) -> List[NodeCapability]:
        """获取所有节点"""
        with self.node_lock:
            return list(self.nodes.values())
    
    def get_online_nodes(self) -> List[NodeCapability]:
        """获取在线节点"""
        with self.node_lock:
            return [node for node in self.nodes.values() if node.status == NodeStatus.ONLINE]
    
    def get_available_nodes(self, task: Task) -> List[NodeCapability]:
        """获取可处理指定任务的可用节点"""
        available_nodes = []
        
        with self.node_lock:
            for node in self.nodes.values():
                if (node.status == NodeStatus.ONLINE and 
                    node.current_load < node.max_concurrent_tasks and
                    node.can_handle_task(task)):
                    available_nodes.append(node)
        
        # 按负载排序，优先选择负载较低的节点
        available_nodes.sort(key=lambda n: n.current_load)
        return available_nodes
    
    def find_best_node_for_task(self, task: Task) -> Optional[NodeCapability]:
        """为任务找到最佳节点"""
        available_nodes = self.get_available_nodes(task)
        
        if not available_nodes:
            return None
        
        # 简单的负载均衡策略：选择负载最低的节点
        return available_nodes[0]
    
    def update_node_load(self, node_id: str, load_delta: int):
        """更新节点负载"""
        with self.node_lock:
            if node_id in self.nodes:
                self.nodes[node_id].current_load += load_delta
                self.nodes[node_id].current_load = max(0, self.nodes[node_id].current_load)
    
    def get_node_statistics(self) -> Dict[str, any]:
        """获取节点统计信息"""
        with self.node_lock:
            stats = {
                'total_nodes': len(self.nodes),
                'online_nodes': 0,
                'offline_nodes': 0,
                'busy_nodes': 0,
                'error_nodes': 0,
                'total_capacity': 0,
                'current_load': 0,
                'node_types': {}
            }
            
            for node in self.nodes.values():
                stats[f'{node.status.value}_nodes'] += 1
                stats['total_capacity'] += node.max_concurrent_tasks
                stats['current_load'] += node.current_load
                
                node_type = node.node_type.value
                if node_type not in stats['node_types']:
                    stats['node_types'][node_type] = 0
                stats['node_types'][node_type] += 1
            
            return stats
    
    def send_control_command(self, node_id: str, command: str, data: Dict = None) -> bool:
        """向节点发送控制命令"""
        # 这个方法需要在实际实现中通过控制信道发送命令
        # 目前只是记录日志
        logger.info(f"发送控制命令到节点 {node_id}: {command}")
        return True
    
    def add_heartbeat_callback(self, callback: Callable[[str, Dict], None]):
        """添加心跳回调"""
        self.heartbeat_callbacks.append(callback)
    
    def remove_heartbeat_callback(self, callback: Callable[[str, Dict], None]):
        """移除心跳回调"""
        if callback in self.heartbeat_callbacks:
            self.heartbeat_callbacks.remove(callback)
    
    def _start_threads(self):
        """启动工作线程"""
        self._control_thread = threading.Thread(target=self._control_worker, daemon=True)
        self._heartbeat_thread = threading.Thread(target=self._heartbeat_worker, daemon=True)
        self._monitor_thread = threading.Thread(target=self._monitor_worker, daemon=True)
        
        self._control_thread.start()
        self._heartbeat_thread.start()
        self._monitor_thread.start()
        
        logger.info("节点管理器工作线程已启动")
    
    def _control_worker(self):
        """控制信道工作线程"""
        while self._running:
            try:
                # 设置超时以便能够响应停止信号
                if self.control_socket.poll(1000):  # 1秒超时
                    message = self.control_socket.recv_json()
                    response = self._handle_control_message(message)
                    self.control_socket.send_json(response)
            except zmq.Again:
                continue
            except Exception as e:
                logger.error(f"控制信道处理失败: {e}")
                time.sleep(1)
    
    def _heartbeat_worker(self):
        """心跳信道工作线程"""
        while self._running:
            try:
                # 设置超时以便能够响应停止信号
                if self.heartbeat_socket.poll(1000):  # 1秒超时
                    topic, message = self.heartbeat_socket.recv_multipart()
                    self._handle_heartbeat_message(message)
            except zmq.Again:
                continue
            except Exception as e:
                logger.error(f"心跳信道处理失败: {e}")
                time.sleep(1)
    
    def _monitor_worker(self):
        """节点监控工作线程"""
        while self._running:
            try:
                self._check_node_timeouts()
                time.sleep(self.config.node_heartbeat_interval)
            except Exception as e:
                logger.error(f"节点监控失败: {e}")
                time.sleep(10)
    
    def _handle_control_message(self, message: Dict) -> Dict:
        """处理控制消息"""
        try:
            action = message.get('action')
            data = message.get('data', {})
            
            if action == 'register':
                capability = NodeCapability.from_dict(data)
                result = self.register_node(capability)
                return result
            
            elif action == 'unregister':
                node_id = data.get('node_id')
                success = self.unregister_node(node_id)
                return {'status': 'success' if success else 'error'}
            
            elif action == 'get_queues':
                # 返回队列配置信息
                queue_configs = {}
                for name, config in self.config.queues.items():
                    queue_configs[name] = config.to_dict()
                return {'status': 'success', 'queues': queue_configs}
            
            else:
                return {'status': 'error', 'message': f'未知操作: {action}'}
                
        except Exception as e:
            logger.error(f"处理控制消息失败: {e}")
            return {'status': 'error', 'message': str(e)}
    
    def _handle_heartbeat_message(self, message: bytes):
        """处理心跳消息"""
        try:
            import json
            heartbeat_data = json.loads(message.decode('utf-8'))
            node_id = heartbeat_data.get('node_id')
            
            if node_id:
                self.update_node_heartbeat(node_id, heartbeat_data)
                
        except Exception as e:
            logger.error(f"处理心跳消息失败: {e}")
    
    def _check_node_timeouts(self):
        """检查节点超时"""
        timeout_threshold = datetime.now() - timedelta(seconds=self.config.node_timeout)
        timed_out_nodes = []
        
        with self.node_lock:
            for node_id, node in self.nodes.items():
                if (node.status == NodeStatus.ONLINE and 
                    node.last_heartbeat and 
                    node.last_heartbeat < timeout_threshold):
                    node.status = NodeStatus.OFFLINE
                    timed_out_nodes.append(node_id)
        
        for node_id in timed_out_nodes:
            logger.warning(f"节点超时离线: {node_id}")
            # 这里可以添加节点故障处理逻辑
    
    def send_cancel_command(self, node_id: str, task_id: str) -> bool:
        """向节点发送任务取消命令"""
        try:
            command_data = {
                'command': 'cancel_task',
                'task_id': task_id,
                'timestamp': datetime.now().isoformat()
            }
            
            return self.send_control_command(node_id, 'cancel_task', command_data)
            
        except Exception as e:
            logger.error(f"发送取消命令失败 {node_id}/{task_id}: {e}")
            return False