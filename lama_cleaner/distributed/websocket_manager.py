"""
WebSocket 实时通信管理器

负责管理 WebSocket 连接，处理客户端订阅和取消订阅，
提供实时任务状态推送和系统监控功能。
"""

import logging
import json
import threading
from typing import Dict, List, Set, Optional, Any, Callable
from datetime import datetime
from flask_socketio import SocketIO, emit, join_room, leave_room, disconnect
from flask import request

from .models import TaskStatus, NodeStatus
from .config import get_config

logger = logging.getLogger(__name__)


class WebSocketManager:
    """WebSocket 连接管理器
    
    提供以下功能：
    - 客户端连接管理
    - 房间订阅管理
    - 实时消息推送
    - 连接状态监控
    """
    
    def __init__(self, socketio: SocketIO):
        self.socketio = socketio
        self.config = get_config()
        
        # 连接管理
        self.connections: Dict[str, Dict[str, Any]] = {}  # session_id -> connection_info
        self.subscriptions: Dict[str, Set[str]] = {  # room_name -> set of session_ids
            'task_updates': set(),
            'node_updates': set(),
            'system_metrics': set(),
            'queue_stats': set()
        }
        
        # 线程锁
        self._lock = threading.RLock()
        
        # 注册事件处理器
        self._register_event_handlers()
        
        logger.info("WebSocket 管理器已初始化")
    
    def _register_event_handlers(self):
        """注册 SocketIO 事件处理器"""
        
        @self.socketio.on('connect')
        def handle_connect():
            """处理客户端连接"""
            session_id = request.sid
            client_info = {
                'session_id': session_id,
                'connected_at': datetime.now(),
                'subscriptions': set(),
                'user_agent': request.headers.get('User-Agent', ''),
                'remote_addr': request.remote_addr
            }
            
            with self._lock:
                self.connections[session_id] = client_info
            
            logger.info(f"客户端已连接: {session_id} from {request.remote_addr}")
            
            # 发送连接确认
            emit('connection_established', {
                'session_id': session_id,
                'server_time': datetime.now().isoformat(),
                'available_rooms': list(self.subscriptions.keys())
            })
        
        @self.socketio.on('disconnect')
        def handle_disconnect():
            """处理客户端断开连接"""
            session_id = request.sid
            
            with self._lock:
                if session_id in self.connections:
                    # 从所有订阅中移除
                    for room_name, subscribers in self.subscriptions.items():
                        subscribers.discard(session_id)
                    
                    # 移除连接记录
                    del self.connections[session_id]
            
            logger.info(f"客户端已断开连接: {session_id}")
        
        @self.socketio.on('subscribe')
        def handle_subscribe(data):
            """处理订阅请求"""
            session_id = request.sid
            room_name = data.get('room')
            
            if not room_name or room_name not in self.subscriptions:
                emit('error', {'message': f'无效的房间名称: {room_name}'})
                return
            
            with self._lock:
                # 加入房间
                join_room(room_name)
                self.subscriptions[room_name].add(session_id)
                
                # 更新连接信息
                if session_id in self.connections:
                    self.connections[session_id]['subscriptions'].add(room_name)
            
            logger.debug(f"客户端 {session_id} 订阅了房间 {room_name}")
            
            emit('subscribed', {
                'room': room_name,
                'message': f'已成功订阅 {room_name}'
            })
            
            # 发送当前状态
            self._send_current_state(session_id, room_name)
        
        @self.socketio.on('unsubscribe')
        def handle_unsubscribe(data):
            """处理取消订阅请求"""
            session_id = request.sid
            room_name = data.get('room')
            
            if not room_name or room_name not in self.subscriptions:
                emit('error', {'message': f'无效的房间名称: {room_name}'})
                return
            
            with self._lock:
                # 离开房间
                leave_room(room_name)
                self.subscriptions[room_name].discard(session_id)
                
                # 更新连接信息
                if session_id in self.connections:
                    self.connections[session_id]['subscriptions'].discard(room_name)
            
            logger.debug(f"客户端 {session_id} 取消订阅房间 {room_name}")
            
            emit('unsubscribed', {
                'room': room_name,
                'message': f'已取消订阅 {room_name}'
            })
        
        @self.socketio.on('get_status')
        def handle_get_status():
            """处理状态查询请求"""
            session_id = request.sid
            
            with self._lock:
                connection_info = self.connections.get(session_id, {})
            
            emit('status_response', {
                'session_id': session_id,
                'subscriptions': list(connection_info.get('subscriptions', [])),
                'connected_at': connection_info.get('connected_at', datetime.now()).isoformat(),
                'total_connections': len(self.connections)
            })
        
        @self.socketio.on('ping')
        def handle_ping():
            """处理心跳请求"""
            emit('pong', {'timestamp': datetime.now().isoformat()})
    
    def _send_current_state(self, session_id: str, room_name: str):
        """向新订阅的客户端发送当前状态"""
        try:
            if room_name == 'task_updates':
                # 发送当前任务统计
                self.socketio.emit('current_task_stats', {
                    'message': '当前任务统计将在下次更新时发送'
                }, room=session_id)
            
            elif room_name == 'node_updates':
                # 发送当前节点状态
                self.socketio.emit('current_node_stats', {
                    'message': '当前节点状态将在下次更新时发送'
                }, room=session_id)
            
            elif room_name == 'system_metrics':
                # 发送当前系统指标
                self.socketio.emit('current_system_metrics', {
                    'message': '当前系统指标将在下次更新时发送'
                }, room=session_id)
            
            elif room_name == 'queue_stats':
                # 发送当前队列统计
                self.socketio.emit('current_queue_stats', {
                    'message': '当前队列统计将在下次更新时发送'
                }, room=session_id)
        
        except Exception as e:
            logger.error(f"发送当前状态失败: {e}")
    
    def broadcast_task_update(self, task_data: Dict[str, Any]):
        """广播任务状态更新"""
        try:
            message = {
                'type': 'task_update',
                'data': task_data,
                'timestamp': datetime.now().isoformat()
            }
            
            self.socketio.emit('task_update', message, room='task_updates')
            logger.debug(f"广播任务更新: {task_data.get('task_id')}")
            
        except Exception as e:
            logger.error(f"广播任务更新失败: {e}")
    
    def broadcast_node_update(self, node_data: Dict[str, Any]):
        """广播节点状态更新"""
        try:
            message = {
                'type': 'node_update',
                'data': node_data,
                'timestamp': datetime.now().isoformat()
            }
            
            self.socketio.emit('node_update', message, room='node_updates')
            logger.debug(f"广播节点更新: {node_data.get('node_id')}")
            
        except Exception as e:
            logger.error(f"广播节点更新失败: {e}")
    
    def broadcast_system_metrics(self, metrics_data: Dict[str, Any]):
        """广播系统指标更新"""
        try:
            message = {
                'type': 'system_metrics',
                'data': metrics_data,
                'timestamp': datetime.now().isoformat()
            }
            
            self.socketio.emit('system_metrics', message, room='system_metrics')
            logger.debug("广播系统指标更新")
            
        except Exception as e:
            logger.error(f"广播系统指标失败: {e}")
    
    def broadcast_queue_stats(self, queue_data: Dict[str, Any]):
        """广播队列统计更新"""
        try:
            message = {
                'type': 'queue_stats',
                'data': queue_data,
                'timestamp': datetime.now().isoformat()
            }
            
            self.socketio.emit('queue_stats', message, room='queue_stats')
            logger.debug("广播队列统计更新")
            
        except Exception as e:
            logger.error(f"广播队列统计失败: {e}")
    
    def send_to_client(self, session_id: str, event: str, data: Dict[str, Any]):
        """向特定客户端发送消息"""
        try:
            self.socketio.emit(event, data, room=session_id)
            logger.debug(f"向客户端 {session_id} 发送消息: {event}")
            
        except Exception as e:
            logger.error(f"向客户端发送消息失败: {e}")
    
    def broadcast_to_all(self, event: str, data: Dict[str, Any]):
        """向所有连接的客户端广播消息"""
        try:
            self.socketio.emit(event, data)
            logger.debug(f"广播消息: {event}")
            
        except Exception as e:
            logger.error(f"广播消息失败: {e}")
    
    def get_connection_stats(self) -> Dict[str, Any]:
        """获取连接统计信息"""
        with self._lock:
            stats = {
                'total_connections': len(self.connections),
                'subscriptions': {
                    room: len(subscribers) 
                    for room, subscribers in self.subscriptions.items()
                },
                'connections': []
            }
            
            for session_id, info in self.connections.items():
                stats['connections'].append({
                    'session_id': session_id,
                    'connected_at': info['connected_at'].isoformat(),
                    'subscriptions': list(info['subscriptions']),
                    'remote_addr': info.get('remote_addr', 'unknown')
                })
        
        return stats
    
    def disconnect_client(self, session_id: str, reason: str = "服务器断开连接"):
        """断开特定客户端连接"""
        try:
            self.socketio.emit('disconnect_notice', {
                'reason': reason,
                'timestamp': datetime.now().isoformat()
            }, room=session_id)
            
            # 强制断开连接
            self.socketio.disconnect(session_id)
            logger.info(f"已断开客户端连接: {session_id}, 原因: {reason}")
            
        except Exception as e:
            logger.error(f"断开客户端连接失败: {e}")
    
    def cleanup_stale_connections(self):
        """清理过期连接"""
        current_time = datetime.now()
        stale_connections = []
        
        with self._lock:
            for session_id, info in self.connections.items():
                # 检查连接是否超时（例如超过1小时无活动）
                if (current_time - info['connected_at']).total_seconds() > 3600:
                    stale_connections.append(session_id)
        
        for session_id in stale_connections:
            self.disconnect_client(session_id, "连接超时")
        
        if stale_connections:
            logger.info(f"清理了 {len(stale_connections)} 个过期连接")
    
    def get_subscribers(self, room_name: str) -> Set[str]:
        """获取指定房间的订阅者列表"""
        with self._lock:
            return self.subscriptions.get(room_name, set()).copy()
    
    def is_client_subscribed(self, session_id: str, room_name: str) -> bool:
        """检查客户端是否订阅了指定房间"""
        with self._lock:
            return session_id in self.subscriptions.get(room_name, set())
    
    def get_client_subscriptions(self, session_id: str) -> Set[str]:
        """获取客户端的订阅列表"""
        with self._lock:
            connection_info = self.connections.get(session_id, {})
            return connection_info.get('subscriptions', set()).copy()


