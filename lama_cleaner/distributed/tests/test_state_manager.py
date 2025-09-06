"""
状态管理器测试

测试状态管理器的核心功能，包括任务状态管理、节点状态监控、
事件通知机制和 Redis 集成。
"""

import pytest
import time
import threading
from unittest.mock import Mock, MagicMock, patch
from datetime import datetime, timedelta

from ..state_manager import StateManager
from ..models import Task, TaskStatus, TaskType, TaskPriority, NodeCapability, NodeStatus, NodeType
from ..config import DistributedConfig


class TestStateManager:
    """状态管理器测试类"""
    
    @pytest.fixture
    def mock_redis(self):
        """模拟 Redis 客户端"""
        redis_mock = Mock()
        redis_mock.hset = Mock()
        redis_mock.hgetall = Mock(return_value={})
        redis_mock.expire = Mock()
        return redis_mock
    
    @pytest.fixture
    def mock_socketio(self):
        """模拟 SocketIO 客户端"""
        socketio_mock = Mock()
        socketio_mock.emit = Mock()
        return socketio_mock
    
    @pytest.fixture
    def mock_config(self):
        """模拟配置"""
        config = DistributedConfig()
        config.completed_task_ttl = 3600
        config.task_cleanup_interval = 60
        return config
    
    @pytest.fixture
    def state_manager(self, mock_redis, mock_socketio, mock_config):
        """创建状态管理器实例"""
        with patch('lama_cleaner.distributed.state_manager.get_config', return_value=mock_config):
            manager = StateManager(redis_client=mock_redis, socketio=mock_socketio)
            yield manager
            manager.shutdown()
    
    @pytest.fixture
    def sample_task(self):
        """创建示例任务"""
        return Task(
            task_id="test-task-001",
            task_type=TaskType.INPAINT,
            status=TaskStatus.PENDING,
            priority=TaskPriority.NORMAL,
            image_path="/test/image.jpg",
            config={"model": "lama", "gpu_required": True}
        )
    
    @pytest.fixture
    def sample_node(self):
        """创建示例节点"""
        node = NodeCapability(
            node_id="test-node-001",
            node_type=NodeType.LOCAL,
            gpu_count=1,
            gpu_memory=8192,
            cpu_cores=8,
            memory_total=16384,
            status=NodeStatus.ONLINE
        )
        node.last_heartbeat = datetime.now()
        return node
    
    def test_task_status_update(self, state_manager, sample_task, mock_redis, mock_socketio):
        """测试任务状态更新"""
        # 更新任务状态
        sample_task.status = TaskStatus.PROCESSING
        sample_task.assigned_node = "test-node-001"
        sample_task.updated_at = datetime.now()
        
        state_manager.update_task_status(sample_task)
        
        # 验证内存缓存
        task_state = state_manager.get_task_status(sample_task.task_id)
        assert task_state is not None
        assert task_state['status'] == TaskStatus.PROCESSING.value
        assert task_state['assigned_node'] == "test-node-001"
        
        # 验证 Redis 调用
        mock_redis.hset.assert_called()
        mock_redis.expire.assert_called()
        
        # 等待事件处理
        time.sleep(0.1)
        
        # 验证 WebSocket 通知
        mock_socketio.emit.assert_called()
    
    def test_node_status_update(self, state_manager, sample_node, mock_redis, mock_socketio):
        """测试节点状态更新"""
        state_manager.update_node_status(sample_node)
        
        # 验证内存缓存
        node_state = state_manager.get_node_status(sample_node.node_id)
        assert node_state is not None
        assert node_state['status'] == NodeStatus.ONLINE.value
        assert node_state['gpu_count'] == 1  # 内存缓存中是整数
        
        # 验证 Redis 调用
        mock_redis.hset.assert_called()
        mock_redis.expire.assert_called()
        
        # 等待事件处理
        time.sleep(1.5)  # 增加等待时间
        
        # 验证 WebSocket 通知
        mock_socketio.emit.assert_called()
    
    def test_task_cancellation(self, state_manager, sample_task):
        """测试任务取消"""
        # 先添加任务
        state_manager.update_task_status(sample_task)
        
        # 取消任务
        result = state_manager.cancel_task(sample_task.task_id)
        assert result is True
        
        # 验证状态已更新
        task_state = state_manager.get_task_status(sample_task.task_id)
        assert task_state['status'] == TaskStatus.CANCELLED.value
    
    def test_task_cancellation_invalid_task(self, state_manager):
        """测试取消不存在的任务"""
        result = state_manager.cancel_task("non-existent-task")
        assert result is False
    
    def test_task_cancellation_completed_task(self, state_manager, sample_task):
        """测试取消已完成的任务"""
        # 设置任务为已完成
        sample_task.status = TaskStatus.COMPLETED
        state_manager.update_task_status(sample_task)
        
        # 尝试取消
        result = state_manager.cancel_task(sample_task.task_id)
        assert result is False
    
    def test_system_metrics_update(self, state_manager, mock_redis, mock_socketio):
        """测试系统指标更新"""
        metrics = {
            'cpu_usage': 75.5,
            'memory_usage': 60.2,
            'queue_length': 10,
            'active_nodes': 3
        }
        
        state_manager.update_system_metrics(metrics)
        
        # 验证内存缓存
        stored_metrics = state_manager.get_system_metrics()
        assert stored_metrics['cpu_usage'] == 75.5
        assert stored_metrics['memory_usage'] == 60.2
        assert 'updated_at' in stored_metrics
        
        # 验证 Redis 调用
        mock_redis.hset.assert_called_with("system:metrics", mapping=metrics)
        mock_redis.expire.assert_called_with("system:metrics", 300)
        
        # 等待事件处理
        time.sleep(1.5)  # 增加等待时间
        
        # 验证 WebSocket 通知
        mock_socketio.emit.assert_called()
    
    def test_task_statistics(self, state_manager):
        """测试任务统计"""
        # 创建不同状态的任务
        tasks = [
            Task(task_id="task-1", status=TaskStatus.PENDING),
            Task(task_id="task-2", status=TaskStatus.PROCESSING),
            Task(task_id="task-3", status=TaskStatus.COMPLETED),
            Task(task_id="task-4", status=TaskStatus.FAILED),
            Task(task_id="task-5", status=TaskStatus.CANCELLED)
        ]
        
        for task in tasks:
            state_manager.update_task_status(task)
        
        stats = state_manager.get_task_statistics()
        assert stats['pending'] == 1
        assert stats['processing'] == 1
        assert stats['completed'] == 1
        assert stats['failed'] == 1
        assert stats['cancelled'] == 1
        assert stats['total'] == 5
    
    def test_node_statistics(self, state_manager):
        """测试节点统计"""
        # 创建不同状态的节点
        nodes = [
            NodeCapability(node_id="node-1", status=NodeStatus.ONLINE, current_load=2, max_concurrent_tasks=4),
            NodeCapability(node_id="node-2", status=NodeStatus.BUSY, current_load=4, max_concurrent_tasks=4),
            NodeCapability(node_id="node-3", status=NodeStatus.OFFLINE, current_load=0, max_concurrent_tasks=2)
        ]
        
        for node in nodes:
            state_manager.update_node_status(node)
        
        stats = state_manager.get_node_statistics()
        assert stats['online'] == 1
        assert stats['busy'] == 1
        assert stats['offline'] == 1
        assert stats['total'] == 3
        assert stats['total_load'] == 6
        assert stats['total_capacity'] == 10
    
    def test_event_callbacks(self, state_manager, sample_task):
        """测试事件回调"""
        task_callback = Mock()
        state_manager.subscribe_to_task_events(task_callback)
        
        # 更新任务状态
        state_manager.update_task_status(sample_task)
        
        # 等待事件处理
        time.sleep(1.5)  # 增加等待时间
        
        # 验证回调被调用
        task_callback.assert_called()
    
    def test_callback_subscription_management(self, state_manager):
        """测试回调订阅管理"""
        callback1 = Mock()
        callback2 = Mock()
        
        # 订阅
        state_manager.subscribe_to_task_events(callback1)
        state_manager.subscribe_to_task_events(callback2)
        assert len(state_manager.task_callbacks) == 2
        
        # 取消订阅
        state_manager.unsubscribe_from_task_events(callback1)
        assert len(state_manager.task_callbacks) == 1
        assert callback2 in state_manager.task_callbacks
    
    def test_batch_operations(self, state_manager):
        """测试批量操作"""
        # 批量更新任务
        tasks = [
            Task(task_id=f"task-{i}", status=TaskStatus.PENDING)
            for i in range(5)
        ]
        
        updated_tasks = state_manager.batch_update_task_states(tasks)
        assert len(updated_tasks) == 5
        
        # 批量更新节点
        nodes = [
            NodeCapability(node_id=f"node-{i}", status=NodeStatus.ONLINE)
            for i in range(3)
        ]
        
        updated_nodes = state_manager.batch_update_node_states(nodes)
        assert len(updated_nodes) == 3
    
    def test_query_methods(self, state_manager):
        """测试查询方法"""
        # 创建测试数据
        task1 = Task(task_id="task-1", status=TaskStatus.PROCESSING, assigned_node="node-1", queue_name="gpu-high")
        task2 = Task(task_id="task-2", status=TaskStatus.QUEUED, queue_name="gpu-high")
        task3 = Task(task_id="task-3", status=TaskStatus.COMPLETED, assigned_node="node-1")
        
        for task in [task1, task2, task3]:
            state_manager.update_task_status(task)
        
        # 测试按节点查询
        node_tasks = state_manager.get_tasks_by_node("node-1")
        assert len(node_tasks) == 2
        
        # 测试按队列查询
        queue_tasks = state_manager.get_tasks_by_queue("gpu-high")
        assert len(queue_tasks) == 2
        
        # 测试活跃任务查询
        active_tasks = state_manager.get_active_tasks()
        assert len(active_tasks) == 2
        
        # 测试已完成任务查询
        completed_tasks = state_manager.get_completed_tasks()
        assert len(completed_tasks) == 1
    
    def test_redis_fallback(self, state_manager, sample_task, mock_redis):
        """测试 Redis 故障时的降级处理"""
        # 模拟 Redis 错误
        mock_redis.hset.side_effect = Exception("Redis connection failed")
        
        # 更新任务状态不应该失败
        state_manager.update_task_status(sample_task)
        
        # 验证内存缓存仍然工作
        task_state = state_manager.get_task_status(sample_task.task_id)
        assert task_state is not None
        assert task_state['status'] == TaskStatus.PENDING.value
    
    def test_websocket_fallback(self, state_manager, sample_task, mock_socketio):
        """测试 WebSocket 故障时的降级处理"""
        # 模拟 WebSocket 错误
        mock_socketio.emit.side_effect = Exception("WebSocket connection failed")
        
        # 更新任务状态不应该失败
        state_manager.update_task_status(sample_task)
        
        # 等待事件处理
        time.sleep(0.1)
        
        # 验证内存缓存仍然工作
        task_state = state_manager.get_task_status(sample_task.task_id)
        assert task_state is not None
    
    def test_cleanup_expired_states(self, state_manager, mock_config):
        """测试过期状态清理"""
        # 创建过期任务
        old_task = Task(task_id="old-task", status=TaskStatus.COMPLETED)
        old_task.updated_at = datetime.now() - timedelta(seconds=mock_config.completed_task_ttl + 100)
        
        # 创建未过期任务
        new_task = Task(task_id="new-task", status=TaskStatus.COMPLETED)
        new_task.updated_at = datetime.now()
        
        state_manager.update_task_status(old_task)
        state_manager.update_task_status(new_task)
        
        # 执行清理
        state_manager.cleanup_expired_states()
        
        # 验证过期任务被清理
        assert state_manager.get_task_status("old-task") is None
        assert state_manager.get_task_status("new-task") is not None
    
    def test_system_status(self, state_manager):
        """测试系统状态获取"""
        # 添加一些测试数据
        task = Task(task_id="test-task", status=TaskStatus.PROCESSING)
        node = NodeCapability(node_id="test-node", status=NodeStatus.ONLINE)
        
        state_manager.update_task_status(task)
        state_manager.update_node_status(node)
        state_manager.update_system_metrics({'cpu_usage': 50.0})
        
        # 获取系统状态
        status = state_manager.get_system_status()
        
        assert 'task_statistics' in status
        assert 'node_statistics' in status
        assert 'queue_statistics' in status
        assert 'system_metrics' in status
        assert 'timestamp' in status
        
        assert status['task_statistics']['processing'] == 1
        assert status['node_statistics']['online'] == 1
    
    def test_concurrent_access(self, state_manager):
        """测试并发访问"""
        def update_task_worker(task_id):
            task = Task(task_id=task_id, status=TaskStatus.PROCESSING)
            state_manager.update_task_status(task)
        
        # 创建多个线程同时更新任务
        threads = []
        for i in range(10):
            thread = threading.Thread(target=update_task_worker, args=(f"task-{i}",))
            threads.append(thread)
            thread.start()
        
        # 等待所有线程完成
        for thread in threads:
            thread.join()
        
        # 验证所有任务都被正确更新
        stats = state_manager.get_task_statistics()
        assert stats['processing'] == 10
        assert stats['total'] == 10


