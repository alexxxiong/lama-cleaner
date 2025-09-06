"""
任务处理循环测试
"""

import os
import tempfile
import time
import unittest
from unittest.mock import Mock, patch, MagicMock
import numpy as np
from PIL import Image

from ..task_processor import TaskProcessor, TaskProcessorPool
from ..models import Task, TaskType, TaskStatus
from ..config import get_config


class TestTaskProcessor(unittest.TestCase):
    """任务处理器测试"""
    
    def setUp(self):
        self.processor = TaskProcessor(device="cpu")
        
        # 创建测试图像
        self.test_image = np.random.randint(0, 255, (256, 256, 3), dtype=np.uint8)
        self.test_mask = np.random.randint(0, 255, (256, 256), dtype=np.uint8)
        
        # 创建临时文件
        self.temp_dir = tempfile.mkdtemp()
        self.image_path = os.path.join(self.temp_dir, "test_image.jpg")
        self.mask_path = os.path.join(self.temp_dir, "test_mask.png")
        
        # 保存测试图像
        Image.fromarray(self.test_image).save(self.image_path)
        Image.fromarray(self.test_mask).save(self.mask_path)
    
    def tearDown(self):
        self.processor.cleanup()
        
        # 清理临时文件
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_processor_initialization(self):
        """测试处理器初始化"""
        self.assertEqual(self.processor.device, "cpu")
        self.assertIsNone(self.processor.model_manager)
        self.assertIsNone(self.processor.current_model)
        self.assertEqual(len(self.processor.progress_callbacks), 0)
    
    def test_load_image(self):
        """测试图像加载"""
        image = self.processor._load_image(self.image_path)
        
        self.assertIsInstance(image, np.ndarray)
        self.assertEqual(len(image.shape), 3)  # RGB 图像
        self.assertEqual(image.shape[2], 3)    # 3 个通道
    
    def test_load_image_not_found(self):
        """测试加载不存在的图像"""
        with self.assertRaises(FileNotFoundError):
            self.processor._load_image("nonexistent.jpg")
    
    def test_load_mask(self):
        """测试遮罩加载"""
        mask = self.processor._load_mask(self.mask_path)
        
        self.assertIsInstance(mask, np.ndarray)
        self.assertEqual(len(mask.shape), 2)  # 灰度图像
    
    def test_load_mask_not_found(self):
        """测试加载不存在的遮罩"""
        mask = self.processor._load_mask("nonexistent.png")
        self.assertIsNone(mask)
    
    def test_create_config(self):
        """测试配置创建"""
        config_dict = {
            'ldm_steps': 30,
            'prompt': 'test prompt',
            'sd_guidance_scale': 8.0
        }
        
        config = self.processor._create_config(config_dict)
        
        self.assertEqual(config.ldm_steps, 30)
        self.assertEqual(config.prompt, 'test prompt')
        self.assertEqual(config.sd_guidance_scale, 8.0)
    
    def test_save_result(self):
        """测试结果保存"""
        task_id = "test_task_001"
        result_image = self.test_image
        
        with patch('pathlib.Path.mkdir'):
            result_path = self.processor._save_result(task_id, result_image, "test")
        
        self.assertIsInstance(result_path, str)
        self.assertIn(task_id, result_path)
        self.assertIn("test_", result_path)
    
    def test_progress_callback(self):
        """测试进度回调"""
        task_id = "test_task_001"
        callback_called = False
        callback_data = None
        
        def test_callback(progress, message):
            nonlocal callback_called, callback_data
            callback_called = True
            callback_data = (progress, message)
        
        # 注册回调
        self.processor.register_progress_callback(task_id, test_callback)
        
        # 报告进度
        self.processor._report_progress(task_id, 0.5, "测试进度")
        
        # 验证回调被调用
        self.assertTrue(callback_called)
        self.assertEqual(callback_data[0], 0.5)
        self.assertEqual(callback_data[1], "测试进度")
        
        # 注销回调
        self.processor.unregister_progress_callback(task_id)
        self.assertNotIn(task_id, self.processor.progress_callbacks)
    
    @patch('lama_cleaner.distributed.task_processor.ModelManager')
    def test_ensure_model_loaded(self, mock_model_manager):
        """测试模型加载"""
        mock_manager = Mock()
        mock_model_manager.return_value = mock_manager
        
        # 首次加载模型
        self.processor._ensure_model_loaded('lama')
        
        self.assertIsNotNone(self.processor.model_manager)
        self.assertEqual(self.processor.current_model, 'lama')
        mock_model_manager.assert_called_once()
        
        # 切换到不同模型
        self.processor._ensure_model_loaded('sd15')
        
        mock_manager.switch.assert_called_once_with('sd15')
        self.assertEqual(self.processor.current_model, 'sd15')
    
    def test_get_supported_models(self):
        """测试获取支持的模型列表"""
        models = self.processor.get_supported_models()
        
        self.assertIsInstance(models, list)
        self.assertIn('lama', models)
        self.assertIn('cv2', models)
    
    @patch('lama_cleaner.distributed.task_processor.ModelManager')
    def test_process_inpaint_task(self, mock_model_manager):
        """测试图像修复任务处理"""
        # 模拟模型管理器
        mock_manager = Mock()
        mock_manager.return_value = self.test_image  # 模拟处理结果
        mock_model_manager.return_value = mock_manager
        
        # 创建测试任务
        task = Task()
        task.task_id = "inpaint_test_001"
        task.task_type = TaskType.INPAINT
        task.image_path = self.image_path
        task.mask_path = self.mask_path
        task.config = {'model': 'lama'}
        
        with patch.object(self.processor, '_save_result', return_value="/tmp/result.jpg"):
            result_path = self.processor._process_inpaint_task(task)
        
        self.assertEqual(result_path, "/tmp/result.jpg")
        mock_manager.assert_called_once()
    
    def test_process_plugin_task(self):
        """测试插件任务处理"""
        task = Task()
        task.task_id = "plugin_test_001"
        task.task_type = TaskType.PLUGIN
        task.image_path = self.image_path
        task.config = {'plugin': 'RemoveBG'}
        
        with patch.object(self.processor, '_run_remove_bg_plugin', return_value=self.test_image):
            with patch.object(self.processor, '_save_result', return_value="/tmp/plugin_result.jpg"):
                result_path = self.processor._process_plugin_task(task)
        
        self.assertEqual(result_path, "/tmp/plugin_result.jpg")
    
    def test_process_upscale_task(self):
        """测试图像放大任务处理"""
        task = Task()
        task.task_id = "upscale_test_001"
        task.task_type = TaskType.UPSCALE
        task.image_path = self.image_path
        task.config = {'scale': 2, 'method': 'RealESRGAN'}
        
        with patch.object(self.processor, '_run_upscale_plugin', return_value=self.test_image):
            with patch.object(self.processor, '_save_result', return_value="/tmp/upscale_result.jpg"):
                result_path = self.processor._process_upscale_task(task)
        
        self.assertEqual(result_path, "/tmp/upscale_result.jpg")
    
    def test_process_segment_task(self):
        """测试图像分割任务处理"""
        task = Task()
        task.task_id = "segment_test_001"
        task.task_type = TaskType.SEGMENT
        task.image_path = self.image_path
        task.config = {'method': 'SAM'}
        
        with patch.object(self.processor, '_run_sam_segmentation', return_value=self.test_image):
            with patch.object(self.processor, '_save_result', return_value="/tmp/segment_result.jpg"):
                result_path = self.processor._process_segment_task(task)
        
        self.assertEqual(result_path, "/tmp/segment_result.jpg")
    
    def test_process_task_complete_flow(self):
        """测试完整的任务处理流程"""
        task = Task()
        task.task_id = "complete_test_001"
        task.task_type = TaskType.INPAINT
        task.image_path = self.image_path
        task.mask_path = self.mask_path
        task.config = {'model': 'lama'}
        task.status = TaskStatus.PENDING
        
        with patch.object(self.processor, '_process_inpaint_task', return_value="/tmp/result.jpg"):
            processed_task = self.processor.process_task(task)
        
        self.assertEqual(processed_task.status, TaskStatus.COMPLETED)
        self.assertEqual(processed_task.result_path, "/tmp/result.jpg")
        self.assertIsNotNone(processed_task.processing_time)
        self.assertGreater(processed_task.processing_time, 0)
    
    def test_process_task_failure(self):
        """测试任务处理失败"""
        task = Task()
        task.task_id = "failure_test_001"
        task.task_type = TaskType.INPAINT
        task.image_path = "nonexistent.jpg"  # 不存在的文件
        task.config = {'model': 'lama'}
        task.status = TaskStatus.PENDING
        
        processed_task = self.processor.process_task(task)
        
        self.assertEqual(processed_task.status, TaskStatus.FAILED)
        self.assertIsNotNone(processed_task.error_message)
        self.assertIn("不存在", processed_task.error_message)
    
    def test_unsupported_task_type(self):
        """测试不支持的任务类型"""
        task = Task()
        task.task_id = "unsupported_test_001"
        task.task_type = "UNSUPPORTED"  # 不支持的类型
        task.status = TaskStatus.PENDING
        
        processed_task = self.processor.process_task(task)
        
        self.assertEqual(processed_task.status, TaskStatus.FAILED)
        self.assertIn("不支持的任务类型", processed_task.error_message)


