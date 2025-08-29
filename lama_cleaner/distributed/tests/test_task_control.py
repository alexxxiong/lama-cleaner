"""
任务控制测试

测试任务取消、重试机制、超时检测等功能。
"""

import unittest
import tempfile
import os
import time
import threading
from unittest.mock import Mock, patch
from datetime import datetime, timedelta

from ..models import Task, TaskStatus, TaskType, TaskPriority
from ..task_control import (
    RetryStrategy, RetryConfig, TaskCancellationReason,
    TaskTimeoutManager, TaskCancellationManager, TaskRetryManager, TaskControlManager
)
from ..task_manager import TaskManager
from ..config import DistributedConfig


class TestRetryConfig(unittest.TestCase):
    """重试配置测试"""
    
    def test_immediate_strategy(self):
        """测试立即重试策略"""
        config = RetryConfig(strategy=RetryStrategy.IMMEDIATE)
        
        self.assertEqual(config.calculate_delay(0), 0.0)
        self.assertEqual(config.calculate_delay(1), 0.0)
        self.assertEqual(config.calculate_delay(5), 0.0)
    
    def test_linear_strategy(self):
        """测试线性退避策略"""
        config = RetryConfig(
            strategy=RetryStrategy.LINEAR,
            base_delay=2.0,
            jitter=False
        )
        
        self.assertEqual(config.calculate_delay(0), 0.0)
        self.assertEqual(config.calculate_delay(1), 2.0)
        self.assertEqual(config.calculate_delay(2), 4.0)
        self.assertEqual(config.calculate_delay(3), 6.0)
    
    def test_exponential_strategy(self):
        """测试指数退避策略"""
        config = RetryConfig(
            strategy=RetryStrategy.EXPONENTIAL,
            base_delay=1.0,
            backoff_multiplier=2.0,
            jitter=False
        )
        
        self.assertEqual(config.calculate_delay(0), 1.0)
        self.assertEqual(config.calculate_delay(1), 2.0)
        self.assertEqual(config.calculate_delay(2), 4.0)
        self.assertEqual(config.calculate_delay(3), 8.0)
    
    def test_fixed_delay_strategy(self):
        """测试固定延迟策略"""
        config = RetryConfig(
            strategy=RetryStrategy.FIXED_DELAY,
            base_delay=5.0,
            jitter=False
        )
        
        self.assertEqual(config.calculate_delay(0), 5.0)
        self.assertEqual(config.calculate_delay(1), 5.0)
        self.assertEqual(config.calculate_delay(10), 5.0)
    
    def test_max_delay_limit(self):
        """测试最大延迟限制"""
        config = RetryConfig(
            strategy=RetryStrategy.EXPONENTIAL,
            base_delay=10.0,
            max_delay=30.0,
            backoff_multiplier=3.0,
            jitter=False
        )
        
        self.assertEqual(config.calculate_delay(0), 10.0)
        self.assertEqual(config.calculate_delay(1), 30.0)  # 30 而不是 30
        self.assertEqual(config.calculate_delay(2), 30.0)  # 限制在 30
    
    def test_jitter(self):
        """测试抖动"""
        config = RetryConfig(
            strategy=RetryStrategy.FIXED_DELAY,
            base_delay=10.0,
            jitter=True
        )
        
        # 多次计算，应该有不同的结果（由于抖动）
        delays = [config.calculate_delay(1) for _ in range(10)]
        
        # 所有延迟都应该在合理范围内
        for delay in delays:
            self.assertGreaterEqual(delay, 9.0)  # 10 - 10% = 9
            self.assertLessEqual(delay, 11.0)    # 10 + 10% = 11
        
        # 应该有一些变化（不是所有值都相同）
        self.assertGreater(len(set(delays)), 1)


