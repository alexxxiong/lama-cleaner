#!/usr/bin/env python3
"""
调试脚本 - 逐步测试每个模块
"""
import sys
import time
import tempfile
from pathlib import Path

def test_module(name, test_func):
    """测试单个模块"""
    print(f"\n{'='*60}")
    print(f"测试: {name}")
    print('='*60)
    try:
        test_func()
        print(f"✅ {name} 测试通过")
        return True
    except Exception as e:
        print(f"❌ {name} 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_privacy_protector():
    """测试隐私保护模块"""
    from lama_cleaner.privacy_protector import (
        privacy_protector, 
        PrivacyConfig,
        DataMasker,
        SensitiveDataDetector
    )
    
    # 测试检测器
    detector = SensitiveDataDetector()
    text = "Email: test@example.com, Phone: 123-456-7890"
    detected = detector.detect(text)
    assert len(detected) > 0, "应该检测到敏感数据"
    
    # 测试脱敏
    config = PrivacyConfig()
    masker = DataMasker(config)
    masked = masker.mask_email("test@example.com")
    assert "@" in masked and "***" in masked, "邮箱应该被脱敏"
    
    # 测试访问控制
    privacy_protector.access_controller.add_user("test_user", "viewer")
    assert privacy_protector.check_access("test_user", "read") == True
    assert privacy_protector.check_access("test_user", "write") == False
    
    print("  - 敏感数据检测: OK")
    print("  - 数据脱敏: OK")
    print("  - 访问控制: OK")

def test_performance_monitor():
    """测试性能监控模块"""
    from lama_cleaner.performance_monitor import (
        performance_monitor,
        ResourceMonitor,
        PerformanceTracker
    )
    
    # 测试资源监控
    monitor = ResourceMonitor()
    metrics = monitor.get_current_metrics()
    assert 'cpu' in metrics, "应该包含CPU指标"
    assert 'memory' in metrics, "应该包含内存指标"
    
    # 测试性能跟踪
    tracker = PerformanceTracker()
    
    @tracker.track_operation("test_func")
    def dummy_func():
        time.sleep(0.01)
        return "ok"
    
    result = dummy_func()
    assert result == "ok", "函数应该正常执行"
    
    report = tracker.get_performance_report()
    assert 'test_func' in report['operations'], "应该记录操作"
    
    print("  - 资源监控: OK")
    print("  - 性能跟踪: OK")
    print("  - 性能报告: OK")

def test_error_tracker():
    """测试错误追踪模块"""
    from lama_cleaner.error_tracker import (
        error_tracker,
        ErrorContext,
        ErrorCategory
    )
    
    # 清空之前的错误
    error_tracker.errors.clear()
    error_tracker.error_index.clear()
    
    # 测试错误追踪
    try:
        raise ValueError("Test error")
    except ValueError as e:
        error_id = error_tracker.track_error(e)
    
    assert error_id.startswith("ERR-"), "错误ID格式不正确"
    
    # 测试错误报告
    report = error_tracker.get_error_report(hours=1)
    assert report['summary']['total_errors'] >= 1, "应该有错误记录"
    
    # 测试去重
    for _ in range(3):
        try:
            raise RuntimeError("Duplicate")
        except RuntimeError as e:
            error_tracker.track_error(e)
    
    report = error_tracker.get_error_report(hours=1)
    unique_count = len([e for e in error_tracker.errors if e.error_message == "Duplicate"])
    assert unique_count == 1, "相同错误应该被去重"
    
    print("  - 错误追踪: OK")
    print("  - 错误报告: OK")
    print("  - 错误去重: OK")

def test_logger_manager():
    """测试日志管理器"""
    from lama_cleaner.logging_config import LoggerManager, LoggingConfig
    from loguru import logger
    
    with tempfile.TemporaryDirectory() as tmpdir:
        # 创建管理器
        log_manager = LoggerManager()
        
        # 配置日志
        config = LoggingConfig(
            level="INFO",
            console_enabled=False,
            file_enabled=True,
            log_directory=tmpdir
        )
        
        log_manager.setup_logging(config=config)
        
        # 写入日志
        logger.info("Test message")
        time.sleep(0.1)  # 等待异步写入
        
        # 检查文件
        log_files = list(Path(tmpdir).glob("*.log"))
        assert len(log_files) > 0, "应该创建日志文件"
        
        # 测试隐私保护
        log_manager.enable_privacy_protection()
        assert log_manager.privacy_enabled == True, "隐私保护应该启用"
        
        # 测试性能监控
        log_manager.start_performance_monitoring(interval=10)
        status = log_manager.get_performance_status()
        assert status['monitoring'] == True, "性能监控应该运行"
        
        # 清理
        log_manager.shutdown()
        logger.remove()
    
    print("  - 日志配置: OK")
    print("  - 文件输出: OK")
    print("  - 隐私保护集成: OK")
    print("  - 性能监控集成: OK")

def test_integration():
    """集成测试"""
    from lama_cleaner.logging_config import LoggerManager
    from loguru import logger
    
    with tempfile.TemporaryDirectory() as tmpdir:
        log_manager = LoggerManager()
        log_manager.config.log_directory = tmpdir
        log_manager.config.file_enabled = True
        log_manager.config.console_enabled = False
        
        # 设置系统
        log_manager.setup_logging()
        log_manager.enable_privacy_protection()
        log_manager.start_performance_monitoring()
        
        # 模拟使用
        logger.info("User test@example.com logged in")
        
        try:
            1/0
        except Exception as e:
            log_manager.track_error(e, operation="division")
        
        # 获取报告
        error_report = log_manager.get_error_report()
        perf_status = log_manager.get_performance_status()
        privacy_report = log_manager.get_privacy_report()
        
        assert error_report['summary']['total_errors'] > 0
        assert perf_status['monitoring'] == True
        assert privacy_report['config']['masking_enabled'] == True
        
        # 清理
        log_manager.shutdown()
        logger.remove()
    
    print("  - 完整流程: OK")
    print("  - 报告生成: OK")
    print("  - 系统集成: OK")

def main():
    """主函数"""
    print("\n" + "="*60)
    print("🔍 日志系统调试测试")
    print("="*60)
    
    results = []
    
    # 逐个测试模块
    tests = [
        ("隐私保护模块", test_privacy_protector),
        ("性能监控模块", test_performance_monitor),
        ("错误追踪模块", test_error_tracker),
        ("日志管理器", test_logger_manager),
        ("系统集成", test_integration)
    ]
    
    for name, test_func in tests:
        result = test_module(name, test_func)
        results.append((name, result))
    
    # 总结
    print("\n" + "="*60)
    print("📊 测试总结")
    print("="*60)
    
    passed = sum(1 for _, r in results if r)
    total = len(results)
    
    for name, result in results:
        status = "✅ 通过" if result else "❌ 失败"
        print(f"  {status} - {name}")
    
    print(f"\n总计: {passed}/{total} 测试通过")
    
    if passed == total:
        print("🎉 所有测试通过！")
    else:
        print("⚠️ 部分测试失败，请检查错误信息")
        sys.exit(1)

if __name__ == "__main__":
    main()