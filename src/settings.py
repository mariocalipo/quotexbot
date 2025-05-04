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