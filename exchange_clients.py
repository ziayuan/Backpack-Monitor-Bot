"""
交易所价格获取客户端
支持多个交易所的公开价格API
"""
import aiohttp
import asyncio
from decimal import Decimal
from typing import Optional, Dict, Any
from abc import ABC, abstractmethod


class ExchangeClient(ABC):
    """交易所客户端基类"""
    
    @abstractmethod
    async def get_price(self, ticker: str) -> Optional[Decimal]:
        """获取指定币种的价格"""
        pass
    
    @property
    @abstractmethod
    def name(self) -> str:
        """交易所名称"""
        pass


class BinanceClient(ExchangeClient):
    """Binance 价格获取客户端"""
    
    BASE_URL = "https://api.binance.com/api/v3"
    
    @property
    def name(self) -> str:
        return "Binance"
    
    async def get_price(self, ticker: str) -> Optional[Decimal]:
        """获取Binance价格"""
        symbol = f"{ticker.upper()}USDT"
        url = f"{self.BASE_URL}/ticker/price?symbol={symbol}"
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as response:
                    if response.status == 200:
                        data = await response.json()
                        if 'price' in data:
                            return Decimal(str(data['price']))
        except Exception as e:
            print(f"⚠️ Binance 获取 {ticker} 价格失败: {e}")
        return None


class BybitClient(ExchangeClient):
    """Bybit 价格获取客户端"""
    
    BASE_URL = "https://api.bybit.com/v5/market"
    
    @property
    def name(self) -> str:
        return "Bybit"
    
    async def get_price(self, ticker: str) -> Optional[Decimal]:
        """获取Bybit价格 (尝试linear合约，再尝试spot)"""
        symbol = f"{ticker.upper()}USDT"
        
        for category in ["linear", "spot"]:
            url = f"{self.BASE_URL}/tickers?category={category}&symbol={symbol}"
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as response:
                        if response.status == 200:
                            data = await response.json()
                            if data.get('result', {}).get('list'):
                                ticker_data = data['result']['list'][0]
                                if 'lastPrice' in ticker_data:
                                    return Decimal(str(ticker_data['lastPrice']))
            except Exception as e:
                print(f"⚠️ Bybit ({category}) 获取 {ticker} 价格失败: {e}")
        return None


class BitgetClient(ExchangeClient):
    """Bitget 价格获取客户端"""
    
    BASE_URL = "https://api.bitget.com/api/v2"
    
    @property
    def name(self) -> str:
        return "Bitget"
    
    async def get_price(self, ticker: str) -> Optional[Decimal]:
        """获取Bitget价格"""
        symbol = f"{ticker.upper()}USDT"
        url = f"{self.BASE_URL}/spot/market/tickers?symbol={symbol}"
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as response:
                    if response.status == 200:
                        data = await response.json()
                        if data.get('data') and len(data['data']) > 0:
                            ticker_data = data['data'][0]
                            if 'lastPr' in ticker_data:
                                return Decimal(str(ticker_data['lastPr']))
        except Exception as e:
            print(f"⚠️ Bitget 获取 {ticker} 价格失败: {e}")
        return None


class HyperliquidClient(ExchangeClient):
    """Hyperliquid 价格获取客户端"""
    
    BASE_URL = "https://api.hyperliquid.xyz/info"
    
    @property
    def name(self) -> str:
        return "Hyperliquid"
    
    async def get_price(self, ticker: str) -> Optional[Decimal]:
        """获取Hyperliquid价格 (通过allMids)"""
        try:
            async with aiohttp.ClientSession() as session:
                payload = {"type": "allMids"}
                headers = {"Content-Type": "application/json"}
                async with session.post(
                    self.BASE_URL,
                    json=payload,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=5)
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        # data格式: {"BTC": "98000.5", "ETH": "3500.0", ...}
                        ticker_upper = ticker.upper()
                        if ticker_upper in data:
                            return Decimal(str(data[ticker_upper]))
        except Exception as e:
            print(f"⚠️ Hyperliquid 获取 {ticker} 价格失败: {e}")
        return None


