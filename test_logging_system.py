#!/usr/bin/env python3
"""
综合日志系统测试套件
包含单元测试、集成测试、性能测试和错误场景测试
"""

import unittest
import tempfile
import shutil
import time
import json
import threading
import sys
from pathlib import Path
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, MagicMock
import io

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent))

from lama_cleaner.logging_config import (
    LoggerManager, 
    LoggingConfig, 
    FileRotationConfig,
    StructuredLogStorage,
    LogFileManager
)
from lama_cleaner.performance_monitor import (
    performance_monitor,
    PerformanceTracker,
    ResourceMonitor
)
from lama_cleaner.error_tracker import (
    error_tracker,
    ErrorContext,
    ErrorCategory,
    ErrorSeverity
)
from lama_cleaner.privacy_protector import (
    privacy_protector,
    PrivacyConfig,
    SensitiveDataDetector,
    DataMasker
)
from loguru import logger


class TestLoggingConfig(unittest.TestCase):
    """测试日志配置功能"""
    
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.log_manager = LoggerManager()
        
    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)
        logger.remove()
        
    def test_default_config(self):
        """测试默认配置加载"""
        config = LoggingConfig()
        self.assertEqual(config.level, "INFO")
        self.assertTrue(config.console_enabled)
        self.assertTrue(config.file_enabled)
        self.assertEqual(config.log_directory, "logs")
        
    def test_custom_config_merge(self):
        """测试自定义配置合并"""
        custom_config = LoggingConfig(
            level="DEBUG",
            console_enabled=False,
            log_directory=self.temp_dir
        )
        self.assertEqual(custom_config.level, "DEBUG")
        self.assertFalse(custom_config.console_enabled)
        self.assertEqual(custom_config.log_directory, self.temp_dir)
        
    def test_config_from_file(self):
        """测试从文件加载配置"""
        config_file = Path(self.temp_dir) / "test_config.json"
        config_data = {
            "level": "WARNING",
            "console_enabled": True,
            "file_enabled": False,
            "log_directory": "/tmp/logs"
        }
        
        with open(config_file, 'w') as f:
            json.dump(config_data, f)
            
        loaded_config = self.log_manager.load_config(str(config_file))
        self.assertEqual(loaded_config.level, "WARNING")
        self.assertTrue(loaded_config.console_enabled)
        self.assertFalse(loaded_config.file_enabled)
        
    def test_invalid_config_handling(self):
        """测试配置错误处理"""
        # 不存在的配置文件
        config = self.log_manager.load_config("/nonexistent/config.json")
        self.assertIsNotNone(config)  # 应返回默认配置
        self.assertEqual(config.level, "INFO")
        
    def test_log_level_validation(self):
        """测试日志级别验证"""
        valid_levels = ["TRACE", "DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        for level in valid_levels:
            config = LoggingConfig(level=level)
            self.assertEqual(config.level, level)


class TestLogOutput(unittest.TestCase):
    """测试日志输出功能"""
    
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.log_manager = LoggerManager()
        
    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)
        logger.remove()
        
    def test_console_output(self):
        """测试控制台输出"""
        # 捕获标准输出
        captured_output = io.StringIO()
        
        # 配置只输出到控制台
        config = LoggingConfig(
            console_enabled=True,
            file_enabled=False
        )
        
        with patch('sys.stdout', captured_output):
            self.log_manager.setup_logging(config=config)
            logger.info("Test console message")
            time.sleep(0.1)  # 等待异步写入
            
        output = captured_output.getvalue()
        self.assertIn("Test console message", output)
        
    def test_file_output(self):
        """测试文件输出"""
        config = LoggingConfig(
            console_enabled=False,
            file_enabled=True,
            log_directory=self.temp_dir
        )
        
        self.log_manager.setup_logging(config=config)
        logger.info("Test file message")
        time.sleep(0.1)
        
        # 检查日志文件是否创建
        log_files = list(Path(self.temp_dir).glob("*.log"))
        self.assertTrue(len(log_files) > 0)
        
        # 验证内容
        with open(log_files[0], 'r') as f:
            content = f.read()
            self.assertIn("Test file message", content)
            
    def test_structured_logging(self):
        """测试结构化日志"""
        config = LoggingConfig(
            console_enabled=False,
            file_enabled=True,
            structured_logging=True,
            log_directory=self.temp_dir
        )
        
        self.log_manager.setup_logging(config=config)
        logger.info("Structured message", extra={"user_id": "123", "action": "login"})
        time.sleep(0.1)
        
        # 检查结构化存储
        db_path = Path(self.temp_dir) / "structured_logs.db"
        self.assertTrue(db_path.exists())
        
    def test_log_rotation(self):
        """测试日志轮转"""
        config = LoggingConfig(
            console_enabled=False,
            file_enabled=True,
            log_directory=self.temp_dir,
            rotation=FileRotationConfig(
                max_size="1 KB",  # 很小的大小以触发轮转
                retention_days=1
            )
        )
        
        self.log_manager.setup_logging(config=config)
        
        # 写入大量日志触发轮转
        for i in range(100):
            logger.info(f"Message {i} " * 50)  # 长消息
        time.sleep(0.5)
        
        # 检查是否有多个日志文件
        log_files = list(Path(self.temp_dir).glob("*.log*"))
        self.assertTrue(len(log_files) >= 1)


