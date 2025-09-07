#!/usr/bin/env python3
"""
错误追踪系统测试脚本
测试错误追踪、分类、统计和报告功能
"""

import time
import random
import threading
from pathlib import Path
import sys

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent))

from lama_cleaner.logging_config import LoggerManager
from lama_cleaner.error_tracker import (
    error_tracker, 
    ErrorContext, 
    ErrorCategory, 
    ErrorSeverity,
    error_analyzer
)
from loguru import logger


def simulate_file_error():
    """模拟文件操作错误"""
    try:
        with open("/nonexistent/file.txt", "r") as f:
            f.read()
    except FileNotFoundError as e:
        error_tracker.track_error(
            e,
            context=ErrorContext(
                operation="file_read",
                custom_data={"file_path": "/nonexistent/file.txt"}
            )
        )
        logger.error(f"文件错误已捕获: {e}")


def simulate_memory_error():
    """模拟内存错误"""
    try:
        # 模拟内存不足
        raise MemoryError("Out of memory while allocating tensor")
    except MemoryError as e:
        error_tracker.track_error(
            e,
            context=ErrorContext(
                operation="tensor_allocation",
                custom_data={"size": "10GB", "device": "GPU"}
            )
        )
        logger.error(f"内存错误已捕获: {e}")


def simulate_network_error():
    """模拟网络错误"""
    try:
        raise ConnectionError("Connection timeout to server api.example.com")
    except ConnectionError as e:
        error_tracker.track_error(
            e,
            context=ErrorContext(
                operation="api_request",
                custom_data={"endpoint": "api.example.com", "timeout": 30}
            )
        )
        logger.error(f"网络错误已捕获: {e}")


def simulate_validation_error():
    """模拟数据验证错误"""
    try:
        value = "invalid_number"
        if not value.isdigit():
            raise ValueError(f"Invalid format: expected number, got {value}")
    except ValueError as e:
        error_tracker.track_error(
            e,
            context=ErrorContext(
                operation="data_validation",
                custom_data={"input": value, "expected": "number"}
            ),
            category=ErrorCategory.VALIDATION,
            severity=ErrorSeverity.LOW
        )
        logger.warning(f"验证错误已捕获: {e}")


def simulate_model_error():
    """模拟模型错误"""
    try:
        raise RuntimeError("CUDA out of memory. Tried to allocate 2.00 GiB")
    except RuntimeError as e:
        error_tracker.track_error(
            e,
            context=ErrorContext(
                operation="model_inference",
                custom_data={
                    "model": "stable-diffusion-v1.5",
                    "batch_size": 4,
                    "resolution": "512x512"
                }
            )
        )
        logger.error(f"模型错误已捕获: {e}")


def simulate_repeated_errors():
    """模拟重复错误（测试去重功能）"""
    logger.info("模拟重复错误...")
    
    for i in range(5):
        try:
            # 故意产生相同的错误
            result = 10 / 0
        except ZeroDivisionError as e:
            error_tracker.track_error(
                e,
                context=ErrorContext(
                    operation="division",
                    custom_data={"iteration": i}
                ),
                category=ErrorCategory.PROCESSING,
                severity=ErrorSeverity.MEDIUM
            )
        time.sleep(0.1)
    
    logger.info("重复错误模拟完成")


def simulate_error_sequence():
    """模拟错误序列（测试模式识别）"""
    logger.info("模拟错误序列...")
    
    # 模拟一个常见的错误序列：网络错误 -> 认证错误 -> 资源错误
    sequence = [
        (ConnectionError("Network timeout"), ErrorCategory.NETWORK),
        (PermissionError("Authentication failed"), ErrorCategory.AUTHENTICATION),
        (MemoryError("Resource exhausted"), ErrorCategory.RESOURCE)
    ]
    
    for _ in range(3):  # 重复序列3次
        for error, category in sequence:
            try:
                raise error
            except Exception as e:
                error_tracker.track_error(e, category=category)
                time.sleep(0.2)
    
    logger.info("错误序列模拟完成")


def simulate_concurrent_errors():
    """模拟并发错误"""
    logger.info("模拟并发错误...")
    
    def worker(worker_id: int):
        errors = [
            FileNotFoundError(f"Worker {worker_id} file not found"),
            ValueError(f"Worker {worker_id} invalid value"),
            ConnectionError(f"Worker {worker_id} connection failed")
        ]
        
        for error in errors:
            try:
                raise error
            except Exception as e:
                error_tracker.track_error(
                    e,
                    context=ErrorContext(
                        operation=f"worker_{worker_id}_task",
                        session_id=f"session_{worker_id}"
                    )
                )
                time.sleep(random.uniform(0.1, 0.3))
    
    threads = []
    for i in range(3):
        t = threading.Thread(target=worker, args=(i,))
        threads.append(t)
        t.start()
    
    for t in threads:
        t.join()
    
    logger.info("并发错误模拟完成")


