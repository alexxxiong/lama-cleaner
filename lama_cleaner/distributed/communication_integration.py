"""
状态管理和通信系统集成示例

展示状态管理器、WebSocket 管理器和控制信道如何协同工作，
提供完整的分布式通信解决方案。
"""

import logging
import time
import threading
from typing import Optional
from flask import Flask
from flask_socketio import SocketIO
import zmq
import redis

from .state_manager import StateManager
from .websocket_manager import WebSocketIntegration
from .control_channel import ControlChannelServer, ControlChannelClient
from .models import Task, TaskStatus, NodeCapability, NodeStatus
from .config import get_config

logger = logging.getLogger(__name__)


class CommunicationSystem:
    """通信系统集成类
    
    整合状态管理、WebSocket 通信和控制信道，
    提供统一的分布式通信接口。
    """
    
    def __init__(self, app: Optional[Flask] = None, redis_client=None):
        self.config = get_config()
        
        # 初始化 Redis 客户端
        self.redis_client = redis_client
        if not self.redis_client and self.config.redis.enabled:
            try:
                self.redis_client = redis.Redis(
                    host=self.config.redis.host,
                    port=self.config.redis.port,
                    db=self.config.redis.db,
                    password=self.config.redis.password,
                    max_connections=self.config.redis.max_connections,
                    socket_timeout=self.config.redis.socket_timeout,
                    socket_connect_timeout=self.config.redis.socket_connect_timeout
                )
                # 测试连接
                self.redis_client.ping()
                logger.info("Redis 连接成功")
            except Exception as e:
                logger.warning(f"Redis 连接失败，将使用内存存储: {e}")
                self.redis_client = None
        
        # 初始化 SocketIO
        self.app = app or Flask(__name__)
        self.socketio = SocketIO(
            self.app,
            cors_allowed_origins="*",
            async_mode='threading'
        )
        
        # 初始化状态管理器
        self.state_manager = StateManager(
            redis_client=self.redis_client,
            socketio=self.socketio
        )
        
        # 初始化 WebSocket 集成
        self.websocket_integration = WebSocketIntegration(
            socketio=self.socketio,
            state_manager=self.state_manager
        )
        
        # 初始化控制信道（服务器端）
        self.zmq_context = zmq.Context()
        self.control_server = ControlChannelServer(zmq_context=self.zmq_context)
        
        # 注册控制命令回调
        self._register_control_callbacks()
        
        # 启动后台任务
        self._start_background_tasks()
        
        logger.info("通信系统已初始化")
    
    def _register_control_callbacks(self):
        """注册控制命令回调"""
        
        def on_cancel_task_response(command):
            """任务取消响应回调"""
            if command.response and command.response.get('status') == 'success':
                logger.info(f"任务取消成功: {command.data.get('task_id')}")
                # 更新任务状态
                task_id = command.data.get('task_id')
                if task_id:
                    # 这里可以更新任务状态为已取消
                    pass
            else:
                logger.error(f"任务取消失败: {command.response}")
        
        def on_node_status_response(command):
            """节点状态查询响应回调"""
            if command.response and command.response.get('status') == 'success':
                node_status = command.response.get('result', {})
                logger.info(f"节点状态: {node_status}")
                # 这里可以更新节点状态
            else:
                logger.error(f"节点状态查询失败: {command.response}")
        
        # 可以添加更多回调...
    
    def _start_background_tasks(self):
        """启动后台任务"""
        
        # 检查是否在测试环境中
        import os
        if os.getenv('PYTEST_CURRENT_TEST'):
            logger.info("检测到测试环境，跳过后台任务启动")
            return
        
        def control_response_worker():
            """控制响应处理工作线程"""
            while True:
                try:
                    # 接收控制响应
                    command = self.control_server.receive_response(timeout=1000)
                    if command:
                        logger.debug(f"收到控制响应: {command.command_id}")
                except Exception as e:
                    logger.error(f"控制响应处理失败: {e}")
                    time.sleep(1)
        
        def cleanup_worker():
            """清理工作线程"""
            while True:
                try:
                    # 清理过期的控制命令
                    self.control_server.cleanup_expired_commands()
                    
                    # 清理过期的状态
                    self.state_manager.cleanup_expired_states()
                    
                    # 清理过期的 WebSocket 连接
                    self.websocket_integration.get_manager().cleanup_stale_connections()
                    
                    time.sleep(300)  # 每5分钟清理一次
                except Exception as e:
                    logger.error(f"清理任务失败: {e}")
                    time.sleep(60)
        
        # 启动后台线程
        control_thread = threading.Thread(target=control_response_worker, daemon=True)
        cleanup_thread = threading.Thread(target=cleanup_worker, daemon=True)
        
        control_thread.start()
        cleanup_thread.start()
        
        logger.info("后台任务已启动")
    
    def update_task_status(self, task: Task):
        """更新任务状态"""
        self.state_manager.update_task_status(task)
    
    def update_node_status(self, node: NodeCapability):
        """更新节点状态"""
        self.state_manager.update_node_status(node)
    
    def cancel_task(self, task_id: str, node_id: str) -> bool:
        """取消任务"""
        # 通过控制信道发送取消命令
        success = self.control_server.cancel_task(task_id, node_id)
        
        if success:
            # 同时更新本地状态
            self.state_manager.cancel_task(task_id)
        
        return success
    
    def get_node_status(self, node_id: str) -> bool:
        """获取节点状态"""
        return self.control_server.get_node_status(node_id)
    
    def shutdown_node(self, node_id: str, graceful: bool = True) -> bool:
        """关闭节点"""
        return self.control_server.shutdown_node(node_id, graceful)
    
    def broadcast_notification(self, message: str, level: str = "info"):
        """广播通知"""
        self.websocket_integration.broadcast_notification(message, level)
    
    def get_system_status(self):
        """获取系统状态"""
        return self.state_manager.get_system_status()
    
    def get_connection_stats(self):
        """获取连接统计"""
        return self.websocket_integration.get_manager().get_connection_stats()
    
    def run(self, host='0.0.0.0', port=5000, debug=False):
        """运行通信系统"""
        logger.info(f"启动通信系统服务器: {host}:{port}")
        self.socketio.run(self.app, host=host, port=port, debug=debug)
    
    def shutdown(self):
        """关闭通信系统"""
        logger.info("正在关闭通信系统...")
        
        # 关闭状态管理器
        self.state_manager.shutdown()
        
        # 关闭控制信道
        self.control_server.close()
        
        # 关闭 ZMQ 上下文
        if self.zmq_context:
            self.zmq_context.term()
        
        # 关闭 Redis 连接
        if self.redis_client:
            self.redis_client.close()
        
        logger.info("通信系统已关闭")