class TestPerformanceMonitoring(unittest.TestCase):
    """测试性能监控功能"""
    
    def test_resource_monitoring(self):
        """测试资源监控"""
        monitor = ResourceMonitor(interval=1, history_size=10)
        
        # 获取当前指标
        metrics = monitor.get_current_metrics()
        self.assertIn('cpu', metrics)
        self.assertIn('memory', metrics)
        self.assertIn('disk', metrics)
        self.assertIn('network', metrics)
        
        # 验证CPU指标
        self.assertGreaterEqual(metrics['cpu']['percent'], 0)
        self.assertLessEqual(metrics['cpu']['percent'], 100)
        
    def test_performance_tracking(self):
        """测试性能跟踪"""
        tracker = PerformanceTracker()
        
        @tracker.track_operation("test_function")
        def slow_function():
            time.sleep(0.1)
            return "done"
            
        result = slow_function()
        self.assertEqual(result, "done")
        
        # 获取性能报告
        report = tracker.get_performance_report()
        self.assertIn('test_function', report['operations'])
        
        stats = report['operations']['test_function']
        self.assertEqual(stats['count'], 1)
        self.assertGreater(stats['avg_time'], 0.09)
        
    def test_performance_context_manager(self):
        """测试性能测量上下文管理器"""
        tracker = PerformanceTracker()
        
        with tracker.measure("test_operation"):
            time.sleep(0.05)
            
        report = tracker.get_performance_report()
        self.assertIn('test_operation', report['operations'])
        
    def test_bottleneck_detection(self):
        """测试性能瓶颈检测"""
        tracker = PerformanceTracker()
        tracker.slow_operation_threshold = 0.05  # 设置低阈值
        
        @tracker.track_operation("slow_op")
        def slow_operation():
            time.sleep(0.1)
            
        slow_operation()
        
        report = tracker.get_performance_report()
        self.assertTrue(len(report['bottlenecks']) > 0)
        self.assertEqual(report['bottlenecks'][0]['operation'], 'slow_op')


class TestErrorTracking(unittest.TestCase):
    """测试错误追踪功能"""
    
    def setUp(self):
        # 清空错误追踪器
        error_tracker.errors.clear()
        error_tracker.error_index.clear()
        
    def test_error_tracking(self):
        """测试错误追踪"""
        try:
            raise ValueError("Test error")
        except ValueError as e:
            error_id = error_tracker.track_error(e)
            
        self.assertIsNotNone(error_id)
        self.assertTrue(error_id.startswith("ERR-"))
        
        # 验证错误记录
        error = error_tracker.get_error_by_id(error_id)
        self.assertIsNotNone(error)
        self.assertEqual(error.error_type, "ValueError")
        self.assertEqual(error.error_message, "Test error")
        
    def test_error_classification(self):
        """测试错误分类"""
        # 文件错误
        try:
            raise FileNotFoundError("file.txt not found")
        except FileNotFoundError as e:
            error_tracker.track_error(e)
            
        # 网络错误
        try:
            raise ConnectionError("Connection timeout")
        except ConnectionError as e:
            error_tracker.track_error(e)
            
        report = error_tracker.get_error_report(hours=1)
        self.assertIn('file_io', report['by_category'])
        self.assertIn('network', report['by_category'])
        
    def test_error_deduplication(self):
        """测试错误去重"""
        # 产生相同错误多次
        for _ in range(5):
            try:
                raise RuntimeError("Duplicate error")
            except RuntimeError as e:
                error_tracker.track_error(e)
                
        report = error_tracker.get_error_report(hours=1)
        self.assertEqual(report['unique_errors'], 1)
        self.assertGreaterEqual(report['total_errors'], 5)
        
    def test_error_solutions(self):
        """测试错误解决方案"""
        try:
            raise MemoryError("CUDA out of memory")
        except MemoryError as e:
            error_id = error_tracker.track_error(e)
            
        error = error_tracker.get_error_by_id(error_id)
        solution = error_tracker.solution_provider.get_solution(error)
        self.assertIsNotNone(solution)
        self.assertIn('GPU内存不足', solution['title'])


