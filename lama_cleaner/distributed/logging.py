"""
分布式系统专用日志器

为分布式系统的各个模块提供专门的日志记录功能，包括：
- 调度器日志
- 工作节点日志  
- 任务管理器日志
- 队列管理器日志
"""

import json
import time
from typing import Dict, Any, Optional, List
from datetime import datetime
from loguru import logger
from .models import Task, TaskStatus, NodeStatus, NodeCapability


class DistributedLogger:
    """分布式系统基础日志器"""
    
    def __init__(self, module_name: str):
        self.module_name = module_name
        self.logger = logger.bind(name=f"distributed.{module_name}")
        
    def _log_with_context(self, level: str, message: str, **context):
        """带上下文信息的日志记录"""
        extra_data = {
            "module": self.module_name,
            "timestamp": datetime.now().isoformat(),
            **context
        }
        
        # 根据级别调用对应的日志方法
        log_method = getattr(self.logger, level.lower())
        log_method(message, extra=extra_data)
    
    def info(self, message: str, **context):
        """信息日志"""
        self._log_with_context("INFO", message, **context)
    
    def success(self, message: str, **context):
        """成功日志"""
        self._log_with_context("SUCCESS", message, **context)
    
    def warning(self, message: str, **context):
        """警告日志"""
        self._log_with_context("WARNING", message, **context)
    
    def error(self, message: str, **context):
        """错误日志"""
        self._log_with_context("ERROR", message, **context)
    
    def debug(self, message: str, **context):
        """调试日志"""
        self._log_with_context("DEBUG", message, **context)


class SchedulerLogger(DistributedLogger):
    """调度器专用日志器"""
    
    def __init__(self):
        super().__init__("scheduler")
    
    def log_startup(self, config: Dict[str, Any]):
        """记录调度器启动"""
        self.info("🚀 调度器启动开始", 
                 action="startup_begin",
                 config=config)
    
    def log_startup_complete(self, host: str, port: int, startup_time: float):
        """记录调度器启动完成"""
        self.success(f"✅ 调度器启动完成 - {host}:{port} (耗时: {startup_time:.2f}s)",
                    action="startup_complete",
                    host=host,
                    port=port,
                    startup_time=startup_time)
    
    def log_task_received(self, task: Task):
        """记录接收到新任务"""
        self.info(f"📋 接收新任务: {task.task_id}",
                 action="task_received",
                 task_id=task.task_id,
                 task_type=task.task_type.value,
                 priority=task.priority.value,
                 user_id=task.user_id)
    
    def log_task_routed(self, task_id: str, node_id: str, routing_reason: str):
        """记录任务路由"""
        self.info(f"🎯 任务路由: {task_id} -> {node_id}",
                 action="task_routed",
                 task_id=task_id,
                 target_node=node_id,
                 routing_reason=routing_reason)
    
    def log_node_registered(self, node_id: str, capability: NodeCapability):
        """记录节点注册"""
        self.success(f"🔗 节点注册成功: {node_id}",
                    action="node_registered",
                    node_id=node_id,
                    node_type=capability.node_type.value,
                    gpu_available=capability.gpu_available,
                    memory_gb=capability.memory_gb)
    
    def log_node_disconnected(self, node_id: str, reason: str):
        """记录节点断开连接"""
        self.warning(f"🔌 节点断开连接: {node_id}",
                    action="node_disconnected",
                    node_id=node_id,
                    reason=reason)
    
    def log_queue_stats(self, queue_name: str, pending: int, processing: int):
        """记录队列统计信息"""
        self.debug(f"📊 队列状态: {queue_name} (待处理: {pending}, 处理中: {processing})",
                  action="queue_stats",
                  queue_name=queue_name,
                  pending_count=pending,
                  processing_count=processing)
    
    def log_error(self, error_msg: str, error_type: str, **context):
        """记录调度器错误"""
        self.error(f"❌ 调度器错误: {error_msg}",
                  action="scheduler_error",
                  error_type=error_type,
                  **context)


