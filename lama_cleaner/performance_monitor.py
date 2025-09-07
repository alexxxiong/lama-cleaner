"""
性能监控模块 - 监控系统资源使用和操作性能
"""
import time
import psutil
import threading
from typing import Dict, Any, Optional, List, Callable
from datetime import datetime, timedelta
from functools import wraps
from contextlib import contextmanager
from collections import deque
from loguru import logger

try:
    import GPUtil
    GPU_AVAILABLE = True
except ImportError:
    GPU_AVAILABLE = False
    logger.warning("GPUtil not available, GPU monitoring disabled")


class ResourceMonitor:
    """系统资源监控器"""
    
    def __init__(self, interval: int = 5, history_size: int = 100):
        """
        初始化资源监控器
        
        Args:
            interval: 监控间隔（秒）
            history_size: 历史记录保留数量
        """
        self.interval = interval
        self.history_size = history_size
        self.history = deque(maxlen=history_size)
        self.monitoring = False
        self.monitor_thread = None
        self.thresholds = {
            'cpu': 80.0,  # CPU使用率阈值
            'memory': 85.0,  # 内存使用率阈值
            'disk': 90.0,  # 磁盘使用率阈值
            'gpu_memory': 90.0  # GPU内存使用率阈值
        }
        
    def start(self):
        """启动资源监控"""
        if not self.monitoring:
            self.monitoring = True
            self.monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
            self.monitor_thread.start()
            logger.info("🚀 资源监控已启动")
            
    def stop(self):
        """停止资源监控"""
        self.monitoring = False
        if self.monitor_thread:
            self.monitor_thread.join(timeout=2)
        logger.info("🛑 资源监控已停止")
        
    def _monitor_loop(self):
        """监控循环"""
        while self.monitoring:
            try:
                metrics = self.get_current_metrics()
                self.history.append(metrics)
                self._check_thresholds(metrics)
                time.sleep(self.interval)
            except Exception as e:
                logger.error(f"资源监控错误: {e}")
                
    def get_current_metrics(self) -> Dict[str, Any]:
        """获取当前系统资源使用情况"""
        metrics = {
            'timestamp': datetime.now().isoformat(),
            'cpu': {
                'percent': psutil.cpu_percent(interval=1),
                'count': psutil.cpu_count(),
                'freq': psutil.cpu_freq().current if psutil.cpu_freq() else 0
            },
            'memory': {
                'percent': psutil.virtual_memory().percent,
                'used': psutil.virtual_memory().used / (1024**3),  # GB
                'available': psutil.virtual_memory().available / (1024**3),  # GB
                'total': psutil.virtual_memory().total / (1024**3)  # GB
            },
            'disk': self._get_disk_usage(),
            'network': self._get_network_stats(),
            'processes': len(psutil.pids())
        }
        
        # GPU监控
        if GPU_AVAILABLE:
            metrics['gpu'] = self._get_gpu_metrics()
            
        return metrics
        
    def _get_disk_usage(self) -> Dict[str, Any]:
        """获取磁盘使用情况"""
        disk = psutil.disk_usage('/')
        return {
            'percent': disk.percent,
            'used': disk.used / (1024**3),  # GB
            'free': disk.free / (1024**3),  # GB
            'total': disk.total / (1024**3)  # GB
        }
        
    def _get_network_stats(self) -> Dict[str, Any]:
        """获取网络统计"""
        net = psutil.net_io_counters()
        return {
            'bytes_sent': net.bytes_sent / (1024**2),  # MB
            'bytes_recv': net.bytes_recv / (1024**2),  # MB
            'packets_sent': net.packets_sent,
            'packets_recv': net.packets_recv
        }
        
    def _get_gpu_metrics(self) -> List[Dict[str, Any]]:
        """获取GPU指标"""
        gpus = []
        try:
            for gpu in GPUtil.getGPUs():
                gpus.append({
                    'id': gpu.id,
                    'name': gpu.name,
                    'load': gpu.load * 100,
                    'memory_percent': gpu.memoryUtil * 100,
                    'memory_used': gpu.memoryUsed,
                    'memory_total': gpu.memoryTotal,
                    'temperature': gpu.temperature
                })
        except Exception as e:
            logger.debug(f"获取GPU信息失败: {e}")
        return gpus
        
    def _check_thresholds(self, metrics: Dict[str, Any]):
        """检查资源使用阈值"""
        # CPU检查
        if metrics['cpu']['percent'] > self.thresholds['cpu']:
            logger.warning(f"⚠️ CPU使用率过高: {metrics['cpu']['percent']:.1f}%")
            
        # 内存检查
        if metrics['memory']['percent'] > self.thresholds['memory']:
            logger.warning(f"⚠️ 内存使用率过高: {metrics['memory']['percent']:.1f}%")
            
        # 磁盘检查
        if metrics['disk']['percent'] > self.thresholds['disk']:
            logger.warning(f"⚠️ 磁盘使用率过高: {metrics['disk']['percent']:.1f}%")
            
        # GPU检查
        if GPU_AVAILABLE and 'gpu' in metrics:
            for gpu in metrics['gpu']:
                if gpu['memory_percent'] > self.thresholds['gpu_memory']:
                    logger.warning(f"⚠️ GPU {gpu['id']} 内存使用率过高: {gpu['memory_percent']:.1f}%")
                    
    def get_resource_summary(self) -> Dict[str, Any]:
        """获取资源使用摘要"""
        if not self.history:
            return {}
            
        recent = list(self.history)[-10:]  # 最近10条记录
        
        return {
            'cpu_avg': sum(m['cpu']['percent'] for m in recent) / len(recent),
            'memory_avg': sum(m['memory']['percent'] for m in recent) / len(recent),
            'disk_usage': recent[-1]['disk']['percent'] if recent else 0,
            'trend': self._calculate_trend(recent)
        }
        
    def _calculate_trend(self, metrics: List[Dict[str, Any]]) -> str:
        """计算资源使用趋势"""
        if len(metrics) < 2:
            return 'stable'
            
        cpu_trend = metrics[-1]['cpu']['percent'] - metrics[0]['cpu']['percent']
        memory_trend = metrics[-1]['memory']['percent'] - metrics[0]['memory']['percent']
        
        if cpu_trend > 20 or memory_trend > 20:
            return 'increasing'
        elif cpu_trend < -20 or memory_trend < -20:
            return 'decreasing'
        return 'stable'


