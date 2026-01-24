"""
Backpack价格价差监控机器人
监控现货和合约价差，超过阈值时发送提醒
"""
import os
import asyncio
import sys
import time
import aiohttp
from decimal import Decimal
from typing import Optional, Dict, Any, List, Tuple
from dataclasses import dataclass
from dotenv import load_dotenv

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bpx.public import Public
from alert_manager import AlertManager
from logger import TradingLogger
from bpx.account import Account


# 交易对符号映射：Backpack格式 -> 币安格式
TICKER_SYMBOL_MAP = {
    "BTC": "BTCUSDT",
    "ETH": "ETHUSDT",
    "SOL": "SOLUSDT",
    "BNB": "BNBUSDT",
    "XRP": "XRPUSDT",
    "ADA": "ADAUSDT",
    "DOGE": "DOGEUSDT",
    "DOT": "DOTUSDT",
    "LINK": "LINKUSDT",
    "LTC": "LTCUSDT",
    "AVAX": "AVAXUSDT",
    "UNI": "UNIUSDT",
    "ATOM": "ATOMUSDT",
    "MATIC": "MATICUSDT",
    "ALGO": "ALGOUSDT",
    "XLM": "XLMUSDT",
    "VET": "VETUSDT",
    "FIL": "FILUSDT",
    "TRX": "TRXUSDT",
    "ETC": "ETCUSDT",
}


async def get_binance_price(ticker: str, logger: Optional[TradingLogger] = None) -> Optional[Decimal]:
    """
    从币安获取价格（备用交易所）
    
    Args:
        ticker: 交易标的（如 BTC, ETH, SOL）
        logger: 日志记录器（可选）
    
    Returns:
        价格（Decimal）或 None
    """
    # 将 Backpack 格式转换为币安格式
    symbol = TICKER_SYMBOL_MAP.get(ticker.upper(), f"{ticker.upper()}USDT")
    
    try:
        async with aiohttp.ClientSession() as session:
            # 使用币安公开 API 获取价格（不需要 API key）
            url = f"https://api.binance.com/api/v3/ticker/price?symbol={symbol}"
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as response:
                if response.status == 200:
                    data = await response.json()
                    if 'price' in data:
                        price = Decimal(str(data['price']))
                        if logger:
                            logger.log(f"✅ 从币安获取价格成功: {symbol} = ${price}", "INFO")
                        return price
                    else:
                        if logger:
                            logger.log(f"⚠️ 币安返回数据格式异常: {data}", "WARNING")
                else:
                    if logger:
                        logger.log(f"⚠️ 币安 API 返回错误状态码: {response.status}", "WARNING")
    except asyncio.TimeoutError:
        if logger:
            logger.log(f"⚠️ 币安 API 请求超时", "WARNING")
    except Exception as e:
        if logger:
            logger.log(f"⚠️ 从币安获取价格失败: {e}", "WARNING")
    
    return None


@dataclass
class MonitorConfig:
    """监控配置"""
    ticker: str = "SOL"  # 交易标的
    threshold_pct: Decimal = Decimal("2.0")  # 价差阈值（百分比）
    check_interval: int = 1  # 检查间隔（秒）
    alert_type: str = "telegram"  # 提醒类型: "phone", "telegram", "both"
    alert_cooldown: int = 0  # 提醒冷却时间（秒）- 设为0表示无冷却
    alert_interval: int = 1  # 持续提醒时的发送间隔（秒）
    enabled: bool = True