class WorkerLogger(DistributedLogger):
    """工作节点专用日志器"""
    
    def __init__(self, node_id: str):
        super().__init__("worker")
        self.node_id = node_id
    
    def log_startup(self, capability: NodeCapability):
        """记录工作节点启动"""
        self.info(f"🚀 工作节点启动: {self.node_id}",
                 action="worker_startup",
                 node_id=self.node_id,
                 node_type=capability.node_type.value,
                 gpu_available=capability.gpu_available,
                 memory_gb=capability.memory_gb,
                 cpu_cores=capability.cpu_cores)
    
    def log_registration_attempt(self, scheduler_host: str, scheduler_port: int):
        """记录注册尝试"""
        self.info(f"🔗 尝试注册到调度器: {scheduler_host}:{scheduler_port}",
                 action="registration_attempt",
                 node_id=self.node_id,
                 scheduler_host=scheduler_host,
                 scheduler_port=scheduler_port)
    
    def log_registration_success(self):
        """记录注册成功"""
        self.success(f"✅ 节点注册成功: {self.node_id}",
                    action="registration_success",
                    node_id=self.node_id)
    
    def log_registration_failed(self, error: str):
        """记录注册失败"""
        self.error(f"❌ 节点注册失败: {self.node_id}",
                  action="registration_failed",
                  node_id=self.node_id,
                  error=error)
    
    def log_task_received(self, task: Task):
        """记录接收到任务"""
        self.info(f"📋 接收任务: {task.task_id}",
                 action="task_received",
                 node_id=self.node_id,
                 task_id=task.task_id,
                 task_type=task.task_type.value)
    
    def log_task_processing_start(self, task_id: str):
        """记录任务开始处理"""
        self.info(f"⚡ 开始处理任务: {task_id}",
                 action="task_processing_start",
                 node_id=self.node_id,
                 task_id=task_id,
                 start_time=datetime.now().isoformat())
    
    def log_task_processing_complete(self, task_id: str, processing_time: float):
        """记录任务处理完成"""
        self.success(f"✅ 任务处理完成: {task_id} (耗时: {processing_time:.2f}s)",
                    action="task_processing_complete",
                    node_id=self.node_id,
                    task_id=task_id,
                    processing_time=processing_time)
    
    def log_task_processing_failed(self, task_id: str, error: str):
        """记录任务处理失败"""
        self.error(f"❌ 任务处理失败: {task_id}",
                  action="task_processing_failed",
                  node_id=self.node_id,
                  task_id=task_id,
                  error=error)
    
    def log_heartbeat_sent(self, status: NodeStatus):
        """记录心跳发送"""
        self.debug(f"💓 发送心跳: {self.node_id}",
                  action="heartbeat_sent",
                  node_id=self.node_id,
                  status=status.value)
    
    def log_capability_update(self, new_capability: NodeCapability):
        """记录能力更新"""
        self.info(f"🔄 节点能力更新: {self.node_id}",
                 action="capability_update",
                 node_id=self.node_id,
                 gpu_available=new_capability.gpu_available,
                 memory_gb=new_capability.memory_gb)


class TaskManagerLogger(DistributedLogger):
    """任务管理器专用日志器"""
    
    def __init__(self):
        super().__init__("task_manager")
    
    def log_task_created(self, task: Task):
        """记录任务创建"""
        self.info(f"📝 任务创建: {task.task_id}",
                 action="task_created",
                 task_id=task.task_id,
                 task_type=task.task_type.value,
                 priority=task.priority.value,
                 user_id=task.user_id,
                 created_at=task.created_at.isoformat())
    
    def log_task_status_change(self, task_id: str, old_status: TaskStatus, new_status: TaskStatus):
        """记录任务状态变更"""
        self.info(f"🔄 任务状态变更: {task_id} ({old_status.value} -> {new_status.value})",
                 action="task_status_change",
                 task_id=task_id,
                 old_status=old_status.value,
                 new_status=new_status.value,
                 change_time=datetime.now().isoformat())
    
    def log_task_lifecycle_event(self, task_id: str, event: str, **context):
        """记录任务生命周期事件"""
        self.info(f"📊 任务生命周期: {task_id} - {event}",
                 action="task_lifecycle_event",
                 task_id=task_id,
                 event=event,
                 **context)
    
    def log_task_timeout(self, task_id: str, timeout_duration: float):
        """记录任务超时"""
        self.warning(f"⏰ 任务超时: {task_id} (超时时间: {timeout_duration}s)",
                    action="task_timeout",
                    task_id=task_id,
                    timeout_duration=timeout_duration)
    
    def log_task_retry(self, task_id: str, retry_count: int, max_retries: int):
        """记录任务重试"""
        self.info(f"🔄 任务重试: {task_id} (第{retry_count}/{max_retries}次)",
                 action="task_retry",
                 task_id=task_id,
                 retry_count=retry_count,
                 max_retries=max_retries)
    
    def log_batch_operation(self, operation: str, task_count: int, **context):
        """记录批量操作"""
        self.info(f"📦 批量操作: {operation} ({task_count}个任务)",
                 action="batch_operation",
                 operation=operation,
                 task_count=task_count,
                 **context)


