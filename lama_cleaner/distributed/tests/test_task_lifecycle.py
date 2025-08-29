"""
任务生命周期管理测试

测试任务的创建、状态转换、持久化存储等功能。
"""

import unittest
import tempfile
import os
from datetime import datetime, timedelta
from pathlib import Path

from ..models import Task, TaskStatus, TaskType, TaskPriority
from ..task_manager import TaskManager, TaskLifecycleManager
from ..storage import SQLiteTaskStorage
from ..config import DistributedConfig


class TestTaskLifecycleManager(unittest.TestCase):
    """任务生命周期管理器测试"""
    
    def test_valid_transitions(self):
        """测试有效的状态转换"""
        # PENDING 可以转换到 QUEUED 或 CANCELLED
        self.assertTrue(TaskLifecycleManager.can_transition(TaskStatus.PENDING, TaskStatus.QUEUED))
        self.assertTrue(TaskLifecycleManager.can_transition(TaskStatus.PENDING, TaskStatus.CANCELLED))
        self.assertFalse(TaskLifecycleManager.can_transition(TaskStatus.PENDING, TaskStatus.PROCESSING))
        
        # QUEUED 可以转换到 PROCESSING、CANCELLED 或 PENDING
        self.assertTrue(TaskLifecycleManager.can_transition(TaskStatus.QUEUED, TaskStatus.PROCESSING))
        self.assertTrue(TaskLifecycleManager.can_transition(TaskStatus.QUEUED, TaskStatus.CANCELLED))
        self.assertTrue(TaskLifecycleManager.can_transition(TaskStatus.QUEUED, TaskStatus.PENDING))
        
        # PROCESSING 可以转换到 COMPLETED、FAILED 或 CANCELLED
        self.assertTrue(TaskLifecycleManager.can_transition(TaskStatus.PROCESSING, TaskStatus.COMPLETED))
        self.assertTrue(TaskLifecycleManager.can_transition(TaskStatus.PROCESSING, TaskStatus.FAILED))
        self.assertTrue(TaskLifecycleManager.can_transition(TaskStatus.PROCESSING, TaskStatus.CANCELLED))
        
        # COMPLETED 不能转换到其他状态
        self.assertFalse(TaskLifecycleManager.can_transition(TaskStatus.COMPLETED, TaskStatus.PENDING))
        self.assertFalse(TaskLifecycleManager.can_transition(TaskStatus.COMPLETED, TaskStatus.FAILED))
        
        # FAILED 可以转换到 PENDING（重试）
        self.assertTrue(TaskLifecycleManager.can_transition(TaskStatus.FAILED, TaskStatus.PENDING))
        self.assertFalse(TaskLifecycleManager.can_transition(TaskStatus.FAILED, TaskStatus.COMPLETED))
        
        # CANCELLED 不能转换到其他状态
        self.assertFalse(TaskLifecycleManager.can_transition(TaskStatus.CANCELLED, TaskStatus.PENDING))
    
    def test_validate_transition(self):
        """测试状态转换验证"""
        task = Task(status=TaskStatus.PENDING)
        
        # 有效转换
        self.assertTrue(TaskLifecycleManager.validate_transition(task, TaskStatus.QUEUED))
        
        # 无效转换
        self.assertFalse(TaskLifecycleManager.validate_transition(task, TaskStatus.PROCESSING))
    
    def test_get_next_valid_statuses(self):
        """测试获取下一个有效状态"""
        pending_next = TaskLifecycleManager.get_next_valid_statuses(TaskStatus.PENDING)
        self.assertIn(TaskStatus.QUEUED, pending_next)
        self.assertIn(TaskStatus.CANCELLED, pending_next)
        
        completed_next = TaskLifecycleManager.get_next_valid_statuses(TaskStatus.COMPLETED)
        self.assertEqual(len(completed_next), 0)


