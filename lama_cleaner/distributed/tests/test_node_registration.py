"""
节点注册和发现机制测试
"""

import json
import threading
import time
import unittest
from unittest.mock import Mock, patch, MagicMock
import zmq

from ..node_manager import NodeManager
from ..worker_node import WorkerNode
from ..models import NodeCapability, NodeType, NodeStatus, Task, TaskType
from ..config import get_config


class TestNodeRegistration(unittest.TestCase):
    """节点注册测试"""
    
    def setUp(self):
        self.node_manager = NodeManager()
        
        # 创建测试节点能力
        self.test_capability = NodeCapability()
        self.test_capability.node_id = "test-node-001"
        self.test_capability.node_type = NodeType.LOCAL
        self.test_capability.cpu_cores = 8
        self.test_capability.memory_total = 16384
        self.test_capability.gpu_count = 1
        self.test_capability.gpu_memory = 8192
        self.test_capability.supported_models = ['lama', 'sd15']
        self.test_capability.supported_tasks = [TaskType.INPAINT, TaskType.PLUGIN]
        self.test_capability.max_concurrent_tasks = 3
    
    def test_register_node_success(self):
        """测试节点注册成功"""
        result = self.node_manager.register_node(self.test_capability)
        
        self.assertEqual(result['status'], 'success')
        self.assertEqual(result['node_id'], self.test_capability.node_id)
        self.assertIn('subscriptions', result)
        self.assertIn('heartbeat_interval', result)
        
        # 验证节点已被添加
        registered_node = self.node_manager.get_node(self.test_capability.node_id)
        self.assertIsNotNone(registered_node)
        self.assertEqual(registered_node.status, NodeStatus.ONLINE)
    
    def test_register_duplicate_node(self):
        """测试重复注册节点"""
        # 第一次注册
        result1 = self.node_manager.register_node(self.test_capability)
        self.assertEqual(result1['status'], 'success')
        
        # 第二次注册（应该更新现有节点）
        self.test_capability.cpu_cores = 16  # 修改配置
        result2 = self.node_manager.register_node(self.test_capability)
        self.assertEqual(result2['status'], 'success')
        
        # 验证节点信息已更新
        updated_node = self.node_manager.get_node(self.test_capability.node_id)
        self.assertEqual(updated_node.cpu_cores, 16)
    
    def test_unregister_node(self):
        """测试节点注销"""
        # 先注册节点
        self.node_manager.register_node(self.test_capability)
        self.assertIsNotNone(self.node_manager.get_node(self.test_capability.node_id))
        
        # 注销节点
        success = self.node_manager.unregister_node(self.test_capability.node_id)
        self.assertTrue(success)
        
        # 验证节点已被移除
        self.assertIsNone(self.node_manager.get_node(self.test_capability.node_id))
    
    def test_unregister_nonexistent_node(self):
        """测试注销不存在的节点"""
        success = self.node_manager.unregister_node("nonexistent-node")
        self.assertFalse(success)
    
    def test_queue_subscriptions(self):
        """测试队列订阅计算"""
        subscriptions = self.test_capability.get_queue_subscriptions()
        
        # 根据测试节点的配置，应该订阅 GPU 和 CPU 队列
        # 8GB GPU 应该订阅 gpu-high 队列
        self.assertIn("gpu-high", subscriptions)  # 8GB GPU >= 8GB
        self.assertIn("cpu-intensive", subscriptions)  # 8 CPU 核心
    
    def test_node_capability_matching(self):
        """测试节点能力匹配"""
        # 注册节点
        self.node_manager.register_node(self.test_capability)
        
        # 创建测试任务
        task = Task()
        task.task_type = TaskType.INPAINT
        task.config = {'model': 'lama', 'gpu_required': False}
        
        # 测试节点能力匹配
        self.assertTrue(self.test_capability.can_handle_task(task))
        
        # 测试不支持的模型
        task.config['model'] = 'unsupported_model'
        self.assertFalse(self.test_capability.can_handle_task(task))
        
        # 测试不支持的任务类型
        task.task_type = TaskType.SEGMENT
        self.assertFalse(self.test_capability.can_handle_task(task))


