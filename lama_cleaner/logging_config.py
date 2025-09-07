"""
统一日志配置管理系统

提供分层配置管理，支持彩色控制台输出和结构化日志记录。
包含高级文件轮转、压缩和自动清理功能。
"""

import sys
import os
import gzip
import shutil
from loguru import logger
from typing import Dict, Any, Optional, List
from pathlib import Path
import json
from datetime import datetime, timedelta
from dataclasses import dataclass, field
import threading
import time
import sqlite3
from typing import Union
import uuid
from lama_cleaner.performance_monitor import performance_monitor, track_performance
from lama_cleaner.error_tracker import error_tracker, ErrorContext, ErrorCategory, ErrorSeverity
from lama_cleaner.privacy_protector import privacy_protector, PrivacyConfig, protect_message, protect_data


@dataclass
class FileRotationConfig:
    """文件轮转配置"""
    max_size: str = "100 MB"  # 最大文件大小
    rotation_time: str = "1 day"  # 轮转时间间隔
    retention_days: int = 30  # 保留天数
    retention_count: int = 10  # 保留文件数量
    compression: str = "gz"  # 压缩格式
    backup_count: int = 5  # 备份文件数量
    
@dataclass 
class LoggingConfig:
    """完整的日志配置"""
    level: str = "INFO"
    console_enabled: bool = True
    file_enabled: bool = True
    structured_logging: bool = True
    log_directory: str = "logs"
    filename_pattern: str = "lama_cleaner_{time:YYYY-MM-DD}.log"
    rotation: FileRotationConfig = field(default_factory=FileRotationConfig)


class LogFileManager:
    """日志文件管理器 - 处理轮转、压缩和清理"""
    
    def __init__(self, log_dir: Path, config: FileRotationConfig):
        self.log_dir = log_dir
        self.config = config
        self.cleanup_thread = None
        self.stop_cleanup = threading.Event()
        
    def start_cleanup_scheduler(self):
        """启动定期清理调度器"""
        if self.cleanup_thread is None or not self.cleanup_thread.is_alive():
            self.stop_cleanup.clear()
            self.cleanup_thread = threading.Thread(target=self._cleanup_worker, daemon=True)
            self.cleanup_thread.start()
            
    def stop_cleanup_scheduler(self):
        """停止清理调度器"""
        if self.cleanup_thread and self.cleanup_thread.is_alive():
            self.stop_cleanup.set()
            self.cleanup_thread.join(timeout=5)
            
    def _cleanup_worker(self):
        """清理工作线程"""
        while not self.stop_cleanup.wait(3600):  # 每小时检查一次
            try:
                self.cleanup_old_logs()
                self.compress_old_logs()
            except Exception as e:
                logger.error(f"日志清理过程中发生错误: {e}")
                
    def cleanup_old_logs(self):
        """清理过期的日志文件"""
        if not self.log_dir.exists():
            return
            
        cutoff_date = datetime.now() - timedelta(days=self.config.retention_days)
        
        # 获取所有日志文件
        log_files = []
        for pattern in ["*.log", "*.log.gz", "*.log.bz2"]:
            log_files.extend(self.log_dir.glob(pattern))
            
        # 按修改时间排序
        log_files.sort(key=lambda f: f.stat().st_mtime, reverse=True)
        
        deleted_count = 0
        
        # 删除过期文件
        for log_file in log_files:
            file_time = datetime.fromtimestamp(log_file.stat().st_mtime)
            if file_time < cutoff_date:
                try:
                    log_file.unlink()
                    deleted_count += 1
                    logger.debug(f"删除过期日志文件: {log_file.name}")
                except Exception as e:
                    logger.warning(f"无法删除日志文件 {log_file.name}: {e}")
                    
        # 保持文件数量限制
        if len(log_files) > self.config.retention_count:
            files_to_delete = log_files[self.config.retention_count:]
            for log_file in files_to_delete:
                try:
                    if log_file.exists():
                        log_file.unlink()
                        deleted_count += 1
                        logger.debug(f"删除多余日志文件: {log_file.name}")
                except Exception as e:
                    logger.warning(f"无法删除日志文件 {log_file.name}: {e}")
                    
        if deleted_count > 0:
            logger.info(f"日志清理完成，删除了 {deleted_count} 个文件")
            
    def compress_old_logs(self):
        """压缩旧的日志文件"""
        if not self.log_dir.exists() or self.config.compression == "none":
            return
            
        # 查找未压缩的日志文件（排除当前日志文件）
        log_files = list(self.log_dir.glob("*.log"))
        current_date = datetime.now().strftime("%Y-%m-%d")
        
        compressed_count = 0
        
        for log_file in log_files:
            # 跳过当前日期的日志文件
            if current_date in log_file.name:
                continue
                
            # 检查文件是否已经压缩
            compressed_file = log_file.with_suffix(f".log.{self.config.compression}")
            if compressed_file.exists():
                continue
                
            try:
                if self.config.compression == "gz":
                    self._compress_gzip(log_file, compressed_file)
                elif self.config.compression == "bz2":
                    self._compress_bzip2(log_file, compressed_file)
                    
                # 删除原文件
                log_file.unlink()
                compressed_count += 1
                logger.debug(f"压缩日志文件: {log_file.name} -> {compressed_file.name}")
                
            except Exception as e:
                logger.warning(f"压缩日志文件失败 {log_file.name}: {e}")
                
        if compressed_count > 0:
            logger.info(f"日志压缩完成，压缩了 {compressed_count} 个文件")
            
    def _compress_gzip(self, source: Path, target: Path):
        """使用gzip压缩文件"""
        with open(source, 'rb') as f_in:
            with gzip.open(target, 'wb') as f_out:
                shutil.copyfileobj(f_in, f_out)
                
    def _compress_bzip2(self, source: Path, target: Path):
        """使用bzip2压缩文件"""
        import bz2
        with open(source, 'rb') as f_in:
            with bz2.open(target, 'wb') as f_out:
                shutil.copyfileobj(f_in, f_out)
                
    def get_log_files_info(self) -> List[Dict[str, Any]]:
        """获取日志文件信息"""
        if not self.log_dir.exists():
            return []
            
        files_info = []
        for log_file in self.log_dir.iterdir():
            if log_file.is_file() and any(log_file.name.endswith(ext) for ext in ['.log', '.log.gz', '.log.bz2']):
                stat = log_file.stat()
                files_info.append({
                    'name': log_file.name,
                    'size': stat.st_size,
                    'size_mb': round(stat.st_size / (1024 * 1024), 2),
                    'modified': datetime.fromtimestamp(stat.st_mtime),
                    'compressed': log_file.suffix in ['.gz', '.bz2']
                })
                
        return sorted(files_info, key=lambda x: x['modified'], reverse=True)


