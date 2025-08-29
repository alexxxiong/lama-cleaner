"""
队列管理器集成测试

测试队列管理器与任务管理器、状态管理器等其他组件的集成功能
"""

import pytest
import time
import threading
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime

from lama_cleaner.distributed.queue_manager import QueueManager
from lama_cleaner.distributed.task_manager import TaskManager
from lama_cleaner.distributed.state_manager import StateManager
from lama_cleaner.distributed.models import Task, TaskType, TaskPriority, QueueConfig
from lama_cleaner.distributed.config import DistributedConfig, ZeroMQConfig


class TestQueueManagerIntegration:
    """队列管理器集成测试"""
    
    @pytest.fixture
    def mock_config(self):
        """创建模拟配置"""
        config = DistributedConfig()
        config.zeromq = ZeroMQConfig(
            host="localhost",
            base_port=16555,  # 使用不同端口避免冲突
            context_io_threads=1,
            socket_linger=100
        )
        
        config.queues = {
            "integration-gpu": QueueConfig(
                name="integration-gpu",
                port=16555,
                requirements={
                    "gpu": True,
                    "gpu_memory": 4096,
                    "models": ["lama", "sd15"]
                },
                max_size=100
            ),
            "integration-cpu": QueueConfig(
                name="integration-cpu", 
                port=16556,
                requirements={
                    "cpu_cores": 4,
                    "memory": 8192,
                    "models": ["opencv"]
                },
                max_size=50
            )
        }
        
        return config
    
    @pytest.fixture
    def queue_manager(self, mock_config):
        """创建队列管理器实例"""
        with patch('lama_cleaner.distributed.queue_manager.get_config', return_value=mock_config):
            manager = QueueManager()
            yield manager
            if hasattr(manager, '_running') and manager._running:
                manager.stop()
    
    @pytest.fixture
    def task_manager(self, mock_config):
        """创建任务管理器实例"""
        with patch('lama_cleaner.distributed.task_manager.get_config', return_value=mock_config):
            manager = TaskManager()
            yield manager
            if hasattr(manager, '_running') and manager._running:
                manager.stop()
    
    @pytest.fixture
    def state_manager(self):
        """创建状态管理器实例"""
        mock_redis = Mock()
        mock_socketio = Mock()
        manager = StateManager(redis_client=mock_redis, socketio=mock_socketio)
        return manager
    
    def test_task_routing_and_submission_workflow(self, queue_manager, task_manager, state_manager):
        """测试任务路由和提交的完整工作流"""
        # 模拟 socket 以避免实际网络操作
        mock_socket = Mock()
        
        with patch.object(queue_manager.context, 'socket', return_value=mock_socket):
            # 初始化队列管理器
            queue_manager._setup_queues()
            
            # 创建测试任务
            task = task_manager.create_task(
                task_type=TaskType.INPAINT,
                image_path="/test/image.jpg",
                config={"model": "lama", "device": "cuda"}
            )
            
            # 路由任务到合适的队列
            selected_queue = queue_manager.route_task(task)
            assert selected_queue == "integration-gpu"
            
            # 发送任务到队列
            result = queue_manager.send_task(selected_queue, task)
            assert result is True
            
            # 验证任务状态更新
            state_manager.update_task_status(task)
            
            # 验证队列统计更新
            stats = queue_manager.get_queue_stats(selected_queue)
            assert stats['pending_count'] == 1
            assert stats['total_sent'] == 1
    
    def test_multiple_tasks_load_balancing(self, queue_manager, task_manager):
        """测试多任务负载均衡"""
        mock_socket = Mock()
        
        with patch.object(queue_manager.context, 'socket', return_value=mock_socket):
            queue_manager._setup_queues()
            
            # 创建多个 GPU 任务
            tasks = []
            for i in range(5):
                task = task_manager.create_task(
                    task_type=TaskType.INPAINT,
                    image_path=f"/test/image_{i}.jpg",
                    config={"model": "lama", "device": "cuda"}
                )
                tasks.append(task)
            
            # 提交所有任务
            for task in tasks:
                queue_name = queue_manager.route_task(task)
                result = queue_manager.send_task(queue_name, task)
                assert result is True
            
            # 验证所有任务都被路由到 GPU 队列
            gpu_stats = queue_manager.get_queue_stats("integration-gpu")
            assert gpu_stats['pending_count'] == 5
            assert gpu_stats['total_sent'] == 5
    
    def test_mixed_task_types_routing(self, queue_manager, task_manager):
        """测试混合任务类型的路由"""
        mock_socket = Mock()
        
        with patch.object(queue_manager.context, 'socket', return_value=mock_socket):
            queue_manager._setup_queues()
            
            # 创建 GPU 任务
            gpu_task = task_manager.create_task(
                task_type=TaskType.INPAINT,
                image_path="/test/gpu_image.jpg",
                config={"model": "sd15", "device": "cuda"}
            )
            
            # 创建 CPU 任务
            cpu_task = task_manager.create_task(
                task_type=TaskType.INPAINT,
                image_path="/test/cpu_image.jpg",
                config={"model": "opencv", "device": "cpu"}
            )
            
            # 路由和发送任务
            gpu_queue = queue_manager.route_task(gpu_task)
            cpu_queue = queue_manager.route_task(cpu_task)
            
            assert gpu_queue == "integration-gpu"
            assert cpu_queue == "integration-cpu"
            
            # 发送任务
            assert queue_manager.send_task(gpu_queue, gpu_task) is True
            assert queue_manager.send_task(cpu_queue, cpu_task) is True
            
            # 验证统计信息
            gpu_stats = queue_manager.get_queue_stats("integration-gpu")
            cpu_stats = queue_manager.get_queue_stats("integration-cpu")
            
            assert gpu_stats['pending_count'] == 1
            assert cpu_stats['pending_count'] == 1
    
    def test_queue_capacity_management(self, queue_manager, task_manager):
        """测试队列容量管理"""
        mock_socket = Mock()
        
        with patch.object(queue_manager.context, 'socket', return_value=mock_socket):
            queue_manager._setup_queues()
            
            # 模拟队列接近容量限制
            queue_manager.queue_stats["integration-cpu"]["pending_count"] = 49  # 接近50的限制
            
            # 创建 CPU 任务
            task1 = task_manager.create_task(
                task_type=TaskType.INPAINT,
                image_path="/test/image1.jpg",
                config={"model": "opencv", "device": "cpu"}
            )
            
            task2 = task_manager.create_task(
                task_type=TaskType.INPAINT,
                image_path="/test/image2.jpg",
                config={"model": "opencv", "device": "cpu"}
            )
            
            # 第一个任务应该成功
            queue_name = queue_manager.route_task(task1)
            result1 = queue_manager.send_task(queue_name, task1)
            assert result1 is True
            
            # 第二个任务应该失败（容量已满）
            queue_name = queue_manager.route_task(task2)
            result2 = queue_manager.send_task(queue_name, task2)
            assert result2 is False
    
    def test_concurrent_task_submission(self, queue_manager, task_manager):
        """测试并发任务提交"""
        mock_socket = Mock()
        
        with patch.object(queue_manager.context, 'socket', return_value=mock_socket):
            queue_manager._setup_queues()
            
            results = []
            
            def submit_tasks():
                """提交任务的工作函数"""
                for i in range(10):
                    task = task_manager.create_task(
                        task_type=TaskType.INPAINT,
                        image_path=f"/test/concurrent_{i}.jpg",
                        config={"model": "lama", "device": "cuda"}
                    )
                    
                    queue_name = queue_manager.route_task(task)
                    result = queue_manager.send_task(queue_name, task)
                    results.append(result)
            
            # 启动多个线程并发提交任务
            threads = []
            for _ in range(3):
                thread = threading.Thread(target=submit_tasks)
                threads.append(thread)
                thread.start()
            
            # 等待所有线程完成
            for thread in threads:
                thread.join()
            
            # 验证所有任务都成功提交
            assert len(results) == 30
            assert all(results)
            
            # 验证统计信息正确
            stats = queue_manager.get_queue_stats("integration-gpu")
            assert stats['pending_count'] == 30
            assert stats['total_sent'] == 30
    
    def test_error_recovery_workflow(self, queue_manager, task_manager, state_manager):
        """测试错误恢复工作流"""
        # 模拟会失败的 socket
        mock_socket = Mock()
        mock_socket.send_multipart.side_effect = [
            Exception("Network error"),  # 第一次失败
            None  # 第二次成功
        ]
        
        with patch.object(queue_manager.context, 'socket', return_value=mock_socket):
            queue_manager._setup_queues()
            
            # 创建任务
            task = task_manager.create_task(
                task_type=TaskType.INPAINT,
                image_path="/test/error_test.jpg",
                config={"model": "lama", "device": "cuda"}
            )
            
            # 第一次提交应该失败
            queue_name = queue_manager.route_task(task)
            result1 = queue_manager.send_task(queue_name, task)
            assert result1 is False
            
            # 重置 mock 以模拟恢复
            mock_socket.send_multipart.side_effect = None
            
            # 第二次提交应该成功
            result2 = queue_manager.send_task(queue_name, task)
            assert result2 is True


