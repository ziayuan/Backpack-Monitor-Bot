"""
Telegram命令控制器
用于接收命令控制警报提醒
"""
import os
import asyncio
import time
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from typing import Optional, Dict, Any
import re
import sys
import datetime


class AlertRegistry:
    """统一警报注册表 - 管理所有监控器的警报状态"""
    
    def __init__(self):
        self.alerts: Dict[int, Dict[str, Any]] = {}  # {id: {'name': str, 'monitor': obj, 'description': str}}
        self.muted_until: Dict[int, float] = {}  # {id: timestamp when mute expires}
    
    def register(self, alert_id: int, name: str, description: str, monitor) -> None:
        """注册一个警报"""
        self.alerts[alert_id] = {
            'name': name,
            'description': description,
            'monitor': monitor
        }
        # 给监控器设置alert_id引用
        if monitor:
            monitor.alert_id = alert_id
            monitor.alert_registry = self
    
    def is_muted(self, alert_id: int) -> bool:
        """检查警报是否被静默"""
        if alert_id not in self.muted_until:
            return False
        return time.time() < self.muted_until[alert_id]
    
    def get_remaining_mute_time(self, alert_id: int) -> int:
        """获取剩余静默时间（秒）"""
        if alert_id not in self.muted_until:
            return 0
        remaining = int(self.muted_until[alert_id] - time.time())
        return max(0, remaining)
    
    def mute(self, alert_id: int, duration_sec: int = 600) -> bool:
        """
        静默指定警报
        
        Args:
            alert_id: 警报ID
            duration_sec: 静默时长（秒），默认10分钟
            
        Returns:
            是否成功
        """
        if alert_id not in self.alerts:
            return False
        
        self.muted_until[alert_id] = time.time() + duration_sec
        
        # 暂停监控器
        monitor = self.alerts[alert_id]['monitor']
        if monitor:
            monitor.monitoring_paused = True
            monitor.stop_alerting = True
            monitor.alerting = False
        
        return True
    
    def unmute(self, alert_id: int) -> bool:
        """取消静默指定警报"""
        if alert_id not in self.alerts:
            return False
        
        if alert_id in self.muted_until:
            del self.muted_until[alert_id]
        
        # 恢复监控器
        monitor = self.alerts[alert_id]['monitor']
        if monitor:
            monitor.monitoring_paused = False
            monitor.stop_alerting = False
        
        return True
    
    def unmute_all(self) -> int:
        """
        取消所有静默 / 恢复所有暂停的警报
        包括被 /get 静默的 和 被 /stop 手动停止的
        """
        count = 0
        # 遍历所有注册的警报
        for alert_id in list(self.alerts.keys()):
            # 只要处于非正常状态（静默或暂停），就尝试恢复
            is_muted = alert_id in self.muted_until
            monitor = self.alerts[alert_id]['monitor']
            is_paused = monitor and getattr(monitor, 'monitoring_paused', False)
            
            if is_muted or is_paused:
                # 移除静默标记
                if alert_id in self.muted_until:
                    del self.muted_until[alert_id]
                
                # 恢复监控器状态
                if monitor:
                    monitor.monitoring_paused = False
                    monitor.stop_alerting = False
                
                count += 1
                
        return count
    
    def get_status_text(self) -> str:
        """获取所有警报的状态文本"""
        if not self.alerts:
            return "❌ 没有注册的警报"
        
        lines = ["📋 **警报列表**\n"]
        
        # 预先获取时间，避免在循环中重复调用
        now = time.time()
        
        for alert_id in sorted(self.alerts.keys()):
            info = self.alerts[alert_id]
            monitor = info['monitor']
            
            # 状态指示
            status_parts = []
            
            # check mute directly to save function call overhead
            is_muted = alert_id in self.muted_until and now < self.muted_until[alert_id]
            
            if is_muted:
                remaining = int(self.muted_until[alert_id] - now)
                if remaining >= 60:
                    status_parts.append(f"🔇 静默中 ({remaining // 60}分钟)")
                else:
                    status_parts.append(f"🔇 静默中 ({remaining}秒)")
            elif monitor and getattr(monitor, 'alerting', False):
                status_parts.append("🔔 报警中")
            elif monitor and getattr(monitor, 'monitoring_paused', False):
                status_parts.append("⏸️ 已暂停")
            else:
                status_parts.append("✅ 正常")
            
            status_str = " ".join(status_parts)
            lines.append(f"**{alert_id}** - {info['name']}: {status_str}")
            # 简化输出，去掉描述行以减小消息体积
            # lines.append(f"    {info['description']}")
        
        lines.append("\n💡 使用 `/stop <编号>` 停止警报")
        lines.append("例如: `/stop 1` 停止1号警报")
        
        return "\n".join(lines)