class StructuredLogStorage:
    """结构化日志存储系统"""
    
    def __init__(self, db_path: str = "logs/structured_logs.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(exist_ok=True, parents=True)
        self._init_database()
        
    def _init_database(self):
        """初始化数据库表结构"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS log_entries (
                    id TEXT PRIMARY KEY,
                    timestamp DATETIME,
                    level TEXT,
                    module TEXT,
                    function TEXT,
                    line INTEGER,
                    message TEXT,
                    extra_data TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # 创建索引以提高查询性能
            conn.execute("CREATE INDEX IF NOT EXISTS idx_timestamp ON log_entries(timestamp)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_level ON log_entries(level)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_module ON log_entries(module)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_created_at ON log_entries(created_at)")
            
    def store_log_entry(self, record: Dict[str, Any]) -> str:
        """存储日志条目"""
        entry_id = str(uuid.uuid4())
        
        try:
            # 处理loguru的record格式
            timestamp = record.get('time')
            if timestamp:
                timestamp = timestamp.isoformat() if hasattr(timestamp, 'isoformat') else str(timestamp)
            
            level = record.get('level')
            if level and hasattr(level, 'name'):
                level = level.name
            elif level:
                level = str(level)
                
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("""
                    INSERT INTO log_entries 
                    (id, timestamp, level, module, function, line, message, extra_data)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    entry_id,
                    timestamp,
                    level,
                    record.get('name'),
                    record.get('function'),
                    record.get('line'),
                    record.get('message'),
                    json.dumps(record.get('extra', {}), ensure_ascii=False)
                ))
                
        except Exception as e:
            # 避免在日志处理器中再次记录错误，防止递归
            pass
            
        return entry_id
        
    def query_logs(self, 
                   start_time: Optional[datetime] = None,
                   end_time: Optional[datetime] = None,
                   level: Optional[str] = None,
                   module: Optional[str] = None,
                   search_text: Optional[str] = None,
                   limit: int = 1000,
                   offset: int = 0) -> List[Dict[str, Any]]:
        """查询日志条目"""
        
        query = "SELECT * FROM log_entries WHERE 1=1"
        params = []
        
        if start_time:
            query += " AND timestamp >= ?"
            params.append(start_time.isoformat())
            
        if end_time:
            query += " AND timestamp <= ?"
            params.append(end_time.isoformat())
            
        if level:
            query += " AND level = ?"
            params.append(level)
            
        if module:
            query += " AND module LIKE ?"
            params.append(f"%{module}%")
            
        if search_text:
            query += " AND (message LIKE ? OR extra_data LIKE ?)"
            params.extend([f"%{search_text}%", f"%{search_text}%"])
            
        query += " ORDER BY timestamp DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.execute(query, params)
                
                results = []
                for row in cursor.fetchall():
                    entry = dict(row)
                    # 解析JSON格式的extra_data
                    try:
                        entry['extra_data'] = json.loads(entry['extra_data']) if entry['extra_data'] else {}
                    except json.JSONDecodeError:
                        entry['extra_data'] = {}
                    results.append(entry)
                    
                return results
                
        except Exception as e:
            logger.error(f"查询日志失败: {e}")
            return []
            
    def get_log_statistics(self, 
                          start_time: Optional[datetime] = None,
                          end_time: Optional[datetime] = None) -> Dict[str, Any]:
        """获取日志统计信息"""
        
        query = "SELECT level, COUNT(*) as count FROM log_entries WHERE 1=1"
        params = []
        
        if start_time:
            query += " AND timestamp >= ?"
            params.append(start_time.isoformat())
            
        if end_time:
            query += " AND timestamp <= ?"
            params.append(end_time.isoformat())
            
        query += " GROUP BY level"
        
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute(query, params)
                level_stats = {row[0]: row[1] for row in cursor.fetchall()}
                
                # 获取总数
                total_query = "SELECT COUNT(*) FROM log_entries WHERE 1=1"
                if params:
                    if start_time:
                        total_query += " AND timestamp >= ?"
                    if end_time:
                        total_query += " AND timestamp <= ?"
                        
                cursor = conn.execute(total_query, params)
                total_count = cursor.fetchone()[0]
                
                # 获取模块统计
                module_query = query.replace("level", "module")
                cursor = conn.execute(module_query, params)
                module_stats = {row[0]: row[1] for row in cursor.fetchall()}
                
                return {
                    "total_entries": total_count,
                    "level_distribution": level_stats,
                    "module_distribution": module_stats,
                    "query_time_range": {
                        "start": start_time.isoformat() if start_time else None,
                        "end": end_time.isoformat() if end_time else None
                    }
                }
                
        except Exception as e:
            logger.error(f"获取日志统计失败: {e}")
            return {}
            
    def cleanup_old_entries(self, retention_days: int = 30) -> int:
        """清理旧的日志条目"""
        cutoff_date = datetime.now() - timedelta(days=retention_days)
        
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.execute(
                "DELETE FROM log_entries WHERE timestamp < ?",
                (cutoff_date.isoformat(),)
            )
            deleted_count = cursor.rowcount
            conn.commit()
            conn.close()
            
            # 在单独的连接中执行VACUUM
            conn = sqlite3.connect(self.db_path)
            conn.execute("VACUUM")
            conn.close()
            
            if deleted_count > 0:
                logger.info(f"清理了 {deleted_count} 条旧日志记录")
            return deleted_count
                
        except Exception as e:
            logger.error(f"清理日志记录失败: {e}")
            return 0
            
    def export_to_json(self, output_path: str, 
                      start_time: Optional[datetime] = None,
                      end_time: Optional[datetime] = None) -> bool:
        """导出日志为JSON格式"""
        try:
            logs = self.query_logs(start_time=start_time, end_time=end_time, limit=10000)
            
            export_data = {
                "export_time": datetime.now().isoformat(),
                "total_entries": len(logs),
                "time_range": {
                    "start": start_time.isoformat() if start_time else None,
                    "end": end_time.isoformat() if end_time else None
                },
                "entries": logs
            }
            
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(export_data, f, ensure_ascii=False, indent=2)
                
            logger.info(f"日志导出完成: {output_path}, 包含 {len(logs)} 条记录")
            return True
            
        except Exception as e:
            logger.error(f"导出日志失败: {e}")
            return False
            
    def create_backup(self, backup_path: str) -> bool:
        """创建数据库备份"""
        try:
            backup_file = Path(backup_path)
            backup_file.parent.mkdir(exist_ok=True, parents=True)
            
            shutil.copy2(self.db_path, backup_file)
            
            logger.info(f"数据库备份完成: {backup_file}")
            return True
            
        except Exception as e:
            logger.error(f"创建数据库备份失败: {e}")
            return False


