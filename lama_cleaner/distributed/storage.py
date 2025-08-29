"""
任务持久化存储接口

提供任务数据的持久化存储，支持 SQLite、PostgreSQL 等数据库。
实现任务的 CRUD 操作和状态管理。
"""

import sqlite3
import json
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
from pathlib import Path
import threading
from contextlib import contextmanager
from abc import ABC, abstractmethod

from .models import Task, TaskStatus, TaskType, TaskPriority
from .config import get_config

logger = logging.getLogger(__name__)


class TaskStorage(ABC):
    """任务存储抽象基类"""
    
    @abstractmethod
    def save_task(self, task: Task) -> bool:
        """保存任务"""
        pass
    
    @abstractmethod
    def get_task(self, task_id: str) -> Optional[Task]:
        """获取任务"""
        pass
    
    @abstractmethod
    def update_task(self, task: Task) -> bool:
        """更新任务"""
        pass
    
    @abstractmethod
    def delete_task(self, task_id: str) -> bool:
        """删除任务"""
        pass
    
    @abstractmethod
    def get_tasks_by_status(self, status: TaskStatus, limit: Optional[int] = None) -> List[Task]:
        """根据状态获取任务列表"""
        pass
    
    @abstractmethod
    def get_tasks_by_node(self, node_id: str) -> List[Task]:
        """获取指定节点的任务"""
        pass
    
    @abstractmethod
    def get_pending_tasks(self, limit: Optional[int] = None) -> List[Task]:
        """获取待处理任务"""
        pass
    
    @abstractmethod
    def cleanup_old_tasks(self, older_than: datetime) -> int:
        """清理旧任务"""
        pass
    
    @abstractmethod
    def get_task_statistics(self) -> Dict[str, int]:
        """获取任务统计信息"""
        pass