class PriceMonitor:
    """价格监控器"""
    
    def __init__(self, config: MonitorConfig):
        self.config = config
        # 使用alert_前缀区分alert bot和grid bot的日志
        self.logger = TradingLogger(exchange="alert_backpack", ticker=config.ticker, log_to_console=True)
        self.alert_manager = AlertManager()
        self.public_client = Public()
        
        # 现货和合约的交易对符号
        # Backpack现货通常格式: SOL_USDC
        # Backpack合约格式可能需要确认，通常是相同的或加上后缀
        self.spot_symbol = f"{config.ticker}_USDC"
        self.futures_symbol = f"{config.ticker}_USDC_PERP"  # 可能需要根据实际情况调整
        
        # 价格历史记录（用于计算平均价差）
        self.price_history = []
        self.max_history = 100
        
        # 持续提醒控制
        self.alerting = False  # 是否正在持续发送提醒
        self.stop_alerting = False  # 停止提醒标志（通过Telegram命令设置）
    
    async def get_spot_price(self) -> Optional[Decimal]:
        """获取现货价格（使用订单簿中间价，实时更新）"""
        # 首先尝试从 Backpack 获取价格
        try:
            # 优先使用订单簿中间价（实时更新），而不是lastPrice（仅在交易时更新）
            depth_data = self.public_client.get_depth(self.spot_symbol)
            if depth_data and 'bids' in depth_data and 'asks' in depth_data:
                bids = depth_data['bids']
                asks = depth_data['asks']
                if bids and asks:
                    # 确保bids和asks已排序
                    bids_sorted = sorted(bids, key=lambda x: Decimal(str(x[0])), reverse=True)
                    asks_sorted = sorted(asks, key=lambda x: Decimal(str(x[0])))
                    best_bid = Decimal(str(bids_sorted[0][0]))
                    best_ask = Decimal(str(asks_sorted[0][0]))
                    mid_price = (best_bid + best_ask) / 2
                    self.logger.log(f"现货价格（中间价）: ${mid_price}", "DEBUG")
                    return mid_price
            
            # 如果订单簿失败，尝试使用ticker的lastPrice作为备用
            ticker_data = self.public_client.get_ticker(self.spot_symbol)
            if ticker_data and 'lastPrice' in ticker_data:
                price = Decimal(str(ticker_data['lastPrice']))
                self.logger.log(f"现货价格（lastPrice备用）: ${price}", "DEBUG")
                return price
                        
        except Exception as e:
            self.logger.log(f"从 Backpack 获取现货价格失败: {e}", "WARNING")
            # Backpack 失败，尝试从币安获取（备用交易所）
            self.logger.log(f"🔄 尝试从币安获取现货价格作为备用...", "INFO")
            binance_price = await get_binance_price(self.config.ticker, self.logger)
            if binance_price is not None:
                return binance_price
            else:
                self.logger.log(f"从币安获取现货价格也失败", "ERROR")
                return None
        
        # 如果 Backpack 返回了数据但没有价格，也尝试币安
        self.logger.log(f"🔄 Backpack 未返回有效现货价格，尝试从币安获取...", "INFO")
        binance_price = await get_binance_price(self.config.ticker, self.logger)
        if binance_price is not None:
            return binance_price
        
        return None
    
    async def get_futures_price(self) -> Optional[Decimal]:
        """获取合约价格（使用订单簿中间价，实时更新）"""
        # 首先尝试从 Backpack 获取价格
        try:
            # 优先使用订单簿中间价（实时更新），而不是lastPrice（仅在交易时更新）
            depth_data = self.public_client.get_depth(self.futures_symbol)
            if depth_data and 'bids' in depth_data and 'asks' in depth_data:
                bids = depth_data['bids']
                asks = depth_data['asks']
                if bids and asks:
                    # 确保bids和asks已排序
                    bids_sorted = sorted(bids, key=lambda x: Decimal(str(x[0])), reverse=True)
                    asks_sorted = sorted(asks, key=lambda x: Decimal(str(x[0])))
                    best_bid = Decimal(str(bids_sorted[0][0]))
                    best_ask = Decimal(str(asks_sorted[0][0]))
                    mid_price = (best_bid + best_ask) / 2
                    self.logger.log(f"合约价格（中间价）: ${mid_price}", "DEBUG")
                    return mid_price
            
            # 如果订单簿失败，尝试使用ticker的lastPrice作为备用
            ticker_data = self.public_client.get_ticker(self.futures_symbol)
            if ticker_data and 'lastPrice' in ticker_data:
                price = Decimal(str(ticker_data['lastPrice']))
                self.logger.log(f"合约价格（lastPrice备用）: ${price}", "DEBUG")
                return price
                        
        except Exception as e:
            self.logger.log(f"从 Backpack 获取合约价格失败: {e}", "WARNING")
            # Backpack 失败，尝试从币安获取永续合约价格（备用交易所）
            # 注意：币安的永续合约价格可能与 Backpack 的合约价格有差异
            self.logger.log(f"🔄 尝试从币安获取永续合约价格作为备用...", "INFO")
            binance_price = await get_binance_price(self.config.ticker, self.logger)
            if binance_price is not None:
                self.logger.log(f"⚠️ 使用币安价格作为合约价格参考（可能与 Backpack 合约价格有差异）", "WARNING")
                return binance_price
            else:
                self.logger.log(f"从币安获取合约价格也失败", "ERROR")
                return None
        
        # 如果 Backpack 返回了数据但没有价格，也尝试币安
        self.logger.log(f"🔄 Backpack 未返回有效合约价格，尝试从币安获取...", "INFO")
        binance_price = await get_binance_price(self.config.ticker, self.logger)
        if binance_price is not None:
            self.logger.log(f"⚠️ 使用币安价格作为合约价格参考（可能与 Backpack 合约价格有差异）", "WARNING")
            return binance_price
        
        return None
    
    def calculate_spread_pct(self, spot_price: Decimal, futures_price: Decimal) -> Decimal:
        """计算价差百分比"""
        if spot_price <= 0:
            return Decimal("0")
        
        # 价差 = (合约价格 - 现货价格) / 现货价格 * 100
        spread = ((futures_price - spot_price) / spot_price) * Decimal("100")
        return spread
    
    async def check_price_spread(self) -> bool:
        """检查价差并触发提醒"""
        spot_price = await self.get_spot_price()
        futures_price = await self.get_futures_price()
        
        if spot_price is None or futures_price is None:
            self.logger.log("无法获取价格数据，跳过本次检查", "WARNING")
            return False
        
        # 计算价差
        spread_pct = self.calculate_spread_pct(spot_price, futures_price)
        abs_spread_pct = abs(spread_pct)
        threshold_float = float(self.config.threshold_pct)
        
        # 记录价格历史
        self.price_history.append({
            'spot': float(spot_price),
            'futures': float(futures_price),
            'spread_pct': float(spread_pct)
        })
        if len(self.price_history) > self.max_history:
            self.price_history.pop(0)
        
        # 打印当前价差
        direction = "合约溢价" if spread_pct > 0 else "现货溢价"
        self.logger.log(
            f"📊 价格监控 - 现货: ${spot_price:.4f}, 合约: ${futures_price:.4f}, "
            f"价差: {abs_spread_pct:.2f}%, 阈值: {threshold_float:.2f}% ({direction})",
            "INFO"
        )
        
        # 检查是否超过阈值（确保类型一致）
        abs_spread_float = float(abs_spread_pct)
        
        # 调试日志
        self.logger.log(
            f"🔍 价差判断: abs_spread={abs_spread_float:.6f}%, threshold={threshold_float:.6f}%, 超过阈值={abs_spread_float >= threshold_float}",
            "DEBUG"
        )
        
        if abs_spread_float >= threshold_float:
            # 如果还没开始持续提醒，启动持续提醒循环
            if not self.alerting and not self.stop_alerting:
                self.alerting = True
                self.stop_alerting = False
                self.logger.log(f"⚠️ 价差超过阈值！开始持续提醒", "WARNING")
                # 启动持续提醒任务（不传价格参数，让它在循环中实时获取）
                asyncio.create_task(self._continuous_alert())
                return True
            # 如果已经在持续提醒中，不重复启动
        else:
            # 价差恢复正常，停止持续提醒
            if self.alerting:
                self.logger.log(f"✅ 价差恢复正常，停止持续提醒", "INFO")
                self.alerting = False
                self.stop_alerting = False
        
        return False
    
    async def _continuous_alert(self):
        """持续发送提醒（每秒一次），直到收到停止命令或价差恢复正常"""
        self.logger.log(f"🔄 开始持续提醒循环", "INFO")
        
        while self.alerting and not self.stop_alerting:
            try:
                # 每次循环都获取最新价格
                spot_price = await self.get_spot_price()
                futures_price = await self.get_futures_price()
                
                if spot_price is None or futures_price is None:
                    self.logger.log("无法获取最新价格，跳过本次提醒", "WARNING")
                    await asyncio.sleep(self.config.alert_interval)
                    continue
                
                # 计算最新价差
                spread_pct = self.calculate_spread_pct(spot_price, futures_price)
                direction = "合约溢价" if spread_pct > 0 else "现货溢价"
                
                # 如果价差恢复正常，停止提醒
                abs_spread_float = float(abs(spread_pct))
                threshold_float = float(self.config.threshold_pct)
                if abs_spread_float < threshold_float:
                    self.logger.log(f"✅ 价差恢复正常 ({abs_spread_float:.4f}% < {threshold_float:.4f}%)，停止持续提醒", "INFO")
                    self.alerting = False
                    self.stop_alerting = False
                    break
                
                message = (
                    f"🚨 价格价差告警！\n\n"
                    f"交易标的: {self.config.ticker}\n"
                    f"现货价格: ${spot_price:.4f}\n"
                    f"合约价格: ${futures_price:.4f}\n"
                    f"价差: {abs(spread_pct):.4f}% ({direction})\n"
                    f"阈值: {self.config.threshold_pct}%\n"
                    f"持续提醒中..."
                )
                
                # 发送提醒（无冷却时间）
                try:
                    results = await self.alert_manager.send_alert(
                        message=message,
                        alert_type=self.config.alert_type,
                        cooldown=0  # 无冷却时间
                    )
                    
                    # 记录提醒结果
                    if results:
                        for alert_name, success in results:
                            if success:
                                self.logger.log(f"✅ {alert_name}提醒发送成功", "INFO")
                            else:
                                self.logger.log(f"❌ {alert_name}提醒发送失败", "WARNING")
                    else:
                        self.logger.log("⚠️ 提醒发送返回空结果", "WARNING")
                except Exception as send_error:
                    self.logger.log(f"❌ 发送提醒时出错: {send_error}", "ERROR")
                    # 即使发送失败，也继续循环
                
                # 等待指定间隔后继续
                await asyncio.sleep(self.config.alert_interval)
                
            except Exception as e:
                self.logger.log(f"❌ 持续提醒循环出错: {e}", "ERROR")
                # 即使出错，也继续循环（等待后重试）
                await asyncio.sleep(self.config.alert_interval)
        
        self.logger.log(f"🛑 持续提醒循环已停止", "INFO")
        self.alerting = False
    
    async def start_monitoring(self):
        """开始监控循环"""
        self.logger.log(
            f"🚀 价格监控启动\n"
            f"交易标的: {self.config.ticker}\n"
            f"价差阈值: {self.config.threshold_pct}%\n"
            f"检查间隔: {self.config.check_interval}秒\n"
            f"提醒类型: {self.config.alert_type}",
            "INFO"
        )
        
        while self.config.enabled:
            try:
                await self.check_price_spread()
                await asyncio.sleep(self.config.check_interval)
            except KeyboardInterrupt:
                self.logger.log("监控停止（用户中断）", "INFO")
                break
            except Exception as e:
                self.logger.log(f"监控异常: {e}", "ERROR")
                await asyncio.sleep(self.config.check_interval)


