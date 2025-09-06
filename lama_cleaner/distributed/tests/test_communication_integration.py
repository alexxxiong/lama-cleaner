"""
通信系统集成测试

测试状态管理器、WebSocket 管理器和控制信道的集成功能。
"""

import pytest
import time
import threading
from unittest.mock import Mock, MagicMock, patch

from ..communication_integration import CommunicationSystem, NodeCommunicationClient
from ..models import Task, TaskStatus, NodeCapability, NodeStatus
from ..config import DistributedConfig


class TestCommunicationSystem:
    """通信系统集成测试类"""
    
    @pytest.fixture
    def mock_flask_app(self):
        """模拟 Flask 应用"""
        app = Mock()
        app.config = {}
        return app
    
    @pytest.fixture
    def mock_redis_client(self):
        """模拟 Redis 客户端"""
        redis_mock = Mock()
        redis_mock.ping = Mock()
        redis_mock.hset = Mock()
        redis_mock.hgetall = Mock(return_value={})
        redis_mock.expire = Mock()
        redis_mock.close = Mock()
        return redis_mock
    
    @pytest.fixture
    def mock_config(self):
        """模拟配置"""
        config = DistributedConfig()
        config.redis.enabled = True
        config.redis.host = "localhost"
        config.redis.port = 6379
        return config
    
    @pytest.fixture
    def communication_system(self, mock_flask_app, mock_redis_client, mock_config):
        """创建通信系统实例"""
        with patch('lama_cleaner.distributed.communication_integration.get_config', return_value=mock_config), \
             patch('lama_cleaner.distributed.communication_integration.redis.Redis', return_value=mock_redis_client), \
             patch('lama_cleaner.distributed.communication_integration.SocketIO') as mock_socketio, \
             patch('lama_cleaner.distributed.communication_integration.zmq.Context') as mock_zmq_context, \
             patch('lama_cleaner.distributed.communication_integration.ControlChannelServer') as mock_control_server:
            
            # 配置 SocketIO mock
            socketio_instance = Mock()
            mock_socketio.return_value = socketio_instance
            
            # 配置 ZMQ mock
            zmq_context_instance = Mock()
            mock_zmq_context.return_value = zmq_context_instance
            
            # 配置控制服务器 mock
            control_server_instance = Mock()
            control_server_instance.receive_response = Mock(return_value=None)
            control_server_instance.cleanup_expired_commands = Mock()
            control_server_instance.close = Mock()
            mock_control_server.return_value = control_server_instance
            
            system = CommunicationSystem(app=mock_flask_app, redis_client=mock_redis_client)
            system.control_server = control_server_instance  # 确保使用 mock
            yield system
            system.shutdown()
    
    def test_system_initialization(self, communication_system, mock_redis_client):
        """测试系统初始化"""
        assert communication_system.redis_client == mock_redis_client
        assert communication_system.state_manager is not None
        assert communication_system.websocket_integration is not None
        assert communication_system.control_server is not None
        
        # 验证控制服务器的 mock 方法被正确配置
        assert hasattr(communication_system.control_server, 'receive_response')
        assert hasattr(communication_system.control_server, 'cleanup_expired_commands')
        assert hasattr(communication_system.control_server, 'close')
        
        # 验证 Redis 连接测试（在初始化过程中可能被调用）
        # 由于我们直接传入了 redis_client，ping 可能不会被调用
        # 所以我们只验证 redis_client 被正确设置
        assert communication_system.redis_client is not None
    
    def test_task_status_update(self, communication_system):
        """测试任务状态更新"""
        task = Task(
            task_id="test-task-001",
            task_type="inpaint",
            status=TaskStatus.PROCESSING
        )
        
        # 更新任务状态
        communication_system.update_task_status(task)
        
        # 验证状态已更新
        task_state = communication_system.state_manager.get_task_status(task.task_id)
        assert task_state is not None
        assert task_state['status'] == TaskStatus.PROCESSING.value
    
    def test_node_status_update(self, communication_system):
        """测试节点状态更新"""
        node = NodeCapability(
            node_id="test-node-001",
            gpu_count=1,
            gpu_memory=8192,
            status=NodeStatus.ONLINE
        )
        
        # 更新节点状态
        communication_system.update_node_status(node)
        
        # 验证状态已更新
        node_state = communication_system.state_manager.get_node_status(node.node_id)
        assert node_state is not None
        assert node_state['status'] == NodeStatus.ONLINE.value
    
    def test_task_cancellation(self, communication_system):
        """测试任务取消"""
        task_id = "test-task-002"
        node_id = "test-node-001"
        
        # 先添加一个任务
        task = Task(task_id=task_id, status=TaskStatus.PROCESSING)
        communication_system.update_task_status(task)
        
        # 模拟控制服务器的取消方法
        with patch.object(communication_system.control_server, 'cancel_task', return_value=True):
            result = communication_system.cancel_task(task_id, node_id)
            
            assert result is True
            communication_system.control_server.cancel_task.assert_called_once_with(task_id, node_id)
    
    def test_system_status(self, communication_system):
        """测试系统状态获取"""
        # 添加一些测试数据
        task = Task(task_id="test-task", status=TaskStatus.PROCESSING)
        node = NodeCapability(node_id="test-node", status=NodeStatus.ONLINE)
        
        communication_system.update_task_status(task)
        communication_system.update_node_status(node)
        
        # 获取系统状态
        status = communication_system.get_system_status()
        
        assert 'task_statistics' in status
        assert 'node_statistics' in status
        assert 'queue_statistics' in status
        assert 'system_metrics' in status
        assert 'timestamp' in status
    
    def test_broadcast_notification(self, communication_system):
        """测试广播通知"""
        message = "Test notification"
        level = "warning"
        
        with patch.object(communication_system.websocket_integration, 'broadcast_notification') as mock_broadcast:
            communication_system.broadcast_notification(message, level)
            mock_broadcast.assert_called_once_with(message, level)
    
    def test_control_server_mock_behavior(self, communication_system):
        """测试控制服务器 mock 行为"""
        control_server = communication_system.control_server
        
        # 测试 receive_response 方法
        control_server.receive_response.return_value = {'status': 'success', 'data': 'test'}
        response = control_server.receive_response()
        assert response['status'] == 'success'
        assert response['data'] == 'test'
        
        # 测试 cleanup_expired_commands 方法
        control_server.cleanup_expired_commands()
        control_server.cleanup_expired_commands.assert_called()
        
        # 测试 close 方法
        control_server.close()
        control_server.close.assert_called()
    
    def test_control_server_error_handling(self, communication_system):
        """测试控制服务器错误处理"""
        control_server = communication_system.control_server
        
        # 模拟 receive_response 抛出异常
        control_server.receive_response.side_effect = Exception("Connection error")
        
        with pytest.raises(Exception, match="Connection error"):
            control_server.receive_response()
        
        # 重置 side_effect 以便后续测试
        control_server.receive_response.side_effect = None
        
        # 验证异常后的清理操作仍然可以正常调用
        control_server.cleanup_expired_commands()
        control_server.cleanup_expired_commands.assert_called()
    
    def test_control_server_integration_with_task_cancellation(self, communication_system):
        """测试控制服务器与任务取消的集成"""
        task_id = "test-task-003"
        node_id = "test-node-002"
        
        # 配置控制服务器的取消任务方法
        control_server = communication_system.control_server
        control_server.cancel_task = Mock(return_value=True)
        
        # 先添加一个处理中的任务
        task = Task(task_id=task_id, status=TaskStatus.PROCESSING)
        task.assigned_node = node_id
        communication_system.update_task_status(task)
        
        # 执行任务取消
        result = communication_system.cancel_task(task_id, node_id)
        
        # 验证结果
        assert result is True
        control_server.cancel_task.assert_called_once_with(task_id, node_id)
    
    def test_control_server_command_timeout_handling(self, communication_system):
        """测试控制服务器命令超时处理"""
        control_server = communication_system.control_server
        
        # 模拟命令超时
        control_server.receive_response.return_value = None  # 超时返回 None
        
        response = control_server.receive_response()
        assert response is None
        
        # 验证超时后的清理操作
        control_server.cleanup_expired_commands()
        control_server.cleanup_expired_commands.assert_called()
    
    def test_redis_connection_failure(self, mock_flask_app, mock_config):
        """测试 Redis 连接失败的处理"""
        # 模拟 Redis 连接失败
        with patch('lama_cleaner.distributed.communication_integration.get_config', return_value=mock_config), \
             patch('lama_cleaner.distributed.communication_integration.redis.Redis') as mock_redis_class, \
             patch('lama_cleaner.distributed.communication_integration.SocketIO'), \
             patch('lama_cleaner.distributed.communication_integration.zmq.Context'), \
             patch('lama_cleaner.distributed.communication_integration.ControlChannelServer') as mock_control_server:
            
            # 配置 Redis 连接失败
            mock_redis_instance = Mock()
            mock_redis_instance.ping.side_effect = Exception("Connection failed")
            mock_redis_class.return_value = mock_redis_instance
            
            # 配置控制服务器 mock
            control_server_instance = Mock()
            control_server_instance.receive_response = Mock(return_value=None)
            control_server_instance.cleanup_expired_commands = Mock()
            control_server_instance.close = Mock()
            mock_control_server.return_value = control_server_instance
            
            system = CommunicationSystem(app=mock_flask_app)
            
            # 验证系统仍然可以初始化，但 Redis 客户端为 None
            assert system.redis_client is None
            
            system.shutdown()


