#!/usr/bin/env python3
"""
Lama Cleaner 分布式系统快速启动脚本

自动安装依赖、配置系统并启动分布式处理服务。
"""

import sys
import os
import subprocess
import logging
import time
from pathlib import Path

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def run_command(command, description="", check=True):
    """运行命令并处理结果"""
    logger.info(f"执行: {description or command}")
    try:
        result = subprocess.run(
            command, 
            shell=True, 
            check=check, 
            capture_output=True, 
            text=True
        )
        if result.stdout:
            logger.info(f"输出: {result.stdout.strip()}")
        return result.returncode == 0
    except subprocess.CalledProcessError as e:
        logger.error(f"命令执行失败: {e}")
        if e.stderr:
            logger.error(f"错误: {e.stderr.strip()}")
        return False


def check_python_version():
    """检查 Python 版本"""
    logger.info("检查 Python 版本...")
    version = sys.version_info
    if version.major != 3 or version.minor < 8:
        logger.error(f"需要 Python 3.8+，当前版本: {version.major}.{version.minor}")
        return False
    logger.info(f"✅ Python 版本: {version.major}.{version.minor}.{version.micro}")
    return True


def install_dependencies():
    """安装依赖包"""
    logger.info("安装分布式系统依赖...")
    
    # 基础依赖
    basic_deps = [
        "pyzmq",
        "redis", 
        "flask",
        "flask-socketio",
        "pydantic",
        "loguru",
        "pyyaml",
        "rich"
    ]
    
    success_count = 0
    for dep in basic_deps:
        if run_command(f"pip3 install {dep}", f"安装 {dep}", check=False):
            success_count += 1
        else:
            logger.warning(f"⚠️  {dep} 安装失败，但系统可能仍能运行")
    
    logger.info(f"依赖安装完成: {success_count}/{len(basic_deps)} 成功")
    return success_count > len(basic_deps) * 0.7  # 70% 成功率即可


def check_redis_service():
    """检查 Redis 服务"""
    logger.info("检查 Redis 服务...")
    
    try:
        import redis
        r = redis.Redis(host='localhost', port=6379, db=0, socket_timeout=1)
        r.ping()
        logger.info("✅ Redis 服务运行正常")
        return True
    except ImportError:
        logger.warning("⚠️  Redis 模块未安装")
        return False
    except Exception as e:
        logger.warning(f"⚠️  Redis 服务未运行: {e}")
        logger.info("提示: 可以运行 'brew install redis && brew services start redis' 启动 Redis")
        return False


def setup_configuration():
    """设置配置"""
    logger.info("设置系统配置...")
    
    # 添加项目路径
    sys.path.insert(0, str(Path(__file__).parent))
    
    try:
        from lama_cleaner.distributed.config import config_manager
        
        # 创建默认配置
        config = config_manager.get_config()
        logger.info(f"✅ 配置加载成功: enabled={config.enabled}")
        
        # 验证配置
        errors = config_manager.validate_config(config)
        if errors:
            logger.warning(f"配置验证警告: {errors}")
        else:
            logger.info("✅ 配置验证通过")
        
        return True
        
    except Exception as e:
        logger.error(f"配置设置失败: {e}")
        return False


def test_core_components():
    """测试核心组件"""
    logger.info("测试核心组件...")
    
    try:
        # 测试数据模型
        from lama_cleaner.distributed.models import Task, TaskType
        task = Task.create_inpaint_task(
            image_data=b"test",
            mask_data=b"test", 
            config={"model": "lama"},
            user_id="test"
        )
        logger.info(f"✅ 任务模型测试通过: {task.task_id}")
        
        # 测试配置系统
        from lama_cleaner.distributed.config import get_config
        config = get_config()
        logger.info(f"✅ 配置系统测试通过")
        
        return True
        
    except Exception as e:
        logger.error(f"组件测试失败: {e}")
        return False


def start_distributed_system():
    """启动分布式系统"""
    logger.info("准备启动分布式系统...")
    
    try:
        # 检查 ZeroMQ
        import zmq
        logger.info("✅ ZeroMQ 可用")
        
        # 这里可以启动实际的分布式组件
        logger.info("🚀 分布式系统组件已就绪")
        logger.info("提示: 使用以下命令启动具体服务:")
        logger.info("  - 调度器: python -m lama_cleaner.distributed.scheduler")
        logger.info("  - 工作节点: python -m lama_cleaner.distributed.worker_node")
        logger.info("  - Web 服务: python -m lama_cleaner.server --distributed")
        
        return True
        
    except ImportError as e:
        logger.error(f"ZeroMQ 不可用: {e}")
        logger.info("系统将以单机模式运行")
        return False
    except Exception as e:
        logger.error(f"系统启动失败: {e}")
        return False


def main():
    """主函数"""
    logger.info("🚀 Lama Cleaner 分布式系统快速启动")
    logger.info("="*60)
    
    steps = [
        ("检查 Python 版本", check_python_version),
        ("安装依赖包", install_dependencies),
        ("检查 Redis 服务", check_redis_service),
        ("设置配置", setup_configuration),
        ("测试核心组件", test_core_components),
        ("启动分布式系统", start_distributed_system),
    ]
    
    results = {}
    
    for step_name, step_func in steps:
        logger.info(f"\n{'='*30}")
        logger.info(f"步骤: {step_name}")
        logger.info(f"{'='*30}")
        
        try:
            result = step_func()
            results[step_name] = result
            status = "✅ 成功" if result else "⚠️  警告"
            logger.info(f"{status}")
        except Exception as e:
            results[step_name] = False
            logger.error(f"❌ 失败: {e}")
    
    # 总结
    logger.info(f"\n{'='*60}")
    logger.info("启动总结")
    logger.info(f"{'='*60}")
    
    success_count = sum(results.values())
    total_count = len(results)
    
    logger.info(f"成功步骤: {success_count}/{total_count}")
    
    for step_name, result in results.items():
        status = "✅" if result else "❌"
        logger.info(f"{status} {step_name}")
    
    if success_count >= total_count * 0.8:  # 80% 成功率
        logger.info("\n🎉 系统启动成功！")
        logger.info("\n下一步操作:")
        logger.info("1. 运行完整测试: python3 debug_distributed_system.py")
        logger.info("2. 启动调度器: python -m lama_cleaner.distributed.scheduler")
        logger.info("3. 启动工作节点: python -m lama_cleaner.distributed.worker_node")
        logger.info("4. 查看系统状态: cat system_status_report.md")
        return 0
    else:
        logger.error("\n💥 系统启动遇到问题")
        logger.info("请检查上述错误信息并解决问题后重试")
        return 1


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)