@dataclass
class VolatilityMonitorConfig:
    """价格波动监控配置"""
    ticker: str = "BTC"  # 交易标的
    time_window_sec: int = 60  # 时间窗口（秒），如60表示1分钟内
    volatility_threshold_pct: Decimal = Decimal("1.0")  # 波动阈值（百分比）
    check_interval: int = 1  # 检查间隔（秒）
    alert_type: str = "telegram"  # 提醒类型: "phone", "telegram", "both"
    alert_interval: int = 1  # 持续提醒时的发送间隔（秒）
    enabled: bool = True


class PriceVolatilityMonitor:
    """价格波动监控器"""
    
    def __init__(self, config: VolatilityMonitorConfig):
        self.config = config
        # 使用alert_前缀区分alert bot和grid bot的日志
        self.logger = TradingLogger(exchange="alert_backpack", ticker=config.ticker, log_to_console=True)
        self.alert_manager = AlertManager()
        self.public_client = Public()
        
        # 交易对符号
        self.symbol = f"{config.ticker}_USDC"
        
        # 价格历史记录：[(timestamp, price), ...]
        self.price_history: List[Tuple[float, Decimal]] = []
        
        # 持续提醒控制
        self.alerting = False  # 是否正在持续发送提醒
        self.stop_alerting = False  # 停止提醒标志（通过Telegram命令设置）
        self.monitoring_paused = False  # 是否暂停监控（通过/continue恢复）
    
    async def get_price(self) -> Optional[Decimal]:
        """获取价格（使用订单簿中间价，实时更新）"""
        # 首先尝试从 Backpack 获取价格
        try:
            # 优先使用订单簿中间价（实时更新），而不是lastPrice（仅在交易时更新）
            depth_data = self.public_client.get_depth(self.symbol)
            if depth_data and 'bids' in depth_data and 'asks' in depth_data:
                bids = depth_data['bids']
                asks = depth_data['asks']
                if bids and asks:
                    # 确保bids和asks已排序
                    bids_sorted = sorted(bids, key=lambda x: Decimal(str(x[0])), reverse=True)
                    asks_sorted = sorted(asks, key=lambda x: Decimal(str(x[0])))
                    best_bid = Decimal(str(bids_sorted[0][0]))
                    best_ask = Decimal(str(asks_sorted[0][0]))
                    mid_price = (best_bid + best_ask) / 2
                    return mid_price
            
            # 如果订单簿失败，尝试使用ticker的lastPrice作为备用
            ticker_data = self.public_client.get_ticker(self.symbol)
            if ticker_data and 'lastPrice' in ticker_data:
                price = Decimal(str(ticker_data['lastPrice']))
                return price
                        
        except Exception as e:
            self.logger.log(f"从 Backpack 获取价格失败: {e}", "WARNING")
            # Backpack 失败，尝试从币安获取（备用交易所）
            self.logger.log(f"🔄 尝试从币安获取价格作为备用...", "INFO")
            binance_price = await get_binance_price(self.config.ticker, self.logger)
            if binance_price is not None:
                return binance_price
            else:
                self.logger.log(f"从币安获取价格也失败，无法获取价格数据", "ERROR")
                return None
        
        # 如果 Backpack 返回了数据但没有价格，也尝试币安
        self.logger.log(f"🔄 Backpack 未返回有效价格，尝试从币安获取...", "INFO")
        binance_price = await get_binance_price(self.config.ticker, self.logger)
        if binance_price is not None:
            return binance_price
        
        return None
    
    def calculate_volatility(self) -> Optional[Tuple[Decimal, Decimal, Decimal, Decimal]]:
        """
        计算时间窗口内的价格波动
        
        Returns:
            (min_price, max_price, volatility_pct, volatility_abs) 或 None
        """
        if not self.price_history:
            return None
        
        current_time = time.time()
        time_window = self.config.time_window_sec
        
        # 过滤出时间窗口内的价格
        window_prices = [
            (ts, price) for ts, price in self.price_history
            if current_time - ts <= time_window
        ]
        
        if not window_prices:
            return None
        
        prices = [price for _, price in window_prices]
        min_price = min(prices)
        max_price = max(prices)
        
        # 计算波动百分比：((max - min) / min) * 100
        if min_price > 0:
            volatility_abs = max_price - min_price
            volatility_pct = (volatility_abs / min_price) * Decimal("100")
            return (min_price, max_price, volatility_pct, volatility_abs)
        
        return None
    
    async def check_volatility(self) -> bool:
        """检查波动并触发提醒"""
        if self.monitoring_paused:
            return False
        
        price = await self.get_price()
        
        if price is None:
            self.logger.log("无法获取价格数据，跳过本次检查", "WARNING")
            return False
        
        # 记录当前价格和时间戳
        current_time = time.time()
        self.price_history.append((current_time, price))
        
        # 清理过期的价格记录（保留2倍时间窗口的数据）
        time_window = self.config.time_window_sec
        cutoff_time = current_time - (time_window * 2)
        self.price_history = [(ts, p) for ts, p in self.price_history if ts > cutoff_time]
        
        # 计算波动
        volatility_result = self.calculate_volatility()
        
        if volatility_result is None:
            return False
        
        min_price, max_price, volatility_pct, volatility_abs = volatility_result
        threshold_float = float(self.config.volatility_threshold_pct)
        volatility_float = float(volatility_pct)
        
        # 打印当前波动
        time_window_display = f"{self.config.time_window_sec}秒内"
        if self.config.time_window_sec >= 60:
            time_window_display = f"{self.config.time_window_sec // 60}分钟内"
        
        self.logger.log(
            f"📊 波动监控 - {self.config.ticker}: ${price:.4f}, "
            f"{time_window_display}波动: {volatility_float:.4f}%, 阈值: {threshold_float:.4f}% "
            f"(最低: ${min_price:.4f}, 最高: ${max_price:.4f})",
            "INFO"
        )
        
        # 检查是否超过阈值
        if volatility_float >= threshold_float:
            # 如果还没开始持续提醒，启动持续提醒循环
            if not self.alerting and not self.stop_alerting:
                self.alerting = True
                self.stop_alerting = False
                self.logger.log(f"⚠️ 价格波动超过阈值！开始持续提醒", "WARNING")
                # 启动持续提醒任务
                asyncio.create_task(self._continuous_alert())
                return True
            # 如果已经在持续提醒中，不重复启动
        
        return False
    
    async def _continuous_alert(self):
        """持续发送提醒（每秒一次），直到收到停止命令或波动恢复正常"""
        self.logger.log(f"🔄 开始持续提醒循环", "INFO")
        
        while self.alerting and not self.stop_alerting:
            try:
                # 每次循环都获取最新价格并更新历史
                price = await self.get_price()
                
                if price is None:
                    self.logger.log("无法获取最新价格，跳过本次提醒", "WARNING")
                    await asyncio.sleep(self.config.alert_interval)
                    continue
                
                # 更新价格历史
                current_time = time.time()
                self.price_history.append((current_time, price))
                time_window = self.config.time_window_sec
                cutoff_time = current_time - (time_window * 2)
                self.price_history = [(ts, p) for ts, p in self.price_history if ts > cutoff_time]
                
                # 计算最新波动
                volatility_result = self.calculate_volatility()
                
                if volatility_result is None:
                    await asyncio.sleep(self.config.alert_interval)
                    continue
                
                min_price, max_price, volatility_pct, volatility_abs = volatility_result
                threshold_float = float(self.config.volatility_threshold_pct)
                volatility_float = float(volatility_pct)
                
                # 如果波动恢复正常，停止提醒
                if volatility_float < threshold_float:
                    self.logger.log(f"✅ 波动恢复正常 ({volatility_float:.4f}% < {threshold_float:.4f}%)，停止持续提醒", "INFO")
                    self.alerting = False
                    self.stop_alerting = False
                    break
                
                message = (
                    f"🚨 价格波动告警！\n\n"
                    f"交易标的: {self.config.ticker}\n"
                    f"当前价格: ${price:.4f}\n"
                    f"{self.config.time_window_sec}秒内最低价: ${min_price:.4f}\n"
                    f"{self.config.time_window_sec}秒内最高价: ${max_price:.4f}\n"
                    f"波动幅度: {volatility_float:.4f}% (${volatility_abs:.4f})\n"
                    f"阈值: {self.config.volatility_threshold_pct}%\n"
                    f"持续提醒中..."
                )
                
                # 发送提醒（无冷却时间）
                try:
                    results = await self.alert_manager.send_alert(
                        message=message,
                        alert_type=self.config.alert_type,
                        cooldown=0  # 无冷却时间
                    )
                    
                    # 记录提醒结果
                    if results:
                        for alert_name, success in results:
                            if success:
                                self.logger.log(f"✅ {alert_name}提醒发送成功", "INFO")
                            else:
                                self.logger.log(f"❌ {alert_name}提醒发送失败", "WARNING")
                    else:
                        self.logger.log("⚠️ 提醒发送返回空结果", "WARNING")
                except Exception as send_error:
                    self.logger.log(f"❌ 发送提醒时出错: {send_error}", "ERROR")
                    # 即使发送失败，也继续循环
                
                # 等待指定间隔后继续
                await asyncio.sleep(self.config.alert_interval)
                
            except Exception as e:
                self.logger.log(f"❌ 持续提醒循环出错: {e}", "ERROR")
                # 即使出错，也继续循环（等待后重试）
                await asyncio.sleep(self.config.alert_interval)
        
        self.logger.log(f"🛑 持续提醒循环已停止", "INFO")
        self.alerting = False
    
    async def start_monitoring(self):
        """开始监控循环"""
        self.logger.log(
            f"🚀 价格波动监控启动\n"
            f"交易标的: {self.config.ticker}\n"
            f"时间窗口: {self.config.time_window_sec}秒\n"
            f"波动阈值: {self.config.volatility_threshold_pct}%\n"
            f"检查间隔: {self.config.check_interval}秒\n"
            f"提醒类型: {self.config.alert_type}",
            "INFO"
        )
        
        while self.config.enabled:
            try:
                await self.check_volatility()
                await asyncio.sleep(self.config.check_interval)
            except KeyboardInterrupt:
                self.logger.log("监控停止（用户中断）", "INFO")
                break
            except Exception as e:
                self.logger.log(f"监控异常: {e}", "ERROR")
                await asyncio.sleep(self.config.check_interval)


