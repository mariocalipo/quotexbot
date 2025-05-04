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
# Add the directory containing the src folder to the Python path
# This assumes the structure is project_root/src/main.py, project_root/src/assets.py, etc.
# If your structure is different, you might need to adjust this.
sys.path.insert(0, str(root))

from settings import EMAIL, PASSWORD, IS_DEMO, TRADE_COOLDOWN, TIMEFRAME # Import TIMEFRAME here
from assets import list_open_otc_assets
from trade import execute_trades
from indicators import calculate_indicators

def setup_logging():
    """Configure logging format and level for the application, with output to both console and file."""
    # Ensure root logger is configured only once
    if not logging.getLogger().hasHandlers():
        logger = logging.getLogger()
        # Set level to DEBUG for file, INFO for console
        logger.setLevel(logging.DEBUG)

        log_format = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S")

        # Console handler (outputs to terminal)
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(log_format)
        console_handler.setLevel(logging.INFO) # Only show INFO and above on console
        logger.addHandler(console_handler)

        # File handler (outputs to a log file)
        log_file = root.parent / "quotexbot.log"
        # Create directory if it doesn't exist (optional, but good practice)
        log_file.parent.mkdir(parents=True, exist_ok=True)
        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=5*1024*1024, # 5 MB limit
            backupCount=3 # Keep up to 3 old log files
        )
        file_handler.setFormatter(log_format)
        file_handler.setLevel(logging.DEBUG) # Log DEBUG and above to file
        logger.addHandler(file_handler)

# Get a logger for this specific module (main.py)
logger = logging.getLogger(__name__)


async def check_connection(client: Quotex) -> bool:
    """Check if the connection is still active by attempting a simple API call."""
    logger.debug("Performing connection check...")
    try:
        # Attempt a simple API call like getting balance to test connection
        balance = await client.get_balance()
        # Log balance at debug level to avoid spamming INFO logs
        logger.debug(f"Connection check successful. Current balance: {balance:.2f} USD")
        return True
    except Exception as e:
        # Log connection check failures as warnings
        logger.warning(f"Connection check failed: {e}", exc_info=False) # Log error without full traceback
        return False

async def reconnect(client: Quotex, max_attempts: int = 5) -> bool:
    """Attempt to reconnect to the Quotex API."""
    logger.info("Attempting to reconnect...")
    delay = 5 # Base delay for reconnection attempts
    for attempt in range(1, max_attempts + 1):
        logger.info(f"Reconnection attempt {attempt}/{max_attempts}...")
        try:
            # Use the actual client.connect() which should handle connection logic
            # It's expected to return a tuple (success_bool, reason_str) or potentially just a bool
            result = await client.connect()

            # Adapt to the potential return types of client.connect() based on your stable_api.py
            if isinstance(result, tuple) and len(result) == 2:
                 success, reason = result
            elif isinstance(result, bool): # Handle cases where it might just return True/False
                 success = result
                 reason = "Connection failed" if not success and result is not None else None # Provide a default reason
            else:
                 # Log unexpected return types from connect method
                 logger.error(f"Unexpected return type from client.connect() during reconnect: {type(result)}. Result: {result}")
                 success = False
                 reason = f"Unexpected connect response: {result}" # Use the result in the reason

            if success:
                logger.info("Reconnection successful!")
                # Re-fetch balance after successful reconnection for logging
                try:
                    balance = await client.get_balance()
                    # Use client.account_is_demo property as set by set_account_mode
                    account_type = "Demo" if client.account_is_demo > 0 else "Real"
                    logger.info(f"Account balance ({account_type}) after reconnection: {balance:.2f} USD") # Formatted balance
                except Exception as e:
                    logger.warning(f"Failed to get balance after reconnection: {e}", exc_info=False) # Use warning for balance fetch failure
                return True
            else:
                # Log reconnection failure reason
                logger.warning(f"Reconnection attempt {attempt} failed: {reason}")

        except asyncio.TimeoutError:
            # Log timeouts during reconnection attempts
            logger.warning(f"Reconnection attempt {attempt}/{max_attempts} timed out.")
            reason = "Timeout" # Set reason for logging
        except Exception as e:
            # Log unexpected exceptions during reconnection attempts
            logger.error(f"Unexpected error during reconnection (attempt {attempt}/{max_attempts}): {e}", exc_info=False)
            reason = f"Exception: {e}" # Capture exception message for logging


        # Wait before the next attempt, unless it was the last attempt
        if attempt < max_attempts:
             # Implement a simple fixed delay for simplicity
             await asyncio.sleep(delay)
        else:
             # Log final failure after max attempts
             logger.error(f"Maximum reconnection attempts ({max_attempts}) reached.")

    # Return False if max attempts reached without success
    logger.critical("Failed to reconnect after multiple attempts. Exiting.") # Use critical for critical failure
    return False


