"""
错误追踪和报告模块 - 详细记录、分类、统计和分析错误
"""
import sys
import traceback
import threading
import hashlib
from typing import Dict, Any, Optional, List, Tuple
from datetime import datetime, timedelta
from collections import defaultdict, deque
from enum import Enum
from dataclasses import dataclass, field
import json
from pathlib import Path
from loguru import logger


class ErrorSeverity(Enum):
    """错误严重程度"""
    LOW = "low"  # 轻微，不影响功能
    MEDIUM = "medium"  # 中等，部分功能受影响
    HIGH = "high"  # 严重，主要功能受影响
    CRITICAL = "critical"  # 致命，系统无法运行


class ErrorCategory(Enum):
    """错误分类"""
    SYSTEM = "system"  # 系统错误
    NETWORK = "network"  # 网络错误
    DATABASE = "database"  # 数据库错误
    FILE_IO = "file_io"  # 文件操作错误
    VALIDATION = "validation"  # 数据验证错误
    AUTHENTICATION = "authentication"  # 认证授权错误
    CONFIGURATION = "configuration"  # 配置错误
    RESOURCE = "resource"  # 资源错误（内存、磁盘等）
    MODEL = "model"  # AI模型相关错误
    PROCESSING = "processing"  # 图像处理错误
    UNKNOWN = "unknown"  # 未知错误


@dataclass
class ErrorContext:
    """错误上下文信息"""
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    request_id: Optional[str] = None
    operation: Optional[str] = None
    input_data: Optional[Dict[str, Any]] = None
    environment: Optional[Dict[str, Any]] = None
    custom_data: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ErrorRecord:
    """错误记录"""
    error_id: str
    timestamp: datetime
    error_type: str
    error_message: str
    stack_trace: str
    category: ErrorCategory
    severity: ErrorSeverity
    context: ErrorContext
    fingerprint: str  # 错误指纹，用于去重
    count: int = 1  # 相同错误发生次数
    first_seen: datetime = None
    last_seen: datetime = None
    resolved: bool = False
    resolution: Optional[str] = None


class ErrorSolutionProvider:
    """错误解决方案提供器"""
    
    def __init__(self):
        # 预定义的错误解决方案
        self.solutions = {
            "OutOfMemoryError": {
                "title": "内存不足错误",
                "steps": [
                    "1. 检查系统可用内存：free -h",
                    "2. 清理不必要的进程释放内存",
                    "3. 考虑增加系统内存或使用更小的模型",
                    "4. 调整批处理大小减少内存占用"
                ],
                "docs": "https://docs.example.com/memory-optimization"
            },
            "CUDA out of memory": {
                "title": "GPU内存不足",
                "steps": [
                    "1. 检查GPU内存使用：nvidia-smi",
                    "2. 清理GPU缓存：torch.cuda.empty_cache()",
                    "3. 减小批处理大小或图像分辨率",
                    "4. 使用CPU模式或切换到更小的模型"
                ],
                "docs": "https://docs.example.com/gpu-memory"
            },
            "FileNotFoundError": {
                "title": "文件未找到",
                "steps": [
                    "1. 检查文件路径是否正确",
                    "2. 确认文件权限设置",
                    "3. 验证文件是否存在：ls -la <filepath>",
                    "4. 检查工作目录：pwd"
                ],
                "docs": "https://docs.example.com/file-operations"
            },
            "ConnectionError": {
                "title": "网络连接错误",
                "steps": [
                    "1. 检查网络连接状态",
                    "2. 验证目标服务是否可用",
                    "3. 检查防火墙设置",
                    "4. 重试连接或使用备用服务"
                ],
                "docs": "https://docs.example.com/network-issues"
            },
            "ModelNotFoundError": {
                "title": "模型未找到",
                "steps": [
                    "1. 检查模型文件是否存在",
                    "2. 验证模型路径配置",
                    "3. 下载缺失的模型文件",
                    "4. 检查模型版本兼容性"
                ],
                "docs": "https://docs.example.com/model-management"
            }
        }
        
    def get_solution(self, error: ErrorRecord) -> Optional[Dict[str, Any]]:
        """获取错误解决方案"""
        # 根据错误消息查找解决方案
        for key, solution in self.solutions.items():
            if key.lower() in error.error_message.lower() or key.lower() in error.error_type.lower():
                return solution
                
        # 根据错误类别提供通用建议
        category_solutions = {
            ErrorCategory.RESOURCE: {
                "title": "资源错误",
                "steps": [
                    "1. 检查系统资源使用情况",
                    "2. 清理不必要的进程和文件",
                    "3. 考虑升级硬件或优化配置",
                    "4. 实施资源限制和监控"
                ]
            },
            ErrorCategory.CONFIGURATION: {
                "title": "配置错误",
                "steps": [
                    "1. 检查配置文件格式和内容",
                    "2. 验证必需的配置项",
                    "3. 使用默认配置作为参考",
                    "4. 查看配置文档"
                ]
            },
            ErrorCategory.MODEL: {
                "title": "模型错误",
                "steps": [
                    "1. 验证模型文件完整性",
                    "2. 检查模型版本兼容性",
                    "3. 清理模型缓存",
                    "4. 重新下载或切换模型"
                ]
            }
        }
        
        return category_solutions.get(error.category)


