"""
日志配置模块

该模块提供完整的日志配置功能，包括：
- 文件日志保存
- 日志轮转
- 不同级别日志分离
- 日志清理策略
- 结构化日志格式
"""

import logging
import logging.handlers
import os
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, Optional
import glob


class JSONFormatter(logging.Formatter):
    """JSON格式的日志格式化器"""
    
    def format(self, record):
        """格式化日志记录为JSON格式"""
        # 创建日志记录的副本，避免修改原始记录
        record_dict = record.__dict__.copy()
        
        log_entry = {
            'timestamp': datetime.fromtimestamp(record.created).isoformat(),
            'level': record.levelname,
            'logger': record.name,
            'message': record.getMessage(),
            'module': record.module,
            'function': record.funcName,
            'line': record.lineno,
            'thread_id': record.thread,
            'process_id': record.process
        }
        
        # 添加异常信息
        if record.exc_info:
            log_entry['exception'] = self.formatException(record.exc_info)
        
        # 添加额外的字段（避免覆盖基础字段）
        extra_fields = ['session_id', 'user_id', 'request_id', 'api_name', 'order_no', 'activity', 'error_type']
        for field in extra_fields:
            if hasattr(record, field) and field not in log_entry:
                log_entry[field] = getattr(record, field)
        
        return json.dumps(log_entry, ensure_ascii=False)