class TestTaskTimeoutManager(unittest.TestCase):
    """任务超时管理器测试"""
    
    def setUp(self):
        """设置测试环境"""
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, f"test_{id(self)}.db")
        
        # 创建测试配置
        config = DistributedConfig()
        config.database.sqlite_path = self.db_path
        config.default_task_timeout = 5  # 5秒超时，便于测试
        
        # 模拟配置
        self.config_patcher = patch('lama_cleaner.distributed.config.get_config')
        self.mock_get_config = self.config_patcher.start()
        self.mock_get_config.return_value = config
        
        # 重置存储管理器
        import lama_cleaner.distributed.storage as storage_module
        storage_module.storage_manager._storage = None
        
        self.task_manager = TaskManager()
        self.timeout_manager = TaskTimeoutManager(self.task_manager)
    
    def tearDown(self):
        """清理测试环境"""
        self.timeout_manager.stop()
        self.config_patcher.stop()
        
        # 重置存储管理器
        import lama_cleaner.distributed.storage as storage_module
        storage_module.storage_manager._storage = None
        
        if os.path.exists(self.db_path):
            os.remove(self.db_path)
        if os.path.exists(self.temp_dir):
            os.rmdir(self.temp_dir)
    
    def test_set_and_remove_timeout(self):
        """测试设置和移除超时"""
        task_id = "test_task"
        
        # 设置超时
        self.timeout_manager.set_task_timeout(task_id, 10)
        self.assertIn(task_id, self.timeout_manager.task_timeouts)
        
        # 移除超时
        self.timeout_manager.remove_task_timeout(task_id)
        self.assertNotIn(task_id, self.timeout_manager.task_timeouts)
    
    def test_timeout_detection(self):
        """测试超时检测"""
        # 创建任务
        task = self.task_manager.create_task(
            task_type=TaskType.INPAINT,
            image_path="/test/image.jpg",
            config={"model": "lama"}
        )
        
        # 设置很短的超时
        self.timeout_manager.set_task_timeout(task.task_id, 0.1)
        
        # 启动超时管理器
        self.timeout_manager.start()
        
        # 等待超时
        time.sleep(0.2)
        
        # 手动触发超时检查
        self.timeout_manager._check_timeouts()
        
        # 验证任务被标记为失败
        updated_task = self.task_manager.get_task(task.task_id)
        self.assertEqual(updated_task.status, TaskStatus.FAILED)
        self.assertIn("超时", updated_task.error_message)


