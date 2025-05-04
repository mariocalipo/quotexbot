from pathlib import Path
from dotenv import load_dotenv
import os

load_dotenv(dotenv_path=Path(__file__).parent.parent / ".env")

EMAIL = os.getenv("EMAIL")
PASSWORD = os.getenv("PASSWORD")
IS_DEMO = os.getenv("IS_DEMO", "true").lower() in ("1", "true", "yes")
TIMEFRAME = os.getenv("TIMEFRAME", "1M").upper()  # Default to 1M
MIN_PAYOUT = float(os.getenv("MIN_PAYOUT", "0"))  # Default to 0 (no filtering)
ASSETS = os.getenv("ASSETS", "").split(",") if os.getenv("ASSETS") else []  # Default to empty list
SORT_BY = os.getenv("SORT_BY", "payout").lower()  # Default to payout
SORT_ORDER = os.getenv("SORT_ORDER", "desc").lower()  # Default to descending

# RSI Configuration
RSI_INDICATOR = os.getenv("RSI_INDICATOR", "true").lower() in ("true", "yes", "1")  # Enable RSI by default
RSI_PERIOD = int(os.getenv("RSI_PERIOD", "14"))  # Default: period=14
RSI_MIN = float(os.getenv("RSI_MIN", "-inf"))    # Default: no minimum filter
RSI_MAX = float(os.getenv("RSI_MAX", "inf"))     # Default: no maximum filter

# SMA Configuration
SMA_INDICATOR = os.getenv("SMA_INDICATOR", "false").lower() in ("true", "yes", "1")  # Disabled by default
SMA_PERIOD = int(os.getenv("SMA_PERIOD", "20"))  # Default: period=20
SMA_MIN = float(os.getenv("SMA_MIN", "-inf"))    # Default: no minimum filter
SMA_MAX = float(os.getenv("SMA_MAX", "inf"))     # Default: no maximum filter

# EMA Configuration
EMA_INDICATOR = os.getenv("EMA_INDICATOR", "false").lower() in ("true", "yes", "1")  # Disabled by default
EMA_PERIOD = int(os.getenv("EMA_PERIOD", "20"))  # Default: period=20
EMA_MIN = float(os.getenv("EMA_MIN", "-inf"))    # Default: no minimum filter
EMA_MAX = float(os.getenv("EMA_MAX", "inf"))     # Default: no maximum filter

# ATR Configuration
ATR_INDICATOR = os.getenv("ATR_INDICATOR", "false").lower() in ("true", "yes", "1")  # Disabled by default
ATR_PERIOD = int(os.getenv("ATR_PERIOD", "14"))  # Default: period=14
ATR_MIN = float(os.getenv("ATR_MIN", "-inf"))    # Default: no minimum filter
ATR_MAX = float(os.getenv("ATR_MAX", "inf"))     # Default: no maximum filter

# Trading Configuration
TRADE_ENABLED = os.getenv("TRADE_ENABLED", "false").lower() in ("true", "yes", "1")  # Disable trading by default
TRADE_PERCENTAGE = float(os.getenv("TRADE_PERCENTAGE", "1"))  # Default: 1% of the balance per trade
TRADE_DURATION = int(os.getenv("TRADE_DURATION", "120"))  # Default: 120 seconds (increased from 60)
RSI_BUY_THRESHOLD = float(os.getenv("RSI_BUY_THRESHOLD", "30"))  # Buy if RSI < 30 (oversold)
RSI_SELL_THRESHOLD = float(os.getenv("RSI_SELL_THRESHOLD", "70"))  # Sell if RSI > 70 (overbought)