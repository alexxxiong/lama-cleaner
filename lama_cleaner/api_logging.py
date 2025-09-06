"""
API服务器日志中间件

为Flask应用提供详细的请求/响应日志记录，包括：
- 请求和响应日志
- 文件上传日志
- 图像处理日志
- 用户会话追踪
- 性能监控
"""

import time
import uuid
from typing import Dict, Optional, Any
from datetime import datetime
from flask import Flask, request, g, session
from werkzeug.exceptions import HTTPException

from lama_cleaner.distributed.logging import get_api_server_logger


class APILoggingMiddleware:
    """API日志中间件"""
    
    def __init__(self, app: Flask = None):
        self.logger = get_api_server_logger()
        self.sessions: Dict[str, Dict[str, Any]] = {}
        
        if app:
            self.init_app(app)
    
    def init_app(self, app: Flask):
        """初始化Flask应用的日志中间件"""
        app.before_request(self._before_request)
        app.after_request(self._after_request)
        app.errorhandler(Exception)(self._handle_exception)
        
        # 注册会话管理
        app.before_first_request(self._setup_session_tracking)
    
    def _setup_session_tracking(self):
        """设置会话追踪"""
        self.logger.info("🔧 API日志中间件已启动", action="middleware_started")
    
    def _before_request(self):
        """请求前处理"""
        # 跳过静态文件和健康检查
        if self._should_skip_logging():
            return
        
        # 记录请求开始时间
        g.request_start_time = time.time()
        
        # 生成或获取会话ID
        session_id = self._get_or_create_session_id()
        g.session_id = session_id
        
        # 获取用户信息
        user_id = self._extract_user_id()
        g.user_id = user_id
        
        # 记录请求开始
        self.logger.log_request_start(
            method=request.method,
            path=request.path,
            user_id=user_id,
            session_id=session_id,
            remote_addr=request.remote_addr,
            user_agent=request.headers.get('User-Agent', ''),
            content_length=request.content_length or 0
        )
        
        # 处理文件上传日志
        if request.files:
            self._log_file_uploads()
    
    def _after_request(self, response):
        """请求后处理"""
        # 跳过静态文件和健康检查
        if self._should_skip_logging():
            return response
        
        # 计算响应时间
        response_time = time.time() - g.get('request_start_time', time.time())
        
        # 记录请求完成
        self.logger.log_request_complete(
            method=request.method,
            path=request.path,
            status_code=response.status_code,
            response_time=response_time,
            user_id=g.get('user_id'),
            session_id=g.get('session_id'),
            response_size=len(response.get_data()) if hasattr(response, 'get_data') else 0
        )
        
        # 更新会话统计
        self._update_session_stats(response_time)
        
        # 性能监控
        self._check_performance_thresholds(response_time)
        
        return response
    
    def _handle_exception(self, error):
        """异常处理"""
        if self._should_skip_logging():
            raise error
        
        # 记录API错误
        error_type = type(error).__name__
        error_msg = str(error)
        
        if isinstance(error, HTTPException):
            status_code = error.code
        else:
            status_code = 500
        
        self.logger.log_api_error(
            error_type=error_type,
            error_msg=error_msg,
            endpoint=request.endpoint or request.path,
            method=request.method,
            path=request.path,
            status_code=status_code,
            user_id=g.get('user_id'),
            session_id=g.get('session_id')
        )
        
        # 重新抛出异常
        raise error
    
    def _should_skip_logging(self) -> bool:
        """判断是否应该跳过日志记录"""
        skip_paths = ['/static', '/favicon.ico', '/health', '/ping']
        return any(request.path.startswith(path) for path in skip_paths)
    
    def _get_or_create_session_id(self) -> str:
        """获取或创建会话ID"""
        # 尝试从session中获取
        if 'session_id' in session:
            session_id = session['session_id']
        else:
            # 创建新的会话ID
            session_id = str(uuid.uuid4())
            session['session_id'] = session_id
            
            # 记录新会话
            self.logger.log_session_start(
                session_id=session_id,
                user_agent=request.headers.get('User-Agent', ''),
                ip_address=request.remote_addr or 'unknown'
            )
            
            # 初始化会话统计
            self.sessions[session_id] = {
                'start_time': time.time(),
                'requests_count': 0,
                'total_response_time': 0.0,
                'last_activity': time.time()
            }
        
        return session_id
    
    def _extract_user_id(self) -> Optional[str]:
        """提取用户ID"""
        # 尝试从不同来源获取用户ID
        user_id = None
        
        # 从请求头获取
        if 'X-User-ID' in request.headers:
            user_id = request.headers['X-User-ID']
        
        # 从session获取
        elif 'user_id' in session:
            user_id = session['user_id']
        
        # 从查询参数获取
        elif 'user_id' in request.args:
            user_id = request.args['user_id']
        
        return user_id
    
    def _log_file_uploads(self):
        """记录文件上传"""
        for field_name, file_obj in request.files.items():
            if file_obj.filename:
                # 获取文件信息
                file_obj.seek(0, 2)  # 移动到文件末尾
                file_size = file_obj.tell()
                file_obj.seek(0)  # 重置到开头
                
                # 获取文件类型
                file_type = file_obj.content_type or 'unknown'
                
                self.logger.log_file_upload(
                    filename=file_obj.filename,
                    file_size=file_size,
                    file_type=file_type,
                    field_name=field_name,
                    user_id=g.get('user_id'),
                    session_id=g.get('session_id')
                )
    
    def _update_session_stats(self, response_time: float):
        """更新会话统计"""
        session_id = g.get('session_id')
        if session_id and session_id in self.sessions:
            stats = self.sessions[session_id]
            stats['requests_count'] += 1
            stats['total_response_time'] += response_time
            stats['last_activity'] = time.time()
    
    def _check_performance_thresholds(self, response_time: float):
        """检查性能阈值"""
        # 响应时间阈值检查
        if response_time > 5.0:  # 5秒
            self.logger.log_performance_warning(
                metric="response_time",
                value=response_time,
                threshold=5.0,
                endpoint=request.endpoint or request.path,
                method=request.method
            )
        
        # 请求大小阈值检查
        content_length = request.content_length or 0
        if content_length > 50 * 1024 * 1024:  # 50MB
            self.logger.log_performance_warning(
                metric="request_size",
                value=content_length,
                threshold=50 * 1024 * 1024,
                endpoint=request.endpoint or request.path,
                method=request.method
            )
    
    def log_image_processing(self, task_id: str, image_path: str, processing_type: str):
        """记录图像处理开始"""
        self.logger.log_image_processing_start(
            task_id=task_id,
            image_path=image_path,
            processing_type=processing_type,
            user_id=g.get('user_id'),
            session_id=g.get('session_id')
        )
    
    def log_image_processing_complete(self, task_id: str, processing_time: float, 
                                    output_path: str):
        """记录图像处理完成"""
        self.logger.log_image_processing_complete(
            task_id=task_id,
            processing_time=processing_time,
            output_path=output_path,
            user_id=g.get('user_id'),
            session_id=g.get('session_id')
        )
    
    def log_image_processing_failed(self, task_id: str, error: str):
        """记录图像处理失败"""
        self.logger.log_image_processing_failed(
            task_id=task_id,
            error=error,
            user_id=g.get('user_id'),
            session_id=g.get('session_id')
        )
    
    def log_model_switch(self, old_model: str, new_model: str, switch_time: float):
        """记录模型切换"""
        self.logger.log_model_switch(old_model, new_model, switch_time)
    
    def cleanup_expired_sessions(self, max_idle_time: int = 3600):
        """清理过期会话"""
        current_time = time.time()
        expired_sessions = []
        
        for session_id, stats in self.sessions.items():
            if current_time - stats['last_activity'] > max_idle_time:
                expired_sessions.append(session_id)
        
        for session_id in expired_sessions:
            stats = self.sessions.pop(session_id)
            duration = current_time - stats['start_time']
            
            self.logger.log_session_end(
                session_id=session_id,
                duration=duration,
                requests_count=stats['requests_count']
            )


# 全局中间件实例
api_logging_middleware = APILoggingMiddleware()

# 便捷函数
def init_api_logging(app: Flask):
    """初始化API日志中间件"""
    api_logging_middleware.init_app(app)

def log_image_processing_start(task_id: str, image_path: str, processing_type: str):
    """记录图像处理开始"""
    api_logging_middleware.log_image_processing(task_id, image_path, processing_type)

def log_image_processing_complete(task_id: str, processing_time: float, output_path: str):
    """记录图像处理完成"""
    api_logging_middleware.log_image_processing_complete(task_id, processing_time, output_path)

def log_image_processing_failed(task_id: str, error: str):
    """记录图像处理失败"""
    api_logging_middleware.log_image_processing_failed(task_id, error)

def log_model_switch(old_model: str, new_model: str, switch_time: float):
    """记录模型切换"""
    api_logging_middleware.log_model_switch(old_model, new_model, switch_time)