class ErrorTracker:
    """错误追踪器"""
    
    def __init__(self, max_records: int = 10000):
        self.max_records = max_records
        self.errors = deque(maxlen=max_records)
        self.error_index = {}  # 错误指纹索引
        self.category_stats = defaultdict(int)
        self.severity_stats = defaultdict(int)
        self.hourly_stats = defaultdict(int)
        self.solution_provider = ErrorSolutionProvider()
        self.lock = threading.Lock()
        
        # 操作历史记录
        self.operation_history = deque(maxlen=100)
        
    def track_error(self, exception: Exception, 
                   context: Optional[ErrorContext] = None,
                   category: Optional[ErrorCategory] = None,
                   severity: Optional[ErrorSeverity] = None) -> str:
        """追踪错误"""
        with self.lock:
            # 生成错误ID
            error_id = self._generate_error_id()
            
            # 获取堆栈跟踪
            tb_lines = traceback.format_exception(
                type(exception), exception, exception.__traceback__
            )
            stack_trace = ''.join(tb_lines)
            
            # 自动分类
            if category is None:
                category = self._classify_error(exception, stack_trace)
                
            # 自动评估严重程度
            if severity is None:
                severity = self._assess_severity(exception, category)
                
            # 生成错误指纹
            fingerprint = self._generate_fingerprint(
                type(exception).__name__, 
                str(exception),
                stack_trace
            )
            
            # 检查是否为重复错误
            if fingerprint in self.error_index:
                # 更新现有错误记录
                existing = self.error_index[fingerprint]
                existing.count += 1
                existing.last_seen = datetime.now()
                error_record = existing
            else:
                # 创建新错误记录
                error_record = ErrorRecord(
                    error_id=error_id,
                    timestamp=datetime.now(),
                    error_type=type(exception).__name__,
                    error_message=str(exception),
                    stack_trace=stack_trace,
                    category=category,
                    severity=severity,
                    context=context or ErrorContext(),
                    fingerprint=fingerprint,
                    first_seen=datetime.now(),
                    last_seen=datetime.now()
                )
                
                self.errors.append(error_record)
                self.error_index[fingerprint] = error_record
                
            # 更新统计
            self._update_statistics(error_record)
            
            # 记录到日志
            self._log_error(error_record)
            
            # 获取并记录解决方案
            solution = self.solution_provider.get_solution(error_record)
            if solution:
                logger.info(f"💡 错误解决建议: {solution.get('title', '未知')}")
                for step in solution.get('steps', []):
                    logger.info(f"  {step}")
                if 'docs' in solution:
                    logger.info(f"  📚 参考文档: {solution['docs']}")
                    
            return error_id
            
    def _generate_error_id(self) -> str:
        """生成错误ID"""
        timestamp = datetime.now().strftime('%Y%m%d%H%M%S%f')
        return f"ERR-{timestamp[:14]}-{timestamp[14:18]}"
        
    def _generate_fingerprint(self, error_type: str, message: str, stack: str) -> str:
        """生成错误指纹用于去重"""
        # 提取关键堆栈帧
        key_frames = []
        for line in stack.split('\n'):
            if 'File' in line and '.py' in line:
                # 移除具体行号，保留文件和函数
                parts = line.split(',')
                if len(parts) >= 2:
                    file_part = parts[0].strip()
                    func_part = parts[2].strip() if len(parts) > 2 else ""
                    key_frames.append(f"{file_part}:{func_part}")
                    
        # 组合关键信息生成指纹
        fingerprint_data = f"{error_type}:{message[:100]}:{'|'.join(key_frames[:5])}"
        return hashlib.md5(fingerprint_data.encode()).hexdigest()
        
    def _classify_error(self, exception: Exception, stack_trace: str) -> ErrorCategory:
        """自动分类错误"""
        error_type = type(exception).__name__
        error_msg = str(exception).lower()
        stack_lower = stack_trace.lower()
        
        # 基于错误类型和消息分类
        if any(kw in error_msg for kw in ['memory', 'oom', 'cuda']):
            return ErrorCategory.RESOURCE
        elif any(kw in error_msg for kw in ['file', 'path', 'directory', 'permission']):
            return ErrorCategory.FILE_IO
        elif any(kw in error_msg for kw in ['connect', 'network', 'timeout', 'socket']):
            return ErrorCategory.NETWORK
        elif any(kw in error_msg for kw in ['database', 'sql', 'query']):
            return ErrorCategory.DATABASE
        elif any(kw in error_msg for kw in ['auth', 'token', 'permission', 'forbidden']):
            return ErrorCategory.AUTHENTICATION
        elif any(kw in error_msg for kw in ['config', 'setting', 'parameter']):
            return ErrorCategory.CONFIGURATION
        elif any(kw in error_msg for kw in ['model', 'inference', 'predict']):
            return ErrorCategory.MODEL
        elif any(kw in error_msg for kw in ['image', 'process', 'resize', 'convert']):
            return ErrorCategory.PROCESSING
        elif any(kw in error_msg for kw in ['valid', 'format', 'type', 'value']):
            return ErrorCategory.VALIDATION
        else:
            return ErrorCategory.UNKNOWN
            
    def _assess_severity(self, exception: Exception, category: ErrorCategory) -> ErrorSeverity:
        """评估错误严重程度"""
        # 致命错误
        critical_types = [SystemExit, KeyboardInterrupt, MemoryError]
        if type(exception) in critical_types:
            return ErrorSeverity.CRITICAL
            
        # 高严重度
        high_categories = [ErrorCategory.SYSTEM, ErrorCategory.RESOURCE, ErrorCategory.DATABASE]
        if category in high_categories:
            return ErrorSeverity.HIGH
            
        # 中等严重度
        medium_categories = [ErrorCategory.NETWORK, ErrorCategory.AUTHENTICATION, ErrorCategory.MODEL]
        if category in medium_categories:
            return ErrorSeverity.MEDIUM
            
        # 低严重度
        return ErrorSeverity.LOW
        
    def _update_statistics(self, error: ErrorRecord):
        """更新错误统计"""
        self.category_stats[error.category] += 1
        self.severity_stats[error.severity] += 1
        
        # 按小时统计
        hour_key = error.timestamp.strftime('%Y-%m-%d %H:00')
        self.hourly_stats[hour_key] += 1
        
    def _log_error(self, error: ErrorRecord):
        """记录错误到日志"""
        severity_emoji = {
            ErrorSeverity.LOW: "🟢",
            ErrorSeverity.MEDIUM: "🟡",
            ErrorSeverity.HIGH: "🟠",
            ErrorSeverity.CRITICAL: "🔴"
        }
        
        emoji = severity_emoji.get(error.severity, "⚪")
        
        log_message = (
            f"{emoji} 错误追踪 [{error.severity.value.upper()}] - {error.error_type}\n"
            f"  错误ID: {error.error_id}\n"
            f"  类别: {error.category.value}\n"
            f"  消息: {error.error_message}\n"
            f"  发生次数: {error.count}\n"
        )
        
        if error.context.operation:
            log_message += f"  操作: {error.context.operation}\n"
            
        # 根据严重程度选择日志级别
        if error.severity == ErrorSeverity.CRITICAL:
            logger.critical(log_message)
        elif error.severity == ErrorSeverity.HIGH:
            logger.error(log_message)
        elif error.severity == ErrorSeverity.MEDIUM:
            logger.warning(log_message)
        else:
            logger.info(log_message)
            
    def add_operation(self, operation: str, details: Optional[Dict[str, Any]] = None):
        """添加操作到历史记录"""
        self.operation_history.append({
            'timestamp': datetime.now(),
            'operation': operation,
            'details': details or {}
        })
        
    def get_error_report(self, hours: int = 24) -> Dict[str, Any]:
        """生成错误报告"""
        cutoff_time = datetime.now() - timedelta(hours=hours)
        recent_errors = [e for e in self.errors if e.timestamp >= cutoff_time]
        
        # 按类别统计
        category_counts = defaultdict(int)
        severity_counts = defaultdict(int)
        top_errors = defaultdict(int)
        
        for error in recent_errors:
            category_counts[error.category.value] += error.count
            severity_counts[error.severity.value] += error.count
            top_errors[f"{error.error_type}: {error.error_message[:50]}"] += error.count
            
        # 错误趋势
        trend_data = []
        for hour in range(hours):
            hour_time = datetime.now() - timedelta(hours=hour)
            hour_key = hour_time.strftime('%Y-%m-%d %H:00')
            trend_data.append({
                'hour': hour_key,
                'count': self.hourly_stats.get(hour_key, 0)
            })
            
        return {
            'summary': {
                'total_errors': sum(e.count for e in recent_errors),
                'unique_errors': len(recent_errors),
                'critical_count': sum(1 for e in recent_errors if e.severity == ErrorSeverity.CRITICAL),
                'unresolved_count': sum(1 for e in recent_errors if not e.resolved)
            },
            'by_category': dict(category_counts),
            'by_severity': dict(severity_counts),
            'top_errors': dict(sorted(top_errors.items(), key=lambda x: x[1], reverse=True)[:10]),
            'trend': trend_data,
            'recent_operations': list(self.operation_history)[-20:]
        }
        
    def get_error_by_id(self, error_id: str) -> Optional[ErrorRecord]:
        """根据ID获取错误记录"""
        for error in self.errors:
            if error.error_id == error_id:
                return error
        return None
        
    def mark_resolved(self, error_id: str, resolution: str) -> bool:
        """标记错误为已解决"""
        error = self.get_error_by_id(error_id)
        if error:
            error.resolved = True
            error.resolution = resolution
            logger.info(f"✅ 错误 {error_id} 已标记为解决: {resolution}")
            return True
        return False
        
    def export_errors(self, filepath: str, format: str = 'json') -> bool:
        """导出错误数据"""
        try:
            data = {
                'export_time': datetime.now().isoformat(),
                'errors': [
                    {
                        'error_id': e.error_id,
                        'timestamp': e.timestamp.isoformat(),
                        'type': e.error_type,
                        'message': e.error_message,
                        'category': e.category.value,
                        'severity': e.severity.value,
                        'count': e.count,
                        'resolved': e.resolved,
                        'resolution': e.resolution
                    }
                    for e in self.errors
                ],
                'statistics': {
                    'by_category': dict(self.category_stats),
                    'by_severity': dict(self.severity_stats)
                }
            }
            
            path = Path(filepath)
            if format == 'json':
                with open(path, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
            
            logger.info(f"📤 错误数据已导出到: {filepath}")
            return True
            
        except Exception as e:
            logger.error(f"导出错误数据失败: {e}")
            return False


class ErrorAnalyzer:
    """错误分析器"""
    
    def __init__(self, tracker: ErrorTracker):
        self.tracker = tracker
        
    def analyze_patterns(self) -> Dict[str, Any]:
        """分析错误模式"""
        if not self.tracker.errors:
            return {'patterns': [], 'correlations': []}
            
        patterns = []
        
        # 分析时间模式
        time_pattern = self._analyze_time_patterns()
        if time_pattern:
            patterns.append(time_pattern)
            
        # 分析错误序列
        sequence_pattern = self._analyze_error_sequences()
        if sequence_pattern:
            patterns.append(sequence_pattern)
            
        # 分析相关性
        correlations = self._analyze_correlations()
        
        return {
            'patterns': patterns,
            'correlations': correlations
        }
        
    def _analyze_time_patterns(self) -> Optional[Dict[str, Any]]:
        """分析时间相关的错误模式"""
        hourly_errors = defaultdict(list)
        
        for error in self.tracker.errors:
            hour = error.timestamp.hour
            hourly_errors[hour].append(error)
            
        # 找出高发时段
        peak_hours = sorted(hourly_errors.items(), 
                          key=lambda x: len(x[1]), 
                          reverse=True)[:3]
        
        if peak_hours and len(peak_hours[0][1]) > 5:
            return {
                'type': 'time_pattern',
                'description': '错误高发时段',
                'peak_hours': [h for h, _ in peak_hours],
                'recommendation': '建议在这些时段加强监控和资源准备'
            }
        return None
        
    def _analyze_error_sequences(self) -> Optional[Dict[str, Any]]:
        """分析错误序列模式"""
        sequences = []
        errors_list = list(self.tracker.errors)
        
        for i in range(len(errors_list) - 2):
            seq = [errors_list[i].category, 
                  errors_list[i+1].category, 
                  errors_list[i+2].category]
            sequences.append(tuple(seq))
            
        # 找出常见序列
        from collections import Counter
        seq_counts = Counter(sequences)
        
        if seq_counts:
            most_common = seq_counts.most_common(1)[0]
            if most_common[1] > 2:
                return {
                    'type': 'sequence_pattern',
                    'description': '常见错误序列',
                    'sequence': [c.value for c in most_common[0]],
                    'count': most_common[1],
                    'recommendation': '这些错误可能存在因果关系，建议深入调查'
                }
        return None
        
    def _analyze_correlations(self) -> List[Dict[str, Any]]:
        """分析错误之间的相关性"""
        correlations = []
        
        # 分析类别之间的关联
        category_pairs = defaultdict(int)
        errors_list = list(self.tracker.errors)
        
        for i in range(len(errors_list) - 1):
            if (errors_list[i+1].timestamp - errors_list[i].timestamp).seconds < 60:
                pair = (errors_list[i].category.value, 
                       errors_list[i+1].category.value)
                category_pairs[pair] += 1
                
        # 找出强相关
        for pair, count in category_pairs.items():
            if count > 3:
                correlations.append({
                    'type': 'category_correlation',
                    'from': pair[0],
                    'to': pair[1],
                    'strength': count,
                    'description': f"{pair[0]}错误后经常出现{pair[1]}错误"
                })
                
        return correlations


# 全局错误追踪器实例
error_tracker = ErrorTracker()
error_analyzer = ErrorAnalyzer(error_tracker)

# 导出便捷函数
def track_error(exception: Exception, **kwargs) -> str:
    """追踪错误的便捷函数"""
    return error_tracker.track_error(exception, **kwargs)

def get_error_report(hours: int = 24) -> Dict[str, Any]:
    """获取错误报告的便捷函数"""
    return error_tracker.get_error_report(hours)

def analyze_errors() -> Dict[str, Any]:
    """分析错误模式的便捷函数"""
    return error_analyzer.analyze_patterns()