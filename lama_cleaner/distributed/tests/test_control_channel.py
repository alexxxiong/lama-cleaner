"""
控制信道通信测试

测试 ZeroMQ REQ/REP 模式的控制信道通信功能，
包括命令发送、响应处理、错误处理等。
"""

import pytest
import time
import json
import threading
from unittest.mock import Mock, MagicMock, patch
from datetime import datetime

from ..control_channel import (
    ControlChannelServer, ControlChannelClient, ControlCommand, 
    ControlCommandType, ControlResponse
)
from ..config import DistributedConfig


class TestControlCommand:
    """控制命令测试类"""
    
    def test_command_creation(self):
        """测试命令创建"""
        command = ControlCommand(
            command_type=ControlCommandType.CANCEL_TASK,
            target_node="test-node-001",
            data={"task_id": "test-task-001"},
            timeout=60
        )
        
        assert command.command_type == ControlCommandType.CANCEL_TASK
        assert command.target_node == "test-node-001"
        assert command.data["task_id"] == "test-task-001"
        assert command.timeout == 60
        assert command.status == "pending"
        assert command.response is None
    
    def test_command_serialization(self):
        """测试命令序列化"""
        command = ControlCommand(
            command_type=ControlCommandType.UPDATE_CONFIG,
            target_node="test-node-001",
            data={"config": {"max_tasks": 4}}
        )
        
        # 转换为字典
        command_dict = command.to_dict()
        assert command_dict["command_type"] == "update_config"
        assert command_dict["target_node"] == "test-node-001"
        assert command_dict["data"]["config"]["max_tasks"] == 4
        
        # 从字典恢复
        restored_command = ControlCommand.from_dict(command_dict)
        assert restored_command.command_id == command.command_id
        assert restored_command.command_type == command.command_type
        assert restored_command.target_node == command.target_node
        assert restored_command.data == command.data