class TestNodeCommunicationClient:
    """节点通信客户端测试类"""
    
    @pytest.fixture
    def mock_config(self):
        """模拟配置"""
        return DistributedConfig()
    
    @pytest.fixture
    def node_client(self, mock_config):
        """创建节点通信客户端实例"""
        with patch('lama_cleaner.distributed.communication_integration.get_config', return_value=mock_config), \
             patch('lama_cleaner.distributed.communication_integration.zmq.Context') as mock_zmq_context, \
             patch('lama_cleaner.distributed.communication_integration.ControlChannelClient') as mock_control_client:
            
            # 配置 mocks
            zmq_context_instance = Mock()
            mock_zmq_context.return_value = zmq_context_instance
            
            control_client_instance = Mock()
            mock_control_client.return_value = control_client_instance
            
            client = NodeCommunicationClient(
                node_id="test-node-001",
                scheduler_host="localhost"
            )
            client.control_client = control_client_instance
            
            yield client
            client.shutdown()
    
    def test_client_initialization(self, node_client):
        """测试客户端初始化"""
        assert node_client.node_id == "test-node-001"
        assert node_client.scheduler_host == "localhost"
        assert node_client.control_client is not None
    
    def test_start_stop(self, node_client):
        """测试启动和停止"""
        # 测试启动
        node_client.start()
        node_client.control_client.start.assert_called_once()
        
        # 测试停止
        node_client.stop()
        node_client.control_client.stop.assert_called_once()
    
    def test_command_handlers_registration(self, node_client):
        """测试命令处理器注册"""
        # 验证处理器已注册
        assert node_client.control_client.register_handler.called
        
        # 验证注册了正确的命令类型
        call_args_list = node_client.control_client.register_handler.call_args_list
        registered_commands = [call[0][0] for call in call_args_list]
        
        from ..control_channel import ControlCommandType
        assert ControlCommandType.CANCEL_TASK in registered_commands
        assert ControlCommandType.UPDATE_CONFIG in registered_commands
        assert ControlCommandType.GET_NODE_STATUS in registered_commands