class PerformanceTracker:
    """操作性能跟踪器"""
    
    def __init__(self):
        self.operations = {}
        self.performance_data = deque(maxlen=1000)
        self.slow_operation_threshold = 5.0  # 慢操作阈值（秒）
        
    def track_operation(self, name: str):
        """装饰器：跟踪函数执行性能"""
        def decorator(func: Callable):
            @wraps(func)
            def wrapper(*args, **kwargs):
                start_time = time.time()
                operation_id = f"{name}_{id(threading.current_thread())}_{start_time}"
                
                # 记录操作开始
                logger.debug(f"📊 开始操作: {name}")
                
                try:
                    result = func(*args, **kwargs)
                    elapsed = time.time() - start_time
                    
                    # 记录性能数据
                    self._record_performance(name, elapsed, 'success')
                    
                    # 检查是否为慢操作
                    if elapsed > self.slow_operation_threshold:
                        logger.warning(f"⏱️ 慢操作检测: {name} 耗时 {elapsed:.2f}秒")
                    else:
                        logger.debug(f"✅ 操作完成: {name} 耗时 {elapsed:.3f}秒")
                        
                    return result
                    
                except Exception as e:
                    elapsed = time.time() - start_time
                    self._record_performance(name, elapsed, 'error', str(e))
                    logger.error(f"❌ 操作失败: {name} ({elapsed:.3f}秒) - {e}")
                    raise
                    
            return wrapper
        return decorator
        
    @contextmanager
    def measure(self, name: str):
        """上下文管理器：测量代码块执行时间"""
        start_time = time.time()
        start_memory = psutil.Process().memory_info().rss / (1024**2)  # MB
        
        logger.debug(f"📏 开始测量: {name}")
        
        try:
            yield
        finally:
            elapsed = time.time() - start_time
            end_memory = psutil.Process().memory_info().rss / (1024**2)  # MB
            memory_delta = end_memory - start_memory
            
            self._record_performance(name, elapsed, 'success', memory_delta=memory_delta)
            
            if elapsed > self.slow_operation_threshold:
                logger.warning(f"⏱️ 慢操作: {name} - 耗时: {elapsed:.2f}秒, 内存变化: {memory_delta:+.1f}MB")
            else:
                logger.debug(f"📊 测量完成: {name} - 耗时: {elapsed:.3f}秒, 内存变化: {memory_delta:+.1f}MB")
                
    def _record_performance(self, name: str, elapsed: float, status: str, 
                           error: str = None, memory_delta: float = None):
        """记录性能数据"""
        data = {
            'timestamp': datetime.now().isoformat(),
            'operation': name,
            'elapsed': elapsed,
            'status': status,
            'error': error,
            'memory_delta': memory_delta
        }
        
        self.performance_data.append(data)
        
        # 更新操作统计
        if name not in self.operations:
            self.operations[name] = {
                'count': 0,
                'total_time': 0,
                'errors': 0,
                'min_time': float('inf'),
                'max_time': 0
            }
            
        stats = self.operations[name]
        stats['count'] += 1
        stats['total_time'] += elapsed
        stats['min_time'] = min(stats['min_time'], elapsed)
        stats['max_time'] = max(stats['max_time'], elapsed)
        
        if status == 'error':
            stats['errors'] += 1
            
    def get_performance_report(self) -> Dict[str, Any]:
        """生成性能报告"""
        report = {
            'summary': {},
            'operations': {},
            'bottlenecks': [],
            'recommendations': []
        }
        
        # 操作统计
        for name, stats in self.operations.items():
            avg_time = stats['total_time'] / stats['count'] if stats['count'] > 0 else 0
            error_rate = stats['errors'] / stats['count'] * 100 if stats['count'] > 0 else 0
            
            report['operations'][name] = {
                'count': stats['count'],
                'avg_time': avg_time,
                'min_time': stats['min_time'],
                'max_time': stats['max_time'],
                'error_rate': error_rate
            }
            
            # 识别瓶颈
            if avg_time > self.slow_operation_threshold:
                report['bottlenecks'].append({
                    'operation': name,
                    'avg_time': avg_time,
                    'severity': 'high' if avg_time > 10 else 'medium'
                })
                
        # 总体统计
        if self.performance_data:
            recent_data = list(self.performance_data)[-100:]
            report['summary'] = {
                'total_operations': len(self.performance_data),
                'recent_avg_time': sum(d['elapsed'] for d in recent_data) / len(recent_data),
                'error_count': sum(1 for d in recent_data if d['status'] == 'error')
            }
            
        # 生成建议
        if report['bottlenecks']:
            report['recommendations'].append("检测到慢操作，建议优化相关代码或增加缓存")
            
        return report
        
    def log_performance_summary(self):
        """记录性能摘要到日志"""
        report = self.get_performance_report()
        
        if report['operations']:
            logger.info("📈 性能统计摘要:")
            for name, stats in report['operations'].items():
                logger.info(f"  • {name}: 平均{stats['avg_time']:.3f}秒, "
                          f"执行{stats['count']}次, 错误率{stats['error_rate']:.1f}%")
                          
        if report['bottlenecks']:
            logger.warning("⚠️ 检测到性能瓶颈:")
            for bottleneck in report['bottlenecks']:
                logger.warning(f"  • {bottleneck['operation']}: "
                             f"平均耗时 {bottleneck['avg_time']:.2f}秒 ({bottleneck['severity']})")


