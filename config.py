import os
from decimal import Decimal
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# ==============================================================================
# Sensitive Configuration (Loaded from .env)
# ==============================================================================

# Telegram
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_ALERT_BOT_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_ALERT_CHAT_ID')

# Backpack Exchange API Keys (loaded dynamically in monitor.py or helper here)
# We will keep the account loading logic generic, but the keys must stay in .env

# ==============================================================================
# Application Configuration
# ==============================================================================

# ------------------------------------------------------------------------------
# Price Spread Monitor (Backpack 现货 vs 合约) - 支持多币种
# ------------------------------------------------------------------------------
PRICE_MONITOR_CONFIGS = [
    {'enabled': True, 'ticker': 'SOL', 'threshold_pct': Decimal("1.0"), 'check_interval': 1, 'alert_cooldown': 0, 'alert_interval': 1},
    {'enabled': True, 'ticker': 'BTC', 'threshold_pct': Decimal("0.5"), 'check_interval': 1, 'alert_cooldown': 0, 'alert_interval': 1},
    {'enabled': True, 'ticker': 'ETH', 'threshold_pct': Decimal("0.8"), 'check_interval': 1, 'alert_cooldown': 0, 'alert_interval': 1},
]


# ------------------------------------------------------------------------------
# Volatility Monitor (Multi-Exchange, Multi-Coin)
# 支持的交易所: binance, bybit, bitget, hyperliquid, lighter, backpack
# 支持的币种: BTC, ETH, BNB, SOL, XRP, etc.
# ------------------------------------------------------------------------------
VOLATILITY_MONITOR_CONFIGS = [
    # Binance
    {'enabled': True, 'exchange': 'binance', 'ticker': 'BTC', 'time_window_sec': 60, 'threshold_pct': Decimal("1.0"), 'check_interval': 3, 'alert_interval': 1},
    {'enabled': True, 'exchange': 'binance', 'ticker': 'ETH', 'time_window_sec': 60, 'threshold_pct': Decimal("1.5"), 'check_interval': 3, 'alert_interval': 1},
    {'enabled': True, 'exchange': 'binance', 'ticker': 'SOL', 'time_window_sec': 60, 'threshold_pct': Decimal("2.0"), 'check_interval': 3, 'alert_interval': 1},
    {'enabled': True, 'exchange': 'binance', 'ticker': 'BNB', 'time_window_sec': 60, 'threshold_pct': Decimal("1.5"), 'check_interval': 3, 'alert_interval': 1},
    {'enabled': True, 'exchange': 'binance', 'ticker': 'XRP', 'time_window_sec': 60, 'threshold_pct': Decimal("2.0"), 'check_interval': 3, 'alert_interval': 1},
    
    # Bybit
    {'enabled': True, 'exchange': 'bybit', 'ticker': 'BTC', 'time_window_sec': 60, 'threshold_pct': Decimal("1.0"), 'check_interval': 3, 'alert_interval': 1},
    {'enabled': True, 'exchange': 'bybit', 'ticker': 'ETH', 'time_window_sec': 60, 'threshold_pct': Decimal("1.5"), 'check_interval': 3, 'alert_interval': 1},
    {'enabled': True, 'exchange': 'bybit', 'ticker': 'SOL', 'time_window_sec': 60, 'threshold_pct': Decimal("2.0"), 'check_interval': 3, 'alert_interval': 1},
    {'enabled': True, 'exchange': 'bybit', 'ticker': 'BNB', 'time_window_sec': 60, 'threshold_pct': Decimal("1.5"), 'check_interval': 3, 'alert_interval': 1},
    {'enabled': True, 'exchange': 'bybit', 'ticker': 'XRP', 'time_window_sec': 60, 'threshold_pct': Decimal("2.0"), 'check_interval': 3, 'alert_interval': 1},
    
    # Bitget
    {'enabled': True, 'exchange': 'bitget', 'ticker': 'BTC', 'time_window_sec': 60, 'threshold_pct': Decimal("1.0"), 'check_interval': 3, 'alert_interval': 1},
    {'enabled': True, 'exchange': 'bitget', 'ticker': 'ETH', 'time_window_sec': 60, 'threshold_pct': Decimal("1.5"), 'check_interval': 3, 'alert_interval': 1},
    {'enabled': True, 'exchange': 'bitget', 'ticker': 'SOL', 'time_window_sec': 60, 'threshold_pct': Decimal("2.0"), 'check_interval': 3, 'alert_interval': 1},
    
    # Hyperliquid
    {'enabled': True, 'exchange': 'hyperliquid', 'ticker': 'BTC', 'time_window_sec': 60, 'threshold_pct': Decimal("1.0"), 'check_interval': 3, 'alert_interval': 1},
    {'enabled': True, 'exchange': 'hyperliquid', 'ticker': 'ETH', 'time_window_sec': 60, 'threshold_pct': Decimal("1.5"), 'check_interval': 3, 'alert_interval': 1},
    {'enabled': True, 'exchange': 'hyperliquid', 'ticker': 'SOL', 'time_window_sec': 60, 'threshold_pct': Decimal("2.0"), 'check_interval': 3, 'alert_interval': 1},
    
    # Lighter (API不返回价格数据,暂时禁用)
    {'enabled': False, 'exchange': 'lighter', 'ticker': 'BTC', 'time_window_sec': 60, 'threshold_pct': Decimal("1.0"), 'check_interval': 3, 'alert_interval': 1},
    {'enabled': False, 'exchange': 'lighter', 'ticker': 'ETH', 'time_window_sec': 60, 'threshold_pct': Decimal("1.5"), 'check_interval': 3, 'alert_interval': 1},
    {'enabled': False, 'exchange': 'lighter', 'ticker': 'SOL', 'time_window_sec': 60, 'threshold_pct': Decimal("2.0"), 'check_interval': 3, 'alert_interval': 1},
    
    
    # Backpack
    {'enabled': True, 'exchange': 'backpack', 'ticker': 'BTC', 'time_window_sec': 60, 'threshold_pct': Decimal("1.0"), 'check_interval': 3, 'alert_interval': 1},
    {'enabled': True, 'exchange': 'backpack', 'ticker': 'ETH', 'time_window_sec': 60, 'threshold_pct': Decimal("1.5"), 'check_interval': 3, 'alert_interval': 1},
    {'enabled': True, 'exchange': 'backpack', 'ticker': 'SOL', 'time_window_sec': 60, 'threshold_pct': Decimal("2.0"), 'check_interval': 3, 'alert_interval': 1},
]


