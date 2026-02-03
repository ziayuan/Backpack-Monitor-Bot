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
# Price Monitor (Difference/Spread)
# ------------------------------------------------------------------------------
PRICE_MONITOR_CONFIG = {
    'enabled': True,
    'ticker': 'SOL',
    'threshold_pct': Decimal("2.0"),
    'check_interval': 1,
    'alert_type': 'telegram',
    'alert_cooldown': 0,
    'alert_interval': 1
}

# ------------------------------------------------------------------------------
# Volatility Monitor
# ------------------------------------------------------------------------------
VOLATILITY_MONITOR_CONFIG = {
    'enabled': True,
    'ticker': 'BTC',
    'time_window_sec': 60,
    'threshold_pct': Decimal("1.0"),
    'check_interval': 1,
    'alert_type': 'telegram',
    'alert_interval': 1
}

# ------------------------------------------------------------------------------
# Price Target Monitor (Bybit/Binance)
# ------------------------------------------------------------------------------
# Default settings for targets
PRICE_TARGET_DEFAULTS = {
    'enabled': False,
    'exchange': 'bybit',
    'check_interval': 1,
    'alert_type': 'telegram',
    'alert_interval': 1
}

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
