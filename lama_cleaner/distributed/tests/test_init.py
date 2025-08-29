"""
测试分布式模块的基础初始化
"""

import unittest
import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))


class TestDistributedInit(unittest.TestCase):
    """测试分布式模块初始化"""
    
    def test_import_distributed_module(self):
        """测试导入分布式模块"""
        try:
            import lama_cleaner.distributed
            self.assertTrue(hasattr(lama_cleaner.distributed, '__version__'))
        except ImportError as e:
            self.fail(f"Failed to import distributed module: {e}")
    
    def test_import_models(self):
        """测试导入数据模型"""
        try:
            from lama_cleaner.distributed.models import (
                Task, TaskType, TaskStatus, TaskPriority,
                NodeCapability, NodeType, NodeStatus,
                QueueConfig
            )
            
            # 验证枚举类型
            self.assertTrue(hasattr(TaskType, 'INPAINT'))
            self.assertTrue(hasattr(TaskStatus, 'PENDING'))
            self.assertTrue(hasattr(TaskPriority, 'NORMAL'))
            self.assertTrue(hasattr(NodeType, 'LOCAL'))
            self.assertTrue(hasattr(NodeStatus, 'ONLINE'))
            
        except ImportError as e:
            self.fail(f"Failed to import models: {e}")
    
    def test_import_config(self):
        """测试导入配置管理"""
        try:
            from lama_cleaner.distributed.config import (
                DistributedConfig, ConfigManager, get_config
            )
            
            # 测试获取默认配置
            config = get_config()
            self.assertIsInstance(config, DistributedConfig)
            
        except ImportError as e:
            self.fail(f"Failed to import config: {e}")
    
    def test_import_managers(self):
        """测试导入管理器类"""
        try:
            from lama_cleaner.distributed.task_manager import TaskManager
            from lama_cleaner.distributed.queue_manager import QueueManager
            from lama_cleaner.distributed.node_manager import NodeManager
            from lama_cleaner.distributed.state_manager import StateManager
            
            # 验证类可以实例化
            task_manager = TaskManager()
            self.assertIsInstance(task_manager, TaskManager)
            
        except ImportError as e:
            self.fail(f"Failed to import managers: {e}")
    
    def test_import_utils(self):
        """测试导入工具函数"""
        try:
            from lama_cleaner.distributed.utils import (
                detect_gpu_info, detect_cpu_info, detect_memory_info,
                get_system_info, validate_image_file
            )
            
            # 测试系统信息检测
            system_info = get_system_info()
            self.assertIsInstance(system_info, dict)
            self.assertIn('platform', system_info)
            self.assertIn('cpu', system_info)
            self.assertIn('memory', system_info)
            
        except ImportError as e:
            self.fail(f"Failed to import utils: {e}")
    
    def test_basic_functionality(self):
        """测试基础功能"""
        try:
            from lama_cleaner.distributed.models import Task, TaskType
            from lama_cleaner.distributed.config import get_config
            
            # 创建一个简单的任务
            task = Task(
                task_type=TaskType.INPAINT,
                image_path="/test/image.jpg",
                config={"model": "lama"}
            )
            
            self.assertIsNotNone(task.task_id)
            self.assertEqual(task.task_type, TaskType.INPAINT)
            
            # 测试配置
            config = get_config()
            self.assertFalse(config.enabled)  # 默认应该是禁用的
            
        except Exception as e:
            self.fail(f"Basic functionality test failed: {e}")
    
    def test_module_completeness(self):
        """测试模块完整性"""
        try:
            # 验证所有核心组件都能导入
            from lama_cleaner.distributed.models import (
                Task, TaskType, TaskStatus, TaskPriority,
                NodeCapability, NodeType, NodeStatus,
                QueueConfig, DEFAULT_QUEUE_CONFIGS
            )
            from lama_cleaner.distributed.config import (
                DistributedConfig, ConfigManager, get_config
            )
            from lama_cleaner.distributed.task_manager import TaskManager
            from lama_cleaner.distributed.queue_manager import QueueManager
            from lama_cleaner.distributed.node_manager import NodeManager
            from lama_cleaner.distributed.state_manager import StateManager
            
            # 验证默认队列配置存在
            self.assertIsInstance(DEFAULT_QUEUE_CONFIGS, dict)
            self.assertGreater(len(DEFAULT_QUEUE_CONFIGS), 0)
            
            # 验证配置管理器可以创建
            config_manager = ConfigManager()
            self.assertIsInstance(config_manager, ConfigManager)
            
        except ImportError as e:
            self.fail(f"Module completeness test failed: {e}")
    
    def test_default_configurations(self):
        """测试默认配置的正确性"""
        try:
            from lama_cleaner.distributed.config import get_config
            from lama_cleaner.distributed.models import DEFAULT_QUEUE_CONFIGS
            
            config = get_config()
            
            # 验证基础配置
            self.assertIsInstance(config.enabled, bool)
            self.assertIsInstance(config.scheduler_host, str)
            self.assertIsInstance(config.scheduler_port, int)
            
            # 验证端口范围合理
            self.assertGreaterEqual(config.scheduler_port, 1024)
            self.assertLessEqual(config.scheduler_port, 65535)
            
            # 验证队列配置
            for queue_name, queue_config in DEFAULT_QUEUE_CONFIGS.items():
                self.assertIsInstance(queue_name, str)
                self.assertIsInstance(queue_config.port, int)
                self.assertGreaterEqual(queue_config.port, 1024)
                self.assertLessEqual(queue_config.port, 65535)
                
        except Exception as e:
            self.fail(f"Default configuration test failed: {e}")
    
    def test_data_model_serialization(self):
        """测试数据模型序列化功能"""
        try:
            from lama_cleaner.distributed.models import Task, TaskType, NodeCapability, NodeType
            
            # 测试任务序列化
            task = Task(
                task_type=TaskType.INPAINT,
                image_path="/test/image.jpg",
                config={"model": "lama"}
            )
            
            # 测试转换为字典
            task_dict = task.to_dict()
            self.assertIsInstance(task_dict, dict)
            self.assertIn('task_id', task_dict)
            self.assertIn('task_type', task_dict)
            
            # 测试从字典恢复
            restored_task = Task.from_dict(task_dict)
            self.assertEqual(restored_task.task_id, task.task_id)
            self.assertEqual(restored_task.task_type, task.task_type)
            
            # 测试 JSON 序列化
            json_str = task.to_json()
            self.assertIsInstance(json_str, str)
            
            json_task = Task.from_json(json_str)
            self.assertEqual(json_task.task_id, task.task_id)
            
            # 测试节点能力序列化
            capability = NodeCapability(
                node_type=NodeType.LOCAL,
                gpu_count=1,
                gpu_memory=8192,
                cpu_cores=8
            )
            
            cap_dict = capability.to_dict()
            self.assertIsInstance(cap_dict, dict)
            
            restored_cap = NodeCapability.from_dict(cap_dict)
            self.assertEqual(restored_cap.node_type, capability.node_type)
            self.assertEqual(restored_cap.gpu_count, capability.gpu_count)
            
        except Exception as e:
            self.fail(f"Data model serialization test failed: {e}")
    
    def test_error_handling(self):
        """测试基础错误处理"""
        try:
            from lama_cleaner.distributed.models import Task, TaskType
            
            # 测试无效的任务类型处理
            with self.assertRaises(ValueError):
                Task.from_dict({'task_type': 'invalid_type'})
            
            # 测试空配置处理
            task = Task(task_type=TaskType.INPAINT)
            self.assertIsInstance(task.config, dict)
            self.assertEqual(len(task.config), 0)
            
        except Exception as e:
            self.fail(f"Error handling test failed: {e}")


if __name__ == '__main__':
    unittest.main()