# ------------------------------------------------------------------------------
# Position Monitor (Backpack Hedging)
# ------------------------------------------------------------------------------
POSITION_MONITOR_GLOBAL_CONFIG = {
    'enabled': True,
    'check_interval': 10,
    'alert_type': 'telegram',
    'alert_interval': 60
}

# Per-Ticker Configuration for Position Monitor
# Define distinct thresholds for each symbol here.
POSITION_TICKER_CONFIGS = {
    'SOL': {
        'diff_threshold': Decimal("3.0"),
        'enabled': True
    },
    'BTC': {
        'diff_threshold': Decimal("0.005"), # Tighter threshold for BTC
        'enabled': True
    },
    # Add more tickers here as needed
    # 'ETH': {
    #     'diff_threshold': Decimal("5.0"),
    #     'enabled': True
    # }
}

# ------------------------------------------------------------------------------
# Deribit IV (DVOL) Monitor - 复合条件报警
# 监控Deribit隐含波动率指数(DVOL)的波动，当以下两个条件同时满足时触发警报：
#   1. DVOL在time_window_sec内的波动幅度超过iv_volatility_threshold
#   2. Binance BTC 1分钟价格波动率超过btc_volatility_threshold_pct
# API: https://www.deribit.com/api/v2/public/get_volatility_index_data
# 参考页面: https://www.deribit.com/statistics/BTC/volatility-index
# ------------------------------------------------------------------------------
DERIBIT_IV_MONITOR_CONFIGS = [
    {
        'enabled': True,
        'currency': 'BTC',
        'iv_volatility_threshold': Decimal("3.0"),   # DVOL波动阈值（百分比变动幅度，如3%即从50波动到51.5）
        'time_window_sec': 120,                       # DVOL波动时间窗口（秒），2分钟
        'btc_volatility_threshold_pct': Decimal("1.0"),  # Binance BTC价格波动阈值（%），1分钟内
        'check_interval': 5,                          # 检查间隔（秒）
        'alert_interval': 60,                         # 持续提醒间隔（秒）
    },
]
