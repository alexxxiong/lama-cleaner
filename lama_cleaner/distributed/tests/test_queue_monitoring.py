"""
队列监控和统计测试

测试队列状态监控、性能指标收集和统计信息持久化功能。
"""

import pytest
import time
import threading
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timedelta

from lama_cleaner.distributed.queue_manager import QueueManager
from lama_cleaner.distributed.models import Task, TaskType, TaskPriority, QueueConfig
from lama_cleaner.distributed.config import DistributedConfig, ZeroMQConfig, MonitoringConfig


class TestQueueStatistics:
    """队列统计测试"""
    
    @pytest.fixture
    def queue_manager(self):
        """创建队列管理器实例"""
        config = DistributedConfig()
        config.monitoring = MonitoringConfig(
            enabled=True,
            metrics_interval=1  # 1秒间隔用于测试
        )
        
        with patch('lama_cleaner.distributed.queue_manager.get_config', return_value=config):
            manager = QueueManager()
            yield manager
            if hasattr(manager, '_running') and manager._running:
                manager.stop()
    
    def test_initial_queue_stats(self, queue_manager):
        """测试初始队列统计"""
        # 模拟队列设置
        mock_socket = Mock()
        with patch.object(queue_manager.context, 'socket', return_value=mock_socket):
            queue_manager._setup_queues()
            
            # 验证初始统计
            for queue_name in queue_manager.config.queues.keys():
                stats = queue_manager.get_queue_stats(queue_name)
                assert stats['pending_count'] == 0
                assert stats['processing_count'] == 0
                assert stats['completed_count'] == 0
                assert stats['failed_count'] == 0
                assert stats['total_sent'] == 0
                assert 'last_updated' in stats
    
    def test_update_queue_stats_increment(self, queue_manager):
        """测试队列统计增量更新"""
        # 初始化统计
        queue_manager.queue_stats = {
            "test-queue": {
                "pending_count": 5,
                "processing_count": 2,
                "completed_count": 10,
                "failed_count": 1,
                "last_updated": datetime.now()
            }
        }
        
        # 测试增量更新
        queue_manager.update_queue_stats("test-queue", "pending_count", 3)
        assert queue_manager.queue_stats["test-queue"]["pending_count"] == 8
        
        queue_manager.update_queue_stats("test-queue", "processing_count", 1)
        assert queue_manager.queue_stats["test-queue"]["processing_count"] == 3
        
        queue_manager.update_queue_stats("test-queue", "completed_count", 5)
        assert queue_manager.queue_stats["test-queue"]["completed_count"] == 15
        
        queue_manager.update_queue_stats("test-queue", "failed_count", 2)
        assert queue_manager.queue_stats["test-queue"]["failed_count"] == 3
    
    def test_update_queue_stats_decrement(self, queue_manager):
        """测试队列统计减量更新"""
        # 初始化统计
        queue_manager.queue_stats = {
            "test-queue": {
                "pending_count": 10,
                "processing_count": 5,
                "last_updated": datetime.now()
            }
        }
        
        # 测试减量更新
        queue_manager.update_queue_stats("test-queue", "pending_count", -3)
        assert queue_manager.queue_stats["test-queue"]["pending_count"] == 7
        
        queue_manager.update_queue_stats("test-queue", "processing_count", -2)
        assert queue_manager.queue_stats["test-queue"]["processing_count"] == 3
    
    def test_update_queue_stats_timestamp(self, queue_manager):
        """测试队列统计时间戳更新"""
        # 初始化统计
        old_time = datetime.now() - timedelta(minutes=5)
        queue_manager.queue_stats = {
            "test-queue": {
                "pending_count": 5,
                "last_updated": old_time
            }
        }
        
        # 更新统计
        queue_manager.update_queue_stats("test-queue", "pending_count", 1)
        
        # 验证时间戳更新
        new_time = queue_manager.queue_stats["test-queue"]["last_updated"]
        assert new_time > old_time
        assert (datetime.now() - new_time).total_seconds() < 1
    
    def test_update_nonexistent_queue_stats(self, queue_manager):
        """测试更新不存在队列的统计"""
        # 应该不会抛出异常
        queue_manager.update_queue_stats("nonexistent-queue", "pending_count", 1)
        
        # 验证不存在的队列没有被创建
        assert "nonexistent-queue" not in queue_manager.queue_stats
    
    def test_get_single_queue_stats(self, queue_manager):
        """测试获取单个队列统计"""
        test_stats = {
            "pending_count": 5,
            "processing_count": 2,
            "completed_count": 100,
            "failed_count": 3,
            "total_sent": 110,
            "last_updated": datetime.now()
        }
        
        queue_manager.queue_stats = {"test-queue": test_stats}
        
        # 获取统计
        stats = queue_manager.get_queue_stats("test-queue")
        
        # 验证返回的是副本
        assert stats == test_stats
        assert stats is not test_stats  # 不是同一个对象
        
        # 修改返回的统计不应该影响原始数据
        stats["pending_count"] = 999
        assert queue_manager.queue_stats["test-queue"]["pending_count"] == 5
    
    def test_get_all_queue_stats(self, queue_manager):
        """测试获取所有队列统计"""
        test_stats = {
            "queue-1": {
                "pending_count": 5,
                "processing_count": 2,
                "last_updated": datetime.now()
            },
            "queue-2": {
                "pending_count": 3,
                "processing_count": 1,
                "last_updated": datetime.now()
            }
        }
        
        queue_manager.queue_stats = test_stats
        
        # 获取所有统计
        all_stats = queue_manager.get_queue_stats()
        
        # 验证返回的是副本
        assert len(all_stats) == 2
        assert "queue-1" in all_stats
        assert "queue-2" in all_stats
        assert all_stats["queue-1"]["pending_count"] == 5
        assert all_stats["queue-2"]["pending_count"] == 3
        
        # 修改返回的统计不应该影响原始数据
        all_stats["queue-1"]["pending_count"] = 999
        assert queue_manager.queue_stats["queue-1"]["pending_count"] == 5
    
    def test_get_nonexistent_queue_stats(self, queue_manager):
        """测试获取不存在队列的统计"""
        stats = queue_manager.get_queue_stats("nonexistent-queue")
        assert stats == {}


