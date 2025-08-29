"""
任务提交和调度测试

测试任务调度器的功能，包括任务提交、路由、调度和批量处理。
"""

import unittest
import tempfile
import os
import time
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime

from ..models import Task, TaskStatus, TaskType, TaskPriority, NodeCapability, NodeType, NodeStatus
from ..scheduler import TaskScheduler, TaskSubmissionRequest
from ..config import DistributedConfig


class TestTaskSubmissionRequest(unittest.TestCase):
    """任务提交请求测试"""
    
    def test_create_request(self):
        """测试创建任务提交请求"""
        request = TaskSubmissionRequest(
            task_type=TaskType.INPAINT,
            image_path="/test/image.jpg",
            config={"model": "lama"},
            mask_path="/test/mask.png",
            priority=TaskPriority.HIGH,
            user_id="user123",
            session_id="session456"
        )
        
        self.assertEqual(request.task_type, TaskType.INPAINT)
        self.assertEqual(request.image_path, "/test/image.jpg")
        self.assertEqual(request.mask_path, "/test/mask.png")
        self.assertEqual(request.priority, TaskPriority.HIGH)
        self.assertEqual(request.user_id, "user123")
        self.assertEqual(request.session_id, "session456")
        self.assertIsInstance(request.submitted_at, datetime)


