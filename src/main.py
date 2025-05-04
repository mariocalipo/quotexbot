#!/usr/bin/env python3
import logging
import sys
import asyncio
from pathlib import Path

root = Path(__file__).parent
sys.path.insert(0, str(root))

from settings import EMAIL, PASSWORD, IS_DEMO
from core import run

def setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

async def main():
    setup_logging()
    await run(EMAIL, PASSWORD, IS_DEMO)

if __name__ == "__main__":
    asyncio.run(main())