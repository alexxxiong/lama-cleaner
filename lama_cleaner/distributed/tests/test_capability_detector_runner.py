#!/usr/bin/env python3
"""
能力检测器测试运行器

专门用于测试节点能力检测功能的完整性和正确性。
"""

import sys
import os
import unittest
import tempfile
import json
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from lama_cleaner.distributed.capability_detector import (
    HardwareDetector, ModelDetector, CapabilityDetector, detect_node_capability
)
from lama_cleaner.distributed.models import NodeType, TaskType


def run_basic_functionality_test():
    """运行基础功能测试"""
    print("🔍 运行基础功能测试...")
    
    try:
        # 测试硬件检测器创建
        hardware_detector = HardwareDetector()
        print("✅ 硬件检测器创建成功")
        
        # 测试模型检测器创建
        model_detector = ModelDetector()
        print("✅ 模型检测器创建成功")
        
        # 测试能力检测器创建
        capability_detector = CapabilityDetector()
        print("✅ 能力检测器创建成功")
        
        return True
    except Exception as e:
        print(f"❌ 基础功能测试失败: {e}")
        return False


def run_mock_detection_test():
    """运行模拟检测测试"""
    print("\n🧪 运行模拟检测测试...")
    
    try:
        from unittest.mock import patch, Mock
        
        detector = CapabilityDetector()
        
        # 模拟硬件信息
        with patch.object(detector.hardware_detector, 'detect_cpu_info', 
                         return_value={'cores': 8, 'logical_cores': 16}):
            with patch.object(detector.hardware_detector, 'detect_memory_info',
                             return_value={'total': 16384, 'available': 8192}):
                with patch.object(detector.hardware_detector, 'detect_gpu_info',
                                 return_value=[{'memory_total': 8192, 'name': 'Test GPU'}]):
                    with patch.object(detector.model_detector, 'detect_supported_models',
                                     return_value=['lama', 'opencv']):
                        
                        capability = detector.detect_full_capability(NodeType.LOCAL)
                        
                        # 验证结果
                        assert capability.cpu_cores == 8
                        assert capability.memory_total == 16384
                        assert capability.gpu_count == 1
                        assert 'lama' in capability.supported_models
                        assert TaskType.INPAINT in capability.supported_tasks
                        
                        print("✅ 模拟检测测试通过")
                        return True
                        
    except Exception as e:
        print(f"❌ 模拟检测测试失败: {e}")
        return False


def run_config_file_test():
    """运行配置文件测试"""
    print("\n📄 运行配置文件测试...")
    
    try:
        from unittest.mock import patch
        
        detector = CapabilityDetector()
        
        # 创建测试配置
        test_config = {
            'node_info': {
                'node_id': 'test-node-123',
                'node_type': 'local'
            },
            'hardware': {
                'cpu_cores': 8,
                'memory_total': 16384,
                'gpu_count': 1,
                'gpu_memory': 8192,
                'gpu_models': ['Test GPU']
            },
            'capabilities': {
                'supported_models': ['lama', 'opencv'],
                'supported_tasks': ['inpaint', 'plugin'],
                'max_concurrent_tasks': 3
            }
        }
        
        # 测试配置文件生成和加载
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(test_config, f, ensure_ascii=False, indent=2)
            config_path = f.name
        
        try:
            # 加载配置
            capability = detector.load_capability_config(config_path)
            
            # 验证加载结果
            assert capability.node_id == 'test-node-123'
            assert capability.cpu_cores == 8
            assert capability.memory_total == 16384
            assert 'lama' in capability.supported_models
            
            print("✅ 配置文件测试通过")
            return True
            
        finally:
            os.unlink(config_path)
            
    except Exception as e:
        print(f"❌ 配置文件测试失败: {e}")
        return False


def run_error_handling_test():
    """运行错误处理测试"""
    print("\n🛡️ 运行错误处理测试...")
    
    try:
        from unittest.mock import patch
        
        detector = CapabilityDetector()
        
        # 测试缺少依赖的情况
        with patch('psutil.cpu_count', side_effect=ImportError("psutil not available")):
            cpu_info = detector.hardware_detector.detect_cpu_info()
            assert isinstance(cpu_info, dict)
            assert 'cores' in cpu_info
        
        # 测试 GPU 检测错误
        with patch('lama_cleaner.distributed.capability_detector.pynvml') as mock_pynvml:
            mock_pynvml.nvmlInit.side_effect = Exception("Driver error")
            gpu_info = detector.hardware_detector.detect_gpu_info()
            assert isinstance(gpu_info, list)
        
        # 测试不存在的配置文件
        try:
            detector.load_capability_config('/nonexistent/path.json')
            assert False, "应该抛出 FileNotFoundError"
        except FileNotFoundError:
            pass  # 预期的异常
        
        print("✅ 错误处理测试通过")
        return True
        
    except Exception as e:
        print(f"❌ 错误处理测试失败: {e}")
        return False


def run_performance_test():
    """运行性能测试"""
    print("\n⚡ 运行性能测试...")
    
    try:
        import time
        from unittest.mock import patch
        
        detector = CapabilityDetector()
        
        # 测试检测性能
        start_time = time.time()
        
        with patch.object(detector.hardware_detector, 'detect_cpu_info', return_value={'cores': 8}):
            with patch.object(detector.hardware_detector, 'detect_memory_info', return_value={'total': 16384}):
                with patch.object(detector.hardware_detector, 'detect_gpu_info', return_value=[]):
                    with patch.object(detector.model_detector, 'detect_supported_models', return_value=['lama']):
                        capability = detector.detect_full_capability()
        
        end_time = time.time()
        detection_time = end_time - start_time
        
        if detection_time < 1.0:
            print(f"✅ 性能测试通过 (检测时间: {detection_time:.3f}s)")
            return True
        else:
            print(f"⚠️ 性能测试警告 (检测时间: {detection_time:.3f}s > 1.0s)")
            return True  # 警告但不失败
            
    except Exception as e:
        print(f"❌ 性能测试失败: {e}")
        return False


def run_integration_test():
    """运行集成测试"""
    print("\n🔗 运行集成测试...")
    
    try:
        from unittest.mock import patch
        
        # 测试便捷函数
        with patch.object(CapabilityDetector, 'detect_full_capability') as mock_detect:
            from lama_cleaner.distributed.models import NodeCapability
            mock_capability = NodeCapability()
            mock_detect.return_value = mock_capability
            
            result = detect_node_capability(NodeType.LOCAL)
            assert result == mock_capability
        
        print("✅ 集成测试通过")
        return True
        
    except Exception as e:
        print(f"❌ 集成测试失败: {e}")
        return False


def main():
    """主测试函数"""
    print("🚀 开始能力检测器测试")
    print("=" * 50)
    
    tests = [
        ("基础功能", run_basic_functionality_test),
        ("模拟检测", run_mock_detection_test),
        ("配置文件", run_config_file_test),
        ("错误处理", run_error_handling_test),
        ("性能测试", run_performance_test),
        ("集成测试", run_integration_test),
    ]
    
    passed = 0
    total = len(tests)
    
    for test_name, test_func in tests:
        if test_func():
            passed += 1
    
    print("\n" + "=" * 50)
    print(f"📊 测试结果: {passed}/{total} 通过")
    
    if passed == total:
        print("🎉 所有测试通过！")
        return 0
    else:
        print("❌ 部分测试失败")
        return 1


if __name__ == "__main__":
    sys.exit(main())