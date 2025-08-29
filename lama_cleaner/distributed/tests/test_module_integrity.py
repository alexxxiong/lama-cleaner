"""
分布式模块完整性和边界条件测试

测试模块的完整性、依赖关系、错误处理等边界情况
"""

import unittest
import sys
import os
from pathlib import Path
from unittest.mock import patch, MagicMock

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))


class TestModuleIntegrity(unittest.TestCase):
    """测试模块完整性"""
    
    def test_all_required_modules_exist(self):
        """测试所有必需的模块文件都存在"""
        distributed_dir = Path(__file__).parent.parent
        
        required_files = [
            '__init__.py',
            'models.py',
            'config.py',
            'task_manager.py',
            'queue_manager.py',
            'node_manager.py',
            'state_manager.py',
            'utils.py'
        ]
        
        for file_name in required_files:
            file_path = distributed_dir / file_name
            self.assertTrue(file_path.exists(), f"Required file missing: {file_name}")
    
    def test_module_dependencies(self):
        """测试模块依赖关系"""
        try:
            # 测试基础模型可以独立导入
            from lama_cleaner.distributed.models import Task, TaskType
            
            # 测试配置模块可以独立导入
            from lama_cleaner.distributed.config import DistributedConfig
            
            # 测试工具模块可以独立导入
            from lama_cleaner.distributed.utils import detect_cpu_info
            
            # 测试管理器模块（可能有依赖）
            from lama_cleaner.distributed.task_manager import TaskManager
            from lama_cleaner.distributed.queue_manager import QueueManager
            
        except ImportError as e:
            self.fail(f"Module dependency test failed: {e}")
    
    def test_circular_import_prevention(self):
        """测试防止循环导入"""
        # 多次导入同一模块应该返回相同对象
        try:
            import lama_cleaner.distributed.models as models1
            import lama_cleaner.distributed.models as models2
            
            self.assertIs(models1, models2)
            
            # 测试不同导入方式
            from lama_cleaner.distributed import models as models3
            self.assertIs(models1, models3)
            
        except Exception as e:
            self.fail(f"Circular import test failed: {e}")


class TestErrorHandling(unittest.TestCase):
    """测试错误处理"""
    
    def test_invalid_task_creation(self):
        """测试无效任务创建的错误处理"""
        from lama_cleaner.distributed.models import Task, TaskType
        
        # 测试无效的任务类型
        with self.assertRaises(ValueError):
            Task.from_dict({'task_type': 'nonexistent_type'})
        
        # 测试缺少必需字段的情况
        task_dict = {'task_id': 'test-123'}
        # 应该使用默认值而不是抛出错误
        task = Task.from_dict(task_dict)
        self.assertEqual(task.task_id, 'test-123')
    
    def test_invalid_node_capability(self):
        """测试无效节点能力的错误处理"""
        from lama_cleaner.distributed.models import NodeCapability, NodeType
        
        # 测试负数 GPU 内存
        capability = NodeCapability(gpu_memory=-1)
        self.assertFalse(capability.has_gpu())
        
        # 测试无效节点类型
        with self.assertRaises(ValueError):
            NodeCapability.from_dict({'node_type': 'invalid_type'})
    
    def test_config_validation_errors(self):
        """测试配置验证错误"""
        from lama_cleaner.distributed.config import ConfigManager, DistributedConfig
        
        config_manager = ConfigManager()
        
        # 测试无效端口配置
        invalid_config = DistributedConfig()
        invalid_config.scheduler_port = 99999  # 超出有效范围
        
        errors = config_manager.validate_config(invalid_config)
        self.assertGreater(len(errors), 0)
        
        # 测试端口冲突
        invalid_config.scheduler_port = 8080
        for queue_config in invalid_config.queues.values():
            queue_config.port = 8080  # 设置相同端口
            break
        
        errors = config_manager.validate_config(invalid_config)
        self.assertGreater(len(errors), 0)