class QueueManagerLogger(DistributedLogger):
    """队列管理器专用日志器"""
    
    def __init__(self):
        super().__init__("queue_manager")
    
    def log_queue_created(self, queue_name: str, config: Dict[str, Any]):
        """记录队列创建"""
        self.info(f"📋 队列创建: {queue_name}",
                 action="queue_created",
                 queue_name=queue_name,
                 config=config)
    
    def log_message_sent(self, queue_name: str, message_type: str, message_id: str):
        """记录消息发送"""
        self.debug(f"📤 消息发送: {queue_name} - {message_type}",
                  action="message_sent",
                  queue_name=queue_name,
                  message_type=message_type,
                  message_id=message_id)
    
    def log_message_received(self, queue_name: str, message_type: str, message_id: str):
        """记录消息接收"""
        self.debug(f"📥 消息接收: {queue_name} - {message_type}",
                  action="message_received",
                  queue_name=queue_name,
                  message_type=message_type,
                  message_id=message_id)
    
    def log_queue_stats(self, queue_name: str, stats: Dict[str, int]):
        """记录队列统计"""
        self.debug(f"📊 队列统计: {queue_name}",
                  action="queue_stats",
                  queue_name=queue_name,
                  **stats)
    
    def log_connection_error(self, queue_name: str, error: str):
        """记录连接错误"""
        self.error(f"❌ 队列连接错误: {queue_name}",
                  action="connection_error",
                  queue_name=queue_name,
                  error=error)
    
    def log_queue_overflow(self, queue_name: str, current_size: int, max_size: int):
        """记录队列溢出"""
        self.warning(f"⚠️ 队列溢出: {queue_name} ({current_size}/{max_size})",
                    action="queue_overflow",
                    queue_name=queue_name,
                    current_size=current_size,
                    max_size=max_size)


