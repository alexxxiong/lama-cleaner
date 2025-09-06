"""
任务处理器

负责执行具体的图像处理任务，集成现有的模型管理器和处理逻辑。
"""

import os
import time
import logging
from typing import Dict, Any, Optional, Callable
from pathlib import Path
import numpy as np
from PIL import Image
import cv2

from ..model_manager import ModelManager
from ..schema import Config
from ..helper import load_img, numpy_to_bytes, resize_max_size
from .models import Task, TaskType, TaskStatus
from .config import get_config

logger = logging.getLogger(__name__)


class TaskProcessor:
    """任务处理器"""
    
    def __init__(self, device: str = "cpu", **kwargs):
        self.device = device
        self.config = get_config()
        self.kwargs = kwargs
        
        # 模型管理器
        self.model_manager: Optional[ModelManager] = None
        self.current_model = None
        
        # 插件管理器
        self.plugins = {}
        
        # 进度回调
        self.progress_callbacks: Dict[str, Callable] = {}
        
        logger.info(f"任务处理器初始化完成，设备: {device}")
    
    def process_task(self, task: Task) -> Task:
        """处理任务"""
        try:
            logger.info(f"开始处理任务: {task.task_id} ({task.task_type.value})")
            
            # 更新任务状态
            task.status = TaskStatus.PROCESSING
            task.updated_at = time.time()
            
            # 根据任务类型调用相应的处理方法
            start_time = time.time()
            
            if task.task_type == TaskType.INPAINT:
                result_path = self._process_inpaint_task(task)
            elif task.task_type == TaskType.PLUGIN:
                result_path = self._process_plugin_task(task)
            elif task.task_type == TaskType.UPSCALE:
                result_path = self._process_upscale_task(task)
            elif task.task_type == TaskType.SEGMENT:
                result_path = self._process_segment_task(task)
            else:
                raise ValueError(f"不支持的任务类型: {task.task_type.value}")
            
            # 更新任务结果
            processing_time = time.time() - start_time
            task.result_path = result_path
            task.processing_time = processing_time
            task.status = TaskStatus.COMPLETED
            
            logger.info(f"任务处理完成: {task.task_id} ({processing_time:.2f}s)")
            
        except Exception as e:
            task.status = TaskStatus.FAILED
            task.error_message = str(e)
            logger.error(f"任务处理失败 {task.task_id}: {e}")
        
        finally:
            task.updated_at = time.time()
        
        return task
    
    def _process_inpaint_task(self, task: Task) -> str:
        """处理图像修复任务"""
        config_dict = task.config
        model_name = config_dict.get('model', 'lama')
        
        # 确保模型已加载
        self._ensure_model_loaded(model_name)
        
        # 加载图像和遮罩
        image = self._load_image(task.image_path)
        mask = self._load_mask(task.mask_path) if task.mask_path else None
        
        # 创建配置对象
        config = self._create_config(config_dict)
        
        # 报告进度
        self._report_progress(task.task_id, 0.1, "模型加载完成")
        
        # 执行图像修复
        self._report_progress(task.task_id, 0.3, "开始图像修复")
        result_image = self.model_manager(image, mask, config)
        
        # 保存结果
        self._report_progress(task.task_id, 0.9, "保存结果")
        result_path = self._save_result(task.task_id, result_image, "inpaint")
        
        self._report_progress(task.task_id, 1.0, "处理完成")
        return result_path
    
    def _process_plugin_task(self, task: Task) -> str:
        """处理插件任务"""
        plugin_name = task.config.get('plugin', '')
        
        if not plugin_name:
            raise ValueError("插件任务缺少插件名称")
        
        # 加载图像
        image = self._load_image(task.image_path)
        
        # 执行插件处理
        self._report_progress(task.task_id, 0.2, f"执行插件: {plugin_name}")
        
        if plugin_name == "RemoveBG":
            result_image = self._run_remove_bg_plugin(image, task.config)
        elif plugin_name == "RealESRGAN":
            result_image = self._run_upscale_plugin(image, task.config)
        elif plugin_name == "GFPGAN":
            result_image = self._run_face_restore_plugin(image, task.config)
        elif plugin_name == "RestoreFormer":
            result_image = self._run_face_restore_plugin(image, task.config, "RestoreFormer")
        elif plugin_name == "InteractiveSeg":
            result_image = self._run_interactive_seg_plugin(image, task.config)
        else:
            raise ValueError(f"不支持的插件: {plugin_name}")
        
        # 保存结果
        self._report_progress(task.task_id, 0.9, "保存结果")
        result_path = self._save_result(task.task_id, result_image, f"plugin_{plugin_name}")
        
        self._report_progress(task.task_id, 1.0, "处理完成")
        return result_path
    
    def _process_upscale_task(self, task: Task) -> str:
        """处理图像放大任务"""
        scale_factor = task.config.get('scale', 2)
        method = task.config.get('method', 'RealESRGAN')
        
        # 加载图像
        image = self._load_image(task.image_path)
        
        # 执行放大
        self._report_progress(task.task_id, 0.3, f"执行 {scale_factor}x 放大")
        
        if method == 'RealESRGAN':
            result_image = self._run_upscale_plugin(image, {'scale': scale_factor})
        else:
            # 简单的双线性插值放大
            h, w = image.shape[:2]
            new_h, new_w = int(h * scale_factor), int(w * scale_factor)
            result_image = cv2.resize(image, (new_w, new_h), interpolation=cv2.INTER_LINEAR)
        
        # 保存结果
        self._report_progress(task.task_id, 0.9, "保存结果")
        result_path = self._save_result(task.task_id, result_image, f"upscale_{scale_factor}x")
        
        self._report_progress(task.task_id, 1.0, "处理完成")
        return result_path
    
    def _process_segment_task(self, task: Task) -> str:
        """处理图像分割任务"""
        method = task.config.get('method', 'SAM')
        
        # 加载图像
        image = self._load_image(task.image_path)
        
        # 执行分割
        self._report_progress(task.task_id, 0.3, f"执行图像分割: {method}")
        
        if method == 'SAM':
            result_image = self._run_sam_segmentation(image, task.config)
        else:
            # 简单的边缘检测分割
            gray = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
            edges = cv2.Canny(gray, 50, 150)
            result_image = cv2.cvtColor(edges, cv2.COLOR_GRAY2RGB)
        
        # 保存结果
        self._report_progress(task.task_id, 0.9, "保存结果")
        result_path = self._save_result(task.task_id, result_image, "segment")
        
        self._report_progress(task.task_id, 1.0, "处理完成")
        return result_path
    
    def _ensure_model_loaded(self, model_name: str):
        """确保指定模型已加载"""
        if self.model_manager is None:
            logger.info(f"初始化模型管理器: {model_name}")
            import torch
            device = torch.device(self.device)
            self.model_manager = ModelManager(model_name, device, **self.kwargs)
            self.current_model = model_name
        elif self.current_model != model_name:
            logger.info(f"切换模型: {self.current_model} -> {model_name}")
            self.model_manager.switch(model_name, **self.kwargs)
            self.current_model = model_name
    
    def _load_image(self, image_path: str) -> np.ndarray:
        """加载图像"""
        if not image_path or not os.path.exists(image_path):
            raise FileNotFoundError(f"图像文件不存在: {image_path}")
        
        try:
            image = load_img(image_path, gray=False)
            logger.debug(f"加载图像: {image_path}, 尺寸: {image.shape}")
            return image
        except Exception as e:
            raise ValueError(f"加载图像失败 {image_path}: {e}")
    
    def _load_mask(self, mask_path: str) -> Optional[np.ndarray]:
        """加载遮罩"""
        if not mask_path or not os.path.exists(mask_path):
            return None
        
        try:
            mask = load_img(mask_path, gray=True)
            logger.debug(f"加载遮罩: {mask_path}, 尺寸: {mask.shape}")
            return mask
        except Exception as e:
            logger.warning(f"加载遮罩失败 {mask_path}: {e}")
            return None
    
    def _create_config(self, config_dict: Dict[str, Any]) -> Config:
        """创建配置对象"""
        config = Config()
        
        # 基础配置
        config.ldm_steps = config_dict.get('ldm_steps', 25)
        config.ldm_sampler = config_dict.get('ldm_sampler', 'plms')
        config.hd_strategy = config_dict.get('hd_strategy', 'Original')
        config.hd_strategy_crop_margin = config_dict.get('hd_strategy_crop_margin', 32)
        config.hd_strategy_crop_trigger_size = config_dict.get('hd_strategy_crop_trigger_size', 1280)
        config.hd_strategy_resize_limit = config_dict.get('hd_strategy_resize_limit', 2048)
        
        # Stable Diffusion 配置
        config.prompt = config_dict.get('prompt', '')
        config.negative_prompt = config_dict.get('negative_prompt', '')
        config.sd_steps = config_dict.get('sd_steps', 20)
        config.sd_guidance_scale = config_dict.get('sd_guidance_scale', 7.5)
        config.sd_strength = config_dict.get('sd_strength', 1.0)
        config.sd_seed = config_dict.get('sd_seed', -1)
        config.sd_match_histograms = config_dict.get('sd_match_histograms', False)
        
        # ControlNet 配置
        config.controlnet_method = config_dict.get('controlnet_method', '')
        config.controlnet_conditioning_scale = config_dict.get('controlnet_conditioning_scale', 1.0)
        
        # Paint by Example 配置
        config.paint_by_example_example_image = config_dict.get('paint_by_example_example_image')
        
        # InstructPix2Pix 配置
        config.p2p_image_guidance_scale = config_dict.get('p2p_image_guidance_scale', 1.5)
        
        return config
    
    def _save_result(self, task_id: str, result_image: np.ndarray, prefix: str = "result") -> str:
        """保存处理结果"""
        # 创建结果目录
        result_dir = Path(self.config.storage.result_dir) / "tasks" / task_id
        result_dir.mkdir(parents=True, exist_ok=True)
        
        # 生成文件名
        timestamp = int(time.time())
        result_filename = f"{prefix}_{timestamp}.jpg"
        result_path = result_dir / result_filename
        
        # 保存图像
        try:
            if isinstance(result_image, np.ndarray):
                # 确保图像格式正确
                if result_image.dtype != np.uint8:
                    result_image = (result_image * 255).astype(np.uint8)
                
                # 转换颜色空间（如果需要）
                if len(result_image.shape) == 3 and result_image.shape[2] == 3:
                    # RGB to BGR for OpenCV
                    result_image = cv2.cvtColor(result_image, cv2.COLOR_RGB2BGR)
                
                cv2.imwrite(str(result_path), result_image)
            else:
                # PIL Image
                result_image.save(str(result_path), 'JPEG', quality=95)
            
            logger.info(f"结果已保存: {result_path}")
            return str(result_path)
            
        except Exception as e:
            raise RuntimeError(f"保存结果失败: {e}")
    
    def _report_progress(self, task_id: str, progress: float, message: str = ""):
        """报告任务进度"""
        callback = self.progress_callbacks.get(task_id)
        if callback:
            try:
                callback(progress, message)
            except Exception as e:
                logger.error(f"进度回调失败: {e}")
        
        logger.debug(f"任务进度 {task_id}: {progress:.1%} - {message}")
    
    def register_progress_callback(self, task_id: str, callback: Callable[[float, str], None]):
        """注册进度回调"""
        self.progress_callbacks[task_id] = callback
    
    def unregister_progress_callback(self, task_id: str):
        """注销进度回调"""
        self.progress_callbacks.pop(task_id, None)
    
    # 插件处理方法
    def _run_remove_bg_plugin(self, image: np.ndarray, config: Dict) -> np.ndarray:
        """运行背景移除插件"""
        try:
            from ..plugins.remove_bg import RemoveBGPlugin
            plugin = RemoveBGPlugin()
            return plugin.process(image, config)
        except ImportError:
            logger.warning("RemoveBG 插件不可用，使用简单的背景移除")
            # 简单的背景移除（基于颜色阈值）
            return self._simple_background_removal(image)
    
    def _run_upscale_plugin(self, image: np.ndarray, config: Dict) -> np.ndarray:
        """运行图像放大插件"""
        try:
            from ..plugins.realesrgan import RealESRGANPlugin
            plugin = RealESRGANPlugin()
            return plugin.process(image, config)
        except ImportError:
            logger.warning("RealESRGAN 插件不可用，使用双线性插值")
            scale = config.get('scale', 2)
            h, w = image.shape[:2]
            return cv2.resize(image, (w * scale, h * scale), interpolation=cv2.INTER_LINEAR)
    
    def _run_face_restore_plugin(self, image: np.ndarray, config: Dict, method: str = "GFPGAN") -> np.ndarray:
        """运行人脸修复插件"""
        try:
            if method == "GFPGAN":
                from ..plugins.gfpgan_plugin import GFPGANPlugin
                plugin = GFPGANPlugin()
            else:
                from ..plugins.restoreformer import RestoreFormerPlugin
                plugin = RestoreFormerPlugin()
            
            return plugin.process(image, config)
        except ImportError:
            logger.warning(f"{method} 插件不可用，返回原图")
            return image
    
    def _run_interactive_seg_plugin(self, image: np.ndarray, config: Dict) -> np.ndarray:
        """运行交互式分割插件"""
        try:
            from ..plugins.interactive_seg import InteractiveSegPlugin
            plugin = InteractiveSegPlugin()
            return plugin.process(image, config)
        except ImportError:
            logger.warning("InteractiveSeg 插件不可用，使用简单分割")
            return self._simple_segmentation(image)
    
    def _run_sam_segmentation(self, image: np.ndarray, config: Dict) -> np.ndarray:
        """运行 SAM 分割"""
        try:
            from ..plugins.segment_anything import SAMPlugin
            plugin = SAMPlugin()
            return plugin.process(image, config)
        except ImportError:
            logger.warning("SAM 插件不可用，使用简单分割")
            return self._simple_segmentation(image)
    
    # 简单的后备处理方法
    def _simple_background_removal(self, image: np.ndarray) -> np.ndarray:
        """简单的背景移除"""
        # 使用 GrabCut 算法
        mask = np.zeros(image.shape[:2], np.uint8)
        bgd_model = np.zeros((1, 65), np.float64)
        fgd_model = np.zeros((1, 65), np.float64)
        
        h, w = image.shape[:2]
        rect = (10, 10, w-20, h-20)  # 假设前景在中心区域
        
        cv2.grabCut(image, mask, rect, bgd_model, fgd_model, 5, cv2.GC_INIT_WITH_RECT)
        
        mask2 = np.where((mask == 2) | (mask == 0), 0, 1).astype('uint8')
        result = image * mask2[:, :, np.newaxis]
        
        return result
    
    def _simple_segmentation(self, image: np.ndarray) -> np.ndarray:
        """简单的图像分割"""
        # 使用 K-means 聚类进行分割
        data = image.reshape((-1, 3))
        data = np.float32(data)
        
        criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 20, 1.0)
        k = 4  # 分割为4个区域
        
        _, labels, centers = cv2.kmeans(data, k, None, criteria, 10, cv2.KMEANS_RANDOM_CENTERS)
        
        # 转换回图像格式
        centers = np.uint8(centers)
        segmented_data = centers[labels.flatten()]
        segmented_image = segmented_data.reshape(image.shape)
        
        return segmented_image
    
    def cleanup(self):
        """清理资源"""
        if self.model_manager:
            # 清理模型内存
            try:
                import torch
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
                del self.model_manager
                self.model_manager = None
                logger.info("模型管理器已清理")
            except Exception as e:
                logger.error(f"清理模型管理器失败: {e}")
        
        # 清理进度回调
        self.progress_callbacks.clear()
    
    def get_supported_models(self) -> list:
        """获取支持的模型列表"""
        from ..model_manager import models
        return list(models.keys())
    
    def is_model_available(self, model_name: str) -> bool:
        """检查模型是否可用"""
        try:
            from ..model_manager import models
            if model_name in models:
                return models[model_name].is_downloaded()
            return False
        except Exception:
            return False


