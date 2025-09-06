#!/usr/bin/env python3
"""
调试启动脚本 - 使用 uv 启动分布式系统组件
"""

import subprocess
import time
import sys
import os

def run_command(cmd, name):
    """运行命令并返回进程"""
    print(f"启动 {name}: {cmd}")
    process = subprocess.Popen(cmd, shell=True)
    return process

def main():
    print("=" * 60)
    print("Lama Cleaner 分布式系统调试启动")
    print("=" * 60)
    
    processes = []
    
    # 1. 启动调度器
    print("\n1. 启动调度器...")
    scheduler_cmd = "uv run python -m lama_cleaner.distributed.scheduler"
    scheduler_process = run_command(scheduler_cmd, "调度器")
    processes.append(("调度器", scheduler_process))
    time.sleep(2)  # 等待调度器启动
    
    # 2. 启动工作节点
    print("\n2. 启动工作节点...")
    worker_cmd = "uv run python -m lama_cleaner.distributed.worker_node"
    worker_process = run_command(worker_cmd, "工作节点")
    processes.append(("工作节点", worker_process))
    time.sleep(2)  # 等待工作节点启动
    
    # 3. 启动 Web 服务
    print("\n3. 启动 Web 服务...")
    web_cmd = "uv run python -m lama_cleaner.server --distributed"
    web_process = run_command(web_cmd, "Web 服务")
    processes.append(("Web 服务", web_process))
    
    print("\n" + "=" * 60)
    print("所有服务已启动")
    print("=" * 60)
    print("\n服务地址:")
    print("  - Web 界面: http://localhost:8080")
    print("  - 调度器: localhost:5555")
    print("  - 工作节点: localhost:5556")
    print("\n按 Ctrl+C 停止所有服务")
    print("=" * 60)
    
    try:
        # 等待进程
        while True:
            time.sleep(1)
            # 检查进程状态
            for name, proc in processes:
                if proc.poll() is not None:
                    print(f"\n警告: {name} 已退出，退出代码: {proc.returncode}")
                    
    except KeyboardInterrupt:
        print("\n\n正在停止所有服务...")
        for name, proc in processes:
            print(f"停止 {name}...")
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                print(f"强制停止 {name}...")
                proc.kill()
        print("所有服务已停止")

if __name__ == "__main__":
    main()