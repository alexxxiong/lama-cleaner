#!/usr/bin/env python3
"""
分布式处理模块测试运行器

用于运行所有分布式模块相关的测试，包括单元测试和集成测试
"""

import sys
import os
import subprocess
import argparse
from pathlib import Path


def setup_environment():
    """设置测试环境"""
    # 添加项目根目录到 Python 路径
    project_root = Path(__file__).parent.parent.parent.parent
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))
    
    # 设置环境变量
    os.environ['PYTHONPATH'] = str(project_root)
    os.environ['TESTING'] = '1'


def run_tests(test_type='all', verbose=False, coverage=False):
    """运行测试"""
    
    test_dir = Path(__file__).parent
    
    # 构建 pytest 命令
    cmd = ['python', '-m', 'pytest']
    
    if verbose:
        cmd.append('-v')
    
    if coverage:
        cmd.extend(['--cov=lama_cleaner.distributed', '--cov-report=html', '--cov-report=term'])
    
    # 根据测试类型选择测试文件
    if test_type == 'init':
        cmd.extend([
            str(test_dir / 'test_init.py'),
            str(test_dir / 'test_module_integrity.py')
        ])
    elif test_type == 'integration':
        cmd.append(str(test_dir / 'test_integration.py'))
    elif test_type == 'models':
        cmd.append(str(test_dir / 'test_models.py'))
    elif test_type == 'all':
        cmd.append(str(test_dir))
    else:
        print(f"Unknown test type: {test_type}")
        return False
    
    # 添加测试标记
    cmd.extend(['-m', 'not slow'])  # 默认跳过慢速测试
    
    print(f"Running command: {' '.join(cmd)}")
    
    try:
        result = subprocess.run(cmd, cwd=test_dir.parent.parent.parent, check=False)
        return result.returncode == 0
    except Exception as e:
        print(f"Error running tests: {e}")
        return False


def check_dependencies():
    """检查测试依赖"""
    required_packages = ['pytest', 'pytest-cov', 'pytest-mock']
    missing_packages = []
    
    for package in required_packages:
        try:
            __import__(package.replace('-', '_'))
        except ImportError:
            missing_packages.append(package)
    
    if missing_packages:
        print("Missing required packages:")
        for package in missing_packages:
            print(f"  - {package}")
        print("\nInstall with: pip install " + " ".join(missing_packages))
        return False
    
    return True


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='Run distributed module tests')
    parser.add_argument(
        '--type', 
        choices=['all', 'init', 'integration', 'models'],
        default='all',
        help='Type of tests to run'
    )
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Verbose output'
    )
    parser.add_argument(
        '--coverage', '-c',
        action='store_true',
        help='Generate coverage report'
    )
    parser.add_argument(
        '--check-deps',
        action='store_true',
        help='Check test dependencies'
    )
    
    args = parser.parse_args()
    
    if args.check_deps:
        if check_dependencies():
            print("All dependencies are available")
            return 0
        else:
            return 1
    
    # 设置环境
    setup_environment()
    
    # 检查依赖
    if not check_dependencies():
        return 1
    
    # 运行测试
    success = run_tests(
        test_type=args.type,
        verbose=args.verbose,
        coverage=args.coverage
    )
    
    if success:
        print("\n✅ All tests passed!")
        return 0
    else:
        print("\n❌ Some tests failed!")
        return 1


if __name__ == '__main__':
    sys.exit(main())