class TestTaskProcessorPool(unittest.TestCase):
    """任务处理器池测试"""
    
    def setUp(self):
        self.pool = TaskProcessorPool(pool_size=3, device="cpu")
    
    def tearDown(self):
        self.pool.cleanup()
    
    def test_pool_initialization(self):
        """测试处理器池初始化"""
        self.assertEqual(self.pool.pool_size, 3)
        self.assertEqual(len(self.pool.processors), 3)
        self.assertEqual(len(self.pool.available_processors), 3)
        self.assertEqual(len(self.pool.busy_processors), 0)
    
    def test_get_processor(self):
        """测试获取处理器"""
        processor = self.pool.get_processor()
        
        self.assertIsNotNone(processor)
        self.assertIsInstance(processor, TaskProcessor)
        self.assertEqual(len(self.pool.available_processors), 2)
        self.assertEqual(len(self.pool.busy_processors), 1)
        self.assertIn(processor, self.pool.busy_processors)
    
    def test_return_processor(self):
        """测试归还处理器"""
        processor = self.pool.get_processor()
        self.pool.return_processor(processor)
        
        self.assertEqual(len(self.pool.available_processors), 3)
        self.assertEqual(len(self.pool.busy_processors), 0)
        self.assertIn(processor, self.pool.available_processors)
    
    def test_get_processor_when_empty(self):
        """测试处理器池为空时获取处理器"""
        # 获取所有处理器
        processors = []
        for _ in range(3):
            processor = self.pool.get_processor()
            processors.append(processor)
        
        # 再次获取应该返回 None
        processor = self.pool.get_processor()
        self.assertIsNone(processor)
        
        # 归还一个处理器
        self.pool.return_processor(processors[0])
        
        # 现在应该能获取到处理器
        processor = self.pool.get_processor()
        self.assertIsNotNone(processor)
    
    def test_pool_status(self):
        """测试处理器池状态"""
        status = self.pool.get_status()
        
        self.assertEqual(status['pool_size'], 3)
        self.assertEqual(status['available'], 3)
        self.assertEqual(status['busy'], 0)
        self.assertEqual(status['device'], 'cpu')
        
        # 获取一个处理器后检查状态
        processor = self.pool.get_processor()
        status = self.pool.get_status()
        
        self.assertEqual(status['available'], 2)
        self.assertEqual(status['busy'], 1)
    
    def test_pool_cleanup(self):
        """测试处理器池清理"""
        self.pool.cleanup()
        
        self.assertEqual(len(self.pool.processors), 0)
        self.assertEqual(len(self.pool.available_processors), 0)
        self.assertEqual(len(self.pool.busy_processors), 0)