class TestControlChannelServer:
    """控制信道服务器测试类"""
    
    @pytest.fixture
    def mock_zmq_context(self):
        """模拟 ZMQ 上下文"""
        context = Mock()
        socket = Mock()
        
        # 配置 socket mock
        socket.bind = Mock()
        socket.send = Mock()
        socket.recv = Mock()
        socket.setsockopt = Mock()
        socket.close = Mock()
        
        context.socket = Mock(return_value=socket)
        return context, socket
    
    @pytest.fixture
    def mock_config(self):
        """模拟配置"""
        config = DistributedConfig()
        config.zeromq.control_port = 5571
        config.zeromq.socket_linger = 1000
        config.zeromq.socket_timeout = 5000
        return config
    
    @pytest.fixture
    def control_server(self, mock_zmq_context, mock_config):
        """创建控制信道服务器实例"""
        context, socket = mock_zmq_context
        
        with patch('lama_cleaner.distributed.control_channel.get_config', return_value=mock_config):
            server = ControlChannelServer(zmq_context=context)
            server.control_socket = socket  # 确保使用 mock socket
            return server, socket
    
    def test_server_initialization(self, control_server, mock_config):
        """测试服务器初始化"""
        server, socket = control_server
        
        # 验证 socket 配置
        socket.setsockopt.assert_called()
        socket.bind.assert_called_with(f"tcp://*:{mock_config.zeromq.control_port}")
        
        # 验证初始状态
        assert len(server.pending_commands) == 0
        assert len(server.command_history) == 0
        assert len(server.response_callbacks) == 0
    
    def test_send_command(self, control_server):
        """测试发送命令"""
        server, socket = control_server
        
        command = ControlCommand(
            command_type=ControlCommandType.CANCEL_TASK,
            target_node="test-node-001",
            data={"task_id": "test-task-001"}
        )
        
        # 发送命令
        result = server.send_command(command)
        
        assert result is True
        assert command.command_id in server.pending_commands
        socket.send.assert_called_once()
        
        # 验证发送的数据
        call_args = socket.send.call_args[0]
        sent_data = json.loads(call_args[0].decode('utf-8'))
        assert sent_data["command_type"] == "cancel_task"
        assert sent_data["target_node"] == "test-node-001"
    
    def test_send_command_with_callback(self, control_server):
        """测试带回调的命令发送"""
        server, socket = control_server
        callback = Mock()
        
        command = ControlCommand(
            command_type=ControlCommandType.PING,
            target_node="test-node-001"
        )
        
        result = server.send_command(command, callback)
        
        assert result is True
        assert command.command_id in server.response_callbacks
        assert server.response_callbacks[command.command_id] == callback
    
    def test_receive_response(self, control_server):
        """测试接收响应"""
        server, socket = control_server
        
        # 先发送一个命令
        command = ControlCommand(
            command_type=ControlCommandType.PING,
            target_node="test-node-001"
        )
        server.send_command(command)
        
        # 模拟响应数据
        response_data = {
            "command_id": command.command_id,
            "status": "success",
            "result": {"pong": True},
            "timestamp": datetime.now().isoformat()
        }
        
        socket.recv.return_value = json.dumps(response_data).encode('utf-8')
        
        # 接收响应
        received_command = server.receive_response()
        
        assert received_command is not None
        assert received_command.command_id == command.command_id
        assert received_command.status == "success"
        assert received_command.response == response_data
        assert command.command_id not in server.pending_commands
        assert len(server.command_history) == 1
    
    def test_receive_response_with_callback(self, control_server):
        """测试带回调的响应接收"""
        server, socket = control_server
        callback = Mock()
        
        # 发送带回调的命令
        command = ControlCommand(
            command_type=ControlCommandType.PING,
            target_node="test-node-001"
        )
        server.send_command(command, callback)
        
        # 模拟响应
        response_data = {
            "command_id": command.command_id,
            "status": "success",
            "result": {"pong": True}
        }
        socket.recv.return_value = json.dumps(response_data).encode('utf-8')
        
        # 接收响应
        server.receive_response()
        
        # 验证回调被调用
        callback.assert_called_once()
        call_args = callback.call_args[0][0]
        assert call_args.command_id == command.command_id
    
    def test_convenience_methods(self, control_server):
        """测试便捷方法"""
        server, socket = control_server
        
        # 测试取消任务
        result = server.cancel_task("task-001", "node-001")
        assert result is True
        assert len(server.pending_commands) == 1
        
        # 测试更新配置
        result = server.update_node_config("node-001", {"max_tasks": 8})
        assert result is True
        assert len(server.pending_commands) == 2
        
        # 测试关闭节点
        result = server.shutdown_node("node-001", graceful=True)
        assert result is True
        assert len(server.pending_commands) == 3
        
        # 测试 ping
        result = server.ping_node("node-001")
        assert result is True
        assert len(server.pending_commands) == 4
    
    def test_cleanup_expired_commands(self, control_server):
        """测试清理过期命令"""
        server, socket = control_server
        
        # 创建一个过期命令
        old_command = ControlCommand(
            command_type=ControlCommandType.PING,
            target_node="test-node-001",
            timeout=1  # 1秒超时
        )
        old_command.created_at = datetime.now().replace(year=2020)  # 很久以前
        
        server.pending_commands[old_command.command_id] = old_command
        
        # 创建一个正常命令
        new_command = ControlCommand(
            command_type=ControlCommandType.PING,
            target_node="test-node-002"
        )
        server.pending_commands[new_command.command_id] = new_command
        
        # 执行清理
        server.cleanup_expired_commands()
        
        # 验证过期命令被清理
        assert old_command.command_id not in server.pending_commands
        assert new_command.command_id in server.pending_commands
        assert len(server.command_history) == 1
        assert server.command_history[0].status == "timeout"
    
    def test_command_history_management(self, control_server):
        """测试命令历史管理"""
        server, socket = control_server
        server.max_history_size = 3  # 设置小的历史大小用于测试
        
        # 添加多个命令到历史
        for i in range(5):
            command = ControlCommand(
                command_type=ControlCommandType.PING,
                target_node=f"node-{i}"
            )
            command.status = "completed"
            server._add_to_history(command)
        
        # 验证历史大小限制
        assert len(server.command_history) == 3
        
        # 验证保留的是最新的命令
        history = server.get_command_history()
        assert len(history) == 3
        assert history[-1].target_node == "node-4"