class ModelManagerLogger(DistributedLogger):
    """AI模型管理器专用日志器"""
    
    def __init__(self):
        super().__init__("model_manager")
    
    def log_model_loading_start(self, model_name: str, device: str, **context):
        """记录模型加载开始"""
        self.info(f"🤖 开始加载模型: {model_name} (设备: {device})",
                 action="model_loading_start",
                 model_name=model_name,
                 device=device,
                 **context)
    
    def log_model_loading_complete(self, model_name: str, loading_time: float, 
                                  memory_usage: Optional[Dict[str, float]] = None, **context):
        """记录模型加载完成"""
        self.success(f"✅ 模型加载完成: {model_name} ({loading_time:.2f}s)",
                    action="model_loading_complete",
                    model_name=model_name,
                    loading_time=loading_time,
                    memory_usage=memory_usage or {},
                    **context)
    
    def log_model_loading_failed(self, model_name: str, error: str, **context):
        """记录模型加载失败"""
        self.error(f"❌ 模型加载失败: {model_name}",
                  action="model_loading_failed",
                  model_name=model_name,
                  error=error,
                  **context)
    
    def log_model_switch_start(self, old_model: str, new_model: str, **context):
        """记录模型切换开始"""
        self.info(f"🔄 开始切换模型: {old_model} -> {new_model}",
                 action="model_switch_start",
                 old_model=old_model,
                 new_model=new_model,
                 **context)
    
    def log_model_switch_complete(self, old_model: str, new_model: str, 
                                 switch_time: float, **context):
        """记录模型切换完成"""
        self.success(f"✅ 模型切换完成: {old_model} -> {new_model} ({switch_time:.2f}s)",
                    action="model_switch_complete",
                    old_model=old_model,
                    new_model=new_model,
                    switch_time=switch_time,
                    **context)
    
    def log_model_inference_start(self, model_name: str, input_shape: tuple, **context):
        """记录模型推理开始"""
        self.debug(f"🧠 开始模型推理: {model_name} (输入: {input_shape})",
                  action="model_inference_start",
                  model_name=model_name,
                  input_shape=input_shape,
                  **context)
    
    def log_model_inference_complete(self, model_name: str, inference_time: float, 
                                   output_shape: tuple, **context):
        """记录模型推理完成"""
        self.debug(f"✅ 模型推理完成: {model_name} ({inference_time:.3f}s, 输出: {output_shape})",
                  action="model_inference_complete",
                  model_name=model_name,
                  inference_time=inference_time,
                  output_shape=output_shape,
                  **context)
    
    def log_gpu_memory_usage(self, model_name: str, memory_info: Dict[str, float]):
        """记录GPU内存使用情况"""
        allocated = memory_info.get('allocated', 0) / 1024**3  # GB
        cached = memory_info.get('cached', 0) / 1024**3  # GB
        total = memory_info.get('total', 0) / 1024**3  # GB
        
        self.debug(f"💾 GPU内存使用: {model_name} (已分配: {allocated:.1f}GB, 缓存: {cached:.1f}GB, 总计: {total:.1f}GB)",
                  action="gpu_memory_usage",
                  model_name=model_name,
                  memory_allocated_gb=allocated,
                  memory_cached_gb=cached,
                  memory_total_gb=total)
    
    def log_memory_cleanup(self, model_name: str, freed_memory: float):
        """记录内存清理"""
        self.info(f"🧹 内存清理: {model_name} (释放: {freed_memory / 1024**3:.1f}GB)",
                 action="memory_cleanup",
                 model_name=model_name,
                 freed_memory_gb=freed_memory / 1024**3)
    
    def log_model_download_start(self, model_name: str, download_url: str):
        """记录模型下载开始"""
        self.info(f"📥 开始下载模型: {model_name}",
                 action="model_download_start",
                 model_name=model_name,
                 download_url=download_url)
    
    def log_model_download_progress(self, model_name: str, progress: float, 
                                   downloaded_mb: float, total_mb: float):
        """记录模型下载进度"""
        self.debug(f"📊 下载进度: {model_name} ({progress:.1%}, {downloaded_mb:.1f}/{total_mb:.1f}MB)",
                  action="model_download_progress",
                  model_name=model_name,
                  progress=progress,
                  downloaded_mb=downloaded_mb,
                  total_mb=total_mb)
    
    def log_model_download_complete(self, model_name: str, download_time: float, 
                                   file_size_mb: float):
        """记录模型下载完成"""
        self.success(f"✅ 模型下载完成: {model_name} ({download_time:.1f}s, {file_size_mb:.1f}MB)",
                    action="model_download_complete",
                    model_name=model_name,
                    download_time=download_time,
                    file_size_mb=file_size_mb)
    
    def log_controlnet_switch(self, old_method: str, new_method: str):
        """记录ControlNet方法切换"""
        self.info(f"🎛️ ControlNet方法切换: {old_method} -> {new_method}",
                 action="controlnet_switch",
                 old_method=old_method,
                 new_method=new_method)


