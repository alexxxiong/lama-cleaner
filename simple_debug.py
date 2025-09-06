#!/usr/bin/env python3
"""
简化的分布式系统调试脚本

不依赖完整环境，只检查核心组件的导入和基本功能。
"""

import sys
import os
import logging
from pathlib import Path

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def check_project_structure():
    """检查项目结构"""
    logger.info("检查项目结构...")
    
    required_dirs = [
        "lama_cleaner",
        "lama_cleaner/distributed",
        "config"
    ]
    
    required_files = [
        "lama_cleaner/distributed/__init__.py",
        "lama_cleaner/distributed/config.py",
        "lama_cleaner/distributed/models.py",
        "lama_cleaner/distributed/queue_manager.py",
        "lama_cleaner/distributed/task_manager.py",
        "lama_cleaner/distributed/worker_node.py",
        "lama_cleaner/distributed/scheduler.py",
        "lama_cleaner/distributed/state_manager.py",
    ]
    
    missing_items = []
    
    # 检查目录
    for dir_path in required_dirs:
        if not Path(dir_path).exists():
            missing_items.append(f"目录: {dir_path}")
        else:
            logger.info(f"✅ 目录存在: {dir_path}")
    
    # 检查文件
    for file_path in required_files:
        if not Path(file_path).exists():
            missing_items.append(f"文件: {file_path}")
        else:
            logger.info(f"✅ 文件存在: {file_path}")
    
    if missing_items:
        logger.error("缺少以下项目:")
        for item in missing_items:
            logger.error(f"  ❌ {item}")
        return False
    
    logger.info("✅ 项目结构完整")
    return True


def check_python_imports():
    """检查 Python 模块导入"""
    logger.info("检查核心模块导入...")
    
    # 添加项目路径
    sys.path.insert(0, str(Path(__file__).parent))
    
    modules_to_test = [
        ("lama_cleaner.distributed", "分布式模块"),
        ("lama_cleaner.distributed.config", "配置模块"),
        ("lama_cleaner.distributed.models", "数据模型"),
    ]
    
    import_errors = []
    
    for module_name, description in modules_to_test:
        try:
            __import__(module_name)
            logger.info(f"✅ {description}: 导入成功")
        except ImportError as e:
            import_errors.append(f"{description}: {e}")
            logger.error(f"❌ {description}: 导入失败 - {e}")
        except Exception as e:
            import_errors.append(f"{description}: {e}")
            logger.error(f"❌ {description}: 其他错误 - {e}")
    
    if import_errors:
        logger.error("模块导入存在问题:")
        for error in import_errors:
            logger.error(f"  {error}")
        return False
    
    logger.info("✅ 所有核心模块导入成功")
    return True


def test_basic_functionality():
    """测试基本功能"""
    logger.info("测试基本功能...")
    
    try:
        # 测试配置系统
        from lama_cleaner.distributed.config import DistributedConfig, ConfigManager
        
        # 创建默认配置
        config = DistributedConfig()
        logger.info(f"✅ 配置创建成功: enabled={config.enabled}")
        
        # 测试配置管理器
        config_manager = ConfigManager()
        logger.info("✅ 配置管理器创建成功")
        
        # 测试数据模型
        from lama_cleaner.distributed.models import Task, TaskType, TaskStatus, TaskPriority
        
        # 创建测试任务
        task = Task.create_inpaint_task(
            image_data=b"test_data",
            mask_data=b"test_mask",
            config={"model": "lama"},
            user_id="test_user"
        )
        logger.info(f"✅ 任务创建成功: {task.task_id}")
        
        # 测试任务序列化
        task_dict = task.to_dict()
        restored_task = Task.from_dict(task_dict)
        logger.info(f"✅ 任务序列化成功: {restored_task.task_id}")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ 基本功能测试失败: {e}")
        return False


