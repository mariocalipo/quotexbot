#!/usr/bin/env python3
import logging
import sys
import asyncio
from pathlib import Path
from quotexapi.stable_api import Quotex
from logging.handlers import RotatingFileHandler

root = Path(__file__).parent
sys.path.insert(0, str(root))

from settings import EMAIL, PASSWORD, IS_DEMO
from assets import list_open_otc_assets

def setup_logging():
    """Configure logging format and level for the application, with output to both console and file."""
    # Create a logger
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)  # Set the logging level

    # Define the log format
    log_format = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S")

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(log_format)
    logger.addHandler(console_handler)

    # File handler with rotation
    log_file = root.parent / "quotexbot.log"  # Save log file in the project root directory
    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=5*1024*1024,  # 5 MB per file
        backupCount=3  # Keep 3 backup files (quotexbot.log.1, quotexbot.log.2, quotexbot.log.3)
    )
    file_handler.setFormatter(log_format)
    logger.addHandler(file_handler)

async def check_connection(client: Quotex) -> bool:
    """Verify if the Quotex client is still connected by checking account balance."""
    try:
        await client.get_balance()
        return True
    except Exception as e:
        logger.error(f"Connection check failed: {e}")
        return False

async def reconnect(client: Quotex, max_attempts: int = 3) -> bool:
    """Attempt to reconnect the Quotex client with a limited number of retries."""
    attempt = 1
    while attempt <= max_attempts:
        logger.info(f"Reconnection attempt {attempt}/{max_attempts}...")
        result = await client.connect()
        if isinstance(result, tuple):
            success, reason = result
        else:
            success, reason = result, None

        if success:
            logger.info("Reconnection successful!")
            return True
        else:
            logger.error(f"Reconnection failed: {reason}")
            if attempt == max_attempts:
                logger.error("Maximum reconnection attempts reached.")
                return False
            attempt += 1
            await asyncio.sleep(5)
    return False

async def main():
    """Initialize the Quotex client, establish connection, display account balance, and list open OTC assets."""
    setup_logging()
    global logger
    logger = logging.getLogger(__name__)

    if not EMAIL or not PASSWORD:
        logger.error("Email or password not provided.")
        return

    logger.info("Initializing Quotex client...")
    client = Quotex(EMAIL, PASSWORD)
    client.demo_account = IS_DEMO

    # Initial connection with timeout
    try:
        async with asyncio.timeout(10):
            max_attempts = 3
            attempt = 1
            while attempt <= max_attempts:
                result = await client.connect()
                if isinstance(result, tuple):
                    success, reason = result
                else:
                    success, reason = result, None

                if success:
                    logger.info("Connection established!")
                    break
                else:
                    logger.error(f"Login failed (attempt {attempt}/{max_attempts}): {reason}")
                    if attempt == max_attempts:
                        logger.error("Maximum attempts reached. Exiting.")
                        return
                    attempt += 1
                    await asyncio.sleep(5)
    except asyncio.TimeoutError:
        logger.error("Connection attempt timed out.")
        return

    # Display account balance
    try:
        balance = await client.get_balance()
        account_type = "Demo" if IS_DEMO else "Real"
        logger.info(f"Account balance ({account_type}): {balance} USD")
    except Exception as e:
        logger.error(f"Failed to retrieve account balance: {e}")
        return

    # List open OTC assets
    await list_open_otc_assets(client)

    # Monitor connection periodically
    while True:
        if not await check_connection(client):
            logger.warning("Connection lost. Attempting to reconnect...")
            if not await reconnect(client):
                logger.error("Failed to reconnect. Exiting.")
                return
        else:
            logger.debug("Connection is active.")
        await asyncio.sleep(60)

if __name__ == "__main__":
    asyncio.run(main())