class TestTaskProcessorPlugins(unittest.TestCase):
    """任务处理器插件测试"""
    
    def setUp(self):
        self.processor = TaskProcessor(device="cpu")
        self.test_image = np.random.randint(0, 255, (256, 256, 3), dtype=np.uint8)
    
    def tearDown(self):
        self.processor.cleanup()
    
    def test_simple_background_removal(self):
        """测试简单背景移除"""
        result = self.processor._simple_background_removal(self.test_image)
        
        self.assertIsInstance(result, np.ndarray)
        self.assertEqual(result.shape, self.test_image.shape)
    
    def test_simple_segmentation(self):
        """测试简单图像分割"""
        result = self.processor._simple_segmentation(self.test_image)
        
        self.assertIsInstance(result, np.ndarray)
        self.assertEqual(result.shape, self.test_image.shape)
    
    @patch('lama_cleaner.distributed.task_processor.cv2.resize')
    def test_upscale_fallback(self, mock_resize):
        """测试图像放大后备方法"""
        mock_resize.return_value = self.test_image
        
        config = {'scale': 2}
        result = self.processor._run_upscale_plugin(self.test_image, config)
        
        mock_resize.assert_called_once()
        self.assertEqual(result, self.test_image)
    
    def test_face_restore_fallback(self):
        """测试人脸修复后备方法"""
        config = {}
        result = self.processor._run_face_restore_plugin(self.test_image, config)
        
        # 后备方法应该返回原图
        np.testing.assert_array_equal(result, self.test_image)
    
    def test_remove_bg_fallback(self):
        """测试背景移除后备方法"""
        config = {}
        result = self.processor._run_remove_bg_plugin(self.test_image, config)
        
        self.assertIsInstance(result, np.ndarray)
        self.assertEqual(result.shape, self.test_image.shape)


