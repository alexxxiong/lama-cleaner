# 分布式处理模块 Makefile

.PHONY: test test-init test-integration test-models test-all test-coverage clean help

# 默认目标
help:
	@echo "Available targets:"
	@echo "  test-init        - Run initialization tests"
	@echo "  test-integrity   - Run module integrity tests"
	@echo "  test-integration - Run integration tests"  
	@echo "  test-models      - Run model tests"
	@echo "  test-all         - Run all tests"
	@echo "  test-coverage    - Run tests with coverage"
	@echo "  test-fast        - Run fast tests only"
	@echo "  clean            - Clean test artifacts"
	@echo "  install-deps     - Install test dependencies"
	@echo "  check-deps       - Check test dependencies"

# 安装测试依赖
install-deps:
	pip install pytest pytest-cov pytest-mock pytest-asyncio

# 检查依赖
check-deps:
	python tests/run_tests.py --check-deps

# 运行初始化测试
test-init:
	python tests/run_tests.py --type init --verbose

# 运行模块完整性测试
test-integrity:
	python -m pytest tests/test_module_integrity.py -v

# 运行集成测试
test-integration:
	python tests/run_tests.py --type integration --verbose

# 运行模型测试
test-models:
	python tests/run_tests.py --type models --verbose

# 运行所有测试
test-all:
	python tests/run_tests.py --type all --verbose

# 运行测试并生成覆盖率报告
test-coverage:
	python tests/run_tests.py --type all --verbose --coverage

# 运行快速测试（跳过慢速测试）
test-fast:
	python -m pytest tests/ -v -m "not slow"

# 运行单个测试文件
test-file:
	@if [ -z "$(FILE)" ]; then \
		echo "Usage: make test-file FILE=test_filename.py"; \
	else \
		python -m pytest tests/$(FILE) -v; \
	fi

# 运行能力检测器测试
test-capability:
	python -m pytest tests/test_capability_detector.py -v

# 运行跨平台测试
test-cross-platform:
	python -m pytest tests/test_capability_detector.py::TestCapabilityDetectorCrossPlatform -v

# 运行性能测试
test-performance:
	python -m pytest tests/test_capability_detector.py::TestCapabilityDetectorPerformance -v

# 运行状态管理器测试
test-state:
	python tests/run_tests.py --type state --verbose

# 运行状态管理器集成测试
test-state-integration:
	python -m pytest tests/test_state_manager_integration.py -v

# 运行通信集成测试
test-communication:
	python tests/run_tests.py --type communication --verbose

# 运行 Mock 完整性测试
test-mock:
	python tests/run_tests.py --type mock --verbose

# 清理测试产生的文件
clean:
	find . -type f -name "*.pyc" -delete
	find . -type d -name "__pycache__" -delete
	find . -type d -name ".pytest_cache" -exec rm -rf {} +
	find . -type f -name ".coverage" -delete
	find . -type d -name "htmlcov" -exec rm -rf {} +
	find . -type d -name ".tox" -exec rm -rf {} +

# 运行代码质量检查
lint:
	python -m flake8 . --count --select=E9,F63,F7,F82 --show-source --statistics
	python -m flake8 . --count --exit-zero --max-complexity=10 --max-line-length=127 --statistics

# 格式化代码
format:
	python -m black . --line-length=100
	python -m isort . --profile black

# 类型检查
typecheck:
	python -m mypy . --ignore-missing-imports

# 完整的代码质量检查
quality: lint typecheck
	@echo "Code quality checks completed"

# 持续集成测试
ci: install-deps test-coverage quality
	@echo "CI pipeline completed"