class TestQueueMonitoring:
    """队列监控测试"""
    
    @pytest.fixture
    def queue_manager(self):
        """创建队列管理器实例"""
        config = DistributedConfig()
        config.monitoring = MonitoringConfig(
            enabled=True,
            metrics_interval=0.1  # 100ms间隔用于测试
        )
        
        with patch('lama_cleaner.distributed.queue_manager.get_config', return_value=config):
            manager = QueueManager()
            yield manager
            if hasattr(manager, '_running') and manager._running:
                manager.stop()
    
    def test_stats_thread_start_stop(self, queue_manager):
        """测试统计线程启动和停止"""
        mock_socket = Mock()
        
        with patch.object(queue_manager.context, 'socket', return_value=mock_socket):
            # 启动队列管理器
            queue_manager.start()
            
            # 验证统计线程启动
            assert queue_manager._running is True
            assert queue_manager._stats_thread is not None
            assert queue_manager._stats_thread.is_alive()
            
            # 停止队列管理器
            queue_manager.stop()
            
            # 验证统计线程停止
            assert queue_manager._running is False
            # 等待线程结束
            time.sleep(0.2)
            assert not queue_manager._stats_thread.is_alive()
    
    def test_stats_thread_update_metrics(self, queue_manager):
        """测试统计线程更新指标"""
        mock_socket = Mock()
        
        with patch.object(queue_manager.context, 'socket', return_value=mock_socket):
            with patch.object(queue_manager, '_update_queue_metrics') as mock_update:
                # 启动队列管理器
                queue_manager.start()
                
                # 等待统计线程运行几次
                time.sleep(0.3)
                
                # 停止队列管理器
                queue_manager.stop()
                
                # 验证指标更新被调用
                assert mock_update.call_count >= 2
    
    def test_stats_thread_error_handling(self, queue_manager):
        """测试统计线程错误处理"""
        mock_socket = Mock()
        
        with patch.object(queue_manager.context, 'socket', return_value=mock_socket):
            with patch.object(queue_manager, '_update_queue_metrics', side_effect=Exception("Test error")):
                # 启动队列管理器
                queue_manager.start()
                
                # 等待一段时间，确保线程处理了异常
                time.sleep(0.3)
                
                # 验证线程仍在运行（没有因为异常而崩溃）
                assert queue_manager._running is True
                assert queue_manager._stats_thread.is_alive()
                
                # 停止队列管理器
                queue_manager.stop()
    
    def test_queue_info_includes_stats(self, queue_manager):
        """测试队列信息包含统计数据"""
        # 设置测试数据
        mock_socket = Mock()
        test_config = QueueConfig(name="test-queue", port=5555)
        
        queue_manager.queues = {
            "test-queue": {
                "socket": mock_socket,
                "config": test_config,
                "created_at": datetime.now()
            }
        }
        
        queue_manager.queue_stats = {
            "test-queue": {
                "pending_count": 5,
                "processing_count": 2,
                "completed_count": 100,
                "total_sent": 107
            }
        }
        
        # 获取队列信息
        info = queue_manager.get_queue_info("test-queue")
        
        # 验证包含统计信息
        assert "stats" in info
        assert info["stats"]["pending_count"] == 5
        assert info["stats"]["processing_count"] == 2
        assert info["stats"]["completed_count"] == 100
        assert info["stats"]["total_sent"] == 107
        
        # 验证不包含 socket 对象
        assert "socket" not in info
    
    def test_queue_capacity_monitoring(self, queue_manager):
        """测试队列容量监控"""
        # 设置队列配置
        queue_manager.config.queues = {
            "test-queue": QueueConfig(
                name="test-queue",
                port=5555,
                max_size=10
            )
        }
        
        # 测试容量检查
        queue_manager.queue_stats = {"test-queue": {"pending_count": 5}}
        assert queue_manager._check_queue_capacity("test-queue") is True
        
        queue_manager.queue_stats = {"test-queue": {"pending_count": 10}}
        assert queue_manager._check_queue_capacity("test-queue") is False
        
        queue_manager.queue_stats = {"test-queue": {"pending_count": 15}}
        assert queue_manager._check_queue_capacity("test-queue") is False