class LogConfig:
    """日志配置类"""
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        初始化日志配置
        
        Args:
            config: 日志配置字典
        """
        self.config = config or self._get_default_config()
        self.log_dir = Path(self.config.get('log_dir', 'logs'))
        self.log_dir.mkdir(exist_ok=True)
        
        # 设置各级别日志文件路径
        self.log_files = {
            'all': self.log_dir / 'chatai_all.log',
            'error': self.log_dir / 'chatai_error.log',
            'access': self.log_dir / 'chatai_access.log',
            'api': self.log_dir / 'chatai_api.log'
        }
        
        self._setup_logging()
        self._setup_cleanup_task()
    
    def _get_default_config(self) -> Dict[str, Any]:
        """获取默认配置"""
        return {
            'log_dir': 'logs',
            'level': 'INFO',
            'console_output': True,
            'file_output': True,
            'json_format': True,
            'max_file_size': '10MB',
            'backup_count': 10,
            'retention_days': 30,
            'separate_error_log': True,
            'loggers': {
                'chatai-api': {
                    'level': 'INFO',
                    'handlers': ['console', 'file_all', 'file_error']
                },
                'chatai-access': {
                    'level': 'INFO',
                    'handlers': ['file_access']
                },
                'chatai-api-calls': {
                    'level': 'INFO',
                    'handlers': ['file_api']
                }
            }
        }
    
    def _setup_logging(self):
        """设置日志配置"""
        # 清除现有的处理器
        root_logger = logging.getLogger()
        for handler in root_logger.handlers[:]:
            root_logger.removeHandler(handler)
        
        # 设置根日志级别
        root_logger.setLevel(logging.DEBUG)
        
        # 创建格式化器
        if self.config.get('json_format', True):
            formatter = JSONFormatter()
        else:
            formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
        
        # 创建处理器
        handlers = {}
        
        # 控制台处理器
        if self.config.get('console_output', True):
            console_handler = logging.StreamHandler()
            console_handler.setLevel(getattr(logging, self.config.get('level', 'INFO')))
            if not self.config.get('json_format', True):
                console_handler.setFormatter(formatter)
            else:
                # 控制台使用简单格式
                console_formatter = logging.Formatter(
                    '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
                )
                console_handler.setFormatter(console_formatter)
            handlers['console'] = console_handler
        
        # 文件处理器
        if self.config.get('file_output', True):
            # 全量日志文件
            file_all_handler = self._create_rotating_file_handler(
                self.log_files['all'], logging.DEBUG
            )
            file_all_handler.setFormatter(formatter)
            handlers['file_all'] = file_all_handler
            
            # 错误日志文件
            if self.config.get('separate_error_log', True):
                file_error_handler = self._create_rotating_file_handler(
                    self.log_files['error'], logging.ERROR
                )
                file_error_handler.setFormatter(formatter)
                handlers['file_error'] = file_error_handler
            
            # 访问日志文件
            file_access_handler = self._create_rotating_file_handler(
                self.log_files['access'], logging.INFO
            )
            file_access_handler.setFormatter(formatter)
            handlers['file_access'] = file_access_handler
            
            # API调用日志文件
            file_api_handler = self._create_rotating_file_handler(
                self.log_files['api'], logging.INFO
            )
            file_api_handler.setFormatter(formatter)
            handlers['file_api'] = file_api_handler
        
        # 配置特定的logger
        for logger_name, logger_config in self.config.get('loggers', {}).items():
            logger = logging.getLogger(logger_name)
            logger.setLevel(getattr(logging, logger_config.get('level', 'INFO')))
            
            # 清除现有处理器
            for handler in logger.handlers[:]:
                logger.removeHandler(handler)
            
            # 添加指定的处理器
            for handler_name in logger_config.get('handlers', []):
                if handler_name in handlers:
                    logger.addHandler(handlers[handler_name])
            
            # 防止日志传播到根logger
            logger.propagate = False
    
    def _create_rotating_file_handler(self, filename: Path, level: int):
        """创建轮转文件处理器"""
        max_bytes = self._parse_size(self.config.get('max_file_size', '10MB'))
        backup_count = self.config.get('backup_count', 10)
        
        handler = logging.handlers.RotatingFileHandler(
            filename=filename,
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding='utf-8'
        )
        handler.setLevel(level)
        return handler
    
    def _parse_size(self, size_str: str) -> int:
        """解析大小字符串，返回字节数"""
        size_str = size_str.upper().strip()
        
        if size_str.endswith('KB'):
            return int(size_str[:-2]) * 1024
        elif size_str.endswith('MB'):
            return int(size_str[:-2]) * 1024 * 1024
        elif size_str.endswith('GB'):
            return int(size_str[:-2]) * 1024 * 1024 * 1024
        else:
            return int(size_str)
    
    def _setup_cleanup_task(self):
        """设置日志清理任务"""
        retention_days = self.config.get('retention_days', 30)
        if retention_days > 0:
            self._cleanup_old_logs(retention_days)
    
    def _cleanup_old_logs(self, retention_days: int):
        """清理过期的日志文件"""
        cutoff_date = datetime.now() - timedelta(days=retention_days)
        
        # 清理轮转的日志文件
        for log_file in self.log_files.values():
            pattern = f"{log_file}.*"
            for old_file in glob.glob(pattern):
                try:
                    file_path = Path(old_file)
                    if file_path.stat().st_mtime < cutoff_date.timestamp():
                        file_path.unlink()
                        print(f"已删除过期日志文件: {old_file}")
                except Exception as e:
                    print(f"删除日志文件失败 {old_file}: {e}")
    
    def get_logger(self, name: str) -> logging.Logger:
        """获取指定名称的logger"""
        return logging.getLogger(name)
    
    def log_request(self, request_info: Dict[str, Any]):
        """记录请求日志"""
        access_logger = logging.getLogger('chatai-access')
        access_logger.info("请求处理", extra=request_info)
    
    def log_api_call(self, api_info: Dict[str, Any]):
        """记录API调用日志"""
        api_logger = logging.getLogger('chatai-api-calls')
        api_logger.info("API调用", extra=api_info)


# 全局日志配置实例
_log_config = None


def init_logging(config: Optional[Dict[str, Any]] = None) -> LogConfig:
    """
    初始化日志配置
    
    Args:
        config: 日志配置字典
        
    Returns:
        LogConfig: 日志配置实例
    """
    global _log_config
    _log_config = LogConfig(config)
    return _log_config


def get_logger(name: str) -> logging.Logger:
    """
    获取logger实例
    
    Args:
        name: logger名称
        
    Returns:
        logging.Logger: logger实例
    """
    if _log_config is None:
        init_logging()
    return _log_config.get_logger(name)


def log_request(session_id: str, user_id: str = None, **kwargs):
    """
    记录请求日志
    
    Args:
        session_id: 会话ID
        user_id: 用户ID
        **kwargs: 其他请求信息
    """
    if _log_config is None:
        init_logging()
    
    request_info = {
        'session_id': session_id,
        'user_id': user_id,
        **kwargs
    }
    _log_config.log_request(request_info)


def log_api_call(api_name: str, session_id: str = None, **kwargs):
    """
    记录API调用日志
    
    Args:
        api_name: API名称
        session_id: 会话ID
        **kwargs: 其他API调用信息
    """
    if _log_config is None:
        init_logging()
    
    api_info = {
        'api_name': api_name,
        'session_id': session_id,
        **kwargs
    }
    _log_config.log_api_call(api_info)


def cleanup_logs(retention_days: int = 30):
    """
    手动清理过期日志
    
    Args:
        retention_days: 保留天数
    """
    if _log_config is None:
        init_logging()
    _log_config._cleanup_old_logs(retention_days) 