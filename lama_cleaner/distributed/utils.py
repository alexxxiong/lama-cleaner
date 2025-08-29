"""
分布式处理工具函数

提供硬件检测、系统信息收集等工具函数。
"""

import os
import platform
import psutil
import logging
from typing import Dict, List, Optional, Any
import subprocess
import json

logger = logging.getLogger(__name__)


def detect_gpu_info() -> Dict[str, Any]:
    """检测 GPU 信息"""
    gpu_info = {
        'count': 0,
        'memory': 0,
        'models': [],
        'available': False
    }
    
    try:
        # 尝试使用 nvidia-ml-py
        try:
            import pynvml
            pynvml.nvmlInit()
            
            device_count = pynvml.nvmlDeviceGetCount()
            gpu_info['count'] = device_count
            gpu_info['available'] = device_count > 0
            
            for i in range(device_count):
                handle = pynvml.nvmlDeviceGetHandleByIndex(i)
                
                # 获取 GPU 名称
                name = pynvml.nvmlDeviceGetName(handle).decode('utf-8')
                gpu_info['models'].append(name)
                
                # 获取内存信息
                mem_info = pynvml.nvmlDeviceGetMemoryInfo(handle)
                gpu_memory_mb = mem_info.total // (1024 * 1024)
                gpu_info['memory'] = max(gpu_info['memory'], gpu_memory_mb)
            
            pynvml.nvmlShutdown()
            
        except ImportError:
            # 如果没有 pynvml，尝试使用 nvidia-smi
            try:
                result = subprocess.run([
                    'nvidia-smi', '--query-gpu=name,memory.total', 
                    '--format=csv,noheader,nounits'
                ], capture_output=True, text=True, timeout=10)
                
                if result.returncode == 0:
                    lines = result.stdout.strip().split('\n')
                    gpu_info['count'] = len(lines)
                    gpu_info['available'] = len(lines) > 0
                    
                    for line in lines:
                        parts = line.split(', ')
                        if len(parts) >= 2:
                            name = parts[0].strip()
                            memory = int(parts[1].strip())
                            gpu_info['models'].append(name)
                            gpu_info['memory'] = max(gpu_info['memory'], memory)
                            
            except (subprocess.TimeoutExpired, subprocess.CalledProcessError, FileNotFoundError):
                pass
        
        # 尝试检测 PyTorch CUDA 支持
        try:
            import torch
            if torch.cuda.is_available():
                if gpu_info['count'] == 0:  # 如果前面的检测失败了
                    gpu_info['count'] = torch.cuda.device_count()
                    gpu_info['available'] = True
                    
                    for i in range(gpu_info['count']):
                        props = torch.cuda.get_device_properties(i)
                        gpu_info['models'].append(props.name)
                        memory_mb = props.total_memory // (1024 * 1024)
                        gpu_info['memory'] = max(gpu_info['memory'], memory_mb)
        except ImportError:
            pass
            
    except Exception as e:
        logger.error(f"GPU 检测失败: {e}")
    
    return gpu_info


def detect_cpu_info() -> Dict[str, Any]:
    """检测 CPU 信息"""
    cpu_info = {
        'cores': psutil.cpu_count(logical=False) or 1,
        'logical_cores': psutil.cpu_count(logical=True) or 1,
        'frequency': 0,
        'model': platform.processor() or 'Unknown',
        'architecture': platform.machine()
    }
    
    try:
        # 获取 CPU 频率
        freq = psutil.cpu_freq()
        if freq:
            cpu_info['frequency'] = freq.max or freq.current or 0
    except Exception as e:
        logger.warning(f"获取 CPU 频率失败: {e}")
    
    return cpu_info


def detect_memory_info() -> Dict[str, Any]:
    """检测内存信息"""
    memory = psutil.virtual_memory()
    
    return {
        'total': memory.total // (1024 * 1024),  # MB
        'available': memory.available // (1024 * 1024),  # MB
        'used': memory.used // (1024 * 1024),  # MB
        'percent': memory.percent
    }


def detect_disk_info() -> Dict[str, Any]:
    """检测磁盘信息"""
    disk = psutil.disk_usage('/')
    
    return {
        'total': disk.total // (1024 * 1024),  # MB
        'free': disk.free // (1024 * 1024),  # MB
        'used': disk.used // (1024 * 1024),  # MB
        'percent': (disk.used / disk.total) * 100
    }


def detect_network_info() -> Dict[str, Any]:
    """检测网络信息"""
    network_info = {
        'hostname': platform.node(),
        'interfaces': []
    }
    
    try:
        # 获取网络接口信息
        interfaces = psutil.net_if_addrs()
        for interface_name, addresses in interfaces.items():
            interface_info = {
                'name': interface_name,
                'addresses': []
            }
            
            for addr in addresses:
                if addr.family.name in ['AF_INET', 'AF_INET6']:
                    interface_info['addresses'].append({
                        'family': addr.family.name,
                        'address': addr.address,
                        'netmask': addr.netmask
                    })
            
            if interface_info['addresses']:
                network_info['interfaces'].append(interface_info)
                
    except Exception as e:
        logger.warning(f"获取网络信息失败: {e}")
    
    return network_info