class TelegramController:
    """Telegram命令控制器"""
    
    def __init__(self, spread_monitors=None, volatility_monitors=None, target_monitor=None, position_monitor=None, extra_monitors=None, iv_monitors=None):
        """
        初始化控制器
        
        Args:
            spread_monitors: list[PriceMonitor]，用于价差监控控制（多币种）
            volatility_monitors: list[PriceVolatilityMonitor]，用于波动监控控制（多交易所多币种）
            target_monitor: PriceTargetMonitor实例，用于价格目标监控控制
            position_monitor: PositionMonitor实例，用于持仓监控控制
            extra_monitors: list[PriceTargetMonitor]，用于其他动态配置的监控控制
            iv_monitors: list[DeribitIVMonitor]，用于Deribit IV监控控制
        """
        self.bot_token = os.getenv('TELEGRAM_ALERT_BOT_TOKEN')
        self.chat_id = os.getenv('TELEGRAM_ALERT_CHAT_ID')
        self.spread_monitors = spread_monitors or []
        self.volatility_monitors = volatility_monitors or []
        self.target_monitor = target_monitor
        self.position_monitor = position_monitor
        self.extra_monitors = extra_monitors or []
        self.iv_monitors = iv_monitors or []
        self.application = None
        
        if not all([self.bot_token, self.chat_id]):
            print("⚠️ 警告: Telegram配置不完整，无法启用命令控制")
            self.enabled = False
        else:
            self.enabled = True
        
        # 初始化警报注册表
        self.alert_registry = AlertRegistry()
        self._register_alerts()
    
    def _register_alerts(self):
        """注册所有警报到注册表"""
        alert_id = 1
        
        # 价差监控 (多个)
        for sm in self.spread_monitors:
            ticker = getattr(sm.config, 'ticker', 'Unknown')
            threshold = getattr(sm.config, 'threshold_pct', '?')
            self.alert_registry.register(
                alert_id, 
                f"{ticker}价差监控",
                f"现货/合约价差 (阈值 {threshold}%)",
                sm
            )
            alert_id += 1
        
        # 波动监控 (多个)
        for vm in self.volatility_monitors:
            exchange = getattr(vm.config, 'exchange', 'unknown')
            ticker = getattr(vm.config, 'ticker', 'Unknown')
            threshold = getattr(vm.config, 'volatility_threshold_pct', '?')
            window = getattr(vm.config, 'time_window_sec', '?')
            self.alert_registry.register(
                alert_id,
                f"{exchange.upper()}-{ticker}波动",
                f"{window}秒波动 (阈值 {threshold}%)",
                vm
            )
            alert_id += 1
        
        # 持仓监控
        if self.position_monitor:
            tickers = list(self.position_monitor.config.ticker_configs.keys())
            tickers_str = ", ".join(tickers)
            self.alert_registry.register(
                alert_id,
                "持仓监控",
                f"多账户持仓风险 ({tickers_str})",
                self.position_monitor
            )
            alert_id += 1
        
        # 价格目标监控
        if self.target_monitor:
            symbol = getattr(self.target_monitor.config, 'symbol', 'Unknown')
            self.alert_registry.register(
                alert_id,
                f"{symbol}价格监控",
                self._get_target_description(self.target_monitor),
                self.target_monitor
            )
            alert_id += 1
        
        # 动态监控
        for monitor in self.extra_monitors:
            if monitor:
                symbol = getattr(monitor.config, 'symbol', f'Monitor_{alert_id}')
                self.alert_registry.register(
                    alert_id,
                    f"{symbol}价格监控",
                    self._get_target_description(monitor),
                    monitor
                )
                alert_id += 1
        
        # Deribit IV监控
        for ivm in self.iv_monitors:
            currency = getattr(ivm.config, 'currency', 'BTC')
            iv_threshold = getattr(ivm.config, 'iv_volatility_threshold', '?')
            btc_threshold = getattr(ivm.config, 'btc_volatility_threshold_pct', '?')
            self.alert_registry.register(
                alert_id,
                f"Deribit-{currency} DVOL",
                f"IV波动>{iv_threshold}% + BTC波动>{btc_threshold}%",
                ivm
            )
            alert_id += 1
    
    def _get_target_description(self, monitor) -> str:
        """获取价格目标监控的描述"""
        parts = []
        if getattr(monitor.config, 'min_price', None) is not None:
            parts.append(f"<{monitor.config.min_price}")
        if getattr(monitor.config, 'max_price', None) is not None:
            parts.append(f">{monitor.config.max_price}")
        if getattr(monitor.config, 'target_price', None) is not None:
            parts.append(f">={monitor.config.target_price}")
        return ", ".join(parts) if parts else "无条件"
    
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """处理/start命令"""
        if str(update.effective_chat.id) != str(self.chat_id):
            await update.message.reply_text("❌ 您没有权限使用此机器人")
            return
        
        welcome_msg = (
            "👋 价格提醒机器人控制\n\n"
            "可用命令：\n"
            "/start - 显示帮助\n"
            "/status - 查看所有警报状态概览\n"
            "/status <编号> - 查看指定警报的详细数据\n"
            "/stop <编号> - 停止指定警报\n"
            "/continue - 恢复所有警报\n"
            "/shutdown - 🔴 停止机器人进程"
        )
        await update.message.reply_text(welcome_msg)
    
    async def stop_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """处理/stop命令 - 停止指定警报"""
        if str(update.effective_chat.id) != str(self.chat_id):
            await update.message.reply_text("❌ 您没有权限使用此机器人")
            return
        
        args = context.args
        
        if not args:
            await update.message.reply_text(
                "❌ 请指定警报编号\n"
                "用法: /stop <编号>\n"
                "例如: /stop 21"
            )
            return
        
        try:
            alert_id = int(args[0])
        except ValueError:
            await update.message.reply_text("❌ 警报编号必须是数字")
            return
        
        if alert_id not in self.alert_registry.alerts:
            await update.message.reply_text(f"❌ 警报 #{alert_id} 不存在")
            return
        
        # 停止特定警报
        info = self.alert_registry.alerts[alert_id]
        monitor = info['monitor']
        alert_name = info['name']
        if monitor:
            monitor.stop_alerting = True
            monitor.alerting = False
            monitor.monitoring_paused = True
        
        await update.message.reply_text(
            f"🛑 已停止警报 #{alert_id} ({alert_name})\n"
            f"💡 使用 /continue 可恢复所有警报"
        )
    
    async def shutdown_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """处理/shutdown命令 - 停止机器人进程"""
        if str(update.effective_chat.id) != str(self.chat_id):
            await update.message.reply_text("❌ 您没有权限使用此机器人")
            return
        
        # 停止所有监控器
        for alert_id, info in self.alert_registry.alerts.items():
            monitor = info['monitor']
            if monitor:
                monitor.stop_alerting = True
                monitor.alerting = False
                monitor.monitoring_paused = True
        
        await update.message.reply_text("🛑 正在停止机器人进程... (需要手动运行 ./run.sh 重启)")
        await self.send_shutdown_notification()
        
        await self.application.stop()
        print("🛑 收到Telegram停止命令，退出进程")
        os._exit(0)
    
    
    async def continue_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """处理/continue命令 - 恢复所有警报"""
        if str(update.effective_chat.id) != str(self.chat_id):
            await update.message.reply_text("❌ 您没有权限使用此机器人")
            return
        
        count = self.alert_registry.unmute_all()
        
        if count > 0:
            await update.message.reply_text(f"✅ 已恢复 {count} 个警报的监控")
        else:
            await update.message.reply_text("ℹ️ 没有需要恢复的警报")
    
    async def status_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """处理/status命令 - 查看状态"""
        if str(update.effective_chat.id) != str(self.chat_id):
            await update.message.reply_text("❌ 您没有权限使用此机器人")
            return
        
        args = context.args
        # 如果指定了ID且不是all，则显示详细信息
        if args and args[0].lower() != 'all':
            try:
                alert_id = int(args[0])
                if alert_id in self.alert_registry.alerts:
                    monitor = self.alert_registry.alerts[alert_id]['monitor']
                    if hasattr(monitor, 'get_status_detail'):
                        detail = monitor.get_status_detail()
                        await update.message.reply_text(detail, parse_mode='Markdown')
                    else:
                        await update.message.reply_text(f"⚠️ 警报 #{alert_id} 不支持详细状态查询")
                else:
                    await update.message.reply_text(f"❌ 警报 #{alert_id} 不存在")
            except ValueError:
                await update.message.reply_text("❌ 请输入有效的警报编号 (例如: /status 1) 或使用 /status all")
            return
        
        status_text = self.alert_registry.get_status_text()
        await update.message.reply_text(status_text, parse_mode='Markdown')
    
    def _get_monitor_config_summary(self) -> str:
        """获取监控配置摘要"""
        return self.alert_registry.get_status_text()

    async def send_startup_notification(self):
        """发送启动通知"""
        if not self.enabled or not self.application:
            return
            
        status_text = self.alert_registry.get_status_text()
        message = f"🚀 **监控机器人已启动**\n\n{status_text}"
        
        try:
            await self.application.bot.send_message(chat_id=self.chat_id, text=message, parse_mode='Markdown')
            print("✅ 已发送启动通知")
        except Exception as e:
            print(f"⚠️ 发送启动通知失败: {e}")

    async def send_shutdown_notification(self):
        """发送停止通知"""
        if not self.enabled or not self.application:
            return
            
        message = "🛑 **监控机器人已停止**"
        
        try:
            await self.application.bot.send_message(chat_id=self.chat_id, text=message)
            print("✅ 已发送停止通知")
        except Exception as e:
            print(f"⚠️ 发送停止通知失败: {e}")
        
    async def start_bot(self):
        """启动Telegram bot"""
        if not self.enabled:
            print("⚠️ Telegram控制器未启用")
            return
        
        try:
            self.application = Application.builder().token(self.bot_token).build()
            
            # 注册命令处理器
            self.application.add_handler(CommandHandler("start", self.start_command))
            self.application.add_handler(CommandHandler("stop", self.stop_command))
            self.application.add_handler(CommandHandler("shutdown", self.shutdown_command))
            self.application.add_handler(CommandHandler("continue", self.continue_command))
            self.application.add_handler(CommandHandler("status", self.status_command))
            
            # 启动bot
            print("🤖 Telegram控制器启动中...")
            await self.application.initialize()
            # 先清理 webhook，防止 getUpdates 被阻塞
            try:
                await self.application.bot.delete_webhook(drop_pending_updates=True)
                print("✅ 已删除Webhook并丢弃挂起更新")
            except Exception as e:
                print(f"⚠️ 删除Webhook失败: {e}")
            await self.application.start()
            await self.application.updater.start_polling(drop_pending_updates=True)
            print("✅ Telegram控制器已启动，可以接收命令")
            
        except Exception as e:
            print(f"❌ Telegram控制器启动失败: {e}")
            self.enabled = False
    
    async def stop_bot(self):
        """停止Telegram bot"""
        if self.application:
            try:
                await self.application.updater.stop()
                await self.application.stop()
                await self.application.shutdown()
                print("✅ Telegram控制器已停止")
            except Exception as e:
                print(f"⚠️ 停止Telegram控制器时出错: {e}")