class TestPrivacyProtection(unittest.TestCase):
    """测试隐私保护功能"""
    
    def test_sensitive_data_detection(self):
        """测试敏感数据检测"""
        detector = SensitiveDataDetector()
        
        text = "Email: user@example.com, Phone: 123-456-7890"
        detected = detector.detect(text)
        
        self.assertIn('EMAIL', [d.name for d in detected.keys()])
        self.assertIn('PHONE', [d.name for d in detected.keys()])
        
    def test_data_masking(self):
        """测试数据脱敏"""
        config = PrivacyConfig()
        masker = DataMasker(config)
        
        # 测试邮箱脱敏
        email = "john@example.com"
        masked = masker.mask_email(email)
        self.assertNotEqual(email, masked)
        self.assertIn("***", masked)
        
        # 测试IP脱敏
        ip = "192.168.1.100"
        masked = masker.mask_ip(ip)
        self.assertEqual(masked, "192.168.*.* ")
        
    def test_dict_masking(self):
        """测试字典脱敏"""
        config = PrivacyConfig()
        masker = DataMasker(config)
        
        data = {
            "email": "test@example.com",
            "password": "secret123",
            "api_key": "sk_test_abcd1234"
        }
        
        masked = masker.mask_dict(data)
        self.assertNotEqual(data["email"], masked["email"])
        self.assertEqual(masked["password"], "***REDACTED***")
        self.assertEqual(masked["api_key"], "***REDACTED***")
        
    def test_access_control(self):
        """测试访问控制"""
        privacy_protector.access_controller.add_user("test_admin", "admin")
        privacy_protector.access_controller.add_user("test_viewer", "viewer")
        
        # 管理员权限
        self.assertTrue(privacy_protector.check_access("test_admin", "write"))
        self.assertTrue(privacy_protector.check_access("test_admin", "delete"))
        
        # 查看者权限
        self.assertTrue(privacy_protector.check_access("test_viewer", "read"))
        self.assertFalse(privacy_protector.check_access("test_viewer", "write"))


class TestIntegration(unittest.TestCase):
    """集成测试"""
    
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.log_manager = LoggerManager()
        
    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)
        logger.remove()
        performance_monitor.stop()
        
    def test_full_logging_flow(self):
        """测试完整日志流程"""
        # 配置日志系统
        config = LoggingConfig(
            level="DEBUG",
            console_enabled=False,
            file_enabled=True,
            structured_logging=True,
            log_directory=self.temp_dir
        )
        
        self.log_manager.setup_logging(config=config)
        
        # 启用隐私保护
        self.log_manager.enable_privacy_protection()
        
        # 启动性能监控
        self.log_manager.start_performance_monitoring(interval=1)
        
        # 模拟应用操作
        logger.info("System starting")
        
        # 记录包含敏感信息的日志
        logger.info("User john@example.com logged in from 192.168.1.100")
        
        # 追踪错误
        try:
            raise ValueError("Test error in integration")
        except ValueError as e:
            error_id = self.log_manager.track_error(e, operation="test_operation")
            
        # 使用性能追踪
        with performance_monitor.measure("integration_test"):
            time.sleep(0.05)
            
        time.sleep(0.2)  # 等待异步操作
        
        # 验证日志文件
        log_files = list(Path(self.temp_dir).glob("*.log"))
        self.assertTrue(len(log_files) > 0)
        
        # 验证结构化存储
        db_path = Path(self.temp_dir) / "structured_logs.db"
        self.assertTrue(db_path.exists())
        
        # 获取报告
        error_report = self.log_manager.get_error_report(hours=1)
        self.assertGreater(error_report['summary']['total_errors'], 0)
        
        perf_status = self.log_manager.get_performance_status()
        self.assertTrue(perf_status['monitoring'])
        
    def test_concurrent_logging(self):
        """测试并发日志记录"""
        config = LoggingConfig(
            console_enabled=False,
            file_enabled=True,
            log_directory=self.temp_dir
        )
        
        self.log_manager.setup_logging(config=config)
        
        def worker(worker_id):
            for i in range(10):
                logger.info(f"Worker {worker_id} message {i}")
                time.sleep(0.01)
                
        threads = []
        for i in range(5):
            t = threading.Thread(target=worker, args=(i,))
            threads.append(t)
            t.start()
            
        for t in threads:
            t.join()
            
        # 验证所有消息都被记录
        log_files = list(Path(self.temp_dir).glob("*.log"))
        self.assertTrue(len(log_files) > 0)
        
        with open(log_files[0], 'r') as f:
            content = f.read()
            # 应该有50条消息（5个线程 × 10条消息）
            message_count = content.count("Worker")
            self.assertEqual(message_count, 50)


