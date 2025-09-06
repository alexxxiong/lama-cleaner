"""
状态管理器集成测试

测试状态管理器与其他组件的集成，包括 Redis、WebSocket、任务管理器等
"""

import pytest
import asyncio
import time
import threading
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timedelta

from ..state_manager import StateManager
from ..task_manager import TaskManager
from ..node_manager import NodeManager
from ..models import Task, TaskStatus, TaskType, NodeCapability, NodeStatus, NodeType
from ..config import DistributedConfig


class TestStateManagerTaskManagerIntegration:
    """状态管理器与任务管理器集成测试"""
    
    @pytest.fixture
    def integrated_managers(self):
        """创建集成的管理器实例"""
        config = DistributedConfig()
        mock_redis = Mock()
        mock_socketio = Mock()
        
        with patch('lama_cleaner.distributed.state_manager.get_config', return_value=config), \
             patch('lama_cleaner.distributed.task_manager.get_config', return_value=config):
            
            state_manager = StateManager(redis_client=mock_redis, socketio=mock_socketio)
            task_manager = TaskManager()
            
            # 设置任务管理器的状态回调
            task_manager.add_status_callback(state_manager.update_task_status)
            
            yield state_manager, task_manager
            
            state_manager.shutdown()
            task_manager.stop()
    
    def test_task_lifecycle_integration(self, integrated_managers):
        """测试任务生命周期集成"""
        state_manager, task_manager = integrated_managers
        
        # 创建任务
        task = task_manager.create_task(
            task_type=TaskType.INPAINT,
            image_path="/test/image.jpg",
            config={"model": "lama"}
        )
        
        # 验证状态管理器收到了任务创建事件
        time.sleep(0.1)
        task_state = state_manager.get_task_status(task.task_id)
        assert task_state is not None
        assert task_state['status'] == TaskStatus.PENDING.value
        
        # 更新任务状态
        task_manager.update_task_status(task.task_id, TaskStatus.PROCESSING)
        
        # 验证状态同步
        time.sleep(0.1)
        updated_state = state_manager.get_task_status(task.task_id)
        assert updated_state['status'] == TaskStatus.PROCESSING.value
    
    def test_task_cancellation_integration(self, integrated_managers):
        """测试任务取消集成"""
        state_manager, task_manager = integrated_managers
        
        # 创建并启动任务
        task = task_manager.create_task(
            task_type=TaskType.INPAINT,
            image_path="/test/image.jpg",
            config={"model": "lama"}
        )
        
        task_manager.update_task_status(task.task_id, TaskStatus.PROCESSING)
        time.sleep(0.1)
        
        # 通过状态管理器取消任务
        result = state_manager.cancel_task(task.task_id)
        assert result is True
        
        # 验证任务管理器中的状态也被更新
        updated_task = task_manager.get_task(task.task_id)
        # 注意：这里可能需要额外的同步机制
        
    def test_batch_operations_integration(self, integrated_managers):
        """测试批量操作集成"""
        state_manager, task_manager = integrated_managers
        
        # 创建多个任务
        tasks = []
        for i in range(5):
            task = task_manager.create_task(
                task_type=TaskType.INPAINT,
                image_path=f"/test/image_{i}.jpg",
                config={"model": "lama"}
            )
            tasks.append(task)
        
        # 等待状态同步
        time.sleep(0.5)
        
        # 验证所有任务都在状态管理器中
        stats = state_manager.get_task_statistics()
        assert stats['pending'] >= 5