class TestNodeDiscovery(unittest.TestCase):
    """节点发现测试"""
    
    def setUp(self):
        self.node_manager = NodeManager()
        
        # 创建多个测试节点
        self.gpu_node = NodeCapability()
        self.gpu_node.node_id = "gpu-node-001"
        self.gpu_node.node_type = NodeType.LOCAL
        self.gpu_node.cpu_cores = 8
        self.gpu_node.memory_total = 32768
        self.gpu_node.gpu_count = 1
        self.gpu_node.gpu_memory = 12288
        self.gpu_node.supported_models = ['lama', 'sd15', 'sd21']
        self.gpu_node.supported_tasks = [TaskType.INPAINT, TaskType.UPSCALE]
        self.gpu_node.max_concurrent_tasks = 4
        
        self.cpu_node = NodeCapability()
        self.cpu_node.node_id = "cpu-node-001"
        self.cpu_node.node_type = NodeType.LOCAL
        self.cpu_node.cpu_cores = 16
        self.cpu_node.memory_total = 64768
        self.cpu_node.gpu_count = 0
        self.cpu_node.supported_models = ['lama', 'opencv']
        self.cpu_node.supported_tasks = [TaskType.INPAINT, TaskType.PLUGIN]
        self.cpu_node.max_concurrent_tasks = 8
        
        # 注册节点
        self.node_manager.register_node(self.gpu_node)
        self.node_manager.register_node(self.cpu_node)
    
    def test_get_all_nodes(self):
        """测试获取所有节点"""
        all_nodes = self.node_manager.get_all_nodes()
        self.assertEqual(len(all_nodes), 2)
        
        node_ids = [node.node_id for node in all_nodes]
        self.assertIn(self.gpu_node.node_id, node_ids)
        self.assertIn(self.cpu_node.node_id, node_ids)
    
    def test_get_online_nodes(self):
        """测试获取在线节点"""
        online_nodes = self.node_manager.get_online_nodes()
        self.assertEqual(len(online_nodes), 2)
        
        # 将一个节点设为离线
        self.cpu_node.status = NodeStatus.OFFLINE
        online_nodes = self.node_manager.get_online_nodes()
        self.assertEqual(len(online_nodes), 1)
        self.assertEqual(online_nodes[0].node_id, self.gpu_node.node_id)
    
    def test_find_available_nodes_for_task(self):
        """测试为任务查找可用节点"""
        # GPU 任务
        gpu_task = Task()
        gpu_task.task_type = TaskType.INPAINT
        gpu_task.config = {'model': 'sd15', 'gpu_required': True}
        
        available_nodes = self.node_manager.get_available_nodes(gpu_task)
        self.assertEqual(len(available_nodes), 1)
        self.assertEqual(available_nodes[0].node_id, self.gpu_node.node_id)
        
        # CPU 任务
        cpu_task = Task()
        cpu_task.task_type = TaskType.INPAINT
        cpu_task.config = {'model': 'lama', 'gpu_required': False}
        
        available_nodes = self.node_manager.get_available_nodes(cpu_task)
        self.assertEqual(len(available_nodes), 2)  # 两个节点都支持
    
    def test_find_best_node_for_task(self):
        """测试为任务找到最佳节点"""
        task = Task()
        task.task_type = TaskType.INPAINT
        task.config = {'model': 'lama'}
        
        # 设置不同的负载
        self.gpu_node.current_load = 2
        self.cpu_node.current_load = 1
        
        best_node = self.node_manager.find_best_node_for_task(task)
        self.assertEqual(best_node.node_id, self.cpu_node.node_id)  # 负载更低
    
    def test_node_load_management(self):
        """测试节点负载管理"""
        node_id = self.gpu_node.node_id
        
        # 增加负载
        self.node_manager.update_node_load(node_id, 2)
        updated_node = self.node_manager.get_node(node_id)
        self.assertEqual(updated_node.current_load, 2)
        
        # 减少负载
        self.node_manager.update_node_load(node_id, -1)
        updated_node = self.node_manager.get_node(node_id)
        self.assertEqual(updated_node.current_load, 1)
        
        # 负载不能为负数
        self.node_manager.update_node_load(node_id, -10)
        updated_node = self.node_manager.get_node(node_id)
        self.assertEqual(updated_node.current_load, 0)
    
    def test_node_statistics(self):
        """测试节点统计信息"""
        stats = self.node_manager.get_node_statistics()
        
        self.assertEqual(stats['total_nodes'], 2)
        self.assertEqual(stats['online_nodes'], 2)
        self.assertEqual(stats['offline_nodes'], 0)
        self.assertEqual(stats['total_capacity'], 12)  # 4 + 8
        self.assertEqual(stats['current_load'], 0)
        self.assertIn('local', stats['node_types'])
        self.assertEqual(stats['node_types']['local'], 2)