class LighterClient(ExchangeClient):
    """Lighter 价格获取客户端"""
    
    BASE_URL = "https://mainnet.zklighter.elliot.ai/api/v1"
    
    @property
    def name(self) -> str:
        return "Lighter"
    
    async def get_price(self, ticker: str) -> Optional[Decimal]:
        """获取Lighter价格 (通过orderBooks)"""
        ticker_upper = ticker.upper()
        url = f"{self.BASE_URL}/orderBooks"
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as response:
                    if response.status == 200:
                        data = await response.json()
                        # 查找对应的市场 (通过symbol字段)
                        if data and 'order_books' in data:
                            for ob in data['order_books']:
                                if ob.get('symbol') == ticker_upper:
                                    # 需要另外获取价格数据
                                    market_id = ob.get('market_id')
                                    if market_id is not None:
                                        return await self._get_market_price(market_id)
        except Exception as e:
            print(f"⚠️ Lighter 获取 {ticker} 价格失败: {e}")
        return None
    
    async def _get_market_price(self, market_id: int) -> Optional[Decimal]:
        """获取指定市场的价格"""
        url = f"{self.BASE_URL}/orderBook?market_id={market_id}"
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as response:
                    if response.status == 200:
                        data = await response.json()
                        # 使用best bid/ask中间价
                        bids = data.get('bids', [])
                        asks = data.get('asks', [])
                        if bids and asks:
                            best_bid = Decimal(str(bids[0]['price']))
                            best_ask = Decimal(str(asks[0]['price']))
                            return (best_bid + best_ask) / 2
        except Exception as e:
            print(f"⚠️ Lighter 获取市场{market_id}价格失败: {e}")
        return None


class BackpackClient(ExchangeClient):
    """Backpack 价格获取客户端"""
    
    BASE_URL = "https://api.backpack.exchange/api/v1"
    
    @property
    def name(self) -> str:
        return "Backpack"
    
    async def get_price(self, ticker: str) -> Optional[Decimal]:
        """获取Backpack价格"""
        symbol = f"{ticker.upper()}_USDC"
        url = f"{self.BASE_URL}/ticker?symbol={symbol}"
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as response:
                    if response.status == 200:
                        data = await response.json()
                        if 'lastPrice' in data:
                            return Decimal(str(data['lastPrice']))
        except Exception as e:
            print(f"⚠️ Backpack 获取 {ticker} 价格失败: {e}")
        return None


# 交易所客户端工厂
EXCHANGE_CLIENTS: Dict[str, ExchangeClient] = {
    "binance": BinanceClient(),
    "bybit": BybitClient(),
    "bitget": BitgetClient(),
    "hyperliquid": HyperliquidClient(),
    "lighter": LighterClient(),
    "backpack": BackpackClient(),
}


async def get_exchange_price(exchange: str, ticker: str) -> Optional[Decimal]:
    """
    获取指定交易所的币种价格
    
    Args:
        exchange: 交易所名称 (binance, bybit, bitget, hyperliquid, lighter, backpack)
        ticker: 币种 (BTC, ETH, SOL, etc.)
    
    Returns:
        价格 (Decimal) 或 None
    """
    exchange_lower = exchange.lower()
    client = EXCHANGE_CLIENTS.get(exchange_lower)
    
    if not client:
        print(f"⚠️ 不支持的交易所: {exchange}")
        return None
    
    return await client.get_price(ticker)


def get_supported_exchanges() -> list:
    """获取支持的交易所列表"""
    return list(EXCHANGE_CLIENTS.keys())


# 测试代码
async def _test():
    """测试所有交易所的价格获取"""
    tickers = ["BTC", "ETH", "SOL"]
    
    for exchange in get_supported_exchanges():
        print(f"\n=== {exchange.upper()} ===")
        for ticker in tickers:
            price = await get_exchange_price(exchange, ticker)
            if price:
                print(f"  {ticker}: ${price:.2f}")
            else:
                print(f"  {ticker}: ❌ 获取失败")


if __name__ == "__main__":
    asyncio.run(_test())