class TestTaskProcessorIntegration(unittest.TestCase):
    """任务处理器集成测试"""
    
    def setUp(self):
        self.processor = TaskProcessor(device="cpu")
        
        # 创建测试图像文件
        self.temp_dir = tempfile.mkdtemp()
        self.image_path = os.path.join(self.temp_dir, "test.jpg")
        
        test_image = np.random.randint(0, 255, (256, 256, 3), dtype=np.uint8)
        Image.fromarray(test_image).save(self.image_path)
    
    def tearDown(self):
        self.processor.cleanup()
        
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_end_to_end_processing(self):
        """测试端到端任务处理"""
        task = Task()
        task.task_id = "e2e_test_001"
        task.task_type = TaskType.UPSCALE  # 使用简单的放大任务
        task.image_path = self.image_path
        task.config = {'scale': 2, 'method': 'bilinear'}
        task.status = TaskStatus.PENDING
        
        with patch.object(self.processor, '_save_result', return_value="/tmp/result.jpg"):
            processed_task = self.processor.process_task(task)
        
        self.assertEqual(processed_task.status, TaskStatus.COMPLETED)
        self.assertIsNotNone(processed_task.result_path)
        self.assertIsNotNone(processed_task.processing_time)
    
    def test_concurrent_processing(self):
        """测试并发处理"""
        import threading
        import concurrent.futures
        
        def process_task(task_id):
            task = Task()
            task.task_id = f"concurrent_test_{task_id}"
            task.task_type = TaskType.SEGMENT
            task.image_path = self.image_path
            task.config = {'method': 'simple'}
            
            with patch.object(self.processor, '_save_result', return_value=f"/tmp/result_{task_id}.jpg"):
                return self.processor.process_task(task)
        
        # 并发处理多个任务
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
            futures = [executor.submit(process_task, i) for i in range(5)]
            results = [f.result() for f in concurrent.futures.as_completed(futures)]
        
        # 验证所有任务都处理成功
        self.assertEqual(len(results), 5)
        for result in results:
            self.assertEqual(result.status, TaskStatus.COMPLETED)
    
    def test_memory_usage(self):
        """测试内存使用情况"""
        import psutil
        import gc
        
        process = psutil.Process()
        initial_memory = process.memory_info().rss
        
        # 处理多个任务
        for i in range(10):
            task = Task()
            task.task_id = f"memory_test_{i}"
            task.task_type = TaskType.SEGMENT
            task.image_path = self.image_path
            task.config = {'method': 'simple'}
            
            with patch.object(self.processor, '_save_result', return_value=f"/tmp/result_{i}.jpg"):
                self.processor.process_task(task)
        
        # 强制垃圾回收
        gc.collect()
        
        final_memory = process.memory_info().rss
        memory_increase = final_memory - initial_memory
        
        # 内存增长应该在合理范围内（小于100MB）
        self.assertLess(memory_increase, 100 * 1024 * 1024, 
                       f"Memory increased by {memory_increase / 1024 / 1024:.1f}MB")