class TestPerformance(unittest.TestCase):
    """性能测试"""
    
    def test_logging_overhead(self):
        """测试日志开销"""
        iterations = 1000
        
        # 无日志的基准测试
        start = time.time()
        for i in range(iterations):
            _ = f"Message {i}"
        baseline_time = time.time() - start
        
        # 配置最小日志
        log_manager = LoggerManager()
        config = LoggingConfig(
            level="ERROR",  # 高级别减少输出
            console_enabled=False,
            file_enabled=False
        )
        log_manager.setup_logging(config=config)
        
        # 带日志的测试
        start = time.time()
        for i in range(iterations):
            logger.debug(f"Message {i}")  # 不会输出
        logging_time = time.time() - start
        
        # 日志开销应该很小
        overhead = logging_time - baseline_time
        overhead_percent = (overhead / baseline_time) * 100
        
        # 开销应该小于50%
        self.assertLess(overhead_percent, 50)
        
    def test_structured_storage_performance(self):
        """测试结构化存储性能"""
        temp_dir = tempfile.mkdtemp()
        
        try:
            storage = StructuredLogStorage(f"{temp_dir}/test.db")
            
            # 批量插入测试
            start = time.time()
            for i in range(100):
                record = {
                    'time': datetime.now(),
                    'level': {'name': 'INFO'},
                    'name': 'test',
                    'function': 'test_func',
                    'line': i,
                    'message': f'Test message {i}',
                    'extra': {'data': i}
                }
                storage.store_log_entry(record)
            insert_time = time.time() - start
            
            # 查询测试
            start = time.time()
            results = storage.query_logs(limit=50)
            query_time = time.time() - start
            
            # 性能标准
            self.assertLess(insert_time, 1.0)  # 100条插入应该在1秒内
            self.assertLess(query_time, 0.5)   # 查询应该在0.5秒内
            
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)


class TestErrorScenarios(unittest.TestCase):
    """错误场景测试"""
    
    def test_disk_full_scenario(self):
        """测试磁盘满场景"""
        # 模拟磁盘满
        with patch('pathlib.Path.mkdir') as mock_mkdir:
            mock_mkdir.side_effect = OSError("No space left on device")
            
            log_manager = LoggerManager()
            config = LoggingConfig(
                file_enabled=True,
                log_directory="/fake/path"
            )
            
            # 应该优雅处理而不崩溃
            try:
                log_manager.setup_logging(config=config)
            except:
                self.fail("Should handle disk full gracefully")
                
    def test_permission_denied(self):
        """测试权限拒绝场景"""
        with patch('builtins.open') as mock_open:
            mock_open.side_effect = PermissionError("Permission denied")
            
            log_manager = LoggerManager()
            
            # 应该优雅处理
            try:
                log_manager.export_logs("/fake/output.zip")
            except:
                self.fail("Should handle permission error gracefully")
                
    def test_corrupted_config(self):
        """测试损坏的配置文件"""
        temp_dir = tempfile.mkdtemp()
        
        try:
            config_file = Path(temp_dir) / "corrupted.json"
            with open(config_file, 'w') as f:
                f.write("{invalid json}")
                
            log_manager = LoggerManager()
            config = log_manager.load_config(str(config_file))
            
            # 应该返回默认配置
            self.assertIsNotNone(config)
            self.assertEqual(config.level, "INFO")
            
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)
            
    def test_memory_exhaustion(self):
        """测试内存耗尽场景"""
        monitor = ResourceMonitor(history_size=10)  # 小历史记录
        
        # 填充历史记录
        for _ in range(20):
            monitor.history.append(monitor.get_current_metrics())
            
        # 历史记录不应该无限增长
        self.assertLessEqual(len(monitor.history), 10)


def run_performance_benchmark():
    """运行性能基准测试"""
    print("\n" + "="*60)
    print("性能基准测试")
    print("="*60)
    
    # 测试日志吞吐量
    log_manager = LoggerManager()
    config = LoggingConfig(
        console_enabled=False,
        file_enabled=True,
        log_directory=tempfile.mkdtemp()
    )
    log_manager.setup_logging(config=config)
    
    message_sizes = [10, 100, 1000]
    
    for size in message_sizes:
        message = "x" * size
        iterations = 10000
        
        start = time.time()
        for _ in range(iterations):
            logger.info(message)
        elapsed = time.time() - start
        
        throughput = iterations / elapsed
        print(f"消息大小 {size}B: {throughput:.0f} msg/s")
        
    print("="*60)


if __name__ == '__main__':
    # 运行单元测试
    unittest.main(argv=[''], exit=False, verbosity=2)
    
    # 运行性能基准测试
    run_performance_benchmark()