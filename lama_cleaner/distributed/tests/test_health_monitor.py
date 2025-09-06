"""
心跳和健康监控测试
"""

import json
import threading
import time
import unittest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timedelta

from ..health_monitor import (
    HealthMetrics, HeartbeatData, HealthCollector,
    HeartbeatSender, HeartbeatReceiver, NodeHealthChecker
)
from ..models import NodeCapability, NodeType, NodeStatus


class TestHealthMetrics(unittest.TestCase):
    """健康指标测试"""
    
    def test_health_metrics_creation(self):
        """测试健康指标创建"""
        metrics = HealthMetrics(
            timestamp=datetime.now(),
            cpu_usage=50.0,
            memory_usage=60.0,
            memory_available=4096,
            disk_usage=70.0,
            gpu_usage=80.0,
            temperature=65.0
        )
        
        self.assertEqual(metrics.cpu_usage, 50.0)
        self.assertEqual(metrics.memory_usage, 60.0)
        self.assertEqual(metrics.memory_available, 4096)
        self.assertEqual(metrics.disk_usage, 70.0)
        self.assertEqual(metrics.gpu_usage, 80.0)
        self.assertEqual(metrics.temperature, 65.0)
    
    def test_health_metrics_serialization(self):
        """测试健康指标序列化"""
        timestamp = datetime.now()
        metrics = HealthMetrics(
            timestamp=timestamp,
            cpu_usage=50.0,
            memory_usage=60.0,
            memory_available=4096,
            disk_usage=70.0
        )
        
        # 转换为字典
        data = metrics.to_dict()
        self.assertIn('timestamp', data)
        self.assertEqual(data['cpu_usage'], 50.0)
        self.assertEqual(data['memory_usage'], 60.0)
        
        # 从字典恢复
        restored_metrics = HealthMetrics.from_dict(data)
        self.assertEqual(restored_metrics.cpu_usage, 50.0)
        self.assertEqual(restored_metrics.memory_usage, 60.0)
        self.assertEqual(restored_metrics.timestamp, timestamp)


class TestHeartbeatData(unittest.TestCase):
    """心跳数据测试"""
    
    def setUp(self):
        self.health_metrics = HealthMetrics(
            timestamp=datetime.now(),
            cpu_usage=50.0,
            memory_usage=60.0,
            memory_available=4096,
            disk_usage=70.0
        )
    
    def test_heartbeat_data_creation(self):
        """测试心跳数据创建"""
        heartbeat = HeartbeatData(
            node_id="test-node-001",
            timestamp=datetime.now(),
            status=NodeStatus.ONLINE,
            current_load=2,
            total_processed=100,
            health_metrics=self.health_metrics,
            error_count=1,
            last_error="Test error"
        )
        
        self.assertEqual(heartbeat.node_id, "test-node-001")
        self.assertEqual(heartbeat.status, NodeStatus.ONLINE)
        self.assertEqual(heartbeat.current_load, 2)
        self.assertEqual(heartbeat.total_processed, 100)
        self.assertEqual(heartbeat.error_count, 1)
        self.assertEqual(heartbeat.last_error, "Test error")
    
    def test_heartbeat_data_serialization(self):
        """测试心跳数据序列化"""
        timestamp = datetime.now()
        heartbeat = HeartbeatData(
            node_id="test-node-001",
            timestamp=timestamp,
            status=NodeStatus.ONLINE,
            current_load=2,
            total_processed=100,
            health_metrics=self.health_metrics
        )
        
        # 转换为字典
        data = heartbeat.to_dict()
        self.assertEqual(data['node_id'], "test-node-001")
        self.assertEqual(data['status'], 'online')
        self.assertEqual(data['current_load'], 2)
        self.assertIn('health_metrics', data)
        
        # 从字典恢复
        restored_heartbeat = HeartbeatData.from_dict(data)
        self.assertEqual(restored_heartbeat.node_id, "test-node-001")
        self.assertEqual(restored_heartbeat.status, NodeStatus.ONLINE)
        self.assertEqual(restored_heartbeat.current_load, 2)
        self.assertEqual(restored_heartbeat.timestamp, timestamp)


