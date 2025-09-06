import torch
import gc
import time
from typing import Dict, Optional

from loguru import logger
from lama_cleaner.distributed.logging import get_model_manager_logger

from lama_cleaner.const import SD15_MODELS
from lama_cleaner.helper import switch_mps_device
from lama_cleaner.model.controlnet import ControlNet
from lama_cleaner.model.fcf import FcF
from lama_cleaner.model.lama import LaMa
from lama_cleaner.model.ldm import LDM
from lama_cleaner.model.manga import Manga
from lama_cleaner.model.mat import MAT
from lama_cleaner.model.paint_by_example import PaintByExample
from lama_cleaner.model.instruct_pix2pix import InstructPix2Pix
from lama_cleaner.model.sd import SD15, SD2, Anything4, RealisticVision14
from lama_cleaner.model.utils import torch_gc
from lama_cleaner.model.zits import ZITS
from lama_cleaner.model.opencv2 import OpenCV2
from lama_cleaner.schema import Config

models = {
    "lama": LaMa,
    "ldm": LDM,
    "zits": ZITS,
    "mat": MAT,
    "fcf": FcF,
    SD15.name: SD15,
    Anything4.name: Anything4,
    RealisticVision14.name: RealisticVision14,
    "cv2": OpenCV2,
    "manga": Manga,
    "sd2": SD2,
    "paint_by_example": PaintByExample,
    "instruct_pix2pix": InstructPix2Pix,
}


class ModelManager:
    def __init__(self, name: str, device: torch.device, **kwargs):
        self.name = name
        self.device = device
        self.kwargs = kwargs
        
        # 使用专用的模型管理器日志器
        self.logger = get_model_manager_logger()
        
        self.model = self.init_model(name, device, **kwargs)

    def init_model(self, name: str, device, **kwargs):
        # 记录模型加载开始
        self.logger.log_model_loading_start(
            model_name=name,
            device=str(device),
            kwargs=kwargs
        )
        
        start_time = time.time()
        
        try:
            if name in SD15_MODELS and kwargs.get("sd_controlnet", False):
                model = ControlNet(device, **{**kwargs, "name": name})
            elif name in models:
                model = models[name](device, **kwargs)
            else:
                raise NotImplementedError(f"Not supported model: {name}")
            
            loading_time = time.time() - start_time
            
            # 获取内存使用情况
            memory_usage = self._get_memory_usage()
            
            # 记录模型加载完成
            self.logger.log_model_loading_complete(
                model_name=name,
                loading_time=loading_time,
                memory_usage=memory_usage
            )
            
            return model
            
        except Exception as e:
            loading_time = time.time() - start_time
            
            # 记录模型加载失败
            self.logger.log_model_loading_failed(
                model_name=name,
                error=str(e),
                loading_time=loading_time
            )
            raise

    def is_downloaded(self, name: str) -> bool:
        if name in models:
            return models[name].is_downloaded()
        else:
            raise NotImplementedError(f"Not supported model: {name}")

    def __call__(self, image, mask, config: Config):
        self.switch_controlnet_method(control_method=config.controlnet_method)
        
        # 记录推理开始
        input_shape = image.shape if hasattr(image, 'shape') else 'unknown'
        self.logger.log_model_inference_start(
            model_name=self.name,
            input_shape=input_shape
        )
        
        start_time = time.time()
        
        try:
            result = self.model(image, mask, config)
            inference_time = time.time() - start_time
            
            # 记录推理完成
            output_shape = result.shape if hasattr(result, 'shape') else 'unknown'
            self.logger.log_model_inference_complete(
                model_name=self.name,
                inference_time=inference_time,
                output_shape=output_shape
            )
            
            # 记录GPU内存使用情况
            memory_info = self._get_memory_usage()
            if memory_info:
                self.logger.log_gpu_memory_usage(self.name, memory_info)
            
            return result
            
        except Exception as e:
            inference_time = time.time() - start_time
            self.logger.error(f"模型推理失败: {self.name}",
                            action="model_inference_failed",
                            model_name=self.name,
                            error=str(e),
                            inference_time=inference_time)
            raise

    def switch(self, new_name: str, **kwargs):
        if new_name == self.name:
            return
        
        old_name = self.name
        
        # 记录模型切换开始
        self.logger.log_model_switch_start(old_name, new_name)
        
        start_time = time.time()
        
        try:
            # 记录内存清理前的使用情况
            memory_before = self._get_memory_usage()
            
            if torch.cuda.memory_allocated() > 0:
                # Clear current loaded model from memory
                allocated_before = torch.cuda.memory_allocated()
                torch.cuda.empty_cache()
                del self.model
                gc.collect()
                
                # 记录内存清理
                freed_memory = allocated_before - torch.cuda.memory_allocated()
                if freed_memory > 0:
                    self.logger.log_memory_cleanup(old_name, freed_memory)

            self.model = self.init_model(
                new_name, switch_mps_device(new_name, self.device), **self.kwargs
            )
            self.name = new_name
            
            switch_time = time.time() - start_time
            
            # 记录模型切换完成
            self.logger.log_model_switch_complete(old_name, new_name, switch_time)
            
        except NotImplementedError as e:
            switch_time = time.time() - start_time
            self.logger.error(f"模型切换失败: {old_name} -> {new_name}",
                            action="model_switch_failed",
                            old_model=old_name,
                            new_model=new_name,
                            error=str(e),
                            switch_time=switch_time)
            raise e

    def switch_controlnet_method(self, control_method: str):
        if not self.kwargs.get("sd_controlnet"):
            return
        if self.kwargs["sd_controlnet_method"] == control_method:
            return
        if not hasattr(self.model, "is_local_sd_model"):
            return

        # 记录ControlNet方法切换
        old_method = self.kwargs["sd_controlnet_method"]
        self.logger.log_controlnet_switch(old_method, control_method)

        if self.model.is_local_sd_model:
            # is_native_control_inpaint 表示加载了普通 SD 模型
            if (
                self.model.is_native_control_inpaint
                and control_method != "control_v11p_sd15_inpaint"
            ):
                error_msg = (f"--sd-local-model-path load a normal SD model, "
                           f"to use {control_method} you should load an inpainting SD model")
                self.logger.error(f"ControlNet方法切换失败: {error_msg}",
                                action="controlnet_switch_failed",
                                old_method=old_method,
                                new_method=control_method,
                                error=error_msg)
                raise RuntimeError(error_msg)
    
    def _get_memory_usage(self) -> Optional[Dict[str, float]]:
        """获取内存使用情况"""
        try:
            if torch.cuda.is_available():
                return {
                    'allocated': torch.cuda.memory_allocated(),
                    'cached': torch.cuda.memory_reserved(),
                    'total': torch.cuda.get_device_properties(0).total_memory
                }
        except Exception as e:
            self.logger.debug(f"获取GPU内存信息失败: {e}")
        
        return None
            elif (
                not self.model.is_native_control_inpaint
                and control_method == "control_v11p_sd15_inpaint"
            ):
                raise RuntimeError(
                    f"--sd-local-model-path load an inpainting SD model, "
                    f"to use {control_method} you should load a norml SD model"
                )

        del self.model
        torch_gc()

        old_method = self.kwargs["sd_controlnet_method"]
        self.kwargs["sd_controlnet_method"] = control_method
        self.model = self.init_model(
            self.name, switch_mps_device(self.name, self.device), **self.kwargs
        )
        logger.info(f"Switch ControlNet method from {old_method} to {control_method}")
