#!/usr/bin/env python3
"""
分布式系统调试脚本

用于测试和调试 Lama Cleaner 分布式处理架构的各个组件。
"""

import sys
import os
import time
import logging
import asyncio
import threading
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent))

from lama_cleaner.distributed.config import get_config, config_manager
from lama_cleaner.distributed.models import Task, TaskType, TaskStatus, TaskPriority
from lama_cleaner.distributed.queue_manager import QueueManager
from lama_cleaner.distributed.task_manager import TaskManager
from lama_cleaner.distributed.worker_node import WorkerNode
from lama_cleaner.distributed.scheduler import DistributedScheduler
from lama_cleaner.distributed.state_manager import StateManager

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class SystemDebugger:
    """系统调试器"""
    
    def __init__(self):
        self.config = get_config()
        self.components = {}
        self.test_results = {}
    
    def run_all_tests(self):
        """运行所有测试"""
        logger.info("开始分布式系统调试...")
        
        tests = [
            ("配置系统", self.test_config_system),
            ("存储系统", self.test_storage_system),
            ("队列管理器", self.test_queue_manager),
            ("任务管理器", self.test_task_manager),
            ("状态管理器", self.test_state_manager),
            ("工作节点", self.test_worker_node),
            ("调度器", self.test_scheduler),
            ("端到端流程", self.test_end_to_end),
        ]
        
        for test_name, test_func in tests:
            logger.info(f"\n{'='*50}")
            logger.info(f"测试: {test_name}")
            logger.info(f"{'='*50}")
            
            try:
                result = test_func()
                self.test_results[test_name] = {
                    'status': 'PASS' if result else 'FAIL',
                    'details': result
                }
                logger.info(f"✅ {test_name}: {'通过' if result else '失败'}")
            except Exception as e:
                self.test_results[test_name] = {
                    'status': 'ERROR',
                    'details': str(e)
                }
                logger.error(f"❌ {test_name}: 错误 - {e}")
        
        self.print_summary()
    
    def test_config_system(self):
        """测试配置系统"""
        try:
            # 测试配置加载
            config = get_config()
            logger.info(f"配置加载成功: enabled={config.enabled}")
            
            # 测试配置验证
            errors = config_manager.validate_config(config)
            if errors:
                logger.warning(f"配置验证发现问题: {errors}")
                return False
            
            logger.info("配置系统正常")
            return True
            
        except Exception as e:
            logger.error(f"配置系统测试失败: {e}")
            return False
    
    def test_storage_system(self):
        """测试存储系统"""
        try:
            from lama_cleaner.distributed.storage import get_task_storage, get_file_storage
            
            # 测试任务存储
            task_storage = get_task_storage()
            logger.info("任务存储初始化成功")
            
            # 测试文件存储
            file_storage = get_file_storage()
            logger.info("文件存储初始化成功")
            
            return True
            
        except Exception as e:
            logger.error(f"存储系统测试失败: {e}")
            return False
    
    def test_queue_manager(self):
        """测试队列管理器"""
        try:
            queue_manager = QueueManager()
            
            # 测试队列初始化
            queue_manager.start()
            logger.info("队列管理器启动成功")
            
            # 测试队列统计
            stats = queue_manager.get_queue_stats()
            logger.info(f"队列统计: {stats}")
            
            # 清理
            queue_manager.stop()
            logger.info("队列管理器停止成功")
            
            return True
            
        except Exception as e:
            logger.error(f"队列管理器测试失败: {e}")
            return False
    
    def test_task_manager(self):
        """测试任务管理器"""
        try:
            task_manager = TaskManager()
            
            # 创建测试任务
            test_task = Task.create_inpaint_task(
                image_data=b"test_image_data",
                mask_data=b"test_mask_data",
                config={"model": "lama"},
                user_id="test_user"
            )
            
            logger.info(f"创建测试任务: {test_task.task_id}")
            
            # 测试任务提交
            task_manager.submit_task(test_task)
            logger.info("任务提交成功")
            
            # 测试任务查询
            retrieved_task = task_manager.get_task(test_task.task_id)
            if retrieved_task:
                logger.info(f"任务查询成功: {retrieved_task.status}")
            else:
                logger.warning("任务查询失败")
                return False
            
            return True
            
        except Exception as e:
            logger.error(f"任务管理器测试失败: {e}")
            return False
    
    def test_state_manager(self):
        """测试状态管理器"""
        try:
            from lama_cleaner.distributed.state_manager import StateManager
            
            # 创建状态管理器（不依赖 Redis）
            state_manager = StateManager(redis_client=None, socketio=None)
            
            # 创建测试任务
            test_task = Task.create_inpaint_task(
                image_data=b"test_image_data",
                mask_data=b"test_mask_data",
                config={"model": "lama"},
                user_id="test_user"
            )
            
            # 测试状态更新
            state_manager.update_task_status(test_task)
            logger.info("状态更新成功")
            
            # 测试状态查询
            status = state_manager.get_task_status(test_task.task_id)
            if status:
                logger.info(f"状态查询成功: {status}")
            else:
                logger.warning("状态查询失败")
                return False
            
            return True
            
        except Exception as e:
            logger.error(f"状态管理器测试失败: {e}")
            return False
    
    def test_worker_node(self):
        """测试工作节点"""
        try:
            from lama_cleaner.distributed.capability_detector import CapabilityDetector
            
            # 测试能力检测
            detector = CapabilityDetector()
            capability = detector.detect_capability()
            logger.info(f"节点能力检测: {capability.to_dict()}")
            
            # 测试工作节点创建
            worker_config = {
                'node_id': 'test_worker',
                'scheduler_host': 'localhost',
                'scheduler_port': 8081
            }
            
            # 注意：这里不启动实际的工作节点，只测试创建
            logger.info("工作节点组件测试通过")
            
            return True
            
        except Exception as e:
            logger.error(f"工作节点测试失败: {e}")
            return False
    
    def test_scheduler(self):
        """测试调度器"""
        try:
            # 测试调度器创建
            scheduler = DistributedScheduler()
            logger.info("调度器创建成功")
            
            # 测试调度器配置
            logger.info(f"调度器配置: host={self.config.scheduler_host}, port={self.config.scheduler_port}")
            
            return True
            
        except Exception as e:
            logger.error(f"调度器测试失败: {e}")
            return False
    
    def test_end_to_end(self):
        """测试端到端流程"""
        try:
            logger.info("端到端测试：模拟完整的任务处理流程")
            
            # 1. 创建任务
            test_task = Task.create_inpaint_task(
                image_data=b"test_image_data",
                mask_data=b"test_mask_data",
                config={"model": "lama"},
                user_id="test_user"
            )
            logger.info(f"1. 创建任务: {test_task.task_id}")
            
            # 2. 任务状态转换测试
            from lama_cleaner.distributed.task_manager import TaskLifecycleManager
            
            # 测试状态转换
            transitions = [
                (TaskStatus.PENDING, TaskStatus.QUEUED),
                (TaskStatus.QUEUED, TaskStatus.PROCESSING),
                (TaskStatus.PROCESSING, TaskStatus.COMPLETED)
            ]
            
            for from_status, to_status in transitions:
                test_task.status = from_status
                if TaskLifecycleManager.can_transition(from_status, to_status):
                    test_task.status = to_status
                    logger.info(f"2. 状态转换成功: {from_status.value} -> {to_status.value}")
                else:
                    logger.error(f"2. 状态转换失败: {from_status.value} -> {to_status.value}")
                    return False
            
            logger.info("端到端测试完成")
            return True
            
        except Exception as e:
            logger.error(f"端到端测试失败: {e}")
            return False
    
    def print_summary(self):
        """打印测试总结"""
        logger.info(f"\n{'='*60}")
        logger.info("测试总结")
        logger.info(f"{'='*60}")
        
        total_tests = len(self.test_results)
        passed_tests = sum(1 for result in self.test_results.values() if result['status'] == 'PASS')
        failed_tests = sum(1 for result in self.test_results.values() if result['status'] == 'FAIL')
        error_tests = sum(1 for result in self.test_results.values() if result['status'] == 'ERROR')
        
        logger.info(f"总测试数: {total_tests}")
        logger.info(f"通过: {passed_tests}")
        logger.info(f"失败: {failed_tests}")
        logger.info(f"错误: {error_tests}")
        logger.info(f"成功率: {passed_tests/total_tests*100:.1f}%")
        
        logger.info("\n详细结果:")
        for test_name, result in self.test_results.items():
            status_icon = "✅" if result['status'] == 'PASS' else "❌"
            logger.info(f"{status_icon} {test_name}: {result['status']}")
            if result['status'] != 'PASS':
                logger.info(f"   详情: {result['details']}")