class TestHeartbeatMechanism(unittest.TestCase):
    """心跳机制测试"""
    
    def setUp(self):
        self.node_manager = NodeManager()
        
        self.test_node = NodeCapability()
        self.test_node.node_id = "heartbeat-test-node"
        self.test_node.node_type = NodeType.LOCAL
        
        self.node_manager.register_node(self.test_node)
    
    def test_heartbeat_update(self):
        """测试心跳更新"""
        node_id = self.test_node.node_id
        heartbeat_data = {
            'current_load': 3,
            'total_processed': 100,
            'timestamp': '2024-01-01T12:00:00'
        }
        
        # 更新心跳
        self.node_manager.update_node_heartbeat(node_id, heartbeat_data)
        
        # 验证节点信息已更新
        updated_node = self.node_manager.get_node(node_id)
        self.assertEqual(updated_node.current_load, 3)
        self.assertEqual(updated_node.total_processed, 100)
        self.assertEqual(updated_node.status, NodeStatus.ONLINE)
        self.assertIsNotNone(updated_node.last_heartbeat)
    
    def test_heartbeat_unknown_node(self):
        """测试未知节点的心跳"""
        # 不应该抛出异常，只是记录警告
        self.node_manager.update_node_heartbeat("unknown-node", {})
    
    def test_heartbeat_callback(self):
        """测试心跳回调"""
        callback_called = False
        callback_data = None
        
        def test_callback(node_id, data):
            nonlocal callback_called, callback_data
            callback_called = True
            callback_data = (node_id, data)
        
        # 注册回调
        self.node_manager.add_heartbeat_callback(test_callback)
        
        # 发送心跳
        heartbeat_data = {'test': 'data'}
        self.node_manager.update_node_heartbeat(self.test_node.node_id, heartbeat_data)
        
        # 验证回调被调用
        self.assertTrue(callback_called)
        self.assertEqual(callback_data[0], self.test_node.node_id)
        self.assertEqual(callback_data[1], heartbeat_data)
        
        # 移除回调
        self.node_manager.remove_heartbeat_callback(test_callback)
    
    @patch('lama_cleaner.distributed.node_manager.datetime')
    def test_node_timeout_detection(self, mock_datetime):
        """测试节点超时检测"""
        from datetime import datetime, timedelta
        
        # 设置当前时间
        current_time = datetime(2024, 1, 1, 12, 0, 0)
        mock_datetime.now.return_value = current_time
        
        # 设置节点最后心跳时间（超时）
        timeout_time = current_time - timedelta(seconds=120)  # 2分钟前
        self.test_node.last_heartbeat = timeout_time
        self.test_node.status = NodeStatus.ONLINE
        
        # 执行超时检查
        self.node_manager._check_node_timeouts()
        
        # 验证节点被标记为离线
        updated_node = self.node_manager.get_node(self.test_node.node_id)
        self.assertEqual(updated_node.status, NodeStatus.OFFLINE)


