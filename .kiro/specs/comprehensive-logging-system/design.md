# 设计文档

## 概述

设计一个完善的日志系统来解决Lama Cleaner项目中调度模块启动时缺乏可见日志输出的问题。该系统将基于现有的loguru库，提供统一的日志配置、实时控制台输出和结构化的日志管理。

## 架构

### 核心组件架构

```
日志系统架构
├── LoggerManager (日志管理器)
│   ├── 配置加载和验证
│   ├── 日志器初始化
│   └── 运行时配置更新
├── ConsoleHandler (控制台处理器)
│   ├── 彩色输出格式化
│   ├── 实时日志显示
│   └── 启动横幅显示
├── FileHandler (文件处理器)
│   ├── 日志文件轮转
│   ├── 结构化日志存储
│   └── 日志清理管理
└── ModuleLogger (模块日志器)
    ├── 分布式调度器日志
    ├── 工作节点日志
    ├── 任务管理器日志
    └── API服务器日志
```

### 日志层次结构

```
lama_cleaner (根日志器)
├── lama_cleaner.server (Flask服务器)
├── lama_cleaner.distributed (分布式系统)
│   ├── lama_cleaner.distributed.scheduler (调度器)
│   ├── lama_cleaner.distributed.worker (工作节点)
│   ├── lama_cleaner.distributed.task_manager (任务管理)
│   └── lama_cleaner.distributed.queue_manager (队列管理)
├── lama_cleaner.model (AI模型)
└── lama_cleaner.plugins (插件系统)
```

## 组件和接口

### 1. LoggerManager (日志管理器)

**职责：** 统一管理所有日志配置和初始化

**接口：**
```python
class LoggerManager:
    def __init__(self, config_path: Optional[str] = None)
    def setup_logging(self) -> None
    def get_logger(self, name: str) -> Logger
    def update_log_level(self, level: str) -> None
    def reload_config(self) -> None
    def shutdown(self) -> None
```

**关键特性：**
- 支持YAML和JSON配置文件
- 自动创建日志目录
- 配置验证和错误处理
- 运行时配置热重载

### 2. ConsoleHandler (控制台处理器)

**职责：** 处理实时控制台日志输出，提供彩色和格式化显示

**接口：**
```python
class ConsoleHandler:
    def format_startup_banner(self, version: str, mode: str) -> str
    def format_log_message(self, record: LogRecord) -> str
    def setup_colors(self) -> Dict[str, str]
    def handle_shutdown_message(self) -> None
```

**输出格式：**
```
🚀 Lama Cleaner v1.0.0 启动中...
📋 模式: 分布式处理
🔧 配置文件: /path/to/config.yaml
⚡ 调度器启动: localhost:5555
✅ 工作节点注册: GPU节点 (CUDA 11.8)
📊 队列管理器: Redis连接成功
🌐 Web服务器: http://localhost:8080
```

### 3. FileHandler (文件处理器)

**职责：** 管理日志文件的存储、轮转和清理

**配置参数：**
```yaml
file_logging:
  enabled: true
  directory: "logs"
  filename_pattern: "lama_cleaner_{time:YYYY-MM-DD}.log"
  rotation: "100 MB"
  retention: "30 days"
  compression: "gz"
  encoding: "utf-8"
```

### 4. ModuleLogger (模块日志器)

**职责：** 为每个模块提供专门的日志记录功能

**调度器日志示例：**
```python
# 启动日志
scheduler_logger.info("🔧 调度器初始化开始", extra={
    "module": "scheduler",
    "action": "startup",
    "config": {"host": "localhost", "port": 5555}
})

# 任务处理日志
scheduler_logger.info("📋 接收新任务", extra={
    "module": "scheduler", 
    "action": "task_received",
    "task_id": "task_123",
    "task_type": "inpainting",
    "priority": "normal"
})

# 错误日志
scheduler_logger.error("❌ 节点连接失败", extra={
    "module": "scheduler",
    "action": "node_connection_failed", 
    "node_id": "worker_001",
    "error": str(e),
    "retry_count": 3
})
```

## 数据模型

### 日志配置模型

