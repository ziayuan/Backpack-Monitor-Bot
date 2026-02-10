"""
交易所WebSocket客户端
支持多交易所的实时价格推送 (BBO/Ticker/Trade)
"""
import asyncio
import json
import logging
import time
import aiohttp
from typing import Optional, Dict, Any, Callable, List
from decimal import Decimal
from abc import ABC, abstractmethod


class ExchangeWebSocketClient(ABC):
    """交易所WebSocket客户端基类"""
    
    def __init__(self, tickers: List[str]):
        self.tickers = tickers
        self.prices: Dict[str, Decimal] = {}
        self.ws = None
        self.running = False
        self.logger = logging.getLogger(self.name)
        # 设置logger
        handler = logging.StreamHandler()
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        handler.setFormatter(formatter)
        if not self.logger.handlers:
            self.logger.addHandler(handler)
            self.logger.setLevel(logging.INFO)

    @property
    @abstractmethod
    def name(self) -> str:
        """交易所名称"""
        pass
    
    @property
    @abstractmethod
    def url(self) -> str:
        """WebSocket URL"""
        pass
    
    @abstractmethod
    async def _subscribe(self):
        """发送订阅消息"""
        pass
    
    @abstractmethod
    def _parse_message(self, message: Dict[str, Any]):
        """解析接收到的消息并更新价格"""
        pass
    
    async def _heartbeat(self):
        """心跳维持 (默认空实现)"""
        pass

    async def connect(self):
        """建立连接并维持"""
        self.running = True
        while self.running:
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.ws_connect(
                        self.url, 
                        heartbeat=20,  # 协议层心跳
                        autoping=True
                    ) as ws:
                        self.ws = ws
                        self.logger.info(f"✅ 已连接到 {self.name} WebSocket")
                        
                        # 发送订阅
                        await self._subscribe()
                        
                        # 启动心跳任务
                        heartbeat_task = asyncio.create_task(self._heartbeat())
                        
                        # 消息循环
                        try:
                            async for msg in ws:
                                if msg.type == aiohttp.WSMsgType.TEXT:
                                    try:
                                        data = json.loads(msg.data)
                                        self._parse_message(data)
                                    except Exception as e:
                                        self.logger.error(f"解析消息失败: {e}")
                                elif msg.type == aiohttp.WSMsgType.ERROR:
                                    self.logger.error(f"WebSocket错误: {ws.exception()}")
                                    break
                                elif msg.type == aiohttp.WSMsgType.CLOSED:
                                    self.logger.warning("WebSocket连接关闭")
                                    break
                        finally:
                            heartbeat_task.cancel()
                            
            except Exception as e:
                self.logger.error(f"连接断开或出错: {e}, 5秒后重连...")
                await asyncio.sleep(5)
    
    def get_price(self, ticker: str) -> Optional[Decimal]:
        """获取最新价格 (非阻塞)"""
        return self.prices.get(ticker.upper())

    async def start(self):
        """启动客户端 (非阻塞)"""
        asyncio.create_task(self.connect())


class BinanceWSClient(ExchangeWebSocketClient):
    """Binance WebSocket (BookTicker)"""
    
    @property
    def name(self) -> str:
        return "Binance"
        
    @property
    def url(self) -> str:
        return "wss://stream.binance.com:9443/ws"

    async def _subscribe(self):
        # 订阅所有ticker的BookTicker
        # 格式: btcusdt@bookTicker
        params = [f"{t.lower()}usdt@bookTicker" for t in self.tickers]
        msg = {
            "method": "SUBSCRIBE",
            "params": params,
            "id": 1
        }
        await self.ws.send_json(msg)
        self.logger.info(f"已订阅 {len(self.tickers)} 个交易对")

    def _parse_message(self, data: Dict[str, Any]):
        # BookTicker payload example:
        # {"u":400900217,"s":"BNBUSDT","b":"25.35190000","B":"31.21000000","a":"25.36520000","A":"40.66000000"}
        if 's' in data and 'b' in data and 'a' in data:
            symbol = data['s']  # e.g. BTCUSDT
            ticker = symbol.replace('USDT', '')
            
            try:
                bid = Decimal(str(data['b']))
                ask = Decimal(str(data['a']))
                # 只有当bid和ask都有效时才更新
                if bid > 0 and ask > 0:
                    mid_price = (bid + ask) / 2
                    self.prices[ticker] = mid_price
            except Exception:
                pass


