# 分布式处理模块测试文档

## 测试概述

本测试套件为 Lama Cleaner 分布式处理模块提供全面的测试覆盖，确保代码质量和系统稳定性。

## 测试结构

```
tests/
├── README.md                    # 测试文档
├── conftest.py                  # pytest 配置和 fixtures
├── run_tests.py                 # 测试运行器
├── test_init.py                 # 基础初始化测试
├── test_module_integrity.py     # 模块完整性测试
├── test_integration.py          # 集成测试
├── test_models.py               # 数据模型测试
└── data/                        # 测试数据
    └── sample_config.yaml       # 示例配置文件
```

## 测试分类

### 1. 初始化测试 (`test_init.py`)
- **目的**: 验证模块基础导入和初始化功能
- **覆盖范围**:
  - 模块导入测试
  - 基础功能验证
  - 默认配置检查
  - 数据模型序列化
  - 基础错误处理

### 2. 模块完整性测试 (`test_module_integrity.py`)
- **目的**: 测试模块完整性和边界条件
- **覆盖范围**:
  - 文件存在性检查
  - 依赖关系验证
  - 循环导入防护
  - 错误处理机制
  - 边界条件测试
  - 性能基准测试
  - Mock 依赖测试

### 3. 数据模型测试 (`test_models.py`)
- **目的**: 验证核心数据模型的正确性
- **覆盖范围**:
  - 任务模型功能
  - 节点能力模型
  - 队列配置模型
  - 序列化/反序列化
  - 数据验证

### 4. 集成测试 (`test_integration.py`)
- **目的**: 测试组件间的协作和接口兼容性
- **覆盖范围**:
  - 端到端工作流
  - 组件集成
  - API 兼容性
  - 命名空间管理

## 运行测试

### 使用测试运行器
```bash
# 运行所有初始化测试
python tests/run_tests.py --type init --verbose

# 运行集成测试
python tests/run_tests.py --type integration --verbose

# 运行模型测试
python tests/run_tests.py --type models --verbose

# 运行所有测试
python tests/run_tests.py --type all --verbose

# 生成覆盖率报告
python tests/run_tests.py --type all --coverage
```

### 使用 Makefile
```bash
# 运行初始化测试
make test-init

# 运行模块完整性测试
make test-integrity

# 运行所有测试
make test-all

# 生成覆盖率报告
make test-coverage
```

### 直接使用 pytest
```bash
# 运行特定测试文件
python -m pytest tests/test_init.py -v

# 运行带标记的测试
python -m pytest -m "not slow" -v

# 生成覆盖率报告
python -m pytest --cov=lama_cleaner.distributed --cov-report=html
```

## 测试配置

### pytest 配置 (`pytest.ini`)
- 测试发现规则
- 输出格式配置
- 标记定义
- 覆盖率设置

### 测试 Fixtures (`conftest.py`)
- `test_config`: 测试配置
- `temp_directory`: 临时目录
- `mock_redis`: 模拟 Redis 客户端
- `mock_zmq_context`: 模拟 ZeroMQ 上下文
- `sample_task_data`: 示例任务数据
- `sample_node_data`: 示例节点数据

## 测试策略

### 1. 单元测试
- **范围**: 单个函数或类的测试
- **特点**: 快速执行，隔离性好
- **工具**: unittest, pytest
- **Mock**: 使用 unittest.mock 模拟外部依赖

### 2. 集成测试
- **范围**: 多个组件协作的测试
- **特点**: 验证接口兼容性
- **工具**: pytest
- **环境**: 使用临时配置和数据

### 3. 边界条件测试
- **范围**: 异常输入和极限情况
- **特点**: 提高系统健壮性
- **覆盖**: 空值、大数据、Unicode、错误输入

### 4. 性能测试
- **范围**: 关键操作的性能基准
- **特点**: 确保性能不退化
- **指标**: 执行时间、内存使用

## 测试数据管理

### 测试数据原则
- 使用最小化的测试数据
- 避免依赖外部资源
- 使用临时文件和目录
- 测试后自动清理

### Mock 策略
- 模拟外部依赖（Redis、ZeroMQ）
- 模拟系统调用（GPU 检测、系统信息）
- 保持测试的确定性和可重复性

## 持续集成

