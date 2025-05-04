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

from settings import EMAIL, PASSWORD, IS_DEMO, TRADE_COOLDOWN, TIMEFRAME_SECONDS # Import TIMEFRAME_SECONDS
from assets import list_open_otc_assets
from trade import execute_trades
from indicators import calculate_indicators

def setup_logging():
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
    logger.debug("Performing connection check...")
    try:
        balance = await client.get_balance()
        logger.debug(f"Connection check successful. Balance: {balance:.2f} USD")
        return True
    except Exception as e:
        logger.warning(f"Connection check failed: {e}", exc_info=False)
        return False

async def reconnect(client: Quotex, max_attempts: int = 5) -> bool:
    logger.info("Attempting to reconnect...")
    delay = 5
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
                 logger.error(f"Unexpected return from client.connect(): {type(result)}. Result: {result}")
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
            else:
                logger.warning(f"Reconnection attempt {attempt} failed: {reason}")

        except asyncio.TimeoutError:
            logger.warning(f"Reconnection attempt {attempt}/{max_attempts} timed out.")
        except Exception as e:
            logger.error(f"Error during reconnection (attempt {attempt}/{max_attempts}): {e}", exc_info=False)

        if attempt < max_attempts:
             await asyncio.sleep(delay)
        else:
             logger.critical("Maximum reconnection attempts reached.")

    logger.critical("Failed to reconnect after multiple attempts. Exiting.")
    return False


async def main():
    setup_logging()
    logger.info("Starting Quotex trading bot...")

    if not EMAIL or not PASSWORD:
        logger.critical("Email or password not provided. Exiting.")
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
        logger.info(f"Connecting to Quotex (Attempt {init_attempt}/{max_init_attempts})...")
        try:
            result = await client.connect()
            if isinstance(result, tuple) and len(result) == 2:
                 success, reason = result
            elif isinstance(result, bool):
                 success = result
                 reason = "Connection failed" if not success else None
            else:
                 logger.error(f"Unexpected return from client.connect(): {type(result)}. Result: {result}")
                 success = False
                 reason = f"Unexpected connect response: {result}"

            if success:
                logger.info("Connection established successfully!")
                connected = True
            else:
                logger.error(f"Connection attempt {init_attempt} failed: {reason}")

        except Exception as e:
            logger.error(f"Error during initial connection attempt {init_attempt}: {e}", exc_info=False)

        if not connected:
             if init_attempt == max_init_attempts:
                  logger.critical("Maximum initial connection attempts reached. Exiting.")
                  return
             init_attempt += 1
             await asyncio.sleep(init_delay)

    if not connected:
         logger.critical("Could not establish initial connection. Exiting.")
         return

    try:
        balance = await client.get_balance()
        account_type = "Demo" if client.account_is_demo > 0 else "Real"
        logger.info(f"Account balance ({account_type}): {balance:.2f} USD")
        logger.info("-" * 50)

    except Exception as e:
        logger.warning(f"Failed to retrieve initial balance: {e}", exc_info=False)


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
                 logger.info("No open OTC assets found meeting criteria.")
            else:
                 logger.debug(f"Processing {len(open_assets_details)} items from list_open_otc_assets.")
                 for item in open_assets_details:
                     if isinstance(item, (list, tuple)) and len(item) == 2:
                         try:
                             asset, payout = item
                             if isinstance(asset, str) and asset and isinstance(payout, (int, float)):
                                 assets_for_trade.append(asset)
                                 valid_assets_details_for_log.append((asset, payout))
                             else:
                                 logger.warning(f"Skipping item: Unexpected types/values for asset/payout. Item: {item}")
                                 skipped_items_count += 1
                         except Exception as unpack_e:
                             logger.warning(f"Skipping item: Failed to unpack {item}: {unpack_e}")
                             skipped_items_count += 1
                     else:
                         item_len = len(item) if isinstance(item, (list, tuple)) else 'N/A'
                         logger.warning(f"Skipping item: Unexpected format {type(item)} size {item_len}. Item: {item}")
                         skipped_items_count += 1

                 if skipped_items_count > 0:
                      logger.warning(f"Filtered out {skipped_items_count} items due to format/content issues.")

            initial_indicators_log = {}
            initial_prices_log = {}
            if assets_for_trade:
                 logger.debug(f"Processing indicators and prices for {len(assets_for_trade)} valid assets.")
                 # Pass TIMEFRAME_SECONDS for logging indicators
                 initial_indicators_log = await calculate_indicators(client, assets_for_trade, TIMEFRAME_SECONDS)
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
                                logger.warning(f"Exception fetching initial price for logging for {asset}: {price_data}")
                                initial_prices_log[asset] = 'N/A'
                           else:
                                logger.warning(f"Could not get initial price for logging for {asset}: Unexpected data {type(price_data)}.")
                                initial_prices_log[asset] = 'N/A'
                 except Exception as e:
                      logger.warning(f"Error during initial price fetching for logging: {e}")


                 logger.info(f"--- Final list of assets for trade ({len(assets_for_trade)}) ---")
                 for asset, payout in valid_assets_details_for_log:
                     if asset in assets_for_trade:
                         price = initial_prices_log.get(asset, "N/A")
                         indicator_values_log = initial_indicators_log.get(asset, {})
                         indicator_str = ", ".join(f"{ind}: {val:.5f}" if isinstance(val, (int, float)) else f"{ind}: N/A" for ind, val in indicator_values_log.items())
                         logger.info(f"    - {asset}: Payout {payout}%, Price: {price}, Initial Indicators: [{indicator_str}]")
                 logger.info("---------------------------------------------------")
            else:
                logger.info("No assets passed all filtering and criteria in this cycle.")

            if assets_for_trade:
                 logger.info("Executing trading logic...")
                 # execute_trades receives the list of assets and initial indicators from assets.py
                 await execute_trades(client, assets_for_trade, initial_indicators_log)
            else:
                 logger.info("Skipping trade execution: No tradable assets for this cycle.")

            logger.debug("Checking connection status before waiting...")
            if not await check_connection(client):
                logger.warning("Connection lost. Attempting reconnect...")
                if not await reconnect(client):
                    logger.critical("Failed to reconnect after connection loss. Exiting.")
                    return

        except Exception as e:
            logger.error(f"Error during main cycle execution: {e}", exc_info=True)

        end_time_cycle = time.time()
        cycle_duration = end_time_cycle - start_time_cycle
        wait_time_needed = max(0, TRADE_COOLDOWN - cycle_duration)

        if wait_time_needed > 0:
            logger.info(f"Cycle completed in {cycle_duration:.2f}s. Waiting {wait_time_needed:.2f}s.")
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
                time_passed_in_wait = time.time() - start_wait_time # Recalculate after sleep
                remaining_wait = max(0, wait_time_needed - time_passed_in_wait)
                if remaining_wait > 0:
                     logger.info(f"Time until next cycle: {remaining_wait:.2f}s remaining.")

            logger.debug("Waiting period concluded.")
        else:
            logger.info(f"Cycle completed in {cycle_duration:.2f}s. No waiting needed.")


if __name__ == "__main__":
    setup_logging()
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped manually.")
    except Exception as e:
        logger.critical(f"Fatal error during bot execution: {e}", exc_info=True)