```python
@dataclass
class LoggingConfig:
    """日志配置数据模型"""
    level: str = "INFO"
    console_enabled: bool = True
    file_enabled: bool = True
    structured_logging: bool = True
    
    console: ConsoleConfig = field(default_factory=ConsoleConfig)
    file: FileConfig = field(default_factory=FileConfig)
    modules: Dict[str, ModuleConfig] = field(default_factory=dict)

@dataclass
class ConsoleConfig:
    """控制台日志配置"""
    level: str = "INFO"
    colored: bool = True
    show_time: bool = True
    show_module: bool = True
    format: str = "<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan> | {message}"

@dataclass
class FileConfig:
    """文件日志配置"""
    level: str = "DEBUG"
    directory: str = "logs"
    filename: str = "lama_cleaner_{time:YYYY-MM-DD}.log"
    rotation: str = "100 MB"
    retention: str = "30 days"
    compression: str = "gz"
```

### 日志记录模型

```python
@dataclass
class LogEntry:
    """结构化日志条目"""
    timestamp: datetime
    level: str
    module: str
    action: str
    message: str
    extra_data: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式，便于JSON序列化"""
        return asdict(self)
```

## 错误处理

### 错误处理策略

1. **配置文件错误**
   - 配置文件不存在：使用默认配置并记录警告
   - 配置格式错误：使用默认配置并记录错误详情
   - 权限错误：尝试使用临时目录并记录错误

2. **日志目录错误**
   - 目录不存在：自动创建目录
   - 权限不足：尝试使用用户目录或临时目录
   - 磁盘空间不足：记录错误并禁用文件日志

3. **运行时错误**
   - 日志写入失败：切换到备用处理器
   - 网络日志发送失败：缓存到本地文件
   - 内存不足：减少日志缓冲区大小

### 错误恢复机制

```python
class LoggerErrorHandler:
    def handle_config_error(self, error: Exception) -> LoggingConfig:
        """处理配置错误，返回安全的默认配置"""
        
    def handle_file_error(self, error: Exception) -> str:
        """处理文件错误，返回备用日志路径"""
        
    def handle_runtime_error(self, error: Exception) -> None:
        """处理运行时错误，执行恢复策略"""
```

## 测试策略

### 单元测试

1. **配置管理测试**
   - 默认配置加载
   - 自定义配置合并
   - 配置验证逻辑
   - 错误配置处理

2. **日志输出测试**
   - 控制台格式化
   - 文件写入功能
   - 日志级别过滤
   - 结构化数据序列化

3. **错误处理测试**
   - 权限错误模拟
   - 磁盘空间不足模拟
   - 网络错误模拟
   - 配置文件损坏模拟

### 集成测试

1. **模块集成测试**
   - 调度器启动日志验证
   - 工作节点注册日志验证
   - 任务处理日志验证
   - API请求日志验证

2. **性能测试**
   - 高并发日志写入
   - 大文件日志轮转
   - 内存使用监控
   - CPU开销测试

### 测试用例示例

```python
def test_scheduler_startup_logging():
    """测试调度器启动时的日志输出"""
    with LogCapture() as log_capture:
        scheduler = DistributedScheduler()
        scheduler.start()
        
        # 验证启动日志
        assert "调度器初始化开始" in log_capture.messages
        assert "ZeroMQ服务器启动" in log_capture.messages
        assert "调度器启动完成" in log_capture.messages
        
        # 验证日志级别
        assert log_capture.has_info_level()
        
        # 验证结构化数据
        startup_log = log_capture.get_log_by_action("startup")
        assert startup_log.extra_data["module"] == "scheduler"
        assert "host" in startup_log.extra_data["config"]
```

## 实施计划

### 第一阶段：立即可见的日志输出（高优先级）

1. **快速修复调度器启动日志**
   - 在关键启动步骤添加立即输出的日志
   - 使用简单的print语句作为临时解决方案
   - 确保错误信息能够立即显示

2. **基础控制台输出**
   - 实现彩色日志输出
   - 添加启动横幅
   - 显示关键系统信息

### 第二阶段：统一日志管理

1. **LoggerManager实现**
   - 创建统一的日志管理器
   - 实现配置加载和验证
   - 集成到现有模块中

2. **模块日志器集成**
   - 为每个分布式模块添加专门的日志器
   - 统一日志格式和级别
   - 添加结构化日志数据

### 第三阶段：高级功能

1. **文件日志管理**
   - 实现日志文件轮转
   - 添加日志压缩和清理
   - 支持多种输出格式

2. **性能监控和错误追踪**
   - 添加性能监控日志
   - 实现详细的错误追踪
   - 支持日志分析和报告