class TestStateManagerIntegration:
    """状态管理器集成测试"""
    
    def test_redis_integration(self):
        """测试 Redis 集成"""
        # 这个测试需要真实的 Redis 实例
        # 在 CI/CD 环境中可以使用 Redis 容器
        pytest.skip("需要真实的 Redis 实例")
    
    def test_socketio_integration(self):
        """测试 SocketIO 集成"""
        # 这个测试需要真实的 SocketIO 服务器
        pytest.skip("需要真实的 SocketIO 服务器")


class TestStateManagerEnhancements:
    """测试状态管理器的新增功能"""
    
    @pytest.fixture
    def state_manager_with_enhanced_features(self):
        """创建具有增强功能的状态管理器"""
        mock_redis = Mock()
        mock_socketio = Mock()
        config = DistributedConfig()
        
        with patch('lama_cleaner.distributed.state_manager.get_config', return_value=config):
            manager = StateManager(redis_client=mock_redis, socketio=mock_socketio)
            yield manager
            manager.shutdown()
    
    def test_distributed_state_sync(self, state_manager_with_enhanced_features):
        """测试分布式状态同步功能"""
        manager = state_manager_with_enhanced_features
        
        # 创建任务并更新状态
        task = Task(
            task_id="sync-test-task",
            task_type=TaskType.INPAINT,
            status=TaskStatus.PROCESSING
        )
        
        # 模拟从其他节点接收状态更新
        manager.update_task_status(task)
        
        # 验证状态同步
        synced_state = manager.get_task_status(task.task_id)
        assert synced_state is not None
        assert synced_state['status'] == TaskStatus.PROCESSING.value
    
    def test_event_notification_mechanism(self, state_manager_with_enhanced_features):
        """测试事件通知机制"""
        manager = state_manager_with_enhanced_features
        
        # 设置事件回调
        task_events = []
        node_events = []
        metrics_events = []
        
        def task_callback(task_id, task_state):
            task_events.append((task_id, task_state))
        
        def node_callback(node_id, node_state):
            node_events.append((node_id, node_state))
        
        def metrics_callback(metrics):
            metrics_events.append(metrics)
        
        manager.subscribe_to_task_events(task_callback)
        manager.subscribe_to_node_events(node_callback)
        manager.subscribe_to_metrics_events(metrics_callback)
        
        # 触发各种事件
        task = Task(task_id="event-task", status=TaskStatus.PROCESSING)
        manager.update_task_status(task)
        
        node = NodeCapability(node_id="event-node", status=NodeStatus.ONLINE)
        manager.update_node_status(node)
        
        manager.update_system_metrics({'test_metric': 100})
        
        # 等待事件处理
        time.sleep(2.0)
        
        # 验证事件被正确触发
        assert len(task_events) > 0
        assert len(node_events) > 0
        assert len(metrics_events) > 0
    
    def test_redis_cache_integration(self, state_manager_with_enhanced_features):
        """测试 Redis 缓存集成"""
        manager = state_manager_with_enhanced_features
        mock_redis = manager.redis
        
        # 测试任务状态缓存
        task = Task(task_id="cache-task", status=TaskStatus.QUEUED)
        manager.update_task_status(task)
        
        # 验证 Redis 调用
        mock_redis.hset.assert_called()
        mock_redis.expire.assert_called()
        
        # 测试从 Redis 恢复状态
        mock_redis.hgetall.return_value = {
            b'task_id': b'cache-task',
            b'status': b'queued',
            b'updated_at': task.updated_at.isoformat().encode()
        }
        
        # 清除内存缓存
        manager.task_states.clear()
        
        # 从 Redis 获取状态
        cached_state = manager.get_task_status('cache-task')
        assert cached_state is not None
    
    def test_node_status_enhanced_tracking(self, state_manager_with_enhanced_features):
        """测试增强的节点状态跟踪"""
        manager = state_manager_with_enhanced_features
        
        # 创建节点并测试各种状态转换
        node = NodeCapability(
            node_id="enhanced-node",
            node_type=NodeType.REMOTE,
            status=NodeStatus.ONLINE,
            current_load=2,
            max_concurrent_tasks=4
        )
        
        # 测试在线状态
        manager.update_node_status(node)
        node_state = manager.get_node_status(node.node_id)
        assert node_state['status'] == NodeStatus.ONLINE.value
        
        # 测试忙碌状态
        node.status = NodeStatus.BUSY
        node.current_load = 4
        manager.update_node_status(node)
        node_state = manager.get_node_status(node.node_id)
        assert node_state['status'] == NodeStatus.BUSY.value
        assert node_state['current_load'] == 4  # 内存缓存中是整数
        
        # 测试离线状态
        node.status = NodeStatus.OFFLINE
        manager.update_node_status(node)
        node_state = manager.get_node_status(node.node_id)
        assert node_state['status'] == NodeStatus.OFFLINE.value
    
    def test_time_based_operations(self, state_manager_with_enhanced_features):
        """测试基于时间的操作"""
        manager = state_manager_with_enhanced_features
        
        # 测试时间戳处理
        task = Task(task_id="time-task", status=TaskStatus.PROCESSING)
        start_time = datetime.now()
        
        manager.update_task_status(task)
        
        task_state = manager.get_task_status(task.task_id)
        updated_time = datetime.fromisoformat(task_state['updated_at'])
        
        # 验证时间戳在合理范围内
        time_diff = (updated_time - start_time).total_seconds()
        assert abs(time_diff) < 1.0  # 应该在1秒内
    
    def test_error_handling_enhancements(self, state_manager_with_enhanced_features):
        """测试增强的错误处理"""
        manager = state_manager_with_enhanced_features
        
        # 测试 Redis 连接失败的处理
        manager.redis.hset.side_effect = ConnectionError("Redis connection lost")
        
        task = Task(task_id="error-task", status=TaskStatus.PROCESSING)
        
        # 应该不会抛出异常，而是优雅降级
        try:
            manager.update_task_status(task)
            # 验证内存缓存仍然工作
            task_state = manager.get_task_status(task.task_id)
            assert task_state is not None
        except Exception as e:
            pytest.fail(f"状态更新不应该因为 Redis 错误而失败: {e}")
    
    def test_performance_under_load(self, state_manager_with_enhanced_features):
        """测试高负载下的性能"""
        manager = state_manager_with_enhanced_features
        
        import time
        start_time = time.time()
        
        # 创建大量任务和节点状态更新
        for i in range(100):
            task = Task(task_id=f"perf-task-{i}", status=TaskStatus.PROCESSING)
            manager.update_task_status(task)
            
            if i % 10 == 0:  # 每10个任务创建一个节点
                node = NodeCapability(node_id=f"perf-node-{i//10}", status=NodeStatus.ONLINE)
                manager.update_node_status(node)
        
        end_time = time.time()
        processing_time = end_time - start_time
        
        # 验证性能在合理范围内（100个操作应该在2秒内完成）
        assert processing_time < 2.0, f"性能测试失败，耗时: {processing_time:.2f}秒"
        
        # 验证所有状态都被正确更新
        stats = manager.get_task_statistics()
        assert stats['processing'] == 100
        
        node_stats = manager.get_node_statistics()
        assert node_stats['online'] == 10


if __name__ == "__main__":
    pytest.main([__file__])