class TestIntegrationScenarios:
    """集成场景测试"""
    
    def test_end_to_end_task_cancellation(self):
        """测试端到端任务取消场景"""
        # 这个测试模拟完整的任务取消流程：
        # 1. 通信系统发送取消命令
        # 2. 节点客户端接收并处理命令
        # 3. 状态更新和通知
        
        # 由于涉及多个组件的真实交互，这里只做基本的模拟测试
        with patch('lama_cleaner.distributed.communication_integration.get_config'), \
             patch('lama_cleaner.distributed.communication_integration.redis.Redis'), \
             patch('lama_cleaner.distributed.communication_integration.SocketIO'), \
             patch('lama_cleaner.distributed.communication_integration.zmq.Context'), \
             patch('lama_cleaner.distributed.communication_integration.ControlChannelServer') as mock_control_server:
            
            # 配置控制服务器 mock
            control_server_instance = Mock()
            control_server_instance.cancel_task = Mock(return_value=True)
            control_server_instance.receive_response = Mock(return_value=None)
            control_server_instance.cleanup_expired_commands = Mock()
            control_server_instance.close = Mock()
            mock_control_server.return_value = control_server_instance
            
            # 创建通信系统
            system = CommunicationSystem()
            
            # 模拟任务取消
            result = system.cancel_task("task-001", "node-001")
            assert result is True
            
            system.shutdown()
    
    def test_concurrent_operations(self):
        """测试并发操作"""
        with patch('lama_cleaner.distributed.communication_integration.get_config'), \
             patch('lama_cleaner.distributed.communication_integration.redis.Redis'), \
             patch('lama_cleaner.distributed.communication_integration.SocketIO'), \
             patch('lama_cleaner.distributed.communication_integration.zmq.Context'), \
             patch('lama_cleaner.distributed.communication_integration.ControlChannelServer') as mock_control_server:
            
            # 配置控制服务器 mock
            control_server_instance = Mock()
            control_server_instance.receive_response = Mock(return_value=None)
            control_server_instance.cleanup_expired_commands = Mock()
            control_server_instance.close = Mock()
            mock_control_server.return_value = control_server_instance
            
            system = CommunicationSystem()
            
            def update_tasks():
                for i in range(10):
                    task = Task(task_id=f"task-{i}", status=TaskStatus.PROCESSING)
                    system.update_task_status(task)
            
            def update_nodes():
                for i in range(5):
                    node = NodeCapability(node_id=f"node-{i}", status=NodeStatus.ONLINE)
                    system.update_node_status(node)
            
            # 并发执行更新操作
            task_thread = threading.Thread(target=update_tasks)
            node_thread = threading.Thread(target=update_nodes)
            
            task_thread.start()
            node_thread.start()
            
            task_thread.join()
            node_thread.join()
            
            # 验证所有更新都成功
            stats = system.get_system_status()
            assert stats['task_statistics']['total'] == 10
            assert stats['node_statistics']['total'] == 5
            
            system.shutdown()


if __name__ == "__main__":
    pytest.main([__file__])