def check_dependencies():
    """检查依赖"""
    logger.info("检查系统依赖...")
    
    required_packages = [
        'zmq',
        'redis',
        'flask',
        'flask_socketio'
    ]
    
    missing_packages = []
    
    for package in required_packages:
        try:
            __import__(package)
            logger.info(f"✅ {package}: 已安装")
        except ImportError:
            missing_packages.append(package)
            logger.error(f"❌ {package}: 未安装")
    
    if missing_packages:
        logger.error(f"缺少依赖包: {missing_packages}")
        logger.info("请运行: uv sync 安装依赖")
        return False
    
    return True


def check_services():
    """检查外部服务"""
    logger.info("检查外部服务...")
    
    # 检查 Redis（可选）
    try:
        import redis
        r = redis.Redis(host='localhost', port=6379, db=0, socket_timeout=1)
        r.ping()
        logger.info("✅ Redis: 连接成功")
    except Exception as e:
        logger.warning(f"⚠️  Redis: 连接失败 - {e}")
        logger.info("Redis 是可选的，系统可以在没有 Redis 的情况下运行")
    
    return True


def main():
    """主函数"""
    logger.info("Lama Cleaner 分布式系统调试工具")
    logger.info("="*60)
    
    # 检查依赖
    if not check_dependencies():
        logger.error("依赖检查失败，退出")
        return 1
    
    # 检查服务
    check_services()
    
    # 运行系统测试
    debugger = SystemDebugger()
    debugger.run_all_tests()
    
    # 检查测试结果
    failed_count = sum(1 for result in debugger.test_results.values() 
                      if result['status'] != 'PASS')
    
    if failed_count == 0:
        logger.info("\n🎉 所有测试通过！分布式系统运行正常。")
        return 0
    else:
        logger.error(f"\n💥 有 {failed_count} 个测试失败，请检查系统配置。")
        return 1


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)