class APIServerLogger(DistributedLogger):
    """API服务器专用日志器"""
    
    def __init__(self):
        super().__init__("api_server")
    
    def log_request_start(self, method: str, path: str, user_id: Optional[str] = None, 
                         session_id: Optional[str] = None, **context):
        """记录API请求开始"""
        self.info(f"📥 {method} {path}",
                 action="request_start",
                 method=method,
                 path=path,
                 user_id=user_id,
                 session_id=session_id,
                 **context)
    
    def log_request_complete(self, method: str, path: str, status_code: int, 
                           response_time: float, **context):
        """记录API请求完成"""
        status_emoji = "✅" if status_code < 400 else "❌"
        self.info(f"{status_emoji} {method} {path} -> {status_code} ({response_time:.3f}s)",
                 action="request_complete",
                 method=method,
                 path=path,
                 status_code=status_code,
                 response_time=response_time,
                 **context)
    
    def log_file_upload(self, filename: str, file_size: int, file_type: str, **context):
        """记录文件上传"""
        self.info(f"📤 文件上传: {filename} ({file_size} bytes)",
                 action="file_upload",
                 filename=filename,
                 file_size=file_size,
                 file_type=file_type,
                 **context)
    
    def log_image_processing_start(self, task_id: str, image_path: str, 
                                  processing_type: str, **context):
        """记录图像处理开始"""
        self.info(f"🖼️ 开始图像处理: {task_id} - {processing_type}",
                 action="image_processing_start",
                 task_id=task_id,
                 image_path=image_path,
                 processing_type=processing_type,
                 **context)
    
    def log_image_processing_complete(self, task_id: str, processing_time: float, 
                                    output_path: str, **context):
        """记录图像处理完成"""
        self.success(f"✅ 图像处理完成: {task_id} ({processing_time:.2f}s)",
                    action="image_processing_complete",
                    task_id=task_id,
                    processing_time=processing_time,
                    output_path=output_path,
                    **context)
    
    def log_image_processing_failed(self, task_id: str, error: str, **context):
        """记录图像处理失败"""
        self.error(f"❌ 图像处理失败: {task_id}",
                  action="image_processing_failed",
                  task_id=task_id,
                  error=error,
                  **context)
    
    def log_model_switch(self, old_model: str, new_model: str, switch_time: float):
        """记录模型切换"""
        self.info(f"🔄 模型切换: {old_model} -> {new_model} ({switch_time:.2f}s)",
                 action="model_switch",
                 old_model=old_model,
                 new_model=new_model,
                 switch_time=switch_time)
    
    def log_session_start(self, session_id: str, user_agent: str, ip_address: str):
        """记录用户会话开始"""
        self.info(f"👤 新用户会话: {session_id}",
                 action="session_start",
                 session_id=session_id,
                 user_agent=user_agent,
                 ip_address=ip_address)
    
    def log_session_end(self, session_id: str, duration: float, requests_count: int):
        """记录用户会话结束"""
        self.info(f"👋 用户会话结束: {session_id} (时长: {duration:.1f}s, 请求: {requests_count})",
                 action="session_end",
                 session_id=session_id,
                 duration=duration,
                 requests_count=requests_count)
    
    def log_api_error(self, error_type: str, error_msg: str, endpoint: str, **context):
        """记录API错误"""
        self.error(f"❌ API错误: {error_type} - {error_msg}",
                  action="api_error",
                  error_type=error_type,
                  error_message=error_msg,
                  endpoint=endpoint,
                  **context)
    
    def log_performance_warning(self, metric: str, value: float, threshold: float, **context):
        """记录性能警告"""
        self.warning(f"⚠️ 性能警告: {metric} = {value:.2f} (阈值: {threshold})",
                    action="performance_warning",
                    metric=metric,
                    value=value,
                    threshold=threshold,
                    **context)


# 便捷函数，用于获取各种日志器
def get_scheduler_logger() -> SchedulerLogger:
    """获取调度器日志器"""
    return SchedulerLogger()

def get_worker_logger(node_id: str) -> WorkerLogger:
    """获取工作节点日志器"""
    return WorkerLogger(node_id)

def get_task_manager_logger() -> TaskManagerLogger:
    """获取任务管理器日志器"""
    return TaskManagerLogger()

def get_queue_manager_logger() -> QueueManagerLogger:
    """获取队列管理器日志器"""
    return QueueManagerLogger()

def get_api_server_logger() -> APIServerLogger:
    """获取API服务器日志器"""
    return APIServerLogger()

def get_model_manager_logger() -> ModelManagerLogger:
    """获取模型管理器日志器"""
    return ModelManagerLogger()