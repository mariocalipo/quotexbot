#!/usr/bin/env python3
import logging
import sys
import asyncio
from pathlib import Path
from quotexapi.stable_api import Quotex
from logging.handlers import RotatingFileHandler
import time

root = Path(__file__).parent
sys.path.insert(0, str(root))

from settings import EMAIL, PASSWORD, IS_DEMO, TRADE_COOLDOWN
from assets import list_open_otc_assets
from trade import execute_trades
from indicators import calculate_indicators

def setup_logging():
    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG)

    log_format = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S")

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(log_format)
    console_handler.setLevel(logging.INFO)
    logger.addHandler(console_handler)

    log_file = root.parent / "quotexbot.log"
    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=5*1024*1024,
        backupCount=3
    )
    file_handler.setFormatter(log_format)
    file_handler.setLevel(logging.DEBUG)
    logger.addHandler(file_handler)

logger = logging.getLogger(__name__)

async def check_connection(client: Quotex) -> bool:
    try:
        await client.get_balance()
        logger.debug("Connection check successful.")
        return True
    except Exception as e:
        logger.error(f"Connection check failed: {e}")
        return False

async def reconnect(client: Quotex, max_attempts: int = 5) -> bool:
    attempt = 1
    while attempt <= max_attempts:
        logger.info(f"Reconnection attempt {attempt}/{max_attempts}...")
        try:
            async with asyncio.timeout(30):
                 result = await client.connect()

            if not isinstance(result, tuple):
                success = bool(result)
                reason = str(result) if not success and result is not None else None
            else:
                success, reason = result

            if success:
                logger.info("Reconnection successful!")
                try:
                    balance = await client.get_balance()
                    account_type = "Demo" if client.account_is_demo else "Real"
                    logger.info(f"Account balance ({account_type}) after reconnection: {balance:.2f} USD")
                except Exception as e:
                    logger.warning(f"Failed to get balance after reconnection: {e}")
                return True
            else:
                logger.error(f"Reconnection failed (attempt {attempt}/{max_attempts}): {reason}")
                if attempt == max_attempts:
                    logger.error("Maximum reconnection attempts reached.")
                    return False
                attempt += 1
                await asyncio.sleep(5)
        except asyncio.TimeoutError:
            logger.error(f"Reconnection attempt {attempt}/{max_attempts} timed out.")
            if attempt == max_attempts:
                 logger.error("Maximum reconnection attempts reached due to timeouts.")
                 return False
            attempt += 1
            await asyncio.sleep(5)
        except Exception as e:
            logger.error(f"Unexpected error during reconnection (attempt {attempt}/{max_attempts}): {e}", exc_info=True)
            if attempt == max_attempts:
                 logger.error("Maximum reconnection attempts reached due to unexpected errors.")
                 return False
            attempt += 1
            await asyncio.sleep(5)
    return False


async def main():
    setup_logging()
    logger.info("Starting Quotex trading bot...")

    if not EMAIL or not PASSWORD:
        logger.error("Email or password not provided in environment variables (.env). Exiting.")
        return

    logger.info("Initializing Quotex client...")
    client = Quotex(EMAIL, PASSWORD)
    client.account_is_demo = 1 if IS_DEMO else 0
    client.totp_prompt = False

    try:
        logger.info("Attempting to connect to Quotex...")
        async with asyncio.timeout(60):
            max_attempts = 5
            attempt = 1
            while attempt <= max_attempts:
                result = await client.connect()

                if not isinstance(result, tuple):
                     success = bool(result)
                     reason = str(result) if not success and result is not None else None
                else:
                    success, reason = result

                if success:
                    logger.info("Connection established successfully!")
                    break
                else:
                    logger.error(f"Connection failed (attempt {attempt}/{max_attempts}): {reason}")
                    if attempt == max_attempts:
                        logger.error("Maximum connection attempts reached. Exiting.")
                        return
                    attempt += 1
                    await asyncio.sleep(5)
            else:
                 logger.error("Connection loop finished without success. Check error logs.")
                 return

    except asyncio.TimeoutError:
        logger.error("Initial connection attempt timed out after 60 seconds. Exiting.")
        return
    except Exception as e:
        logger.error(f"Unexpected error during initial connection: {e}", exc_info=True)
        return

    try:
        balance = await client.get_balance()
        account_type = "Demo" if client.account_is_demo else "Real"
        logger.info(f"Account balance ({account_type}): {balance:.2f} USD")
    except Exception as e:
        logger.error(f"Failed to retrieve account balance: {e}", exc_info=True)
        return

    while True:
        start_time = time.time()
        logger.info("-" * 50)
        logger.info(f"Starting new main cycle...")

        try:
            logger.info("Listing and filtering open OTC assets...")
            open_assets = await list_open_otc_assets(client)

            if open_assets:
                logger.info(f"Tradable OTC assets found in this cycle ({len(open_assets)}): {open_assets}")
                logger.info("Calculating technical indicators for the filtered tradable assets...")
                indicators = await calculate_indicators(client, open_assets)

                logger.info("Executing trading logic based on assets and indicators...")
                await execute_trades(client, open_assets, indicators)

            else:
                logger.info("No tradable OTC assets found in this cycle based on current criteria.")

        except Exception as e:
            logger.error(f"Error during main cycle execution: {e}", exc_info=True)

        logger.debug("Checking connection status...")
        if not await check_connection(client):
            logger.warning("Connection lost. Attempting to reconnect...")
            if not await reconnect(client):
                logger.error("Failed to reconnect after connection loss. Exiting.")
                return

        end_time = time.time()
        duration = end_time - start_time
        wait_time = max(0, TRADE_COOLDOWN - duration)

        logger.info(f"Main cycle completed in {duration:.2f} seconds.")
        if wait_time > 0:
             logger.info(f"Waiting for {wait_time:.2f} seconds before the next cycle (based on TRADE_COOLDOWN={TRADE_COOLDOWN}s).")
             await asyncio.sleep(wait_time)
        else:
             logger.info(f"Cycle execution time ({duration:.2f}s) is longer than or equal to TRADE_COOLDOWN ({TRADE_COOLDOWN}s). Continuing immediately.")
        logger.info("-" * 50)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped manually by user (KeyboardInterrupt).")
    except Exception as e:
        logger.critical(f"Fatal error occurred during bot execution: {e}", exc_info=True)