class TestHealthCollector(unittest.TestCase):
    """健康指标收集器测试"""
    
    def setUp(self):
        self.collector = HealthCollector()
    
    @patch('psutil.cpu_percent')
    @patch('psutil.virtual_memory')
    @patch('psutil.disk_usage')
    def test_collect_metrics(self, mock_disk, mock_memory, mock_cpu):
        """测试指标收集"""
        # 模拟系统指标
        mock_cpu.return_value = 45.5
        
        mock_mem = Mock()
        mock_mem.percent = 65.2
        mock_mem.available = 8 * 1024 * 1024 * 1024  # 8GB
        mock_memory.return_value = mock_mem
        
        mock_disk_info = Mock()
        mock_disk_info.percent = 75.8
        mock_disk.return_value = mock_disk_info
        
        # 收集指标
        metrics = self.collector.collect_metrics()
        
        self.assertIsInstance(metrics, HealthMetrics)
        self.assertEqual(metrics.cpu_usage, 45.5)
        self.assertEqual(metrics.memory_usage, 65.2)
        self.assertEqual(metrics.memory_available, 8192)  # MB
        self.assertEqual(metrics.disk_usage, 75.8)
        self.assertIsInstance(metrics.timestamp, datetime)
    
    @patch('psutil.getloadavg')
    def test_collect_load_average(self, mock_loadavg):
        """测试负载平均值收集"""
        mock_loadavg.return_value = (1.5, 1.2, 1.0)
        
        with patch('psutil.cpu_percent', return_value=50.0):
            with patch('psutil.virtual_memory') as mock_mem:
                mock_mem.return_value.percent = 60.0
                mock_mem.return_value.available = 4 * 1024 * 1024 * 1024
                
                with patch('psutil.disk_usage') as mock_disk:
                    mock_disk.return_value.percent = 70.0
                    
                    metrics = self.collector.collect_metrics()
                    self.assertEqual(metrics.load_average, 1.5)
    
    def test_collect_metrics_with_exception(self):
        """测试指标收集异常处理"""
        with patch('psutil.cpu_percent', side_effect=Exception("CPU error")):
            metrics = self.collector.collect_metrics()
            
            # 应该返回基础指标而不是崩溃
            self.assertIsInstance(metrics, HealthMetrics)
            self.assertEqual(metrics.cpu_usage, 0.0)
            self.assertEqual(metrics.memory_usage, 0.0)
    
    def test_gpu_availability_check(self):
        """测试GPU可用性检查"""
        # 测试无GPU情况
        with patch('lama_cleaner.distributed.health_monitor.pynvml', side_effect=ImportError):
            collector = HealthCollector()
            self.assertFalse(collector.gpu_available)
        
        # 测试有GPU情况
        with patch('lama_cleaner.distributed.health_monitor.pynvml') as mock_pynvml:
            mock_pynvml.nvmlInit.return_value = None
            collector = HealthCollector()
            self.assertTrue(collector.gpu_available)


