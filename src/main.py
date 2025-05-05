#!/usr/bin/env python3
import logging
import sys
import asyncio
from pathlib import Path
from quotexapi.stable_api import Quotex
from logging.handlers import RotatingFileHandler
import time

# Adjust the root path to correctly find modules
root = Path(__file__).parent
sys.path.insert(0, str(root))

from settings import EMAIL, PASSWORD, IS_DEMO, TRADE_COOLDOWN, TIMEFRAME
from assets import list_open_otc_assets
from trade import execute_trades
from indicators import calculate_indicators

def setup_logging():
    """Configure logging format and level for the application, with output to both console and file."""
    if not logging.getLogger().hasHandlers():
        logger = logging.getLogger()
        logger.setLevel(logging.DEBUG)
        log_format = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(log_format)
        console_handler.setLevel(logging.INFO)
        logger.addHandler(console_handler)
        log_file = root.parent / "quotexbot.log"
        log_file.parent.mkdir(parents=True, exist_ok=True)
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
    """Check if the connection is still active by attempting a simple API call."""
    logger.debug("Performing connection check...")
    try:
        balance = await client.get_balance()
        logger.debug(f"Connection check successful. Current balance: {balance:.2f} USD")
        return True
    except Exception as e:
        logger.warning(f"Connection check failed: {e}", exc_info=False)
        return False

async def reconnect(client: Quotex, max_attempts: int = 5) -> bool:
    """Attempt to reconnect to the Quotex API with exponential backoff."""
    logger.info("Attempting to reconnect...")
    for attempt in range(1, max_attempts + 1):
        logger.info(f"Reconnection attempt {attempt}/{max_attempts}...")
        try:
            result = await client.connect()
            if isinstance(result, tuple) and len(result) == 2:
                success, reason = result
            elif isinstance(result, bool):
                success = result
                reason = "Connection failed" if not success else None
            else:
                logger.error(f"Unexpected return type from client.connect(): {type(result)}. Result: {result}")
                success = False
                reason = f"Unexpected connect response: {result}"

            if success:
                logger.info("Reconnection successful!")
                try:
                    balance = await client.get_balance()
                    account_type = "Demo" if client.account_is_demo > 0 else "Real"
                    logger.info(f"Account balance ({account_type}) after reconnection: {balance:.2f} USD")
                except Exception as e:
                    logger.warning(f"Failed to get balance after reconnection: {e}", exc_info=False)
                return True
            logger.warning(f"Attempt {attempt} failed: {reason}")
        except Exception as e:
            logger.error(f"Error in attempt {attempt}: {e}", exc_info=False)
        delay = min(5 * (2 ** attempt), 60)  # Exponential backoff: 5s, 10s, 20s, 40s, max 60s
        await asyncio.sleep(delay)
    logger.critical("Failed to reconnect after max attempts.")
    return False