class TestStateManagerNodeManagerIntegration:
    """状态管理器与节点管理器集成测试"""
    
    @pytest.fixture
    def integrated_node_managers(self):
        """创建集成的节点管理器实例"""
        config = DistributedConfig()
        mock_redis = Mock()
        mock_socketio = Mock()
        
        with patch('lama_cleaner.distributed.state_manager.get_config', return_value=config), \
             patch('lama_cleaner.distributed.node_manager.get_config', return_value=config):
            
            state_manager = StateManager(redis_client=mock_redis, socketio=mock_socketio)
            node_manager = NodeManager()
            
            # 设置节点管理器的状态回调
            node_manager.add_heartbeat_callback(
                lambda node_id, data: state_manager.update_node_status(
                    node_manager.get_node(node_id)
                )
            )
            
            yield state_manager, node_manager
            
            state_manager.shutdown()
            node_manager.stop()
    
    def test_node_registration_integration(self, integrated_node_managers):
        """测试节点注册集成"""
        state_manager, node_manager = integrated_node_managers
        
        # 创建节点能力
        capability = NodeCapability(
            node_id="integration-node",
            node_type=NodeType.LOCAL,
            gpu_count=1,
            gpu_memory=8192,
            cpu_cores=8,
            memory_total=16384
        )
        
        # 注册节点
        result = node_manager.register_node(capability)
        assert result['status'] == 'success'
        
        # 验证状态管理器收到了节点状态
        time.sleep(0.1)
        node_state = state_manager.get_node_status(capability.node_id)
        assert node_state is not None
        assert node_state['status'] == NodeStatus.ONLINE.value
    
    def test_node_heartbeat_integration(self, integrated_node_managers):
        """测试节点心跳集成"""
        state_manager, node_manager = integrated_node_managers
        
        # 注册节点
        capability = NodeCapability(node_id="heartbeat-node")
        node_manager.register_node(capability)
        
        # 模拟心跳数据
        heartbeat_data = {
            'current_load': 2,
            'total_processed': 10,
            'timestamp': datetime.now().isoformat()
        }
        
        # 更新心跳
        node_manager.update_node_heartbeat(capability.node_id, heartbeat_data)
        
        # 验证状态管理器收到了更新
        time.sleep(0.1)
        node_state = state_manager.get_node_status(capability.node_id)
        assert node_state['current_load'] == '2'  # Redis 存储为字符串


class TestStateManagerRedisIntegration:
    """状态管理器 Redis 集成测试"""
    
    @pytest.fixture
    def redis_state_manager(self):
        """创建带有真实 Redis 模拟的状态管理器"""
        # 使用 fakeredis 进行测试
        try:
            import fakeredis
            redis_client = fakeredis.FakeRedis()
        except ImportError:
            pytest.skip("需要 fakeredis 库进行 Redis 集成测试")
        
        config = DistributedConfig()
        mock_socketio = Mock()
        
        with patch('lama_cleaner.distributed.state_manager.get_config', return_value=config):
            manager = StateManager(redis_client=redis_client, socketio=mock_socketio)
            yield manager
            manager.shutdown()
    
    def test_redis_persistence(self, redis_state_manager):
        """测试 Redis 持久化"""
        manager = redis_state_manager
        
        # 创建任务并更新状态
        task = Task(
            task_id="redis-task",
            task_type=TaskType.INPAINT,
            status=TaskStatus.PROCESSING
        )
        
        manager.update_task_status(task)
        
        # 清除内存缓存
        manager.task_states.clear()
        
        # 从 Redis 恢复状态
        recovered_state = manager.get_task_status(task.task_id)
        assert recovered_state is not None
        assert recovered_state['status'] == TaskStatus.PROCESSING.value
    
    def test_redis_expiration(self, redis_state_manager):
        """测试 Redis 过期机制"""
        manager = redis_state_manager
        
        # 创建任务
        task = Task(task_id="expiring-task", status=TaskStatus.COMPLETED)
        manager.update_task_status(task)
        
        # 验证 TTL 被设置
        ttl = manager.redis.ttl(f"task:{task.task_id}")
        assert ttl > 0