class LogSearchEngine:
    """日志搜索引擎"""
    
    def __init__(self, storage: StructuredLogStorage):
        self.storage = storage
        
    def search(self, query: str, **filters) -> List[Dict[str, Any]]:
        """搜索日志条目"""
        return self.storage.query_logs(search_text=query, **filters)
        
    def search_by_pattern(self, pattern: str, **filters) -> List[Dict[str, Any]]:
        """使用正则表达式搜索"""
        import re
        
        # 获取所有匹配的日志
        all_logs = self.storage.query_logs(**filters)
        
        try:
            regex = re.compile(pattern, re.IGNORECASE)
            filtered_logs = []
            
            for log in all_logs:
                if (regex.search(log['message']) or 
                    regex.search(json.dumps(log.get('extra_data', {})))):
                    filtered_logs.append(log)
                    
            return filtered_logs
            
        except re.error as e:
            logger.error(f"正则表达式错误: {e}")
            return []
            
    def get_error_summary(self, hours: int = 24) -> Dict[str, Any]:
        """获取错误摘要"""
        end_time = datetime.now()
        start_time = end_time - timedelta(hours=hours)
        
        error_logs = self.storage.query_logs(
            start_time=start_time,
            end_time=end_time,
            level="ERROR"
        )
        
        # 按错误消息分组
        error_groups = {}
        for log in error_logs:
            message = log['message']
            if message not in error_groups:
                error_groups[message] = {
                    'count': 0,
                    'first_occurrence': log['timestamp'],
                    'last_occurrence': log['timestamp'],
                    'modules': set()
                }
            
            error_groups[message]['count'] += 1
            error_groups[message]['modules'].add(log['module'])
            
            # 更新时间范围
            if log['timestamp'] < error_groups[message]['first_occurrence']:
                error_groups[message]['first_occurrence'] = log['timestamp']
            if log['timestamp'] > error_groups[message]['last_occurrence']:
                error_groups[message]['last_occurrence'] = log['timestamp']
                
        # 转换set为list以便JSON序列化
        for group in error_groups.values():
            group['modules'] = list(group['modules'])
            
        return {
            'time_range': f"最近 {hours} 小时",
            'total_errors': len(error_logs),
            'unique_errors': len(error_groups),
            'error_groups': error_groups
        }


