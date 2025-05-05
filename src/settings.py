from pathlib import Path
from dotenv import load_dotenv
import os

# Load environment variables from .env file
load_dotenv(dotenv_path=Path(__file__).parent.parent / ".env")

# Account settings
EMAIL = os.getenv("EMAIL")
PASSWORD = os.getenv("PASSWORD")
IS_DEMO = os.getenv("IS_DEMO", "true").lower() in ("1", "true", "yes")  # Use true for Demo account, false for Real

# General settings
TIMEFRAME = os.getenv("TIMEFRAME", "1M").upper()  # Default to 1M timeframe for indicators and payout checks
MIN_PAYOUT = float(os.getenv("MIN_PAYOUT", "0"))  # Minimum payout percentage (0 for no filtering)
ASSETS = os.getenv("ASSETS", "").split(",") if os.getenv("ASSETS") else []  # Comma-separated list of assets, empty for all OTC
SORT_BY = os.getenv("SORT_BY", "payout").lower()  # Sort assets by payout or price
SORT_ORDER = os.getenv("SORT_ORDER", "desc").lower()  # Sort order: ascending or descending

# RSI Configuration
RSI_INDICATOR = os.getenv("RSI_INDICATOR", "true").lower() in ("true", "yes", "1")  # Enable RSI by default
RSI_PERIOD = int(os.getenv("RSI_PERIOD", "14"))  # RSI period, default 14
RSI_MIN = float(os.getenv("RSI_MIN", "-inf"))  # Minimum RSI filter, default no limit
RSI_MAX = float(os.getenv("RSI_MAX", "inf"))  # Maximum RSI filter, default no limit
RSI_BUY_THRESHOLD = float(os.getenv("RSI_BUY_THRESHOLD", "35"))  # Trigger CALL if RSI < this value
RSI_SELL_THRESHOLD = float(os.getenv("RSI_SELL_THRESHOLD", "65"))  # Trigger PUT if RSI > this value

# SMA Configuration
SMA_INDICATOR = os.getenv("SMA_INDICATOR", "true").lower() in ("true", "yes", "1")  # Enable SMA for trend confirmation
SMA_PERIOD = int(os.getenv("SMA_PERIOD", "20"))  # SMA period, default 20
SMA_MIN = float(os.getenv("SMA_MIN", "-inf"))  # Minimum SMA filter, default no limit
SMA_MAX = float(os.getenv("SMA_MAX", "inf"))  # Maximum SMA filter, default no limit

# EMA Configuration
EMA_INDICATOR = os.getenv("EMA_INDICATOR", "false").lower() in ("true", "yes", "1")  # Disabled by default
EMA_PERIOD = int(os.getenv("EMA_PERIOD", "20"))  # EMA period, default 20
EMA_MIN = float(os.getenv("EMA_MIN", "-inf"))  # Minimum EMA filter, default no limit
EMA_MAX = float(os.getenv("EMA_MAX", "inf"))  # Maximum EMA filter, default no limit

# ATR Configuration
ATR_INDICATOR = os.getenv("ATR_INDICATOR", "true").lower() in ("true", "yes", "1")  # Enable ATR for volatility check
ATR_PERIOD = int(os.getenv("ATR_PERIOD", "14"))  # ATR period, default 14
ATR_MIN = float(os.getenv("ATR_MIN", "-inf"))  # Minimum ATR filter, default no limit
ATR_MAX = float(os.getenv("ATR_MAX", "0.05"))  # Maximum ATR for PUT signals, default 0.05

# Trading Configuration
TRADE_ENABLED = os.getenv("TRADE_ENABLED", "false").lower() in ("true", "yes", "1")  # Disable trading by default
TRADE_PERCENTAGE = float(os.getenv("TRADE_PERCENTAGE", "5"))  # Base trade size: 5% of balance
TRADE_PERCENTAGE_MIN = float(os.getenv("TRADE_PERCENTAGE_MIN", "2"))  # Minimum trade size after losses: 2%
TRADE_PERCENTAGE_MAX = float(os.getenv("TRADE_PERCENTAGE_MAX", "5"))  # Maximum trade size after wins: 5%
TRADE_DURATION = int(os.getenv("TRADE_DURATION", "120"))  # Trade duration in seconds, default 120
TRADE_COOLDOWN = int(os.getenv("TRADE_COOLDOWN", "300"))  # Cooldown between trades per asset, default 300s
DAILY_LOSS_LIMIT = float(os.getenv("DAILY_LOSS_LIMIT", "10"))  # Daily loss limit as percentage, default 10%
CONSECUTIVE_LOSSES_THRESHOLD = int(os.getenv("CONSECUTIVE_LOSSES_THRESHOLD", "2"))  # Reduce risk after 2 losses
CONSECUTIVE_WINS_THRESHOLD = int(os.getenv("CONSECUTIVE_WINS_THRESHOLD", "2"))  # Increase risk after 2 wins