def test_error_resolution():
    """测试错误解决标记"""
    logger.info("测试错误解决功能...")
    
    # 创建一个错误
    try:
        raise RuntimeError("Test error for resolution")
    except RuntimeError as e:
        error_id = error_tracker.track_error(e)
        logger.info(f"创建错误 ID: {error_id}")
        
        # 标记为已解决
        success = error_tracker.mark_resolved(
            error_id, 
            "问题已通过重启服务解决"
        )
        
        if success:
            logger.success(f"错误 {error_id} 已标记为解决")
        else:
            logger.error(f"无法标记错误 {error_id} 为解决")


def main():
    """主测试函数"""
    # 初始化日志系统
    log_manager = LoggerManager()
    log_manager.setup_logging(level="INFO", enable_file_logging=True)
    
    logger.info("=" * 60)
    logger.info("🚀 开始错误追踪测试")
    logger.info("=" * 60)
    
    # 记录一些操作历史
    error_tracker.add_operation("system_startup", {"version": "1.0.0"})
    error_tracker.add_operation("model_load", {"model": "lama", "device": "cuda"})
    
    try:
        # 测试1: 各种类型的错误
        logger.info("\n📌 测试1: 模拟各种类型的错误")
        simulate_file_error()
        simulate_memory_error()
        simulate_network_error()
        simulate_validation_error()
        simulate_model_error()
        
        # 测试2: 重复错误（去重）
        logger.info("\n📌 测试2: 重复错误去重")
        simulate_repeated_errors()
        
        # 测试3: 错误序列
        logger.info("\n📌 测试3: 错误序列模式")
        simulate_error_sequence()
        
        # 测试4: 并发错误
        logger.info("\n📌 测试4: 并发错误处理")
        simulate_concurrent_errors()
        
        # 测试5: 错误解决标记
        logger.info("\n📌 测试5: 错误解决标记")
        test_error_resolution()
        
        # 等待一下让所有错误都被记录
        time.sleep(1)
        
        # 生成错误报告
        logger.info("\n" + "=" * 60)
        logger.info("📊 错误报告")
        logger.info("=" * 60)
        
        report = error_tracker.get_error_report(hours=1)
        
        # 显示摘要
        summary = report['summary']
        logger.info("📈 错误摘要:")
        logger.info(f"  • 总错误数: {summary['total_errors']}")
        logger.info(f"  • 唯一错误: {summary['unique_errors']}")
        logger.info(f"  • 严重错误: {summary['critical_count']}")
        logger.info(f"  • 未解决数: {summary['unresolved_count']}")
        
        # 按类别统计
        logger.info("\n📁 按类别统计:")
        for category, count in sorted(report['by_category'].items(), 
                                    key=lambda x: x[1], reverse=True):
            logger.info(f"  • {category}: {count}")
        
        # 按严重程度统计
        logger.info("\n⚠️ 按严重程度:")
        for severity, count in report['by_severity'].items():
            severity_emoji = {
                'low': '🟢',
                'medium': '🟡', 
                'high': '🟠',
                'critical': '🔴'
            }.get(severity, '⚪')
            logger.info(f"  {severity_emoji} {severity}: {count}")
        
        # 高频错误
        logger.info("\n🔝 高频错误 Top 5:")
        for error, count in list(report['top_errors'].items())[:5]:
            logger.info(f"  • {error}: {count}次")
        
        # 分析错误模式
        logger.info("\n" + "=" * 60)
        logger.info("🔬 错误模式分析")
        logger.info("=" * 60)
        
        patterns = error_analyzer.analyze_patterns()
        
        if patterns['patterns']:
            logger.info("发现的模式:")
            for pattern in patterns['patterns']:
                logger.info(f"  • {pattern['type']}: {pattern['description']}")
                if 'recommendation' in pattern:
                    logger.info(f"    建议: {pattern['recommendation']}")
        
        if patterns['correlations']:
            logger.info("\n错误相关性:")
            for corr in patterns['correlations']:
                logger.info(f"  • {corr['from']} → {corr['to']} (强度: {corr['strength']})")
                logger.info(f"    {corr['description']}")
        
        # 使用日志管理器生成报告
        logger.info("\n" + "=" * 60)
        logger.info("📋 使用LoggerManager生成错误报告")
        logger.info("=" * 60)
        log_manager.log_error_report(hours=1)
        
        # 导出错误数据
        export_path = "test_error_report.json"
        if error_tracker.export_errors(export_path):
            logger.success(f"✅ 错误数据已导出到: {export_path}")
        
        # 显示最近的操作历史
        logger.info("\n📜 最近操作历史:")
        recent_ops = report.get('recent_operations', [])[-5:]
        for op in recent_ops:
            logger.info(f"  • {op['operation']} - {op.get('details', {})}")
        
    except Exception as e:
        logger.error(f"测试过程中发生错误: {e}")
        import traceback
        traceback.print_exc()
        
    finally:
        logger.info("\n" + "=" * 60)
        logger.success("✅ 错误追踪测试完成！")
        logger.info("=" * 60)
        
        # 清理
        if Path(export_path).exists():
            logger.info(f"清理导出文件: {export_path}")
            Path(export_path).unlink()


if __name__ == "__main__":
    main()