### CI/CD 集成
- 自动运行测试套件
- 生成覆盖率报告
- 性能回归检测
- 测试结果通知

### 质量门禁
- 测试通过率 > 95%
- 代码覆盖率 > 80%
- 性能不退化
- 无严重安全漏洞

## 测试最佳实践

### 1. 测试命名
- 使用描述性的测试名称
- 遵循 `test_功能_条件_期望结果` 格式
- 使用中文注释说明测试目的

### 2. 测试组织
- 按功能模块组织测试
- 使用测试类分组相关测试
- 保持测试的独立性

### 3. 断言策略
- 使用具体的断言方法
- 提供有意义的错误消息
- 验证预期行为和边界条件

### 4. 测试维护
- 定期更新测试用例
- 移除过时的测试
- 重构重复的测试代码

## 故障排查

### 常见问题
1. **导入错误**: 检查 Python 路径和依赖
2. **配置错误**: 验证测试配置文件
3. **临时文件**: 确保临时目录权限
4. **Mock 失效**: 检查 Mock 对象设置

### 调试技巧
- 使用 `-v` 参数获得详细输出
- 使用 `--pdb` 进入调试器
- 检查测试日志和错误信息
- 隔离失败的测试用例

## 扩展测试

### 添加新测试
1. 确定测试类型和位置
2. 编写测试用例
3. 更新测试运行器
4. 添加必要的 fixtures
5. 更新文档

### 测试覆盖率
- 定期检查覆盖率报告
- 识别未覆盖的代码路径
- 添加针对性的测试用例
- 保持高质量的测试覆盖

## 新增测试模块

### 5. 能力检测器测试 (`test_capability_detector.py`)
- **目的**: 测试节点硬件能力检测和模型支持检测
- **覆盖范围**:
  - 硬件检测（CPU、内存、GPU）
  - 模型支持检测和验证
  - 跨平台兼容性（Linux、macOS、Windows）
  - 配置文件生成和加载
  - 错误处理和边界条件
  - 性能基准测试

### 测试类别详细说明

#### 硬件检测测试
- **TestHardwareDetector**: 基础硬件检测功能
- **TestCapabilityDetectorCrossPlatform**: 跨平台兼容性
- **TestCapabilityDetectorEdgeCases**: 边界条件和异常情况

#### 模型检测测试
- **TestModelDetector**: 模型支持检测和框架验证
- **TestCapabilityDetectorIntegrationScenarios**: 真实场景集成测试

#### 错误处理测试
- **TestCapabilityDetectorErrorHandling**: 异常情况和错误恢复
- **TestCapabilityDetectorPerformance**: 性能基准和优化验证

### 专用测试工具

#### 测试运行器 (`test_capability_detector_runner.py`)
- 独立的测试验证工具
- 模拟各种硬件环境
- 性能基准测试
- 错误处理验证
- 集成测试验证

```bash
# 运行能力检测器专用测试
python tests/test_capability_detector_runner.py

# 运行特定测试类别
make test-capability
make test-cross-platform
make test-performance
```

## 测试策略更新

### 1. Mock 策略增强
- **硬件模拟**: 使用 unittest.mock 模拟各种硬件配置
- **跨平台测试**: 模拟不同操作系统的系统调用
- **依赖隔离**: 模拟缺失依赖和驱动问题

### 2. 边界条件覆盖
- **极端配置**: 测试零内存、超高配置等边界情况
- **Unicode 支持**: 测试硬件名称中的特殊字符
- **混合环境**: 测试多厂商 GPU 混合配置

### 3. 性能验证
- **检测速度**: 确保硬件检测在合理时间内完成
- **内存使用**: 监控检测过程的内存占用
- **配置生成**: 验证大型配置文件的生成性能

### 4. 真实场景测试
- **游戏 PC**: 中高端消费级配置
- **服务器**: 高性能多 GPU 配置  
- **笔记本**: 移动端中等配置
- **工作站**: 专业级混合配置

## 总结

这个测试套件提供了全面的测试覆盖，确保分布式处理模块的质量和稳定性。通过分层的测试策略、完善的测试工具和持续的质量监控，我们能够及时发现和修复问题，保证系统的可靠性。

新增的能力检测器测试特别关注跨平台兼容性和硬件多样性，确保系统能够在各种环境下正确识别和利用硬件资源。