#!/usr/bin/env python3
"""
日志管理命令行工具

提供日志查询、统计、清理和导出功能。
"""

import argparse
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from lama_cleaner.logging_config import LoggerManager, LoggingConfig


def parse_datetime(date_str: str) -> datetime:
    """解析日期时间字符串"""
    formats = [
        "%Y-%m-%d",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%m-%d %H:%M",
        "%H:%M"
    ]
    
    for fmt in formats:
        try:
            if fmt == "%H:%M":
                # 今天的时间
                today = datetime.now().date()
                time_part = datetime.strptime(date_str, fmt).time()
                return datetime.combine(today, time_part)
            elif fmt == "%m-%d %H:%M":
                # 今年的日期时间
                year = datetime.now().year
                dt = datetime.strptime(f"{year}-{date_str}", "%Y-%m-%d %H:%M")
                return dt
            else:
                return datetime.strptime(date_str, fmt)
        except ValueError:
            continue
            
    raise ValueError(f"无法解析日期时间: {date_str}")


def main():
    parser = argparse.ArgumentParser(description="Lama Cleaner 日志管理工具")
    subparsers = parser.add_subparsers(dest="command", help="可用命令")
    
    # 查询日志命令
    search_parser = subparsers.add_parser("search", help="搜索日志")
    search_parser.add_argument("query", help="搜索关键词")
    search_parser.add_argument("--level", help="日志级别过滤")
    search_parser.add_argument("--module", help="模块名过滤")
    search_parser.add_argument("--start", help="开始时间 (YYYY-MM-DD HH:MM:SS)")
    search_parser.add_argument("--end", help="结束时间 (YYYY-MM-DD HH:MM:SS)")
    search_parser.add_argument("--limit", type=int, default=100, help="结果数量限制")
    search_parser.add_argument("--format", choices=["table", "json"], default="table", help="输出格式")
    
    # 统计信息命令
    stats_parser = subparsers.add_parser("stats", help="显示日志统计信息")
    stats_parser.add_argument("--hours", type=int, default=24, help="统计时间范围（小时）")
    
    # 错误摘要命令
    error_parser = subparsers.add_parser("errors", help="显示错误摘要")
    error_parser.add_argument("--hours", type=int, default=24, help="统计时间范围（小时）")
    
    # 文件信息命令
    files_parser = subparsers.add_parser("files", help="显示日志文件信息")
    
    # 清理命令
    cleanup_parser = subparsers.add_parser("cleanup", help="清理旧日志")
    cleanup_parser.add_argument("--days", type=int, default=30, help="保留天数")
    cleanup_parser.add_argument("--dry-run", action="store_true", help="仅显示将要删除的文件")
    
    # 导出命令
    export_parser = subparsers.add_parser("export", help="导出日志")
    export_parser.add_argument("output", help="输出文件路径")
    export_parser.add_argument("--start", help="开始时间")
    export_parser.add_argument("--end", help="结束时间")
    export_parser.add_argument("--format", choices=["zip", "json"], default="zip", help="导出格式")
    
    # 备份命令
    backup_parser = subparsers.add_parser("backup", help="备份结构化日志数据库")
    backup_parser.add_argument("output", help="备份文件路径")
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return
        
    # 初始化日志管理器
    manager = LoggerManager()
    
    # 尝试加载配置
    config_path = "config/logging_config.json"
    if Path(config_path).exists():
        config = manager.load_config(config_path)
        manager.setup_logging(config=config)
    else:
        manager.setup_logging(enable_file_logging=True)
        
    try:
        if args.command == "search":
            handle_search(manager, args)
        elif args.command == "stats":
            handle_stats(manager, args)
        elif args.command == "errors":
            handle_errors(manager, args)
        elif args.command == "files":
            handle_files(manager, args)
        elif args.command == "cleanup":
            handle_cleanup(manager, args)
        elif args.command == "export":
            handle_export(manager, args)
        elif args.command == "backup":
            handle_backup(manager, args)
            
    except Exception as e:
        print(f"❌ 执行命令时发生错误: {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        manager.shutdown()


def handle_search(manager: LoggerManager, args):
    """处理搜索命令"""
    filters = {}
    
    if args.level:
        filters['level'] = args.level.upper()
    if args.module:
        filters['module'] = args.module
    if args.start:
        filters['start_time'] = parse_datetime(args.start)
    if args.end:
        filters['end_time'] = parse_datetime(args.end)
    if args.limit:
        filters['limit'] = args.limit
        
    results = manager.search_logs(args.query, **filters)
    
    if not results:
        print("🔍 未找到匹配的日志记录")
        return
        
    if args.format == "json":
        print(json.dumps(results, ensure_ascii=False, indent=2, default=str))
    else:
        print(f"🔍 找到 {len(results)} 条匹配记录:\n")
        for i, log in enumerate(results, 1):
            print(f"{i:3d}. [{log['level']}] {log['timestamp']}")
            print(f"     模块: {log['module']}")
            print(f"     消息: {log['message']}")
            if log.get('extra_data'):
                print(f"     额外: {json.dumps(log['extra_data'], ensure_ascii=False)}")
            print()


def handle_stats(manager: LoggerManager, args):
    """处理统计命令"""
    stats = manager.get_log_statistics(args.hours)
    
    if not stats:
        print("📊 暂无统计数据")
        return
        
    print(f"📊 日志统计信息 (最近 {args.hours} 小时)")
    print("=" * 50)
    print(f"总记录数: {stats.get('total_entries', 0)}")
    
    print("\n📈 级别分布:")
    for level, count in stats.get('level_distribution', {}).items():
        print(f"  {level}: {count}")
        
    print("\n🏗️ 模块分布:")
    for module, count in sorted(stats.get('module_distribution', {}).items(), 
                               key=lambda x: x[1], reverse=True)[:10]:
        print(f"  {module}: {count}")


def handle_errors(manager: LoggerManager, args):
    """处理错误摘要命令"""
    summary = manager.get_error_summary(args.hours)
    
    if not summary:
        print("✅ 暂无错误记录")
        return
        
    print(f"❌ 错误摘要 ({summary.get('time_range', '')})")
    print("=" * 50)
    print(f"总错误数: {summary.get('total_errors', 0)}")
    print(f"唯一错误: {summary.get('unique_errors', 0)}")
    
    print("\n🔥 错误详情:")
    for message, info in summary.get('error_groups', {}).items():
        print(f"\n  错误: {message}")
        print(f"  次数: {info['count']}")
        print(f"  模块: {', '.join(info['modules'])}")
        print(f"  首次: {info['first_occurrence']}")
        print(f"  最近: {info['last_occurrence']}")


def handle_files(manager: LoggerManager, args):
    """处理文件信息命令"""
    files = manager.get_log_files_info()
    
    if not files:
        print("📁 暂无日志文件")
        return
        
    print("📁 日志文件信息")
    print("=" * 70)
    print(f"{'文件名':<30} {'大小(MB)':<10} {'修改时间':<20} {'压缩':<6}")
    print("-" * 70)
    
    total_size = 0
    for file_info in files:
        compressed = "✓" if file_info['compressed'] else "✗"
        print(f"{file_info['name']:<30} {file_info['size_mb']:<10.2f} "
              f"{file_info['modified'].strftime('%Y-%m-%d %H:%M'):<20} {compressed:<6}")
        total_size += file_info['size_mb']
        
    print("-" * 70)
    print(f"总计: {len(files)} 个文件, {total_size:.2f} MB")


def handle_cleanup(manager: LoggerManager, args):
    """处理清理命令"""
    if args.dry_run:
        print(f"🧹 模拟清理 (保留 {args.days} 天)")
        # 这里可以添加模拟清理的逻辑
        print("注意: 这是模拟运行，实际文件不会被删除")
    else:
        print(f"🧹 开始清理日志 (保留 {args.days} 天)")
        
        # 清理文件日志
        result = manager.manual_cleanup()
        print(f"文件清理完成: 删除了 {result.get('deleted', 0)} 个文件")
        
        # 清理结构化日志
        deleted_entries = manager.cleanup_structured_logs(args.days)
        print(f"数据库清理完成: 删除了 {deleted_entries} 条记录")


def handle_export(manager: LoggerManager, args):
    """处理导出命令"""
    start_time = parse_datetime(args.start) if args.start else None
    end_time = parse_datetime(args.end) if args.end else None
    
    print(f"📦 开始导出日志到: {args.output}")
    
    if args.format == "json":
        success = manager.export_structured_logs(args.output, start_time, end_time)
    else:
        date_range = (start_time, end_time) if start_time and end_time else None
        success = manager.export_logs(args.output, date_range)
        
    if success:
        print("✅ 导出完成")
    else:
        print("❌ 导出失败")
        sys.exit(1)


def handle_backup(manager: LoggerManager, args):
    """处理备份命令"""
    print(f"💾 开始备份结构化日志数据库到: {args.output}")
    
    success = manager.backup_structured_logs(args.output)
    
    if success:
        print("✅ 备份完成")
    else:
        print("❌ 备份失败")
        sys.exit(1)


if __name__ == "__main__":
    main()