class PerformanceMonitor:
    """性能监控管理器（单例）"""
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance
        
    def __init__(self):
        if not hasattr(self, 'initialized'):
            self.resource_monitor = ResourceMonitor()
            self.performance_tracker = PerformanceTracker()
            self.initialized = True
            
    def start(self):
        """启动性能监控"""
        self.resource_monitor.start()
        logger.info("🎯 性能监控系统已启动")
        
    def stop(self):
        """停止性能监控"""
        self.resource_monitor.stop()
        self.performance_tracker.log_performance_summary()
        logger.info("🛑 性能监控系统已停止")
        
    def get_status(self) -> Dict[str, Any]:
        """获取监控状态"""
        return {
            'monitoring': self.resource_monitor.monitoring,
            'resource_summary': self.resource_monitor.get_resource_summary(),
            'performance_report': self.performance_tracker.get_performance_report()
        }
        
    # 便捷方法
    def track(self, name: str):
        """性能跟踪装饰器"""
        return self.performance_tracker.track_operation(name)
        
    def measure(self, name: str):
        """性能测量上下文管理器"""
        return self.performance_tracker.measure(name)
        
    def get_metrics(self) -> Dict[str, Any]:
        """获取当前资源指标"""
        return self.resource_monitor.get_current_metrics()


# 全局性能监控实例
performance_monitor = PerformanceMonitor()

# 导出便捷函数
track_performance = performance_monitor.track
measure_performance = performance_monitor.measure