class TestControlChannelClient:
    """控制信道客户端测试类"""
    
    @pytest.fixture
    def mock_zmq_context(self):
        """模拟 ZMQ 上下文"""
        context = Mock()
        socket = Mock()
        
        socket.connect = Mock()
        socket.recv = Mock()
        socket.send = Mock()
        socket.setsockopt = Mock()
        socket.close = Mock()
        
        context.socket = Mock(return_value=socket)
        return context, socket
    
    @pytest.fixture
    def mock_config(self):
        """模拟配置"""
        config = DistributedConfig()
        config.zeromq.control_port = 5571
        config.zeromq.socket_linger = 1000
        config.zeromq.socket_timeout = 5000
        return config
    
    @pytest.fixture
    def control_client(self, mock_zmq_context, mock_config):
        """创建控制信道客户端实例"""
        context, socket = mock_zmq_context
        
        with patch('lama_cleaner.distributed.control_channel.get_config', return_value=mock_config):
            client = ControlChannelClient(
                node_id="test-node-001",
                scheduler_host="localhost",
                zmq_context=context
            )
            client.control_socket = socket
            return client, socket
    
    def test_client_initialization(self, control_client, mock_config):
        """测试客户端初始化"""
        client, socket = control_client
        
        assert client.node_id == "test-node-001"
        assert client.scheduler_host == "localhost"
        
        # 验证 socket 配置
        socket.setsockopt.assert_called()
        socket.connect.assert_called_with(f"tcp://localhost:{mock_config.zeromq.control_port}")
        
        # 验证命令处理器
        assert len(client.command_handlers) > 0
        assert ControlCommandType.CANCEL_TASK in client.command_handlers
        assert ControlCommandType.PING in client.command_handlers
    
    def test_register_handler(self, control_client):
        """测试注册外部处理器"""
        client, socket = control_client
        
        def custom_handler(data):
            return {"custom": "response"}
        
        client.register_handler(ControlCommandType.CANCEL_TASK, custom_handler)
        
        assert ControlCommandType.CANCEL_TASK in client.external_handlers
        assert client.external_handlers[ControlCommandType.CANCEL_TASK] == custom_handler
    
    def test_process_command_ping(self, control_client):
        """测试处理 ping 命令"""
        client, socket = control_client
        
        command_dict = {
            "command_id": "test-command-001",
            "command_type": "ping",
            "target_node": "test-node-001",
            "data": {},
            "timeout": 30,
            "created_at": datetime.now().isoformat()
        }
        
        response = client._process_command(command_dict)
        
        assert response["command_id"] == "test-command-001"
        assert response["status"] == "success"
        assert response["result"]["pong"] is True
        assert response["result"]["node_id"] == "test-node-001"
    
    def test_process_command_cancel_task(self, control_client):
        """测试处理取消任务命令"""
        client, socket = control_client
        
        command_dict = {
            "command_id": "test-command-002",
            "command_type": "cancel_task",
            "target_node": "test-node-001",
            "data": {"task_id": "test-task-001"},
            "timeout": 30,
            "created_at": datetime.now().isoformat()
        }
        
        response = client._process_command(command_dict)
        
        assert response["command_id"] == "test-command-002"
        assert response["status"] == "success"
        assert "test-task-001" in response["result"]["message"]
    
    def test_process_command_with_external_handler(self, control_client):
        """测试使用外部处理器处理命令"""
        client, socket = control_client
        
        def custom_cancel_handler(data):
            task_id = data.get("task_id")
            return {"cancelled": True, "task_id": task_id}
        
        client.register_handler(ControlCommandType.CANCEL_TASK, custom_cancel_handler)
        
        command_dict = {
            "command_id": "test-command-003",
            "command_type": "cancel_task",
            "target_node": "test-node-001",
            "data": {"task_id": "test-task-002"},
            "timeout": 30,
            "created_at": datetime.now().isoformat()
        }
        
        response = client._process_command(command_dict)
        
        assert response["status"] == "success"
        assert response["result"]["cancelled"] is True
        assert response["result"]["task_id"] == "test-task-002"
    
    def test_process_command_wrong_target(self, control_client):
        """测试处理错误目标节点的命令"""
        client, socket = control_client
        
        command_dict = {
            "command_id": "test-command-004",
            "command_type": "ping",
            "target_node": "wrong-node",  # 错误的目标节点
            "data": {},
            "timeout": 30,
            "created_at": datetime.now().isoformat()
        }
        
        response = client._process_command(command_dict)
        
        assert response["status"] == "error"
        assert "命令目标节点不匹配" in response["message"]
    
    def test_process_command_invalid_type(self, control_client):
        """测试处理无效命令类型"""
        client, socket = control_client
        
        command_dict = {
            "command_id": "test-command-005",
            "command_type": "invalid_command",
            "target_node": "test-node-001",
            "data": {},
            "timeout": 30,
            "created_at": datetime.now().isoformat()
        }
        
        # 这会抛出异常，因为 invalid_command 不是有效的枚举值
        response = client._process_command(command_dict)
        
        assert response["status"] == "error"
        assert "invalid_command" in response["message"]
    
    def test_default_command_handlers(self, control_client):
        """测试默认命令处理器"""
        client, socket = control_client
        
        # 测试获取节点状态
        result = client._handle_get_node_status({})
        assert result["node_id"] == "test-node-001"
        assert result["status"] == "online"
        
        # 测试获取节点指标
        result = client._handle_get_node_metrics({})
        assert result["node_id"] == "test-node-001"
        assert "metrics" in result
        
        # 测试更新配置
        result = client._handle_update_config({"config_updates": {"max_tasks": 8}})
        assert "配置更新命令已接收" in result["message"]
        
        # 测试关闭节点
        result = client._handle_shutdown_node({"graceful": True})
        assert "节点关闭命令已接收" in result["message"]


