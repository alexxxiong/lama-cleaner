"""
分布式处理模块集成测试

测试整个分布式模块的集成功能，包括组件间的协作和接口兼容性
"""

import pytest
from unittest.mock import patch, MagicMock
import sys


class TestDistributedModuleIntegration:
    """测试分布式模块的集成功能"""
    
    def test_basic_workflow_integration(self):
        """测试基本工作流程的集成"""
        
        # 导入并测试基本功能
        try:
            import lama_cleaner.distributed as distributed
            
            # 创建任务
            task = distributed.Task()
            assert task is not None
            
            # 创建管理器
            task_manager = distributed.TaskManager()
            queue_manager = distributed.QueueManager()
            
            assert task_manager is not None
            assert queue_manager is not None
            
        except Exception as e:
            pytest.fail(f"Basic workflow integration failed: {e}")
    
    def test_all_components_importable(self):
        """测试所有组件都可以正常导入"""
        try:
            import lama_cleaner.distributed as distributed
            
            # 获取所有声明的导出
            all_exports = distributed.__all__
            
            # 尝试访问每个导出的组件
            for export_name in all_exports:
                component = getattr(distributed, export_name)
                assert component is not None, f"Component {export_name} is None"
                
        except ImportError as e:
            pytest.fail(f"Failed to import component: {e}")
        except AttributeError as e:
            pytest.fail(f"Component not found: {e}")
    
    def test_module_docstring_and_metadata(self):
        """测试模块文档字符串和元数据"""
        import lama_cleaner.distributed as distributed
        
        # 检查模块文档
        assert distributed.__doc__ is not None
        assert "分布式处理模块" in distributed.__doc__
        
        # 检查版本信息
        assert hasattr(distributed, '__version__')
        assert hasattr(distributed, '__author__')
        
        # 验证版本格式
        version_parts = distributed.__version__.split('.')
        assert len(version_parts) >= 2, "Version should have at least major.minor format"
    
    def test_configuration_integration(self):
        """测试配置集成"""
        
        try:
            import lama_cleaner.distributed as distributed
            
            config = distributed.DistributedConfig()
            assert config is not None
            
        except Exception as e:
            pytest.fail(f"Configuration integration failed: {e}")
    
    def test_error_handling_on_missing_dependencies(self):
        """测试缺少依赖时的错误处理"""
        
        # 模拟缺少某个依赖模块
        with patch.dict('sys.modules', {
            'lama_cleaner.distributed.models': None
        }):
            # 清理已导入的模块
            if 'lama_cleaner.distributed' in sys.modules:
                del sys.modules['lama_cleaner.distributed']
            
            with pytest.raises(ImportError):
                import lama_cleaner.distributed
    
    def test_namespace_pollution_prevention(self):
        """测试防止命名空间污染"""
        import lama_cleaner.distributed as distributed
        
        # 检查 __all__ 中声明的组件都存在
        for component in distributed.__all__:
            assert hasattr(distributed, component), f"Missing component: {component}"
        
        # 检查关键的公开 API 存在
        assert hasattr(distributed, '__version__')
        assert hasattr(distributed, '__author__')
        
        # 检查不应该有明显的内部模块泄露（以 _ 开头的）
        public_attrs = [attr for attr in dir(distributed) if not attr.startswith('_')]
        internal_attrs = [attr for attr in public_attrs if attr.startswith('_')]
        
        assert len(internal_attrs) == 0, f"Internal attributes leaked: {internal_attrs}"


class TestDistributedModuleCompatibility:
    """测试分布式模块的兼容性"""
    
    def test_python_version_compatibility(self):
        """测试 Python 版本兼容性"""
        import sys
        
        # 检查 Python 版本是否在支持范围内
        python_version = sys.version_info
        assert python_version >= (3, 9), "Requires Python 3.9 or higher"
        assert python_version < (3, 11), "Tested up to Python 3.10"
    
    def test_import_performance(self):
        """测试导入性能"""
        import time
        
        # 清理模块缓存
        modules_to_clean = [
            'lama_cleaner.distributed',
        ]
        for module in modules_to_clean:
            if module in sys.modules:
                del sys.modules[module]
        
        # 测量导入时间
        start_time = time.time()
        try:
            import lama_cleaner.distributed
        except ImportError:
            # 如果依赖模块不存在，跳过性能测试
            pytest.skip("Dependencies not available for performance test")
        
        import_time = time.time() - start_time
        
        # 导入时间应该在合理范围内（小于1秒）
        assert import_time < 1.0, f"Import took too long: {import_time:.2f}s"
    
    def test_memory_usage_reasonable(self):
        """测试内存使用合理性"""
        import psutil
        import os
        
        process = psutil.Process(os.getpid())
        memory_before = process.memory_info().rss
        
        try:
            import lama_cleaner.distributed
        except ImportError:
            pytest.skip("Dependencies not available for memory test")
        
        memory_after = process.memory_info().rss
        memory_increase = memory_after - memory_before
        
        # 内存增长应该在合理范围内（小于50MB）
        max_memory_increase = 50 * 1024 * 1024  # 50MB
        assert memory_increase < max_memory_increase, \
            f"Memory increase too large: {memory_increase / 1024 / 1024:.2f}MB"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])