class LoggerManager:
    """统一日志管理器"""
    
    def __init__(self, config_path: Optional[str] = None):
        self.config_path = config_path
        self.is_setup = False
        self.config = LoggingConfig()
        self.file_manager: Optional[LogFileManager] = None
        self.structured_storage: Optional[StructuredLogStorage] = None
        self.search_engine: Optional[LogSearchEngine] = None
        self.privacy_enabled = True  # 默认启用隐私保护
        self.privacy_config = PrivacyConfig()  # 隐私保护配置
        
    def setup_logging(self, level: str = "INFO", enable_file_logging: bool = True, 
                     config: Optional[LoggingConfig] = None) -> None:
        """设置日志配置"""
        if self.is_setup:
            return
            
        # 使用提供的配置或默认配置
        if config:
            self.config = config
        else:
            self.config.level = level
            self.config.file_enabled = enable_file_logging
            
        # 移除默认处理器
        logger.remove()
        
        # 配置控制台输出
        if self.config.console_enabled:
            self._setup_console_handler(self.config.level)
        
        # 配置文件输出
        if self.config.file_enabled:
            self._setup_file_handler(self.config.level)
            
        self.is_setup = True
        
    def load_config(self, config_path: str) -> LoggingConfig:
        """从文件加载配置"""
        try:
            config_file = Path(config_path)
            if not config_file.exists():
                logger.warning(f"配置文件不存在: {config_path}，使用默认配置")
                return LoggingConfig()
                
            with open(config_file, 'r', encoding='utf-8') as f:
                if config_path.endswith('.json'):
                    config_data = json.load(f)
                else:
                    # 支持YAML配置
                    try:
                        import yaml
                        config_data = yaml.safe_load(f)
                    except ImportError:
                        logger.error("需要安装PyYAML来支持YAML配置文件")
                        return LoggingConfig()
                        
            # 将配置数据转换为LoggingConfig对象
            return self._dict_to_config(config_data)
            
        except Exception as e:
            logger.error(f"加载配置文件失败: {e}，使用默认配置")
            return LoggingConfig()
            
    def _dict_to_config(self, config_data: Dict[str, Any]) -> LoggingConfig:
        """将字典转换为配置对象"""
        config = LoggingConfig()
        
        # 基本配置
        config.level = config_data.get('level', config.level)
        config.console_enabled = config_data.get('console_enabled', config.console_enabled)
        config.file_enabled = config_data.get('file_enabled', config.file_enabled)
        config.structured_logging = config_data.get('structured_logging', config.structured_logging)
        config.log_directory = config_data.get('log_directory', config.log_directory)
        config.filename_pattern = config_data.get('filename_pattern', config.filename_pattern)
        
        # 轮转配置
        rotation_data = config_data.get('rotation', {})
        config.rotation.max_size = rotation_data.get('max_size', config.rotation.max_size)
        config.rotation.rotation_time = rotation_data.get('rotation_time', config.rotation.rotation_time)
        config.rotation.retention_days = rotation_data.get('retention_days', config.rotation.retention_days)
        config.rotation.retention_count = rotation_data.get('retention_count', config.rotation.retention_count)
        config.rotation.compression = rotation_data.get('compression', config.rotation.compression)
        config.rotation.backup_count = rotation_data.get('backup_count', config.rotation.backup_count)
        
        return config
        
    def _setup_console_handler(self, level: str) -> None:
        """配置彩色控制台输出"""
        
        def format_record(record):
            """自定义格式化函数，添加emoji和颜色"""
            # 根据日志级别添加emoji图标
            level_emojis = {
                "TRACE": "🔍",
                "DEBUG": "🐛", 
                "INFO": "ℹ️",
                "SUCCESS": "✅",
                "WARNING": "⚠️",
                "ERROR": "❌",
                "CRITICAL": "💥"
            }
            
            # 获取emoji图标
            emoji = level_emojis.get(record["level"].name, "📝")
            
            # 根据级别设置颜色
            level_colors = {
                "TRACE": "dim",
                "DEBUG": "cyan",
                "INFO": "normal",
                "SUCCESS": "green",
                "WARNING": "yellow",
                "ERROR": "red",
                "CRITICAL": "red bold"
            }
            
            level_color = level_colors.get(record["level"].name, "normal")
            
            # 格式化输出
            fmt = (
                "<green>{time:HH:mm:ss.SSS}</green> | "
                f"<{level_color}>{emoji} {{level: <8}}</{level_color}> | "
                "<cyan>{name: <20}</cyan> | "
                f"<{level_color}>{{message}}</{level_color}>"
            )
            
            return fmt
        
        # 添加带隐私保护的过滤器
        def privacy_filter(record):
            if self.privacy_enabled:
                # 保护消息中的敏感信息
                record["message"] = protect_message(record["message"])
                # 保护额外数据
                if "extra" in record and isinstance(record["extra"], dict):
                    record["extra"] = protect_data(record["extra"])
            return True
            
        logger.add(
            sys.stdout,
            format=format_record,
            level=level,
            colorize=True,
            backtrace=True,
            filter=privacy_filter,
            diagnose=True,
            enqueue=True  # 线程安全
        )
        
    def _setup_file_handler(self, level: str) -> None:
        """配置高级文件日志输出"""
        log_dir = Path(self.config.log_directory)
        log_dir.mkdir(exist_ok=True, parents=True)
        
        # 初始化文件管理器
        self.file_manager = LogFileManager(log_dir, self.config.rotation)
        
        # 根据配置选择日志格式
        if self.config.structured_logging:
            file_format = self._get_structured_format()
        else:
            file_format = (
                "{time:YYYY-MM-DD HH:mm:ss.SSS} | "
                "{level: <8} | "
                "{name}:{line} | "
                "{message}"
            )
        
        # 配置主日志文件
        log_file_path = log_dir / self.config.filename_pattern
        
        # 文件日志的隐私保护过滤器
        def file_privacy_filter(record):
            if self.privacy_enabled:
                record["message"] = protect_message(record["message"])
                if "extra" in record and isinstance(record["extra"], dict):
                    record["extra"] = protect_data(record["extra"])
            return True
            
        logger.add(
            log_file_path,
            format=file_format,
            level=level,
            rotation=self.config.rotation.max_size,
            retention=f"{self.config.rotation.retention_days} days",
            compression=self.config.rotation.compression if self.config.rotation.compression != "none" else None,
            backtrace=True,
            diagnose=True,
            enqueue=True,  # 线程安全
            serialize=self.config.structured_logging,  # JSON序列化
            filter=file_privacy_filter
        )
        
        # 启动文件管理器
        self.file_manager.start_cleanup_scheduler()
        
        # 如果启用结构化日志，初始化存储系统
        if self.config.structured_logging:
            self._setup_structured_storage(log_dir)
        
        logger.info(f"文件日志已配置: {log_file_path}")
        logger.info(f"轮转策略: 大小={self.config.rotation.max_size}, 保留={self.config.rotation.retention_days}天")
        
    def _setup_structured_storage(self, log_dir: Path):
        """设置结构化日志存储"""
        db_path = log_dir / "structured_logs.db"
        self.structured_storage = StructuredLogStorage(str(db_path))
        self.search_engine = LogSearchEngine(self.structured_storage)
        
        # 添加自定义处理器来存储结构化日志
        def structured_handler(message):
            if self.structured_storage:
                # message.record 包含完整的日志记录信息
                record_dict = message.record
                self.structured_storage.store_log_entry(record_dict)
                
        logger.add(
            structured_handler,
            level=self.config.level,
            format="{message}",  # 简单格式，因为我们存储完整的记录
            filter=lambda record: self.config.structured_logging
        )
        
        logger.info("结构化日志存储已启用")
        
    def _get_structured_format(self) -> str:
        """获取结构化日志格式"""
        return "{message}"  # 使用serialize=True时，loguru会自动处理JSON格式
        
    def get_logger(self, name: str):
        """获取指定模块的日志器"""
        return logger.bind(name=name)
        
    def get_log_files_info(self) -> List[Dict[str, Any]]:
        """获取日志文件信息"""
        if self.file_manager:
            return self.file_manager.get_log_files_info()
        return []
        
    def manual_cleanup(self) -> Dict[str, int]:
        """手动执行日志清理"""
        if not self.file_manager:
            return {"deleted": 0, "compressed": 0}
            
        # 获取清理前的文件数量
        files_before = len(self.get_log_files_info())
        
        # 执行清理
        self.file_manager.cleanup_old_logs()
        self.file_manager.compress_old_logs()
        
        # 获取清理后的文件数量
        files_after = len(self.get_log_files_info())
        
        return {
            "files_before": files_before,
            "files_after": files_after,
            "deleted": max(0, files_before - files_after)
        }
        
    def update_log_level(self, level: str) -> None:
        """动态更新日志级别"""
        try:
            # 移除现有处理器
            logger.remove()
            
            # 重新设置处理器
            self.config.level = level
            self.is_setup = False
            self.setup_logging(level, self.config.file_enabled, self.config)
            
            logger.info(f"日志级别已更新为: {level}")
            
        except Exception as e:
            logger.error(f"更新日志级别失败: {e}")
            
    def shutdown(self) -> None:
        """关闭日志管理器"""
        if self.file_manager:
            self.file_manager.stop_cleanup_scheduler()
            
        # 停止性能监控
        performance_monitor.stop()
        
        logger.info("日志管理器已关闭")
        
    def export_logs(self, output_path: str, date_range: Optional[tuple] = None) -> bool:
        """导出日志文件"""
        try:
            output_file = Path(output_path)
            log_dir = Path(self.config.log_directory)
            
            if not log_dir.exists():
                logger.error("日志目录不存在")
                return False
                
            # 收集要导出的日志文件
            log_files = []
            for pattern in ["*.log", "*.log.gz", "*.log.bz2"]:
                log_files.extend(log_dir.glob(pattern))
                
            if date_range:
                start_date, end_date = date_range
                filtered_files = []
                for log_file in log_files:
                    file_time = datetime.fromtimestamp(log_file.stat().st_mtime)
                    if start_date <= file_time <= end_date:
                        filtered_files.append(log_file)
                log_files = filtered_files
                
            # 创建压缩包
            import zipfile
            with zipfile.ZipFile(output_file, 'w', zipfile.ZIP_DEFLATED) as zipf:
                for log_file in log_files:
                    zipf.write(log_file, log_file.name)
                    
            logger.info(f"日志导出完成: {output_file}, 包含 {len(log_files)} 个文件")
            return True
            
        except Exception as e:
            logger.error(f"导出日志失败: {e}")
            return False
            
    def search_logs(self, query: str, **filters) -> List[Dict[str, Any]]:
        """搜索日志"""
        if self.search_engine:
            return self.search_engine.search(query, **filters)
        return []
        
    def get_log_statistics(self, hours: int = 24) -> Dict[str, Any]:
        """获取日志统计信息"""
        if self.structured_storage:
            end_time = datetime.now()
            start_time = end_time - timedelta(hours=hours)
            return self.structured_storage.get_log_statistics(start_time, end_time)
        return {}
        
    def get_error_summary(self, hours: int = 24) -> Dict[str, Any]:
        """获取错误摘要"""
        if self.search_engine:
            return self.search_engine.get_error_summary(hours)
        return {}
        
    def start_performance_monitoring(self, interval: int = 5) -> None:
        """启动性能监控"""
        try:
            performance_monitor.resource_monitor.interval = interval
            performance_monitor.start()
            logger.info(f"性能监控已启动，监控间隔: {interval}秒")
        except Exception as e:
            logger.error(f"启动性能监控失败: {e}")
            
    def stop_performance_monitoring(self) -> None:
        """停止性能监控"""
        try:
            performance_monitor.stop()
            logger.info("性能监控已停止")
        except Exception as e:
            logger.error(f"停止性能监控失败: {e}")
            
    def get_performance_status(self) -> Dict[str, Any]:
        """获取性能监控状态"""
        return performance_monitor.get_status()
        
    def get_current_metrics(self) -> Dict[str, Any]:
        """获取当前系统资源指标"""
        return performance_monitor.get_metrics()
        
    def log_performance_report(self) -> None:
        """记录性能报告到日志"""
        try:
            report = performance_monitor.performance_tracker.get_performance_report()
            
            logger.info("=" * 50)
            logger.info("📊 性能监控报告")
            logger.info("=" * 50)
            
            # 资源使用摘要
            metrics = self.get_current_metrics()
            logger.info("🖥️ 系统资源使用:")
            logger.info(f"  • CPU: {metrics['cpu']['percent']:.1f}% ({metrics['cpu']['count']}核心)")
            logger.info(f"  • 内存: {metrics['memory']['percent']:.1f}% "
                       f"({metrics['memory']['used']:.1f}GB / {metrics['memory']['total']:.1f}GB)")
            logger.info(f"  • 磁盘: {metrics['disk']['percent']:.1f}% "
                       f"({metrics['disk']['used']:.1f}GB / {metrics['disk']['total']:.1f}GB)")
            
            # GPU信息
            if 'gpu' in metrics and metrics['gpu']:
                logger.info("🎮 GPU使用:")
                for gpu in metrics['gpu']:
                    logger.info(f"  • GPU {gpu['id']}: {gpu['name']}")
                    logger.info(f"    负载: {gpu['load']:.1f}%, "
                               f"内存: {gpu['memory_percent']:.1f}% "
                               f"({gpu['memory_used']}MB / {gpu['memory_total']}MB)")
            
            # 操作性能统计
            if report['operations']:
                logger.info("\n⚡ 操作性能统计:")
                for name, stats in report['operations'].items():
                    logger.info(f"  • {name}:")
                    logger.info(f"    - 执行次数: {stats['count']}")
                    logger.info(f"    - 平均耗时: {stats['avg_time']:.3f}秒")
                    logger.info(f"    - 最小/最大: {stats['min_time']:.3f}s / {stats['max_time']:.3f}s")
                    if stats['error_rate'] > 0:
                        logger.warning(f"    - 错误率: {stats['error_rate']:.1f}%")
            
            # 性能瓶颈
            if report['bottlenecks']:
                logger.warning("\n⚠️ 检测到性能瓶颈:")
                for bottleneck in report['bottlenecks']:
                    severity_emoji = "🔴" if bottleneck['severity'] == 'high' else "🟡"
                    logger.warning(f"  {severity_emoji} {bottleneck['operation']}: "
                                 f"平均耗时 {bottleneck['avg_time']:.2f}秒")
            
            # 建议
            if report['recommendations']:
                logger.info("\n💡 优化建议:")
                for rec in report['recommendations']:
                    logger.info(f"  • {rec}")
            
            logger.info("=" * 50)
            
        except Exception as e:
            logger.error(f"生成性能报告失败: {e}")
    
    def export_structured_logs(self, output_path: str, 
                              start_time: Optional[datetime] = None,
                              end_time: Optional[datetime] = None) -> bool:
        """导出结构化日志"""
        if self.structured_storage:
            return self.structured_storage.export_to_json(output_path, start_time, end_time)
        return False
        
    def backup_structured_logs(self, backup_path: str) -> bool:
        """备份结构化日志数据库"""
        if self.structured_storage:
            return self.structured_storage.create_backup(backup_path)
        return False
        
    def cleanup_structured_logs(self, retention_days: int = 30) -> int:
        """清理旧的结构化日志"""
        if self.structured_storage:
            return self.structured_storage.cleanup_old_entries(retention_days)
        return 0
        
    def track_error(self, exception: Exception, 
                   operation: Optional[str] = None,
                   user_id: Optional[str] = None,
                   session_id: Optional[str] = None,
                   **kwargs) -> str:
        """追踪错误"""
        context = ErrorContext(
            user_id=user_id,
            session_id=session_id,
            operation=operation,
            custom_data=kwargs
        )
        return error_tracker.track_error(exception, context=context)
        
    def add_operation_log(self, operation: str, details: Optional[Dict[str, Any]] = None):
        """添加操作日志到错误追踪器历史"""
        error_tracker.add_operation(operation, details)
        
    def get_error_report(self, hours: int = 24) -> Dict[str, Any]:
        """获取错误报告"""
        return error_tracker.get_error_report(hours)
        
    def analyze_error_patterns(self) -> Dict[str, Any]:
        """分析错误模式"""
        from lama_cleaner.error_tracker import error_analyzer
        return error_analyzer.analyze_patterns()
        
    def export_error_report(self, filepath: str) -> bool:
        """导出错误报告"""
        return error_tracker.export_errors(filepath)
        
    def log_error_report(self, hours: int = 24) -> None:
        """记录错误报告到日志"""
        try:
            report = self.get_error_report(hours)
            
            logger.info("=" * 50)
            logger.info("🔍 错误追踪报告")
            logger.info("=" * 50)
            
            # 摘要信息
            summary = report.get('summary', {})
            logger.info("📊 错误摘要:")
            logger.info(f"  • 总错误数: {summary.get('total_errors', 0)}")
            logger.info(f"  • 唯一错误: {summary.get('unique_errors', 0)}")
            logger.info(f"  • 严重错误: {summary.get('critical_count', 0)}")
            logger.info(f"  • 未解决数: {summary.get('unresolved_count', 0)}")
            
            # 按类别统计
            by_category = report.get('by_category', {})
            if by_category:
                logger.info("\n📁 按类别统计:")
                for category, count in sorted(by_category.items(), key=lambda x: x[1], reverse=True):
                    logger.info(f"  • {category}: {count}")
            
            # 按严重程度统计
            by_severity = report.get('by_severity', {})
            if by_severity:
                logger.info("\n⚠️ 按严重程度:")
                for severity, count in by_severity.items():
                    logger.info(f"  • {severity}: {count}")
            
            # 高频错误
            top_errors = report.get('top_errors', {})
            if top_errors:
                logger.info("\n🔝 高频错误:")
                for error, count in list(top_errors.items())[:5]:
                    logger.info(f"  • {error}: {count}次")
            
            # 错误模式分析
            patterns = self.analyze_error_patterns()
            if patterns.get('patterns'):
                logger.info("\n🔬 错误模式:")
                for pattern in patterns['patterns']:
                    logger.info(f"  • {pattern.get('description', '未知模式')}")
                    if 'recommendation' in pattern:
                        logger.info(f"    建议: {pattern['recommendation']}")
            
            logger.info("=" * 50)
            
        except Exception as e:
            logger.error(f"生成错误报告失败: {e}")
            
    def enable_privacy_protection(self, config: Optional[PrivacyConfig] = None):
        """启用隐私保护"""
        self.privacy_enabled = True
        if config:
            self.privacy_config = config
            privacy_protector.config = config
        logger.info("✅ 隐私保护已启用")
        
    def disable_privacy_protection(self):
        """禁用隐私保护"""
        self.privacy_enabled = False
        logger.warning("⚠️ 隐私保护已禁用")
        
    def configure_privacy(self, **kwargs):
        """配置隐私保护选项"""
        for key, value in kwargs.items():
            if hasattr(self.privacy_config, key):
                setattr(self.privacy_config, key, value)
        privacy_protector.config = self.privacy_config
        logger.info("隐私保护配置已更新")
        
    def add_log_user(self, user_id: str, role: str = 'viewer'):
        """添加日志访问用户"""
        privacy_protector.access_controller.add_user(user_id, role)
        
    def check_log_access(self, user_id: str, action: str) -> bool:
        """检查用户日志访问权限"""
        return privacy_protector.check_access(user_id, action)
        
    def protect_log_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """保护日志数据"""
        if self.privacy_enabled:
            return privacy_protector.protect_log_data(data)
        return data
        
    def get_privacy_report(self) -> Dict[str, Any]:
        """获取隐私保护报告"""
        return privacy_protector.export_privacy_report()
        
    def get_audit_log(self, limit: int = 100) -> List[Dict[str, Any]]:
        """获取访问审计日志"""
        return privacy_protector.get_audit_log(limit)
        
    def show_startup_banner(self, version: str = "1.0.0", mode: str = "分布式处理", 
                            host: str = "localhost", port: int = 8080) -> None:
        """显示启动横幅"""
        import platform
        from datetime import datetime
        
        # 获取系统信息
        py_version = platform.python_version()
        os_info = platform.system()
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # ASCII艺术字
        ascii_art = """
╔══════════════════════════════════════════════════════════════╗
║                                                              ║
║    🦙 LAMA CLEANER - Image Inpainting System                ║
║                                                              ║
╚══════════════════════════════════════════════════════════════╝"""
        
        banner = f"""{ascii_art}

🚀 系统启动信息
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
   📦 版本:      v{version}
   🎯 运行模式:  {mode}
   🌐 监听地址:  http://{host}:{port}
   📁 日志目录:  ./logs/
   🖥️  系统环境:  {os_info} | Python {py_version}
   🕐 启动时间:  {timestamp}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
        print(banner)
        

# 全局日志管理器实例
_logger_manager = LoggerManager()

def setup_logging(level: str = "INFO", enable_file_logging: bool = True) -> None:
    """设置全局日志配置"""
    _logger_manager.setup_logging(level, enable_file_logging)

def get_logger(name: str):
    """获取模块日志器"""
    return _logger_manager.get_logger(name)

def show_startup_banner(version: str = "1.0.0", mode: str = "分布式处理", 
                       host: str = "localhost", port: int = 8080) -> None:
    """显示启动横幅"""
    _logger_manager.show_startup_banner(version, mode, host, port)

def log_success(message: str, name: str = "system") -> None:
    """记录成功消息"""
    logger.bind(name=name).success(message)

def log_shutdown(name: str = "system") -> None:
    """显示优雅关闭消息"""
    shutdown_msg = """
╔══════════════════════════════════════════════════════════════╗
║    🛑 系统正在优雅关闭...                                    ║
║    👋 感谢使用 Lama Cleaner!                                ║
╚══════════════════════════════════════════════════════════════╝
"""
    print(shutdown_msg)
    logger.bind(name=name).info("系统已安全关闭")