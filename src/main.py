#!/usr/bin/env python3
import logging
import sys
from pathlib import Path

root = Path(__file__).parent
sys.path.insert(0, str(root))

from settings import EMAIL, PASSWORD, IS_DEMO
from core import connect_and_list_assets

def setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

def main():
    setup_logging()
    connect_and_list_assets(EMAIL, PASSWORD, IS_DEMO)

if __name__ == "__main__":
    main()