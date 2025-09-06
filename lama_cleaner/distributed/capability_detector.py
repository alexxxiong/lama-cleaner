"""
节点能力检测模块

负责检测节点的硬件能力（GPU、CPU、内存）和支持的模型，
生成节点能力配置文件。
"""

import os
import sys
import json
import platform
import subprocess
import logging
from typing import Dict, List, Optional, Tuple
from pathlib import Path
import psutil

from .models import NodeCapability, NodeType, TaskType

logger = logging.getLogger(__name__)


class HardwareDetector:
    """硬件能力检测器"""
    
    def __init__(self):
        self.system_info = self._get_system_info()
    
    def _get_system_info(self) -> Dict[str, str]:
        """获取系统基本信息"""
        return {
            'platform': platform.platform(),
            'system': platform.system(),
            'machine': platform.machine(),
            'processor': platform.processor(),
            'python_version': platform.python_version(),
        }
    
    def detect_cpu_info(self) -> Dict[str, any]:
        """检测 CPU 信息"""
        try:
            cpu_info = {
                'cores': psutil.cpu_count(logical=False),  # 物理核心数
                'logical_cores': psutil.cpu_count(logical=True),  # 逻辑核心数
                'frequency': 0,
                'model': '',
                'architecture': platform.machine(),
            }
            
            # 获取 CPU 频率
            try:
                freq_info = psutil.cpu_freq()
                if freq_info:
                    cpu_info['frequency'] = int(freq_info.max) if freq_info.max else 0
            except Exception:
                pass
            
            # 获取 CPU 型号
            try:
                if platform.system() == "Linux":
                    with open('/proc/cpuinfo', 'r') as f:
                        for line in f:
                            if 'model name' in line:
                                cpu_info['model'] = line.split(':')[1].strip()
                                break
                elif platform.system() == "Darwin":  # macOS
                    result = subprocess.run(['sysctl', '-n', 'machdep.cpu.brand_string'], 
                                          capture_output=True, text=True)
                    if result.returncode == 0:
                        cpu_info['model'] = result.stdout.strip()
                elif platform.system() == "Windows":
                    import winreg
                    key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, 
                                       r"HARDWARE\DESCRIPTION\System\CentralProcessor\0")
                    cpu_info['model'] = winreg.QueryValueEx(key, "ProcessorNameString")[0]
                    winreg.CloseKey(key)
            except Exception as e:
                logger.debug(f"获取 CPU 型号失败: {e}")
            
            logger.info(f"检测到 CPU: {cpu_info['cores']}核心, {cpu_info['model']}")
            return cpu_info
            
        except Exception as e:
            logger.error(f"CPU 检测失败: {e}")
            return {
                'cores': 1,
                'logical_cores': 1,
                'frequency': 0,
                'model': 'Unknown',
                'architecture': platform.machine(),
            }
    
    def detect_memory_info(self) -> Dict[str, any]:
        """检测内存信息"""
        try:
            memory = psutil.virtual_memory()
            swap = psutil.swap_memory()
            
            memory_info = {
                'total': int(memory.total / 1024 / 1024),  # MB
                'available': int(memory.available / 1024 / 1024),  # MB
                'used': int(memory.used / 1024 / 1024),  # MB
                'percent': memory.percent,
                'swap_total': int(swap.total / 1024 / 1024),  # MB
                'swap_used': int(swap.used / 1024 / 1024),  # MB
            }
            
            logger.info(f"检测到内存: {memory_info['total']}MB 总量, {memory_info['available']}MB 可用")
            return memory_info
            
        except Exception as e:
            logger.error(f"内存检测失败: {e}")
            return {
                'total': 8192,  # 默认 8GB
                'available': 4096,
                'used': 4096,
                'percent': 50.0,
                'swap_total': 0,
                'swap_used': 0,
            }
    
    def detect_gpu_info(self) -> List[Dict[str, any]]:
        """检测 GPU 信息"""
        gpus = []
        
        # 尝试使用 nvidia-ml-py 检测 NVIDIA GPU
        try:
            import pynvml
            pynvml.nvmlInit()
            device_count = pynvml.nvmlDeviceGetCount()
            
            for i in range(device_count):
                handle = pynvml.nvmlDeviceGetHandleByIndex(i)
                name = pynvml.nvmlDeviceGetName(handle).decode('utf-8')
                memory_info = pynvml.nvmlDeviceGetMemoryInfo(handle)
                
                gpu_info = {
                    'index': i,
                    'name': name,
                    'memory_total': int(memory_info.total / 1024 / 1024),  # MB
                    'memory_free': int(memory_info.free / 1024 / 1024),  # MB
                    'memory_used': int(memory_info.used / 1024 / 1024),  # MB
                    'vendor': 'NVIDIA',
                    'driver_version': pynvml.nvmlSystemGetDriverVersion().decode('utf-8'),
                    'cuda_version': self._get_cuda_version(),
                }
                
                gpus.append(gpu_info)
                logger.info(f"检测到 NVIDIA GPU {i}: {name}, {gpu_info['memory_total']}MB")
            
            pynvml.nvmlShutdown()
            
        except ImportError:
            logger.debug("pynvml 未安装，跳过 NVIDIA GPU 检测")
        except Exception as e:
            logger.debug(f"NVIDIA GPU 检测失败: {e}")
        
        # 尝试检测 AMD GPU (Linux)
        if platform.system() == "Linux":
            try:
                amd_gpus = self._detect_amd_gpu_linux()
                gpus.extend(amd_gpus)
            except Exception as e:
                logger.debug(f"AMD GPU 检测失败: {e}")
        
        # 尝试检测 Intel GPU
        try:
            intel_gpus = self._detect_intel_gpu()
            gpus.extend(intel_gpus)
        except Exception as e:
            logger.debug(f"Intel GPU 检测失败: {e}")
        
        # 尝试检测 Apple Silicon GPU (macOS)
        if platform.system() == "Darwin" and platform.machine() == "arm64":
            try:
                apple_gpu = self._detect_apple_silicon_gpu()
                if apple_gpu:
                    gpus.append(apple_gpu)
            except Exception as e:
                logger.debug(f"Apple Silicon GPU 检测失败: {e}")
        
        if not gpus:
            logger.info("未检测到可用的 GPU")
        
        return gpus
    
    def _get_cuda_version(self) -> Optional[str]:
        """获取 CUDA 版本"""
        try:
            result = subprocess.run(['nvcc', '--version'], 
                                  capture_output=True, text=True)
            if result.returncode == 0:
                for line in result.stdout.split('\n'):
                    if 'release' in line:
                        return line.split('release')[1].split(',')[0].strip()
        except Exception:
            pass
        
        # 尝试从 PyTorch 获取 CUDA 版本
        try:
            import torch
            if torch.cuda.is_available():
                return torch.version.cuda
        except ImportError:
            pass
        
        return None
    
    def _detect_amd_gpu_linux(self) -> List[Dict[str, any]]:
        """检测 AMD GPU (Linux)"""
        gpus = []
        
        try:
            # 检查 /sys/class/drm 目录
            drm_path = Path("/sys/class/drm")
            if drm_path.exists():
                for card_dir in drm_path.glob("card*"):
                    if not card_dir.is_dir():
                        continue
                    
                    device_path = card_dir / "device"
                    if not device_path.exists():
                        continue
                    
                    # 读取设备信息
                    try:
                        vendor_file = device_path / "vendor"
                        device_file = device_path / "device"
                        
                        if vendor_file.exists() and device_file.exists():
                            vendor_id = vendor_file.read_text().strip()
                            device_id = device_file.read_text().strip()
                            
                            # AMD 的 vendor ID 是 0x1002
                            if vendor_id == "0x1002":
                                gpu_info = {
                                    'index': len(gpus),
                                    'name': f"AMD GPU {device_id}",
                                    'memory_total': 0,  # AMD GPU 内存信息较难获取
                                    'memory_free': 0,
                                    'memory_used': 0,
                                    'vendor': 'AMD',
                                    'device_id': device_id,
                                }
                                gpus.append(gpu_info)
                    except Exception:
                        continue
        except Exception as e:
            logger.debug(f"AMD GPU 检测异常: {e}")
        
        return gpus
    
    def _detect_intel_gpu(self) -> List[Dict[str, any]]:
        """检测 Intel GPU"""
        gpus = []
        
        # Intel GPU 检测相对复杂，这里提供基础实现
        try:
            if platform.system() == "Linux":
                # 检查 Intel GPU 驱动
                result = subprocess.run(['lspci', '-nn'], 
                                      capture_output=True, text=True)
                if result.returncode == 0:
                    for line in result.stdout.split('\n'):
                        if 'Intel' in line and ('VGA' in line or 'Display' in line):
                            gpu_info = {
                                'index': len(gpus),
                                'name': line.split(':')[2].strip() if ':' in line else 'Intel GPU',
                                'memory_total': 0,  # Intel 集成显卡共享系统内存
                                'memory_free': 0,
                                'memory_used': 0,
                                'vendor': 'Intel',
                            }
                            gpus.append(gpu_info)
        except Exception as e:
            logger.debug(f"Intel GPU 检测异常: {e}")
        
        return gpus
    
    def _detect_apple_silicon_gpu(self) -> Optional[Dict[str, any]]:
        """检测 Apple Silicon GPU"""
        try:
            # 检查是否是 Apple Silicon Mac
            result = subprocess.run(['sysctl', '-n', 'hw.optional.arm64'], 
                                  capture_output=True, text=True)
            if result.returncode == 0 and result.stdout.strip() == '1':
                # 获取 GPU 核心数
                result = subprocess.run(['sysctl', '-n', 'hw.gpu.family_name'], 
                                      capture_output=True, text=True)
                gpu_name = result.stdout.strip() if result.returncode == 0 else 'Apple GPU'
                
                return {
                    'index': 0,
                    'name': gpu_name,
                    'memory_total': 0,  # Apple Silicon 使用统一内存架构
                    'memory_free': 0,
                    'memory_used': 0,
                    'vendor': 'Apple',
                    'unified_memory': True,
                }
        except Exception as e:
            logger.debug(f"Apple Silicon GPU 检测异常: {e}")
        
        return None