class TestTaskScheduler(unittest.TestCase):
    """任务调度器测试"""
    
    def setUp(self):
        """设置测试环境"""
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, f"test_{id(self)}.db")
        
        # 创建测试配置
        config = DistributedConfig()
        config.database.sqlite_path = self.db_path
        config.enabled = True
        
        # 模拟配置
        self.config_patcher = patch('lama_cleaner.distributed.config.get_config')
        self.mock_get_config = self.config_patcher.start()
        self.mock_get_config.return_value = config
        
        # 重置存储管理器
        import lama_cleaner.distributed.storage as storage_module
        storage_module.storage_manager._storage = None
        
        # 创建调度器（但不启动）
        self.scheduler = TaskScheduler()
        
        # 模拟队列管理器和节点管理器
        self.scheduler.queue_manager = Mock()
        self.scheduler.node_manager = Mock()
        
        # 设置默认的模拟返回值
        self.scheduler.queue_manager.send_task_to_queue = Mock(return_value=True)
        self.scheduler.node_manager.get_online_nodes = Mock(return_value=[])
    
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
    
    def test_submit_task(self):
        """测试提交任务"""
        request = TaskSubmissionRequest(
            task_type=TaskType.INPAINT,
            image_path="/test/image.jpg",
            config={"model": "lama"},
            priority=TaskPriority.HIGH
        )
        
        task_id = self.scheduler.submit_task(request)
        
        self.assertIsNotNone(task_id)
        self.assertEqual(self.scheduler.stats['submitted_tasks'], 1)
        
        # 验证任务已创建
        task = self.scheduler.task_manager.get_task(task_id)
        self.assertIsNotNone(task)
        self.assertEqual(task.task_type, TaskType.INPAINT)
        self.assertEqual(task.priority, TaskPriority.HIGH)
        self.assertEqual(task.status, TaskStatus.PENDING)
    
    def test_submit_inpaint_task(self):
        """测试提交图像修复任务"""
        task_id = self.scheduler.submit_inpaint_task(
            image_path="/test/image.jpg",
            mask_path="/test/mask.png",
            config={"model": "lama"},
            priority=TaskPriority.NORMAL,
            user_id="user123"
        )
        
        self.assertIsNotNone(task_id)
        
        task = self.scheduler.task_manager.get_task(task_id)
        self.assertEqual(task.task_type, TaskType.INPAINT)
        self.assertEqual(task.image_path, "/test/image.jpg")
        self.assertEqual(task.mask_path, "/test/mask.png")
        self.assertEqual(task.user_id, "user123")
    
    def test_submit_plugin_task(self):
        """测试提交插件任务"""
        task_id = self.scheduler.submit_plugin_task(
            image_path="/test/image.jpg",
            plugin_name="realesrgan",
            config={"scale": 4},
            priority=TaskPriority.HIGH
        )
        
        self.assertIsNotNone(task_id)
        
        task = self.scheduler.task_manager.get_task(task_id)
        self.assertEqual(task.task_type, TaskType.PLUGIN)
        self.assertEqual(task.config['plugin_name'], "realesrgan")
        self.assertEqual(task.config['scale'], 4)
    
    def test_submit_batch_tasks(self):
        """测试批量提交任务"""
        requests = [
            TaskSubmissionRequest(
                task_type=TaskType.INPAINT,
                image_path=f"/test/image{i}.jpg",
                config={"model": "lama"}
            )
            for i in range(3)
        ]
        
        task_ids = self.scheduler.submit_batch_tasks(requests)
        
        self.assertEqual(len(task_ids), 3)
        self.assertEqual(self.scheduler.stats['submitted_tasks'], 3)
        
        # 验证所有任务都已创建
        for task_id in task_ids:
            task = self.scheduler.task_manager.get_task(task_id)
            self.assertIsNotNone(task)
            self.assertEqual(task.task_type, TaskType.INPAINT)
    
    def test_cancel_task(self):
        """测试取消任务"""
        task_id = self.scheduler.submit_inpaint_task(
            image_path="/test/image.jpg",
            mask_path="/test/mask.png",
            config={"model": "lama"}
        )
        
        # 取消任务
        success = self.scheduler.cancel_task(task_id)
        self.assertTrue(success)
        
        # 验证任务状态
        task = self.scheduler.task_manager.get_task(task_id)
        self.assertEqual(task.status, TaskStatus.CANCELLED)
    
    def test_get_task_status(self):
        """测试获取任务状态"""
        task_id = self.scheduler.submit_inpaint_task(
            image_path="/test/image.jpg",
            mask_path="/test/mask.png",
            config={"model": "lama"}
        )
        
        status = self.scheduler.get_task_status(task_id)
        
        self.assertIsNotNone(status)
        self.assertEqual(status['task_id'], task_id)
        self.assertEqual(status['status'], TaskStatus.PENDING.value)
        self.assertIn('progress_percent', status)
        self.assertIn('created_at', status)
    
    def test_analyze_task_requirements(self):
        """测试分析任务需求"""
        # 测试 Stable Diffusion 任务
        sd_task = Task(
            task_type=TaskType.INPAINT,
            config={"model": "sd15"}
        )
        
        requirements = self.scheduler._analyze_task_requirements(sd_task)
        
        self.assertTrue(requirements['gpu_required'])
        self.assertEqual(requirements['min_memory'], 8192)
        self.assertIn('sd15', requirements['required_models'])
        
        # 测试 LaMa 任务
        lama_task = Task(
            task_type=TaskType.INPAINT,
            config={"model": "lama", "use_gpu": False}
        )
        
        requirements = self.scheduler._analyze_task_requirements(lama_task)
        
        self.assertFalse(requirements['gpu_required'])
        self.assertEqual(requirements['min_memory'], 2048)
        self.assertIn('lama', requirements['required_models'])
    
    def test_find_suitable_nodes(self):
        """测试查找合适的节点"""
        # 创建测试节点
        gpu_node = NodeCapability(
            node_id="gpu_node",
            node_type=NodeType.LOCAL,
            gpu_count=1,
            gpu_memory=8192,
            cpu_cores=8,
            memory_total=16384,
            supported_models=["sd15", "lama"],
            supported_tasks=[TaskType.INPAINT],
            status=NodeStatus.ONLINE
        )
        
        cpu_node = NodeCapability(
            node_id="cpu_node",
            node_type=NodeType.LOCAL,
            gpu_count=0,
            cpu_cores=4,
            memory_total=8192,
            supported_models=["lama", "opencv"],
            supported_tasks=[TaskType.INPAINT],
            status=NodeStatus.ONLINE
        )
        
        self.scheduler.node_manager.get_online_nodes.return_value = [gpu_node, cpu_node]
        
        # 测试 GPU 任务需求
        gpu_requirements = {
            'task_type': TaskType.INPAINT,
            'gpu_required': True,
            'min_memory': 8192,
            'min_cpu_cores': 1,
            'required_models': ['sd15']
        }
        
        suitable_nodes = self.scheduler._find_suitable_nodes(gpu_requirements)
        self.assertEqual(len(suitable_nodes), 1)
        self.assertEqual(suitable_nodes[0].node_id, "gpu_node")
        
        # 测试 CPU 任务需求
        cpu_requirements = {
            'task_type': TaskType.INPAINT,
            'gpu_required': False,
            'min_memory': 4096,
            'min_cpu_cores': 1,
            'required_models': ['lama']
        }
        
        suitable_nodes = self.scheduler._find_suitable_nodes(cpu_requirements)
        self.assertEqual(len(suitable_nodes), 2)  # 两个节点都可以处理
    
    def test_node_meets_requirements(self):
        """测试节点需求匹配"""
        node = NodeCapability(
            node_id="test_node",
            gpu_count=1,
            gpu_memory=8192,
            cpu_cores=8,
            memory_total=16384,
            supported_models=["sd15", "lama"],
            supported_tasks=[TaskType.INPAINT],
            max_concurrent_tasks=4
        )
        
        # 模拟节点任务数量检查
        self.scheduler.task_manager.can_assign_task_to_node = Mock(return_value=True)
        
        # 测试满足需求的情况
        requirements = {
            'task_type': TaskType.INPAINT,
            'gpu_required': True,
            'min_memory': 4096,
            'min_cpu_cores': 4,
            'required_models': ['sd15']
        }
        
        self.assertTrue(self.scheduler._node_meets_requirements(node, requirements))
        
        # 测试不满足 GPU 需求
        requirements['gpu_required'] = True
        node.gpu_count = 0
        self.assertFalse(self.scheduler._node_meets_requirements(node, requirements))
        
        # 测试不满足内存需求
        node.gpu_count = 1
        requirements['min_memory'] = 32768
        self.assertFalse(self.scheduler._node_meets_requirements(node, requirements))
        
        # 测试不支持的模型
        requirements['min_memory'] = 4096
        requirements['required_models'] = ['unsupported_model']
        self.assertFalse(self.scheduler._node_meets_requirements(node, requirements))
    
    def test_select_best_node(self):
        """测试选择最佳节点"""
        # 创建不同性能的节点
        high_perf_node = NodeCapability(
            node_id="high_perf",
            gpu_count=1,
            gpu_memory=16384,
            cpu_cores=16,
            memory_total=32768,
            max_concurrent_tasks=8,
            total_processed=1000
        )
        
        low_perf_node = NodeCapability(
            node_id="low_perf",
            gpu_count=1,
            gpu_memory=4096,
            cpu_cores=4,
            memory_total=8192,
            max_concurrent_tasks=2,
            total_processed=100
        )
        
        # 模拟节点负载
        self.scheduler.task_manager.get_node_task_count = Mock(side_effect=lambda node_id: {
            "high_perf": 2,
            "low_perf": 1
        }.get(node_id, 0))
        
        task = Task(task_type=TaskType.INPAINT)
        nodes = [low_perf_node, high_perf_node]  # 故意颠倒顺序
        
        best_node = self.scheduler._select_best_node(nodes, task)
        
        # 高性能节点应该被选中
        self.assertEqual(best_node.node_id, "high_perf")
    
    def test_calculate_node_score(self):
        """测试计算节点评分"""
        node = NodeCapability(
            node_id="test_node",
            gpu_count=1,
            gpu_memory=8192,
            cpu_cores=8,
            memory_total=16384,
            max_concurrent_tasks=4,
            total_processed=500
        )
        
        # 模拟节点负载
        self.scheduler.task_manager.get_node_task_count = Mock(return_value=1)
        
        task = Task(task_type=TaskType.INPAINT)
        score = self.scheduler._calculate_node_score(node, task)
        
        self.assertGreater(score, 0)
        self.assertIsInstance(score, float)
    
    def test_select_queue_for_task(self):
        """测试为任务选择队列"""
        # 高性能 GPU 节点
        high_gpu_node = NodeCapability(
            node_id="high_gpu_node",
            gpu_count=1,
            gpu_memory=8192,
            cpu_cores=8,
            memory_total=16384
        )
        
        # 中等性能 GPU 节点
        med_gpu_node = NodeCapability(
            node_id="med_gpu_node",
            gpu_count=1,
            gpu_memory=4096,
            cpu_cores=4,
            memory_total=8192
        )
        
        # 高内存需求任务
        high_mem_task = Task(
            task_type=TaskType.INPAINT,
            config={"model": "sd15"}
        )
        
        queue_name = self.scheduler._select_queue_for_task(high_mem_task, high_gpu_node)
        self.assertEqual(queue_name, "gpu-high")
        
        # 中等内存需求任务
        med_mem_task = Task(
            task_type=TaskType.INPAINT,
            config={"model": "lama", "use_gpu": True}
        )
        
        queue_name = self.scheduler._select_queue_for_task(med_mem_task, med_gpu_node)
        self.assertEqual(queue_name, "gpu-medium")
    
    def test_process_scheduling(self):
        """测试处理任务调度"""
        # 创建任务（明确指定不使用 GPU）
        task_id = self.scheduler.submit_inpaint_task(
            image_path="/test/image.jpg",
            mask_path="/test/mask.png",
            config={"model": "lama", "use_gpu": False}
        )
        
        # 创建合适的节点
        node = NodeCapability(
            node_id="test_node",
            gpu_count=0,
            cpu_cores=4,
            memory_total=8192,
            supported_models=["lama"],
            supported_tasks=[TaskType.INPAINT],
            max_concurrent_tasks=4,
            status=NodeStatus.ONLINE
        )
        
        self.scheduler.node_manager.get_online_nodes.return_value = [node]
        self.scheduler.task_manager.can_assign_task_to_node = Mock(return_value=True)
        
        # 处理调度
        self.scheduler._process_scheduling(task_id, None)
        
        # 验证任务已被调度
        task = self.scheduler.task_manager.get_task(task_id)
        self.assertEqual(task.status, TaskStatus.QUEUED)
        self.assertEqual(task.assigned_node, "test_node")
        self.assertIsNotNone(task.queue_name)
        
        # 验证队列管理器被调用
        self.scheduler.queue_manager.send_task_to_queue.assert_called_once()
    
    def test_get_scheduler_statistics(self):
        """测试获取调度器统计信息"""
        # 提交一些任务
        for i in range(3):
            self.scheduler.submit_inpaint_task(
                image_path=f"/test/image{i}.jpg",
                mask_path=f"/test/mask{i}.png",
                config={"model": "lama"}
            )
        
        # 模拟节点管理器返回值
        self.scheduler.node_manager.get_online_nodes.return_value = [
            NodeCapability(node_id="node1", status=NodeStatus.ONLINE),
            NodeCapability(node_id="node2", status=NodeStatus.ONLINE)
        ]
        
        stats = self.scheduler.get_scheduler_statistics()
        
        self.assertIn('submitted_tasks', stats)
        self.assertIn('scheduled_tasks', stats)
        self.assertIn('queue_status', stats)
        self.assertIn('active_nodes', stats)
        self.assertEqual(stats['submitted_tasks'], 3)
        self.assertEqual(stats['active_nodes'], 2)


if __name__ == '__main__':
    unittest.main()