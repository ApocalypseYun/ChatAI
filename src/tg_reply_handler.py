import pandas as pd
import os
from typing import Dict, Optional, Tuple
from src.config import get_message_by_language
from src.logging_config import get_logger

logger = get_logger("chatai-api")

class TGReplyHandler:
    """处理TG工作人员回复的类"""
    
    def __init__(self):
        self.reply_mapping = {}
        self.load_reply_mapping()
    
    def load_reply_mapping(self):
        """从CSV文件加载回复话术映射"""
        try:
            csv_path = "/Users/liuguanzhong/Desktop/Code/ChatAI/回复话术&三方回复总计.csv"
            if os.path.exists(csv_path):
                df = pd.read_csv(csv_path)
                
                # 构建映射字典：{三方回复: {语言: 文本}}
                for _, row in df.iterrows():
                    tg_reply_raw = row.get('对应三方回复', '')
                    # 先检查是否为NaN，再进行strip操作
                    if pd.notna(tg_reply_raw):
                        tg_reply = str(tg_reply_raw).strip()
                        if tg_reply:  # 确保不是空字符串
                            category_raw = row.get('所属类别', '')
                            category = str(category_raw).strip() if pd.notna(category_raw) else ''
                            
                            # 构建多语言回复
                            replies = {}
                            for lang in ['zh', 'en', 'tl']:
                                if lang in row and pd.notna(row[lang]):
                                    replies[lang] = str(row[lang]).strip()
                            
                            if replies:  # 只有当有回复内容时才添加
                                self.reply_mapping[tg_reply] = {
                                    'category': category,
                                    'replies': replies
                                }
                
                logger.info(f"成功加载{len(self.reply_mapping)}条TG回复映射", extra={
                    'loaded_replies': list(self.reply_mapping.keys())
                })
            else:
                logger.warning(f"TG回复话术文件不存在: {csv_path}")
                
        except Exception as e:
            logger.error(f"加载TG回复话术失败: {e}", exc_info=True)
    
    def match_tg_reply(self, tg_message: str) -> Optional[Dict]:
        """
        匹配TG工作人员的回复
        
        Args:
            tg_message: TG工作人员发送的消息内容
            
        Returns:
            Dict: 包含匹配结果的字典，如果没有匹配则返回None
            {
                'tg_reply_type': str,  # 匹配到的三方回复类型
                'category': str,       # 所属类别
                'replies': Dict[str, str]  # 多语言回复内容
            }
        """
        if not tg_message:
            return None
            
        tg_message = tg_message.strip()
        
        # 精确匹配
        if tg_message in self.reply_mapping:
            result = self.reply_mapping[tg_message].copy()
            result['tg_reply_type'] = tg_message
            logger.info(f"精确匹配TG回复: {tg_message}")
            return result
        
        # 模糊匹配（包含关键词）
        for tg_reply, mapping_info in self.reply_mapping.items():
            if tg_reply in tg_message or tg_message in tg_reply:
                result = mapping_info.copy()
                result['tg_reply_type'] = tg_reply
                logger.info(f"模糊匹配TG回复: {tg_message} -> {tg_reply}")
                return result
        
        logger.warning(f"未找到匹配的TG回复: {tg_message}")
        return None
    
    def get_user_reply(self, tg_message: str, language: str = "zh") -> Optional[str]:
        """
        根据TG回复获取对应的用户回复
        
        Args:
            tg_message: TG工作人员发送的消息内容
            language: 目标语言
            
        Returns:
            str: 对应语言的用户回复文本，如果没有找到则返回None
        """
        match_result = self.match_tg_reply(tg_message)
        if not match_result:
            return None
        
        replies = match_result.get('replies', {})
        
        # 优先返回指定语言的回复
        if language in replies:
            return replies[language]
        
        # 降级到中文
        if 'zh' in replies:
            return replies['zh']
        
        # 降级到英文
        if 'en' in replies:
            return replies['en']
        
        # 返回任何可用的语言
        if replies:
            return list(replies.values())[0]
        
        return None
    
    def get_business_category(self, tg_message: str) -> Optional[str]:
        """
        根据TG回复获取业务类别
        
        Args:
            tg_message: TG工作人员发送的消息内容
            
        Returns:
            str: 业务类别（充值/提现/通用）
        """
        match_result = self.match_tg_reply(tg_message)
        if match_result:
            return match_result.get('category')
        return None
    
    def get_all_tg_reply_types(self) -> Dict[str, str]:
        """
        获取所有的TG回复类型及其对应的业务类别
        
        Returns:
            Dict[str, str]: {TG回复类型: 业务类别}
        """
        return {tg_reply: info['category'] for tg_reply, info in self.reply_mapping.items()}


# 全局实例
tg_reply_handler = TGReplyHandler()


