"""
任务路由逻辑测试

专门测试任务路由算法，包括需求分析、队列匹配、负载均衡等功能。
"""

import pytest
from unittest.mock import Mock, patch
from datetime import datetime

from lama_cleaner.distributed.queue_manager import QueueManager
from lama_cleaner.distributed.models import Task, TaskType, TaskPriority, QueueConfig
from lama_cleaner.distributed.config import DistributedConfig, ZeroMQConfig


class TestTaskRequirementAnalysis:
    """任务需求分析测试"""
    
    @pytest.fixture
    def queue_manager(self):
        """创建队列管理器实例"""
        config = DistributedConfig()
        with patch('lama_cleaner.distributed.queue_manager.get_config', return_value=config):
            return QueueManager()
    
    def test_analyze_lama_gpu_requirements(self, queue_manager):
        """测试 LaMa GPU 模型需求分析"""
        task = Task(
            task_type=TaskType.INPAINT,
            config={
                "model": "lama",
                "device": "cuda"
            }
        )
        
        requirements = queue_manager._analyze_task_requirements(task)
        
        assert requirements['gpu'] is True
        assert requirements['gpu_memory'] == 2048
        assert 'lama' in requirements['models']
    
    def test_analyze_lama_cpu_requirements(self, queue_manager):
        """测试 LaMa CPU 模型需求分析"""
        task = Task(
            task_type=TaskType.INPAINT,
            config={
                "model": "lama",
                "device": "cpu"
            }
        )
        
        requirements = queue_manager._analyze_task_requirements(task)
        
        assert requirements.get('gpu', False) is False
        assert requirements['cpu_cores'] == 2
        assert requirements['memory'] == 4096
        assert 'lama' in requirements['models']
    
    def test_analyze_stable_diffusion_requirements(self, queue_manager):
        """测试 Stable Diffusion 模型需求分析"""
        test_cases = [
            ("sd15", 4096),
            ("sd21", 4096),
            ("sdxl", 8192)
        ]
        
        for model, expected_memory in test_cases:
            task = Task(
                task_type=TaskType.INPAINT,
                config={
                    "model": model,
                    "device": "cuda"
                }
            )
            
            requirements = queue_manager._analyze_task_requirements(task)
            
            assert requirements['gpu'] is True
            assert requirements['gpu_memory'] == expected_memory
            assert model in requirements['models']
    
    def test_analyze_mat_requirements(self, queue_manager):
        """测试 MAT 模型需求分析"""
        # GPU 版本
        task_gpu = Task(
            task_type=TaskType.INPAINT,
            config={
                "model": "mat",
                "device": "cuda"
            }
        )
        
        requirements_gpu = queue_manager._analyze_task_requirements(task_gpu)
        assert requirements_gpu['gpu'] is True
        assert requirements_gpu['gpu_memory'] == 2048
        
        # CPU 版本
        task_cpu = Task(
            task_type=TaskType.INPAINT,
            config={
                "model": "mat",
                "device": "cpu"
            }
        )
        
        requirements_cpu = queue_manager._analyze_task_requirements(task_cpu)
        assert requirements_cpu.get('gpu', False) is False
        assert requirements_cpu['cpu_cores'] == 4
        assert requirements_cpu['memory'] == 8192
    
    def test_analyze_zits_requirements(self, queue_manager):
        """测试 ZITS 模型需求分析"""
        task = Task(
            task_type=TaskType.INPAINT,
            config={
                "model": "zits",
                "device": "cpu"
            }
        )
        
        requirements = queue_manager._analyze_task_requirements(task)
        
        assert requirements.get('gpu', False) is False
        assert requirements['cpu_cores'] == 4
        assert requirements['memory'] == 8192
    
    def test_analyze_opencv_requirements(self, queue_manager):
        """测试 OpenCV 模型需求分析"""
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
    
    def test_analyze_plugin_requirements(self, queue_manager):
        """测试插件任务需求分析"""
        # GPU 插件
        gpu_plugins = ["realesrgan", "gfpgan"]
        for plugin in gpu_plugins:
            task = Task(
                task_type=TaskType.PLUGIN,
                config={"name": plugin}
            )
            
            requirements = queue_manager._analyze_task_requirements(task)
            assert requirements['gpu'] is True
            assert requirements['gpu_memory'] == 2048
        
        # CPU 插件
        cpu_plugins = ["remove_bg", "anime_seg"]
        for plugin in cpu_plugins:
            task = Task(
                task_type=TaskType.PLUGIN,
                config={"name": plugin}
            )
            
            requirements = queue_manager._analyze_task_requirements(task)
            assert requirements.get('gpu', False) is False
            assert requirements['cpu_cores'] == 2
            assert requirements['memory'] == 4096
    
    def test_analyze_priority_boost(self, queue_manager):
        """测试优先级提升需求"""
        task = Task(
            task_type=TaskType.INPAINT,
            priority=TaskPriority.URGENT,
            config={
                "model": "lama",
                "device": "cpu"
            }
        )
        
        requirements = queue_manager._analyze_task_requirements(task)
        
        assert requirements.get('priority_boost', False) is True
    
    def test_analyze_unknown_model(self, queue_manager):
        """测试未知模型的需求分析"""
        task = Task(
            task_type=TaskType.INPAINT,
            config={
                "model": "unknown_model",
                "device": "cpu"
            }
        )
        
        requirements = queue_manager._analyze_task_requirements(task)
        
        # 应该有基本的默认需求
        assert 'models' in requirements


