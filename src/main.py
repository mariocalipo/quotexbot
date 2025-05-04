#!/usr/bin/env python3
import logging
import sys
import asyncio
from pathlib import Path

root = Path(__file__).parent
sys.path.insert(0, str(root))

from settings import EMAIL, PASSWORD, IS_DEMO
from logging_config import setup_logging
from core import run

async def main():
    setup_logging()
    await run(EMAIL, PASSWORD, IS_DEMO)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception:
        logging.getLogger().exception("Unhandled exception in main")
        sys.exit(1)