"""
控制信道通信模块

使用 ZeroMQ REQ/REP 模式实现调度器与处理节点之间的控制通信，
支持任务取消、配置更新、节点管理等控制指令。
"""

import logging
import json
import threading
import time
import uuid
from typing import Dict, Any, Optional, Callable, List
from datetime import datetime, timedelta
from enum import Enum
import zmq

from .models import NodeCapability, Task
from .config import get_config

logger = logging.getLogger(__name__)


class ControlCommandType(Enum):
    """控制命令类型"""
    CANCEL_TASK = "cancel_task"
    UPDATE_CONFIG = "update_config"
    SHUTDOWN_NODE = "shutdown_node"
    RESTART_NODE = "restart_node"
    GET_NODE_STATUS = "get_node_status"
    GET_NODE_METRICS = "get_node_metrics"
    PAUSE_NODE = "pause_node"
    RESUME_NODE = "resume_node"
    PING = "ping"


class ControlResponse(Enum):
    """控制响应状态"""
    SUCCESS = "success"
    ERROR = "error"
    NOT_FOUND = "not_found"
    TIMEOUT = "timeout"
    INVALID_COMMAND = "invalid_command"


class ControlCommand:
    """控制命令数据结构"""
    
    def __init__(self, command_type: ControlCommandType, target_node: str, 
                 data: Optional[Dict[str, Any]] = None, timeout: int = 30):
        self.command_id = str(uuid.uuid4())
        self.command_type = command_type
        self.target_node = target_node
        self.data = data or {}
        self.timeout = timeout
        self.created_at = datetime.now()
        self.response = None
        self.completed_at = None
        self.status = "pending"
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            'command_id': self.command_id,
            'command_type': self.command_type.value,
            'target_node': self.target_node,
            'data': self.data,
            'timeout': self.timeout,
            'created_at': self.created_at.isoformat()
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ControlCommand':
        """从字典创建命令对象"""
        cmd = cls(
            command_type=ControlCommandType(data['command_type']),
            target_node=data['target_node'],
            data=data.get('data', {}),
            timeout=data.get('timeout', 30)
        )
        cmd.command_id = data['command_id']
        cmd.created_at = datetime.fromisoformat(data['created_at'])
        return cmd


