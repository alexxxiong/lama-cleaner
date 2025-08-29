"""
队列管理系统集成测试

测试整个队列管理系统的端到端功能，包括队列初始化、任务路由、发送和监控。
"""

import pytest
import time
from unittest.mock import Mock, patch
from datetime import datetime

from lama_cleaner.distributed.queue_manager import QueueManager
from lama_cleaner.distributed.models import Task, TaskType, TaskPriority
from lama_cleaner.distributed.config import DistributedConfig


class TestQueueSystemIntegration:
    """队列系统集成测试"""
    
    @pytest.fixture
    def queue_manager(self):
        """创建完整的队列管理器"""
        config = DistributedConfig()
        with patch('lama_cleaner.distributed.queue_manager.get_config', return_value=config):
            manager = QueueManager()
            yield manager
            if hasattr(manager, '_running') and manager._running:
                manager.stop()
    
    def test_complete_task_workflow(self, queue_manager):
        """测试完整的任务工作流程"""
        # 模拟 ZMQ socket
        mock_socket = Mock()
        
        with patch.object(queue_manager.context, 'socket', return_value=mock_socket):
            # 1. 启动队列管理器
            queue_manager.start()
            
            # 验证队列已创建
            assert len(queue_manager.queues) > 0
            assert len(queue_manager.queue_stats) > 0
            
            # 2. 创建不同类型的任务
            tasks = [
                Task(
                    task_id="gpu-task-1",
                    task_type=TaskType.INPAINT,
                    priority=TaskPriority.HIGH,
                    config={"model": "sdxl", "device": "cuda"}
                ),
                Task(
                    task_id="gpu-task-2", 
                    task_type=TaskType.INPAINT,
                    priority=TaskPriority.NORMAL,
                    config={"model": "lama", "device": "cuda"}
                ),
                Task(
                    task_id="cpu-task-1",
                    task_type=TaskType.INPAINT,
                    priority=TaskPriority.LOW,
                    config={"model": "lama", "device": "cpu"}
                ),
                Task(
                    task_id="plugin-task-1",
                    task_type=TaskType.PLUGIN,
                    priority=TaskPriority.NORMAL,
                    config={"name": "realesrgan"}
                )
            ]
            
            # 3. 路由和发送任务
            sent_tasks = []
            for task in tasks:
                # 路由任务
                selected_queue = queue_manager.route_task(task)
                assert selected_queue is not None, f"No queue found for task {task.task_id}"
                
                # 发送任务
                result = queue_manager.send_task(selected_queue, task)
                assert result is True, f"Failed to send task {task.task_id}"
                
                sent_tasks.append((task, selected_queue))
            
            # 4. 验证统计信息更新
            total_sent = 0
            for queue_name in queue_manager.config.queues.keys():
                stats = queue_manager.get_queue_stats(queue_name)
                total_sent += stats.get('total_sent', 0)
            
            assert total_sent == len(tasks), f"Expected {len(tasks)} tasks sent, got {total_sent}"
            
            # 5. 验证任务被正确路由
            gpu_tasks = [t for t, q in sent_tasks if 'gpu' in q]
            cpu_tasks = [t for t, q in sent_tasks if 'cpu' in q]
            
            # GPU 任务应该路由到 GPU 队列
            assert len(gpu_tasks) == 3  # sdxl, lama-gpu, realesrgan
            # CPU 任务应该路由到 CPU 队列
            assert len(cpu_tasks) == 1   # lama-cpu
            
            # 6. 验证优先级任务处理
            high_priority_tasks = [t for t, q in sent_tasks if t.priority == TaskPriority.HIGH]
            assert len(high_priority_tasks) == 1
            
            # 7. 停止队列管理器
            queue_manager.stop()
            
            # 验证清理
            assert queue_manager._running is False
    
    def test_load_balancing_across_queues(self, queue_manager):
        """测试跨队列负载均衡"""
        # 添加多个相同类型的队列用于负载均衡测试
        from lama_cleaner.distributed.models import QueueConfig
        
        queue_manager.config.queues.update({
            "gpu-high-2": QueueConfig(
                name="gpu-high-2",
                port=5565,
                requirements={
                    "gpu": True,
                    "gpu_memory": 8192,
                    "models": ["sd15", "sd21", "sdxl", "lama"]
                }
            ),
            "gpu-high-3": QueueConfig(
                name="gpu-high-3",
                port=5566,
                requirements={
                    "gpu": True,
                    "gpu_memory": 8192,
                    "models": ["sd15", "sd21", "sdxl", "lama"]
                }
            )
        })
        
        # 模拟 socket
        mock_socket = Mock()
        
        with patch.object(queue_manager.context, 'socket', return_value=mock_socket):
            queue_manager._setup_queues()
            
            # 设置不同的队列负载
            queue_manager.queue_stats.update({
                "gpu-high": {"pending_count": 10},
                "gpu-high-2": {"pending_count": 3},
                "gpu-high-3": {"pending_count": 7}
            })
            
            # 创建需要高端 GPU 的任务
            task = Task(
                task_type=TaskType.INPAINT,
                config={"model": "sdxl", "device": "cuda"}
            )
            
            # 路由任务
            selected_queue = queue_manager.route_task(task)
            
            # 应该选择负载最轻的队列
            assert selected_queue == "gpu-high-2"
    
    def test_queue_capacity_management(self, queue_manager):
        """测试队列容量管理"""
        # 设置小容量队列用于测试
        from lama_cleaner.distributed.models import QueueConfig
        
        queue_manager.config.queues = {
            "small-queue": QueueConfig(
                name="small-queue",
                port=5567,
                requirements={
                    "gpu": True,
                    "gpu_memory": 4096,
                    "models": ["lama"]
                },
                max_size=2  # 小容量
            )
        }
        
        mock_socket = Mock()
        
        with patch.object(queue_manager.context, 'socket', return_value=mock_socket):
            queue_manager._setup_queues()
            
            # 创建任务
            tasks = [
                Task(task_id=f"task-{i}", task_type=TaskType.INPAINT, 
                     config={"model": "lama", "device": "cuda"})
                for i in range(5)
            ]
            
            # 发送任务直到容量满
            successful_sends = 0
            failed_sends = 0
            
            for task in tasks:
                result = queue_manager.send_task("small-queue", task)
                if result:
                    successful_sends += 1
                else:
                    failed_sends += 1
            
            # 验证容量限制
            assert successful_sends == 2  # 队列容量
            assert failed_sends == 3      # 超出容量的任务
            
            # 验证统计信息
            stats = queue_manager.get_queue_stats("small-queue")
            assert stats["pending_count"] == 2
            assert stats["total_sent"] == 2
    
    def test_error_recovery_and_monitoring(self, queue_manager):
        """测试错误恢复和监控"""
        mock_socket = Mock()
        
        with patch.object(queue_manager.context, 'socket', return_value=mock_socket):
            # 启动队列管理器
            queue_manager.start()
            
            # 模拟发送错误
            mock_socket.send_multipart.side_effect = Exception("Network error")
            
            # 尝试发送任务
            task = Task(
                task_type=TaskType.INPAINT,
                config={"model": "lama", "device": "cuda"}
            )
            
            selected_queue = queue_manager.route_task(task)
            result = queue_manager.send_task(selected_queue, task)
            
            # 验证错误处理
            assert result is False
            
            # 验证统计信息没有错误更新
            stats = queue_manager.get_queue_stats(selected_queue)
            assert stats["total_sent"] == 0
            assert stats["pending_count"] == 0
            
            # 恢复正常功能
            mock_socket.send_multipart.side_effect = None
            
            # 再次尝试发送
            result = queue_manager.send_task(selected_queue, task)
            assert result is True
            
            # 验证统计信息正确更新
            stats = queue_manager.get_queue_stats(selected_queue)
            assert stats["total_sent"] == 1
            assert stats["pending_count"] == 1
            
            queue_manager.stop()
    
    def test_concurrent_operations(self, queue_manager):
        """测试并发操作"""
        import threading
        
        mock_socket = Mock()
        
        with patch.object(queue_manager.context, 'socket', return_value=mock_socket):
            queue_manager._setup_queues()
            
            # 并发发送任务
            def send_tasks(start_id, count):
                for i in range(count):
                    task = Task(
                        task_id=f"concurrent-task-{start_id}-{i}",
                        task_type=TaskType.INPAINT,
                        config={"model": "lama", "device": "cuda"}
                    )
                    
                    selected_queue = queue_manager.route_task(task)
                    if selected_queue:
                        queue_manager.send_task(selected_queue, task)
            
            # 启动多个线程
            threads = []
            for i in range(3):
                thread = threading.Thread(target=send_tasks, args=(i, 10))
                threads.append(thread)
                thread.start()
            
            # 等待所有线程完成
            for thread in threads:
                thread.join()
            
            # 验证所有任务都被处理
            total_sent = 0
            for queue_name in queue_manager.config.queues.keys():
                stats = queue_manager.get_queue_stats(queue_name)
                total_sent += stats.get('total_sent', 0)
            
            assert total_sent == 30  # 3 threads * 10 tasks each
    
    def test_system_metrics_collection(self, queue_manager):
        """测试系统指标收集"""
        mock_socket = Mock()
        
        with patch.object(queue_manager.context, 'socket', return_value=mock_socket):
            queue_manager._setup_queues()
            
            # 模拟一些活动
            tasks = [
                Task(task_type=TaskType.INPAINT, config={"model": "lama", "device": "cuda"}),
                Task(task_type=TaskType.INPAINT, config={"model": "opencv", "device": "cpu"}),
                Task(task_type=TaskType.PLUGIN, config={"name": "realesrgan"})
            ]
            
            for task in tasks:
                selected_queue = queue_manager.route_task(task)
                if selected_queue:
                    queue_manager.send_task(selected_queue, task)
            
            # 模拟任务完成
            for queue_name in queue_manager.config.queues.keys():
                if queue_manager.queue_stats[queue_name].get('total_sent', 0) > 0:
                    queue_manager.update_queue_stats(queue_name, "pending_count", -1)
                    queue_manager.update_queue_stats(queue_name, "processing_count", 1)
                    queue_manager.update_queue_stats(queue_name, "processing_count", -1)
                    queue_manager.update_queue_stats(queue_name, "completed_count", 1)
            
            # 收集系统指标
            all_stats = queue_manager.get_queue_stats()
            
            # 计算总体指标
            total_completed = sum(stats.get('completed_count', 0) for stats in all_stats.values())
            total_pending = sum(stats.get('pending_count', 0) for stats in all_stats.values())
            total_processing = sum(stats.get('processing_count', 0) for stats in all_stats.values())
            
            # 验证指标
            assert total_completed > 0
            assert total_pending >= 0
            assert total_processing == 0  # 所有任务都已完成
            
            # 验证每个队列都有时间戳
            for stats in all_stats.values():
                assert 'last_updated' in stats
                assert isinstance(stats['last_updated'], datetime)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])