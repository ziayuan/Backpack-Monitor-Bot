"""
简化的提醒管理器
仅支持Telegram提醒
"""
import os
import asyncio
import aiohttp
import json
from typing import Optional

class TelegramAlert:
    """Telegram消息提醒"""
    
    def __init__(self):
        self.bot_token = os.getenv('TELEGRAM_ALERT_BOT_TOKEN')
        self.chat_id = os.getenv('TELEGRAM_ALERT_CHAT_ID')
        
        if not all([self.bot_token, self.chat_id]):
            print(f"⚠️ 警告: Telegram配置不完整")
            self.enabled = False
            self.api_url = None
        else:
            self.enabled = True
            self.api_url = f"https://api.telegram.org/bot{self.bot_token}"
            print(f"✅ Telegram配置完成: Chat ID={self.chat_id}")
    
    async def send_message(self, text: str) -> bool:
        """
        发送Telegram消息
        """
        if not self.enabled:
            return False
        
        try:
            # 添加警告标记
            if "🚨" not in text:
                message = f"🚨 价格提醒\n\n{text}"
            else:
                message = text
                
            payload = {
                'chat_id': self.chat_id,
                'text': message,
                'parse_mode': 'HTML'
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.api_url}/sendMessage",
                    json=payload
                ) as response:
                    result = await response.json()
                    
                    if result.get('ok'):
                        print(f"✅ Telegram消息发送成功")
                        return True
                    else:
                        print(f"❌ Telegram消息发送失败: {result.get('description')}")
                        return False
                        
        except Exception as e:
            print(f"❌ Telegram消息异常: {e}")
            return False

class AlertManager:
    """提醒管理器"""
    
    def __init__(self):
        print("=" * 50)
        print("初始化提醒管理器 (Standalone)...")
        print("=" * 50)
        
        self.telegram_alert = TelegramAlert()
        self.last_alert_time = {}
        
        print("=" * 50)
        
    async def send_alert(self, message: str, alert_type: str = "telegram", cooldown: int = 300):
        """
        发送提醒
        """
        print(f"\n{'='*50}")
        print(f"📤 send_alert 被调用")
        print(f"   cooldown: {cooldown}秒")
        print(f"{'='*50}\n")
        
        # 添加进程标识
        message = f"{message}\n\n@[TerminalName: Python, ProcessId: {os.getpid()}]"
        
        current_time = asyncio.get_event_loop().time()
        
        # 冷却检查
        if cooldown > 0:
            last_time = self.last_alert_time.get('telegram', 0)
            time_since_last = current_time - last_time
            
            if time_since_last < cooldown:
                print(f"⏸️ 提醒冷却中，跳过 (需等待 {cooldown - int(time_since_last)}秒)")
                return []
            
        # 发送
        result = await self.telegram_alert.send_message(message)
        
        if result:
            self.last_alert_time['telegram'] = current_time
            return [("Telegram", True)]
        else:
            return [("Telegram", False)]