class ControlChannelServer:
    """控制信道服务器端（调度器端）
    
    负责发送控制命令给处理节点，并处理响应。
    """
    
    def __init__(self, zmq_context: zmq.Context = None):
        self.config = get_config()
        self.context = zmq_context or zmq.Context()
        
        # 控制信道 socket
        self.control_socket = self.context.socket(zmq.REQ)
        self.control_socket.setsockopt(zmq.LINGER, self.config.zeromq.socket_linger)
        self.control_socket.setsockopt(zmq.RCVTIMEO, self.config.zeromq.socket_timeout)
        self.control_socket.setsockopt(zmq.SNDTIMEO, self.config.zeromq.socket_timeout)
        
        # 绑定到控制端口
        control_address = f"tcp://*:{self.config.zeromq.control_port}"
        self.control_socket.bind(control_address)
        
        # 命令管理
        self.pending_commands: Dict[str, ControlCommand] = {}
        self.command_history: List[ControlCommand] = []
        self.max_history_size = 1000
        
        # 线程锁
        self._lock = threading.RLock()
        
        # 响应回调
        self.response_callbacks: Dict[str, Callable[[ControlCommand], None]] = {}
        
        logger.info(f"控制信道服务器已启动，监听端口: {self.config.zeromq.control_port}")
    
    def send_command(self, command: ControlCommand, 
                    callback: Optional[Callable[[ControlCommand], None]] = None) -> bool:
        """发送控制命令"""
        try:
            with self._lock:
                self.pending_commands[command.command_id] = command
                if callback:
                    self.response_callbacks[command.command_id] = callback
            
            # 发送命令
            command_data = json.dumps(command.to_dict()).encode('utf-8')
            self.control_socket.send(command_data, zmq.NOBLOCK)
            
            logger.debug(f"发送控制命令: {command.command_type.value} -> {command.target_node}")
            return True
            
        except zmq.Again:
            logger.warning(f"控制命令发送超时: {command.command_id}")
            self._handle_command_timeout(command)
            return False
        except Exception as e:
            logger.error(f"发送控制命令失败: {e}")
            self._handle_command_error(command, str(e))
            return False
    
    def receive_response(self, timeout: int = 5000) -> Optional[ControlCommand]:
        """接收控制响应"""
        try:
            # 设置接收超时
            self.control_socket.setsockopt(zmq.RCVTIMEO, timeout)
            
            # 接收响应
            response_data = self.control_socket.recv()
            response = json.loads(response_data.decode('utf-8'))
            
            command_id = response.get('command_id')
            if not command_id:
                logger.warning("收到无效的控制响应：缺少 command_id")
                return None
            
            with self._lock:
                command = self.pending_commands.get(command_id)
                if not command:
                    logger.warning(f"收到未知命令的响应: {command_id}")
                    return None
                
                # 更新命令状态
                command.response = response
                command.completed_at = datetime.now()
                command.status = response.get('status', 'completed')
                
                # 移除待处理命令
                del self.pending_commands[command_id]
                
                # 添加到历史记录
                self._add_to_history(command)
                
                # 触发回调
                callback = self.response_callbacks.pop(command_id, None)
                if callback:
                    try:
                        callback(command)
                    except Exception as e:
                        logger.error(f"控制响应回调失败: {e}")
            
            logger.debug(f"收到控制响应: {command_id}")
            return command
            
        except zmq.Again:
            logger.debug("控制响应接收超时")
            return None
        except Exception as e:
            logger.error(f"接收控制响应失败: {e}")
            return None
    
    def cancel_task(self, task_id: str, node_id: str, 
                   callback: Optional[Callable[[ControlCommand], None]] = None) -> bool:
        """取消任务"""
        command = ControlCommand(
            command_type=ControlCommandType.CANCEL_TASK,
            target_node=node_id,
            data={'task_id': task_id}
        )
        return self.send_command(command, callback)
    
    def update_node_config(self, node_id: str, config_updates: Dict[str, Any],
                          callback: Optional[Callable[[ControlCommand], None]] = None) -> bool:
        """更新节点配置"""
        command = ControlCommand(
            command_type=ControlCommandType.UPDATE_CONFIG,
            target_node=node_id,
            data={'config_updates': config_updates}
        )
        return self.send_command(command, callback)
    
    def shutdown_node(self, node_id: str, graceful: bool = True,
                     callback: Optional[Callable[[ControlCommand], None]] = None) -> bool:
        """关闭节点"""
        command = ControlCommand(
            command_type=ControlCommandType.SHUTDOWN_NODE,
            target_node=node_id,
            data={'graceful': graceful}
        )
        return self.send_command(command, callback)
    
    def restart_node(self, node_id: str,
                    callback: Optional[Callable[[ControlCommand], None]] = None) -> bool:
        """重启节点"""
        command = ControlCommand(
            command_type=ControlCommandType.RESTART_NODE,
            target_node=node_id
        )
        return self.send_command(command, callback)
    
    def get_node_status(self, node_id: str,
                       callback: Optional[Callable[[ControlCommand], None]] = None) -> bool:
        """获取节点状态"""
        command = ControlCommand(
            command_type=ControlCommandType.GET_NODE_STATUS,
            target_node=node_id
        )
        return self.send_command(command, callback)
    
    def get_node_metrics(self, node_id: str,
                        callback: Optional[Callable[[ControlCommand], None]] = None) -> bool:
        """获取节点指标"""
        command = ControlCommand(
            command_type=ControlCommandType.GET_NODE_METRICS,
            target_node=node_id
        )
        return self.send_command(command, callback)
    
    def pause_node(self, node_id: str,
                  callback: Optional[Callable[[ControlCommand], None]] = None) -> bool:
        """暂停节点"""
        command = ControlCommand(
            command_type=ControlCommandType.PAUSE_NODE,
            target_node=node_id
        )
        return self.send_command(command, callback)
    
    def resume_node(self, node_id: str,
                   callback: Optional[Callable[[ControlCommand], None]] = None) -> bool:
        """恢复节点"""
        command = ControlCommand(
            command_type=ControlCommandType.RESUME_NODE,
            target_node=node_id
        )
        return self.send_command(command, callback)
    
    def ping_node(self, node_id: str,
                 callback: Optional[Callable[[ControlCommand], None]] = None) -> bool:
        """ping 节点"""
        command = ControlCommand(
            command_type=ControlCommandType.PING,
            target_node=node_id
        )
        return self.send_command(command, callback)
    
    def get_pending_commands(self) -> List[ControlCommand]:
        """获取待处理命令列表"""
        with self._lock:
            return list(self.pending_commands.values())
    
    def get_command_history(self, limit: int = 100) -> List[ControlCommand]:
        """获取命令历史"""
        with self._lock:
            return self.command_history[-limit:]
    
    def cleanup_expired_commands(self):
        """清理过期命令"""
        current_time = datetime.now()
        expired_commands = []
        
        with self._lock:
            for command_id, command in self.pending_commands.items():
                if (current_time - command.created_at).total_seconds() > command.timeout:
                    expired_commands.append(command_id)
        
        for command_id in expired_commands:
            with self._lock:
                command = self.pending_commands.pop(command_id, None)
                if command:
                    self._handle_command_timeout(command)
        
        if expired_commands:
            logger.info(f"清理了 {len(expired_commands)} 个过期控制命令")
    
    def _handle_command_timeout(self, command: ControlCommand):
        """处理命令超时"""
        command.status = "timeout"
        command.completed_at = datetime.now()
        command.response = {
            'status': ControlResponse.TIMEOUT.value,
            'message': f'命令执行超时 ({command.timeout}s)'
        }
        
        self._add_to_history(command)
        
        # 触发回调
        callback = self.response_callbacks.pop(command.command_id, None)
        if callback:
            try:
                callback(command)
            except Exception as e:
                logger.error(f"超时回调失败: {e}")
    
    def _handle_command_error(self, command: ControlCommand, error_message: str):
        """处理命令错误"""
        command.status = "error"
        command.completed_at = datetime.now()
        command.response = {
            'status': ControlResponse.ERROR.value,
            'message': error_message
        }
        
        with self._lock:
            self.pending_commands.pop(command.command_id, None)
        
        self._add_to_history(command)
        
        # 触发回调
        callback = self.response_callbacks.pop(command.command_id, None)
        if callback:
            try:
                callback(command)
            except Exception as e:
                logger.error(f"错误回调失败: {e}")
    
    def _add_to_history(self, command: ControlCommand):
        """添加到历史记录"""
        with self._lock:
            self.command_history.append(command)
            
            # 限制历史记录大小
            if len(self.command_history) > self.max_history_size:
                self.command_history = self.command_history[-self.max_history_size:]
    
    def close(self):
        """关闭控制信道"""
        logger.info("正在关闭控制信道服务器...")
        
        if self.control_socket:
            self.control_socket.close()
        
        logger.info("控制信道服务器已关闭")


