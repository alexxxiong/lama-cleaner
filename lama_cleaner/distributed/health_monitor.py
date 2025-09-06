"""
节点健康监控和心跳管理

负责节点的健康检查、心跳发送和接收、异常检测和自动恢复。
"""

import json
import logging
import threading
import time
import zmq
from typing import Dict, List, Optional, Callable, Any
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict
import psutil

from .models import NodeCapability, NodeStatus
from .config import get_config

logger = logging.getLogger(__name__)


@dataclass
class HealthMetrics:
    """健康指标数据"""
    timestamp: datetime
    cpu_usage: float
    memory_usage: float
    memory_available: int  # MB
    disk_usage: float
    gpu_usage: Optional[float] = None
    gpu_memory_usage: Optional[float] = None
    temperature: Optional[float] = None
    load_average: Optional[float] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        data = asdict(self)
        data['timestamp'] = self.timestamp.isoformat()
        return data
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'HealthMetrics':
        """从字典创建对象"""
        data = data.copy()
        data['timestamp'] = datetime.fromisoformat(data['timestamp'])
        return cls(**data)


@dataclass
class HeartbeatData:
    """心跳数据"""
    node_id: str
    timestamp: datetime
    status: NodeStatus
    current_load: int
    total_processed: int
    health_metrics: HealthMetrics
    error_count: int = 0
    last_error: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            'node_id': self.node_id,
            'timestamp': self.timestamp.isoformat(),
            'status': self.status.value,
            'current_load': self.current_load,
            'total_processed': self.total_processed,
            'health_metrics': self.health_metrics.to_dict(),
            'error_count': self.error_count,
            'last_error': self.last_error
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'HeartbeatData':
        """从字典创建对象"""
        data = data.copy()
        data['timestamp'] = datetime.fromisoformat(data['timestamp'])
        data['status'] = NodeStatus(data['status'])
        data['health_metrics'] = HealthMetrics.from_dict(data['health_metrics'])
        return cls(**data)


class HealthCollector:
    """健康指标收集器"""
    
    def __init__(self):
        self.gpu_available = self._check_gpu_availability()
        logger.info(f"健康指标收集器初始化完成，GPU可用: {self.gpu_available}")
    
    def _check_gpu_availability(self) -> bool:
        """检查GPU是否可用"""
        try:
            import pynvml
            pynvml.nvmlInit()
            return True
        except (ImportError, Exception):
            return False
    
    def collect_metrics(self) -> HealthMetrics:
        """收集当前健康指标"""
        try:
            # CPU 使用率
            cpu_usage = psutil.cpu_percent(interval=1)
            
            # 内存使用情况
            memory = psutil.virtual_memory()
            memory_usage = memory.percent
            memory_available = int(memory.available / 1024 / 1024)  # MB
            
            # 磁盘使用情况
            disk = psutil.disk_usage('/')
            disk_usage = disk.percent
            
            # 负载平均值（仅 Unix 系统）
            load_average = None
            try:
                load_average = psutil.getloadavg()[0]  # 1分钟负载平均值
            except AttributeError:
                pass  # Windows 系统不支持
            
            # GPU 指标
            gpu_usage = None
            gpu_memory_usage = None
            temperature = None
            
            if self.gpu_available:
                gpu_metrics = self._collect_gpu_metrics()
                gpu_usage = gpu_metrics.get('usage')
                gpu_memory_usage = gpu_metrics.get('memory_usage')
                temperature = gpu_metrics.get('temperature')
            
            # CPU 温度（如果可用）
            if temperature is None:
                temperature = self._get_cpu_temperature()
            
            return HealthMetrics(
                timestamp=datetime.now(),
                cpu_usage=cpu_usage,
                memory_usage=memory_usage,
                memory_available=memory_available,
                disk_usage=disk_usage,
                gpu_usage=gpu_usage,
                gpu_memory_usage=gpu_memory_usage,
                temperature=temperature,
                load_average=load_average
            )
            
        except Exception as e:
            logger.error(f"收集健康指标失败: {e}")
            # 返回基础指标
            return HealthMetrics(
                timestamp=datetime.now(),
                cpu_usage=0.0,
                memory_usage=0.0,
                memory_available=0,
                disk_usage=0.0
            )
    
    def _collect_gpu_metrics(self) -> Dict[str, float]:
        """收集GPU指标"""
        try:
            import pynvml
            
            device_count = pynvml.nvmlDeviceGetCount()
            if device_count == 0:
                return {}
            
            # 获取第一个GPU的信息
            handle = pynvml.nvmlDeviceGetHandleByIndex(0)
            
            # GPU 使用率
            utilization = pynvml.nvmlDeviceGetUtilizationRates(handle)
            gpu_usage = utilization.gpu
            
            # GPU 内存使用率
            memory_info = pynvml.nvmlDeviceGetMemoryInfo(handle)
            gpu_memory_usage = (memory_info.used / memory_info.total) * 100
            
            # GPU 温度
            temperature = pynvml.nvmlDeviceGetTemperature(handle, pynvml.NVML_TEMPERATURE_GPU)
            
            return {
                'usage': gpu_usage,
                'memory_usage': gpu_memory_usage,
                'temperature': temperature
            }
            
        except Exception as e:
            logger.debug(f"收集GPU指标失败: {e}")
            return {}
    
    def _get_cpu_temperature(self) -> Optional[float]:
        """获取CPU温度"""
        try:
            # 尝试从 psutil 获取温度信息
            temps = psutil.sensors_temperatures()
            if temps:
                # 查找CPU温度
                for name, entries in temps.items():
                    if 'cpu' in name.lower() or 'core' in name.lower():
                        if entries:
                            return entries[0].current
                
                # 如果没有找到CPU温度，返回第一个可用的温度
                for entries in temps.values():
                    if entries:
                        return entries[0].current
            
        except (AttributeError, Exception):
            pass  # 某些系统不支持温度传感器
        
        return None