class BybitWSClient(ExchangeWebSocketClient):
    """Bybit WebSocket (Ticker)"""
    
    @property
    def name(self) -> str:
        return "Bybit"
        
    @property
    def url(self) -> str:
        return "wss://stream.bybit.com/v5/public/linear"

    async def _subscribe(self):
        # 订阅tickers
        # 格式: tickers.BTCUSDT
        args = [f"tickers.{t.upper()}USDT" for t in self.tickers]
        msg = {
            "op": "subscribe",
            "args": args
        }
        await self.ws.send_json(msg)
        self.logger.info(f"已订阅 {len(self.tickers)} 个交易对")
        
    async def _heartbeat(self):
        while self.running:
            try:
                await asyncio.sleep(20)
                if self.ws and not self.ws.closed:
                    await self.ws.send_json({"op": "ping"})
            except Exception:
                break

    def _parse_message(self, data: Dict[str, Any]):
        # data: {"topic": "tickers.BTCUSDT", "data": {...}}
        if 'topic' in data and data['topic'].startswith('tickers.'):
            symbol = data['topic'].split('.')[1]
            ticker = symbol.replace('USDT', '')
            
            ticker_data = data.get('data', {})
            
            # Bybit推送的是增量数据或快照
            bid = ticker_data.get('bid1Price')
            ask = ticker_data.get('ask1Price')
            last = ticker_data.get('lastPrice')
            
            price = None
            if bid and ask:
                try:
                    price = (Decimal(str(bid)) + Decimal(str(ask))) / 2
                except:
                    pass
            elif last:
                try:
                    price = Decimal(str(last))
                except:
                    pass
            
            if price:
                self.prices[ticker] = price


class BitgetWSClient(ExchangeWebSocketClient):
    """Bitget WebSocket (Ticker)"""
    
    @property
    def name(self) -> str:
        return "Bitget"
        
    @property
    def url(self) -> str:
        return "wss://ws.bitget.com/v2/ws/public"

    async def _subscribe(self):
        # 订阅tickers
        args = []
        for t in self.tickers:
            args.append({
                "instType": "SPOT",
                "channel": "ticker",
                "instId": f"{t.upper()}USDT"
            })
            
        msg = {
            "op": "subscribe",
            "args": args
        }
        await self.ws.send_json(msg)
        self.logger.info(f"已订阅 {len(self.tickers)} 个交易对")
        
    async def _heartbeat(self):
        while self.running:
            try:
                await asyncio.sleep(20)
                if self.ws and not self.ws.closed:
                    await self.ws.send_str("ping")
            except Exception:
                break

    def _parse_message(self, data: Dict[str, Any]):
        # data: {"action":"snapshot","arg":{"instType":"SPOT","channel":"ticker","instId":"BTCUSDT"},"data":[...]}
        if 'arg' in data and data.get('action') in ['snapshot', 'update']:
            instId = data['arg'].get('instId', '')
            if instId.endswith('USDT'):
                ticker = instId.replace('USDT', '')
                
                ticker_data_list = data.get('data', [])
                if ticker_data_list:
                    item = ticker_data_list[0]
                    # Bitget ticker format: askPr, bidPr, lastPr
                    bid = item.get('bidPr')
                    ask = item.get('askPr')
                    last = item.get('lastPr')
                    
                    price = None
                    try:
                        if bid and ask:
                            price = (Decimal(str(bid)) + Decimal(str(ask))) / 2
                        elif last:
                            price = Decimal(str(last))
                    except:
                        pass
                        
                    if price:
                        self.prices[ticker] = price