async def main():
    """Main asynchronous function to run the trading bot."""
    setup_logging()
    logger.info("Starting Quotex trading bot...")

    if not EMAIL or not PASSWORD:
        logger.critical("Email or password not provided in environment variables (.env). Exiting.")
        return

    logger.info("Initializing Quotex client...")
    client = Quotex(EMAIL, PASSWORD, lang="pt")
    client.set_account_mode("PRACTICE" if IS_DEMO else "REAL")
    client.totp_prompt = False

    max_init_attempts = 5
    init_attempt = 1
    init_delay = 5
    connected = False

    while init_attempt <= max_init_attempts and not connected:
        logger.info(f"Attempting to connect to Quotex (Attempt {init_attempt}/{max_init_attempts})...")
        try:
            result = await client.connect()
            if isinstance(result, tuple) and len(result) == 2:
                success, reason = result
            elif isinstance(result, bool):
                success = result
                reason = "Connection failed" if not success else None
            else:
                logger.error(f"Unexpected return type from client.connect(): {type(result)}. Result: {result}")
                success = False
                reason = f"Unexpected connect response: {result}"

            if success:
                logger.info("Connection established successfully!")
                connected = True
            else:
                logger.error(f"Connection attempt {init_attempt} failed: {reason}")
        except Exception as e:
            logger.error(f"An unexpected error occurred during initial connection attempt {init_attempt}: {e}", exc_info=False)

        if not connected:
            if init_attempt == max_init_attempts:
                logger.critical("Maximum initial connection attempts reached. Exiting.")
                return
            init_attempt += 1
            await asyncio.sleep(init_delay)

    if not connected:
        logger.critical("Could not establish initial connection after multiple attempts. Exiting.")
        return

    try:
        balance = await client.get_balance()
        account_type = "Demo" if client.account_is_demo > 0 else "Real"
        logger.info(f"Account balance ({account_type}): {balance:.2f} USD")
        logger.info("-" * 50)
    except Exception as e:
        logger.warning(f"Failed to retrieve initial account balance: {e}", exc_info=False)

    logger.info("Entering main trading cycle loop.")
    while True:
        start_time_cycle = time.time()
        logger.info("-" * 50)
        logger.info("Starting new main cycle...")

        try:
            logger.info("Listing and filtering open OTC assets...")
            open_assets_details = await list_open_otc_assets(client)
            assets_for_trade = []
            valid_assets_details_for_log = []
            skipped_items_count = 0

            if not open_assets_details:
                logger.info("No open OTC assets found with sufficient payout or matching criteria.")
            else:
                logger.debug(f"Processing {len(open_assets_details)} items returned by list_open_otc_assets.")
                for item in open_assets_details:
                    if isinstance(item, (list, tuple)) and len(item) == 2:
                        try:
                            asset, payout = item
                            if isinstance(asset, str) and asset and isinstance(payout, (int, float)):
                                assets_for_trade.append(asset)
                                valid_assets_details_for_log.append((asset, payout))
                            else:
                                logger.warning(f"Skipping item: Unexpected types/values. Expected (str, number), got ({type(asset)}, {type(payout)}). Item: {item}")
                                skipped_items_count += 1
                        except Exception as e:
                            logger.warning(f"Skipping item: Failed to unpack {item}: {e}")
                            skipped_items_count += 1
                    else:
                        item_len = len(item) if isinstance(item, (list, tuple)) else 'N/A'
                        logger.warning(f"Skipping item: Expected list/tuple of size 2, got {type(item)} of size {item_len}. Item: {item}")
                        skipped_items_count += 1

                if skipped_items_count > 0:
                    logger.warning(f"Filtered out {skipped_items_count} items due to unexpected format.")

            initial_indicators_log = {}
            initial_prices_log = {}
            if assets_for_trade:
                logger.debug(f"Processing indicators and prices for {len(assets_for_trade)} valid assets.")
                initial_indicators_log = await calculate_indicators(client, assets_for_trade)
                try:
                    price_tasks = [client.get_realtime_price(asset) for asset in assets_for_trade]
                    price_data_list = await asyncio.gather(*price_tasks, return_exceptions=True)
                    for i, asset in enumerate(assets_for_trade):
                        price_data = price_data_list[i]
                        if isinstance(price_data, list) and price_data and isinstance(price_data[0], dict):
                            initial_prices_log[asset] = price_data[0].get('price', 'N/A')
                        elif isinstance(price_data, dict) and price_data:
                            initial_prices_log[asset] = price_data.get('price', 'N/A')
                        elif isinstance(price_data, Exception):
                            logger.warning(f"Exception fetching initial price for {asset}: {price_data}", exc_info=False)
                            initial_prices_log[asset] = 'N/A'
                        else:
                            logger.warning(f"Could not get initial price for {asset}: Unexpected data type {type(price_data)}")
                            initial_prices_log[asset] = 'N/A'
                except Exception as e:
                    logger.warning(f"Unexpected error during initial price fetching: {e}", exc_info=False)

                logger.info(f"--- Final list of assets for trade execution ({len(assets_for_trade)}) ---")
                for asset, payout in valid_assets_details_for_log:
                    if asset in assets_for_trade:
                        price = initial_prices_log.get(asset, "N/A")
                        indicator_values_log = initial_indicators_log.get(asset, {})
                        indicator_str = ", ".join(f"{ind}: {val:.5f}" if isinstance(val, (int, float)) and val is not None else f"{ind}: N/A" for ind, val in indicator_values_log.items())
                        logger.info(f"    - {asset}: Payout {payout}%, Price: {price}, Initial Indicators: [{indicator_str}]")
                logger.info("---------------------------------------------------")
            else:
                logger.info("No assets passed all filtering and initial trading criteria.")

            if assets_for_trade:
                logger.info("Executing trading logic...")
                await execute_trades(client, assets_for_trade, initial_indicators_log)
            else:
                logger.info("Skipping trade execution: No tradable assets.")

            logger.debug("Checking connection status before waiting...")
            if not await check_connection(client):
                logger.warning("Connection lost. Attempting to reconnect...")
                if not await reconnect(client):
                    logger.critical("Failed to reconnect. Exiting.")
                    return

        except Exception as e:
            logger.error(f"Unexpected error in main cycle: {e}", exc_info=True)

        end_time_cycle = time.time()
        cycle_duration = end_time_cycle - start_time_cycle
        wait_time_needed = max(0, TRADE_COOLDOWN - cycle_duration)

        if wait_time_needed > 0:
            logger.info(f"Main cycle completed in {cycle_duration:.2f} seconds.")
            logger.info(f"Waiting for {wait_time_needed:.2f} seconds before next cycle (TRADE_COOLDOWN={TRADE_COOLDOWN}s).")
            sleep_interval = 10
            start_wait_time = time.time()
            while True:
                time_passed_in_wait = time.time() - start_wait_time
                remaining_wait = max(0, wait_time_needed - time_passed_in_wait)
                if remaining_wait <= 1.0:
                    break
                time_until_next_log_tick = sleep_interval - (time_passed_in_wait % sleep_interval)
                if time_until_next_log_tick <= 0.01:
                    time_until_next_log_tick = sleep_interval
                sleep_duration = min(time_until_next_log_tick, remaining_wait)
                if sleep_duration > 0:
                    await asyncio.sleep(sleep_duration)
                remaining_wait = max(0, wait_time_needed - (time.time() - start_wait_time))
                if remaining_wait > 0:
                    logger.info(f"Time until next cycle: {remaining_wait:.2f} seconds remaining.")
            logger.debug("Waiting period concluded.")
        else:
            logger.info(f"Main cycle completed in {cycle_duration:.2f} seconds. No waiting needed.")

if __name__ == "__main__":
    setup_logging()
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped manually by user (KeyboardInterrupt).")
    except Exception as e:
        logger.critical(f"Fatal error during bot execution: {e}", exc_info=True)