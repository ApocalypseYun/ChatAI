#!/usr/bin/env python3
"""
日志管理工具

该脚本提供以下功能：
1. 查看日志文件列表和大小
2. 清理过期日志
3. 日志统计分析
4. 查看日志尾部
"""

import argparse
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, List


class LogManager:
    """日志管理器"""
    
    def __init__(self, config_path: str = "config/logging_config.json"):
        """
        初始化日志管理器
        
        Args:
            config_path: 日志配置文件路径
        """
        self.config_path = Path(config_path)
        self.config = self._load_config()
        self.log_dir = Path(self.config.get("log_dir", "logs"))
        
    def _load_config(self) -> Dict[str, Any]:
        """加载日志配置"""
        if self.config_path.exists():
            with open(self.config_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {}
    
    def list_logs(self) -> List[Dict[str, Any]]:
        """列出所有日志文件"""
        if not self.log_dir.exists():
            print(f"日志目录不存在: {self.log_dir}")
            return []
        
        log_files = []
        for log_file in self.log_dir.glob("*.log*"):
            stat = log_file.stat()
            log_files.append({
                "file": str(log_file),
                "size": stat.st_size,
                "size_mb": round(stat.st_size / 1024 / 1024, 2),
                "modified": datetime.fromtimestamp(stat.st_mtime),
                "type": self._get_log_type(log_file.name)
            })
        
        return sorted(log_files, key=lambda x: x["modified"], reverse=True)
    
    def _get_log_type(self, filename: str) -> str:
        """根据文件名获取日志类型"""
        if "error" in filename:
            return "错误日志"
        elif "access" in filename:
            return "访问日志"
        elif "api" in filename:
            return "API日志"
        elif "all" in filename:
            return "全量日志"
        else:
            return "其他日志"
    
    def show_stats(self):
        """显示日志统计信息"""
        log_files = self.list_logs()
        
        if not log_files:
            print("没有找到日志文件")
            return
        
        total_size = sum(f["size"] for f in log_files)
        total_files = len(log_files)
        
        # 按类型统计
        type_stats = {}
        for f in log_files:
            log_type = f["type"]
            if log_type not in type_stats:
                type_stats[log_type] = {"count": 0, "size": 0}
            type_stats[log_type]["count"] += 1
            type_stats[log_type]["size"] += f["size"]
        
        print("=" * 60)
        print("日志统计信息")
        print("=" * 60)
        print(f"总文件数: {total_files}")
        print(f"总大小: {round(total_size / 1024 / 1024, 2)} MB")
        print(f"日志目录: {self.log_dir}")
        print()
        
        print("按类型统计:")
        for log_type, stats in type_stats.items():
            size_mb = round(stats["size"] / 1024 / 1024, 2)
            print(f"  {log_type}: {stats['count']} 个文件, {size_mb} MB")
        print()
        
        print("最近的日志文件:")
        for f in log_files[:10]:  # 显示最近的10个文件
            print(f"  {f['file']} ({f['size_mb']} MB, {f['modified'].strftime('%Y-%m-%d %H:%M:%S')})")
    
    def cleanup(self, days: int = None, dry_run: bool = False):
        """
        清理过期日志
        
        Args:
            days: 保留天数，默认使用配置文件中的值
            dry_run: 仅显示将要删除的文件，不实际删除
        """
        if days is None:
            days = self.config.get("retention_days", 30)
        
        cutoff_date = datetime.now() - timedelta(days=days)
        log_files = self.list_logs()
        
        files_to_delete = [
            f for f in log_files 
            if f["modified"] < cutoff_date and not f["file"].endswith(".log")
        ]
        
        if not files_to_delete:
            print(f"没有找到超过 {days} 天的日志文件")
            return
        
        total_size = sum(f["size"] for f in files_to_delete)
        print(f"找到 {len(files_to_delete)} 个过期日志文件 (总计 {round(total_size / 1024 / 1024, 2)} MB)")
        
        if dry_run:
            print("预览模式 - 以下文件将被删除:")
            for f in files_to_delete:
                print(f"  {f['file']} ({f['size_mb']} MB)")
            return
        
        # 确认删除
        response = input("确认删除这些文件？(y/N): ")
        if response.lower() != 'y':
            print("操作已取消")
            return
        
        deleted_count = 0
        for f in files_to_delete:
            try:
                Path(f["file"]).unlink()
                print(f"已删除: {f['file']}")
                deleted_count += 1
            except Exception as e:
                print(f"删除失败 {f['file']}: {e}")
        
        print(f"成功删除 {deleted_count} 个文件")
    
    def tail_log(self, log_type: str = "all", lines: int = 50):
        """
        查看日志尾部
        
        Args:
            log_type: 日志类型 (all, error, access, api)
            lines: 显示行数
        """
        log_files = {
            "all": "chatai_all.log",
            "error": "chatai_error.log", 
            "access": "chatai_access.log",
            "api": "chatai_api.log"
        }
        
        if log_type not in log_files:
            print(f"无效的日志类型: {log_type}")
            print(f"可用的类型: {', '.join(log_files.keys())}")
            return
        
        log_file = self.log_dir / log_files[log_type]
        if not log_file.exists():
            print(f"日志文件不存在: {log_file}")
            return
        
        try:
            with open(log_file, 'r', encoding='utf-8') as f:
                all_lines = f.readlines()
                tail_lines = all_lines[-lines:] if len(all_lines) > lines else all_lines
                
                print(f"日志文件: {log_file}")
                print(f"显示最后 {len(tail_lines)} 行:")
                print("=" * 80)
                
                for line in tail_lines:
                    print(line.rstrip())
        
        except Exception as e:
            print(f"读取日志文件失败: {e}")


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description="ChatAI 日志管理工具")
    subparsers = parser.add_subparsers(dest="command", help="可用命令")
    
    # 列出日志文件
    list_parser = subparsers.add_parser("list", help="列出日志文件")
    
    # 显示统计信息
    stats_parser = subparsers.add_parser("stats", help="显示日志统计信息")
    
    # 清理日志
    cleanup_parser = subparsers.add_parser("cleanup", help="清理过期日志")
    cleanup_parser.add_argument("--days", type=int, help="保留天数")
    cleanup_parser.add_argument("--dry-run", action="store_true", help="仅预览，不实际删除")
    
    # 查看日志尾部
    tail_parser = subparsers.add_parser("tail", help="查看日志尾部")
    tail_parser.add_argument("--type", default="all", choices=["all", "error", "access", "api"], help="日志类型")
    tail_parser.add_argument("--lines", type=int, default=50, help="显示行数")
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return
    
    # 初始化日志管理器
    log_manager = LogManager()
    
    # 执行相应命令
    try:
        if args.command == "list":
            log_files = log_manager.list_logs()
            if log_files:
                print(f"{'文件名':<40} {'大小(MB)':<10} {'类型':<10} {'修改时间':<20}")
                print("-" * 80)
                for f in log_files:
                    filename = Path(f["file"]).name
                    print(f"{filename:<40} {f['size_mb']:<10.2f} {f['type']:<10} {f['modified'].strftime('%Y-%m-%d %H:%M:%S')}")
            else:
                print("没有找到日志文件")
        
        elif args.command == "stats":
            log_manager.show_stats()
        
        elif args.command == "cleanup":
            log_manager.cleanup(args.days, args.dry_run)
        
        elif args.command == "tail":
            log_manager.tail_log(args.type, args.lines)
    
    except KeyboardInterrupt:
        print("\n操作已取消")
    except Exception as e:
        print(f"执行命令时发生错误: {e}")


if __name__ == "__main__":
    main() 