class TestControlCommands(unittest.TestCase):
    """控制命令测试"""
    
    def setUp(self):
        self.node_manager = NodeManager()
    
    def test_handle_register_command(self):
        """测试处理注册命令"""
        capability_data = {
            'node_id': 'test-node',
            'node_type': 'local',
            'cpu_cores': 4,
            'memory_total': 8192
        }
        
        message = {
            'action': 'register',
            'data': capability_data
        }
        
        response = self.node_manager._handle_control_message(message)
        
        self.assertEqual(response['status'], 'success')
        self.assertEqual(response['node_id'], 'test-node')
        self.assertIn('subscriptions', response)
    
    def test_handle_unregister_command(self):
        """测试处理注销命令"""
        # 先注册一个节点
        capability = NodeCapability()
        capability.node_id = 'test-node'
        self.node_manager.register_node(capability)
        
        # 注销节点
        message = {
            'action': 'unregister',
            'data': {'node_id': 'test-node'}
        }
        
        response = self.node_manager._handle_control_message(message)
        self.assertEqual(response['status'], 'success')
        
        # 验证节点已被移除
        self.assertIsNone(self.node_manager.get_node('test-node'))
    
    def test_handle_get_queues_command(self):
        """测试获取队列配置命令"""
        message = {
            'action': 'get_queues',
            'data': {}
        }
        
        response = self.node_manager._handle_control_message(message)
        
        self.assertEqual(response['status'], 'success')
        self.assertIn('queues', response)
        self.assertIsInstance(response['queues'], dict)
    
    def test_handle_unknown_command(self):
        """测试处理未知命令"""
        message = {
            'action': 'unknown_action',
            'data': {}
        }
        
        response = self.node_manager._handle_control_message(message)
        
        self.assertEqual(response['status'], 'error')
        self.assertIn('未知操作', response['message'])
    
    def test_handle_malformed_message(self):
        """测试处理格式错误的消息"""
        message = {
            'action': 'register',
            'data': None  # 无效的 data 字段
        }
        
        response = self.node_manager._handle_control_message(message)
        self.assertEqual(response['status'], 'error')


class TestWorkerNodeIntegration(unittest.TestCase):
    """工作节点集成测试"""
    
    def setUp(self):
        # 创建测试配置
        self.node_config = {
            'node_type': 'local',
            'host': 'localhost'
        }
        
        # 创建测试能力
        self.test_capability = NodeCapability()
        self.test_capability.node_id = "worker-test-node"
        self.test_capability.cpu_cores = 4
        self.test_capability.memory_total = 8192
        self.test_capability.supported_models = ['lama']
        self.test_capability.supported_tasks = [TaskType.INPAINT]
        self.test_capability.max_concurrent_tasks = 2
    
    @patch('lama_cleaner.distributed.worker_node.detect_node_capability')
    def test_worker_node_creation(self, mock_detect):
        """测试工作节点创建"""
        mock_detect.return_value = self.test_capability
        
        worker = WorkerNode(self.node_config)
        
        self.assertEqual(worker.capability.node_id, self.test_capability.node_id)
        self.assertEqual(worker.capability.cpu_cores, 4)
        self.assertFalse(worker.is_running)
    
    def test_worker_node_with_capability_file(self):
        """测试从配置文件创建工作节点"""
        import tempfile
        import json
        
        # 创建临时配置文件
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            config_data = {
                'node_info': {'node_id': self.test_capability.node_id},
                'hardware': {
                    'cpu_cores': self.test_capability.cpu_cores,
                    'memory_total': self.test_capability.memory_total
                },
                'capabilities': {
                    'supported_models': self.test_capability.supported_models,
                    'supported_tasks': [t.value for t in self.test_capability.supported_tasks],
                    'max_concurrent_tasks': self.test_capability.max_concurrent_tasks
                }
            }
            json.dump(config_data, f)
            capability_file = f.name
        
        try:
            node_config = self.node_config.copy()
            node_config['capability_file'] = capability_file
            
            worker = WorkerNode(node_config)
            
            self.assertEqual(worker.capability.node_id, self.test_capability.node_id)
            self.assertEqual(worker.capability.cpu_cores, 4)
            
        finally:
            import os
            os.unlink(capability_file)
    
    def test_worker_node_status(self):
        """测试工作节点状态"""
        worker = WorkerNode(self.node_config, self.test_capability)
        
        status = worker.get_status()
        
        self.assertEqual(status['node_id'], self.test_capability.node_id)
        self.assertEqual(status['node_type'], 'local')
        self.assertFalse(status['is_running'])
        self.assertEqual(status['current_tasks'], 0)
        self.assertEqual(status['max_concurrent_tasks'], 2)
        self.assertIn('supported_models', status)
        self.assertIn('queue_subscriptions', status)
    
    def test_task_callback_registration(self):
        """测试任务回调注册"""
        worker = WorkerNode(self.node_config, self.test_capability)
        
        callback_called = False
        
        def test_callback(task):
            nonlocal callback_called
            callback_called = True
        
        worker.register_task_callback('inpaint', test_callback)
        
        # 验证回调已注册
        self.assertIn('inpaint', worker.task_callbacks)
        self.assertEqual(worker.task_callbacks['inpaint'], test_callback)