@dataclass
class PriceTargetMonitorConfig:
    """价格目标监控配置"""
    exchange: str = "bybit"  # 交易所名称
    symbol: str = "MMTUSDT"  # 交易对符号
    category: str = "linear"  # Bybit市场类型: spot(现货), linear(线性合约), inverse(反向合约)
    target_price: Optional[Decimal] = None  # 目标价格（达到或超过时触发）- 用于单一目标价格监控
    min_price: Optional[Decimal] = None  # 最低价格（低于此价格时触发）
    max_price: Optional[Decimal] = None  # 最高价格（高于此价格时触发）
    check_interval: int = 1  # 检查间隔（秒）
    alert_type: str = "telegram"  # 提醒类型: "phone", "telegram", "both"
    alert_interval: int = 1  # 持续提醒时的发送间隔（秒）
    enabled: bool = True


class PriceTargetMonitor:
    """价格目标监控器"""
    
    def __init__(self, config: PriceTargetMonitorConfig):
        self.config = config
        # 使用alert_前缀区分alert bot和grid bot的日志
        self.logger = TradingLogger(exchange=f"alert_{config.exchange}", ticker=config.symbol, log_to_console=True)
        self.alert_manager = AlertManager()
        self.exchange_name = config.exchange.lower()
        
        # 根据交易所初始化客户端
        if self.exchange_name == "bybit":
            try:
                from pybit.unified_trading import HTTP
                self.client = HTTP(testnet=False)
            except ImportError:
                self.logger.log("⚠️ 未安装 pybit 库，请运行: pip install pybit", "ERROR")
                self.client = None
        else:
            self.client = None
            self.logger.log(f"⚠️ 不支持的交易所: {config.exchange}", "ERROR")
        
        # 持续提醒控制
        self.alerting = False  # 是否正在持续发送提醒
        self.stop_alerting = False  # 停止提醒标志（通过Telegram命令设置）
        self.monitoring_paused = False  # 是否暂停监控（通过/continue恢复）
        self.target_reached = False  # 是否已触发价格条件
        self.trigger_reason = ""  # 触发原因：below_min, above_max, above_target
    
    async def get_price(self) -> Optional[Decimal]:
        """获取价格"""
        if not self.client:
            return None
        
        try:
            if self.exchange_name == "bybit":
                # 获取 Bybit 价格（使用 get_tickers，复数形式）
                # 支持 spot(现货), linear(线性合约), inverse(反向合约), perp(永续合约)
                # 如果配置的 category 失败，自动尝试其他常见类型
                categories_to_try = [self.config.category, "linear", "spot", "inverse", "perp"]
                # 去重，保持顺序
                seen = set()
                categories_to_try = [c for c in categories_to_try if c not in seen and not seen.add(c)]
                
                last_error = None
                for category in categories_to_try:
                    try:
                        ticker = self.client.get_tickers(
                            category=category,
                            symbol=self.config.symbol
                        )
                        
                        if ticker and 'result' in ticker and 'list' in ticker['result']:
                            ticker_list = ticker['result']['list']
                            if ticker_list and len(ticker_list) > 0:
                                last_price = Decimal(str(ticker_list[0]['lastPrice']))
                                # 如果使用的 category 与配置的不同，记录警告
                                if category != self.config.category:
                                    self.logger.log(
                                        f"⚠️ 配置的 category '{self.config.category}' 无效，已自动切换到 '{category}'",
                                        "WARNING"
                                    )
                                return last_price
                    except Exception as e:
                        last_error = e
                        # 继续尝试下一个 category
                        continue
                
                # 所有 category 都失败了
                if last_error:
                    self.logger.log(
                        f"获取价格失败: {last_error} (已尝试所有 category: {', '.join(categories_to_try)})",
                        "ERROR"
                    )
                else:
                    self.logger.log(
                        f"获取价格失败: 未找到有效的 category (已尝试: {', '.join(categories_to_try)})",
                        "ERROR"
                    )
                return None
                        
        except Exception as e:
            self.logger.log(f"获取价格失败: {e}", "ERROR")
            return None
        
        return None
    
    async def check_price_target(self) -> bool:
        """检查价格是否触发条件（目标价格、最低价格、最高价格）"""
        if self.monitoring_paused:
            return False
        
        current_price = await self.get_price()
        
        if current_price is None:
            self.logger.log("无法获取价格数据，跳过本次检查", "WARNING")
            return False
        
        # 检查价格条件
        triggered = False
        trigger_reason = ""
        
        # 检查是否低于最低价格
        if self.config.min_price is not None and current_price < self.config.min_price:
            triggered = True
            trigger_reason = "below_min"
        
        # 检查是否高于最高价格
        elif self.config.max_price is not None and current_price > self.config.max_price:
            triggered = True
            trigger_reason = "above_max"
        
        # 检查是否达到目标价格（兼容旧功能）
        elif self.config.target_price is not None and current_price >= self.config.target_price:
            triggered = True
            trigger_reason = "above_target"
        
        # 构建状态信息
        status_parts = []
        if self.config.min_price is not None:
            status_parts.append(f"最低: ${self.config.min_price:.2f}")
        if self.config.max_price is not None:
            status_parts.append(f"最高: ${self.config.max_price:.2f}")
        if self.config.target_price is not None:
            status_parts.append(f"目标: ${self.config.target_price:.2f}")
        
        status_info = ", ".join(status_parts)
        
        # 确定当前状态
        if triggered:
            status_display = "✅ 已触发"
        else:
            status_display = "⏳ 正常范围"
        
        # 打印当前价格
        self.logger.log(
            f"📊 价格监控 - {self.config.symbol}: ${current_price:.2f}, "
            f"条件: [{status_info}], "
            f"状态: {status_display}",
            "INFO"
        )
        
        # 如果触发条件且还没开始持续提醒
        if triggered:
            if not self.target_reached:
                self.target_reached = True
                self.trigger_reason = trigger_reason
                if not self.alerting and not self.stop_alerting:
                    self.alerting = True
                    self.stop_alerting = False
                    # 安全地构建原因文本，处理None值
                    if trigger_reason == "below_min" and self.config.min_price is not None:
                        reason_text = f"价格低于最低价格 ${self.config.min_price:.2f}"
                    elif trigger_reason == "above_max" and self.config.max_price is not None:
                        reason_text = f"价格高于最高价格 ${self.config.max_price:.2f}"
                    elif trigger_reason == "above_target" and self.config.target_price is not None:
                        reason_text = f"价格达到目标价格 ${self.config.target_price:.2f}"
                    else:
                        reason_text = "价格触发条件"
                    self.logger.log(f"🎯 {reason_text}！开始持续提醒", "WARNING")
                    self.logger.log(f"📝 调试信息: alerting={self.alerting}, stop_alerting={self.stop_alerting}, target_reached={self.target_reached}, trigger_reason={trigger_reason}", "INFO")
                    # 启动持续提醒任务
                    try:
                        # 确保在事件循环中创建任务
                        loop = asyncio.get_event_loop()
                        if loop.is_running():
                            task = asyncio.create_task(self._continuous_alert())
                            self.logger.log(f"📝 已创建持续提醒任务，任务对象: {task}", "INFO")
                            # 给任务添加异常处理
                            def task_done_callback(future):
                                try:
                                    exception = future.exception()
                                    if exception:
                                        self.logger.log(f"❌ 持续提醒任务异常: {exception}", "ERROR")
                                        import traceback
                                        self.logger.log(f"❌ 异常堆栈:\n{traceback.format_exc()}", "ERROR")
                                except Exception as e:
                                    self.logger.log(f"❌ 任务回调异常: {e}", "ERROR")
                            task.add_done_callback(task_done_callback)
                        else:
                            self.logger.log(f"❌ 事件循环未运行，无法创建任务", "ERROR")
                    except Exception as e:
                        self.logger.log(f"❌ 创建持续提醒任务失败: {e}", "ERROR")
                        import traceback
                        self.logger.log(f"❌ 异常堆栈:\n{traceback.format_exc()}", "ERROR")
                    return True
                else:
                    self.logger.log(f"⚠️ 触发条件但未启动提醒: alerting={self.alerting}, stop_alerting={self.stop_alerting}", "WARNING")
            else:
                # 已经触发过，持续提醒应该已经在运行中
                self.logger.log(f"📝 条件已触发，持续提醒状态: alerting={self.alerting}, stop_alerting={self.stop_alerting}", "DEBUG")
        elif not triggered:
            # 价格回到正常范围，重置状态
            if self.target_reached:
                self.logger.log(f"📉 价格回到正常范围，重置监控状态", "INFO")
            self.target_reached = False
            self.trigger_reason = ""
        
        return False
    
    async def _continuous_alert(self):
        """持续发送提醒（每秒一次），直到收到停止命令或价格回落"""
        self.logger.log(f"🔄 开始持续提醒循环 (trigger_reason={self.trigger_reason})", "INFO")
        self.logger.log(f"📝 持续提醒循环初始状态: alerting={self.alerting}, stop_alerting={self.stop_alerting}, alert_type={self.config.alert_type}", "INFO")
        
        loop_count = 0
        while self.alerting and not self.stop_alerting:
            loop_count += 1
            if loop_count == 1:
                self.logger.log(f"📝 进入持续提醒循环，第一次循环", "INFO")
            self.logger.log(f"📝 持续提醒循环第{loop_count}次，条件检查: alerting={self.alerting}, stop_alerting={self.stop_alerting}", "INFO")
            try:
                # 每次循环都获取最新价格
                current_price = await self.get_price()
                
                if current_price is None:
                    self.logger.log("无法获取最新价格，跳过本次提醒", "WARNING")
                    await asyncio.sleep(self.config.alert_interval)
                    continue
                
                # 检查价格是否回到正常范围，停止提醒
                should_stop = False
                stop_reason = ""
                
                if self.trigger_reason == "below_min" and self.config.min_price is not None:
                    # 如果之前是因为低于最低价触发，现在价格回到最低价以上
                    if current_price >= self.config.min_price:
                        should_stop = True
                        stop_reason = f"价格回到最低价格以上 ({current_price:.2f} >= {self.config.min_price:.2f})"
                elif self.trigger_reason == "above_max" and self.config.max_price is not None:
                    # 如果之前是因为高于最高价触发，现在价格回到最高价以下
                    if current_price <= self.config.max_price:
                        should_stop = True
                        stop_reason = f"价格回到最高价格以下 ({current_price:.2f} <= {self.config.max_price:.2f})"
                elif self.trigger_reason == "above_target" and self.config.target_price is not None:
                    # 如果之前是因为达到目标价触发，现在价格回落
                    if current_price < self.config.target_price:
                        should_stop = True
                        stop_reason = f"价格回落 ({current_price:.2f} < {self.config.target_price:.2f})"
                
                if should_stop:
                    self.logger.log(f"📉 {stop_reason}，停止持续提醒", "INFO")
                    self.alerting = False
                    self.stop_alerting = False
                    self.target_reached = False
                    self.trigger_reason = ""
                    break
                
                category_display = {
                    "spot": "现货",
                    "linear": "线性合约",
                    "inverse": "反向合约"
                }.get(self.config.category, self.config.category)
                
                # 构建提醒消息（安全处理None值）
                trigger_message = ""
                if self.trigger_reason == "below_min" and self.config.min_price is not None:
                    trigger_message = f"⚠️ 价格低于最低价格！\n最低价格: ${self.config.min_price:.2f}"
                elif self.trigger_reason == "above_max" and self.config.max_price is not None:
                    trigger_message = f"⚠️ 价格高于最高价格！\n最高价格: ${self.config.max_price:.2f}"
                elif self.trigger_reason == "above_target" and self.config.target_price is not None:
                    trigger_message = f"🎯 价格达到目标价格！\n目标价格: ${self.config.target_price:.2f}"
                else:
                    trigger_message = "⚠️ 价格触发条件！"
                
                message = (
                    f"{trigger_message}\n\n"
                    f"交易所: {self.config.exchange.upper()}\n"
                    f"市场类型: {category_display}\n"
                    f"交易对: {self.config.symbol}\n"
                    f"当前价格: ${current_price:.2f}\n"
                    f"持续提醒中..."
                )
                
                # 发送提醒（无冷却时间）
                try:
                    self.logger.log(f"📝 准备发送提醒消息 (第{loop_count}次循环)", "INFO")
                    self.logger.log(f"📝 消息长度: {len(message)}字符, alert_type={self.config.alert_type}", "INFO")
                    results = await self.alert_manager.send_alert(
                        message=message,
                        alert_type=self.config.alert_type,
                        cooldown=0  # 无冷却时间
                    )
                    
                    # 记录提醒结果
                    self.logger.log(f"📝 提醒发送API返回结果: {results}", "INFO")
                    if results:
                        for alert_name, success in results:
                            if success:
                                self.logger.log(f"✅ {alert_name}提醒发送成功", "INFO")
                            else:
                                self.logger.log(f"❌ {alert_name}提醒发送失败", "WARNING")
                    else:
                        self.logger.log("⚠️ 提醒发送返回空结果", "WARNING")
                except Exception as send_error:
                    self.logger.log(f"❌ 发送提醒时出错: {send_error}", "ERROR")
                    import traceback
                    self.logger.log(f"❌ 错误堆栈:\n{traceback.format_exc()}", "ERROR")
                    # 即使发送失败，也继续循环
                
                # 等待指定间隔后继续
                await asyncio.sleep(self.config.alert_interval)
                
            except Exception as e:
                self.logger.log(f"❌ 持续提醒循环出错: {e}", "ERROR")
                # 即使出错，也继续循环（等待后重试）
                await asyncio.sleep(self.config.alert_interval)
        
        self.logger.log(f"🛑 持续提醒循环已停止", "INFO")
        self.alerting = False
    
    async def start_monitoring(self):
        """开始监控循环"""
        category_display = {
            "spot": "现货",
            "linear": "线性合约",
            "inverse": "反向合约"
        }.get(self.config.category, self.config.category)
        
        # 构建价格条件信息
        conditions = []
        if self.config.min_price is not None:
            conditions.append(f"最低价格: ${self.config.min_price:.2f} (低于时触发)")
        if self.config.max_price is not None:
            conditions.append(f"最高价格: ${self.config.max_price:.2f} (高于时触发)")
        if self.config.target_price is not None:
            conditions.append(f"目标价格: ${self.config.target_price:.2f} (达到时触发)")
        
        conditions_str = "\n".join(conditions) if conditions else "无价格条件"
        
        self.logger.log(
            f"🚀 价格目标监控启动\n"
            f"交易所: {self.config.exchange.upper()}\n"
            f"市场类型: {category_display}\n"
            f"交易对: {self.config.symbol}\n"
            f"价格条件:\n{conditions_str}\n"
            f"检查间隔: {self.config.check_interval}秒\n"
            f"提醒类型: {self.config.alert_type}",
            "INFO"
        )
        
        while self.config.enabled:
            try:
                await self.check_price_target()
                await asyncio.sleep(self.config.check_interval)
            except KeyboardInterrupt:
                self.logger.log("监控停止（用户中断）", "INFO")
                break
            except Exception as e:
                self.logger.log(f"监控异常: {e}", "ERROR")
                import traceback
                self.logger.log(f"异常堆栈:\n{traceback.format_exc()}", "ERROR")
                await asyncio.sleep(self.config.check_interval)