class WebSocketIntegration:
    """WebSocket 集成类
    
    将 WebSocket 管理器与状态管理器集成，
    提供统一的实时通信接口。
    """
    
    def __init__(self, socketio: SocketIO, state_manager=None):
        self.websocket_manager = WebSocketManager(socketio)
        self.state_manager = state_manager
        
        # 如果提供了状态管理器，则注册回调
        if self.state_manager:
            self._register_state_callbacks()
        
        logger.info("WebSocket 集成已初始化")
    
    def _register_state_callbacks(self):
        """注册状态管理器回调"""
        
        def on_task_update(task_id: str, task_state: Dict[str, Any]):
            """任务状态更新回调"""
            self.websocket_manager.broadcast_task_update({
                'task_id': task_id,
                'status': task_state.get('status'),
                'progress': task_state.get('progress', 0),
                'message': task_state.get('message', ''),
                'error_message': task_state.get('error_message'),
                'updated_at': task_state.get('updated_at')
            })
        
        def on_node_update(node_id: str, node_state: Dict[str, Any]):
            """节点状态更新回调"""
            self.websocket_manager.broadcast_node_update({
                'node_id': node_id,
                'status': node_state.get('status'),
                'current_load': node_state.get('current_load', 0),
                'max_concurrent_tasks': node_state.get('max_concurrent_tasks', 0),
                'last_heartbeat': node_state.get('last_heartbeat'),
                'updated_at': datetime.now().isoformat()
            })
        
        def on_metrics_update(metrics: Dict[str, Any]):
            """系统指标更新回调"""
            self.websocket_manager.broadcast_system_metrics(metrics)
        
        # 注册回调
        self.state_manager.subscribe_to_task_events(on_task_update)
        self.state_manager.subscribe_to_node_events(on_node_update)
        self.state_manager.subscribe_to_metrics_events(on_metrics_update)
        
        logger.info("状态管理器回调已注册")
    
    def get_manager(self) -> WebSocketManager:
        """获取 WebSocket 管理器实例"""
        return self.websocket_manager
    
    def broadcast_custom_message(self, event: str, data: Dict[str, Any], room: Optional[str] = None):
        """广播自定义消息"""
        if room:
            self.websocket_manager.socketio.emit(event, data, room=room)
        else:
            self.websocket_manager.broadcast_to_all(event, data)
    
    def send_notification(self, session_id: str, message: str, level: str = "info"):
        """向特定客户端发送通知"""
        self.websocket_manager.send_to_client(session_id, 'notification', {
            'message': message,
            'level': level,
            'timestamp': datetime.now().isoformat()
        })
    
    def broadcast_notification(self, message: str, level: str = "info"):
        """向所有客户端广播通知"""
        self.websocket_manager.broadcast_to_all('notification', {
            'message': message,
            'level': level,
            'timestamp': datetime.now().isoformat()
        })