class ModelDetector:
    """模型支持检测器"""
    
    def __init__(self):
        self.available_models = {}
        self.model_requirements = self._get_model_requirements()
    
    def _get_model_requirements(self) -> Dict[str, Dict[str, any]]:
        """获取各模型的硬件需求"""
        return {
            'lama': {
                'min_memory': 2048,  # MB
                'gpu_required': False,
                'frameworks': ['torch'],
                'model_size': 200,  # MB
            },
            'ldm': {
                'min_memory': 4096,
                'gpu_required': True,
                'gpu_memory': 4096,
                'frameworks': ['torch', 'diffusers'],
                'model_size': 1500,
            },
            'sd15': {
                'min_memory': 6144,
                'gpu_required': True,
                'gpu_memory': 6144,
                'frameworks': ['torch', 'diffusers'],
                'model_size': 4000,
            },
            'sd21': {
                'min_memory': 8192,
                'gpu_required': True,
                'gpu_memory': 8192,
                'frameworks': ['torch', 'diffusers'],
                'model_size': 5000,
            },
            'sdxl': {
                'min_memory': 12288,
                'gpu_required': True,
                'gpu_memory': 12288,
                'frameworks': ['torch', 'diffusers'],
                'model_size': 7000,
            },
            'mat': {
                'min_memory': 3072,
                'gpu_required': False,
                'frameworks': ['torch'],
                'model_size': 500,
            },
            'fcf': {
                'min_memory': 2048,
                'gpu_required': False,
                'frameworks': ['torch'],
                'model_size': 300,
            },
            'zits': {
                'min_memory': 4096,
                'gpu_required': False,
                'frameworks': ['torch'],
                'model_size': 800,
            },
            'opencv': {
                'min_memory': 1024,
                'gpu_required': False,
                'frameworks': ['opencv'],
                'model_size': 0,
            },
            'manga': {
                'min_memory': 2048,
                'gpu_required': False,
                'frameworks': ['torch'],
                'model_size': 400,
            },
        }
    
    def detect_supported_models(self, hardware_info: Dict[str, any]) -> List[str]:
        """根据硬件信息检测支持的模型"""
        supported_models = []
        
        cpu_info = hardware_info.get('cpu', {})
        memory_info = hardware_info.get('memory', {})
        gpu_info = hardware_info.get('gpus', [])
        
        total_memory = memory_info.get('total', 0)
        has_gpu = len(gpu_info) > 0
        gpu_memory = max([gpu.get('memory_total', 0) for gpu in gpu_info], default=0)
        
        for model_name, requirements in self.model_requirements.items():
            # 检查内存需求
            if total_memory < requirements['min_memory']:
                continue
            
            # 检查 GPU 需求
            if requirements.get('gpu_required', False):
                if not has_gpu:
                    continue
                if gpu_memory < requirements.get('gpu_memory', 0):
                    continue
            
            # 检查框架支持
            if self._check_framework_support(requirements.get('frameworks', [])):
                supported_models.append(model_name)
        
        logger.info(f"检测到支持的模型: {supported_models}")
        return supported_models
    
    def _check_framework_support(self, required_frameworks: List[str]) -> bool:
        """检查框架支持"""
        for framework in required_frameworks:
            if not self._is_framework_available(framework):
                return False
        return True
    
    def _is_framework_available(self, framework: str) -> bool:
        """检查框架是否可用"""
        try:
            if framework == 'torch':
                import torch
                return True
            elif framework == 'diffusers':
                import diffusers
                return True
            elif framework == 'opencv':
                import cv2
                return True
            elif framework == 'transformers':
                import transformers
                return True
            else:
                return False
        except ImportError:
            return False
    
    def validate_model_installation(self, model_name: str) -> Tuple[bool, Optional[str]]:
        """验证模型安装状态"""
        if model_name not in self.model_requirements:
            return False, f"未知模型: {model_name}"
        
        requirements = self.model_requirements[model_name]
        
        # 检查框架依赖
        for framework in requirements.get('frameworks', []):
            if not self._is_framework_available(framework):
                return False, f"缺少框架依赖: {framework}"
        
        # 检查模型文件（这里简化处理，实际应该检查具体的模型文件）
        try:
            if model_name in ['lama', 'mat', 'fcf', 'zits', 'manga']:
                # 这些模型通常需要预训练权重
                return True, None  # 简化处理
            elif model_name in ['sd15', 'sd21', 'sdxl', 'ldm']:
                # Stable Diffusion 模型
                import diffusers
                return True, None
            elif model_name == 'opencv':
                import cv2
                return True, None
            else:
                return True, None
        except Exception as e:
            return False, str(e)