class TestBoundaryConditions(unittest.TestCase):
    """测试边界条件"""
    
    def test_empty_configurations(self):
        """测试空配置的处理"""
        from lama_cleaner.distributed.models import Task, TaskType
        
        # 测试空配置字典
        task = Task(task_type=TaskType.INPAINT, config={})
        self.assertIsInstance(task.config, dict)
        self.assertEqual(len(task.config), 0)
        
        # 测试 None 配置
        task = Task(task_type=TaskType.INPAINT, config=None)
        # 应该转换为空字典
        self.assertIsInstance(task.config, dict)
    
    def test_large_data_handling(self):
        """测试大数据处理"""
        from lama_cleaner.distributed.models import Task, TaskType
        
        # 测试大配置字典
        large_config = {f"key_{i}": f"value_{i}" for i in range(1000)}
        task = Task(task_type=TaskType.INPAINT, config=large_config)
        
        # 测试序列化和反序列化
        task_dict = task.to_dict()
        restored_task = Task.from_dict(task_dict)
        
        self.assertEqual(len(restored_task.config), 1000)
        self.assertEqual(restored_task.config["key_500"], "value_500")
    
    def test_unicode_handling(self):
        """测试 Unicode 字符处理"""
        from lama_cleaner.distributed.models import Task, TaskType
        
        # 测试包含中文的配置
        unicode_config = {
            "模型": "lama",
            "描述": "这是一个测试任务",
            "路径": "/测试/图像.jpg"
        }
        
        task = Task(task_type=TaskType.INPAINT, config=unicode_config)
        
        # 测试 JSON 序列化
        json_str = task.to_json()
        restored_task = Task.from_json(json_str)
        
        self.assertEqual(restored_task.config["模型"], "lama")
        self.assertEqual(restored_task.config["描述"], "这是一个测试任务")


class TestPerformance(unittest.TestCase):
    """测试性能相关的边界条件"""
    
    def test_task_creation_performance(self):
        """测试任务创建性能"""
        import time
        from lama_cleaner.distributed.models import Task, TaskType
        
        start_time = time.time()
        
        # 创建大量任务
        tasks = []
        for i in range(1000):
            task = Task(
                task_type=TaskType.INPAINT,
                image_path=f"/test/image_{i}.jpg",
                config={"model": "lama", "index": i}
            )
            tasks.append(task)
        
        end_time = time.time()
        creation_time = end_time - start_time
        
        # 创建1000个任务应该在合理时间内完成（小于1秒）
        self.assertLess(creation_time, 1.0, f"Task creation too slow: {creation_time:.2f}s")
        
        # 验证所有任务都有唯一ID
        task_ids = [task.task_id for task in tasks]
        unique_ids = set(task_ids)
        self.assertEqual(len(unique_ids), len(tasks), "Task IDs are not unique")
    
    def test_serialization_performance(self):
        """测试序列化性能"""
        import time
        from lama_cleaner.distributed.models import Task, TaskType
        
        # 创建复杂任务
        complex_config = {
            "model": "sd15",
            "parameters": {f"param_{i}": i for i in range(100)},
            "metadata": {"description": "复杂任务测试" * 100}
        }
        
        task = Task(task_type=TaskType.INPAINT, config=complex_config)
        
        # 测试序列化性能
        start_time = time.time()
        for _ in range(100):
            json_str = task.to_json()
            Task.from_json(json_str)
        end_time = time.time()
        
        serialization_time = end_time - start_time
        
        # 100次序列化/反序列化应该在合理时间内完成
        self.assertLess(serialization_time, 1.0, f"Serialization too slow: {serialization_time:.2f}s")


class TestMockDependencies(unittest.TestCase):
    """测试模拟依赖的情况"""
    
    @patch('lama_cleaner.distributed.utils.psutil')
    def test_system_info_with_mock_psutil(self, mock_psutil):
        """测试在模拟 psutil 的情况下获取系统信息"""
        # 设置模拟返回值
        mock_psutil.cpu_count.return_value = 8
        mock_psutil.virtual_memory.return_value = MagicMock(
            total=16 * 1024 * 1024 * 1024,  # 16GB
            available=8 * 1024 * 1024 * 1024  # 8GB
        )
        
        from lama_cleaner.distributed.utils import detect_cpu_info, detect_memory_info
        
        cpu_info = detect_cpu_info()
        memory_info = detect_memory_info()
        
        self.assertEqual(cpu_info['cores'], 8)
        self.assertGreater(memory_info['total'], 0)
    
    @patch('lama_cleaner.distributed.utils.subprocess.run')
    def test_gpu_detection_with_mock_nvidia_smi(self, mock_run):
        """测试在模拟 nvidia-smi 的情况下检测 GPU"""
        # 模拟 nvidia-smi 输出
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "Tesla V100, 32510\nRTX 4090, 24564"
        mock_run.return_value = mock_result
        
        from lama_cleaner.distributed.utils import detect_gpu_info
        
        gpu_info = detect_gpu_info()
        
        self.assertEqual(gpu_info['count'], 2)
        self.assertGreater(gpu_info['memory'], 0)
        self.assertTrue(gpu_info['available'])


if __name__ == '__main__':
    unittest.main()