def check_configuration_files():
    """检查配置文件"""
    logger.info("检查配置文件...")
    
    config_dir = Path("config")
    if not config_dir.exists():
        config_dir.mkdir(exist_ok=True)
        logger.info("✅ 创建配置目录")
    
    # 检查是否有配置文件
    config_files = list(config_dir.glob("*.yaml")) + list(config_dir.glob("*.yml"))
    
    if not config_files:
        logger.info("ℹ️  没有找到配置文件，将使用默认配置")
        
        # 创建示例配置
        try:
            from lama_cleaner.distributed.config import ConfigManager
            config_manager = ConfigManager()
            config_manager.create_default_config()
            logger.info("✅ 创建默认配置文件")
        except Exception as e:
            logger.warning(f"⚠️  创建默认配置失败: {e}")
    else:
        logger.info(f"✅ 找到配置文件: {[f.name for f in config_files]}")
    
    return True


def check_dependencies():
    """检查关键依赖"""
    logger.info("检查关键依赖...")
    
    # 只检查分布式系统必需的依赖
    critical_deps = [
        ("json", "JSON 处理"),
        ("threading", "多线程支持"),
        ("datetime", "时间处理"),
        ("pathlib", "路径处理"),
        ("logging", "日志系统"),
    ]
    
    optional_deps = [
        ("zmq", "ZeroMQ 消息队列"),
        ("redis", "Redis 缓存"),
        ("yaml", "YAML 配置"),
    ]
    
    # 检查关键依赖
    missing_critical = []
    for dep, desc in critical_deps:
        try:
            __import__(dep)
            logger.info(f"✅ {desc}: 可用")
        except ImportError:
            missing_critical.append(f"{desc} ({dep})")
            logger.error(f"❌ {desc}: 不可用")
    
    # 检查可选依赖
    missing_optional = []
    for dep, desc in optional_deps:
        try:
            __import__(dep)
            logger.info(f"✅ {desc}: 可用")
        except ImportError:
            missing_optional.append(f"{desc} ({dep})")
            logger.warning(f"⚠️  {desc}: 不可用")
    
    if missing_critical:
        logger.error(f"缺少关键依赖: {missing_critical}")
        return False
    
    if missing_optional:
        logger.warning(f"缺少可选依赖: {missing_optional}")
        logger.info("系统可以运行，但某些功能可能受限")
    
    return True


def main():
    """主函数"""
    logger.info("Lama Cleaner 分布式系统简化调试")
    logger.info("="*50)
    
    tests = [
        ("项目结构", check_project_structure),
        ("关键依赖", check_dependencies),
        ("Python 导入", check_python_imports),
        ("配置文件", check_configuration_files),
        ("基本功能", test_basic_functionality),
    ]
    
    results = {}
    
    for test_name, test_func in tests:
        logger.info(f"\n{'='*30}")
        logger.info(f"测试: {test_name}")
        logger.info(f"{'='*30}")
        
        try:
            result = test_func()
            results[test_name] = result
            status = "✅ 通过" if result else "❌ 失败"
            logger.info(f"{status}")
        except Exception as e:
            results[test_name] = False
            logger.error(f"❌ 错误: {e}")
    
    # 总结
    logger.info(f"\n{'='*50}")
    logger.info("测试总结")
    logger.info(f"{'='*50}")
    
    passed = sum(results.values())
    total = len(results)
    
    logger.info(f"通过: {passed}/{total}")
    
    for test_name, result in results.items():
        status = "✅" if result else "❌"
        logger.info(f"{status} {test_name}")
    
    if passed == total:
        logger.info("\n🎉 所有测试通过！分布式系统基础组件正常。")
        logger.info("\n下一步:")
        logger.info("1. 安装完整依赖: uv sync")
        logger.info("2. 启动 Redis 服务 (可选)")
        logger.info("3. 运行完整的系统测试")
        return 0
    else:
        logger.error(f"\n💥 有 {total - passed} 个测试失败。")
        return 1


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)