class TestQueueMetrics:
    """队列指标测试"""
    
    @pytest.fixture
    def queue_manager(self):
        """创建队列管理器实例"""
        config = DistributedConfig()
        with patch('lama_cleaner.distributed.queue_manager.get_config', return_value=config):
            return QueueManager()
    
    def test_task_send_updates_metrics(self, queue_manager):
        """测试发送任务更新指标"""
        # 设置测试队列
        mock_socket = Mock()
        queue_manager.queues = {
            "test-queue": {
                "socket": mock_socket,
                "config": QueueConfig(name="test-queue", port=5555, max_size=100)
            }
        }
        
        # 初始化统计
        queue_manager.queue_stats = {
            "test-queue": {
                "pending_count": 5,
                "total_sent": 10,
                "last_updated": datetime.now()
            }
        }
        
        # 设置队列配置到 config 中
        queue_manager.config.queues = {
            "test-queue": QueueConfig(name="test-queue", port=5555, max_size=100)
        }
        
        # 创建测试任务
        task = Task(
            task_id="test-task",
            task_type=TaskType.INPAINT,
            config={"model": "lama"}
        )
        
        # 发送任务
        result = queue_manager.send_task("test-queue", task)
        
        # 验证结果和指标更新
        assert result is True
        assert queue_manager.queue_stats["test-queue"]["pending_count"] == 6
        assert queue_manager.queue_stats["test-queue"]["total_sent"] == 11
        
        # 验证时间戳更新
        assert (datetime.now() - queue_manager.queue_stats["test-queue"]["last_updated"]).total_seconds() < 1
    
    def test_concurrent_metrics_update(self, queue_manager):
        """测试并发指标更新"""
        # 初始化统计
        queue_manager.queue_stats = {
            "test-queue": {
                "pending_count": 0,
                "processing_count": 0,
                "completed_count": 0,
                "last_updated": datetime.now()
            }
        }
        
        def update_pending():
            for _ in range(50):
                queue_manager.update_queue_stats("test-queue", "pending_count", 1)
        
        def update_processing():
            for _ in range(30):
                queue_manager.update_queue_stats("test-queue", "processing_count", 1)
        
        def update_completed():
            for _ in range(20):
                queue_manager.update_queue_stats("test-queue", "completed_count", 1)
        
        # 启动并发更新
        threads = [
            threading.Thread(target=update_pending),
            threading.Thread(target=update_processing),
            threading.Thread(target=update_completed)
        ]
        
        for thread in threads:
            thread.start()
        
        for thread in threads:
            thread.join()
        
        # 验证最终结果
        stats = queue_manager.get_queue_stats("test-queue")
        assert stats["pending_count"] == 50
        assert stats["processing_count"] == 30
        assert stats["completed_count"] == 20
    
    def test_metrics_calculation(self, queue_manager):
        """测试指标计算"""
        # 设置测试数据
        queue_manager.queue_stats = {
            "queue-1": {
                "pending_count": 10,
                "processing_count": 5,
                "completed_count": 100,
                "failed_count": 3,
                "total_sent": 118
            },
            "queue-2": {
                "pending_count": 3,
                "processing_count": 2,
                "completed_count": 50,
                "failed_count": 1,
                "total_sent": 56
            }
        }
        
        # 计算总体指标
        all_stats = queue_manager.get_queue_stats()
        
        total_pending = sum(stats["pending_count"] for stats in all_stats.values())
        total_processing = sum(stats["processing_count"] for stats in all_stats.values())
        total_completed = sum(stats["completed_count"] for stats in all_stats.values())
        total_failed = sum(stats["failed_count"] for stats in all_stats.values())
        total_sent = sum(stats["total_sent"] for stats in all_stats.values())
        
        assert total_pending == 13
        assert total_processing == 7
        assert total_completed == 150
        assert total_failed == 4
        assert total_sent == 174
        
        # 计算成功率
        total_processed = total_completed + total_failed
        success_rate = total_completed / total_processed if total_processed > 0 else 0
        assert abs(success_rate - 0.974) < 0.001  # 150/154 ≈ 0.974