class TestSQLiteTaskStorage(unittest.TestCase):
    """SQLite 任务存储测试"""
    
    def setUp(self):
        """设置测试环境"""
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, "test.db")
        self.storage = SQLiteTaskStorage(self.db_path)
    
    def tearDown(self):
        """清理测试环境"""
        if os.path.exists(self.db_path):
            os.remove(self.db_path)
        os.rmdir(self.temp_dir)
    
    def test_save_and_get_task(self):
        """测试保存和获取任务"""
        task = Task(
            task_type=TaskType.INPAINT,
            image_path="/test/image.jpg",
            config={"model": "lama"},
            priority=TaskPriority.HIGH,
            user_id="user123",
            session_id="session456"
        )
        
        # 保存任务
        self.assertTrue(self.storage.save_task(task))
        
        # 获取任务
        retrieved_task = self.storage.get_task(task.task_id)
        self.assertIsNotNone(retrieved_task)
        self.assertEqual(retrieved_task.task_id, task.task_id)
        self.assertEqual(retrieved_task.task_type, task.task_type)
        self.assertEqual(retrieved_task.status, task.status)
        self.assertEqual(retrieved_task.priority, task.priority)
        self.assertEqual(retrieved_task.image_path, task.image_path)
        self.assertEqual(retrieved_task.config, task.config)
        self.assertEqual(retrieved_task.user_id, task.user_id)
        self.assertEqual(retrieved_task.session_id, task.session_id)
    
    def test_update_task(self):
        """测试更新任务"""
        task = Task(task_type=TaskType.INPAINT, image_path="/test/image.jpg")
        
        # 保存任务
        self.assertTrue(self.storage.save_task(task))
        
        # 更新任务状态
        task.status = TaskStatus.PROCESSING
        task.assigned_node = "node123"
        task.error_message = "Test error"
        
        self.assertTrue(self.storage.update_task(task))
        
        # 验证更新
        retrieved_task = self.storage.get_task(task.task_id)
        self.assertEqual(retrieved_task.status, TaskStatus.PROCESSING)
        self.assertEqual(retrieved_task.assigned_node, "node123")
        self.assertEqual(retrieved_task.error_message, "Test error")
    
    def test_delete_task(self):
        """测试删除任务"""
        task = Task(task_type=TaskType.INPAINT, image_path="/test/image.jpg")
        
        # 保存任务
        self.assertTrue(self.storage.save_task(task))
        
        # 确认任务存在
        self.assertIsNotNone(self.storage.get_task(task.task_id))
        
        # 删除任务
        self.assertTrue(self.storage.delete_task(task.task_id))
        
        # 确认任务已删除
        self.assertIsNone(self.storage.get_task(task.task_id))
    
    def test_get_tasks_by_status(self):
        """测试根据状态获取任务"""
        # 创建不同状态的任务
        task1 = Task(task_type=TaskType.INPAINT, status=TaskStatus.PENDING)
        task2 = Task(task_type=TaskType.INPAINT, status=TaskStatus.PROCESSING)
        task3 = Task(task_type=TaskType.INPAINT, status=TaskStatus.PENDING)
        
        self.storage.save_task(task1)
        self.storage.save_task(task2)
        self.storage.save_task(task3)
        
        # 获取待处理任务
        pending_tasks = self.storage.get_tasks_by_status(TaskStatus.PENDING)
        self.assertEqual(len(pending_tasks), 2)
        
        # 获取处理中任务
        processing_tasks = self.storage.get_tasks_by_status(TaskStatus.PROCESSING)
        self.assertEqual(len(processing_tasks), 1)
        
        # 测试限制数量
        limited_tasks = self.storage.get_tasks_by_status(TaskStatus.PENDING, limit=1)
        self.assertEqual(len(limited_tasks), 1)
    
    def test_get_pending_tasks_priority_order(self):
        """测试待处理任务按优先级排序"""
        # 创建不同优先级的任务
        task_low = Task(task_type=TaskType.INPAINT, priority=TaskPriority.LOW)
        task_normal = Task(task_type=TaskType.INPAINT, priority=TaskPriority.NORMAL)
        task_high = Task(task_type=TaskType.INPAINT, priority=TaskPriority.HIGH)
        task_urgent = Task(task_type=TaskType.INPAINT, priority=TaskPriority.URGENT)
        
        # 按随机顺序保存
        self.storage.save_task(task_normal)
        self.storage.save_task(task_low)
        self.storage.save_task(task_urgent)
        self.storage.save_task(task_high)
        
        # 获取待处理任务
        pending_tasks = self.storage.get_pending_tasks()
        
        # 验证排序（优先级降序）
        self.assertEqual(len(pending_tasks), 4)
        self.assertEqual(pending_tasks[0].priority, TaskPriority.URGENT)
        self.assertEqual(pending_tasks[1].priority, TaskPriority.HIGH)
        self.assertEqual(pending_tasks[2].priority, TaskPriority.NORMAL)
        self.assertEqual(pending_tasks[3].priority, TaskPriority.LOW)
    
    def test_cleanup_old_tasks(self):
        """测试清理旧任务"""
        # 创建旧任务
        old_time = datetime.now() - timedelta(hours=25)
        task_old = Task(task_type=TaskType.INPAINT, status=TaskStatus.COMPLETED)
        task_old.updated_at = old_time
        
        # 创建新任务
        task_new = Task(task_type=TaskType.INPAINT, status=TaskStatus.COMPLETED)
        
        self.storage.save_task(task_old)
        self.storage.save_task(task_new)
        
        # 清理24小时前的任务
        cutoff_time = datetime.now() - timedelta(hours=24)
        cleaned_count = self.storage.cleanup_old_tasks(cutoff_time)
        
        self.assertEqual(cleaned_count, 1)
        
        # 验证旧任务已删除，新任务仍存在
        self.assertIsNone(self.storage.get_task(task_old.task_id))
        self.assertIsNotNone(self.storage.get_task(task_new.task_id))
    
    def test_get_task_statistics(self):
        """测试获取任务统计"""
        # 创建不同状态的任务
        tasks = [
            Task(task_type=TaskType.INPAINT, status=TaskStatus.PENDING),
            Task(task_type=TaskType.INPAINT, status=TaskStatus.PENDING),
            Task(task_type=TaskType.INPAINT, status=TaskStatus.PROCESSING),
            Task(task_type=TaskType.INPAINT, status=TaskStatus.COMPLETED),
            Task(task_type=TaskType.INPAINT, status=TaskStatus.FAILED),
        ]
        
        for task in tasks:
            self.storage.save_task(task)
        
        stats = self.storage.get_task_statistics()
        
        self.assertEqual(stats['pending'], 2)
        self.assertEqual(stats['processing'], 1)
        self.assertEqual(stats['completed'], 1)
        self.assertEqual(stats['failed'], 1)
        self.assertEqual(stats['cancelled'], 0)
        self.assertEqual(stats['total'], 5)