class TestControlChannelIntegration:
    """控制信道集成测试"""
    
    def test_command_flow_simulation(self):
        """测试命令流程模拟"""
        # 这个测试模拟完整的命令发送和响应流程
        # 在实际环境中需要真实的 ZeroMQ 连接
        
        # 创建服务器
        server_context = Mock()
        server_socket = Mock()
        server_context.socket.return_value = server_socket
        
        config = DistributedConfig()
        
        with patch('lama_cleaner.distributed.control_channel.get_config', return_value=config):
            server = ControlChannelServer(zmq_context=server_context)
            server.control_socket = server_socket
        
        # 创建客户端
        client_context = Mock()
        client_socket = Mock()
        client_context.socket.return_value = client_socket
        
        with patch('lama_cleaner.distributed.control_channel.get_config', return_value=config):
            client = ControlChannelClient(
                node_id="test-node-001",
                zmq_context=client_context
            )
            client.control_socket = client_socket
        
        # 模拟命令发送
        command = ControlCommand(
            command_type=ControlCommandType.PING,
            target_node="test-node-001"
        )
        
        server.send_command(command)
        
        # 验证服务器端
        assert command.command_id in server.pending_commands
        server_socket.send.assert_called_once()
        
        # 模拟客户端处理
        sent_data = server_socket.send.call_args[0][0]
        command_dict = json.loads(sent_data.decode('utf-8'))
        
        response = client._process_command(command_dict)
        
        # 验证响应
        assert response["status"] == "success"
        assert response["result"]["pong"] is True


if __name__ == "__main__":
    pytest.main([__file__])