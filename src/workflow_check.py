"""
工作流检查模块
"""

from typing import List, Dict, Any

def identify_intent(messages: str, history: List[Dict[str, Any]], language: str) -> str:
    """
    识别意图
    """
    return "intent"

def identify_stage(intent: str, messages: List[str], history: List[Dict[str, Any]], language: str) -> str:
    """
    识别阶段
    """
    return "stage"