class TestTaskManager(unittest.TestCase):
    """任务管理器测试"""
    
    def setUp(self):
        """设置测试环境"""
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, f"test_{id(self)}.db")
        
        # 创建测试配置
        config = DistributedConfig()
        config.database.sqlite_path = self.db_path
        
        # 模拟配置
        import lama_cleaner.distributed.config as config_module
        self.original_get_config = config_module.get_config
        config_module.get_config = lambda: config
        
        # 重置存储管理器
        import lama_cleaner.distributed.storage as storage_module
        storage_module.storage_manager._storage = None
        
        self.task_manager = TaskManager()
    
    def tearDown(self):
        """清理测试环境"""
        # 恢复原始配置函数
        import lama_cleaner.distributed.config as config_module
        config_module.get_config = self.original_get_config
        
        # 重置存储管理器
        import lama_cleaner.distributed.storage as storage_module
        storage_module.storage_manager._storage = None
        
        if os.path.exists(self.db_path):
            os.remove(self.db_path)
        if os.path.exists(self.temp_dir):
            os.rmdir(self.temp_dir)
    
    def test_create_task(self):
        """测试创建任务"""
        task = self.task_manager.create_task(
            task_type=TaskType.INPAINT,
            image_path="/test/image.jpg",
            config={"model": "lama"},
            priority=TaskPriority.HIGH,
            user_id="user123"
        )
        
        self.assertIsNotNone(task)
        self.assertEqual(task.task_type, TaskType.INPAINT)
        self.assertEqual(task.status, TaskStatus.PENDING)
        self.assertEqual(task.priority, TaskPriority.HIGH)
        self.assertEqual(task.user_id, "user123")
        
        # 验证任务已保存到存储
        retrieved_task = self.task_manager.get_task(task.task_id)
        self.assertIsNotNone(retrieved_task)
        self.assertEqual(retrieved_task.task_id, task.task_id)
    
    def test_update_task_status(self):
        """测试更新任务状态"""
        task = self.task_manager.create_task(
            task_type=TaskType.INPAINT,
            image_path="/test/image.jpg",
            config={}
        )
        
        # 有效状态转换
        self.assertTrue(self.task_manager.update_task_status(
            task.task_id, TaskStatus.QUEUED, assigned_node="node123"
        ))
        
        updated_task = self.task_manager.get_task(task.task_id)
        self.assertEqual(updated_task.status, TaskStatus.QUEUED)
        self.assertEqual(updated_task.assigned_node, "node123")
        
        # 无效状态转换
        self.assertFalse(self.task_manager.update_task_status(
            task.task_id, TaskStatus.COMPLETED  # QUEUED 不能直接转换到 COMPLETED
        ))
    
    def test_cancel_task(self):
        """测试取消任务"""
        task = self.task_manager.create_task(
            task_type=TaskType.INPAINT,
            image_path="/test/image.jpg",
            config={}
        )
        
        # 取消待处理任务
        self.assertTrue(self.task_manager.cancel_task(task.task_id))
        
        updated_task = self.task_manager.get_task(task.task_id)
        self.assertEqual(updated_task.status, TaskStatus.CANCELLED)
        
        # 不能取消已取消的任务
        self.assertFalse(self.task_manager.cancel_task(task.task_id))
    
    def test_retry_task(self):
        """测试重试任务"""
        task = self.task_manager.create_task(
            task_type=TaskType.INPAINT,
            image_path="/test/image.jpg",
            config={}
        )
        
        # 先标记为失败
        self.task_manager.update_task_status(task.task_id, TaskStatus.QUEUED)
        self.task_manager.update_task_status(task.task_id, TaskStatus.PROCESSING)
        self.task_manager.update_task_status(task.task_id, TaskStatus.FAILED, error_message="Test error")
        
        # 重试任务
        self.assertTrue(self.task_manager.retry_task(task.task_id))
        
        updated_task = self.task_manager.get_task(task.task_id)
        self.assertEqual(updated_task.status, TaskStatus.PENDING)
        self.assertEqual(updated_task.retry_count, 1)
        self.assertIsNone(updated_task.assigned_node)
        self.assertIsNone(updated_task.error_message)
    
    def test_assign_task_to_node(self):
        """测试分配任务给节点"""
        task = self.task_manager.create_task(
            task_type=TaskType.INPAINT,
            image_path="/test/image.jpg",
            config={}
        )
        
        # 分配任务
        self.assertTrue(self.task_manager.assign_task_to_node(
            task.task_id, "node123", "gpu-high"
        ))
        
        updated_task = self.task_manager.get_task(task.task_id)
        self.assertEqual(updated_task.status, TaskStatus.QUEUED)
        self.assertEqual(updated_task.assigned_node, "node123")
        self.assertEqual(updated_task.queue_name, "gpu-high")
    
    def test_task_lifecycle_flow(self):
        """测试完整的任务生命周期"""
        # 创建任务
        task = self.task_manager.create_task(
            task_type=TaskType.INPAINT,
            image_path="/test/image.jpg",
            config={"model": "lama"}
        )
        self.assertEqual(task.status, TaskStatus.PENDING)
        
        # 分配给节点
        self.assertTrue(self.task_manager.assign_task_to_node(
            task.task_id, "node123", "gpu-high"
        ))
        
        # 开始处理
        self.assertTrue(self.task_manager.mark_task_processing(task.task_id, "node123"))
        
        # 完成任务
        self.assertTrue(self.task_manager.complete_task(
            task.task_id, "/result/image.jpg", 15.5
        ))
        
        final_task = self.task_manager.get_task(task.task_id)
        self.assertEqual(final_task.status, TaskStatus.COMPLETED)
        self.assertEqual(final_task.result_path, "/result/image.jpg")
        self.assertEqual(final_task.processing_time, 15.5)
    
    def test_get_pending_tasks(self):
        """测试获取待处理任务"""
        # 清理现有任务
        stats = self.task_manager.get_task_statistics()
        
        # 创建不同优先级的任务
        task1 = self.task_manager.create_task(
            TaskType.INPAINT, "/test1.jpg", {}, priority=TaskPriority.LOW
        )
        task2 = self.task_manager.create_task(
            TaskType.INPAINT, "/test2.jpg", {}, priority=TaskPriority.HIGH
        )
        task3 = self.task_manager.create_task(
            TaskType.INPAINT, "/test3.jpg", {}, priority=TaskPriority.NORMAL
        )
        
        pending_tasks = self.task_manager.get_pending_tasks()
        
        # 过滤出我们刚创建的任务
        our_tasks = [t for t in pending_tasks if t.task_id in [task1.task_id, task2.task_id, task3.task_id]]
        
        # 验证按优先级排序
        self.assertEqual(len(our_tasks), 3)
        self.assertEqual(our_tasks[0].priority, TaskPriority.HIGH)
        self.assertEqual(our_tasks[1].priority, TaskPriority.NORMAL)
        self.assertEqual(our_tasks[2].priority, TaskPriority.LOW)
    
    def test_node_task_management(self):
        """测试节点任务管理"""
        # 使用唯一的节点ID
        node_id = f"node_{id(self)}"
        
        # 创建任务并分配给节点
        task1 = self.task_manager.create_task(TaskType.INPAINT, "/test1.jpg", {})
        task2 = self.task_manager.create_task(TaskType.INPAINT, "/test2.jpg", {})
        
        self.task_manager.assign_task_to_node(task1.task_id, node_id, "gpu-high")
        self.task_manager.assign_task_to_node(task2.task_id, node_id, "gpu-high")
        
        # 开始处理
        self.task_manager.mark_task_processing(task1.task_id, node_id)
        self.task_manager.mark_task_processing(task2.task_id, node_id)
        
        # 检查节点任务数量
        self.assertEqual(self.task_manager.get_node_task_count(node_id), 2)
        self.assertFalse(self.task_manager.can_assign_task_to_node(node_id, 2))
        self.assertTrue(self.task_manager.can_assign_task_to_node(node_id, 3))
        
        # 完成一个任务
        self.task_manager.complete_task(task1.task_id, "/result1.jpg", 10.0)
        self.assertEqual(self.task_manager.get_node_task_count(node_id), 1)


if __name__ == '__main__':
    unittest.main()