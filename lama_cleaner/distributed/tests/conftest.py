"""
pytest 配置文件

为分布式模块测试提供共享的 fixtures 和配置
"""

import pytest
import sys
import os
import tempfile
import shutil
from pathlib import Path
from unittest.mock import MagicMock

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))


@pytest.fixture(scope="session")
def test_config():
    """测试配置 fixture"""
    return {
        'test_data_dir': Path(__file__).parent / 'data',
        'temp_dir': None,
        'mock_redis': True,
        'mock_zmq': True
    }


@pytest.fixture(scope="function")
def temp_directory():
    """临时目录 fixture"""
    temp_dir = tempfile.mkdtemp(prefix='lama_cleaner_test_')
    yield Path(temp_dir)
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture(scope="function")
def mock_redis():
    """模拟 Redis 客户端"""
    mock_client = MagicMock()
    mock_client.hset.return_value = True
    mock_client.hgetall.return_value = {}
    mock_client.expire.return_value = True
    return mock_client


@pytest.fixture(scope="function")
def mock_zmq_context():
    """模拟 ZeroMQ 上下文"""
    mock_context = MagicMock()
    mock_socket = MagicMock()
    mock_context.socket.return_value = mock_socket
    return mock_context


@pytest.fixture(scope="function")
def sample_task_data():
    """示例任务数据"""
    return {
        'task_id': 'test-task-001',
        'task_type': 'inpaint',
        'status': 'pending',
        'priority': 2,
        'image_path': '/test/image.jpg',
        'config': {
            'model': 'lama',
            'device': 'cpu'
        }
    }


@pytest.fixture(scope="function")
def sample_node_data():
    """示例节点数据"""
    return {
        'node_id': 'test-node-001',
        'node_type': 'local',
        'gpu_count': 1,
        'gpu_memory': 8192,
        'cpu_cores': 8,
        'memory_total': 32768,
        'supported_models': ['lama', 'opencv'],
        'supported_tasks': ['inpaint']
    }


@pytest.fixture(scope="function")
def test_image_path(temp_directory):
    """测试图像文件路径"""
    # 创建一个简单的测试图像文件
    image_path = temp_directory / 'test_image.jpg'
    
    # 创建一个最小的 JPEG 文件头（用于测试）
    jpeg_header = bytes([
        0xFF, 0xD8, 0xFF, 0xE0, 0x00, 0x10, 0x4A, 0x46,
        0x49, 0x46, 0x00, 0x01, 0x01, 0x01, 0x00, 0x48,
        0x00, 0x48, 0x00, 0x00, 0xFF, 0xD9
    ])
    
    with open(image_path, 'wb') as f:
        f.write(jpeg_header)
    
    return str(image_path)


@pytest.fixture(autouse=True)
def setup_test_environment():
    """自动设置测试环境"""
    # 设置测试环境变量
    os.environ['TESTING'] = '1'
    os.environ['LOG_LEVEL'] = 'ERROR'  # 减少测试时的日志输出
    
    yield
    
    # 清理环境变量
    os.environ.pop('TESTING', None)
    os.environ.pop('LOG_LEVEL', None)


@pytest.fixture(scope="function")
def isolated_config(temp_directory):
    """隔离的配置环境"""
    from lama_cleaner.distributed.config import ConfigManager
    
    # 创建临时配置目录
    config_dir = temp_directory / 'config'
    config_dir.mkdir()
    
    # 创建配置管理器
    config_manager = ConfigManager(str(config_dir))
    
    return config_manager


def pytest_configure(config):
    """pytest 配置钩子"""
    # 添加自定义标记
    config.addinivalue_line(
        "markers", "slow: marks tests as slow (deselect with '-m \"not slow\"')"
    )
    config.addinivalue_line(
        "markers", "integration: marks tests as integration tests"
    )
    config.addinivalue_line(
        "markers", "unit: marks tests as unit tests"
    )


def pytest_collection_modifyitems(config, items):
    """修改测试收集"""
    # 为没有标记的测试添加 unit 标记
    for item in items:
        if not any(item.iter_markers()):
            item.add_marker(pytest.mark.unit)


@pytest.fixture(scope="session")
def check_dependencies():
    """检查测试依赖"""
    required_modules = [
        'unittest',
        'pathlib',
        'tempfile',
        'json'
    ]
    
    missing_modules = []
    for module in required_modules:
        try:
            __import__(module)
        except ImportError:
            missing_modules.append(module)
    
    if missing_modules:
        pytest.skip(f"Missing required modules: {missing_modules}")
    
    return True