def get_system_info() -> Dict[str, Any]:
    """获取完整的系统信息"""
    return {
        'platform': {
            'system': platform.system(),
            'release': platform.release(),
            'version': platform.version(),
            'machine': platform.machine(),
            'processor': platform.processor()
        },
        'python': {
            'version': platform.python_version(),
            'implementation': platform.python_implementation()
        },
        'gpu': detect_gpu_info(),
        'cpu': detect_cpu_info(),
        'memory': detect_memory_info(),
        'disk': detect_disk_info(),
        'network': detect_network_info()
    }


def check_port_available(host: str, port: int) -> bool:
    """检查端口是否可用"""
    import socket
    
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(1)
            result = sock.connect_ex((host, port))
            return result != 0  # 0 表示连接成功，即端口被占用
    except Exception:
        return False


def find_available_port(host: str, start_port: int, max_attempts: int = 100) -> Optional[int]:
    """查找可用端口"""
    for port in range(start_port, start_port + max_attempts):
        if check_port_available(host, port):
            return port
    return None


def format_bytes(bytes_value: int) -> str:
    """格式化字节数"""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if bytes_value < 1024.0:
            return f"{bytes_value:.1f} {unit}"
        bytes_value /= 1024.0
    return f"{bytes_value:.1f} PB"


def format_duration(seconds: float) -> str:
    """格式化时间长度"""
    if seconds < 60:
        return f"{seconds:.1f}秒"
    elif seconds < 3600:
        minutes = seconds / 60
        return f"{minutes:.1f}分钟"
    else:
        hours = seconds / 3600
        return f"{hours:.1f}小时"


def validate_image_file(file_path: str) -> bool:
    """验证图像文件"""
    if not os.path.exists(file_path):
        return False
    
    # 检查文件扩展名
    valid_extensions = {'.jpg', '.jpeg', '.png', '.bmp', '.tiff', '.webp'}
    _, ext = os.path.splitext(file_path.lower())
    if ext not in valid_extensions:
        return False
    
    # 尝试打开图像文件
    try:
        from PIL import Image
        with Image.open(file_path) as img:
            img.verify()
        return True
    except Exception:
        return False


def get_file_hash(file_path: str) -> Optional[str]:
    """获取文件哈希值"""
    import hashlib
    
    try:
        hash_md5 = hashlib.md5()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_md5.update(chunk)
        return hash_md5.hexdigest()
    except Exception as e:
        logger.error(f"计算文件哈希失败 {file_path}: {e}")
        return None


def ensure_directory(directory: str):
    """确保目录存在"""
    os.makedirs(directory, exist_ok=True)


def cleanup_temp_files(temp_dir: str, max_age_hours: int = 24):
    """清理临时文件"""
    import time
    from pathlib import Path
    
    if not os.path.exists(temp_dir):
        return
    
    current_time = time.time()
    max_age_seconds = max_age_hours * 3600
    cleaned_count = 0
    
    try:
        for file_path in Path(temp_dir).rglob('*'):
            if file_path.is_file():
                file_age = current_time - file_path.stat().st_mtime
                if file_age > max_age_seconds:
                    try:
                        file_path.unlink()
                        cleaned_count += 1
                    except Exception as e:
                        logger.warning(f"删除临时文件失败 {file_path}: {e}")
        
        if cleaned_count > 0:
            logger.info(f"清理了 {cleaned_count} 个临时文件")
            
    except Exception as e:
        logger.error(f"清理临时文件失败: {e}")


def get_available_models() -> List[str]:
    """获取可用的模型列表"""
    # 这里应该根据实际安装的模型来返回
    # 目前返回一个基础的模型列表
    models = ['lama', 'opencv']
    
    try:
        # 检查是否有 GPU 支持的模型
        gpu_info = detect_gpu_info()
        if gpu_info['available']:
            models.extend(['sd15', 'mat', 'fcf'])
            
            # 如果 GPU 内存足够，添加更大的模型
            if gpu_info['memory'] >= 8192:
                models.extend(['sd21', 'sdxl'])
                
    except Exception as e:
        logger.warning(f"检测可用模型失败: {e}")
    
    return models


def create_task_directory(task_id: str, base_path: str = "storage/tasks") -> str:
    """创建任务目录"""
    task_dir = os.path.join(base_path, task_id)
    ensure_directory(task_dir)
    return task_dir


def save_task_config(task_id: str, config: Dict[str, Any], base_path: str = "storage/tasks"):
    """保存任务配置"""
    task_dir = create_task_directory(task_id, base_path)
    config_path = os.path.join(task_dir, "config.json")
    
    try:
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"保存任务配置失败 {task_id}: {e}")


def load_task_config(task_id: str, base_path: str = "storage/tasks") -> Optional[Dict[str, Any]]:
    """加载任务配置"""
    config_path = os.path.join(base_path, task_id, "config.json")
    
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"加载任务配置失败 {task_id}: {e}")
        return None