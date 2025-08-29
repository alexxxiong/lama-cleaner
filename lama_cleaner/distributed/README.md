# 分布式处理模块

该模块为 Lama Cleaner 实现了基于 ZeroMQ 的分布式图像处理架构，支持多个处理节点并行处理任务。

## 主要组件

### 核心数据模型 (`models.py`)
- **Task**: 任务数据模型，包含任务类型、状态、配置等信息
- **NodeCapability**: 节点能力模型，描述节点的硬件配置和支持的功能
- **QueueConfig**: 队列配置模型，定义不同类型队列的需求和参数

### 管理器组件
- **TaskManager**: 任务管理器，负责任务的创建、路由和状态管理
- **QueueManager**: 队列管理器，基于 ZeroMQ 管理不同类型的任务队列
- **NodeManager**: 节点管理器，管理处理节点的注册、发现和监控
- **StateManager**: 状态管理器，维护任务和节点的状态信息

### 配置管理 (`config.py`)
- **DistributedConfig**: 分布式处理主配置类
- **ConfigManager**: 配置管理器，支持分层配置和热重载

### 工具函数 (`utils.py`)
- 硬件检测函数（GPU、CPU、内存）
- 系统信息收集
- 文件验证和管理工具

## 架构特点

### 队列系统
- 基于 ZeroMQ 的 PUSH/PULL 模式
- 支持多种队列类型：
  - `gpu-high`: 高端 GPU 队列（8GB+ 显存）
  - `gpu-medium`: 中端 GPU 队列（4GB+ 显存）
  - `gpu-low`: 低端 GPU 队列（2GB+ 显存）
  - `cpu-intensive`: CPU 密集型队列
  - `cpu-light`: 轻量级 CPU 队列
  - `serverless`: Serverless 函数队列

### 任务路由
- 智能任务路由，根据任务需求自动选择合适的队列
- 支持任务优先级和负载均衡
- 自动重试和故障恢复机制

### 节点管理
- 自动节点发现和注册
- 硬件能力检测和匹配
- 心跳监控和健康检查

## 使用示例

```python
from lama_cleaner.distributed import (
    Task, TaskType, TaskManager, 
    QueueManager, NodeManager, 
    DistributedConfig
)

# 创建任务
task = Task(
    task_type=TaskType.INPAINT,
    image_path="/path/to/image.jpg",
    config={"model": "lama", "device": "cuda"}
)

# 创建管理器
task_manager = TaskManager()
queue_manager = QueueManager()
node_manager = NodeManager()

# 启动服务
task_manager.start()
queue_manager.start()
node_manager.start()
```

## 配置

配置文件支持 YAML 格式，可以通过环境变量覆盖：

```yaml
# 基础配置
enabled: true
scheduler_host: "localhost"
scheduler_port: 8081

# ZeroMQ 配置
zeromq:
  host: "localhost"
  base_port: 5555

# Redis 配置
redis:
  enabled: true
  host: "localhost"
  port: 6379
```

## 测试

运行测试套件：

```bash
# 运行所有测试
python lama_cleaner/distributed/tests/run_tests.py --type all --verbose

# 运行特定类型的测试
python lama_cleaner/distributed/tests/run_tests.py --type models --verbose
python lama_cleaner/distributed/tests/run_tests.py --type integration --verbose

# 生成覆盖率报告
python lama_cleaner/distributed/tests/run_tests.py --coverage
```

## 依赖

- `pyzmq`: ZeroMQ Python 绑定
- `redis`: Redis 客户端
- `psutil`: 系统信息收集
- `pyyaml`: YAML 配置文件支持

## 状态

当前实现状态：
- ✅ 核心数据模型
- ✅ 基础配置管理
- ✅ 管理器基础结构
- ✅ 工具函数
- ✅ 单元测试和集成测试

待实现功能：
- 🔄 ZeroMQ 通信实现
- 🔄 Redis 状态存储
- 🔄 节点心跳机制
- 🔄 任务调度算法
- 🔄 故障恢复机制
- 🔄 Serverless 集成
- 🔄 监控和日志系统