class TestHeartbeatSender(unittest.TestCase):
    """心跳发送器测试"""
    
    def setUp(self):
        self.capability = NodeCapability()
        self.capability.node_id = "test-sender-node"
        self.capability.node_type = NodeType.LOCAL
        
        self.sender = HeartbeatSender(self.capability, "localhost")
    
    def tearDown(self):
        if self.sender.is_running:
            self.sender.stop()
    
    def test_sender_initialization(self):
        """测试发送器初始化"""
        self.assertEqual(self.sender.node_capability.node_id, "test-sender-node")
        self.assertEqual(self.sender.scheduler_host, "localhost")
        self.assertFalse(self.sender.is_running)
        self.assertEqual(self.sender.current_load, 0)
        self.assertEqual(self.sender.total_processed, 0)
    
    @patch('zmq.Context')
    def test_sender_start_stop(self, mock_context):
        """测试发送器启动和停止"""
        mock_socket = Mock()
        mock_context.return_value.socket.return_value = mock_socket
        
        # 启动发送器
        self.sender.start()
        self.assertTrue(self.sender.is_running)
        self.assertIsNotNone(self.sender.heartbeat_thread)
        
        # 停止发送器
        self.sender.stop()
        self.assertFalse(self.sender.is_running)
    
    def test_update_load(self):
        """测试负载更新"""
        self.sender.update_load(5)
        self.assertEqual(self.sender.current_load, 5)
    
    def test_increment_processed(self):
        """测试处理计数增加"""
        initial_count = self.sender.total_processed
        self.sender.increment_processed()
        self.assertEqual(self.sender.total_processed, initial_count + 1)
    
    def test_report_error(self):
        """测试错误报告"""
        self.sender.report_error("Test error message")
        self.assertEqual(self.sender.error_count, 1)
        self.assertEqual(self.sender.last_error, "Test error message")
    
    @patch('zmq.Context')
    def test_heartbeat_sending(self, mock_context):
        """测试心跳发送"""
        mock_socket = Mock()
        mock_context.return_value.socket.return_value = mock_socket
        
        # 创建测试心跳数据
        health_metrics = HealthMetrics(
            timestamp=datetime.now(),
            cpu_usage=50.0,
            memory_usage=60.0,
            memory_available=4096,
            disk_usage=70.0
        )
        
        heartbeat_data = HeartbeatData(
            node_id=self.capability.node_id,
            timestamp=datetime.now(),
            status=NodeStatus.ONLINE,
            current_load=2,
            total_processed=100,
            health_metrics=health_metrics
        )
        
        # 发送心跳
        self.sender._send_heartbeat(heartbeat_data)
        
        # 验证发送调用
        mock_socket.send_multipart.assert_called_once()
        args = mock_socket.send_multipart.call_args[0][0]
        self.assertEqual(args[0], b"heartbeat")
        
        # 验证消息内容
        message_data = json.loads(args[1].decode('utf-8'))
        self.assertEqual(message_data['node_id'], self.capability.node_id)
        self.assertEqual(message_data['current_load'], 2)