class TestTaskCancellationManager(unittest.TestCase):
    """任务取消管理器测试"""
    
    def setUp(self):
        """设置测试环境"""
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, f"test_{id(self)}.db")
        
        # 创建测试配置
        config = DistributedConfig()
        config.database.sqlite_path = self.db_path
        
        # 模拟配置
        self.config_patcher = patch('lama_cleaner.distributed.config.get_config')
        self.mock_get_config = self.config_patcher.start()
        self.mock_get_config.return_value = config
        
        # 重置存储管理器
        import lama_cleaner.distributed.storage as storage_module
        storage_module.storage_manager._storage = None
        
        self.task_manager = TaskManager()
        self.queue_manager = Mock()
        self.node_manager = Mock()
        
        self.cancellation_manager = TaskCancellationManager(
            self.task_manager, self.queue_manager, self.node_manager
        )
    
    def tearDown(self):
        """清理测试环境"""
        self.config_patcher.stop()
        
        # 重置存储管理器
        import lama_cleaner.distributed.storage as storage_module
        storage_module.storage_manager._storage = None
        
        if os.path.exists(self.db_path):
            os.remove(self.db_path)
        if os.path.exists(self.temp_dir):
            os.rmdir(self.temp_dir)
    
    def test_cancel_pending_task(self):
        """测试取消待处理任务"""
        # 创建待处理任务
        task = self.task_manager.create_task(
            task_type=TaskType.INPAINT,
            image_path="/test/image.jpg",
            config={"model": "lama"}
        )
        
        # 取消任务
        success = self.cancellation_manager.cancel_task(task.task_id)
        self.assertTrue(success)
        
        # 验证任务状态
        updated_task = self.task_manager.get_task(task.task_id)
        self.assertEqual(updated_task.status, TaskStatus.CANCELLED)
        self.assertIn("已取消", updated_task.error_message)
    
    def test_cancel_queued_task(self):
        """测试取消队列中的任务"""
        # 创建任务并分配到队列
        task = self.task_manager.create_task(
            task_type=TaskType.INPAINT,
            image_path="/test/image.jpg",
            config={"model": "lama"}
        )
        
        # 模拟任务在队列中
        self.task_manager.assign_task_to_node(task.task_id, "node123", "gpu-high")
        
        # 取消任务
        success = self.cancellation_manager.cancel_task(task.task_id)
        self.assertTrue(success)
        
        # 验证队列管理器被调用
        self.queue_manager.remove_task_from_queue.assert_called_once_with("gpu-high", task.task_id)
        
        # 验证任务状态
        updated_task = self.task_manager.get_task(task.task_id)
        self.assertEqual(updated_task.status, TaskStatus.CANCELLED)
    
    def test_cancel_processing_task(self):
        """测试取消处理中的任务"""
        # 创建任务并开始处理
        task = self.task_manager.create_task(
            task_type=TaskType.INPAINT,
            image_path="/test/image.jpg",
            config={"model": "lama"}
        )
        
        self.task_manager.assign_task_to_node(task.task_id, "node123", "gpu-high")
        self.task_manager.mark_task_processing(task.task_id, "node123")
        
        # 取消任务
        success = self.cancellation_manager.cancel_task(task.task_id)
        self.assertTrue(success)
        
        # 验证节点管理器被调用
        self.node_manager.send_cancel_command.assert_called_once_with("node123", task.task_id)
        
        # 验证任务状态
        updated_task = self.task_manager.get_task(task.task_id)
        self.assertEqual(updated_task.status, TaskStatus.CANCELLED)
    
    def test_cancel_completed_task(self):
        """测试取消已完成任务（应该失败）"""
        # 创建并完成任务
        task = self.task_manager.create_task(
            task_type=TaskType.INPAINT,
            image_path="/test/image.jpg",
            config={"model": "lama"}
        )
        
        self.task_manager.complete_task(task.task_id, "/result.jpg", 10.0)
        
        # 尝试取消任务
        success = self.cancellation_manager.cancel_task(task.task_id)
        self.assertFalse(success)
        
        # 验证任务状态未改变
        updated_task = self.task_manager.get_task(task.task_id)
        self.assertEqual(updated_task.status, TaskStatus.COMPLETED)
    
    def test_cancel_user_tasks(self):
        """测试取消用户任务"""
        user_id = f"user_{id(self)}"  # 使用唯一的用户ID
        
        # 创建多个用户任务
        tasks = []
        for i in range(3):
            task = self.task_manager.create_task(
                task_type=TaskType.INPAINT,
                image_path=f"/test/image{i}.jpg",
                config={"model": "lama"},
                user_id=user_id
            )
            tasks.append(task)
        
        # 完成一个任务（不应该被取消）
        self.task_manager.complete_task(tasks[0].task_id, "/result.jpg", 10.0)
        
        # 取消用户任务
        cancelled_count = self.cancellation_manager.cancel_user_tasks(user_id)
        self.assertEqual(cancelled_count, 2)  # 只有2个任务被取消
        
        # 验证任务状态
        self.assertEqual(self.task_manager.get_task(tasks[0].task_id).status, TaskStatus.COMPLETED)
        self.assertEqual(self.task_manager.get_task(tasks[1].task_id).status, TaskStatus.CANCELLED)
        self.assertEqual(self.task_manager.get_task(tasks[2].task_id).status, TaskStatus.CANCELLED)
    
    def test_cancellation_callback(self):
        """测试取消回调"""
        callback_called = []
        
        def test_callback(task_id, reason):
            callback_called.append((task_id, reason))
        
        self.cancellation_manager.add_cancellation_callback(test_callback)
        
        # 创建并取消任务
        task = self.task_manager.create_task(
            task_type=TaskType.INPAINT,
            image_path="/test/image.jpg",
            config={"model": "lama"}
        )
        
        self.cancellation_manager.cancel_task(task.task_id, TaskCancellationReason.TIMEOUT)
        
        # 验证回调被调用
        self.assertEqual(len(callback_called), 1)
        self.assertEqual(callback_called[0][0], task.task_id)
        self.assertEqual(callback_called[0][1], TaskCancellationReason.TIMEOUT)