@dataclass
class PositionMonitorConfig:
    """持仓监控配置"""
    accounts: List[Dict[str, str]]  # 账户列表 [{'name': 'A', 'key': '...', 'secret': '...'}, ...]
    symbol: str = "SOL"  # 监控币种
    diff_threshold: Decimal = Decimal("1.0")  # 现货与合约持仓差值阈值
    check_interval: int = 60  # 检查间隔（秒）
    alert_type: str = "telegram"
    alert_interval: int = 60
    enabled: bool = True


class PositionMonitor:
    """持仓监控器"""
    
    def __init__(self, config: PositionMonitorConfig):
        self.config = config
        self.logger = TradingLogger(exchange="alert_position", ticker=config.symbol, log_to_console=True)
        self.alert_manager = AlertManager()
        
        # 初始化账户客户端
        self.account_clients = []
        for acc in config.accounts:
            try:
                key = acc['key'].strip()
                secret = acc['secret'].strip()
                
                # 检查密钥长度 (通常 Ed25519 key base64 编码后为 44 字符)
                if len(secret) != 44:
                     self.logger.log(f"⚠️ 账户 {acc['name']} 密钥长度可能不正确 ({len(secret)} 字符, 预期 44). 请检查环境变量.", "WARNING")
                
                client = Account(public_key=key, secret_key=secret)
                self.account_clients.append({
                    'name': acc['name'],
                    'client': client
                })
            except Exception as e:
                self.logger.log(f"⚠️ 初始化账户 {acc['name']} 失败: {e}", "ERROR")
        
        self.spot_symbol = f"{config.symbol}_USDC"  # 假设是USDC交易对
        self.futures_symbol = f"{config.symbol}_USDC_PERP"
        
        # 持续提醒控制
        self.alerting = False
        self.stop_alerting = False
        self.monitoring_paused = False
        self.triggered_accounts = set()  # 记录触发报警的账户名

    async def get_account_positions(self, client, account_name: str) -> Optional[Tuple[Decimal, Decimal]]:
        """获取账户的现货和合约持仓"""
        try:
            # 获取现货余额 (使用 get_collateral 以包含理财借出部分)
            spot_qty = Decimal("0")
            try:
                collateral_info = client.get_collateral()
                if collateral_info and 'collateral' in collateral_info:
                    for asset in collateral_info['collateral']:
                        if asset.get('symbol') == self.config.symbol:
                            spot_qty = Decimal(str(asset.get('totalQuantity', 0)))
                            break
            except Exception as e:
                self.logger.log(f"获取Collateral失败: {e} - 尝试回退到get_balances", "WARNING")
                # Fallback to get_balances
                balances = client.get_balances()
                if balances and isinstance(balances, dict):
                    if self.config.symbol in balances:
                         spot_balance = balances.get(self.config.symbol, {})
                         spot_qty = Decimal(str(spot_balance.get('available', 0))) + \
                                    Decimal(str(spot_balance.get('locked', 0)))
            
            # 获取合约持仓
            futures_qty = Decimal("0")
            positions = client.get_open_positions()
            if positions:
                for pos in positions:
                    if pos.get('symbol') == self.futures_symbol:
                        futures_qty = Decimal(str(pos.get('netQuantity', 0)))
                        break
            
            return spot_qty, futures_qty
        except Exception as e:
            self.logger.log(f"获取账户 {account_name} 持仓失败: {e}", "ERROR")
            return None

    async def check_positions(self) -> bool:
        """检查所有账户持仓"""
        if self.monitoring_paused:
            return False
            
        triggered_any = False
        new_triggered_accounts = set()
        
        for account in self.account_clients:
            name = account['name']
            client = account['client']
            
            pos = await self.get_account_positions(client, name)
            if pos is None:
                continue
                
            spot_qty, futures_qty = pos
            
            # 计算风险敞口: abs(spot_qty + futures_qty)
            net_exposure = abs(spot_qty + futures_qty)
            diff_msg = f"现货: {spot_qty:.4f}, 合约: {futures_qty:.4f}, 净敞口: {net_exposure:.4f}"
            
            self.logger.log(f"⚖️ 持仓检查 - 账户 {name}: {diff_msg}", "INFO")
            
            if net_exposure > self.config.diff_threshold:
                new_triggered_accounts.add(name)
                triggered_any = True
                
                if name not in self.triggered_accounts:
                    self.logger.log(f"🚨 账户 {name} 持仓偏差过大! {diff_msg}", "WARNING")
        
        # 更新触发状态
        if triggered_any:
            self.triggered_accounts = new_triggered_accounts
            if not self.alerting and not self.stop_alerting:
                self.alerting = True
                self.stop_alerting = False
                asyncio.create_task(self._continuous_alert())
                return True
        elif self.alerting:
            # 如果所有账户都恢复正常
            self.logger.log(f"✅ 所有账户持仓恢复正常", "INFO")
            self.alerting = False
            self.stop_alerting = False
            self.triggered_accounts.clear()
            
        return False

    async def _continuous_alert(self):
        """持续提醒循环"""
        self.logger.log(f"🔄 开始持仓异常持续提醒", "INFO")
        
        while self.alerting and not self.stop_alerting:
            try:
                messages = []
                monitor_still_triggered = False
                
                for account in self.account_clients:
                    name = account['name']
                    # 只提醒之前触发的账户，或者重新检查所有账户
                    client = account['client']
                    pos = await self.get_account_positions(client, name)
                    
                    if pos:
                        spot_qty, futures_qty = pos
                        net_exposure = abs(spot_qty + futures_qty)
                        
                        if net_exposure > self.config.diff_threshold:
                            monitor_still_triggered = True
                            msg = (
                                f"🚨 账户 {name} 持仓警告！\n"
                                f"现货: {spot_qty:.4f}\n"
                                f"合约: {futures_qty:.4f}\n"
                                f"净敞口: {net_exposure:.4f}\n"
                                f"阈值: {self.config.diff_threshold}"
                            )
                            messages.append(msg)
                
                if not monitor_still_triggered:
                     self.logger.log(f"✅ 循环检查中发现已恢复正常", "INFO")
                     self.alerting = False
                     self.stop_alerting = False
                     break
                
                if messages:
                    full_msg = f"⚖️ **多账户持仓风险报警**\n监控币种: {self.config.symbol}\n\n" + "\n\n".join(messages)
                    
                    await self.alert_manager.send_alert(
                        message=full_msg,
                        alert_type=self.config.alert_type,
                        cooldown=0
                    )
                
                await asyncio.sleep(self.config.alert_interval)
                
            except Exception as e:
                self.logger.log(f"❌ 持仓提醒循环异常: {e}", "ERROR")
                await asyncio.sleep(self.config.alert_interval)
                
        self.logger.log(f"🛑 持仓持续提醒已停止", "INFO")
        self.alerting = False

    async def start_monitoring(self):
        """启动持仓监控"""
        self.logger.log(
            f"🚀 持仓监控启动\n"
            f"监控账户数: {len(self.account_clients)}\n"
            f"监控币种: {self.config.symbol}\n"
            f"敞口阈值: {self.config.diff_threshold}\n"
            f"检查间隔: {self.config.check_interval}秒",
            "INFO"
        )
        
        while self.config.enabled:
            try:
                await self.check_positions()
                await asyncio.sleep(self.config.check_interval)
            except KeyboardInterrupt:
                break
            except Exception as e:
                self.logger.log(f"持仓监控异常: {e}", "ERROR")
                await asyncio.sleep(self.config.check_interval)


