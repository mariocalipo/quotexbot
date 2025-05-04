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

# MACD Configuration
MACD_INDICATOR = os.getenv("MACD_INDICATOR", "false").lower() in ("true", "yes", "1")  # Disabled by default
MACD_FAST_PERIOD = int(os.getenv("MACD_FAST_PERIOD", "12"))    # Default: fast_period=12
MACD_SLOW_PERIOD = int(os.getenv("MACD_SLOW_PERIOD", "26"))    # Default: slow_period=26
MACD_SIGNAL_PERIOD = int(os.getenv("MACD_SIGNAL_PERIOD", "9")) # Default: signal_period=9
MACD_MIN = float(os.getenv("MACD_MIN", "-inf"))  # Default: no minimum filter
MACD_MAX = float(os.getenv("MACD_MAX", "inf"))   # Default: no maximum filter

# SMA Configuration
SMA_INDICATOR = os.getenv("SMA_INDICATOR", "false").lower() in ("true", "yes", "1")  # Disabled by default
SMA_PERIOD = int(os.getenv("SMA_PERIOD", "20"))  # Default: period=20
SMA_MIN = float(os.getenv("SMA_MIN", "-inf"))    # Default: no minimum filter
SMA_MAX = float(os.getenv("SMA_MAX", "inf"))     # Default: no maximum filter

# Add more indicators as needed (EMA, BOLLINGER, STOCHASTIC, ATR, ADX, ICHIMOKU)