class HeartbeatSender:
    """心跳发送器（用于工作节点）"""
    
    def __init__(self, node_capability: NodeCapability, scheduler_host: str = "localhost"):
        self.node_capability = node_capability
        self.scheduler_host = scheduler_host
        self.config = get_config()
        
        # ZeroMQ 上下文和 socket
        self.context = zmq.Context()
        self.socket = None
        
        # 健康指标收集器
        self.health_collector = HealthCollector()
        
        # 状态信息
        self.current_load = 0
        self.total_processed = 0
        self.error_count = 0
        self.last_error = None
        
        # 控制变量
        self.is_running = False
        self.heartbeat_thread = None
        
        logger.info(f"心跳发送器初始化完成: {node_capability.node_id}")
    
    def start(self):
        """启动心跳发送"""
        if self.is_running:
            logger.warning("心跳发送器已在运行")
            return
        
        try:
            # 连接到调度器
            self._connect_to_scheduler()
            
            # 启动心跳线程
            self.is_running = True
            self.heartbeat_thread = threading.Thread(
                target=self._heartbeat_worker,
                daemon=True,
                name=f"Heartbeat-{self.node_capability.node_id[:8]}"
            )
            self.heartbeat_thread.start()
            
            logger.info("心跳发送器已启动")
            
        except Exception as e:
            logger.error(f"启动心跳发送器失败: {e}")
            self.stop()
            raise
    
    def stop(self):
        """停止心跳发送"""
        if not self.is_running:
            return
        
        logger.info("正在停止心跳发送器...")
        self.is_running = False
        
        # 等待心跳线程结束
        if self.heartbeat_thread and self.heartbeat_thread.is_alive():
            self.heartbeat_thread.join(timeout=5)
        
        # 关闭 socket
        if self.socket:
            self.socket.close()
        
        self.context.term()
        logger.info("心跳发送器已停止")
    
    def _connect_to_scheduler(self):
        """连接到调度器"""
        self.socket = self.context.socket(zmq.PUB)
        self.socket.setsockopt(zmq.LINGER, self.config.zeromq.socket_linger)
        
        heartbeat_address = f"tcp://{self.scheduler_host}:{self.config.zeromq.heartbeat_port}"
        self.socket.connect(heartbeat_address)
        
        # 等待连接建立
        time.sleep(0.1)
        
        logger.info(f"已连接到调度器心跳端口: {heartbeat_address}")
    
    def _heartbeat_worker(self):
        """心跳工作线程"""
        heartbeat_interval = self.config.node_heartbeat_interval
        
        while self.is_running:
            try:
                # 收集健康指标
                health_metrics = self.health_collector.collect_metrics()
                
                # 创建心跳数据
                heartbeat_data = HeartbeatData(
                    node_id=self.node_capability.node_id,
                    timestamp=datetime.now(),
                    status=self.node_capability.status,
                    current_load=self.current_load,
                    total_processed=self.total_processed,
                    health_metrics=health_metrics,
                    error_count=self.error_count,
                    last_error=self.last_error
                )
                
                # 发送心跳
                self._send_heartbeat(heartbeat_data)
                
                # 等待下次心跳
                time.sleep(heartbeat_interval)
                
            except Exception as e:
                logger.error(f"心跳发送失败: {e}")
                self.error_count += 1
                self.last_error = str(e)
                time.sleep(heartbeat_interval)
    
    def _send_heartbeat(self, heartbeat_data: HeartbeatData):
        """发送心跳数据"""
        try:
            message = json.dumps(heartbeat_data.to_dict()).encode('utf-8')
            self.socket.send_multipart([b"heartbeat", message])
            
            logger.debug(f"心跳已发送: {heartbeat_data.node_id}")
            
        except Exception as e:
            logger.error(f"发送心跳消息失败: {e}")
            raise
    
    def update_load(self, current_load: int):
        """更新当前负载"""
        self.current_load = current_load
    
    def increment_processed(self):
        """增加处理计数"""
        self.total_processed += 1
    
    def report_error(self, error_message: str):
        """报告错误"""
        self.error_count += 1
        self.last_error = error_message
        logger.warning(f"节点错误: {error_message}")