class TestQueueMatching:
    """队列匹配测试"""
    
    @pytest.fixture
    def queue_manager(self):
        """创建队列管理器实例"""
        config = DistributedConfig()
        with patch('lama_cleaner.distributed.queue_manager.get_config', return_value=config):
            return QueueManager()
    
    def test_gpu_queue_matching(self, queue_manager):
        """测试 GPU 队列匹配"""
        # 高端 GPU 队列
        gpu_high_config = QueueConfig(
            name="gpu-high",
            port=5555,
            requirements={
                "gpu": True,
                "gpu_memory": 8192,
                "models": ["sd15", "sd21", "sdxl", "lama"]
            }
        )
        
        # 匹配的需求
        requirements = {
            "gpu": True,
            "gpu_memory": 4096,
            "models": ["sd15"]
        }
        assert queue_manager._queue_matches_requirements(gpu_high_config, requirements)
        
        # 内存需求过高
        requirements = {
            "gpu": True,
            "gpu_memory": 16384,
            "models": ["sd15"]
        }
        assert not queue_manager._queue_matches_requirements(gpu_high_config, requirements)
        
        # 模型不支持
        requirements = {
            "gpu": True,
            "gpu_memory": 4096,
            "models": ["unsupported_model"]
        }
        assert not queue_manager._queue_matches_requirements(gpu_high_config, requirements)
    
    def test_cpu_queue_matching(self, queue_manager):
        """测试 CPU 队列匹配"""
        cpu_config = QueueConfig(
            name="cpu-intensive",
            port=5558,
            requirements={
                "cpu_cores": 8,
                "memory": 16384,
                "models": ["opencv", "zits"]
            }
        )
        
        # 匹配的需求
        requirements = {
            "gpu": False,
            "cpu_cores": 4,
            "memory": 8192,
            "models": ["opencv"]
        }
        assert queue_manager._queue_matches_requirements(cpu_config, requirements)
        
        # CPU 核心数不足
        requirements = {
            "gpu": False,
            "cpu_cores": 16,
            "memory": 8192,
            "models": ["opencv"]
        }
        assert not queue_manager._queue_matches_requirements(cpu_config, requirements)
        
        # 内存不足
        requirements = {
            "gpu": False,
            "cpu_cores": 4,
            "memory": 32768,
            "models": ["opencv"]
        }
        assert not queue_manager._queue_matches_requirements(cpu_config, requirements)
    
    def test_mixed_requirements_matching(self, queue_manager):
        """测试混合需求匹配"""
        queue_config = QueueConfig(
            name="mixed-queue",
            port=5559,
            requirements={
                "gpu": True,
                "gpu_memory": 4096,
                "cpu_cores": 4,
                "memory": 8192,
                "models": ["lama", "mat"]
            }
        )
        
        # GPU 任务匹配
        gpu_requirements = {
            "gpu": True,
            "gpu_memory": 2048,
            "models": ["lama"]
        }
        assert queue_manager._queue_matches_requirements(queue_config, gpu_requirements)
        
        # CPU 任务不匹配（队列要求 GPU）
        cpu_requirements = {
            "gpu": False,
            "cpu_cores": 2,
            "memory": 4096,
            "models": ["lama"]
        }
        assert not queue_manager._queue_matches_requirements(queue_config, cpu_requirements)
    
    def test_empty_model_requirements(self, queue_manager):
        """测试空模型需求匹配"""
        queue_config = QueueConfig(
            name="test-queue",
            port=5560,
            requirements={
                "gpu": True,
                "gpu_memory": 4096,
                "models": ["lama"]
            }
        )
        
        # 空模型需求应该匹配
        requirements = {
            "gpu": True,
            "gpu_memory": 2048,
            "models": []
        }
        assert queue_manager._queue_matches_requirements(queue_config, requirements)
        
        # 队列没有模型要求也应该匹配
        queue_config.requirements.pop("models")
        requirements = {
            "gpu": True,
            "gpu_memory": 2048,
            "models": ["any_model"]
        }
        assert queue_manager._queue_matches_requirements(queue_config, requirements)
        
        # 队列和任务都没有模型要求也应该匹配
        requirements = {
            "gpu": True,
            "gpu_memory": 2048,
            "models": []
        }
        assert queue_manager._queue_matches_requirements(queue_config, requirements)