async def main():
    """主函数"""
    # 加载环境变量
    load_dotenv()
    
    # 从环境变量读取价差监控配置
    ticker = os.getenv('ALERT_TICKER', 'SOL')
    threshold_pct = Decimal(os.getenv('ALERT_THRESHOLD_PCT', '2.0'))
    check_interval = int(os.getenv('ALERT_CHECK_INTERVAL', '1'))
    alert_type = os.getenv('ALERT_TYPE', 'telegram')  # phone, telegram, both
    alert_cooldown = int(os.getenv('ALERT_COOLDOWN', '0'))  # 设为0表示无冷却
    alert_interval = int(os.getenv('ALERT_INTERVAL', '1'))  # 持续提醒间隔（秒）
    
    spread_config = MonitorConfig(
        ticker=ticker,
        threshold_pct=threshold_pct,
        check_interval=check_interval,
        alert_type=alert_type,
        alert_cooldown=alert_cooldown,
        alert_interval=alert_interval
    )
    
    spread_monitor = PriceMonitor(spread_config)
    
    # 从环境变量读取波动监控配置
    volatility_ticker = os.getenv('VOLATILITY_TICKER', 'BTC')
    volatility_time_window = int(os.getenv('VOLATILITY_TIME_WINDOW_SEC', '60'))  # 秒
    volatility_threshold_pct = Decimal(os.getenv('VOLATILITY_THRESHOLD_PCT', '1.0'))
    volatility_check_interval = int(os.getenv('VOLATILITY_CHECK_INTERVAL', '1'))
    volatility_enabled = os.getenv('VOLATILITY_ENABLED', 'true').lower() == 'true'
    
    volatility_config = VolatilityMonitorConfig(
        ticker=volatility_ticker,
        time_window_sec=volatility_time_window,
        volatility_threshold_pct=volatility_threshold_pct,
        check_interval=volatility_check_interval,
        alert_type=alert_type,
        alert_interval=alert_interval,
        enabled=volatility_enabled
    )
    
    volatility_monitor = PriceVolatilityMonitor(volatility_config)
    
    # 从环境变量读取价格目标监控配置
    target_exchange = os.getenv('PRICE_TARGET_EXCHANGE', 'bybit')
    target_symbol = os.getenv('PRICE_TARGET_SYMBOL', 'MMTUSDT')
    target_category = os.getenv('PRICE_TARGET_CATEGORY', 'linear')  # spot, linear, inverse
    target_price_str = os.getenv('PRICE_TARGET_PRICE', '')
    target_min_price_str = os.getenv('PRICE_TARGET_MIN_PRICE', '')
    target_max_price_str = os.getenv('PRICE_TARGET_MAX_PRICE', '')
    target_check_interval = int(os.getenv('PRICE_TARGET_CHECK_INTERVAL', '1'))
    target_enabled = os.getenv('PRICE_TARGET_ENABLED', 'true').lower() == 'true'
    
    target_price = Decimal(target_price_str) if target_price_str else None
    target_min_price = Decimal(target_min_price_str) if target_min_price_str else None
    target_max_price = Decimal(target_max_price_str) if target_max_price_str else None
    
    target_config = PriceTargetMonitorConfig(
        exchange=target_exchange,
        symbol=target_symbol,
        category=target_category,
        target_price=target_price,
        min_price=target_min_price,
        max_price=target_max_price,
        check_interval=target_check_interval,
        alert_type=alert_type,
        alert_interval=alert_interval,
        enabled=target_enabled
    )
    
    target_monitor = PriceTargetMonitor(target_config)
    
    # 动态加载 SYMBOLn 本监控配置
    extra_monitors = []
    n = 1
    # 最多尝试加载到 SYMBOL50，防止无限循环，如果连续3个都没找到就停止
    not_found_count = 0
    max_check = 50
    
    print(f"🔄 开始加载动态监控配置 (SYMBOL1 ~ SYMBOL{max_check})...")
    
    while n <= max_check:
        prefix = f"SYMBOL{n}_PRICE_"
        
        # 检查是否配置了 enabled 或 symbol
        enabled_str = os.getenv(f'{prefix}ENABLED')
        symbol_str = os.getenv(f'{prefix}SYMBOL')
        
        if not enabled_str and not symbol_str:
            not_found_count += 1
            if not_found_count >= 3:
                # 连续3个未找到，认为后面也没有了
                break
            n += 1
            continue
            
        # 找到了配置，重置未找到计数
        not_found_count = 0
        
        enabled = (enabled_str or 'true').lower() == 'true'
        
        if enabled:
            exchange = os.getenv(f'{prefix}EXCHANGE', 'bybit')
            symbol = symbol_str or f"SYMBOL{n}"
            category = os.getenv(f'{prefix}CATEGORY', 'linear')
            min_price_str = os.getenv(f'{prefix}MIN', '')
            max_price_str = os.getenv(f'{prefix}MAX', '')
            check_interval = int(os.getenv(f'{prefix}CHECK_INTERVAL', '1'))
            
            min_price = Decimal(min_price_str) if min_price_str else None
            max_price = Decimal(max_price_str) if max_price_str else None
            
            if min_price is not None or max_price is not None:
                config = PriceTargetMonitorConfig(
                    exchange=exchange,
                    symbol=symbol,
                    category=category,
                    target_price=None,
                    min_price=min_price,
                    max_price=max_price,
                    check_interval=check_interval,
                    alert_type=alert_type,
                    alert_interval=alert_interval,
                    enabled=enabled
                )
                monitor = PriceTargetMonitor(config)
                extra_monitors.append(monitor)
                print(f"✅ 已加载监控: {symbol} (SYMBOL{n})")
            else:
                print(f"⚠️ SYMBOL{n} 已启用但未配置价格区间(MIN/MAX)，跳过")
        else:
            print(f"ℹ️ SYMBOL{n} 已配置但被禁用")
            
        n += 1
    
    # 加载持仓监控配置
    position_monitor_enabled = os.getenv('POSITION_MONITOR_ENABLED', 'false').lower() == 'true'
    position_monitor = None
    
    if position_monitor_enabled:
        pos_symbol = os.getenv('POSITION_MONITOR_SYMBOL', 'SOL')
        pos_threshold = Decimal(os.getenv('POSITION_DIFF_THRESHOLD', '1.0'))
        pos_check_interval = int(os.getenv('POSITION_CHECK_INTERVAL', '60'))
        
        # 动态加载账户配置 BP_ACCOUNT{n}_*
        accounts = []
        n = 1
        while n <= 50:
            acc_name = os.getenv(f'BP_ACCOUNT{n}_NAME')
            acc_key = os.getenv(f'BP_ACCOUNT{n}_KEY')
            acc_secret = os.getenv(f'BP_ACCOUNT{n}_SECRET')
            
            if acc_key and acc_secret:
                accounts.append({
                    'name': acc_name or f"Account_{n}",
                    'key': acc_key,
                    'secret': acc_secret
                })
                print(f"✅ 已加载持仓监控账户: {acc_name or f'Account_{n}'}")
            elif not acc_name and n > 3: # 连续没找到，稍微宽容点
                if not os.getenv(f'BP_ACCOUNT{n+1}_KEY'): # 简单预判下一个也不存在
                    break
            n += 1
            
        if accounts:
            pos_config = PositionMonitorConfig(
                accounts=accounts,
                symbol=pos_symbol,
                diff_threshold=pos_threshold,
                check_interval=pos_check_interval,
                alert_type=alert_type,
                alert_interval=alert_interval
            )
            position_monitor = PositionMonitor(pos_config)
        else:
            print("⚠️ 开启了持仓监控但未找到有效的账户配置 (BP_ACCOUNTn_*)")
            position_monitor_enabled = False

    # 启动Telegram控制器（支持多个监控器）
    from telegram_controller import TelegramController
    telegram_controller = TelegramController(
        spread_monitor=spread_monitor,
        volatility_monitor=volatility_monitor,
        target_monitor=target_monitor,
        position_monitor=position_monitor,
        extra_monitors=extra_monitors
    )
    
    # 启动Telegram bot（异步任务）
    if telegram_controller.enabled:
        # 使用await确保bot完全启动
        await telegram_controller.start_bot()
        # 发送启动通知
        await telegram_controller.send_startup_notification()
    
    # 并行运行监控任务
    try:
        tasks = [
            asyncio.create_task(spread_monitor.start_monitoring()),
        ]
        
        if volatility_enabled:
            tasks.append(asyncio.create_task(volatility_monitor.start_monitoring()))
        
        if target_enabled:
            tasks.append(asyncio.create_task(target_monitor.start_monitoring()))
            
        if position_monitor_enabled and position_monitor:
            tasks.append(asyncio.create_task(position_monitor.start_monitoring()))
        
        # 添加动态监控任务
        for monitor in extra_monitors:
            tasks.append(asyncio.create_task(monitor.start_monitoring()))
        
        # 等待所有任务完成
        if tasks:
            await asyncio.gather(*tasks)
        else:
            print("没有活动的监控任务")
            
    except KeyboardInterrupt:
        print("\n监控停止（用户中断）")
    finally:
        # 清理：停止Telegram控制器
        if telegram_controller.enabled:
            # 发送停止通知
            await telegram_controller.send_shutdown_notification()
            await telegram_controller.stop_bot()


if __name__ == "__main__":
    asyncio.run(main())