class ControlChannelClient:
    """控制信道客户端（处理节点端）
    
    负责接收和处理来自调度器的控制命令。
    """
    
    def __init__(self, node_id: str, scheduler_host: str = "localhost", 
                 zmq_context: zmq.Context = None):
        self.node_id = node_id
        self.scheduler_host = scheduler_host
        self.config = get_config()
        self.context = zmq_context or zmq.Context()
        
        # 控制信道 socket
        self.control_socket = self.context.socket(zmq.REP)
        self.control_socket.setsockopt(zmq.LINGER, self.config.zeromq.socket_linger)
        self.control_socket.setsockopt(zmq.RCVTIMEO, self.config.zeromq.socket_timeout)
        self.control_socket.setsockopt(zmq.SNDTIMEO, self.config.zeromq.socket_timeout)
        
        # 连接到调度器
        control_address = f"tcp://{scheduler_host}:{self.config.zeromq.control_port}"
        self.control_socket.connect(control_address)
        
        # 命令处理器
        self.command_handlers: Dict[ControlCommandType, Callable] = {
            ControlCommandType.CANCEL_TASK: self._handle_cancel_task,
            ControlCommandType.UPDATE_CONFIG: self._handle_update_config,
            ControlCommandType.SHUTDOWN_NODE: self._handle_shutdown_node,
            ControlCommandType.RESTART_NODE: self._handle_restart_node,
            ControlCommandType.GET_NODE_STATUS: self._handle_get_node_status,
            ControlCommandType.GET_NODE_METRICS: self._handle_get_node_metrics,
            ControlCommandType.PAUSE_NODE: self._handle_pause_node,
            ControlCommandType.RESUME_NODE: self._handle_resume_node,
            ControlCommandType.PING: self._handle_ping
        }
        
        # 外部处理器回调
        self.external_handlers: Dict[ControlCommandType, Callable] = {}
        
        # 运行状态
        self.running = False
        self.worker_thread = None
        
        logger.info(f"控制信道客户端已初始化，节点ID: {node_id}")
    
    def start(self):
        """启动控制信道客户端"""
        if self.running:
            logger.warning("控制信道客户端已在运行")
            return
        
        self.running = True
        self.worker_thread = threading.Thread(target=self._worker_loop, daemon=True)
        self.worker_thread.start()
        
        logger.info("控制信道客户端已启动")
    
    def stop(self):
        """停止控制信道客户端"""
        if not self.running:
            return
        
        self.running = False
        
        if self.worker_thread and self.worker_thread.is_alive():
            self.worker_thread.join(timeout=5)
        
        logger.info("控制信道客户端已停止")
    
    def register_handler(self, command_type: ControlCommandType, 
                        handler: Callable[[Dict[str, Any]], Dict[str, Any]]):
        """注册外部命令处理器"""
        self.external_handlers[command_type] = handler
        logger.debug(f"注册了外部处理器: {command_type.value}")
    
    def _worker_loop(self):
        """工作循环"""
        while self.running:
            try:
                # 接收命令
                command_data = self.control_socket.recv(zmq.NOBLOCK)
                command_dict = json.loads(command_data.decode('utf-8'))
                
                # 处理命令
                response = self._process_command(command_dict)
                
                # 发送响应
                response_data = json.dumps(response).encode('utf-8')
                self.control_socket.send(response_data)
                
            except zmq.Again:
                # 没有消息，继续循环
                time.sleep(0.1)
            except Exception as e:
                logger.error(f"控制信道处理失败: {e}")
                # 发送错误响应
                try:
                    error_response = {
                        'status': ControlResponse.ERROR.value,
                        'message': str(e),
                        'timestamp': datetime.now().isoformat()
                    }
                    response_data = json.dumps(error_response).encode('utf-8')
                    self.control_socket.send(response_data)
                except:
                    pass
    
    def _process_command(self, command_dict: Dict[str, Any]) -> Dict[str, Any]:
        """处理控制命令"""
        try:
            command = ControlCommand.from_dict(command_dict)
            
            # 检查目标节点
            if command.target_node != self.node_id:
                return {
                    'command_id': command.command_id,
                    'status': ControlResponse.ERROR.value,
                    'message': f'命令目标节点不匹配: 期望 {self.node_id}, 实际 {command.target_node}',
                    'timestamp': datetime.now().isoformat()
                }
            
            # 获取处理器
            handler = self.command_handlers.get(command.command_type)
            if not handler:
                return {
                    'command_id': command.command_id,
                    'status': ControlResponse.INVALID_COMMAND.value,
                    'message': f'不支持的命令类型: {command.command_type.value}',
                    'timestamp': datetime.now().isoformat()
                }
            
            # 执行处理器
            result = handler(command.data)
            
            # 构建响应
            response = {
                'command_id': command.command_id,
                'status': ControlResponse.SUCCESS.value,
                'result': result,
                'timestamp': datetime.now().isoformat()
            }
            
            logger.debug(f"处理控制命令: {command.command_type.value}")
            return response
            
        except Exception as e:
            logger.error(f"处理控制命令失败: {e}")
            return {
                'command_id': command_dict.get('command_id', 'unknown'),
                'status': ControlResponse.ERROR.value,
                'message': str(e),
                'timestamp': datetime.now().isoformat()
            }
    
    def _handle_cancel_task(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """处理取消任务命令"""
        task_id = data.get('task_id')
        if not task_id:
            raise ValueError("缺少 task_id 参数")
        
        # 检查是否有外部处理器
        if ControlCommandType.CANCEL_TASK in self.external_handlers:
            return self.external_handlers[ControlCommandType.CANCEL_TASK](data)
        
        # 默认处理：记录日志
        logger.info(f"收到取消任务命令: {task_id}")
        return {'message': f'任务取消命令已接收: {task_id}'}
    
    def _handle_update_config(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """处理更新配置命令"""
        config_updates = data.get('config_updates', {})
        
        if ControlCommandType.UPDATE_CONFIG in self.external_handlers:
            return self.external_handlers[ControlCommandType.UPDATE_CONFIG](data)
        
        logger.info(f"收到配置更新命令: {config_updates}")
        return {'message': '配置更新命令已接收', 'updates': config_updates}
    
    def _handle_shutdown_node(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """处理关闭节点命令"""
        graceful = data.get('graceful', True)
        
        if ControlCommandType.SHUTDOWN_NODE in self.external_handlers:
            return self.external_handlers[ControlCommandType.SHUTDOWN_NODE](data)
        
        logger.info(f"收到关闭节点命令: graceful={graceful}")
        return {'message': '节点关闭命令已接收', 'graceful': graceful}
    
    def _handle_restart_node(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """处理重启节点命令"""
        if ControlCommandType.RESTART_NODE in self.external_handlers:
            return self.external_handlers[ControlCommandType.RESTART_NODE](data)
        
        logger.info("收到重启节点命令")
        return {'message': '节点重启命令已接收'}
    
    def _handle_get_node_status(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """处理获取节点状态命令"""
        if ControlCommandType.GET_NODE_STATUS in self.external_handlers:
            return self.external_handlers[ControlCommandType.GET_NODE_STATUS](data)
        
        # 默认返回基本状态
        return {
            'node_id': self.node_id,
            'status': 'online',
            'timestamp': datetime.now().isoformat()
        }
    
    def _handle_get_node_metrics(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """处理获取节点指标命令"""
        if ControlCommandType.GET_NODE_METRICS in self.external_handlers:
            return self.external_handlers[ControlCommandType.GET_NODE_METRICS](data)
        
        # 默认返回基本指标
        return {
            'node_id': self.node_id,
            'metrics': {
                'uptime': time.time(),
                'timestamp': datetime.now().isoformat()
            }
        }
    
    def _handle_pause_node(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """处理暂停节点命令"""
        if ControlCommandType.PAUSE_NODE in self.external_handlers:
            return self.external_handlers[ControlCommandType.PAUSE_NODE](data)
        
        logger.info("收到暂停节点命令")
        return {'message': '节点暂停命令已接收'}
    
    def _handle_resume_node(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """处理恢复节点命令"""
        if ControlCommandType.RESUME_NODE in self.external_handlers:
            return self.external_handlers[ControlCommandType.RESUME_NODE](data)
        
        logger.info("收到恢复节点命令")
        return {'message': '节点恢复命令已接收'}
    
    def _handle_ping(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """处理 ping 命令"""
        if ControlCommandType.PING in self.external_handlers:
            return self.external_handlers[ControlCommandType.PING](data)
        
        return {
            'node_id': self.node_id,
            'pong': True,
            'timestamp': datetime.now().isoformat()
        }
    
    def close(self):
        """关闭控制信道客户端"""
        logger.info("正在关闭控制信道客户端...")
        
        self.stop()
        
        if self.control_socket:
            self.control_socket.close()
        
        logger.info("控制信道客户端已关闭")