class CapabilityDetector:
    """节点能力检测器主类"""
    
    def __init__(self):
        self.hardware_detector = HardwareDetector()
        self.model_detector = ModelDetector()
    
    def detect_full_capability(self, node_type: NodeType = NodeType.LOCAL) -> NodeCapability:
        """检测完整的节点能力"""
        logger.info("开始检测节点能力...")
        
        # 检测硬件信息
        cpu_info = self.hardware_detector.detect_cpu_info()
        memory_info = self.hardware_detector.detect_memory_info()
        gpu_info = self.hardware_detector.detect_gpu_info()
        
        hardware_info = {
            'cpu': cpu_info,
            'memory': memory_info,
            'gpus': gpu_info
        }
        
        # 检测支持的模型
        supported_models = self.model_detector.detect_supported_models(hardware_info)
        
        # 创建节点能力对象
        capability = NodeCapability()
        capability.node_type = node_type
        
        # 设置硬件信息
        capability.cpu_cores = cpu_info.get('cores', 1)
        capability.memory_total = memory_info.get('total', 0)
        
        if gpu_info:
            capability.gpu_count = len(gpu_info)
            capability.gpu_memory = max([gpu.get('memory_total', 0) for gpu in gpu_info], default=0)
            capability.gpu_models = [gpu.get('name', 'Unknown') for gpu in gpu_info]
        
        # 设置支持的模型和任务
        capability.supported_models = supported_models
        capability.supported_tasks = self._determine_supported_tasks(supported_models)
        
        # 计算最大并发任务数
        capability.max_concurrent_tasks = self._calculate_max_concurrent_tasks(capability)
        
        logger.info(f"节点能力检测完成: GPU={capability.gpu_count}, CPU={capability.cpu_cores}核心, "
                   f"内存={capability.memory_total}MB, 支持模型={len(supported_models)}个")
        
        return capability
    
    def _determine_supported_tasks(self, supported_models: List[str]) -> List[TaskType]:
        """根据支持的模型确定支持的任务类型"""
        supported_tasks = []
        
        # 图像修复任务
        inpaint_models = ['lama', 'ldm', 'sd15', 'sd21', 'sdxl', 'mat', 'fcf', 'zits', 'opencv', 'manga']
        if any(model in supported_models for model in inpaint_models):
            supported_tasks.append(TaskType.INPAINT)
        
        # 插件任务（通常需要基础的图像处理能力）
        if 'opencv' in supported_models or any(model in supported_models for model in inpaint_models):
            supported_tasks.append(TaskType.PLUGIN)
        
        # 图像放大任务
        upscale_models = ['sd15', 'sd21', 'sdxl']  # 这里简化处理
        if any(model in supported_models for model in upscale_models):
            supported_tasks.append(TaskType.UPSCALE)
        
        # 图像分割任务
        if 'opencv' in supported_models:
            supported_tasks.append(TaskType.SEGMENT)
        
        return supported_tasks
    
    def _calculate_max_concurrent_tasks(self, capability: NodeCapability) -> int:
        """计算最大并发任务数"""
        # 基于内存和 GPU 内存计算
        base_concurrent = 1
        
        # 根据系统内存调整
        if capability.memory_total >= 32768:  # 32GB+
            base_concurrent = 4
        elif capability.memory_total >= 16384:  # 16GB+
            base_concurrent = 3
        elif capability.memory_total >= 8192:   # 8GB+
            base_concurrent = 2
        else:
            base_concurrent = 1
        
        # 根据 GPU 内存调整
        if capability.has_gpu():
            if capability.gpu_memory >= 24576:  # 24GB+
                base_concurrent = min(base_concurrent + 2, 6)
            elif capability.gpu_memory >= 12288:  # 12GB+
                base_concurrent = min(base_concurrent + 1, 4)
            elif capability.gpu_memory >= 8192:   # 8GB+
                base_concurrent = min(base_concurrent, 3)
            else:
                base_concurrent = min(base_concurrent, 2)
        
        # 根据 CPU 核心数调整
        if capability.cpu_cores >= 16:
            base_concurrent = min(base_concurrent + 1, 8)
        elif capability.cpu_cores >= 8:
            base_concurrent = min(base_concurrent, 6)
        elif capability.cpu_cores <= 2:
            base_concurrent = min(base_concurrent, 2)
        
        return max(1, base_concurrent)
    
    def generate_capability_config(self, capability: NodeCapability, 
                                 output_path: Optional[str] = None) -> str:
        """生成节点能力配置文件"""
        config_data = {
            'node_info': {
                'node_id': capability.node_id,
                'node_type': capability.node_type.value,
                'generated_at': capability.last_heartbeat.isoformat() if capability.last_heartbeat else None,
            },
            'hardware': {
                'cpu_cores': capability.cpu_cores,
                'memory_total': capability.memory_total,
                'gpu_count': capability.gpu_count,
                'gpu_memory': capability.gpu_memory,
                'gpu_models': capability.gpu_models,
            },
            'capabilities': {
                'supported_models': capability.supported_models,
                'supported_tasks': [task.value for task in capability.supported_tasks],
                'max_concurrent_tasks': capability.max_concurrent_tasks,
                'queue_subscriptions': capability.get_queue_subscriptions(),
            },
            'system_info': self.hardware_detector.system_info,
        }
        
        config_json = json.dumps(config_data, indent=2, ensure_ascii=False)
        
        if output_path:
            output_file = Path(output_path)
            output_file.parent.mkdir(parents=True, exist_ok=True)
            output_file.write_text(config_json, encoding='utf-8')
            logger.info(f"节点能力配置已保存到: {output_path}")
        
        return config_json
    
    def load_capability_config(self, config_path: str) -> NodeCapability:
        """从配置文件加载节点能力"""
        try:
            config_file = Path(config_path)
            if not config_file.exists():
                raise FileNotFoundError(f"配置文件不存在: {config_path}")
            
            config_data = json.loads(config_file.read_text(encoding='utf-8'))
            
            capability = NodeCapability()
            
            # 加载节点信息
            node_info = config_data.get('node_info', {})
            capability.node_id = node_info.get('node_id', capability.node_id)
            capability.node_type = NodeType(node_info.get('node_type', NodeType.LOCAL.value))
            
            # 加载硬件信息
            hardware = config_data.get('hardware', {})
            capability.cpu_cores = hardware.get('cpu_cores', 0)
            capability.memory_total = hardware.get('memory_total', 0)
            capability.gpu_count = hardware.get('gpu_count', 0)
            capability.gpu_memory = hardware.get('gpu_memory', 0)
            capability.gpu_models = hardware.get('gpu_models', [])
            
            # 加载能力信息
            capabilities = config_data.get('capabilities', {})
            capability.supported_models = capabilities.get('supported_models', [])
            capability.supported_tasks = [TaskType(task) for task in capabilities.get('supported_tasks', [])]
            capability.max_concurrent_tasks = capabilities.get('max_concurrent_tasks', 1)
            
            logger.info(f"从配置文件加载节点能力: {config_path}")
            return capability
            
        except Exception as e:
            logger.error(f"加载节点能力配置失败 {config_path}: {e}")
            raise