class TaskProcessorPool:
    """任务处理器池"""
    
    def __init__(self, pool_size: int = 1, device: str = "cpu", **kwargs):
        self.pool_size = pool_size
        self.device = device
        self.kwargs = kwargs
        self.processors = []
        self.available_processors = []
        self.busy_processors = set()
        
        # 初始化处理器池
        for i in range(pool_size):
            processor = TaskProcessor(device=device, **kwargs)
            self.processors.append(processor)
            self.available_processors.append(processor)
        
        logger.info(f"任务处理器池初始化完成，大小: {pool_size}")
    
    def get_processor(self) -> Optional[TaskProcessor]:
        """获取可用的处理器"""
        if self.available_processors:
            processor = self.available_processors.pop(0)
            self.busy_processors.add(processor)
            return processor
        return None
    
    def return_processor(self, processor: TaskProcessor):
        """归还处理器"""
        if processor in self.busy_processors:
            self.busy_processors.remove(processor)
            self.available_processors.append(processor)
    
    def cleanup(self):
        """清理所有处理器"""
        for processor in self.processors:
            processor.cleanup()
        
        self.processors.clear()
        self.available_processors.clear()
        self.busy_processors.clear()
        
        logger.info("任务处理器池已清理")
    
    def get_status(self) -> Dict:
        """获取处理器池状态"""
        return {
            'pool_size': self.pool_size,
            'available': len(self.available_processors),
            'busy': len(self.busy_processors),
            'device': self.device
        }


def create_task_processor(device: str = "cpu", **kwargs) -> TaskProcessor:
    """创建任务处理器的便捷函数"""
    return TaskProcessor(device=device, **kwargs)


def create_processor_pool(pool_size: int = 1, device: str = "cpu", **kwargs) -> TaskProcessorPool:
    """创建任务处理器池的便捷函数"""
    return TaskProcessorPool(pool_size=pool_size, device=device, **kwargs)