class TestTaskProcessorErrorHandling(unittest.TestCase):
    """任务处理器错误处理测试"""
    
    def setUp(self):
        self.processor = TaskProcessor(device="cpu")
    
    def tearDown(self):
        self.processor.cleanup()
    
    def test_invalid_image_path(self):
        """测试无效图像路径"""
        task = Task()
        task.task_id = "invalid_path_test"
        task.task_type = TaskType.INPAINT
        task.image_path = "/nonexistent/path.jpg"
        task.config = {'model': 'lama'}
        
        processed_task = self.processor.process_task(task)
        
        self.assertEqual(processed_task.status, TaskStatus.FAILED)
        self.assertIn("不存在", processed_task.error_message)
    
    def test_corrupted_image(self):
        """测试损坏的图像文件"""
        # 创建损坏的图像文件
        temp_dir = tempfile.mkdtemp()
        corrupted_path = os.path.join(temp_dir, "corrupted.jpg")
        
        with open(corrupted_path, 'wb') as f:
            f.write(b"not an image file")
        
        try:
            task = Task()
            task.task_id = "corrupted_image_test"
            task.task_type = TaskType.INPAINT
            task.image_path = corrupted_path
            task.config = {'model': 'lama'}
            
            processed_task = self.processor.process_task(task)
            
            self.assertEqual(processed_task.status, TaskStatus.FAILED)
            self.assertIsNotNone(processed_task.error_message)
            
        finally:
            import shutil
            shutil.rmtree(temp_dir, ignore_errors=True)
    
    def test_model_loading_failure(self):
        """测试模型加载失败"""
        with patch.object(self.processor, '_ensure_model_loaded', 
                         side_effect=RuntimeError("Model loading failed")):
            task = Task()
            task.task_id = "model_failure_test"
            task.task_type = TaskType.INPAINT
            task.image_path = "/tmp/test.jpg"
            task.config = {'model': 'lama'}
            
            processed_task = self.processor.process_task(task)
            
            self.assertEqual(processed_task.status, TaskStatus.FAILED)
            self.assertIn("Model loading failed", processed_task.error_message)
    
    def test_save_result_failure(self):
        """测试结果保存失败"""
        temp_dir = tempfile.mkdtemp()
        image_path = os.path.join(temp_dir, "test.jpg")
        
        # 创建测试图像
        test_image = np.random.randint(0, 255, (256, 256, 3), dtype=np.uint8)
        Image.fromarray(test_image).save(image_path)
        
        try:
            with patch.object(self.processor, '_save_result', 
                             side_effect=RuntimeError("Save failed")):
                task = Task()
                task.task_id = "save_failure_test"
                task.task_type = TaskType.SEGMENT
                task.image_path = image_path
                task.config = {'method': 'simple'}
                
                processed_task = self.processor.process_task(task)
                
                self.assertEqual(processed_task.status, TaskStatus.FAILED)
                self.assertIn("Save failed", processed_task.error_message)
                
        finally:
            import shutil
            shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == '__main__':
    unittest.main()