def handle_tg_staff_reply(tg_message: str, language: str = "zh", 
                         business_type: str = "", order_id: str = "") -> Dict:
    """
    处理TG工作人员回复
    
    Args:
        tg_message: TG工作人员发送的消息内容
        language: 用户语言
        business_type: 业务类型 (S001/S002等)
        order_id: 订单号
        
    Returns:
        Dict: 处理结果
        {
            'matched': bool,           # 是否匹配成功
            'tg_reply_type': str,      # TG回复类型
            'category': str,           # 业务类别
            'user_reply': str,         # 用户回复文本
            'next_action': str,        # 下一步操作 (finish/continue/transfer)
            'stage': str              # 响应阶段
        }
    """
    result = {
        'matched': False,
        'tg_reply_type': '',
        'category': '',
        'user_reply': '',
        'next_action': 'finish',
        'stage': 'finish'
    }
    
    try:
        # 匹配TG回复
        match_result = tg_reply_handler.match_tg_reply(tg_message)
        if not match_result:
            # 未匹配到，使用默认回复
            result['user_reply'] = get_message_by_language({
                "zh": "我们已收到第三方的回复，正在为您处理相关事宜。",
                "en": "We have received a response from the third party and are handling your request accordingly.",
                "th": "เราได้รับการตอบกลับจากบุคคลที่สามและกำลังดำเนินการตามคำขอของคุณ",
                "tl": "Natanggap na namin ang tugon mula sa third party at pinoproseso ang inyong request.",
                "ja": "第三者からの返答を受け取り、お客様のご要求に応じて対応しております。"
            }, language)
            return result
        
        result['matched'] = True
        result['tg_reply_type'] = match_result['tg_reply_type']
        result['category'] = match_result['category']
        
        # 获取用户回复文本
        user_reply = tg_reply_handler.get_user_reply(tg_message, language)
        if user_reply:
            result['user_reply'] = user_reply
        
        # 根据TG回复类型确定下一步操作
        result['next_action'], result['stage'] = _determine_next_action(
            match_result['tg_reply_type'], 
            match_result['category'],
            business_type
        )
        
        logger.info(f"成功处理TG回复", extra={
            'tg_message': tg_message[:100],
            'tg_reply_type': result['tg_reply_type'],
            'category': result['category'],
            'next_action': result['next_action'],
            'language': language,
            'business_type': business_type
        })
        
    except Exception as e:
        logger.error(f"处理TG回复失败: {e}", extra={
            'tg_message': tg_message,
            'language': language,
            'business_type': business_type
        }, exc_info=True)
        
        # 错误情况下的默认回复
        result['user_reply'] = get_message_by_language({
            "zh": "系统处理中遇到问题，已为您转接人工客服。",
            "en": "We encountered an issue while processing. You have been transferred to customer service.",
            "th": "เราประสบปัญหาขณะดำเนินการ คุณได้ถูกโอนไปยังฝ่ายบริการลูกค้าแล้ว",
            "tl": "May naranasan kaming problema habang nagpoproseso. Na-transfer na kayo sa customer service.",
            "ja": "処理中に問題が発生しました。カスタマーサービスに転送されました。"
        }, language)
        result['next_action'] = 'transfer'
    
    return result


def _determine_next_action(tg_reply_type: str, category: str, business_type: str) -> Tuple[str, str]:
    """
    根据TG回复类型确定下一步操作
    
    Args:
        tg_reply_type: TG回复类型
        category: 业务类别
        business_type: 业务类型
        
    Returns:
        Tuple[str, str]: (next_action, stage)
    """
    # 需要继续等待的情况
    continue_keywords = [
        "提现处理中", "正在处理中，已加急", "等待第三方支付"
    ]
    
    # 需要用户提供更多信息的情况
    user_input_keywords = [
        "提供转账人信息", "请求发送GCash INBOX收据"
    ]
    
    # 成功完成的情况
    success_keywords = [
        "收到款项订单已回调", "已出款成功", "该笔款项已到账", "第三方已成功处理你的订单",
        "出款成功，请重新检查账户", "充值成功，请耐心等待"
    ]
    
    # 需要用户重新操作的情况
    retry_keywords = [
        "重新提交提现申请", "请日切后重新提交订单", "修改客户收款卡",
        "客户收款卡已限额", "客户收款卡号错误", "客户收款银行维护", "客户卡号异常"
    ]
    
    if any(keyword in tg_reply_type for keyword in continue_keywords):
        return "continue", "working"
    elif any(keyword in tg_reply_type for keyword in user_input_keywords):
        return "continue", "working"
    elif any(keyword in tg_reply_type for keyword in success_keywords):
        return "finish", "finish"
    elif any(keyword in tg_reply_type for keyword in retry_keywords):
        return "continue", "working"
    else:
        # 默认情况：结束对话
        return "finish", "finish"
