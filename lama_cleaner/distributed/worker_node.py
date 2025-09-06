"""
处理节点（Worker Node）

负责向调度器注册、接收和处理任务、发送心跳等。
"""

import json
import sys
import threading
import time
import zmq
from typing import Dict, List, Optional, Callable
from datetime import datetime
from pathlib import Path

# 添加项目根路径
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from lama_cleaner.logging_config import setup_logging, show_startup_banner, log_success, log_shutdown
from .models import NodeCapability, NodeType, NodeStatus, Task, TaskStatus
from .capability_detector import detect_node_capability
from .config import get_config
from .task_processor import TaskProcessor
from .health_monitor import HeartbeatSender, NodeHealthChecker
from .logging import get_worker_logger


class WorkerNode:
    """处理节点"""
    
    def __init__(self, node_config: Dict = None, capability: NodeCapability = None):
        # 首先设置日志系统，确保立即可见的输出
        setup_logging(level="INFO", enable_file_logging=True)
        
        self.config = get_config()
        self.node_config = node_config or {}
        
        # 节点能力检测和配置
        if capability:
            self.capability = capability
        else:
            self.capability = self._detect_or_load_capability()
        
        # 使用专用的工作节点日志器（需要node_id）
        self.logger = get_worker_logger(self.capability.node_id)
        
        # 记录启动信息
        self.logger.log_startup(self.capability)
        
        # 显示启动横幅
        show_startup_banner(version="1.0.0", mode="分布式工作节点")
        
        # 显示节点能力信息
        self._display_node_capabilities()
        
        # ZeroMQ 上下文和 sockets
        self.logger.info("🔧 初始化通信组件...")
        self.context = zmq.Context()
        self.control_socket = None
        self.heartbeat_socket = None
        self.task_sockets = {}
        
        # 状态管理
        self.current_tasks: Dict[str, Task] = {}
        self.task_lock = threading.RLock()
        self.is_running = False
        
        # 工作线程
        self._task_threads = {}
        self._health_check_thread = None
        
        # 回调函数
        self.task_callbacks: Dict[str, Callable] = {}
        
        # 任务处理器
        device = self.node_config.get('device', 'cpu')
        self.task_processor = TaskProcessor(device=device, **self.node_config)
        self.logger.success(f"任务处理器初始化完成 (设备: {device})", action="task_processor_init")
        
        # 心跳发送器
        scheduler_host = self.node_config.get('scheduler_host', 'localhost')
        self.heartbeat_sender = HeartbeatSender(self.capability, scheduler_host)
        self.logger.success("心跳发送器初始化完成", action="heartbeat_sender_init")
        
        # 健康检查器
        self.health_checker = NodeHealthChecker(self.capability)
        self.logger.success("健康检查器初始化完成", action="health_checker_init")
        
        self.logger.success("🎉 工作节点初始化完成", action="worker_init_complete")
    
    def _detect_or_load_capability(self) -> NodeCapability:
        """检测或加载节点能力"""
        capability_file = self.node_config.get('capability_file')
        
        if capability_file and Path(capability_file).exists():
            # 从配置文件加载
            from .capability_detector import CapabilityDetector
            detector = CapabilityDetector()
            capability = detector.load_capability_config(capability_file)
            self.logger.info(f"📄 从配置文件加载节点能力: {capability_file}")
        else:
            # 自动检测
            node_type = NodeType(self.node_config.get('node_type', 'local'))
            capability = detect_node_capability(node_type)
            self.logger.info("✅ 自动检测节点能力完成")
        
        # 设置网络信息
        capability.host = self.node_config.get('host', 'localhost')
        capability.port = self.node_config.get('port', 0)
        
        return capability
    
    def _display_node_capabilities(self):
        """显示节点能力信息"""
        self.logger.info("📊 节点能力信息:")
        self.logger.info(f"  ├─ 节点ID: {self.capability.node_id}")
        self.logger.info(f"  ├─ 节点类型: {self.capability.node_type.value}")
        self.logger.info(f"  ├─ 最大并发任务: {self.capability.max_concurrent_tasks}")
        
        # GPU信息
        if hasattr(self.capability, 'gpu_info') and self.capability.gpu_info:
            gpu_info = self.capability.gpu_info
            self.logger.info(f"  ├─ GPU设备: {gpu_info.get('name', 'Unknown')}")
            self.logger.info(f"  ├─ GPU内存: {gpu_info.get('memory_total', 0) / 1024**3:.1f} GB")
        else:
            self.logger.info("  ├─ GPU设备: 无 (CPU模式)")
        
        # 支持的模型
        if hasattr(self.capability, 'supported_models') and self.capability.supported_models:
            models = ', '.join(self.capability.supported_models[:3])  # 显示前3个
            if len(self.capability.supported_models) > 3:
                models += f" 等{len(self.capability.supported_models)}个模型"
            self.logger.info(f"  ├─ 支持模型: {models}")
        
        # 支持的任务类型
        if hasattr(self.capability, 'supported_tasks') and self.capability.supported_tasks:
            tasks = ', '.join([t.value for t in self.capability.supported_tasks])
            self.logger.info(f"  └─ 支持任务: {tasks}")
        
        self.logger.success("节点能力检测完成")
    
    def start(self):
        """启动工作节点"""
        if self.is_running:
            self.logger.warning("⚠️ 工作节点已在运行")
            return
        
        try:
            self.logger.info("🚀 正在启动工作节点服务...")
            
            # 连接到调度器
            self.logger.log_registration_attempt(self.config.scheduler_host, self.config.scheduler_port)
            self._connect_to_scheduler()
            
            # 注册节点
            registration_result = self._register_node()
            if registration_result['status'] != 'success':
                self.logger.log_registration_failed(str(registration_result))
                raise RuntimeError(f"节点注册失败: {registration_result}")
            
            self.logger.log_registration_success()
            
            # 设置任务队列连接
            subscriptions = registration_result.get('subscriptions', [])
            self._setup_task_queues(subscriptions)
            
            # 启动心跳发送器
            self.heartbeat_sender.start()
            self.logger.success("心跳发送器已启动", action="heartbeat_started")
            
            # 启动工作线程
            self.is_running = True
            self._start_threads()
            
            self.logger.success("🎉 工作节点启动成功", 
                              action="worker_start_complete",
                              subscriptions=subscriptions)
            
        except Exception as e:
            self.logger.log_registration_failed(str(e))
            self.stop()
            raise
    
    def stop(self):
        """停止工作节点"""
        if not self.is_running:
            return
        
        self.logger.info("🛑 正在停止工作节点...")
        self.is_running = False
        
        # 等待当前任务完成
        self.logger.info("⏳ 等待当前任务完成...")
        self._wait_for_tasks_completion()
        
        # 停止心跳发送器
        self.logger.info("💓 停止心跳发送器...")
        if hasattr(self, 'heartbeat_sender'):
            self.heartbeat_sender.stop()
        self.logger.info("✅ 心跳发送器已停止")
        
        # 注销节点
        self.logger.info("📝 从调度器注销节点...")
        self._unregister_node()
        
        # 停止工作线程
        self.logger.info("🔧 停止工作线程...")
        self._stop_threads()
        self.logger.info("✅ 工作线程已停止")
        
        # 关闭 sockets
        self.logger.info("🔗 关闭网络连接...")
        self._close_sockets()
        
        # 清理任务处理器
        self.logger.info("🧹 清理任务处理器...")
        if hasattr(self, 'task_processor'):
            self.task_processor.cleanup()
        
        # 关闭 ZeroMQ 上下文
        self.context.term()
        
        log_shutdown("worker")
        self.logger.success("工作节点已安全关闭")
    
    def _connect_to_scheduler(self):
        """连接到调度器"""
        scheduler_host = self.config.scheduler_host
        
        # 控制信道连接
        self.control_socket = self.context.socket(zmq.REQ)
        self.control_socket.setsockopt(zmq.LINGER, self.config.zeromq.socket_linger)
        control_address = f"tcp://{scheduler_host}:{self.config.zeromq.control_port}"
        self.control_socket.connect(control_address)
        
        # 心跳信道连接
        self.heartbeat_socket = self.context.socket(zmq.PUB)
        self.heartbeat_socket.setsockopt(zmq.LINGER, self.config.zeromq.socket_linger)
        heartbeat_address = f"tcp://{scheduler_host}:{self.config.zeromq.heartbeat_port}"
        self.heartbeat_socket.connect(heartbeat_address)
        
        self.logger.success(f"已连接到调度器: {scheduler_host}")
    
    def _register_node(self) -> Dict:
        """向调度器注册节点"""
        registration_data = {
            'action': 'register',
            'data': self.capability.to_dict()
        }
        
        self.control_socket.send_json(registration_data)
        response = self.control_socket.recv_json()
        
        if response.get('status') == 'success':
            self.logger.success(f"节点注册成功: {self.capability.node_id}")
        else:
            self.logger.error(f"节点注册失败: {response}")
        
        return response
    
    def _unregister_node(self):
        """从调度器注销节点"""
        try:
            unregister_data = {
                'action': 'unregister',
                'data': {'node_id': self.capability.node_id}
            }
            
            self.control_socket.send_json(unregister_data)
            response = self.control_socket.recv_json()
            
            if response.get('status') == 'success':
                self.logger.success(f"节点注销成功: {self.capability.node_id}")
            else:
                self.logger.warning(f"⚠️ 节点注销失败: {response}")
                
        except Exception as e:
            self.logger.error(f"节点注销异常: {e}")
    
    def _setup_task_queues(self, subscriptions: List[str]):
        """设置任务队列连接"""
        scheduler_host = self.config.scheduler_host
        
        for queue_name in subscriptions:
            if queue_name not in self.config.queues:
                self.logger.warning(f"⚠️ 未知队列: {queue_name}")
                continue
            
            queue_config = self.config.queues[queue_name]
            socket = self.context.socket(zmq.PULL)
            socket.setsockopt(zmq.LINGER, self.config.zeromq.socket_linger)
            
            queue_address = f"tcp://{scheduler_host}:{queue_config.port}"
            socket.connect(queue_address)
            
            self.task_sockets[queue_name] = socket
            self.logger.success(f"已连接到任务队列: {queue_name} ({queue_address})")
    
    def _start_threads(self):
        """启动工作线程"""
        # 健康检查线程
        self._health_check_thread = threading.Thread(
            target=self._health_check_worker,
            daemon=True,
            name=f"HealthCheck-{self.capability.node_id[:8]}"
        )
        self._health_check_thread.start()
        
        # 任务处理线程（每个队列一个线程）
        for queue_name in self.task_sockets:
            thread = threading.Thread(
                target=self._task_worker,
                args=(queue_name,),
                daemon=True,
                name=f"TaskWorker-{queue_name}-{self.capability.node_id[:8]}"
            )
            self._task_threads[queue_name] = thread
            thread.start()
        
        self.logger.success(f"工作线程已启动: 健康检查线程 + {len(self.task_sockets)} 个任务线程")
    
    def _stop_threads(self):
        """停止工作线程"""
        # 等待健康检查线程结束
        if self._health_check_thread and self._health_check_thread.is_alive():
            self._health_check_thread.join(timeout=5)
        
        # 等待任务线程结束
        for thread in self._task_threads.values():
            if thread.is_alive():
                thread.join(timeout=5)
    
    def _close_sockets(self):
        """关闭所有 sockets"""
        if self.control_socket:
            self.control_socket.close()
        if self.heartbeat_socket:
            self.heartbeat_socket.close()
        
        for socket in self.task_sockets.values():
            socket.close()
        
        self.task_sockets.clear()
    
    def _health_check_worker(self):
        """健康检查工作线程"""
        check_interval = 30  # 30秒检查一次
        
        while self.is_running:
            try:
                # 执行健康检查
                is_healthy = self.health_checker.check_health()
                
                # 更新节点状态
                if not is_healthy:
                    if self.capability.status == NodeStatus.ONLINE:
                        self.capability.status = NodeStatus.ERROR
                        self.logger.warning("⚠️ 节点健康检查失败，状态设为ERROR")
                else:
                    if self.capability.status == NodeStatus.ERROR:
                        self.capability.status = NodeStatus.ONLINE
                        self.logger.success("节点健康检查恢复，状态设为ONLINE")
                
                # 更新心跳发送器的负载信息
                self.heartbeat_sender.update_load(len(self.current_tasks))
                
                time.sleep(check_interval)
                
            except Exception as e:
                self.logger.error(f"健康检查失败: {e}")
                self.heartbeat_sender.report_error(str(e))
                time.sleep(check_interval)
    
    def _task_worker(self, queue_name: str):
        """任务处理工作线程"""
        socket = self.task_sockets[queue_name]
        
        while self.is_running:
            try:
                # 检查是否还能接受新任务
                if len(self.current_tasks) >= self.capability.max_concurrent_tasks:
                    time.sleep(1)
                    continue
                
                # 非阻塞接收任务
                if socket.poll(1000):  # 1秒超时
                    message_parts = socket.recv_multipart(zmq.NOBLOCK)
                    
                    if len(message_parts) >= 3:
                        queue_name_bytes, task_id_bytes, task_data = message_parts[:3]
                        task = self._deserialize_task(task_data)
                        
                        if task:
                            self._process_task(task)
                
            except zmq.Again:
                continue
            except Exception as e:
                self.logger.error(f"任务处理线程异常 {queue_name}: {e}")
                time.sleep(1)
    
    def _deserialize_task(self, task_data: bytes) -> Optional[Task]:
        """反序列化任务数据"""
        try:
            task_dict = json.loads(task_data.decode('utf-8'))
            return Task.from_dict(task_dict)
        except Exception as e:
            self.logger.error(f"任务反序列化失败: {e}")
            return None
    
    def _process_task(self, task: Task):
        """处理单个任务"""
        task_id = task.task_id
        
        with self.task_lock:
            if task_id in self.current_tasks:
                self.logger.warning(f"⚠️ 任务已在处理中: {task_id}", action="task_duplicate")
                return
            
            self.current_tasks[task_id] = task
        
        # 记录任务接收
        self.logger.log_task_received(task)
        
        try:
            # 记录任务开始处理
            self.logger.log_task_processing_start(task_id)
            
            # 更新任务状态
            task.status = TaskStatus.PROCESSING
            task.assigned_node = self.capability.node_id
            task.updated_at = datetime.now()
            
            # 执行任务处理
            start_time = time.time()
            result = self._execute_task(task)
            processing_time = time.time() - start_time
            
            # 更新任务结果
            if result:
                task.status = TaskStatus.COMPLETED
                task.result_path = result
                task.processing_time = processing_time
                self.logger.log_task_processing_complete(task_id, processing_time)
            else:
                task.status = TaskStatus.FAILED
                task.error_message = "任务处理返回空结果"
                self.logger.log_task_processing_failed(task_id, "任务处理返回空结果")
            
        except Exception as e:
            task.status = TaskStatus.FAILED
            task.error_message = str(e)
            self.logger.log_task_processing_failed(task_id, str(e))
            
            # 报告错误到心跳发送器
            self.heartbeat_sender.report_error(f"任务处理失败: {str(e)}")
        
        finally:
            task.updated_at = datetime.now()
            
            # 更新统计信息
            self.capability.total_processed += 1
            self.heartbeat_sender.increment_processed()
            
            # 移除当前任务
            with self.task_lock:
                self.current_tasks.pop(task_id, None)
            
            # 通知任务完成（这里可以发送结果到结果队列）
            self._notify_task_completion(task)
    
    def _execute_task(self, task: Task) -> Optional[str]:
        """执行具体的任务处理"""
        # 注册进度回调
        self.task_processor.register_progress_callback(
            task.task_id, 
            lambda progress, message: self._report_task_progress(task.task_id, progress, message)
        )
        
        try:
            # 使用任务处理器处理任务
            processed_task = self.task_processor.process_task(task)
            
            # 更新任务状态
            task.status = processed_task.status
            task.result_path = processed_task.result_path
            task.error_message = processed_task.error_message
            task.processing_time = processed_task.processing_time
            
            return processed_task.result_path
            
        finally:
            # 注销进度回调
            self.task_processor.unregister_progress_callback(task.task_id)
    
    def _report_task_progress(self, task_id: str, progress: float, message: str):
        """报告任务进度"""
        # 这里可以通过心跳或专门的进度通道发送进度信息
        self.logger.debug(f"📊 任务进度 {task_id}: {progress:.1%} - {message}")
        
        # 可以发送进度更新到调度器
        # self._send_progress_update(task_id, progress, message)
    
    def _notify_task_completion(self, task: Task):
        """通知任务完成"""
        # 这里可以发送任务结果到结果队列或直接更新状态管理器
        self.logger.debug(f"📝 任务完成通知: {task.task_id} -> {task.status.value}")
        
        # 调用回调函数
        callback = self.task_callbacks.get(task.task_type.value)
        if callback:
            try:
                callback(task)
            except Exception as e:
                self.logger.error(f"任务完成回调失败: {e}")
    
    def _wait_for_tasks_completion(self, timeout: int = 30):
        """等待当前任务完成"""
        start_time = time.time()
        
        while self.current_tasks and (time.time() - start_time) < timeout:
            self.logger.info(f"⏳ 等待 {len(self.current_tasks)} 个任务完成...")
            time.sleep(1)
        
        if self.current_tasks:
            self.logger.warning(f"⚠️ 超时，仍有 {len(self.current_tasks)} 个任务未完成")
    
    def register_task_callback(self, task_type: str, callback: Callable[[Task], None]):
        """注册任务完成回调"""
        self.task_callbacks[task_type] = callback
    
    def get_status(self) -> Dict:
        """获取节点状态"""
        with self.task_lock:
            return {
                'node_id': self.capability.node_id,
                'node_type': self.capability.node_type.value,
                'status': self.capability.status.value,
                'is_running': self.is_running,
                'current_tasks': len(self.current_tasks),
                'max_concurrent_tasks': self.capability.max_concurrent_tasks,
                'total_processed': self.capability.total_processed,
                'supported_models': self.capability.supported_models,
                'supported_tasks': [t.value for t in self.capability.supported_tasks],
                'queue_subscriptions': self.capability.get_queue_subscriptions()
            }