class TestLoadBalancing:
    """负载均衡测试"""
    
    @pytest.fixture
    def queue_manager(self):
        """创建队列管理器实例"""
        config = DistributedConfig()
        config.queues = {
            "gpu-1": QueueConfig(
                name="gpu-1",
                port=5555,
                requirements={
                    "gpu": True,
                    "gpu_memory": 4096,
                    "models": ["lama"]
                }
            ),
            "gpu-2": QueueConfig(
                name="gpu-2",
                port=5556,
                requirements={
                    "gpu": True,
                    "gpu_memory": 4096,
                    "models": ["lama"]
                }
            ),
            "gpu-3": QueueConfig(
                name="gpu-3",
                port=5557,
                requirements={
                    "gpu": True,
                    "gpu_memory": 4096,
                    "models": ["lama"]
                }
            )
        }
        
        with patch('lama_cleaner.distributed.queue_manager.get_config', return_value=config):
            return QueueManager()
    
    def test_select_least_loaded_queue(self, queue_manager):
        """测试选择负载最轻的队列"""
        # 设置不同的负载
        queue_manager.queue_stats = {
            "gpu-1": {"pending_count": 10},
            "gpu-2": {"pending_count": 3},
            "gpu-3": {"pending_count": 7}
        }
        
        task = Task(
            task_type=TaskType.INPAINT,
            config={
                "model": "lama",
                "device": "cuda"
            }
        )
        
        selected_queue = queue_manager.route_task(task)
        
        # 应该选择 gpu-2（负载最轻）
        assert selected_queue == "gpu-2"
    
    def test_load_balancing_with_equal_load(self, queue_manager):
        """测试相等负载时的选择"""
        # 设置相等的负载
        queue_manager.queue_stats = {
            "gpu-1": {"pending_count": 5},
            "gpu-2": {"pending_count": 5},
            "gpu-3": {"pending_count": 5}
        }
        
        task = Task(
            task_type=TaskType.INPAINT,
            config={
                "model": "lama",
                "device": "cuda"
            }
        )
        
        selected_queue = queue_manager.route_task(task)
        
        # 应该选择其中一个队列
        assert selected_queue in ["gpu-1", "gpu-2", "gpu-3"]
    
    def test_load_balancing_with_zero_load(self, queue_manager):
        """测试零负载时的选择"""
        # 设置零负载
        queue_manager.queue_stats = {
            "gpu-1": {"pending_count": 0},
            "gpu-2": {"pending_count": 0},
            "gpu-3": {"pending_count": 0}
        }
        
        task = Task(
            task_type=TaskType.INPAINT,
            config={
                "model": "lama",
                "device": "cuda"
            }
        )
        
        selected_queue = queue_manager.route_task(task)
        
        # 应该选择其中一个队列
        assert selected_queue in ["gpu-1", "gpu-2", "gpu-3"]
    
    def test_load_balancing_excludes_unsuitable_queues(self, queue_manager):
        """测试负载均衡排除不合适的队列"""
        # 添加一个不合适的队列
        queue_manager.config.queues["cpu-only"] = QueueConfig(
            name="cpu-only",
            port=5558,
            requirements={
                "gpu": False,
                "cpu_cores": 4,
                "models": ["opencv"]
            }
        )
        
        # 设置负载（CPU 队列负载最轻）
        queue_manager.queue_stats = {
            "gpu-1": {"pending_count": 10},
            "gpu-2": {"pending_count": 8},
            "gpu-3": {"pending_count": 12},
            "cpu-only": {"pending_count": 1}  # 最轻负载
        }
        
        task = Task(
            task_type=TaskType.INPAINT,
            config={
                "model": "lama",
                "device": "cuda"  # 需要 GPU
            }
        )
        
        selected_queue = queue_manager.route_task(task)
        
        # 应该选择 GPU 队列中负载最轻的，而不是 CPU 队列
        assert selected_queue == "gpu-2"
        assert selected_queue != "cpu-only"