async def main():
    """Main asynchronous function to run the trading bot."""
    setup_logging()
    logger.info("Starting Quotex trading bot...")

    # Validate essential settings (EMAIL and PASSWORD from .env)
    if not EMAIL or not PASSWORD:
        logger.critical("Email or password not provided in environment variables (.env). Exiting.") # Use critical for fatal error
        return

    logger.info("Initializing Quotex client...")
    # Pass email, password, and lang to the client constructor
    client = Quotex(EMAIL, PASSWORD, lang="pt")
    # Use the set_account_mode method provided in stable_api.py based on IS_DEMO setting
    client.set_account_mode("PRACTICE" if IS_DEMO else "REAL")
    client.totp_prompt = False # Assuming this setting is desired (disables TOTP prompt)

    # Initial Connection Logic with multiple attempts and error handling
    max_init_attempts = 5
    init_attempt = 1
    init_delay = 5
    connected = False

    while init_attempt <= max_init_attempts and not connected:
        logger.info(f"Attempting to connect to Quotex (Attempt {init_attempt}/{max_init_attempts})...")
        try:
            # Use client.connect() directly. It should handle its own timeouts if designed well.
            # Expected to return (success_bool, reason_str) or just a bool.
            result = await client.connect()

            # Adapt to the potential return types of client.connect()
            if isinstance(result, tuple) and len(result) == 2:
                 success, reason = result
            elif isinstance(result, bool): # Handle cases where it might just return True/False
                 success = result
                 reason = "Connection failed" if not success and result is not None else None # Provide a default reason
            else:
                 # Log unexpected return types from connect method
                 logger.error(f"Unexpected return type from client.connect() during initial connection: {type(result)}. Result: {result}")
                 success = False
                 reason = f"Unexpected connect response: {result}" # Use the result in the reason

            if success:
                logger.info("Connection established successfully!")
                connected = True # Set flag to exit loop
            else:
                # Log connection failure reason
                logger.error(f"Connection attempt {init_attempt} failed: {reason}")

        except Exception as e:
            # Log unexpected exceptions during initial connection attempts
            logger.error(f"An unexpected error occurred during initial connection attempt {init_attempt}: {e}", exc_info=False)
            reason = f"Exception: {e}" # Capture exception message for logging

        # If not connected after this attempt
        if not connected:
             # Check if max attempts reached before waiting or exiting
             if init_attempt == max_init_attempts:
                  logger.critical("Maximum initial connection attempts reached. Exiting.") # Use critical
                  return # Exit main if connection fails after all attempts
             init_attempt += 1
             await asyncio.sleep(init_delay) # Wait before retrying

    # If loop finishes and not connected, something went wrong and we should exit
    if not connected:
         logger.critical("Could not establish initial connection after multiple attempts. Exiting.")
         return # Ensure exit if not connected


    # Initial balance fetch after successful connection
    try:
        balance = await client.get_balance()
        # Use client.account_is_demo property as set by set_account_mode
        account_type = "Demo" if client.account_is_demo > 0 else "Real"
        logger.info(f"Account balance ({account_type}): {balance:.2f} USD") # Formatted balance
        logger.info("-" * 50) # Separator for clarity

    except Exception as e:
        # Log a warning if initial balance fetch fails, but continue
        logger.warning(f"Failed to retrieve initial account balance: {e}", exc_info=False)
        # The bot will continue, but trade execution should handle cases where balance is None/invalid


    # --- Main Trading Cycle Loop ---
    logger.info("Entering main trading cycle loop.")
    while True:
        start_time_cycle = time.time()
        logger.info("-" * 50) # Separator for new cycle
        logger.info("Starting new main cycle...")

        try:
            # 1. List and filter assets
            logger.info("Listing and filtering open OTC assets...")
            # list_open_otc_assets should handle its own logging about filtering steps
            # It should return a list of (asset_name, payout) tuples for valid assets
            # The previous ValueError occurred here due to unexpected items in the list returned
            open_assets_details = await list_open_otc_assets(client)

            # --- Modified processing of open_assets_details with explicit loop and error handling ---
            assets_for_trade = [] # List to store only valid asset names
            # This list will store valid (asset, payout) tuples for logging the final list
            valid_assets_details_for_log = []
            skipped_items_count = 0 # Counter for items filtered out

            if not open_assets_details:
                 logger.info("No open OTC assets found with sufficient payout or matching criteria.")
                 # assets_for_trade remains empty
            else:
                 # Iterate through each item returned by list_open_otc_assets
                 logger.debug(f"Processing {len(open_assets_details)} items returned by list_open_otc_assets.")
                 for item in open_assets_details:
                     # Check if the item is a list or tuple and has exactly 2 elements
                     if isinstance(item, (list, tuple)) and len(item) == 2:
                         try:
                             # Attempt to unpack the item into asset and payout
                             asset, payout = item
                             # Add optional checks for the types of asset and payout if needed
                             # Ensure asset name is a non-empty string and payout is a number
                             if isinstance(asset, str) and asset and isinstance(payout, (int, float)):
                                 # If unpacking and basic type check is successful, add the asset name
                                 assets_for_trade.append(asset)
                                 # Store the valid (asset, payout) tuple for later logging
                                 valid_assets_details_for_log.append((asset, payout))
                             else:
                                 # Log if unpacking works but types/values are wrong
                                 logger.warning(f"Skipping item from assets.py list: Unexpected types or values for asset or payout after unpacking. Expected (non-empty str, number), got ({type(asset)}, {type(payout)}). Item: {item}")
                                 skipped_items_count += 1

                         except Exception as unpack_e:
                             # Log any error that occurs during unpacking (shouldn't happen if len is 2, but for safety)
                             logger.warning(f"Skipping item from assets.py list: Failed to unpack item {item}: {unpack_e}")
                             skipped_items_count += 1
                     else:
                         # Log items that do not meet the basic list/tuple and size 2 criteria
                         # Try to get length safely if it's not a list/tuple
                         item_len = len(item) if isinstance(item, (list, tuple)) else 'N/A'
                         logger.warning(f"Skipping item from assets.py list: Unexpected format. Expected list/tuple of size 2, got {type(item)} of size {item_len}. Item: {item}")
                         skipped_items_count += 1

                 # Log a summary if any items were skipped during processing
                 if skipped_items_count > 0:
                      logger.warning(f"Filtered out a total of {skipped_items_count} items from the list of tradable assets returned by assets.py due to unexpected format or content.")

            # --- End of modified processing of open_assets_details ---


            # --- Logging the Final List of Assets for Trade Execution ---
            initial_indicators_log = {}
            initial_prices_log = {}
            if assets_for_trade: # Check if there are any valid asset names left after processing
                 logger.debug(f"Processing indicators and prices for {len(assets_for_trade)} valid assets.")
                 # Fetch indicators and prices for logging the final list (only for assets_for_trade)
                 # Assuming calculate_indicators in indicators.py uses a default timeframe or setting if not provided
                 initial_indicators_log = await calculate_indicators(client, assets_for_trade)
                 try:
                      # Fetch prices concurrently for efficiency, only for assets_for_trade
                      price_tasks = [client.get_realtime_price(asset) for asset in assets_for_trade]
                      # Use return_exceptions=True to prevent one failed fetch from stopping the others
                      price_data_list = await asyncio.gather(*price_tasks, return_exceptions=True)

                      for i, asset in enumerate(assets_for_trade):
                           price_data = price_data_list[i]
                           # Process returned price data, handling success, exceptions, and unexpected formats
                           if isinstance(price_data, list) and price_data and isinstance(price_data[0], dict):
                                initial_prices_log[asset] = price_data[0].get('price', 'N/A')
                           elif isinstance(price_data, dict) and price_data:
                                initial_prices_log[asset] = price_data.get('price', 'N/A')
                           elif isinstance(price_data, Exception):
                                # Log exceptions from get_realtime_price task
                                logger.warning(f"Exception fetching initial price for logging for {asset}: {price_data}", exc_info=False)
                                initial_prices_log[asset] = 'N/A' # Set to N/A on exception
                           else:
                                # Log any other unexpected data type returned
                                logger.warning(f"Could not get initial price data for logging for {asset}: Unexpected data type {type(price_data)}. Data: {price_data}")
                                initial_prices_log[asset] = 'N/A' # Set to N/A on unexpected data
                 except Exception as e:
                      # This outer catch might not be needed if gather handles exceptions, but kept for safety
                      logger.warning(f"An unexpected error occurred during initial price fetching for logging: {e}", exc_info=False)
                      # Prices will remain 'N/A' for assets where fetching failed


                 # Log the final list using valid_assets_details_for_log to show asset and payout
                 logger.info(f"--- Final list of assets for trade execution ({len(assets_for_trade)}) ---")
                 # Iterate over the list containing valid (asset, payout) tuples that were included
                 # Note: This assumes the order in valid_assets_details_for_log matches assets_for_trade
                 # If order matters and list_open_otc_assets sorts, need to maintain sorting
                 # For logging purposes, iterating valid_assets_details_for_log is fine.
                 for asset, payout in valid_assets_details_for_log:
                     # Check if the asset was actually included in assets_for_trade after all checks
                     if asset in assets_for_trade:
                         price = initial_prices_log.get(asset, "N/A")
                         indicator_values_log = initial_indicators_log.get(asset, {})
                         # Format indicator values, handle None and non-numeric values
                         # Using .5f for float formatting, N/A for others
                         indicator_str = ", ".join(f"{ind}: {val:.5f}" if isinstance(val, (int, float)) and val is not None else f"{ind}: N/A" for ind, val in indicator_values_log.items())
                         logger.info(f"    - {asset}: Payout {payout}%, Price: {price}, Initial Indicators: [{indicator_str}]")
                 logger.info("---------------------------------------------------")
            else:
                # Log if no assets are left after all filtering (including the new explicit checks)
                logger.info("No assets passed all filtering and initial trading criteria in this cycle.")

            # --- End of Logging the Final List ---


            # 2. Execute trading logic and manage trades
            # Only proceed with trade execution if there are assets in assets_for_trade
            if assets_for_trade:
                 logger.info("Executing trading logic based on assets and indicators...")
                 # Pass the filtered list of asset names (assets_for_trade) and the initial indicators for trading logic
                 # execute_trades will recalculate indicators with fresh data just before making a trade decision
                 await execute_trades(client, assets_for_trade, initial_indicators_log) # Passing indicators for consistency, execute_trades might use or re-calculate

            else:
                 logger.info("Skipping trade execution: No tradable assets for this cycle.") # Explicitly log when skipping trade execution


            # 3. Check connection before the next cycle
            logger.debug("Checking connection status before waiting...")
            if not await check_connection(client):
                logger.warning("Connection lost. Attempting to reconnect...")
                # Attempt to reconnect using the separate async function
                if not await reconnect(client):
                    logger.critical("Failed to reconnect after connection loss. Exiting.") # Use critical
                    return # Exit main if reconnection fails

        except Exception as e:
            # Catch any unexpected errors during the main cycle execution to prevent bot crash
            # This catch will now be less likely to catch the ValueError due to the explicit loop above
            logger.error(f"An unexpected error occurred during main cycle execution: {e}", exc_info=True)
            # The bot will continue to the waiting period and the next cycle after logging the error.


        # --- Waiting Period Before Next Cycle (Modified for Periodic Logging) ---
        end_time_cycle = time.time()
        cycle_duration = end_time_cycle - start_time_cycle
        # Ensure wait time is not negative
        wait_time_needed = max(0, TRADE_COOLDOWN - cycle_duration)

        if wait_time_needed > 0:
            logger.info(f"Main cycle completed in {cycle_duration:.2f} seconds.")
            logger.info(f"Waiting for {wait_time_needed:.2f} seconds before the next cycle (based on TRADE_COOLDOWN={TRADE_COOLDOWN}s).")

            sleep_interval = 10 # Log remaining time approximately every 10 seconds
            start_wait_time = time.time() # Time when waiting starts

            while True:
                # Calculate how much total time has passed since the start of the wait
                time_passed_in_wait = time.time() - start_wait_time
                # Calculate the true remaining wait time
                remaining_wait = max(0, wait_time_needed - time_passed_in_wait)

                # If no significant time is left, break the loop
                if remaining_wait <= 1.0: # Use 1.0 to avoid logging tiny remaining times
                    break

                # Calculate time until the next desired log tick (every 10 seconds from the start of waiting)
                time_until_next_log_tick = sleep_interval - (time_passed_in_wait % sleep_interval)
                # If time_until_next_log_tick is very small, set it to the full interval for the next sleep
                if time_until_next_log_tick <= 0.01:
                     time_until_next_log_tick = sleep_interval

                # Determine how long to sleep: the minimum of time until the next log tick or the total remaining time
                sleep_duration = min(time_until_next_log_tick, remaining_wait)

                # Only sleep if there's a meaningful duration to sleep for
                if sleep_duration > 0:
                     await asyncio.sleep(sleep_duration)

                # Log the remaining time after waking up
                # Recalculate remaining time precisely after sleeping
                time_passed_in_wait = time.time() - start_wait_time
                remaining_wait = max(0, wait_time_needed - time_passed_in_wait)

                # Log remaining time if still greater than 0 after sleep
                if remaining_wait > 0:
                     logger.info(f"Time until next cycle: {remaining_wait:.2f} seconds remaining.")


            # After the loop finishes, remaining_wait is <= 1.0, meaning the waiting period is complete.
            logger.debug("Waiting period concluded.")


        else:
            # If cycle duration is >= TRADE_COOLDOWN, no waiting is needed.
            logger.info(f"Main cycle completed in {cycle_duration:.2f} seconds. No waiting needed (cycle duration >= TRADE_COOLDOWN).")

        # The loop will continue to the next cycle immediately after the waiting period (or lack thereof)
        # logger.info("-" * 50) # Separator is already printed at the start of the next cycle

    # This part of the code is unreachable as the main loop is infinite
    # In a real application, you might handle graceful shutdown here (e.g., closing client connection)
    # async with client: # If the client supports async context management
    #    await main() # Example of running main within a client context

    # If the bot is stopped manually (KeyboardInterrupt) or by a fatal error, the handlers below will catch it.


if __name__ == "__main__":
    # Ensure logging is set up before running the main function
    setup_logging()
    try:
        # Run the main asynchronous function using asyncio.run()
        asyncio.run(main())
    except KeyboardInterrupt:
        # Handle manual stop by user (Ctrl+C)
        logger.info("Bot stopped manually by user (KeyboardInterrupt).")
        # Add graceful shutdown here if needed (e.g., signal to execute_trades to stop, close client connection)
    except Exception as e:
        # Catch any fatal errors that escape the main loop's error handling
        logger.critical(f"Fatal error occurred during bot execution: {e}", exc_info=True)
        # No further action needed here, the bot process will exit after this.