class HeartbeatReceiver:
    """心跳接收器（用于调度器）"""
    
    def __init__(self):
        self.config = get_config()
        
        # ZeroMQ 上下文和 socket
        self.context = zmq.Context()
        self.socket = None
        
        # 节点心跳数据
        self.node_heartbeats: Dict[str, HeartbeatData] = {}
        self.heartbeat_lock = threading.RLock()
        
        # 回调函数
        self.heartbeat_callbacks: List[Callable[[HeartbeatData], None]] = []
        self.timeout_callbacks: List[Callable[[str], None]] = []
        
        # 控制变量
        self.is_running = False
        self.receiver_thread = None
        self.monitor_thread = None
        
        logger.info("心跳接收器初始化完成")
    
    def start(self):
        """启动心跳接收"""
        if self.is_running:
            logger.warning("心跳接收器已在运行")
            return
        
        try:
            # 设置 socket
            self._setup_socket()
            
            # 启动工作线程
            self.is_running = True
            self._start_threads()
            
            logger.info("心跳接收器已启动")
            
        except Exception as e:
            logger.error(f"启动心跳接收器失败: {e}")
            self.stop()
            raise
    
    def stop(self):
        """停止心跳接收"""
        if not self.is_running:
            return
        
        logger.info("正在停止心跳接收器...")
        self.is_running = False
        
        # 等待线程结束
        for thread in [self.receiver_thread, self.monitor_thread]:
            if thread and thread.is_alive():
                thread.join(timeout=5)
        
        # 关闭 socket
        if self.socket:
            self.socket.close()
        
        self.context.term()
        logger.info("心跳接收器已停止")
    
    def _setup_socket(self):
        """设置 socket"""
        self.socket = self.context.socket(zmq.SUB)
        self.socket.setsockopt(zmq.LINGER, self.config.zeromq.socket_linger)
        self.socket.bind(f"tcp://*:{self.config.zeromq.heartbeat_port}")
        self.socket.setsockopt(zmq.SUBSCRIBE, b"heartbeat")
        
        logger.info(f"心跳接收端口: {self.config.zeromq.heartbeat_port}")
    
    def _start_threads(self):
        """启动工作线程"""
        self.receiver_thread = threading.Thread(
            target=self._receiver_worker,
            daemon=True,
            name="HeartbeatReceiver"
        )
        
        self.monitor_thread = threading.Thread(
            target=self._monitor_worker,
            daemon=True,
            name="HeartbeatMonitor"
        )
        
        self.receiver_thread.start()
        self.monitor_thread.start()
        
        logger.info("心跳接收器工作线程已启动")
    
    def _receiver_worker(self):
        """心跳接收工作线程"""
        while self.is_running:
            try:
                if self.socket.poll(1000):  # 1秒超时
                    topic, message = self.socket.recv_multipart(zmq.NOBLOCK)
                    self._handle_heartbeat_message(message)
                    
            except zmq.Again:
                continue
            except Exception as e:
                logger.error(f"心跳接收失败: {e}")
                time.sleep(1)
    
    def _monitor_worker(self):
        """心跳监控工作线程"""
        while self.is_running:
            try:
                self._check_node_timeouts()
                time.sleep(self.config.node_heartbeat_interval)
                
            except Exception as e:
                logger.error(f"心跳监控失败: {e}")
                time.sleep(10)
    
    def _handle_heartbeat_message(self, message: bytes):
        """处理心跳消息"""
        try:
            data = json.loads(message.decode('utf-8'))
            heartbeat_data = HeartbeatData.from_dict(data)
            
            with self.heartbeat_lock:
                self.node_heartbeats[heartbeat_data.node_id] = heartbeat_data
            
            logger.debug(f"收到心跳: {heartbeat_data.node_id}")
            
            # 调用回调函数
            for callback in self.heartbeat_callbacks:
                try:
                    callback(heartbeat_data)
                except Exception as e:
                    logger.error(f"心跳回调失败: {e}")
                    
        except Exception as e:
            logger.error(f"处理心跳消息失败: {e}")
    
    def _check_node_timeouts(self):
        """检查节点超时"""
        timeout_threshold = datetime.now() - timedelta(seconds=self.config.node_timeout)
        timed_out_nodes = []
        
        with self.heartbeat_lock:
            for node_id, heartbeat_data in self.node_heartbeats.items():
                if heartbeat_data.timestamp < timeout_threshold:
                    timed_out_nodes.append(node_id)
        
        # 处理超时节点
        for node_id in timed_out_nodes:
            logger.warning(f"节点心跳超时: {node_id}")
            
            # 调用超时回调
            for callback in self.timeout_callbacks:
                try:
                    callback(node_id)
                except Exception as e:
                    logger.error(f"超时回调失败: {e}")
    
    def get_node_heartbeat(self, node_id: str) -> Optional[HeartbeatData]:
        """获取节点心跳数据"""
        with self.heartbeat_lock:
            return self.node_heartbeats.get(node_id)
    
    def get_all_heartbeats(self) -> Dict[str, HeartbeatData]:
        """获取所有节点心跳数据"""
        with self.heartbeat_lock:
            return self.node_heartbeats.copy()
    
    def get_online_nodes(self) -> List[str]:
        """获取在线节点列表"""
        timeout_threshold = datetime.now() - timedelta(seconds=self.config.node_timeout)
        online_nodes = []
        
        with self.heartbeat_lock:
            for node_id, heartbeat_data in self.node_heartbeats.items():
                if heartbeat_data.timestamp >= timeout_threshold:
                    online_nodes.append(node_id)
        
        return online_nodes
    
    def add_heartbeat_callback(self, callback: Callable[[HeartbeatData], None]):
        """添加心跳回调"""
        self.heartbeat_callbacks.append(callback)
    
    def add_timeout_callback(self, callback: Callable[[str], None]):
        """添加超时回调"""
        self.timeout_callbacks.append(callback)
    
    def remove_heartbeat_callback(self, callback: Callable[[HeartbeatData], None]):
        """移除心跳回调"""
        if callback in self.heartbeat_callbacks:
            self.heartbeat_callbacks.remove(callback)
    
    def remove_timeout_callback(self, callback: Callable[[str], None]):
        """移除超时回调"""
        if callback in self.timeout_callbacks:
            self.timeout_callbacks.remove(callback)
    
    def get_health_statistics(self) -> Dict[str, Any]:
        """获取健康统计信息"""
        with self.heartbeat_lock:
            if not self.node_heartbeats:
                return {}
            
            # 计算统计信息
            total_nodes = len(self.node_heartbeats)
            online_nodes = len(self.get_online_nodes())
            
            cpu_usages = []
            memory_usages = []
            gpu_usages = []
            temperatures = []
            
            for heartbeat_data in self.node_heartbeats.values():
                metrics = heartbeat_data.health_metrics
                cpu_usages.append(metrics.cpu_usage)
                memory_usages.append(metrics.memory_usage)
                
                if metrics.gpu_usage is not None:
                    gpu_usages.append(metrics.gpu_usage)
                
                if metrics.temperature is not None:
                    temperatures.append(metrics.temperature)
            
            stats = {
                'total_nodes': total_nodes,
                'online_nodes': online_nodes,
                'offline_nodes': total_nodes - online_nodes,
                'cpu_usage': {
                    'avg': sum(cpu_usages) / len(cpu_usages) if cpu_usages else 0,
                    'max': max(cpu_usages) if cpu_usages else 0,
                    'min': min(cpu_usages) if cpu_usages else 0
                },
                'memory_usage': {
                    'avg': sum(memory_usages) / len(memory_usages) if memory_usages else 0,
                    'max': max(memory_usages) if memory_usages else 0,
                    'min': min(memory_usages) if memory_usages else 0
                }
            }
            
            if gpu_usages:
                stats['gpu_usage'] = {
                    'avg': sum(gpu_usages) / len(gpu_usages),
                    'max': max(gpu_usages),
                    'min': min(gpu_usages)
                }
            
            if temperatures:
                stats['temperature'] = {
                    'avg': sum(temperatures) / len(temperatures),
                    'max': max(temperatures),
                    'min': min(temperatures)
                }
            
            return stats