class TestNodeManagerLifecycle(unittest.TestCase):
    """节点管理器生命周期测试"""
    
    @patch('zmq.Context')
    def test_node_manager_start_stop(self, mock_context):
        """测试节点管理器启动和停止"""
        mock_socket = Mock()
        mock_context.return_value.socket.return_value = mock_socket
        
        node_manager = NodeManager()
        
        # 测试启动
        with patch.object(node_manager, '_start_threads'):
            node_manager.start()
            self.assertTrue(node_manager._running)
        
        # 测试停止
        with patch.object(threading.Thread, 'join'):
            node_manager.stop()
            self.assertFalse(node_manager._running)
    
    def test_socket_setup(self):
        """测试 socket 设置"""
        with patch('zmq.Context') as mock_context:
            mock_socket = Mock()
            mock_context.return_value.socket.return_value = mock_socket
            
            node_manager = NodeManager()
            node_manager._setup_sockets()
            
            # 验证 socket 创建和配置
            self.assertEqual(mock_context.return_value.socket.call_count, 2)  # REP + SUB
            mock_socket.bind.assert_called()
            mock_socket.setsockopt.assert_called()


class TestErrorHandling(unittest.TestCase):
    """错误处理测试"""
    
    def setUp(self):
        self.node_manager = NodeManager()
    
    def test_invalid_capability_data(self):
        """测试无效的节点能力数据"""
        invalid_message = {
            'action': 'register',
            'data': {
                'invalid_field': 'invalid_value'
                # 缺少必要字段
            }
        }
        
        response = self.node_manager._handle_control_message(invalid_message)
        self.assertEqual(response['status'], 'error')
    
    def test_heartbeat_parsing_error(self):
        """测试心跳消息解析错误"""
        # 不应该抛出异常
        invalid_message = b"invalid json data"
        self.node_manager._handle_heartbeat_message(invalid_message)
    
    def test_concurrent_node_operations(self):
        """测试并发节点操作"""
        import concurrent.futures
        
        def register_node(i):
            capability = NodeCapability()
            capability.node_id = f"concurrent-node-{i}"
            return self.node_manager.register_node(capability)
        
        # 并发注册多个节点
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(register_node, i) for i in range(20)]
            results = [f.result() for f in concurrent.futures.as_completed(futures)]
        
        # 验证所有节点都注册成功
        self.assertEqual(len(results), 20)
        for result in results:
            self.assertEqual(result['status'], 'success')
        
        # 验证节点数量
        self.assertEqual(len(self.node_manager.get_all_nodes()), 20)


if __name__ == '__main__':
    unittest.main()