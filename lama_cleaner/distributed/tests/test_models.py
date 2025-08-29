"""
测试核心数据模型
"""

import unittest
from datetime import datetime
from ..models import (
    Task, TaskType, TaskStatus, TaskPriority,
    NodeCapability, NodeType, NodeStatus,
    QueueConfig, DEFAULT_QUEUE_CONFIGS
)


class TestTask(unittest.TestCase):
    """测试任务模型"""
    
    def test_task_creation(self):
        """测试任务创建"""
        task = Task(
            task_type=TaskType.INPAINT,
            image_path="/test/image.jpg",
            config={"model": "lama"}
        )
        
        self.assertIsNotNone(task.task_id)
        self.assertEqual(task.task_type, TaskType.INPAINT)
        self.assertEqual(task.status, TaskStatus.PENDING)
        self.assertEqual(task.priority, TaskPriority.NORMAL)
        self.assertEqual(task.image_path, "/test/image.jpg")
        self.assertEqual(task.config["model"], "lama")
        self.assertEqual(task.retry_count, 0)
        self.assertEqual(task.max_retries, 3)
    
    def test_task_serialization(self):
        """测试任务序列化"""
        task = Task(
            task_type=TaskType.INPAINT,
            image_path="/test/image.jpg",
            config={"model": "lama", "device": "cuda"}
        )
        
        # 测试转换为字典
        task_dict = task.to_dict()
        self.assertEqual(task_dict["task_id"], task.task_id)
        self.assertEqual(task_dict["task_type"], "inpaint")
        self.assertEqual(task_dict["status"], "pending")
        self.assertEqual(task_dict["config"]["model"], "lama")
        
        # 测试从字典创建
        new_task = Task.from_dict(task_dict)
        self.assertEqual(new_task.task_id, task.task_id)
        self.assertEqual(new_task.task_type, task.task_type)
        self.assertEqual(new_task.config, task.config)
        
        # 测试 JSON 序列化
        json_str = task.to_json()
        self.assertIsInstance(json_str, str)
        
        task_from_json = Task.from_json(json_str)
        self.assertEqual(task_from_json.task_id, task.task_id)


class TestNodeCapability(unittest.TestCase):
    """测试节点能力模型"""
    
    def test_node_capability_creation(self):
        """测试节点能力创建"""
        capability = NodeCapability(
            node_type=NodeType.LOCAL,
            gpu_count=1,
            gpu_memory=8192,
            cpu_cores=8,
            memory_total=32768
        )
        
        self.assertIsNotNone(capability.node_id)
        self.assertEqual(capability.node_type, NodeType.LOCAL)
        self.assertTrue(capability.has_gpu())
        self.assertEqual(capability.gpu_memory, 8192)
        self.assertEqual(capability.cpu_cores, 8)
    
    def test_gpu_detection(self):
        """测试 GPU 检测"""
        # 有 GPU 的节点
        gpu_node = NodeCapability(gpu_count=1, gpu_memory=4096)
        self.assertTrue(gpu_node.has_gpu())
        
        # 没有 GPU 的节点
        cpu_node = NodeCapability(gpu_count=0, gpu_memory=0)
        self.assertFalse(cpu_node.has_gpu())
    
    def test_queue_subscriptions(self):
        """测试队列订阅"""
        # 高端 GPU 节点
        high_gpu_node = NodeCapability(
            gpu_count=1,
            gpu_memory=8192,
            cpu_cores=8
        )
        subscriptions = high_gpu_node.get_queue_subscriptions()
        self.assertIn("gpu-high", subscriptions)
        self.assertIn("cpu-intensive", subscriptions)
        
        # 中端 GPU 节点
        medium_gpu_node = NodeCapability(
            gpu_count=1,
            gpu_memory=4096,
            cpu_cores=4
        )
        subscriptions = medium_gpu_node.get_queue_subscriptions()
        self.assertIn("gpu-medium", subscriptions)
        self.assertIn("cpu-light", subscriptions)
        
        # CPU 节点
        cpu_node = NodeCapability(
            gpu_count=0,
            gpu_memory=0,
            cpu_cores=8
        )
        subscriptions = cpu_node.get_queue_subscriptions()
        self.assertNotIn("gpu-high", subscriptions)
        self.assertIn("cpu-intensive", subscriptions)
    
    def test_task_compatibility(self):
        """测试任务兼容性检查"""
        # GPU 节点
        gpu_node = NodeCapability(
            gpu_count=1,
            gpu_memory=4096,
            supported_models=["lama", "sd15"],
            supported_tasks=[TaskType.INPAINT]
        )
        
        # GPU 任务
        gpu_task = Task(
            task_type=TaskType.INPAINT,
            config={"model": "sd15", "gpu_required": True}
        )
        self.assertTrue(gpu_node.can_handle_task(gpu_task))
        
        # 不支持的模型
        unsupported_task = Task(
            task_type=TaskType.INPAINT,
            config={"model": "sdxl", "gpu_required": True}
        )
        self.assertFalse(gpu_node.can_handle_task(unsupported_task))
        
        # CPU 节点处理 GPU 任务
        cpu_node = NodeCapability(
            gpu_count=0,
            supported_models=["lama"],
            supported_tasks=[TaskType.INPAINT]
        )
        self.assertFalse(cpu_node.can_handle_task(gpu_task))


class TestQueueConfig(unittest.TestCase):
    """测试队列配置"""
    
    def test_queue_config_creation(self):
        """测试队列配置创建"""
        config = QueueConfig(
            name="test-queue",
            port=5555,
            requirements={"gpu": True, "gpu_memory": 4096}
        )
        
        self.assertEqual(config.name, "test-queue")
        self.assertEqual(config.port, 5555)
        self.assertEqual(config.pattern, "PUSH/PULL")
        self.assertTrue(config.requirements["gpu"])
        self.assertEqual(config.max_size, 1000)
    
    def test_default_queue_configs(self):
        """测试默认队列配置"""
        self.assertIn("gpu-high", DEFAULT_QUEUE_CONFIGS)
        self.assertIn("gpu-medium", DEFAULT_QUEUE_CONFIGS)
        self.assertIn("cpu-intensive", DEFAULT_QUEUE_CONFIGS)
        
        gpu_high = DEFAULT_QUEUE_CONFIGS["gpu-high"]
        self.assertEqual(gpu_high.port, 5555)
        self.assertTrue(gpu_high.requirements["gpu"])
        self.assertEqual(gpu_high.requirements["gpu_memory"], 8192)
    
    def test_queue_serialization(self):
        """测试队列配置序列化"""
        config = QueueConfig(
            name="test-queue",
            port=5555,
            requirements={"gpu": True}
        )
        
        config_dict = config.to_dict()
        self.assertEqual(config_dict["name"], "test-queue")
        self.assertEqual(config_dict["port"], 5555)
        
        new_config = QueueConfig.from_dict(config_dict)
        self.assertEqual(new_config.name, config.name)
        self.assertEqual(new_config.port, config.port)
        self.assertEqual(new_config.requirements, config.requirements)


if __name__ == '__main__':
    unittest.main()