class NodeHealthChecker:
    """节点健康检查器"""
    
    def __init__(self, node_capability: NodeCapability):
        self.node_capability = node_capability
        self.health_collector = HealthCollector()
        
        # 健康阈值
        self.cpu_threshold = 90.0      # CPU 使用率阈值
        self.memory_threshold = 90.0   # 内存使用率阈值
        self.disk_threshold = 95.0     # 磁盘使用率阈值
        self.temperature_threshold = 80.0  # 温度阈值（摄氏度）
        
        # 健康状态
        self.is_healthy = True
        self.health_issues = []
        
        logger.info(f"节点健康检查器初始化完成: {node_capability.node_id}")
    
    def check_health(self) -> bool:
        """检查节点健康状态"""
        try:
            metrics = self.health_collector.collect_metrics()
            self.health_issues.clear()
            
            # 检查 CPU 使用率
            if metrics.cpu_usage > self.cpu_threshold:
                self.health_issues.append(f"CPU使用率过高: {metrics.cpu_usage:.1f}%")
            
            # 检查内存使用率
            if metrics.memory_usage > self.memory_threshold:
                self.health_issues.append(f"内存使用率过高: {metrics.memory_usage:.1f}%")
            
            # 检查磁盘使用率
            if metrics.disk_usage > self.disk_threshold:
                self.health_issues.append(f"磁盘使用率过高: {metrics.disk_usage:.1f}%")
            
            # 检查温度
            if metrics.temperature and metrics.temperature > self.temperature_threshold:
                self.health_issues.append(f"温度过高: {metrics.temperature:.1f}°C")
            
            # 检查 GPU 使用率（如果有GPU）
            if metrics.gpu_usage and metrics.gpu_usage > 95.0:
                self.health_issues.append(f"GPU使用率过高: {metrics.gpu_usage:.1f}%")
            
            # 检查可用内存
            if metrics.memory_available < 512:  # 小于512MB
                self.health_issues.append(f"可用内存不足: {metrics.memory_available}MB")
            
            # 更新健康状态
            self.is_healthy = len(self.health_issues) == 0
            
            if not self.is_healthy:
                logger.warning(f"节点健康检查发现问题: {', '.join(self.health_issues)}")
            
            return self.is_healthy
            
        except Exception as e:
            logger.error(f"健康检查失败: {e}")
            self.health_issues = [f"健康检查异常: {str(e)}"]
            self.is_healthy = False
            return False
    
    def get_health_report(self) -> Dict[str, Any]:
        """获取健康报告"""
        metrics = self.health_collector.collect_metrics()
        
        return {
            'node_id': self.node_capability.node_id,
            'is_healthy': self.is_healthy,
            'health_issues': self.health_issues,
            'metrics': metrics.to_dict(),
            'thresholds': {
                'cpu_threshold': self.cpu_threshold,
                'memory_threshold': self.memory_threshold,
                'disk_threshold': self.disk_threshold,
                'temperature_threshold': self.temperature_threshold
            }
        }
    
    def set_thresholds(self, **thresholds):
        """设置健康阈值"""
        if 'cpu_threshold' in thresholds:
            self.cpu_threshold = thresholds['cpu_threshold']
        if 'memory_threshold' in thresholds:
            self.memory_threshold = thresholds['memory_threshold']
        if 'disk_threshold' in thresholds:
            self.disk_threshold = thresholds['disk_threshold']
        if 'temperature_threshold' in thresholds:
            self.temperature_threshold = thresholds['temperature_threshold']
        
        logger.info(f"健康阈值已更新: {thresholds}")


def create_heartbeat_sender(node_capability: NodeCapability, scheduler_host: str = "localhost") -> HeartbeatSender:
    """创建心跳发送器的便捷函数"""
    return HeartbeatSender(node_capability, scheduler_host)


def create_heartbeat_receiver() -> HeartbeatReceiver:
    """创建心跳接收器的便捷函数"""
    return HeartbeatReceiver()


def create_health_checker(node_capability: NodeCapability) -> NodeHealthChecker:
    """创建健康检查器的便捷函数"""
    return NodeHealthChecker(node_capability)