class TestQueueStatsPersistence:
    """队列统计持久化测试"""
    
    @pytest.fixture
    def queue_manager(self):
        """创建队列管理器实例"""
        config = DistributedConfig()
        with patch('lama_cleaner.distributed.queue_manager.get_config', return_value=config):
            return QueueManager()
    
    def test_stats_data_structure(self, queue_manager):
        """测试统计数据结构"""
        # 设置测试统计
        test_time = datetime.now()
        queue_manager.queue_stats = {
            "test-queue": {
                "pending_count": 5,
                "processing_count": 2,
                "completed_count": 100,
                "failed_count": 3,
                "total_sent": 110,
                "last_updated": test_time
            }
        }
        
        # 获取统计数据
        stats = queue_manager.get_queue_stats("test-queue")
        
        # 验证数据结构
        required_fields = [
            "pending_count", "processing_count", "completed_count",
            "failed_count", "total_sent", "last_updated"
        ]
        
        for field in required_fields:
            assert field in stats, f"Missing required field: {field}"
        
        # 验证数据类型
        assert isinstance(stats["pending_count"], int)
        assert isinstance(stats["processing_count"], int)
        assert isinstance(stats["completed_count"], int)
        assert isinstance(stats["failed_count"], int)
        assert isinstance(stats["total_sent"], int)
        assert isinstance(stats["last_updated"], datetime)
    
    def test_stats_serialization_compatibility(self, queue_manager):
        """测试统计数据序列化兼容性"""
        import json
        
        # 设置测试统计
        test_time = datetime.now()
        queue_manager.queue_stats = {
            "test-queue": {
                "pending_count": 5,
                "processing_count": 2,
                "completed_count": 100,
                "failed_count": 3,
                "total_sent": 110,
                "last_updated": test_time
            }
        }
        
        # 获取统计数据
        stats = queue_manager.get_queue_stats("test-queue")
        
        # 准备序列化数据（转换 datetime）
        serializable_stats = stats.copy()
        serializable_stats["last_updated"] = stats["last_updated"].isoformat()
        
        # 测试 JSON 序列化
        json_str = json.dumps(serializable_stats)
        assert json_str is not None
        
        # 测试反序列化
        deserialized = json.loads(json_str)
        assert deserialized["pending_count"] == 5
        assert deserialized["processing_count"] == 2
        assert deserialized["completed_count"] == 100
        assert deserialized["failed_count"] == 3
        assert deserialized["total_sent"] == 110
        
        # 验证时间戳可以恢复
        restored_time = datetime.fromisoformat(deserialized["last_updated"])
        assert abs((restored_time - test_time).total_seconds()) < 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])