class TestHeartbeatReceiver(unittest.TestCase):
    """心跳接收器测试"""
    
    def setUp(self):
        self.receiver = HeartbeatReceiver()
    
    def tearDown(self):
        if self.receiver.is_running:
            self.receiver.stop()
    
    def test_receiver_initialization(self):
        """测试接收器初始化"""
        self.assertFalse(self.receiver.is_running)
        self.assertEqual(len(self.receiver.node_heartbeats), 0)
        self.assertEqual(len(self.receiver.heartbeat_callbacks), 0)
        self.assertEqual(len(self.receiver.timeout_callbacks), 0)
    
    @patch('zmq.Context')
    def test_receiver_start_stop(self, mock_context):
        """测试接收器启动和停止"""
        mock_socket = Mock()
        mock_context.return_value.socket.return_value = mock_socket
        
        # 启动接收器
        self.receiver.start()
        self.assertTrue(self.receiver.is_running)
        self.assertIsNotNone(self.receiver.receiver_thread)
        self.assertIsNotNone(self.receiver.monitor_thread)
        
        # 停止接收器
        self.receiver.stop()
        self.assertFalse(self.receiver.is_running)
    
    def test_heartbeat_callback_management(self):
        """测试心跳回调管理"""
        callback1 = Mock()
        callback2 = Mock()
        
        # 添加回调
        self.receiver.add_heartbeat_callback(callback1)
        self.receiver.add_heartbeat_callback(callback2)
        self.assertEqual(len(self.receiver.heartbeat_callbacks), 2)
        
        # 移除回调
        self.receiver.remove_heartbeat_callback(callback1)
        self.assertEqual(len(self.receiver.heartbeat_callbacks), 1)
        self.assertIn(callback2, self.receiver.heartbeat_callbacks)
    
    def test_timeout_callback_management(self):
        """测试超时回调管理"""
        callback1 = Mock()
        callback2 = Mock()
        
        # 添加回调
        self.receiver.add_timeout_callback(callback1)
        self.receiver.add_timeout_callback(callback2)
        self.assertEqual(len(self.receiver.timeout_callbacks), 2)
        
        # 移除回调
        self.receiver.remove_timeout_callback(callback1)
        self.assertEqual(len(self.receiver.timeout_callbacks), 1)
        self.assertIn(callback2, self.receiver.timeout_callbacks)
    
    def test_handle_heartbeat_message(self):
        """测试心跳消息处理"""
        # 创建测试心跳数据
        health_metrics = HealthMetrics(
            timestamp=datetime.now(),
            cpu_usage=50.0,
            memory_usage=60.0,
            memory_available=4096,
            disk_usage=70.0
        )
        
        heartbeat_data = HeartbeatData(
            node_id="test-node-001",
            timestamp=datetime.now(),
            status=NodeStatus.ONLINE,
            current_load=2,
            total_processed=100,
            health_metrics=health_metrics
        )
        
        # 处理心跳消息
        message = json.dumps(heartbeat_data.to_dict()).encode('utf-8')
        self.receiver._handle_heartbeat_message(message)
        
        # 验证心跳数据已存储
        stored_heartbeat = self.receiver.get_node_heartbeat("test-node-001")
        self.assertIsNotNone(stored_heartbeat)
        self.assertEqual(stored_heartbeat.node_id, "test-node-001")
        self.assertEqual(stored_heartbeat.current_load, 2)
    
    def test_heartbeat_callback_execution(self):
        """测试心跳回调执行"""
        callback = Mock()
        self.receiver.add_heartbeat_callback(callback)
        
        # 创建测试心跳数据
        health_metrics = HealthMetrics(
            timestamp=datetime.now(),
            cpu_usage=50.0,
            memory_usage=60.0,
            memory_available=4096,
            disk_usage=70.0
        )
        
        heartbeat_data = HeartbeatData(
            node_id="test-node-001",
            timestamp=datetime.now(),
            status=NodeStatus.ONLINE,
            current_load=2,
            total_processed=100,
            health_metrics=health_metrics
        )
        
        # 处理心跳消息
        message = json.dumps(heartbeat_data.to_dict()).encode('utf-8')
        self.receiver._handle_heartbeat_message(message)
        
        # 验证回调被调用
        callback.assert_called_once()
        called_heartbeat = callback.call_args[0][0]
        self.assertEqual(called_heartbeat.node_id, "test-node-001")
    
    def test_get_online_nodes(self):
        """测试获取在线节点"""
        # 添加在线节点
        current_time = datetime.now()
        online_heartbeat = HeartbeatData(
            node_id="online-node",
            timestamp=current_time,
            status=NodeStatus.ONLINE,
            current_load=1,
            total_processed=50,
            health_metrics=HealthMetrics(
                timestamp=current_time,
                cpu_usage=30.0,
                memory_usage=40.0,
                memory_available=8192,
                disk_usage=50.0
            )
        )
        
        # 添加离线节点（超时）
        old_time = current_time - timedelta(minutes=10)
        offline_heartbeat = HeartbeatData(
            node_id="offline-node",
            timestamp=old_time,
            status=NodeStatus.ONLINE,
            current_load=0,
            total_processed=25,
            health_metrics=HealthMetrics(
                timestamp=old_time,
                cpu_usage=20.0,
                memory_usage=30.0,
                memory_available=4096,
                disk_usage=40.0
            )
        )
        
        # 手动添加心跳数据
        self.receiver.node_heartbeats["online-node"] = online_heartbeat
        self.receiver.node_heartbeats["offline-node"] = offline_heartbeat
        
        # 获取在线节点
        online_nodes = self.receiver.get_online_nodes()
        
        self.assertIn("online-node", online_nodes)
        self.assertNotIn("offline-node", online_nodes)
    
    def test_get_health_statistics(self):
        """测试健康统计信息"""
        # 添加测试心跳数据
        current_time = datetime.now()
        
        for i in range(3):
            heartbeat = HeartbeatData(
                node_id=f"node-{i}",
                timestamp=current_time,
                status=NodeStatus.ONLINE,
                current_load=i,
                total_processed=i * 10,
                health_metrics=HealthMetrics(
                    timestamp=current_time,
                    cpu_usage=30.0 + i * 10,
                    memory_usage=40.0 + i * 10,
                    memory_available=8192 - i * 1024,
                    disk_usage=50.0 + i * 5,
                    gpu_usage=60.0 + i * 10 if i > 0 else None,
                    temperature=65.0 + i * 5 if i > 1 else None
                )
            )
            self.receiver.node_heartbeats[f"node-{i}"] = heartbeat
        
        # 获取统计信息
        stats = self.receiver.get_health_statistics()
        
        self.assertEqual(stats['total_nodes'], 3)
        self.assertEqual(stats['online_nodes'], 3)
        self.assertEqual(stats['offline_nodes'], 0)
        
        # 验证 CPU 统计
        self.assertAlmostEqual(stats['cpu_usage']['avg'], 40.0, places=1)
        self.assertEqual(stats['cpu_usage']['max'], 50.0)
        self.assertEqual(stats['cpu_usage']['min'], 30.0)
        
        # 验证 GPU 统计（只有2个节点有GPU数据）
        self.assertIn('gpu_usage', stats)
        self.assertAlmostEqual(stats['gpu_usage']['avg'], 75.0, places=1)


