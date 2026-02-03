"""
Telegram命令控制器
用于接收/stop命令停止持续提醒
"""
import os
import asyncio
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from typing import Optional
import re
import sys
import datetime


class TelegramController:
    """Telegram命令控制器"""
    
    def __init__(self, spread_monitor=None, volatility_monitor=None, target_monitor=None, position_monitor=None, extra_monitors=None):
        """
        初始化控制器
        
        Args:
            spread_monitor: PriceMonitor实例，用于价差监控控制
            volatility_monitor: PriceVolatilityMonitor实例，用于波动监控控制
            target_monitor: PriceTargetMonitor实例，用于价格目标监控控制
            position_monitor: PositionMonitor实例，用于持仓监控控制
            extra_monitors: list[PriceTargetMonitor]，用于其他动态配置的监控控制
        """
        self.bot_token = os.getenv('TELEGRAM_ALERT_BOT_TOKEN')
        self.chat_id = os.getenv('TELEGRAM_ALERT_CHAT_ID')
        self.spread_monitor = spread_monitor
        self.volatility_monitor = volatility_monitor
        self.target_monitor = target_monitor
        self.position_monitor = position_monitor
        self.extra_monitors = extra_monitors or []
        self.application = None
        
        if not all([self.bot_token, self.chat_id]):
            print("⚠️ 警告: Telegram配置不完整，无法启用命令控制")
            self.enabled = False
        else:
            self.enabled = True
        
        self._resume_task = None  # Store the scheduled resume task
    
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """处理/start命令"""
        if str(update.effective_chat.id) != str(self.chat_id):
            await update.message.reply_text("❌ 您没有权限使用此机器人")
            return
        
        welcome_msg = (
            "👋 价格提醒机器人控制\n\n"
            "可用命令：\n"
            "/start - 显示帮助\n"
            "/pause [时长] - 暂停提醒 (例如: /pause 10m, /pause 1h, 或不带参数永久暂停)\n"
            "/continue - 恢复监控\n"
            "/status - 查看状态\n"
            "/stop - 🔴 停止机器人进程"
        )
        await update.message.reply_text(welcome_msg)
    
    async def pause_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """处理/pause命令 - 暂停提醒，支持时长参数"""
        if str(update.effective_chat.id) != str(self.chat_id):
            await update.message.reply_text("❌ 您没有权限使用此机器人")
            return
        
        # Parse arguments
        args = context.args
        duration_str = args[0] if args else None
        
        # Calculate duration if provided
        seconds = 0
        readable_duration = "永久"
        
        if duration_str:
            match = re.match(r'^(\d+)(s|m|h|d)?$', duration_str.lower())
            if match:
                value = int(match.group(1))
                unit = match.group(2) or 'm' # Default to minutes if no unit
                
                if unit == 's':
                    seconds = value
                    readable_duration = f"{value}秒"
                elif unit == 'm':
                    seconds = value * 60
                    readable_duration = f"{value}分钟"
                elif unit == 'h':
                    seconds = value * 3600
                    readable_duration = f"{value}小时"
                elif unit == 'd':
                    seconds = value * 86400
                    readable_duration = f"{value}天"
            else:
                await update.message.reply_text("❌ 格式错误。示例: /pause 10m, /pause 1h")
                return
        
        # Cancel existing resume task if exists
        if self._resume_task:
            self._resume_task.cancel()
            self._resume_task = None

        stopped_list = []
        
        # 停止价差监控提醒
        if self.spread_monitor:
            self.spread_monitor.stop_alerting = True
            self.spread_monitor.alerting = False
            stopped_list.append("价差监控")
        
        # 停止波动监控提醒（并暂停监控）
        if self.volatility_monitor:
            self.volatility_monitor.stop_alerting = True
            self.volatility_monitor.alerting = False
            self.volatility_monitor.monitoring_paused = True
            stopped_list.append("波动监控")
        
        # 停止价格目标监控提醒（并暂停监控）
        if self.target_monitor:
            self.target_monitor.stop_alerting = True
            self.target_monitor.alerting = False
            self.target_monitor.monitoring_paused = True
            stopped_list.append("价格目标监控")

        # 停止持仓监控提醒（并暂停监控）
        if self.position_monitor:
            self.position_monitor.stop_alerting = True
            self.position_monitor.alerting = False
            self.position_monitor.monitoring_paused = True
            stopped_list.append("持仓监控")
        
        # 停止其他动态监控提醒（并暂停监控）
        for i, monitor in enumerate(self.extra_monitors):
            if monitor:
                monitor.stop_alerting = True
                monitor.alerting = False
                monitor.monitoring_paused = True
                monitor_name = getattr(monitor.config, 'symbol', f"Monitor_{i+1}")
                stopped_list.append(f"{monitor_name}监控")
        
        if stopped_list:
            msg = f"⏸️ 已暂停: {', '.join(stopped_list)}\n⏳ 暂停时长: {readable_duration}"
            await update.message.reply_text(msg)
            
            # If duration is set, schedule auto-resume
            if seconds > 0:
                self._resume_task = asyncio.create_task(self._scheduled_resume(seconds, update, context))
        else:
            await update.message.reply_text("❌ 没有找到可用的监控器")

    async def _scheduled_resume(self, delay: int, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Scheduled task to resume monitoring"""
        try:
            await asyncio.sleep(delay)
            # Call continue logic
            await update.message.reply_text("⏰ 暂停结束，自动恢复监控...")
            await self.continue_command(update, context)
            self._resume_task = None
        except asyncio.CancelledError:
            pass # Task was cancelled, do nothing

    async def stop_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """处理/stop命令 - 停止进程"""
        if str(update.effective_chat.id) != str(self.chat_id):
            await update.message.reply_text("❌ 您没有权限使用此机器人")
            return
            
        await update.message.reply_text("🛑 正在停止机器人进程... (需要手动运行 ./run.sh 重启)")
        await self.send_shutdown_notification()
        
        # Stop the updater and application
        await self.application.stop()
        
        # Force exit
        print("🛑 收到Telegram停止命令，退出进程")
        os._exit(0)
    
    async def continue_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """处理/continue命令 - 恢复波动监控"""
        if str(update.effective_chat.id) != str(self.chat_id):
            await update.message.reply_text("❌ 您没有权限使用此机器人")
            return
        
        resumed_list = []
        
        # Cancel resume task if manually continued
        if self._resume_task:
            self._resume_task.cancel()
            self._resume_task = None
        
        if self.volatility_monitor:
            self.volatility_monitor.monitoring_paused = False
            self.volatility_monitor.stop_alerting = False
            resumed_list.append("波动监控")
        
        if self.target_monitor:
            self.target_monitor.monitoring_paused = False
            self.target_monitor.stop_alerting = False
            resumed_list.append("价格目标监控")

        if self.position_monitor:
            self.position_monitor.monitoring_paused = False
            self.position_monitor.stop_alerting = False
            resumed_list.append("持仓监控")
        
        for i, monitor in enumerate(self.extra_monitors):
            if monitor:
                monitor.monitoring_paused = False
                monitor.stop_alerting = False
                monitor_name = getattr(monitor.config, 'symbol', f"Monitor_{i+1}")
                resumed_list.append(f"{monitor_name}监控")
        
        if resumed_list:
            await update.message.reply_text(f"✅ 已恢复以下监控：{', '.join(resumed_list)}，将继续监控并通知")
        else:
            await update.message.reply_text("❌ 没有可恢复的监控")
    
    async def status_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """处理/status命令 - 查看状态"""
        if str(update.effective_chat.id) != str(self.chat_id):
            await update.message.reply_text("❌ 您没有权限使用此机器人")
            return
        
    def _get_monitor_config_summary(self) -> str:
        """获取监控配置摘要"""
        parts = []
        
        if self.spread_monitor:
            parts.append(f"📊 价差监控: {self.spread_monitor.config.ticker} (阈值 {self.spread_monitor.config.threshold_pct}%)")
            
        if self.volatility_monitor:
            parts.append(f"📈 波动监控: {self.volatility_monitor.config.ticker} (阈值 {self.volatility_monitor.config.volatility_threshold_pct}%)")
            
        if self.position_monitor:
            for symbol, cfg in self.position_monitor.config.ticker_configs.items():
                parts.append(f"⚖️ 持仓监控: {symbol} (阈值 {cfg.get('diff_threshold', '?')})")
            
        all_targets = []
        if self.target_monitor: all_targets.append(self.target_monitor)
        if self.extra_monitors: all_targets.extend(self.extra_monitors)
        
        for m in all_targets:
            if not m: continue
            name = getattr(m.config, 'symbol', 'Unknown')
            conds = []
            if m.config.min_price is not None: conds.append(f"<{m.config.min_price}")
            if m.config.max_price is not None: conds.append(f">{m.config.max_price}")
            if m.config.target_price is not None: conds.append(f">={m.config.target_price}")
            cond_str = ", ".join(conds)
            parts.append(f"🎯 价格监控: {name} [{cond_str}]")
            
        return "\n".join(parts) if parts else "无活动监控"

    async def send_startup_notification(self):
        """发送启动通知"""
        if not self.enabled or not self.application:
            return
            
        status_text = self._get_monitor_config_summary()
        message = f"🚀 **监控机器人已启动**\n\n当前监控配置：\n{status_text}"
        
        try:
            await self.application.bot.send_message(chat_id=self.chat_id, text=message)
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

    def _get_monitor_status(self) -> str:
        """获取所有监控器的状态文本"""
        status_parts = []
        
        # 价差监控状态
        if self.spread_monitor:
            status_parts.append(
                f"📊 价差监控\n"
                f"交易标的: {self.spread_monitor.config.ticker}\n"
                f"价差阈值: {self.spread_monitor.config.threshold_pct}%\n"
                f"检查间隔: {self.spread_monitor.config.check_interval}秒"
            )
        
        # 波动监控状态
        if self.volatility_monitor:
            status_parts.append(
                f"\n📈 波动监控\n"
                f"交易标的: {self.volatility_monitor.config.ticker}\n"
                f"时间窗口: {self.volatility_monitor.config.time_window_sec}秒\n"
                f"波动阈值: {self.volatility_monitor.config.volatility_threshold_pct}%\n"
                f"检查间隔: {self.volatility_monitor.config.check_interval}秒"
            )
        
        # 价格目标监控状态 (Legacy & Dynamic)
        all_target_monitors = []
        if self.target_monitor:
            all_target_monitors.append(self.target_monitor)
        
        if self.extra_monitors:
            all_target_monitors.extend(self.extra_monitors)

        for i, monitor in enumerate(all_target_monitors):
            if not monitor:
                continue
                
            category_display = {
                "spot": "现货",
                "linear": "线性合约",
                "inverse": "反向合约"
            }.get(monitor.config.category, monitor.config.category)
            
            conditions = []
            if monitor.config.min_price is not None:
                conditions.append(f"最低: ${monitor.config.min_price:.2f}")
            if monitor.config.max_price is not None:
                conditions.append(f"最高: ${monitor.config.max_price:.2f}")
            if monitor.config.target_price is not None:
                conditions.append(f"目标: ${monitor.config.target_price:.2f}")
            
            conditions_str = ", ".join(conditions) if conditions else "无"
            
            monitor_name = getattr(monitor.config, 'symbol', f"Monitor")
            
            status_parts.append(
                f"\n🎯 {monitor_name}监控\n"
                f"交易所: {monitor.config.exchange.upper()}\n"
                f"市场类型: {category_display}\n"
                f"价格条件: {conditions_str}\n"
                f"检查间隔: {monitor.config.check_interval}秒"
            )
            
        if not status_parts:
            return "❌ 没有配置活动的监控器"
            
        return "\n".join(status_parts)

    def _get_full_status_text(self):
        """获取完整的状态文本（包含运行时状态）"""
        status_parts = []
        
        # 价差监控
        if self.spread_monitor:
            status_parts.append(
                f"📊 价差监控\n"
                f"交易标的: {self.spread_monitor.config.ticker}\n"
                f"价差阈值: {self.spread_monitor.config.threshold_pct}%\n"
                f"检查间隔: {self.spread_monitor.config.check_interval}秒\n"
                f"持续提醒中: {'是' if self.spread_monitor.alerting else '否'}\n"
                f"停止标志: {'是' if self.spread_monitor.stop_alerting else '否'}"
            )
            
        # 波动监控
        if self.volatility_monitor:
            status_parts.append(
                f"\n📈 波动监控\n"
                f"交易标的: {self.volatility_monitor.config.ticker}\n"
                f"阈值: {self.volatility_monitor.config.volatility_threshold_pct}%\n"
                f"暂停: {'是' if self.volatility_monitor.monitoring_paused else '否'}"
            )
            
        # 目标监控
        all_monitors = []
        if self.target_monitor: all_monitors.append(self.target_monitor)
        if self.extra_monitors: all_monitors.extend(self.extra_monitors)
        
        for m in all_monitors:
            if not m: continue
            name = getattr(m.config, 'symbol', 'Monitor')
            status_parts.append(
                f"\n🎯 {name}\n"
                f"暂停: {'是' if m.monitoring_paused else '否'}"
            )
            
        return "\n".join(status_parts) if status_parts else "无监控"

    async def status_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """处理/status命令 - 查看状态"""
        if str(update.effective_chat.id) != str(self.chat_id):
            await update.message.reply_text("❌ 您没有权限使用此机器人")
            return
        
        # 使用新的完整状态方法
        await update.message.reply_text(self._get_full_status_text())

    def _get_full_status_text(self):
        """获取完整的状态文本（包含运行时状态）"""
        status_parts = []
        
        # 价差监控
        if self.spread_monitor:
            status_parts.append(
                f"📊 价差监控\n"
                f"交易标的: {self.spread_monitor.config.ticker}\n"
                f"价差阈值: {self.spread_monitor.config.threshold_pct}%\n"
                f"检查间隔: {self.spread_monitor.config.check_interval}秒\n"
                f"持续提醒中: {'是' if self.spread_monitor.alerting else '否'}\n"
                f"停止标志: {'是' if self.spread_monitor.stop_alerting else '否'}"
            )
            
        # 波动监控
        if self.volatility_monitor:
            status_parts.append(
                f"\n📈 波动监控\n"
                f"交易标的: {self.volatility_monitor.config.ticker}\n"
                f"阈值: {self.volatility_monitor.config.volatility_threshold_pct}%\n"
                f"暂停: {'是' if self.volatility_monitor.monitoring_paused else '否'}"
            )
            
        # 持仓监控
        if self.position_monitor:
            status_parts.append("\n⚖️ 持仓监控")
            for symbol, cfg in self.position_monitor.config.ticker_configs.items():
                status_parts.append(
                    f"  - {symbol}: 阈值 {cfg.get('diff_threshold', '?')}"
                )
            status_parts.append(
                f"检查间隔: {self.position_monitor.config.check_interval}秒\n"
                f"持续提醒中: {'是' if self.position_monitor.alerting else '否'}\n"
                f"停止标志: {'是' if self.position_monitor.stop_alerting else '否'}\n"
                f"监控暂停: {'是' if self.position_monitor.monitoring_paused else '否'}"
            )
            
        # 目标监控
        all_monitors = []
        if self.target_monitor: all_monitors.append(self.target_monitor)
        if self.extra_monitors: all_monitors.extend(self.extra_monitors)
        
        for m in all_monitors:
            if not m: continue
            name = getattr(m.config, 'symbol', 'Monitor')
            status_parts.append(
                f"\n🎯 {name}\n"
                f"暂停: {'是' if m.monitoring_paused else '否'}"
            )
            
        return "\n".join(status_parts) if status_parts else "无监控"

        
        # 波动监控状态
        if self.volatility_monitor:
            status_parts.append(
                f"\n📈 波动监控\n"
                f"交易标的: {self.volatility_monitor.config.ticker}\n"
                f"时间窗口: {self.volatility_monitor.config.time_window_sec}秒\n"
                f"波动阈值: {self.volatility_monitor.config.volatility_threshold_pct}%\n"
                f"检查间隔: {self.volatility_monitor.config.check_interval}秒\n"
                f"持续提醒中: {'是' if self.volatility_monitor.alerting else '否'}\n"
                f"停止标志: {'是' if self.volatility_monitor.stop_alerting else '否'}\n"
                f"监控暂停: {'是' if self.volatility_monitor.monitoring_paused else '否'}"
            )
        
        # 价格目标监控状态
        if self.target_monitor:
            category_display = {
                "spot": "现货",
                "linear": "线性合约",
                "inverse": "反向合约"
            }.get(self.target_monitor.config.category, self.target_monitor.config.category)
            
            conditions = []
            if self.target_monitor.config.min_price is not None:
                conditions.append(f"最低: ${self.target_monitor.config.min_price:.2f}")
            if self.target_monitor.config.max_price is not None:
                conditions.append(f"最高: ${self.target_monitor.config.max_price:.2f}")
            if self.target_monitor.config.target_price is not None:
                conditions.append(f"目标: ${self.target_monitor.config.target_price:.2f}")
            
            conditions_str = ", ".join(conditions) if conditions else "无"
            
            status_parts.append(
                f"\n🎯 价格目标监控\n"
                f"交易所: {self.target_monitor.config.exchange.upper()}\n"
                f"市场类型: {category_display}\n"
                f"交易对: {self.target_monitor.config.symbol}\n"
                f"价格条件: {conditions_str}\n"
                f"检查间隔: {self.target_monitor.config.check_interval}秒\n"
                f"持续提醒中: {'是' if self.target_monitor.alerting else '否'}\n"
                f"停止标志: {'是' if self.target_monitor.stop_alerting else '否'}\n"
                f"监控暂停: {'是' if self.target_monitor.monitoring_paused else '否'}"
            )
        
        # 其他动态监控状态
        for i, monitor in enumerate(self.extra_monitors):
            if monitor:
                category_display = {
                    "spot": "现货",
                    "linear": "线性合约",
                    "inverse": "反向合约"
                }.get(monitor.config.category, monitor.config.category)
                
                conditions = []
                if monitor.config.min_price is not None:
                    conditions.append(f"最低: ${monitor.config.min_price:.2f}")
                if monitor.config.max_price is not None:
                    conditions.append(f"最高: ${monitor.config.max_price:.2f}")
                
                conditions_str = ", ".join(conditions) if conditions else "无"
                
                # 使用配置中的 symbol 或默认名称
                monitor_name = getattr(monitor.config, 'symbol', f"Extra Monitor {i+1}")
                
                status_parts.append(
                    f"\n💎 {monitor_name}监控\n"
                    f"交易所: {monitor.config.exchange.upper()}\n"
                    f"市场类型: {category_display}\n"
                    f"交易对: {monitor.config.symbol}\n"
                    f"价格条件: {conditions_str}\n"
                    f"检查间隔: {monitor.config.check_interval}秒\n"
                    f"持续提醒中: {'是' if monitor.alerting else '否'}\n"
                    f"停止标志: {'是' if monitor.stop_alerting else '否'}\n"
                    f"监控暂停: {'是' if monitor.monitoring_paused else '否'}"
                )
        
        return "\n".join(status_parts) if status_parts else "❌ 没有找到可用的监控器"
    
    async def start_bot(self):
        """启动Telegram bot"""
        if not self.enabled:
            print("⚠️ Telegram控制器未启用")
            return
        
        try:
            self.application = Application.builder().token(self.bot_token).build()
            
            # 注册命令处理器
            self.application.add_handler(CommandHandler("start", self.start_command))
            self.application.add_handler(CommandHandler("pause", self.pause_command))
            self.application.add_handler(CommandHandler("stop", self.stop_command))
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