class TestTaskRoutingIntegration:
    """任务路由集成测试"""
    
    @pytest.fixture
    def queue_manager(self):
        """创建完整的队列管理器"""
        config = DistributedConfig()
        # 使用默认的队列配置
        with patch('lama_cleaner.distributed.queue_manager.get_config', return_value=config):
            return QueueManager()
    
    def test_route_various_task_types(self, queue_manager):
        """测试路由各种类型的任务"""
        # 设置队列统计
        queue_manager.queue_stats = {
            queue_name: {"pending_count": 0}
            for queue_name in queue_manager.config.queues.keys()
        }
        
        test_cases = [
            # (任务配置, 期望的队列类型)
            ({"model": "sdxl", "device": "cuda"}, "gpu"),  # sdxl 需要 8GB，会匹配 gpu 队列
            ({"model": "sd15", "device": "cuda"}, "gpu"),  # sd15 需要 4GB，会匹配 gpu 队列
            ({"model": "lama", "device": "cuda"}, "gpu"),  # lama GPU 会匹配 gpu 队列
            ({"model": "lama", "device": "cpu"}, "cpu"),   # lama CPU 会匹配 cpu 队列
            ({"model": "opencv", "device": "cpu"}, "cpu"), # opencv 会匹配 cpu 队列
            ({"model": "zits", "device": "cpu"}, "cpu"),   # zits 会匹配 cpu 队列
        ]
        
        for config, expected_queue_type in test_cases:
            task = Task(
                task_type=TaskType.INPAINT,
                config=config
            )
            
            selected_queue = queue_manager.route_task(task)
            
            assert selected_queue is not None, f"No queue found for config: {config}"
            assert expected_queue_type in selected_queue, \
                f"Expected {expected_queue_type} queue for {config}, got {selected_queue}"
    
    def test_route_plugin_tasks(self, queue_manager):
        """测试路由插件任务"""
        # 设置队列统计
        queue_manager.queue_stats = {
            queue_name: {"pending_count": 0}
            for queue_name in queue_manager.config.queues.keys()
        }
        
        plugin_test_cases = [
            # (插件名称, 期望的队列类型)
            ("realesrgan", "gpu"),
            ("gfpgan", "gpu"),
            ("remove_bg", "cpu"),
            ("anime_seg", "cpu"),
        ]
        
        for plugin_name, expected_queue_type in plugin_test_cases:
            task = Task(
                task_type=TaskType.PLUGIN,
                config={"name": plugin_name}
            )
            
            selected_queue = queue_manager.route_task(task)
            
            assert selected_queue is not None, f"No queue found for plugin: {plugin_name}"
            assert expected_queue_type in selected_queue, \
                f"Expected {expected_queue_type} queue for {plugin_name}, got {selected_queue}"
    
    def test_route_with_priority(self, queue_manager):
        """测试优先级任务路由"""
        # 设置队列统计
        queue_manager.queue_stats = {
            queue_name: {"pending_count": 0}
            for queue_name in queue_manager.config.queues.keys()
        }
        
        # 普通优先级任务
        normal_task = Task(
            task_type=TaskType.INPAINT,
            priority=TaskPriority.NORMAL,
            config={"model": "lama", "device": "cuda"}
        )
        
        # 紧急优先级任务
        urgent_task = Task(
            task_type=TaskType.INPAINT,
            priority=TaskPriority.URGENT,
            config={"model": "lama", "device": "cuda"}
        )
        
        normal_queue = queue_manager.route_task(normal_task)
        urgent_queue = queue_manager.route_task(urgent_task)
        
        # 两个任务都应该能找到队列
        assert normal_queue is not None
        assert urgent_queue is not None
        
        # 紧急任务的需求分析应该包含优先级提升
        urgent_requirements = queue_manager._analyze_task_requirements(urgent_task)
        assert urgent_requirements.get('priority_boost', False) is True
    
    def test_route_with_no_suitable_queue(self, queue_manager):
        """测试没有合适队列的情况"""
        # 创建一个需求极高的任务
        task = Task(
            task_type=TaskType.INPAINT,
            config={
                "model": "hypothetical_huge_model",
                "device": "cuda",
                "min_gpu_memory": 64000  # 64GB GPU 内存
            }
        )
        
        selected_queue = queue_manager.route_task(task)
        
        # 应该返回 None
        assert selected_queue is None
    
    def test_route_task_end_to_end(self, queue_manager):
        """测试端到端的任务路由"""
        # 模拟真实的队列设置
        mock_socket = Mock()
        
        with patch.object(queue_manager.context, 'socket', return_value=mock_socket):
            # 设置队列
            queue_manager._setup_queues()
            
            # 创建任务
            task = Task(
                task_type=TaskType.INPAINT,
                config={
                    "model": "lama",
                    "device": "cuda"
                }
            )
            
            # 路由任务
            selected_queue = queue_manager.route_task(task)
            assert selected_queue is not None
            
            # 发送任务
            result = queue_manager.send_task(selected_queue, task)
            assert result is True
            
            # 验证任务被发送
            mock_socket.send_multipart.assert_called_once()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])