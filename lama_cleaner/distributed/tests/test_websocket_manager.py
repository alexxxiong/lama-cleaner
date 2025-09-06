"""
WebSocket 管理器测试

测试 WebSocket 连接管理、房间订阅、消息广播等功能。
"""

import pytest
import time
import json
from unittest.mock import Mock, MagicMock, patch
from datetime import datetime

from ..websocket_manager import WebSocketManager, WebSocketIntegration
from ..models import TaskStatus, NodeStatus
from ..config import DistributedConfig


class TestWebSocketManager:
    """WebSocket 管理器测试类"""
    
    @pytest.fixture
    def mock_socketio(self):
        """模拟 SocketIO 实例"""
        socketio_mock = Mock()
        socketio_mock.emit = Mock()
        socketio_mock.disconnect = Mock()
        socketio_mock.on = Mock()
        return socketio_mock
    
    @pytest.fixture
    def mock_config(self):
        """模拟配置"""
        return DistributedConfig()
    
    @pytest.fixture
    def websocket_manager(self, mock_socketio, mock_config):
        """创建 WebSocket 管理器实例"""
        with patch('lama_cleaner.distributed.websocket_manager.get_config', return_value=mock_config):
            return WebSocketManager(mock_socketio)
    
    def test_initialization(self, websocket_manager, mock_socketio):
        """测试初始化"""
        assert websocket_manager.socketio == mock_socketio
        assert len(websocket_manager.connections) == 0
        assert 'task_updates' in websocket_manager.subscriptions
        assert 'node_updates' in websocket_manager.subscriptions
        assert 'system_metrics' in websocket_manager.subscriptions
        assert 'queue_stats' in websocket_manager.subscriptions
        
        # 验证事件处理器已注册
        assert mock_socketio.on.called
    
    def test_broadcast_task_update(self, websocket_manager, mock_socketio):
        """测试任务更新广播"""
        task_data = {
            'task_id': 'test-task-001',
            'status': TaskStatus.PROCESSING.value,
            'progress': 50.0,
            'message': '正在处理'
        }
        
        websocket_manager.broadcast_task_update(task_data)
        
        # 验证 emit 被调用
        mock_socketio.emit.assert_called_once()
        call_args = mock_socketio.emit.call_args
        
        assert call_args[0][0] == 'task_update'  # 事件名
        assert call_args[1]['room'] == 'task_updates'  # 房间名
        
        # 验证消息内容
        message = call_args[0][1]
        assert message['type'] == 'task_update'
        assert message['data'] == task_data
        assert 'timestamp' in message
    
    def test_broadcast_node_update(self, websocket_manager, mock_socketio):
        """测试节点更新广播"""
        node_data = {
            'node_id': 'test-node-001',
            'status': NodeStatus.ONLINE.value,
            'current_load': 2,
            'max_concurrent_tasks': 4
        }
        
        websocket_manager.broadcast_node_update(node_data)
        
        # 验证 emit 被调用
        mock_socketio.emit.assert_called_once()
        call_args = mock_socketio.emit.call_args
        
        assert call_args[0][0] == 'node_update'
        assert call_args[1]['room'] == 'node_updates'
        
        message = call_args[0][1]
        assert message['type'] == 'node_update'
        assert message['data'] == node_data
    
    def test_broadcast_system_metrics(self, websocket_manager, mock_socketio):
        """测试系统指标广播"""
        metrics_data = {
            'cpu_usage': 75.5,
            'memory_usage': 60.2,
            'active_nodes': 3,
            'queue_length': 10
        }
        
        websocket_manager.broadcast_system_metrics(metrics_data)
        
        mock_socketio.emit.assert_called_once()
        call_args = mock_socketio.emit.call_args
        
        assert call_args[0][0] == 'system_metrics'
        assert call_args[1]['room'] == 'system_metrics'
        
        message = call_args[0][1]
        assert message['type'] == 'system_metrics'
        assert message['data'] == metrics_data
    
    def test_broadcast_queue_stats(self, websocket_manager, mock_socketio):
        """测试队列统计广播"""
        queue_data = {
            'gpu-high': {'pending': 5, 'processing': 2, 'completed': 10},
            'cpu-light': {'pending': 3, 'processing': 1, 'completed': 8}
        }
        
        websocket_manager.broadcast_queue_stats(queue_data)
        
        mock_socketio.emit.assert_called_once()
        call_args = mock_socketio.emit.call_args
        
        assert call_args[0][0] == 'queue_stats'
        assert call_args[1]['room'] == 'queue_stats'
        
        message = call_args[0][1]
        assert message['type'] == 'queue_stats'
        assert message['data'] == queue_data
    
    def test_send_to_client(self, websocket_manager, mock_socketio):
        """测试向特定客户端发送消息"""
        session_id = 'test-session-001'
        event = 'custom_event'
        data = {'message': 'Hello, client!'}
        
        websocket_manager.send_to_client(session_id, event, data)
        
        mock_socketio.emit.assert_called_once_with(event, data, room=session_id)
    
    def test_broadcast_to_all(self, websocket_manager, mock_socketio):
        """测试向所有客户端广播"""
        event = 'global_announcement'
        data = {'message': 'System maintenance in 10 minutes'}
        
        websocket_manager.broadcast_to_all(event, data)
        
        mock_socketio.emit.assert_called_once_with(event, data)
    
    def test_connection_management(self, websocket_manager):
        """测试连接管理"""
        # 模拟添加连接
        session_id = 'test-session-001'
        connection_info = {
            'session_id': session_id,
            'connected_at': datetime.now(),
            'subscriptions': set(),
            'remote_addr': '127.0.0.1'
        }
        
        websocket_manager.connections[session_id] = connection_info
        
        # 测试获取连接统计
        stats = websocket_manager.get_connection_stats()
        assert stats['total_connections'] == 1
        assert len(stats['connections']) == 1
        assert stats['connections'][0]['session_id'] == session_id
    
    def test_subscription_management(self, websocket_manager):
        """测试订阅管理"""
        session_id = 'test-session-001'
        room_name = 'task_updates'
        
        # 添加订阅
        websocket_manager.subscriptions[room_name].add(session_id)
        
        # 测试订阅检查
        assert websocket_manager.is_client_subscribed(session_id, room_name)
        assert not websocket_manager.is_client_subscribed(session_id, 'node_updates')
        
        # 测试获取订阅者
        subscribers = websocket_manager.get_subscribers(room_name)
        assert session_id in subscribers
    
    def test_disconnect_client(self, websocket_manager, mock_socketio):
        """测试断开客户端连接"""
        session_id = 'test-session-001'
        reason = 'Test disconnect'
        
        websocket_manager.disconnect_client(session_id, reason)
        
        # 验证发送断开通知
        assert mock_socketio.emit.called
        # 验证强制断开连接
        mock_socketio.disconnect.assert_called_once_with(session_id)
    
    def test_cleanup_stale_connections(self, websocket_manager):
        """测试清理过期连接"""
        # 添加一个过期连接
        old_session = 'old-session'
        old_time = datetime.now().replace(year=2020)  # 很久以前的时间
        
        websocket_manager.connections[old_session] = {
            'session_id': old_session,
            'connected_at': old_time,
            'subscriptions': set(),
            'remote_addr': '127.0.0.1'
        }
        
        # 添加一个正常连接
        new_session = 'new-session'
        websocket_manager.connections[new_session] = {
            'session_id': new_session,
            'connected_at': datetime.now(),
            'subscriptions': set(),
            'remote_addr': '127.0.0.1'
        }
        
        # 执行清理
        with patch.object(websocket_manager, 'disconnect_client') as mock_disconnect:
            websocket_manager.cleanup_stale_connections()
            mock_disconnect.assert_called_once_with(old_session, "连接超时")
    
    def test_error_handling(self, websocket_manager, mock_socketio):
        """测试错误处理"""
        # 模拟 emit 抛出异常
        mock_socketio.emit.side_effect = Exception("Network error")
        
        # 广播消息不应该抛出异常
        task_data = {'task_id': 'test-task', 'status': 'processing'}
        websocket_manager.broadcast_task_update(task_data)
        
        # 验证异常被捕获并记录
        assert mock_socketio.emit.called


