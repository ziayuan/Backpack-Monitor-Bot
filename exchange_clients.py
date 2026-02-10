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



# 共享会话
_SHARED_SESSION: Optional[aiohttp.ClientSession] = None

async def get_shared_session() -> aiohttp.ClientSession:
    """获取共享的aiohttp session"""
    global _SHARED_SESSION
    if _SHARED_SESSION is None or _SHARED_SESSION.closed:
        # 设置连接池限制和DNS缓存
        connector = aiohttp.TCPConnector(limit=100, ttl_dns_cache=300)
        _SHARED_SESSION = aiohttp.ClientSession(connector=connector)
    return _SHARED_SESSION

async def close_shared_session():
    """关闭共享session"""
    global _SHARED_SESSION
    if _SHARED_SESSION and not _SHARED_SESSION.closed:
        await _SHARED_SESSION.close()


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
            session = await get_shared_session()
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
        
        try:
            session = await get_shared_session()
            for category in ["linear", "spot"]:
                url = f"{self.BASE_URL}/tickers?category={category}&symbol={symbol}"
                try:
                    async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as response:
                        if response.status == 200:
                            data = await response.json()
                            if data.get('result', {}).get('list'):
                                ticker_data = data['result']['list'][0]
                                if 'lastPrice' in ticker_data:
                                    return Decimal(str(ticker_data['lastPrice']))
                except Exception:
                    continue
        except Exception as e:
            print(f"⚠️ Bybit 获取 {ticker} 价格失败: {e}")
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
            session = await get_shared_session()
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
            session = await get_shared_session()
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
        """获取Lighter价格"""
        return None # 暂不支持


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
            session = await get_shared_session()
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
    """获取指定交易所的币种价格"""
    exchange_lower = exchange.lower()
    client = EXCHANGE_CLIENTS.get(exchange_lower)
    
    if not client:
        return None
    
    return await client.get_price(ticker)


def get_supported_exchanges() -> list:
    """获取支持的交易所列表"""
    return list(EXCHANGE_CLIENTS.keys())


# 测试代码
async def _test():
    """测试所有交易所的价格获取"""
    tickers = ["BTC", "ETH", "SOL"]
    
    try:
        for exchange in get_supported_exchanges():
            if exchange == 'lighter': continue
            print(f"\n=== {exchange.upper()} ===")
            for ticker in tickers:
                price = await get_exchange_price(exchange, ticker)
                if price:
                    print(f"  {ticker}: ${price:.2f}")
                else:
                    print(f"  {ticker}: ❌ 获取失败")
    finally:
        await close_shared_session()


if __name__ == "__main__":
    asyncio.run(_test())

if __name__ == "__main__":
    asyncio.run(_test())
