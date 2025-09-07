#!/usr/bin/env python3
"""
性能监控系统测试脚本
测试性能监控的各项功能
"""

import time
import random
import threading
from pathlib import Path
import sys

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent))

from lama_cleaner.logging_config import LoggerManager
from lama_cleaner.performance_monitor import (
    performance_monitor, 
    track_performance, 
    measure_performance
)
from loguru import logger


# 测试函数：模拟CPU密集型操作
@track_performance("cpu_intensive_task")
def cpu_intensive_task(duration: float = 2.0):
    """模拟CPU密集型任务"""
    logger.info(f"执行CPU密集型任务 ({duration}秒)")
    start = time.time()
    while time.time() - start < duration:
        # 执行一些计算
        _ = sum(i**2 for i in range(10000))
    return "CPU任务完成"


# 测试函数：模拟内存密集型操作
@track_performance("memory_intensive_task")
def memory_intensive_task(size_mb: int = 100):
    """模拟内存密集型任务"""
    logger.info(f"执行内存密集型任务 (分配{size_mb}MB)")
    # 分配大量内存
    data = bytearray(size_mb * 1024 * 1024)
    # 写入一些数据
    for i in range(0, len(data), 1024):
        data[i] = random.randint(0, 255)
    time.sleep(1)
    return f"分配了{size_mb}MB内存"


# 测试函数：模拟慢操作
@track_performance("slow_operation")
def slow_operation(sleep_time: float = 6.0):
    """模拟慢操作（超过阈值）"""
    logger.info(f"执行慢操作 ({sleep_time}秒)")
    time.sleep(sleep_time)
    return "慢操作完成"


# 测试函数：模拟快速操作
@track_performance("fast_operation")
def fast_operation():
    """模拟快速操作"""
    time.sleep(0.1)
    return "快速操作完成"


# 测试函数：模拟会失败的操作
@track_performance("failing_operation")
def failing_operation():
    """模拟会失败的操作"""
    logger.info("执行会失败的操作")
    time.sleep(0.5)
    raise ValueError("模拟的错误")


# 测试上下文管理器
def test_context_manager():
    """测试性能测量上下文管理器"""
    logger.info("测试上下文管理器")
    
    with measure_performance("context_test_1"):
        time.sleep(1)
        logger.info("上下文测试1执行中")
        
    with measure_performance("context_test_2"):
        # 模拟一些内存分配
        data = [i for i in range(1000000)]
        time.sleep(0.5)
        logger.info("上下文测试2执行中")


# 测试并发操作
def test_concurrent_operations():
    """测试并发操作的性能跟踪"""
    logger.info("测试并发操作")
    
    def worker(worker_id: int):
        for i in range(3):
            with measure_performance(f"worker_{worker_id}_task_{i}"):
                time.sleep(random.uniform(0.1, 0.5))
                
    threads = []
    for i in range(3):
        t = threading.Thread(target=worker, args=(i,))
        threads.append(t)
        t.start()
        
    for t in threads:
        t.join()
        
    logger.info("并发操作完成")


def main():
    """主测试函数"""
    # 初始化日志系统
    log_manager = LoggerManager()
    log_manager.setup_logging(level="INFO", enable_file_logging=True)
    
    logger.info("=" * 60)
    logger.info("🚀 开始性能监控测试")
    logger.info("=" * 60)
    
    # 启动性能监控
    log_manager.start_performance_monitoring(interval=2)
    
    try:
        # 测试1: CPU密集型任务
        logger.info("\n📌 测试1: CPU密集型任务")
        result = cpu_intensive_task(1.5)
        logger.success(f"结果: {result}")
        
        # 测试2: 内存密集型任务
        logger.info("\n📌 测试2: 内存密集型任务")
        result = memory_intensive_task(50)
        logger.success(f"结果: {result}")
        
        # 测试3: 慢操作（触发警告）
        logger.info("\n📌 测试3: 慢操作")
        result = slow_operation(3)
        logger.success(f"结果: {result}")
        
        # 测试4: 快速操作
        logger.info("\n📌 测试4: 快速操作批量执行")
        for i in range(5):
            result = fast_operation()
        logger.success("快速操作批量执行完成")
        
        # 测试5: 失败的操作
        logger.info("\n📌 测试5: 失败的操作")
        try:
            failing_operation()
        except ValueError as e:
            logger.error(f"预期的错误: {e}")
            
        # 测试6: 上下文管理器
        logger.info("\n📌 测试6: 上下文管理器")
        test_context_manager()
        
        # 测试7: 并发操作
        logger.info("\n📌 测试7: 并发操作")
        test_concurrent_operations()
        
        # 等待一段时间让监控收集更多数据
        logger.info("\n⏳ 等待5秒收集更多监控数据...")
        time.sleep(5)
        
        # 获取并显示性能状态
        logger.info("\n" + "=" * 60)
        logger.info("📊 性能监控状态")
        logger.info("=" * 60)
        
        status = log_manager.get_performance_status()
        
        # 显示资源摘要
        resource_summary = status.get('resource_summary', {})
        if resource_summary:
            logger.info("🖥️ 资源使用摘要:")
            logger.info(f"  • CPU平均使用率: {resource_summary.get('cpu_avg', 0):.1f}%")
            logger.info(f"  • 内存平均使用率: {resource_summary.get('memory_avg', 0):.1f}%")
            logger.info(f"  • 磁盘使用率: {resource_summary.get('disk_usage', 0):.1f}%")
            logger.info(f"  • 趋势: {resource_summary.get('trend', 'unknown')}")
        
        # 显示性能报告
        perf_report = status.get('performance_report', {})
        if perf_report.get('operations'):
            logger.info("\n⚡ 操作性能统计:")
            for name, stats in perf_report['operations'].items():
                logger.info(f"  • {name}:")
                logger.info(f"    - 执行次数: {stats['count']}")
                logger.info(f"    - 平均耗时: {stats['avg_time']:.3f}秒")
                logger.info(f"    - 最小/最大: {stats['min_time']:.3f}s / {stats['max_time']:.3f}s")
                if stats['error_rate'] > 0:
                    logger.warning(f"    - 错误率: {stats['error_rate']:.1f}%")
        
        # 显示性能瓶颈
        if perf_report.get('bottlenecks'):
            logger.warning("\n⚠️ 检测到的性能瓶颈:")
            for bottleneck in perf_report['bottlenecks']:
                logger.warning(f"  • {bottleneck['operation']}: 平均{bottleneck['avg_time']:.2f}秒")
        
        # 生成完整的性能报告
        logger.info("\n" + "=" * 60)
        logger.info("📈 生成完整性能报告")
        logger.info("=" * 60)
        log_manager.log_performance_report()
        
    except Exception as e:
        logger.error(f"测试过程中发生错误: {e}")
        import traceback
        traceback.print_exc()
        
    finally:
        # 停止性能监控
        logger.info("\n🛑 停止性能监控")
        log_manager.stop_performance_monitoring()
        
        # 关闭日志管理器
        log_manager.shutdown()
        
        logger.info("\n" + "=" * 60)
        logger.success("✅ 性能监控测试完成！")
        logger.info("=" * 60)


if __name__ == "__main__":
    main()