def detect_node_capability(node_type: NodeType = NodeType.LOCAL, 
                         config_output: Optional[str] = None) -> NodeCapability:
    """便捷函数：检测节点能力"""
    detector = CapabilityDetector()
    capability = detector.detect_full_capability(node_type)
    
    if config_output:
        detector.generate_capability_config(capability, config_output)
    
    return capability


if __name__ == "__main__":
    # 命令行工具
    import argparse
    
    parser = argparse.ArgumentParser(description="节点能力检测工具")
    parser.add_argument("--output", "-o", help="输出配置文件路径")
    parser.add_argument("--type", "-t", choices=['local', 'remote', 'serverless'], 
                       default='local', help="节点类型")
    parser.add_argument("--verbose", "-v", action="store_true", help="详细输出")
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO)
    
    node_type = NodeType(args.type)
    capability = detect_node_capability(node_type, args.output)
    
    print("节点能力检测结果:")
    print(f"  节点类型: {capability.node_type.value}")
    print(f"  CPU 核心: {capability.cpu_cores}")
    print(f"  内存总量: {capability.memory_total} MB")
    print(f"  GPU 数量: {capability.gpu_count}")
    print(f"  GPU 内存: {capability.gpu_memory} MB")
    print(f"  支持模型: {', '.join(capability.supported_models)}")
    print(f"  支持任务: {', '.join([t.value for t in capability.supported_tasks])}")
    print(f"  最大并发: {capability.max_concurrent_tasks}")
    print(f"  可订阅队列: {', '.join(capability.get_queue_subscriptions())}")