class TestQueueManagerPerformance:
    """队列管理器性能测试"""
    
    @pytest.fixture
    def queue_manager(self):
        """创建队列管理器实例"""
        config = DistributedConfig()
        with patch('lama_cleaner.distributed.queue_manager.get_config', return_value=config):
            manager = QueueManager()
            yield manager
            if hasattr(manager, '_running') and manager._running:
                manager.stop()
    
    @pytest.mark.slow
    def test_high_throughput_task_routing(self, queue_manager):
        """测试高吞吐量任务路由性能"""
        mock_socket = Mock()
        
        with patch.object(queue_manager.context, 'socket', return_value=mock_socket):
            queue_manager._setup_queues()
            
            # 创建大量任务
            tasks = []
            for i in range(1000):
                task = Task(
                    task_type=TaskType.INPAINT,
                    image_path=f"/test/perf_{i}.jpg",
                    config={"model": "lama", "device": "cuda"}
                )
                tasks.append(task)
            
            # 测量路由性能
            start_time = time.time()
            
            for task in tasks:
                queue_name = queue_manager.route_task(task)
                assert queue_name is not None
            
            end_time = time.time()
            routing_time = end_time - start_time
            
            # 路由1000个任务应该在合理时间内完成（小于1秒）
            assert routing_time < 1.0, f"Routing too slow: {routing_time:.2f}s"
            
            # 计算吞吐量
            throughput = len(tasks) / routing_time
            assert throughput > 500, f"Throughput too low: {throughput:.2f} tasks/s"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])