class TestNodeHealthChecker(unittest.TestCase):
    """节点健康检查器测试"""
    
    def setUp(self):
        self.capability = NodeCapability()
        self.capability.node_id = "test-health-node"
        
        self.health_checker = NodeHealthChecker(self.capability)
    
    @patch.object(HealthCollector, 'collect_metrics')
    def test_health_check_healthy(self, mock_collect):
        """测试健康检查 - 健康状态"""
        # 模拟健康的指标
        mock_collect.return_value = HealthMetrics(
            timestamp=datetime.now(),
            cpu_usage=50.0,      # 低于阈值
            memory_usage=60.0,   # 低于阈值
            memory_available=2048,  # 足够的内存
            disk_usage=70.0,     # 低于阈值
            temperature=70.0     # 低于阈值
        )
        
        is_healthy = self.health_checker.check_health()
        
        self.assertTrue(is_healthy)
        self.assertTrue(self.health_checker.is_healthy)
        self.assertEqual(len(self.health_checker.health_issues), 0)
    
    @patch.object(HealthCollector, 'collect_metrics')
    def test_health_check_unhealthy(self, mock_collect):
        """测试健康检查 - 不健康状态"""
        # 模拟不健康的指标
        mock_collect.return_value = HealthMetrics(
            timestamp=datetime.now(),
            cpu_usage=95.0,      # 超过阈值
            memory_usage=95.0,   # 超过阈值
            memory_available=256,   # 内存不足
            disk_usage=98.0,     # 超过阈值
            temperature=85.0,    # 超过阈值
            gpu_usage=98.0       # GPU使用率过高
        )
        
        is_healthy = self.health_checker.check_health()
        
        self.assertFalse(is_healthy)
        self.assertFalse(self.health_checker.is_healthy)
        self.assertGreater(len(self.health_checker.health_issues), 0)
        
        # 检查具体的健康问题
        issues_text = ' '.join(self.health_checker.health_issues)
        self.assertIn("CPU使用率过高", issues_text)
        self.assertIn("内存使用率过高", issues_text)
        self.assertIn("可用内存不足", issues_text)
        self.assertIn("磁盘使用率过高", issues_text)
        self.assertIn("温度过高", issues_text)
        self.assertIn("GPU使用率过高", issues_text)
    
    @patch.object(HealthCollector, 'collect_metrics')
    def test_health_check_exception(self, mock_collect):
        """测试健康检查异常处理"""
        mock_collect.side_effect = Exception("Metrics collection failed")
        
        is_healthy = self.health_checker.check_health()
        
        self.assertFalse(is_healthy)
        self.assertFalse(self.health_checker.is_healthy)
        self.assertEqual(len(self.health_checker.health_issues), 1)
        self.assertIn("健康检查异常", self.health_checker.health_issues[0])
    
    def test_set_thresholds(self):
        """测试设置健康阈值"""
        new_thresholds = {
            'cpu_threshold': 85.0,
            'memory_threshold': 85.0,
            'temperature_threshold': 75.0
        }
        
        self.health_checker.set_thresholds(**new_thresholds)
        
        self.assertEqual(self.health_checker.cpu_threshold, 85.0)
        self.assertEqual(self.health_checker.memory_threshold, 85.0)
        self.assertEqual(self.health_checker.temperature_threshold, 75.0)
        # disk_threshold 应该保持默认值
        self.assertEqual(self.health_checker.disk_threshold, 95.0)
    
    @patch.object(HealthCollector, 'collect_metrics')
    def test_get_health_report(self, mock_collect):
        """测试获取健康报告"""
        test_metrics = HealthMetrics(
            timestamp=datetime.now(),
            cpu_usage=45.0,
            memory_usage=55.0,
            memory_available=4096,
            disk_usage=65.0,
            temperature=68.0
        )
        mock_collect.return_value = test_metrics
        
        # 执行健康检查
        self.health_checker.check_health()
        
        # 获取健康报告
        report = self.health_checker.get_health_report()
        
        self.assertEqual(report['node_id'], self.capability.node_id)
        self.assertTrue(report['is_healthy'])
        self.assertEqual(len(report['health_issues']), 0)
        self.assertIn('metrics', report)
        self.assertIn('thresholds', report)
        
        # 验证指标数据
        metrics_data = report['metrics']
        self.assertEqual(metrics_data['cpu_usage'], 45.0)
        self.assertEqual(metrics_data['memory_usage'], 55.0)
        
        # 验证阈值数据
        thresholds = report['thresholds']
        self.assertEqual(thresholds['cpu_threshold'], 90.0)
        self.assertEqual(thresholds['memory_threshold'], 90.0)