class SQLiteTaskStorage(TaskStorage):
    """SQLite 任务存储实现"""
    
    def __init__(self, db_path: str = None):
        self.config = get_config()
        self.db_path = db_path or self.config.database.sqlite_path
        self.lock = threading.RLock()
        
        # 确保数据库目录存在
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        
        # 初始化数据库
        self._init_database()
        
        logger.info(f"SQLite 任务存储已初始化: {self.db_path}")
    
    def _init_database(self):
        """初始化数据库表"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # 创建任务表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS tasks (
                    task_id TEXT PRIMARY KEY,
                    task_type TEXT NOT NULL,
                    status TEXT NOT NULL,
                    priority INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    image_path TEXT,
                    mask_path TEXT,
                    config TEXT,
                    assigned_node TEXT,
                    queue_name TEXT,
                    retry_count INTEGER DEFAULT 0,
                    max_retries INTEGER DEFAULT 3,
                    result_path TEXT,
                    error_message TEXT,
                    processing_time REAL,
                    user_id TEXT,
                    session_id TEXT,
                    metadata TEXT
                )
            ''')
            
            # 创建索引
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_tasks_created_at ON tasks(created_at)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_tasks_assigned_node ON tasks(assigned_node)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_tasks_user_id ON tasks(user_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_tasks_session_id ON tasks(session_id)')
            
            conn.commit()
    
    @contextmanager
    def _get_connection(self):
        """获取数据库连接"""
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        conn.row_factory = sqlite3.Row  # 使用字典式访问
        try:
            yield conn
        finally:
            conn.close()
    
    def save_task(self, task: Task) -> bool:
        """保存任务"""
        try:
            with self.lock:
                with self._get_connection() as conn:
                    cursor = conn.cursor()
                    
                    cursor.execute('''
                        INSERT OR REPLACE INTO tasks (
                            task_id, task_type, status, priority, created_at, updated_at,
                            image_path, mask_path, config, assigned_node, queue_name,
                            retry_count, max_retries, result_path, error_message,
                            processing_time, user_id, session_id, metadata
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (
                        task.task_id,
                        task.task_type.value,
                        task.status.value,
                        task.priority.value,
                        task.created_at.isoformat(),
                        task.updated_at.isoformat(),
                        task.image_path,
                        task.mask_path,
                        json.dumps(task.config, ensure_ascii=False),
                        task.assigned_node,
                        task.queue_name,
                        task.retry_count,
                        task.max_retries,
                        task.result_path,
                        task.error_message,
                        task.processing_time,
                        task.user_id,
                        task.session_id,
                        json.dumps(task.metadata, ensure_ascii=False)
                    ))
                    
                    conn.commit()
                    return True
                    
        except Exception as e:
            logger.error(f"保存任务失败 {task.task_id}: {e}")
            return False
    
    def get_task(self, task_id: str) -> Optional[Task]:
        """获取任务"""
        try:
            with self.lock:
                with self._get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute('SELECT * FROM tasks WHERE task_id = ?', (task_id,))
                    row = cursor.fetchone()
                    
                    if row:
                        return self._row_to_task(row)
                    return None
                    
        except Exception as e:
            logger.error(f"获取任务失败 {task_id}: {e}")
            return None
    
    def update_task(self, task: Task) -> bool:
        """更新任务"""
        return self.save_task(task)  # SQLite 使用 INSERT OR REPLACE
    
    def delete_task(self, task_id: str) -> bool:
        """删除任务"""
        try:
            with self.lock:
                with self._get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute('DELETE FROM tasks WHERE task_id = ?', (task_id,))
                    conn.commit()
                    return cursor.rowcount > 0
                    
        except Exception as e:
            logger.error(f"删除任务失败 {task_id}: {e}")
            return False
    
    def get_tasks_by_status(self, status: TaskStatus, limit: Optional[int] = None) -> List[Task]:
        """根据状态获取任务列表"""
        try:
            with self.lock:
                with self._get_connection() as conn:
                    cursor = conn.cursor()
                    
                    query = 'SELECT * FROM tasks WHERE status = ? ORDER BY created_at DESC'
                    params = [status.value]
                    
                    if limit:
                        query += ' LIMIT ?'
                        params.append(limit)
                    
                    cursor.execute(query, params)
                    rows = cursor.fetchall()
                    
                    return [self._row_to_task(row) for row in rows]
                    
        except Exception as e:
            logger.error(f"根据状态获取任务失败 {status.value}: {e}")
            return []
    
    def get_tasks_by_node(self, node_id: str) -> List[Task]:
        """获取指定节点的任务"""
        try:
            with self.lock:
                with self._get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute(
                        'SELECT * FROM tasks WHERE assigned_node = ? ORDER BY created_at DESC',
                        (node_id,)
                    )
                    rows = cursor.fetchall()
                    
                    return [self._row_to_task(row) for row in rows]
                    
        except Exception as e:
            logger.error(f"获取节点任务失败 {node_id}: {e}")
            return []
    
    def get_pending_tasks(self, limit: Optional[int] = None) -> List[Task]:
        """获取待处理任务"""
        try:
            with self.lock:
                with self._get_connection() as conn:
                    cursor = conn.cursor()
                    
                    # 按优先级降序，创建时间升序排序
                    query = '''
                        SELECT * FROM tasks 
                        WHERE status = ? 
                        ORDER BY priority DESC, created_at ASC
                    '''
                    params = [TaskStatus.PENDING.value]
                    
                    if limit:
                        query += ' LIMIT ?'
                        params.append(limit)
                    
                    cursor.execute(query, params)
                    rows = cursor.fetchall()
                    
                    return [self._row_to_task(row) for row in rows]
                    
        except Exception as e:
            logger.error(f"获取待处理任务失败: {e}")
            return []
    
    def cleanup_old_tasks(self, older_than: datetime) -> int:
        """清理旧任务"""
        try:
            with self.lock:
                with self._get_connection() as conn:
                    cursor = conn.cursor()
                    
                    # 删除已完成、失败或取消的旧任务
                    cursor.execute('''
                        DELETE FROM tasks 
                        WHERE status IN (?, ?, ?) 
                        AND updated_at < ?
                    ''', (
                        TaskStatus.COMPLETED.value,
                        TaskStatus.FAILED.value,
                        TaskStatus.CANCELLED.value,
                        older_than.isoformat()
                    ))
                    
                    conn.commit()
                    return cursor.rowcount
                    
        except Exception as e:
            logger.error(f"清理旧任务失败: {e}")
            return 0
    
    def get_task_statistics(self) -> Dict[str, int]:
        """获取任务统计信息"""
        try:
            with self.lock:
                with self._get_connection() as conn:
                    cursor = conn.cursor()
                    
                    # 获取各状态的任务数量
                    cursor.execute('''
                        SELECT status, COUNT(*) as count 
                        FROM tasks 
                        GROUP BY status
                    ''')
                    
                    stats = {}
                    total = 0
                    
                    for row in cursor.fetchall():
                        status = row['status']
                        count = row['count']
                        stats[status] = count
                        total += count
                    
                    # 确保所有状态都有值
                    for status in TaskStatus:
                        if status.value not in stats:
                            stats[status.value] = 0
                    
                    stats['total'] = total
                    return stats
                    
        except Exception as e:
            logger.error(f"获取任务统计失败: {e}")
            return {}
    
    def get_tasks_by_user(self, user_id: str, limit: Optional[int] = None) -> List[Task]:
        """获取用户的任务"""
        try:
            with self.lock:
                with self._get_connection() as conn:
                    cursor = conn.cursor()
                    
                    query = 'SELECT * FROM tasks WHERE user_id = ? ORDER BY created_at DESC'
                    params = [user_id]
                    
                    if limit:
                        query += ' LIMIT ?'
                        params.append(limit)
                    
                    cursor.execute(query, params)
                    rows = cursor.fetchall()
                    
                    return [self._row_to_task(row) for row in rows]
                    
        except Exception as e:
            logger.error(f"获取用户任务失败 {user_id}: {e}")
            return []
    
    def get_tasks_by_session(self, session_id: str) -> List[Task]:
        """获取会话的任务"""
        try:
            with self.lock:
                with self._get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute(
                        'SELECT * FROM tasks WHERE session_id = ? ORDER BY created_at DESC',
                        (session_id,)
                    )
                    rows = cursor.fetchall()
                    
                    return [self._row_to_task(row) for row in rows]
                    
        except Exception as e:
            logger.error(f"获取会话任务失败 {session_id}: {e}")
            return []
    
    def _row_to_task(self, row) -> Task:
        """将数据库行转换为任务对象"""
        task = Task()
        task.task_id = row['task_id']
        task.task_type = TaskType(row['task_type'])
        task.status = TaskStatus(row['status'])
        task.priority = TaskPriority(row['priority'])
        task.created_at = datetime.fromisoformat(row['created_at'])
        task.updated_at = datetime.fromisoformat(row['updated_at'])
        task.image_path = row['image_path']
        task.mask_path = row['mask_path']
        task.config = json.loads(row['config']) if row['config'] else {}
        task.assigned_node = row['assigned_node']
        task.queue_name = row['queue_name']
        task.retry_count = row['retry_count'] or 0
        task.max_retries = row['max_retries'] or 3
        task.result_path = row['result_path']
        task.error_message = row['error_message']
        task.processing_time = row['processing_time']
        task.user_id = row['user_id']
        task.session_id = row['session_id']
        task.metadata = json.loads(row['metadata']) if row['metadata'] else {}
        
        return task


class TaskStorageManager:
    """任务存储管理器"""
    
    def __init__(self):
        self.config = get_config()
        self._storage: Optional[TaskStorage] = None
    
    def get_storage(self) -> TaskStorage:
        """获取存储实例"""
        if self._storage is None:
            if self.config.database.type == "sqlite":
                self._storage = SQLiteTaskStorage(self.config.database.sqlite_path)
            else:
                # 未来可以扩展支持其他数据库
                raise NotImplementedError(f"不支持的数据库类型: {self.config.database.type}")
        
        return self._storage
    
    def close(self):
        """关闭存储连接"""
        # SQLite 不需要显式关闭，连接在上下文管理器中自动关闭
        pass


# 全局存储管理器实例
storage_manager = TaskStorageManager()


def get_task_storage() -> TaskStorage:
    """获取任务存储实例"""
    return storage_manager.get_storage()