class NodeCommunicationClient:
    """节点通信客户端
    
    处理节点端的通信，包括控制命令接收和状态上报。
    """
    
    def __init__(self, node_id: str, scheduler_host: str = "localhost"):
        self.node_id = node_id
        self.scheduler_host = scheduler_host
        self.config = get_config()
        
        # 初始化控制信道客户端
        self.zmq_context = zmq.Context()
        self.control_client = ControlChannelClient(
            node_id=node_id,
            scheduler_host=scheduler_host,
            zmq_context=self.zmq_context
        )
        
        # 注册命令处理器
        self._register_command_handlers()
        
        logger.info(f"节点通信客户端已初始化: {node_id}")
    
    def _register_command_handlers(self):
        """注册命令处理器"""
        from .control_channel import ControlCommandType
        
        def handle_cancel_task(data):
            """处理取消任务命令"""
            task_id = data.get('task_id')
            logger.info(f"收到取消任务命令: {task_id}")
            
            # 这里应该实现实际的任务取消逻辑
            # 例如：停止正在处理的任务，清理资源等
            
            return {
                'cancelled': True,
                'task_id': task_id,
                'message': f'任务 {task_id} 已取消'
            }
        
        def handle_update_config(data):
            """处理配置更新命令"""
            config_updates = data.get('config_updates', {})
            logger.info(f"收到配置更新命令: {config_updates}")
            
            # 这里应该实现实际的配置更新逻辑
            
            return {
                'updated': True,
                'config_updates': config_updates,
                'message': '配置已更新'
            }
        
        def handle_get_node_status(data):
            """处理获取节点状态命令"""
            # 这里应该返回实际的节点状态
            return {
                'node_id': self.node_id,
                'status': 'online',
                'current_load': 0,  # 实际的负载
                'max_concurrent_tasks': 4,  # 实际的最大并发任务数
                'uptime': time.time(),
                'timestamp': time.time()
            }
        
        # 注册处理器
        self.control_client.register_handler(ControlCommandType.CANCEL_TASK, handle_cancel_task)
        self.control_client.register_handler(ControlCommandType.UPDATE_CONFIG, handle_update_config)
        self.control_client.register_handler(ControlCommandType.GET_NODE_STATUS, handle_get_node_status)
    
    def start(self):
        """启动节点通信客户端"""
        self.control_client.start()
        logger.info(f"节点通信客户端已启动: {self.node_id}")
    
    def stop(self):
        """停止节点通信客户端"""
        self.control_client.stop()
        logger.info(f"节点通信客户端已停止: {self.node_id}")
    
    def shutdown(self):
        """关闭节点通信客户端"""
        logger.info("正在关闭节点通信客户端...")
        
        self.control_client.close()
        
        if self.zmq_context:
            self.zmq_context.term()
        
        logger.info("节点通信客户端已关闭")


def create_demo_system():
    """创建演示系统"""
    
    # 创建通信系统
    comm_system = CommunicationSystem()
    
    # 添加一些演示数据
    def add_demo_data():
        time.sleep(2)  # 等待系统启动
        
        # 创建演示任务
        task1 = Task(
            task_id="demo-task-001",
            task_type="inpaint",
            status=TaskStatus.PROCESSING,
            image_path="/demo/image1.jpg"
        )
        
        task2 = Task(
            task_id="demo-task-002", 
            task_type="inpaint",
            status=TaskStatus.QUEUED,
            image_path="/demo/image2.jpg"
        )
        
        # 创建演示节点
        node1 = NodeCapability(
            node_id="demo-node-001",
            gpu_count=1,
            gpu_memory=8192,
            cpu_cores=8,
            memory_total=16384,
            status=NodeStatus.ONLINE
        )
        
        # 更新状态
        comm_system.update_task_status(task1)
        comm_system.update_task_status(task2)
        comm_system.update_node_status(node1)
        
        # 广播通知
        comm_system.broadcast_notification("演示系统已启动", "info")
        
        logger.info("演示数据已添加")
    
    # 在后台线程中添加演示数据
    demo_thread = threading.Thread(target=add_demo_data, daemon=True)
    demo_thread.start()
    
    return comm_system


if __name__ == "__main__":
    # 配置日志
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # 创建并运行演示系统
    system = create_demo_system()
    
    try:
        system.run(debug=True)
    except KeyboardInterrupt:
        logger.info("收到中断信号，正在关闭系统...")
    finally:
        system.shutdown()