class TestHeartbeatIntegration(unittest.TestCase):
    """心跳系统集成测试"""
    
    def setUp(self):
        self.capability = NodeCapability()
        self.capability.node_id = "integration-test-node"
        self.capability.node_type = NodeType.LOCAL
    
    @patch('zmq.Context')
    def test_sender_receiver_integration(self, mock_context):
        """测试发送器和接收器集成"""
        # 模拟 ZeroMQ sockets
        mock_sender_socket = Mock()
        mock_receiver_socket = Mock()
        
        mock_context.return_value.socket.side_effect = [
            mock_sender_socket,  # 发送器 socket
            mock_receiver_socket  # 接收器 socket
        ]
        
        # 创建发送器和接收器
        sender = HeartbeatSender(self.capability, "localhost")
        receiver = HeartbeatReceiver()
        
        # 设置接收器回调
        received_heartbeats = []
        
        def heartbeat_callback(heartbeat_data):
            received_heartbeats.append(heartbeat_data)
        
        receiver.add_heartbeat_callback(heartbeat_callback)
        
        try:
            # 启动接收器
            receiver.start()
            
            # 模拟接收心跳消息
            health_metrics = HealthMetrics(
                timestamp=datetime.now(),
                cpu_usage=50.0,
                memory_usage=60.0,
                memory_available=4096,
                disk_usage=70.0
            )
            
            heartbeat_data = HeartbeatData(
                node_id=self.capability.node_id,
                timestamp=datetime.now(),
                status=NodeStatus.ONLINE,
                current_load=2,
                total_processed=100,
                health_metrics=health_metrics
            )
            
            # 直接调用消息处理方法（模拟接收）
            message = json.dumps(heartbeat_data.to_dict()).encode('utf-8')
            receiver._handle_heartbeat_message(message)
            
            # 验证心跳数据被正确处理
            self.assertEqual(len(received_heartbeats), 1)
            received_heartbeat = received_heartbeats[0]
            self.assertEqual(received_heartbeat.node_id, self.capability.node_id)
            self.assertEqual(received_heartbeat.current_load, 2)
            
            # 验证心跳数据被存储
            stored_heartbeat = receiver.get_node_heartbeat(self.capability.node_id)
            self.assertIsNotNone(stored_heartbeat)
            self.assertEqual(stored_heartbeat.node_id, self.capability.node_id)
            
        finally:
            receiver.stop()
    
    def test_timeout_detection(self):
        """测试超时检测"""
        receiver = HeartbeatReceiver()
        
        # 设置超时回调
        timed_out_nodes = []
        
        def timeout_callback(node_id):
            timed_out_nodes.append(node_id)
        
        receiver.add_timeout_callback(timeout_callback)
        
        try:
            # 添加一个过期的心跳
            old_time = datetime.now() - timedelta(minutes=10)
            old_heartbeat = HeartbeatData(
                node_id="timeout-test-node",
                timestamp=old_time,
                status=NodeStatus.ONLINE,
                current_load=1,
                total_processed=50,
                health_metrics=HealthMetrics(
                    timestamp=old_time,
                    cpu_usage=30.0,
                    memory_usage=40.0,
                    memory_available=4096,
                    disk_usage=50.0
                )
            )
            
            receiver.node_heartbeats["timeout-test-node"] = old_heartbeat
            
            # 执行超时检查
            receiver._check_node_timeouts()
            
            # 验证超时回调被调用
            self.assertEqual(len(timed_out_nodes), 1)
            self.assertEqual(timed_out_nodes[0], "timeout-test-node")
            
        finally:
            receiver.stop()


if __name__ == '__main__':
    unittest.main()