class TestTaskRetryManager(unittest.TestCase):
    """任务重试管理器测试"""
    
    def setUp(self):
        """设置测试环境"""
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, f"test_{id(self)}.db")
        
        # 创建测试配置
        config = DistributedConfig()
        config.database.sqlite_path = self.db_path
        config.max_task_retries = 3
        
        # 模拟配置
        self.config_patcher = patch('lama_cleaner.distributed.config.get_config')
        self.mock_get_config = self.config_patcher.start()
        self.mock_get_config.return_value = config
        
        # 重置存储管理器
        import lama_cleaner.distributed.storage as storage_module
        storage_module.storage_manager._storage = None
        
        self.task_manager = TaskManager()
        self.retry_manager = TaskRetryManager(self.task_manager)
    
    def tearDown(self):
        """清理测试环境"""
        self.retry_manager.stop()
        self.config_patcher.stop()
        
        # 重置存储管理器
        import lama_cleaner.distributed.storage as storage_module
        storage_module.storage_manager._storage = None
        
        if os.path.exists(self.db_path):
            os.remove(self.db_path)
        if os.path.exists(self.temp_dir):
            os.rmdir(self.temp_dir)
    
    def test_immediate_retry(self):
        """测试立即重试"""
        # 创建失败的任务
        task = self.task_manager.create_task(
            task_type=TaskType.INPAINT,
            image_path="/test/image.jpg",
            config={"model": "lama"}
        )
        
        self.task_manager.fail_task(task.task_id, "Test error")
        
        # 设置立即重试配置
        retry_config = RetryConfig(strategy=RetryStrategy.IMMEDIATE)
        self.retry_manager.set_task_retry_config(task.task_id, retry_config)
        
        # 重试任务
        success = self.retry_manager.retry_task(task.task_id)
        self.assertTrue(success)
        
        # 验证任务状态
        updated_task = self.task_manager.get_task(task.task_id)
        self.assertEqual(updated_task.status, TaskStatus.PENDING)
        self.assertEqual(updated_task.retry_count, 1)
    
    def test_delayed_retry(self):
        """测试延迟重试"""
        # 创建失败的任务
        task = self.task_manager.create_task(
            task_type=TaskType.INPAINT,
            image_path="/test/image.jpg",
            config={"model": "lama"}
        )
        
        self.task_manager.fail_task(task.task_id, "Test error")
        
        # 设置延迟重试配置
        retry_config = RetryConfig(
            strategy=RetryStrategy.FIXED_DELAY,
            base_delay=0.1,  # 0.1秒延迟
            jitter=False
        )
        self.retry_manager.set_task_retry_config(task.task_id, retry_config)
        
        # 启动重试管理器
        self.retry_manager.start()
        
        # 重试任务
        success = self.retry_manager.retry_task(task.task_id)
        self.assertTrue(success)
        
        # 任务应该还是失败状态（延迟重试）
        task_before = self.task_manager.get_task(task.task_id)
        self.assertEqual(task_before.status, TaskStatus.FAILED)
        
        # 等待延迟重试
        time.sleep(0.3)  # 增加等待时间
        
        # 手动触发延迟重试处理
        self.retry_manager._process_delayed_retries()
        
        # 验证任务被重试
        updated_task = self.task_manager.get_task(task.task_id)
        self.assertEqual(updated_task.status, TaskStatus.PENDING)
        self.assertEqual(updated_task.retry_count, 1)
    
    def test_max_retries_limit(self):
        """测试最大重试次数限制"""
        # 创建任务并设置最大重试次数为2
        task = self.task_manager.create_task(
            task_type=TaskType.INPAINT,
            image_path="/test/image.jpg",
            config={"model": "lama"}
        )
        task.max_retries = 2
        
        # 设置重试配置
        retry_config = RetryConfig(max_retries=2)
        self.retry_manager.set_task_retry_config(task.task_id, retry_config)
        
        # 手动设置任务为失败状态并增加重试次数
        task.status = TaskStatus.FAILED
        task.retry_count = 0
        self.task_manager.storage.update_task(task)
        
        # 第一次重试应该成功
        success1 = self.retry_manager.retry_task(task.task_id)
        self.assertTrue(success1)
        
        # 手动设置任务为失败状态并增加重试次数
        task.status = TaskStatus.FAILED
        task.retry_count = 1
        self.task_manager.storage.update_task(task)
        
        # 第二次重试应该成功
        success2 = self.retry_manager.retry_task(task.task_id)
        self.assertTrue(success2)
        
        # 手动设置任务为失败状态并增加重试次数到最大值
        task.status = TaskStatus.FAILED
        task.retry_count = 2
        self.task_manager.storage.update_task(task)
        
        # 第三次重试应该失败（已达到最大重试次数）
        success3 = self.retry_manager.retry_task(task.task_id)
        self.assertFalse(success3)
    
    def test_retry_failed_tasks(self):
        """测试批量重试失败任务"""
        # 创建多个失败任务
        failed_tasks = []
        for i in range(3):
            task = self.task_manager.create_task(
                task_type=TaskType.INPAINT,
                image_path=f"/test/image{i}.jpg",
                config={"model": "lama"}
            )
            # 手动设置为失败状态
            task.status = TaskStatus.FAILED
            task.error_message = f"Test error {i}"
            self.task_manager.storage.update_task(task)
            # 更新缓存
            with self.task_manager.cache_lock:
                self.task_manager.task_cache[task.task_id] = task
            failed_tasks.append(task)
        
        # 批量重试（限制数量）
        retry_count = self.retry_manager.retry_failed_tasks(limit=3)
        self.assertEqual(retry_count, 3)
        
        # 验证所有任务都被重试
        for task in failed_tasks:
            updated_task = self.task_manager.get_task(task.task_id)
            self.assertEqual(updated_task.status, TaskStatus.PENDING)
            self.assertEqual(updated_task.retry_count, 1)