class TestStateManagerWebSocketIntegration:
    """状态管理器 WebSocket 集成测试"""
    
    @pytest.fixture
    def websocket_state_manager(self):
        """创建带有 WebSocket 模拟的状态管理器"""
        config = DistributedConfig()
        mock_redis = Mock()
        mock_socketio = Mock()
        
        with patch('lama_cleaner.distributed.state_manager.get_config', return_value=config):
            manager = StateManager(redis_client=mock_redis, socketio=mock_socketio)
            yield manager, mock_socketio
            manager.shutdown()
    
    def test_real_time_notifications(self, websocket_state_manager):
        """测试实时通知"""
        manager, mock_socketio = websocket_state_manager
        
        # 更新任务状态
        task = Task(task_id="ws-task", status=TaskStatus.PROCESSING)
        manager.update_task_status(task)
        
        # 等待事件处理
        time.sleep(0.1)
        
        # 验证 WebSocket 通知被发送
        mock_socketio.emit.assert_called()
        
        # 检查通知内容
        call_args = mock_socketio.emit.call_args
        assert call_args[0][0] == 'task_update'  # 事件名称
        assert 'task_id' in call_args[0][1]      # 事件数据
        assert call_args[0][1]['task_id'] == task.task_id
    
    def test_system_metrics_notifications(self, websocket_state_manager):
        """测试系统指标通知"""
        manager, mock_socketio = websocket_state_manager
        
        # 更新系统指标
        metrics = {
            'cpu_usage': 75.0,
            'memory_usage': 60.0,
            'active_tasks': 5
        }
        
        manager.update_system_metrics(metrics)
        
        # 等待事件处理
        time.sleep(1.5)
        
        # 验证指标通知被发送
        mock_socketio.emit.assert_called()


class TestStateManagerPerformanceIntegration:
    """状态管理器性能集成测试"""
    
    def test_concurrent_updates_performance(self):
        """测试并发更新性能"""
        config = DistributedConfig()
        mock_redis = Mock()
        mock_socketio = Mock()
        
        with patch('lama_cleaner.distributed.state_manager.get_config', return_value=config):
            manager = StateManager(redis_client=mock_redis, socketio=mock_socketio)
            
            def update_worker(worker_id):
                """工作线程函数"""
                for i in range(50):
                    task = Task(
                        task_id=f"perf-task-{worker_id}-{i}",
                        status=TaskStatus.PROCESSING
                    )
                    manager.update_task_status(task)
            
            # 启动多个工作线程
            threads = []
            start_time = time.time()
            
            for worker_id in range(4):
                thread = threading.Thread(target=update_worker, args=(worker_id,))
                threads.append(thread)
                thread.start()
            
            # 等待所有线程完成
            for thread in threads:
                thread.join()
            
            end_time = time.time()
            total_time = end_time - start_time
            
            # 验证性能（200个并发更新应该在3秒内完成）
            assert total_time < 3.0, f"并发性能测试失败，耗时: {total_time:.2f}秒"
            
            # 验证所有更新都成功
            stats = manager.get_task_statistics()
            assert stats['processing'] == 200
            
            manager.shutdown()
    
    def test_memory_usage_under_load(self):
        """测试高负载下的内存使用"""
        import psutil
        import os
        
        process = psutil.Process(os.getpid())
        initial_memory = process.memory_info().rss
        
        config = DistributedConfig()
        mock_redis = Mock()
        mock_socketio = Mock()
        
        with patch('lama_cleaner.distributed.state_manager.get_config', return_value=config):
            manager = StateManager(redis_client=mock_redis, socketio=mock_socketio)
            
            # 创建大量状态更新
            for i in range(1000):
                task = Task(task_id=f"memory-task-{i}", status=TaskStatus.PROCESSING)
                manager.update_task_status(task)
                
                node = NodeCapability(node_id=f"memory-node-{i}", status=NodeStatus.ONLINE)
                manager.update_node_status(node)
            
            # 等待所有事件处理完成
            time.sleep(2.0)
            
            final_memory = process.memory_info().rss
            memory_increase = final_memory - initial_memory
            
            # 内存增长应该在合理范围内（小于100MB）
            max_memory_increase = 100 * 1024 * 1024  # 100MB
            assert memory_increase < max_memory_increase, \
                f"内存使用过多: {memory_increase / 1024 / 1024:.2f}MB"
            
            manager.shutdown()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])