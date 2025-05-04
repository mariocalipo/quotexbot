from pathlib import Path
from dotenv import load_dotenv
import os

load_dotenv(dotenv_path=Path(__file__).parent.parent / ".env")

EMAIL = os.getenv("EMAIL")
PASSWORD = os.getenv("PASSWORD")
IS_DEMO = os.getenv("IS_DEMO", "true").lower() in ("1", "true", "yes")
MAX_RETRIES = int(os.getenv("MAX_RETRIES", "3"))
INITIAL_BACKOFF = float(os.getenv("INITIAL_BACKOFF", "1"))