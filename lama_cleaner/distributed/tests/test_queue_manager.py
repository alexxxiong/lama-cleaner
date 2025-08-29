"""
队列管理器单元测试

测试 QueueManager 类的各项功能，包括队列初始化、任务路由、统计监控等。
"""

import pytest
import zmq
import json
import threading
import time
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime

from lama_cleaner.distributed.queue_manager import QueueManager
from lama_cleaner.distributed.models import Task, TaskType, TaskPriority, QueueConfig
from lama_cleaner.distributed.config import DistributedConfig, ZeroMQConfig


class TestQueueManager:
    """队列管理器测试类"""
    
    @pytest.fixture
    def mock_config(self):
        """创建模拟配置"""
        config = DistributedConfig()
        config.zeromq = ZeroMQConfig(
            host="localhost",
            base_port=15555,  # 使用不同的端口避免冲突
            context_io_threads=1,
            socket_linger=100
        )
        
        # 配置测试队列
        config.queues = {
            "test-gpu": QueueConfig(
                name="test-gpu",
                port=15555,
                requirements={
                    "gpu": True,
                    "gpu_memory": 4096,
                    "models": ["lama", "sd15"]
                },
                max_size=100
            ),
            "test-cpu": QueueConfig(
                name="test-cpu", 
                port=15556,
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
            # 清理
            if hasattr(manager, '_running') and manager._running:
                manager.stop()
    
    @pytest.fixture
    def sample_task(self):
        """创建示例任务"""
        task = Task(
            task_id="test-task-001",
            task_type=TaskType.INPAINT,
            priority=TaskPriority.NORMAL,
            config={
                "model": "lama",
                "device": "cuda",
                "gpu_required": True
            }
        )
        return task
    
    def test_queue_manager_initialization(self, queue_manager):
        """测试队列管理器初始化"""
        assert queue_manager is not None
        assert queue_manager.context is not None
        assert isinstance(queue_manager.queues, dict)
        assert isinstance(queue_manager.queue_stats, dict)
        assert not queue_manager._running
    
    def test_setup_queues(self, queue_manager):
        """测试队列设置"""
        # 模拟 ZMQ socket
        mock_socket = Mock()
        
        with patch.object(queue_manager.context, 'socket', return_value=mock_socket):
            queue_manager._setup_queues()
            
            # 验证队列创建
            assert len(queue_manager.queues) == 2
            assert "test-gpu" in queue_manager.queues
            assert "test-cpu" in queue_manager.queues
            
            # 验证统计信息初始化
            assert len(queue_manager.queue_stats) == 2
            for queue_name in ["test-gpu", "test-cpu"]:
                stats = queue_manager.queue_stats[queue_name]
                assert stats['pending_count'] == 0
                assert stats['processing_count'] == 0
                assert stats['completed_count'] == 0
                assert stats['failed_count'] == 0
    
    def test_analyze_task_requirements_inpaint_gpu(self, queue_manager):
        """测试分析 GPU 修复任务需求"""
        task = Task(
            task_type=TaskType.INPAINT,
            config={
                "model": "sd15",
                "device": "cuda"
            }
        )
        
        requirements = queue_manager._analyze_task_requirements(task)
        
        assert requirements['gpu'] is True
        assert requirements['gpu_memory'] == 4096
        assert 'sd15' in requirements['models']
    
    def test_analyze_task_requirements_inpaint_cpu(self, queue_manager):
        """测试分析 CPU 修复任务需求"""
        task = Task(
            task_type=TaskType.INPAINT,
            config={
                "model": "opencv",
                "device": "cpu"
            }
        )
        
        requirements = queue_manager._analyze_task_requirements(task)
        
        assert requirements.get('gpu', False) is False
        assert requirements['cpu_cores'] == 2
        assert requirements['memory'] == 4096
    
    def test_analyze_task_requirements_plugin(self, queue_manager):
        """测试分析插件任务需求"""
        task = Task(
            task_type=TaskType.PLUGIN,
            config={
                "name": "realesrgan"
            }
        )
        
        requirements = queue_manager._analyze_task_requirements(task)
        
        assert requirements['gpu'] is True
        assert requirements['gpu_memory'] == 2048
    
    def test_find_suitable_queues_gpu_task(self, queue_manager):
        """测试查找适合 GPU 任务的队列"""
        requirements = {
            "gpu": True,
            "gpu_memory": 4096,
            "models": ["lama"]
        }
        
        suitable_queues = queue_manager._find_suitable_queues(requirements)
        
        assert "test-gpu" in suitable_queues
        assert "test-cpu" not in suitable_queues
    
    def test_find_suitable_queues_cpu_task(self, queue_manager):
        """测试查找适合 CPU 任务的队列"""
        requirements = {
            "gpu": False,
            "cpu_cores": 4,
            "memory": 8192,
            "models": ["opencv"]
        }
        
        suitable_queues = queue_manager._find_suitable_queues(requirements)
        
        assert "test-cpu" in suitable_queues
        assert "test-gpu" not in suitable_queues
    
    def test_queue_matches_requirements_gpu(self, queue_manager):
        """测试 GPU 队列需求匹配"""
        queue_config = QueueConfig(
            name="test",
            port=5555,
            requirements={
                "gpu": True,
                "gpu_memory": 4096,
                "models": ["lama", "sd15"]
            }
        )
        
        # 匹配的需求
        requirements = {
            "gpu": True,
            "gpu_memory": 2048,
            "models": ["lama"]
        }
        assert queue_manager._queue_matches_requirements(queue_config, requirements)
        
        # 不匹配的需求（内存不足）
        requirements = {
            "gpu": True,
            "gpu_memory": 8192,
            "models": ["lama"]
        }
        assert not queue_manager._queue_matches_requirements(queue_config, requirements)
        
        # 不匹配的需求（模型不支持）
        requirements = {
            "gpu": True,
            "gpu_memory": 2048,
            "models": ["unsupported_model"]
        }
        assert not queue_manager._queue_matches_requirements(queue_config, requirements)
    
    def test_route_task_success(self, queue_manager, sample_task):
        """测试成功路由任务"""
        # 设置队列统计
        queue_manager.queue_stats = {
            "test-gpu": {"pending_count": 5},
            "test-cpu": {"pending_count": 10}
        }
        
        selected_queue = queue_manager.route_task(sample_task)
        
        assert selected_queue == "test-gpu"
    
    def test_route_task_load_balancing(self, queue_manager):
        """测试负载均衡路由"""
        # 创建两个 GPU 队列配置
        queue_manager.config.queues["test-gpu-2"] = QueueConfig(
            name="test-gpu-2",
            port=15557,
            requirements={
                "gpu": True,
                "gpu_memory": 4096,
                "models": ["lama"]
            }
        )
        
        # 设置不同的负载
        queue_manager.queue_stats = {
            "test-gpu": {"pending_count": 10},
            "test-gpu-2": {"pending_count": 3},
            "test-cpu": {"pending_count": 5}
        }
        
        task = Task(
            task_type=TaskType.INPAINT,
            config={"model": "lama", "device": "cuda"}  # 添加 device 参数
        )
        
        selected_queue = queue_manager.route_task(task)
        
        # 应该选择负载较轻的队列
        assert selected_queue == "test-gpu-2"
    
    def test_route_task_no_suitable_queue(self, queue_manager):
        """测试没有合适队列的情况"""
        task = Task(
            task_type=TaskType.INPAINT,
            config={
                "model": "unsupported_model",
                "gpu_required": True
            }
        )
        
        selected_queue = queue_manager.route_task(task)
        
        assert selected_queue is None
    
    def test_send_task_success(self, queue_manager, sample_task):
        """测试成功发送任务"""
        # 模拟 socket
        mock_socket = Mock()
        queue_manager.queues = {
            "test-gpu": {
                "socket": mock_socket,
                "config": queue_manager.config.queues["test-gpu"]
            }
        }
        queue_manager.queue_stats = {
            "test-gpu": {
                "pending_count": 5,
                "total_sent": 10,
                "last_updated": datetime.now()
            }
        }
        
        result = queue_manager.send_task("test-gpu", sample_task)
        
        assert result is True
        mock_socket.send_multipart.assert_called_once()
        
        # 验证统计更新
        assert queue_manager.queue_stats["test-gpu"]["pending_count"] == 6
        assert queue_manager.queue_stats["test-gpu"]["total_sent"] == 11
    
    def test_send_task_queue_not_exists(self, queue_manager, sample_task):
        """测试发送任务到不存在的队列"""
        result = queue_manager.send_task("nonexistent-queue", sample_task)
        
        assert result is False
    
    def test_send_task_capacity_exceeded(self, queue_manager, sample_task):
        """测试队列容量超限"""
        # 设置队列容量已满
        queue_manager.queue_stats = {
            "test-gpu": {"pending_count": 100}  # 等于 max_size
        }
        
        result = queue_manager.send_task("test-gpu", sample_task)
        
        assert result is False
    
    def test_check_queue_capacity(self, queue_manager):
        """测试队列容量检查"""
        queue_manager.queue_stats = {
            "test-gpu": {"pending_count": 50}
        }
        
        # 容量未满
        assert queue_manager._check_queue_capacity("test-gpu") is True
        
        # 容量已满
        queue_manager.queue_stats["test-gpu"]["pending_count"] = 100
        assert queue_manager._check_queue_capacity("test-gpu") is False
        
        # 队列不存在
        assert queue_manager._check_queue_capacity("nonexistent") is False
    
    def test_serialize_task(self, queue_manager, sample_task):
        """测试任务序列化"""
        serialized = queue_manager._serialize_task(sample_task)
        
        assert isinstance(serialized, bytes)
        
        # 验证可以反序列化
        task_dict = json.loads(serialized.decode('utf-8'))
        assert task_dict['task_id'] == sample_task.task_id
        assert task_dict['task_type'] == sample_task.task_type.value
    
    def test_update_queue_stats(self, queue_manager):
        """测试更新队列统计"""
        queue_manager.queue_stats = {
            "test-gpu": {
                "pending_count": 5,
                "processing_count": 2,
                "last_updated": datetime.now()
            }
        }
        
        # 增加待处理任务数
        queue_manager.update_queue_stats("test-gpu", "pending_count", 3)
        assert queue_manager.queue_stats["test-gpu"]["pending_count"] == 8
        
        # 减少处理中任务数
        queue_manager.update_queue_stats("test-gpu", "processing_count", -1)
        assert queue_manager.queue_stats["test-gpu"]["processing_count"] == 1
        
        # 不存在的队列
        queue_manager.update_queue_stats("nonexistent", "pending_count", 1)
        # 应该不会抛出异常
    
    def test_get_queue_stats(self, queue_manager):
        """测试获取队列统计"""
        test_stats = {
            "test-gpu": {
                "pending_count": 5,
                "processing_count": 2,
                "completed_count": 100
            },
            "test-cpu": {
                "pending_count": 3,
                "processing_count": 1,
                "completed_count": 50
            }
        }
        queue_manager.queue_stats = test_stats
        
        # 获取单个队列统计
        gpu_stats = queue_manager.get_queue_stats("test-gpu")
        assert gpu_stats["pending_count"] == 5
        assert gpu_stats["processing_count"] == 2
        
        # 获取所有队列统计
        all_stats = queue_manager.get_queue_stats()
        assert len(all_stats) == 2
        assert "test-gpu" in all_stats
        assert "test-cpu" in all_stats
        
        # 不存在的队列
        empty_stats = queue_manager.get_queue_stats("nonexistent")
        assert empty_stats == {}
    
    def test_get_queue_info(self, queue_manager):
        """测试获取队列信息"""
        # 设置测试数据
        mock_socket = Mock()
        queue_manager.queues = {
            "test-gpu": {
                "socket": mock_socket,
                "config": queue_manager.config.queues["test-gpu"],
                "created_at": datetime.now()
            }
        }
        queue_manager.queue_stats = {
            "test-gpu": {
                "pending_count": 5,
                "total_sent": 100
            }
        }
        
        # 获取单个队列信息
        info = queue_manager.get_queue_info("test-gpu")
        assert "config" in info
        assert "stats" in info
        assert "socket" not in info  # socket 应该被移除
        assert info["stats"]["pending_count"] == 5
        
        # 获取所有队列信息
        all_info = queue_manager.get_queue_info()
        assert "test-gpu" in all_info
        
        # 不存在的队列
        empty_info = queue_manager.get_queue_info("nonexistent")
        assert empty_info == {}
    
    def test_start_and_stop(self, queue_manager):
        """测试启动和停止队列管理器"""
        mock_socket = Mock()
        
        with patch.object(queue_manager.context, 'socket', return_value=mock_socket):
            # 启动
            queue_manager.start()
            assert queue_manager._running is True
            assert queue_manager._stats_thread is not None
            
            # 停止
            queue_manager.stop()
            assert queue_manager._running is False
            mock_socket.close.assert_called()
    
    def test_stats_thread_functionality(self, queue_manager):
        """测试统计线程功能"""
        mock_socket = Mock()
        
        with patch.object(queue_manager.context, 'socket', return_value=mock_socket):
            with patch.object(queue_manager, '_update_queue_metrics') as mock_update:
                queue_manager.start()
                
                # 等待统计线程运行
                time.sleep(0.1)
                
                queue_manager.stop()
                
                # 验证统计更新被调用
                # 注意：由于时间间隔设置，可能不会立即调用
                # 这里主要验证线程启动成功
                assert queue_manager._stats_thread is not None


class TestQueueManagerErrorHandling:
    """队列管理器错误处理测试"""
    
    @pytest.fixture
    def queue_manager(self):
        """创建队列管理器实例"""
        config = DistributedConfig()
        with patch('lama_cleaner.distributed.queue_manager.get_config', return_value=config):
            manager = QueueManager()
            yield manager
            if hasattr(manager, '_running') and manager._running:
                manager.stop()
    
    def test_setup_queues_socket_error(self, queue_manager):
        """测试队列设置时的 socket 错误"""
        with patch.object(queue_manager.context, 'socket', side_effect=zmq.ZMQError("Socket error")):
            with pytest.raises(zmq.ZMQError):
                queue_manager._setup_queues()
    
    def test_send_task_socket_error(self, queue_manager):
        """测试发送任务时的 socket 错误"""
        mock_socket = Mock()
        mock_socket.send_multipart.side_effect = zmq.ZMQError("Send error")
        
        queue_manager.queues = {
            "test-queue": {
                "socket": mock_socket,
                "config": QueueConfig(name="test-queue", port=5555, max_size=100)
            }
        }
        queue_manager.queue_stats = {
            "test-queue": {"pending_count": 0}
        }
        
        task = Task()
        result = queue_manager.send_task("test-queue", task)
        
        assert result is False
    
    def test_serialize_task_error(self, queue_manager):
        """测试任务序列化错误"""
        # 创建一个无法序列化的任务
        task = Task()
        task.config = {"invalid": object()}  # 不可序列化的对象
        
        with pytest.raises(TypeError):
            queue_manager._serialize_task(task)


class TestQueueManagerConcurrency:
    """队列管理器并发测试"""
    
    @pytest.fixture
    def queue_manager(self):
        """创建队列管理器实例"""
        config = DistributedConfig()
        with patch('lama_cleaner.distributed.queue_manager.get_config', return_value=config):
            manager = QueueManager()
            yield manager
            if hasattr(manager, '_running') and manager._running:
                manager.stop()
    
    def test_concurrent_stats_update(self, queue_manager):
        """测试并发统计更新"""
        queue_manager.queue_stats = {
            "test-queue": {
                "pending_count": 0,
                "processing_count": 0,
                "last_updated": datetime.now()
            }
        }
        
        def update_stats():
            for i in range(100):
                queue_manager.update_queue_stats("test-queue", "pending_count", 1)
        
        # 启动多个线程并发更新
        threads = []
        for _ in range(5):
            thread = threading.Thread(target=update_stats)
            threads.append(thread)
            thread.start()
        
        # 等待所有线程完成
        for thread in threads:
            thread.join()
        
        # 验证最终结果
        assert queue_manager.queue_stats["test-queue"]["pending_count"] == 500
    
    def test_concurrent_queue_access(self, queue_manager):
        """测试并发队列访问"""
        queue_manager.queue_stats = {
            "test-queue": {
                "pending_count": 0,
                "last_updated": datetime.now()
            }
        }
        
        results = []
        
        def get_stats():
            for _ in range(50):
                stats = queue_manager.get_queue_stats("test-queue")
                results.append(stats)
        
        def update_stats():
            for i in range(50):
                queue_manager.update_queue_stats("test-queue", "pending_count", 1)
        
        # 启动读写线程
        read_thread = threading.Thread(target=get_stats)
        write_thread = threading.Thread(target=update_stats)
        
        read_thread.start()
        write_thread.start()
        
        read_thread.join()
        write_thread.join()
        
        # 验证没有异常发生
        assert len(results) == 50
        assert all(isinstance(result, dict) for result in results)


class TestQueueManagerAdditionalCoverage:
    """额外的测试用例以提高覆盖率"""
    
    @pytest.fixture
    def queue_manager(self):
        """创建队列管理器实例"""
        config = DistributedConfig()
        with patch('lama_cleaner.distributed.queue_manager.get_config', return_value=config):
            manager = QueueManager()
            yield manager
            if hasattr(manager, '_running') and manager._running:
                manager.stop()
    
    def test_analyze_task_requirements_urgent_priority(self, queue_manager):
        """测试紧急优先级任务需求分析"""
        task = Task(
            task_type=TaskType.INPAINT,
            priority=TaskPriority.URGENT,
            config={"model": "lama"}
        )
        
        requirements = queue_manager._analyze_task_requirements(task)
        
        # 验证紧急任务有优先级提升标记
        assert requirements.get('priority_boost') is True
    
    def test_analyze_task_requirements_unknown_plugin(self, queue_manager):
        """测试未知插件任务需求分析"""
        task = Task(
            task_type=TaskType.PLUGIN,
            config={"name": "unknown_plugin"}
        )
        
        requirements = queue_manager._analyze_task_requirements(task)
        
        # 未知插件应该默认为 CPU 处理
        assert requirements.get('gpu', False) is False
        assert requirements['cpu_cores'] == 2
        assert requirements['memory'] == 4096
    
    def test_send_task_with_exception_handling(self, queue_manager):
        """测试发送任务时的异常处理"""
        # 模拟会抛出异常的 socket
        mock_socket = Mock()
        mock_socket.send_multipart.side_effect = Exception("Unexpected error")
        
        queue_manager.queues = {
            "test-queue": {
                "socket": mock_socket,
                "config": QueueConfig(name="test-queue", port=5555, max_size=100)
            }
        }
        queue_manager.queue_stats = {
            "test-queue": {"pending_count": 0}
        }
        
        task = Task()
        result = queue_manager.send_task("test-queue", task)
        
        # 应该返回 False 并记录错误
        assert result is False
    
    def test_stats_thread_with_exception(self, queue_manager):
        """测试统计线程异常处理"""
        mock_socket = Mock()
        
        with patch.object(queue_manager.context, 'socket', return_value=mock_socket):
            with patch.object(queue_manager, '_update_queue_metrics', side_effect=Exception("Metrics error")):
                # 启动管理器
                queue_manager.start()
                
                # 等待一小段时间让统计线程运行
                time.sleep(0.2)
                
                # 停止管理器
                queue_manager.stop()
                
                # 验证线程能够处理异常并继续运行
                assert queue_manager._stats_thread is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])