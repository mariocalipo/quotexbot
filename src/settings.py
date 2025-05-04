from pathlib import Path
from dotenv import load_dotenv
import os
import logging

logger = logging.getLogger(__name__)

load_dotenv(dotenv_path=Path(__file__).parent.parent / ".env")

EMAIL = os.getenv("EMAIL")
PASSWORD = os.getenv("PASSWORD")
IS_DEMO = os.getenv("IS_DEMO", "true").lower() in ("1", "true", "yes")
TIMEFRAME_STR = os.getenv("TIMEFRAME", "1M").upper()

def parse_timeframe(timeframe_str: str) -> int:
    """Converts timeframe string (e.g., '1M', '5M') to seconds."""
    try:
        if timeframe_str.endswith('S'):
            return int(timeframe_str[:-1])
        elif timeframe_str.endswith('M'):
            return int(timeframe_str[:-1]) * 60
        elif timeframe_str.endswith('H'):
            return int(timeframe_str[:-1]) * 3600
        elif timeframe_str.endswith('D'):
            return int(timeframe_str[:-1]) * 86400
        else:
            # Default to 60 seconds if format is unknown
            logger.warning(f"Unknown TIMEFRAME format: {timeframe_str}. Using 60 seconds.")
            return 60
    except ValueError:
        logger.warning(f"Invalid number in TIMEFRAME: {timeframe_str}. Using 60 seconds.")
        return 60
    except Exception as e:
        logger.warning(f"Error parsing TIMEFRAME {timeframe_str}: {e}. Using 60 seconds.")
        return 60

TIMEFRAME_SECONDS = parse_timeframe(TIMEFRAME_STR)

MIN_PAYOUT = float(os.getenv("MIN_PAYOUT", "0"))
ASSETS = [asset.strip() for asset in os.getenv("ASSETS", "").split(",") if asset.strip()] if os.getenv("ASSETS") else []
SORT_BY = os.getenv("SORT_BY", "payout").lower()
SORT_ORDER = os.getenv("SORT_ORDER", "desc").lower()

# RSI
RSI_INDICATOR = os.getenv("RSI_INDICATOR", "true").lower() in ("true", "yes", "1")
RSI_PERIOD = int(os.getenv("RSI_PERIOD", "14"))
RSI_MIN = float(os.getenv("RSI_MIN", "-inf"))
RSI_MAX = float(os.getenv("RSI_MAX", "inf"))
RSI_BUY_THRESHOLD = float(os.getenv("RSI_BUY_THRESHOLD", "35"))
RSI_SELL_THRESHOLD = float(os.getenv("RSI_SELL_THRESHOLD", "65"))

# SMA
SMA_INDICATOR = os.getenv("SMA_INDICATOR", "true").lower() in ("true", "yes", "1")
SMA_PERIOD = int(os.getenv("SMA_PERIOD", "20"))
SMA_MIN = float(os.getenv("SMA_MIN", "-inf"))
SMA_MAX = float(os.getenv("SMA_MAX", "inf"))

# EMA
EMA_INDICATOR = os.getenv("EMA_INDICATOR", "false").lower() in ("true", "yes", "1")
EMA_PERIOD = int(os.getenv("EMA_PERIOD", "20"))
EMA_MIN = float(os.getenv("EMA_MIN", "-inf"))
EMA_MAX = float(os.getenv("EMA_MAX", "inf"))

# ATR
ATR_INDICATOR = os.getenv("ATR_INDICATOR", "true").lower() in ("true", "yes", "1")
ATR_PERIOD = int(os.getenv("ATR_PERIOD", "14"))
ATR_MIN = float(os.getenv("ATR_MIN", "-inf"))
ATR_MAX = float(os.getenv("ATR_MAX", "0.05"))

# Trading
TRADE_ENABLED = os.getenv("TRADE_ENABLED", "false").lower() in ("true", "yes", "1")
TRADE_PERCENTAGE = float(os.getenv("TRADE_PERCENTAGE", "5"))
TRADE_PERCENTAGE_MIN = float(os.getenv("TRADE_PERCENTAGE_MIN", "2"))
TRADE_PERCENTAGE_MAX = float(os.getenv("TRADE_PERCENTAGE_MAX", "5"))
TRADE_DURATION = int(os.getenv("TRADE_DURATION", "120"))
TRADE_COOLDOWN = int(os.getenv("TRADE_COOLDOWN", "300"))
DAILY_LOSS_LIMIT = float(os.getenv("DAILY_LOSS_LIMIT", "10"))
CONSECUTIVE_LOSSES_THRESHOLD = int(os.getenv("CONSECUTIVE_LOSSES_THRESHOLD", "2"))
CONSECUTIVE_WINS_THRESHOLD = int(os.getenv("CONSECUTIVE_WINS_THRESHOLD", "2"))