class HyperliquidWSClient(ExchangeWebSocketClient):
    """Hyperliquid WebSocket (AllMids)"""
    
    @property
    def name(self) -> str:
        return "Hyperliquid"
        
    @property
    def url(self) -> str:
        return "wss://api.hyperliquid.xyz/ws"

    async def _subscribe(self):
        # 订阅allMids
        msg = {
            "method": "subscribe",
            "subscription": { "type": "allMids" }
        }
        await self.ws.send_json(msg)
        self.logger.info("已订阅 allMids")
        
    async def _heartbeat(self):
        while self.running:
            try:
                await asyncio.sleep(50) # Hyperliquid needs ping every 50s
                if self.ws and not self.ws.closed:
                    await self.ws.send_json({"method": "ping"})
            except Exception:
                break

    def _parse_message(self, data: Dict[str, Any]):
        # data: {"channel": "allMids", "data": {"mids": {"BTC": "68000.5", ...}}}
        if data.get('channel') == 'allMids':
            inner_data = data.get('data', {})
            prices_data = inner_data.get('mids', {})
            
            for ticker in self.tickers:
                ticker_upper = ticker.upper()
                if ticker_upper in prices_data:
                    try:
                        self.prices[ticker_upper] = Decimal(str(prices_data[ticker_upper]))
                    except:
                        pass


class BackpackWSClient(ExchangeWebSocketClient):
    """Backpack WebSocket (Ticker)"""
    
    @property
    def name(self) -> str:
        return "Backpack"
        
    @property
    def url(self) -> str:
        return "wss://ws.backpack.exchange"

    async def _subscribe(self):
        # 订阅bookTicker (Spot and Perp)
        # 格式: bookTicker.BTC_USDC
        params = []
        for t in self.tickers:
            params.append(f"bookTicker.{t.upper()}_USDC")
            params.append(f"bookTicker.{t.upper()}_USDC_PERP")
            
        msg = {
            "method": "SUBSCRIBE",
            "params": params
        }
        await self.ws.send_json(msg)
        self.logger.info(f"已订阅 {len(self.tickers)} 个交易对 (BookTicker)")
        
    async def _heartbeat(self):
        pass # Backpack usually doesn't strictly require app-level ping if protocol ping is on

    def _parse_message(self, data: Dict[str, Any]):
        # data format for bookTicker stream
        # {"e":"bookTicker", "s":"BTC_USDC", "b":"68000.5", "a":"68001.5", ...}
        inner_data = data.get('data', data)
        
        if inner_data.get('e') == 'bookTicker':
            symbol = inner_data.get('s', '')
            bid = inner_data.get('b')
            ask = inner_data.get('a')
            
            if not bid or not ask: return
            
            try:
                # 计算中间价
                price = (Decimal(str(bid)) + Decimal(str(ask))) / 2
                
                if '_USDC_PERP' in symbol:
                    # 合约: BTC_USDC_PERP -> BTC_PERP
                    ticker = symbol.replace('_USDC_PERP', '')
                    self.prices[f"{ticker}_PERP"] = price
                elif '_USDC' in symbol:
                    # 现货: BTC_USDC -> BTC
                    ticker = symbol.replace('_USDC', '')
                    self.prices[ticker] = price
            except:
                pass


# 测试代码
async def _test():
    clients = [
        BinanceWSClient(["BTC", "ETH", "SOL", "BNB", "XRP"]),
        BybitWSClient(["BTC", "ETH", "SOL", "BNB", "XRP"]),
        BitgetWSClient(["BTC", "ETH", "SOL"]),
        HyperliquidWSClient(["BTC", "ETH", "SOL"]),
        BackpackWSClient(["BTC", "ETH", "SOL"])
    ]
    
    for client in clients:
        await client.start()
    
    print("正在接收价格数据...")
    try:
        while True:
            await asyncio.sleep(2) # 每2秒打印一次
            print("\n" + "="*30)
            for client in clients:
                # 只打印前3个价格示例
                prices_str = ", ".join([f"{k}: {v}" for k, v in list(client.prices.items())[:3]])
                print(f"[{client.name}]: {{{prices_str}}}")
    except KeyboardInterrupt:
        pass

if __name__ == "__main__":
    asyncio.run(_test())
