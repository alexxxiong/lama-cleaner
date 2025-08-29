"""
Flask API 集成模块

集成现有的 Flask API 端点，支持分布式任务处理。
保持与现有 API 的兼容性，同时添加新的分布式功能。
"""

import logging
import os
import tempfile
from typing import Dict, Any, Optional, Tuple
from datetime import datetime
from flask import Flask, request, jsonify, send_file
from werkzeug.utils import secure_filename
import uuid

from .scheduler import get_scheduler, TaskSubmissionRequest
from .models import TaskType, TaskPriority, TaskStatus
from .config import get_config

logger = logging.getLogger(__name__)


class DistributedAPIIntegration:
    """分布式 API 集成"""
    
    def __init__(self, app: Flask):
        self.app = app
        self.config = get_config()
        self.scheduler = get_scheduler()
        
        # 文件存储配置
        self.upload_folder = self.config.storage.base_path
        self.temp_folder = self.config.storage.temp_path
        
        # 确保目录存在
        os.makedirs(self.upload_folder, exist_ok=True)
        os.makedirs(self.temp_folder, exist_ok=True)
        
        # 注册路由
        self._register_routes()
    
    def _register_routes(self):
        """注册 API 路由"""
        
        @self.app.route('/api/v1/inpaint', methods=['POST'])
        def distributed_inpaint():
            """分布式图像修复端点"""
            return self._handle_inpaint_request()
        
        @self.app.route('/api/v1/run_plugin', methods=['POST'])
        def distributed_run_plugin():
            """分布式插件处理端点"""
            return self._handle_plugin_request()
        
        @self.app.route('/api/v1/task/<task_id>/status', methods=['GET'])
        def get_task_status(task_id: str):
            """获取任务状态"""
            return self._handle_task_status_request(task_id)
        
        @self.app.route('/api/v1/task/<task_id>/cancel', methods=['POST'])
        def cancel_task(task_id: str):
            """取消任务"""
            return self._handle_task_cancel_request(task_id)
        
        @self.app.route('/api/v1/task/<task_id>/result', methods=['GET'])
        def get_task_result(task_id: str):
            """获取任务结果"""
            return self._handle_task_result_request(task_id)
        
        @self.app.route('/api/v1/tasks/batch', methods=['POST'])
        def submit_batch_tasks():
            """批量提交任务"""
            return self._handle_batch_tasks_request()
        
        @self.app.route('/api/v1/user/<user_id>/tasks', methods=['GET'])
        def get_user_tasks(user_id: str):
            """获取用户任务"""
            return self._handle_user_tasks_request(user_id)
        
        @self.app.route('/api/v1/scheduler/status', methods=['GET'])
        def get_scheduler_status():
            """获取调度器状态"""
            return self._handle_scheduler_status_request()
    
    def _handle_inpaint_request(self) -> Tuple[Dict[str, Any], int]:
        """处理图像修复请求"""
        try:
            # 检查是否启用分布式处理
            if not self.config.enabled:
                return {'error': '分布式处理未启用'}, 400
            
            # 验证请求
            if 'image' not in request.files:
                return {'error': '缺少图像文件'}, 400
            
            if 'mask' not in request.files:
                return {'error': '缺少遮罩文件'}, 400
            
            image_file = request.files['image']
            mask_file = request.files['mask']
            
            if image_file.filename == '' or mask_file.filename == '':
                return {'error': '文件名不能为空'}, 400
            
            # 保存上传的文件
            image_path, mask_path = self._save_uploaded_files(image_file, mask_file)
            
            # 解析配置参数
            config = self._parse_inpaint_config(request.form)
            
            # 获取优先级
            priority = self._parse_priority(request.form.get('priority', 'normal'))
            
            # 获取用户信息
            user_id = request.form.get('user_id')
            session_id = request.form.get('session_id', str(uuid.uuid4()))
            
            # 提交任务
            task_id = self.scheduler.submit_inpaint_task(
                image_path=image_path,
                mask_path=mask_path,
                config=config,
                priority=priority,
                user_id=user_id,
                session_id=session_id
            )
            
            return {
                'task_id': task_id,
                'status': 'submitted',
                'message': '任务已提交，正在处理中'
            }, 202
            
        except Exception as e:
            logger.error(f"处理图像修复请求失败: {e}")
            return {'error': str(e)}, 500
    
    def _handle_plugin_request(self) -> Tuple[Dict[str, Any], int]:
        """处理插件请求"""
        try:
            # 检查是否启用分布式处理
            if not self.config.enabled:
                return {'error': '分布式处理未启用'}, 400
            
            # 验证请求
            if 'image' not in request.files:
                return {'error': '缺少图像文件'}, 400
            
            if 'plugin_name' not in request.form:
                return {'error': '缺少插件名称'}, 400
            
            image_file = request.files['image']
            plugin_name = request.form['plugin_name']
            
            if image_file.filename == '':
                return {'error': '文件名不能为空'}, 400
            
            # 保存上传的文件
            image_path = self._save_single_file(image_file)
            
            # 解析配置参数
            config = self._parse_plugin_config(request.form, plugin_name)
            
            # 获取优先级
            priority = self._parse_priority(request.form.get('priority', 'normal'))
            
            # 获取用户信息
            user_id = request.form.get('user_id')
            session_id = request.form.get('session_id', str(uuid.uuid4()))
            
            # 提交任务
            task_id = self.scheduler.submit_plugin_task(
                image_path=image_path,
                plugin_name=plugin_name,
                config=config,
                priority=priority,
                user_id=user_id,
                session_id=session_id
            )
            
            return {
                'task_id': task_id,
                'status': 'submitted',
                'message': '任务已提交，正在处理中'
            }, 202
            
        except Exception as e:
            logger.error(f"处理插件请求失败: {e}")
            return {'error': str(e)}, 500
    
    def _handle_task_status_request(self, task_id: str) -> Tuple[Dict[str, Any], int]:
        """处理任务状态请求"""
        try:
            status = self.scheduler.get_task_status(task_id)
            if not status:
                return {'error': '任务不存在'}, 404
            
            return status, 200
            
        except Exception as e:
            logger.error(f"获取任务状态失败 {task_id}: {e}")
            return {'error': str(e)}, 500
    
    def _handle_task_cancel_request(self, task_id: str) -> Tuple[Dict[str, Any], int]:
        """处理任务取消请求"""
        try:
            success = self.scheduler.cancel_task(task_id)
            if success:
                return {'message': '任务已取消'}, 200
            else:
                return {'error': '任务无法取消'}, 400
                
        except Exception as e:
            logger.error(f"取消任务失败 {task_id}: {e}")
            return {'error': str(e)}, 500
    
    def _handle_task_result_request(self, task_id: str) -> Any:
        """处理任务结果请求"""
        try:
            task = self.scheduler.task_manager.get_task(task_id)
            if not task:
                return jsonify({'error': '任务不存在'}), 404
            
            if task.status != TaskStatus.COMPLETED:
                return jsonify({
                    'error': '任务未完成',
                    'status': task.status.value
                }), 400
            
            if not task.result_path or not os.path.exists(task.result_path):
                return jsonify({'error': '结果文件不存在'}), 404
            
            return send_file(
                task.result_path,
                as_attachment=True,
                download_name=f"result_{task_id}.jpg"
            )
            
        except Exception as e:
            logger.error(f"获取任务结果失败 {task_id}: {e}")
            return jsonify({'error': str(e)}), 500
    
    def _handle_batch_tasks_request(self) -> Tuple[Dict[str, Any], int]:
        """处理批量任务请求"""
        try:
            # 解析批量任务请求
            data = request.get_json()
            if not data or 'tasks' not in data:
                return {'error': '缺少任务数据'}, 400
            
            requests = []
            for task_data in data['tasks']:
                # 这里需要根据实际需求解析批量任务数据
                # 暂时返回未实现错误
                pass
            
            return {'error': '批量任务功能暂未实现'}, 501
            
        except Exception as e:
            logger.error(f"处理批量任务请求失败: {e}")
            return {'error': str(e)}, 500
    
    def _handle_user_tasks_request(self, user_id: str) -> Tuple[Dict[str, Any], int]:
        """处理用户任务请求"""
        try:
            limit = request.args.get('limit', type=int)
            tasks = self.scheduler.get_user_tasks(user_id, limit)
            
            task_list = []
            for task in tasks:
                task_list.append({
                    'task_id': task.task_id,
                    'task_type': task.task_type.value,
                    'status': task.status.value,
                    'priority': task.priority.value,
                    'created_at': task.created_at.isoformat(),
                    'updated_at': task.updated_at.isoformat(),
                    'processing_time': task.processing_time,
                    'error_message': task.error_message
                })
            
            return {
                'user_id': user_id,
                'tasks': task_list,
                'total': len(task_list)
            }, 200
            
        except Exception as e:
            logger.error(f"获取用户任务失败 {user_id}: {e}")
            return {'error': str(e)}, 500
    
    def _handle_scheduler_status_request(self) -> Tuple[Dict[str, Any], int]:
        """处理调度器状态请求"""
        try:
            status = self.scheduler.get_scheduler_statistics()
            return status, 200
            
        except Exception as e:
            logger.error(f"获取调度器状态失败: {e}")
            return {'error': str(e)}, 500
    
    def _save_uploaded_files(self, image_file, mask_file) -> Tuple[str, str]:
        """保存上传的文件"""
        # 生成唯一的文件名
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        unique_id = str(uuid.uuid4())[:8]
        
        # 保存图像文件
        image_filename = f"{timestamp}_{unique_id}_image.jpg"
        image_path = os.path.join(self.upload_folder, image_filename)
        image_file.save(image_path)
        
        # 保存遮罩文件
        mask_filename = f"{timestamp}_{unique_id}_mask.png"
        mask_path = os.path.join(self.upload_folder, mask_filename)
        mask_file.save(mask_path)
        
        return image_path, mask_path
    
    def _save_single_file(self, file) -> str:
        """保存单个文件"""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        unique_id = str(uuid.uuid4())[:8]
        
        # 获取文件扩展名
        filename = secure_filename(file.filename)
        ext = os.path.splitext(filename)[1] or '.jpg'
        
        # 生成新文件名
        new_filename = f"{timestamp}_{unique_id}{ext}"
        file_path = os.path.join(self.upload_folder, new_filename)
        file.save(file_path)
        
        return file_path
    
    def _parse_inpaint_config(self, form_data) -> Dict[str, Any]:
        """解析图像修复配置"""
        config = {}
        
        # 模型配置
        config['model'] = form_data.get('model', 'lama')
        config['device'] = form_data.get('device', 'auto')
        
        # Stable Diffusion 配置
        if config['model'].startswith('sd'):
            config['prompt'] = form_data.get('prompt', '')
            config['negative_prompt'] = form_data.get('negative_prompt', '')
            config['num_inference_steps'] = int(form_data.get('num_inference_steps', 20))
            config['guidance_scale'] = float(form_data.get('guidance_scale', 7.5))
            config['strength'] = float(form_data.get('strength', 0.75))
        
        # 通用配置
        config['hd_strategy'] = form_data.get('hd_strategy', 'none')
        config['hd_strategy_crop_margin'] = int(form_data.get('hd_strategy_crop_margin', 32))
        config['hd_strategy_crop_trigger_size'] = int(form_data.get('hd_strategy_crop_trigger_size', 512))
        config['hd_strategy_resize_limit'] = int(form_data.get('hd_strategy_resize_limit', 2048))
        
        # 其他配置
        config['use_croper'] = form_data.get('use_croper', 'false').lower() == 'true'
        config['croper_x'] = int(form_data.get('croper_x', 0))
        config['croper_y'] = int(form_data.get('croper_y', 0))
        config['croper_height'] = int(form_data.get('croper_height', 512))
        config['croper_width'] = int(form_data.get('croper_width', 512))
        
        return config
    
    def _parse_plugin_config(self, form_data, plugin_name: str) -> Dict[str, Any]:
        """解析插件配置"""
        config = {'plugin_name': plugin_name}
        
        # 根据插件类型解析特定配置
        if plugin_name == 'realesrgan':
            config['scale'] = int(form_data.get('scale', 4))
            config['model_name'] = form_data.get('model_name', 'RealESRGAN_x4plus')
        
        elif plugin_name == 'gfpgan':
            config['scale'] = int(form_data.get('scale', 2))
            config['bg_upsampler'] = form_data.get('bg_upsampler', 'realesrgan')
        
        elif plugin_name == 'remove_bg':
            config['model'] = form_data.get('model', 'u2net')
        
        elif plugin_name == 'interactive_seg':
            config['positive_points'] = form_data.get('positive_points', '[]')
            config['negative_points'] = form_data.get('negative_points', '[]')
        
        return config
    
    def _parse_priority(self, priority_str: str) -> TaskPriority:
        """解析优先级"""
        priority_map = {
            'low': TaskPriority.LOW,
            'normal': TaskPriority.NORMAL,
            'high': TaskPriority.HIGH,
            'urgent': TaskPriority.URGENT
        }
        
        return priority_map.get(priority_str.lower(), TaskPriority.NORMAL)


def setup_distributed_api(app: Flask) -> DistributedAPIIntegration:
    """设置分布式 API 集成"""
    return DistributedAPIIntegration(app)