class TestTaskControlManager(unittest.TestCase):
    """任务控制管理器测试"""
    
    def setUp(self):
        """设置测试环境"""
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, f"test_{id(self)}.db")
        
        # 创建测试配置
        config = DistributedConfig()
        config.database.sqlite_path = self.db_path
        config.default_task_timeout = 10
        config.max_task_retries = 3
        
        # 模拟配置
        self.config_patcher = patch('lama_cleaner.distributed.config.get_config')
        self.mock_get_config = self.config_patcher.start()
        self.mock_get_config.return_value = config
        
        # 重置存储管理器
        import lama_cleaner.distributed.storage as storage_module
        storage_module.storage_manager._storage = None
        
        self.task_manager = TaskManager()
        self.queue_manager = Mock()
        self.node_manager = Mock()
        
        self.control_manager = TaskControlManager(
            self.task_manager, self.queue_manager, self.node_manager
        )
    
    def tearDown(self):
        """清理测试环境"""
        self.control_manager.stop()
        self.config_patcher.stop()
        
        # 重置存储管理器
        import lama_cleaner.distributed.storage as storage_module
        storage_module.storage_manager._storage = None
        
        if os.path.exists(self.db_path):
            os.remove(self.db_path)
        if os.path.exists(self.temp_dir):
            os.rmdir(self.temp_dir)
    
    def test_automatic_timeout_management(self):
        """测试自动超时管理"""
        # 创建任务
        task = self.task_manager.create_task(
            task_type=TaskType.INPAINT,
            image_path="/test/image.jpg",
            config={"model": "lama"}
        )
        
        # 开始处理任务
        self.task_manager.mark_task_processing(task.task_id, "node123")
        
        # 验证超时已设置
        self.assertIn(task.task_id, self.control_manager.timeout_manager.task_timeouts)
        
        # 完成任务
        self.task_manager.complete_task(task.task_id, "/result.jpg", 10.0)
        
        # 验证超时已移除
        self.assertNotIn(task.task_id, self.control_manager.timeout_manager.task_timeouts)
    
    def test_automatic_retry_on_failure(self):
        """测试失败时自动重试"""
        # 启动控制管理器
        self.control_manager.start()
        
        # 创建任务
        task = self.task_manager.create_task(
            task_type=TaskType.INPAINT,
            image_path="/test/image.jpg",
            config={"model": "lama"}
        )
        
        # 手动设置任务为失败状态（模拟任务失败）
        task.status = TaskStatus.FAILED
        task.error_message = "Test error"
        self.task_manager.storage.update_task(task)
        # 更新缓存
        with self.task_manager.cache_lock:
            self.task_manager.task_cache[task.task_id] = task
        
        # 手动触发状态变更回调
        self.control_manager._on_task_status_change(task)
        
        # 等待自动重试
        time.sleep(0.2)
        
        # 手动触发延迟重试处理
        self.control_manager.retry_manager._process_delayed_retries()
        
        # 验证任务被重试（状态变为 PENDING，重试次数增加）
        updated_task = self.task_manager.get_task(task.task_id)
        self.assertEqual(updated_task.status, TaskStatus.PENDING)
        self.assertEqual(updated_task.retry_count, 1)


if __name__ == '__main__':
    unittest.main()