class TestWebSocketIntegration:
    """WebSocket 集成测试类"""
    
    @pytest.fixture
    def mock_socketio(self):
        """模拟 SocketIO 实例"""
        socketio_mock = Mock()
        socketio_mock.emit = Mock()
        socketio_mock.on = Mock()
        return socketio_mock
    
    @pytest.fixture
    def mock_state_manager(self):
        """模拟状态管理器"""
        state_manager = Mock()
        state_manager.subscribe_to_task_events = Mock()
        state_manager.subscribe_to_node_events = Mock()
        state_manager.subscribe_to_metrics_events = Mock()
        return state_manager
    
    @pytest.fixture
    def mock_config(self):
        """模拟配置"""
        return DistributedConfig()
    
    @pytest.fixture
    def websocket_integration(self, mock_socketio, mock_state_manager, mock_config):
        """创建 WebSocket 集成实例"""
        with patch('lama_cleaner.distributed.websocket_manager.get_config', return_value=mock_config):
            return WebSocketIntegration(mock_socketio, mock_state_manager)
    
    def test_initialization_with_state_manager(self, websocket_integration, mock_state_manager):
        """测试带状态管理器的初始化"""
        assert websocket_integration.state_manager == mock_state_manager
        
        # 验证回调已注册
        mock_state_manager.subscribe_to_task_events.assert_called_once()
        mock_state_manager.subscribe_to_node_events.assert_called_once()
        mock_state_manager.subscribe_to_metrics_events.assert_called_once()
    
    def test_initialization_without_state_manager(self, mock_socketio, mock_config):
        """测试不带状态管理器的初始化"""
        with patch('lama_cleaner.distributed.websocket_manager.get_config', return_value=mock_config):
            integration = WebSocketIntegration(mock_socketio)
            assert integration.state_manager is None
    
    def test_get_manager(self, websocket_integration):
        """测试获取管理器实例"""
        manager = websocket_integration.get_manager()
        assert isinstance(manager, WebSocketManager)
    
    def test_broadcast_custom_message(self, websocket_integration, mock_socketio):
        """测试广播自定义消息"""
        event = 'custom_event'
        data = {'message': 'Custom message'}
        room = 'custom_room'
        
        # 测试向特定房间广播
        websocket_integration.broadcast_custom_message(event, data, room)
        mock_socketio.emit.assert_called_with(event, data, room=room)
        
        # 重置 mock
        mock_socketio.emit.reset_mock()
        
        # 测试向所有客户端广播
        websocket_integration.broadcast_custom_message(event, data)
        mock_socketio.emit.assert_called_with(event, data)
    
    def test_send_notification(self, websocket_integration):
        """测试发送通知"""
        session_id = 'test-session'
        message = 'Test notification'
        level = 'warning'
        
        with patch.object(websocket_integration.websocket_manager, 'send_to_client') as mock_send:
            websocket_integration.send_notification(session_id, message, level)
            
            mock_send.assert_called_once()
            call_args = mock_send.call_args
            
            assert call_args[0][0] == session_id
            assert call_args[0][1] == 'notification'
            
            notification_data = call_args[0][2]
            assert notification_data['message'] == message
            assert notification_data['level'] == level
            assert 'timestamp' in notification_data
    
    def test_broadcast_notification(self, websocket_integration):
        """测试广播通知"""
        message = 'System notification'
        level = 'info'
        
        with patch.object(websocket_integration.websocket_manager, 'broadcast_to_all') as mock_broadcast:
            websocket_integration.broadcast_notification(message, level)
            
            mock_broadcast.assert_called_once()
            call_args = mock_broadcast.call_args
            
            assert call_args[0][0] == 'notification'
            
            notification_data = call_args[0][1]
            assert notification_data['message'] == message
            assert notification_data['level'] == level
            assert 'timestamp' in notification_data
    
    def test_state_manager_callbacks(self, websocket_integration, mock_state_manager):
        """测试状态管理器回调"""
        # 获取注册的回调函数
        task_callback = mock_state_manager.subscribe_to_task_events.call_args[0][0]
        node_callback = mock_state_manager.subscribe_to_node_events.call_args[0][0]
        metrics_callback = mock_state_manager.subscribe_to_metrics_events.call_args[0][0]
        
        # 测试任务回调
        with patch.object(websocket_integration.websocket_manager, 'broadcast_task_update') as mock_broadcast:
            task_callback('test-task', {'status': 'processing', 'progress': 50})
            mock_broadcast.assert_called_once()
        
        # 测试节点回调
        with patch.object(websocket_integration.websocket_manager, 'broadcast_node_update') as mock_broadcast:
            node_callback('test-node', {'status': 'online', 'current_load': 2})
            mock_broadcast.assert_called_once()
        
        # 测试指标回调
        with patch.object(websocket_integration.websocket_manager, 'broadcast_system_metrics') as mock_broadcast:
            metrics_callback({'cpu_usage': 75.0})
            mock_broadcast.assert_called_once()


class TestWebSocketEventHandlers:
    """WebSocket 事件处理器测试"""
    
    def test_event_handler_registration(self):
        """测试事件处理器注册"""
        mock_socketio = Mock()
        mock_config = DistributedConfig()
        
        with patch('lama_cleaner.distributed.websocket_manager.get_config', return_value=mock_config):
            WebSocketManager(mock_socketio)
        
        # 验证所有必要的事件处理器都已注册
        expected_events = ['connect', 'disconnect', 'subscribe', 'unsubscribe', 'get_status', 'ping']
        
        registered_events = [call[0][0] for call in mock_socketio.on.call_args_list]
        
        for event in expected_events:
            assert event in registered_events


if __name__ == "__main__":
    pytest.main([__file__])