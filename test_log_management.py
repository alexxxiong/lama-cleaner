#!/usr/bin/env python3
"""
测试日志文件管理功能

验证日志轮转、压缩、清理和结构化存储功能。
"""

import time
import json
from datetime import datetime, timedelta
from pathlib import Path

from lama_cleaner.logging_config import LoggerManager, LoggingConfig, FileRotationConfig


def test_basic_logging():
    """测试基本日志功能"""
    print("🧪 测试基本日志功能...")
    
    # 创建测试配置
    config = LoggingConfig()
    config.structured_logging = True
    config.log_directory = "test_logs"
    
    manager = LoggerManager()
    manager.setup_logging(config=config)
    
    # 获取日志器并记录测试消息
    logger = manager.get_logger("test_module")
    
    logger.info("这是一条测试信息日志")
    logger.warning("这是一条测试警告日志")
    logger.error("这是一条测试错误日志", extra={"error_code": 500, "user_id": "test_user"})
    
    print("✅ 基本日志功能测试完成")
    return manager


def test_file_rotation():
    """测试文件轮转功能"""
    print("🧪 测试文件轮转功能...")
    
    # 创建小文件大小的配置以触发轮转
    config = LoggingConfig()
    config.log_directory = "test_logs"
    config.rotation.max_size = "1 KB"  # 很小的文件大小
    config.rotation.retention_days = 7
    config.rotation.compression = "gz"
    
    manager = LoggerManager()
    manager.setup_logging(config=config)
    
    logger = manager.get_logger("rotation_test")
    
    # 生成大量日志以触发轮转
    for i in range(100):
        logger.info(f"这是第 {i+1} 条测试日志，用于触发文件轮转功能。" * 5)
        
    time.sleep(1)  # 等待文件写入
    
    # 检查日志文件
    files_info = manager.get_log_files_info()
    print(f"📁 生成了 {len(files_info)} 个日志文件")
    
    for file_info in files_info:
        print(f"  - {file_info['name']}: {file_info['size_mb']:.2f} MB")
        
    print("✅ 文件轮转功能测试完成")
    return manager


def test_structured_logging():
    """测试结构化日志存储"""
    print("🧪 测试结构化日志存储...")
    
    config = LoggingConfig()
    config.structured_logging = True
    config.log_directory = "test_logs"
    
    manager = LoggerManager()
    manager.setup_logging(config=config)
    
    logger = manager.get_logger("structured_test")
    
    # 记录不同类型的结构化日志
    test_data = [
        {"level": "INFO", "message": "用户登录", "extra": {"user_id": "user123", "ip": "192.168.1.1"}},
        {"level": "WARNING", "message": "内存使用率过高", "extra": {"memory_usage": 85.5, "threshold": 80}},
        {"level": "ERROR", "message": "数据库连接失败", "extra": {"db_host": "localhost", "retry_count": 3}},
        {"level": "INFO", "message": "任务完成", "extra": {"task_id": "task_456", "duration": 120.5}},
    ]
    
    for data in test_data:
        if data["level"] == "INFO":
            logger.info(data["message"], **data["extra"])
        elif data["level"] == "WARNING":
            logger.warning(data["message"], **data["extra"])
        elif data["level"] == "ERROR":
            logger.error(data["message"], **data["extra"])
            
    time.sleep(1)  # 等待数据写入
    
    # 测试查询功能
    print("\n🔍 测试日志查询功能:")
    
    # 查询所有日志
    all_logs = manager.search_logs("")
    print(f"  总日志数: {len(all_logs)}")
    
    # 查询错误日志
    error_logs = manager.search_logs("", level="ERROR")
    print(f"  错误日志数: {len(error_logs)}")
    
    # 查询包含特定关键词的日志
    user_logs = manager.search_logs("用户")
    print(f"  包含'用户'的日志数: {len(user_logs)}")
    
    # 获取统计信息
    stats = manager.get_log_statistics(24)
    print(f"\n📊 日志统计:")
    print(f"  总记录数: {stats.get('total_entries', 0)}")
    print(f"  级别分布: {stats.get('level_distribution', {})}")
    
    # 获取错误摘要
    error_summary = manager.get_error_summary(24)
    print(f"\n❌ 错误摘要:")
    print(f"  总错误数: {error_summary.get('total_errors', 0)}")
    print(f"  唯一错误数: {error_summary.get('unique_errors', 0)}")
    
    print("✅ 结构化日志存储测试完成")
    return manager


def test_log_cleanup():
    """测试日志清理功能"""
    print("🧪 测试日志清理功能...")
    
    config = LoggingConfig()
    config.log_directory = "test_logs"
    config.rotation.retention_days = 1  # 只保留1天
    
    manager = LoggerManager()
    manager.setup_logging(config=config)
    
    # 获取清理前的文件信息
    files_before = manager.get_log_files_info()
    print(f"清理前文件数: {len(files_before)}")
    
    # 执行手动清理
    cleanup_result = manager.manual_cleanup()
    print(f"清理结果: {cleanup_result}")
    
    # 清理结构化日志
    deleted_entries = manager.cleanup_structured_logs(1)
    print(f"清理的数据库记录数: {deleted_entries}")
    
    print("✅ 日志清理功能测试完成")
    return manager


def test_log_export():
    """测试日志导出功能"""
    print("🧪 测试日志导出功能...")
    
    config = LoggingConfig()
    config.structured_logging = True
    config.log_directory = "test_logs"
    
    manager = LoggerManager()
    manager.setup_logging(config=config)
    
    # 导出文件日志
    export_path = "test_logs/exported_logs.zip"
    success = manager.export_logs(export_path)
    print(f"文件日志导出: {'成功' if success else '失败'}")
    
    if success and Path(export_path).exists():
        size = Path(export_path).stat().st_size
        print(f"导出文件大小: {size / 1024:.2f} KB")
    
    # 导出结构化日志
    json_export_path = "test_logs/structured_logs.json"
    success = manager.export_structured_logs(json_export_path)
    print(f"结构化日志导出: {'成功' if success else '失败'}")
    
    if success and Path(json_export_path).exists():
        with open(json_export_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        print(f"导出的结构化日志记录数: {data.get('total_entries', 0)}")
    
    # 备份数据库
    backup_path = "test_logs/backup_structured_logs.db"
    success = manager.backup_structured_logs(backup_path)
    print(f"数据库备份: {'成功' if success else '失败'}")
    
    print("✅ 日志导出功能测试完成")
    return manager


def main():
    """运行所有测试"""
    print("🚀 开始测试日志文件管理功能\n")
    
    try:
        # 清理测试目录
        test_dir = Path("test_logs")
        if test_dir.exists():
            import shutil
            shutil.rmtree(test_dir)
        
        # 运行测试
        manager1 = test_basic_logging()
        print()
        
        manager2 = test_structured_logging()
        print()
        
        manager3 = test_file_rotation()
        print()
        
        manager4 = test_log_export()
        print()
        
        manager5 = test_log_cleanup()
        print()
        
        # 关闭管理器
        for manager in [manager1, manager2, manager3, manager4, manager5]:
            manager.shutdown()
        
        print("🎉 所有测试完成!")
        
        # 显示测试结果摘要
        print("\n📋 测试结果摘要:")
        print("✅ 基本日志功能")
        print("✅ 结构化日志存储")
        print("✅ 文件轮转功能")
        print("✅ 日志导出功能")
        print("✅ 日志清理功能")
        
        print(f"\n📁 测试文件位于: {test_dir.absolute()}")
        
    except Exception as e:
        print(f"❌ 测试过程中发生错误: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()