def create_worker_node(config_file: str = None, **kwargs) -> WorkerNode:
    """创建工作节点的便捷函数"""
    node_config = kwargs
    
    if config_file:
        import yaml
        with open(config_file, 'r', encoding='utf-8') as f:
            file_config = yaml.safe_load(f)
        node_config.update(file_config)
    
    return WorkerNode(node_config)


if __name__ == "__main__":
    # 命令行工具
    import argparse
    import signal
    import sys
    
    def signal_handler(signum, frame):
        print("📝 收到停止信号，正在关闭工作节点...")
        if 'worker' in globals():
            worker.stop()
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    parser = argparse.ArgumentParser(description="工作节点")
    parser.add_argument("--config", "-c", help="配置文件路径")
    parser.add_argument("--host", default="localhost", help="调度器主机地址")
    parser.add_argument("--type", "-t", choices=['local', 'remote', 'serverless'], 
                       default='local', help="节点类型")
    parser.add_argument("--capability", help="节点能力配置文件路径")
    parser.add_argument("--verbose", "-v", action="store_true", help="详细输出")
    
    args = parser.parse_args()
    
    # 日志配置在 WorkerNode.__init__ 中已经设置
    if args.verbose:
        setup_logging(level="DEBUG")
    else:
        setup_logging(level="INFO")
    
    # 创建工作节点
    node_config = {
        'host': args.host,
        'node_type': args.type,
        'capability_file': args.capability
    }
    
    worker = create_worker_node(args.config, **node_config)
    
    try:
        worker.start()
        
        # 保持运行
        while worker.is_running:
            time.sleep(1)
            
    except KeyboardInterrupt:
        print("👋 收到中断信号")
    except Exception as e:
        print(f"💥 工作节点运行异常: {e}")
    finally:
        worker.stop()