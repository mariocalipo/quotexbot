import logging
import asyncio
from quotexapi.stable_api import Quotex
from settings import TIMEFRAME, MIN_PAYOUT, ASSETS, SORT_BY, SORT_ORDER, RSI_BUY_THRESHOLD, RSI_SELL_THRESHOLD, ATR_MAX
from indicators import calculate_indicators # Make sure calculate_indicators is correctly imported

logger = logging.getLogger(__name__)

# Assuming get_realtime_prices is also in assets.py based on previous code shares
# If it's not, you'll need to ensure it's available or imported correctly
async def get_realtime_prices(client: Quotex, assets: list) -> dict:
    """Fetch real-time prices for the specified assets."""
    prices = {}
    if not assets:
        logger.debug("No assets provided to get_realtime_prices. Returning empty dict.")
        return {}

    # Start price streams concurrently
    price_stream_tasks = [client.start_realtime_price(asset) for asset in assets]
    # Use return_exceptions=True to allow other streams to start even if one fails
    await asyncio.gather(*price_stream_tasks, return_exceptions=True)

    logger.debug(f"Real-time price streams initiated for {len(assets)} assets. Waiting a moment for initial data...")
    await asyncio.sleep(2) # Give some time for initial data to arrive via websocket - Increased sleep slightly

    logger.debug("Attempting to retrieve latest real-time prices from internal client data.")
    # Fetch prices concurrently after giving streams time to start
    price_fetch_tasks = [client.get_realtime_price(asset) for asset in assets]
    price_data_list = await asyncio.gather(*price_fetch_tasks, return_exceptions=True)

    for i, asset in enumerate(assets):
        price_data = price_data_list[i]
        if isinstance(price_data, Exception):
             # Log exceptions from the fetch task
             logger.warning(f"Exception fetching price for {asset}: {price_data}", exc_info=False)
             continue # Skip this asset
        
        # --- Start of Fix for 'list' object error in price data ---
        price = None
        # timestamp = None # Timestamp not used here, but good practice to get it

        if isinstance(price_data, list) and len(price_data) > 0:
            # If it's a list, find the latest entry (assuming entries have a 'time' key)
            try:
                latest_entry = max(price_data, key=lambda x: x.get('time', 0)) # Use .get safely
                price = latest_entry.get('price') # Use .get safely
                # timestamp = latest_entry.get('time') # Use .get safely
                if price is not None: # Check if price was successfully extracted
                    # logger.debug(f"Price data for {asset} was a list. Extracted latest price: {price}") # Detailed debug
                    pass # Price extracted
                else:
                    logger.debug(f"Price field was None in latest list entry for {asset}. Data: {latest_entry}")

            except Exception as e:
                logger.warning(f"Could not process price data list for {asset}: {e}. Data: {price_data}", exc_info=False)


        elif isinstance(price_data, dict) and price_data:
            # If it's a dictionary (the expected format from client.get_realtime_price)
            price = price_data.get('price')
            # timestamp = price_data.get('time')
            if price is not None: # Check if price was successfully extracted
                 # logger.debug(f"Price data for {asset} was a dictionary. Extracted price: {price}") # Detailed debug
                 pass # Price extracted
            else:
                 logger.debug(f"Price field was None in dictionary data for {asset}. Data: {price_data}")


        else:
            # Handle other unexpected types or empty data
            logger.debug(f"No real-time price data available internally for {asset} after initial wait, or data format unexpected. Data: {price_data}")

        # --- End of Fix ---

        # If a valid price (numeric) was obtained, add it to the prices dictionary
        if price is not None and isinstance(price, (int, float)):
            prices[asset] = price
        else:
             logger.debug(f"Valid numeric price not obtained for {asset}. Skipping price for this asset.")


    logger.debug(f"Real-time price retrieval attempt concluded. Prices obtained for {len(prices)} assets.")
    return prices


async def list_open_otc_assets(client: Quotex):
    """
    Lists open OTC assets with sufficient payout and calculates initial indicators.
    Returns a list of (asset_name, payout) tuples for assets meeting criteria.
    """
    # --- Configuration and Validation ---
    valid_timeframes_payout = ['1M', '5M', '24H']
    # Use TIMEFRAME from settings for payout check
    timeframe_payout = TIMEFRAME if TIMEFRAME in valid_timeframes_payout else '1M'
    if TIMEFRAME not in valid_timeframes_payout:
        logger.warning(f"TIMEFRAME '{TIMEFRAME}' in .env is not a standard payout timeframe ('1M', '5M', '24H'). Using '1M' for payout check.")

    valid_sort_by = ['payout', 'price']
    sort_by = SORT_BY if SORT_BY in valid_sort_by else 'payout'
    if SORT_BY not in valid_sort_by:
        logger.warning(f"SORT_BY '{SORT_BY}' in .env invalid. Using default 'payout'.")

    valid_sort_order = ['asc', 'desc']
    sort_order = SORT_ORDER if SORT_ORDER in valid_sort_order else 'desc'
    if SORT_ORDER not in valid_sort_order:
        logger.warning(f"SORT_ORDER '{SORT_ORDER}' in .env invalid. Using default 'desc'.")

    # --- Fetch Instruments and Assets ---
    logger.debug("Waiting for instruments from API to load...")
    attempt = 0
    max_attempts_instruments = 30 # Increased attempts slightly
    # Access client.api.instruments directly as it's likely populated by client.connect()
    while client.api.instruments is None and attempt < max_attempts_instruments:
        logger.debug(f"Instruments not yet loaded, waiting 0.5s (attempt {attempt + 1}/{max_attempts_instruments})...")
        await asyncio.sleep(0.5)
        attempt += 1

    if client.api.instruments is None:
        logger.error("Failed to load instruments from API after multiple attempts. Cannot proceed with asset listing.")
        return [] # Return empty list on failure

    logger.debug(f"{len(client.api.instruments) if client.api.instruments else 0} instruments loaded from API.")

    try:
        # get_all_assets populates client.codes_asset and returns it
        all_assets_dict = await client.get_all_assets()
        # Ensure all_assets_dict is a dict before proceeding
        if not isinstance(all_assets_dict, dict):
             logger.error(f"client.get_all_assets did not return a dictionary. Received type: {type(all_assets_dict)}. Cannot proceed.")
             return [] # Return empty list on failure
        logger.debug(f"{len(all_assets_dict)} assets available (mapped by name:code).")
    except Exception as e:
        logger.error(f"Failed to get all assets from client: {e}", exc_info=True)
        return [] # Return empty list on failure


    # --- Identify OTC Assets and Filter by .env Settings ---
    # Use the keys from the dictionary returned by get_all_assets
    otc_assets_names = [asset for asset in all_assets_dict.keys() if asset and isinstance(asset, str) and asset.lower().endswith('_otc')]
    logger.debug(f"{len(otc_assets_names)} assets identified as OTC based on naming.")

    assets_to_process = [] # List of asset names to check availability and payout for
    if ASSETS and isinstance(ASSETS, list): # Check if ASSETS is a non-empty list
        # Filter assets specified in .env to include only valid OTC asset names found
        selected_assets = [asset.strip() for asset in ASSETS if isinstance(asset, str) and asset.strip()]
        logger.info(f"Assets specified in .env: {selected_assets if selected_assets else 'None'}")
        assets_to_process = [asset for asset in selected_assets if asset in otc_assets_names]

        invalid_assets = [asset for asset in selected_assets if asset and asset not in otc_assets_names]
        if invalid_assets:
            logger.warning(f"Invalid, non-OTC, or unavailable assets specified in .env (will be ignored): {invalid_assets}")

        if not assets_to_process and selected_assets: # If assets were specified but none are valid/OTC
             logger.info("None of the assets specified in .env are valid OTC assets or currently available based on initial listing.")
             return [] # Return empty list if no valid assets from .env

    elif ASSETS: # Handle case where ASSETS might be set but not a list (e.g., single string without split)
         logger.warning(f"ASSETS setting in .env is not in expected list format. Received type: {type(ASSETS)}. Processing all open OTC assets.")
         assets_to_process = otc_assets_names # Fallback to all OTC if format is wrong
    else:
        logger.info("No assets specified in .env. Processing all open OTC assets.")
        assets_to_process = otc_assets_names # Process all OTC if ASSETS is empty or None


    if not assets_to_process:
         logger.info("No assets to process after applying .env filters.")
         return [] # Return empty list if assets_to_process is empty


    logger.debug(f"Candidate OTC assets for availability and payout check ({len(assets_to_process)}): {assets_to_process}")


    # --- Check Availability and Payout ---
    open_otc_assets_with_payout = [] # List to store (asset_name, payout) tuples for open assets with sufficient payout
    logger.debug("Checking if candidate assets are open and meet minimum payout...")

    # Use asyncio.gather to check asset status and payout concurrently
    check_tasks = [client.check_asset_open(asset_name) for asset_name in assets_to_process]
    results = await asyncio.gather(*check_tasks, return_exceptions=True)

    for i, asset_name in enumerate(assets_to_process):
        result = results[i]

        if isinstance(result, Exception):
             # Log any exceptions from check_asset_open task
             logger.error(f"Exception checking asset {asset_name} status/payout: {result}", exc_info=False)
             continue # Skip this asset

        # check_asset_open is expected to return (instrument_data, asset_open_status)
        if isinstance(result, tuple) and len(result) == 2:
            instrument_data, asset_open_status = result

            # Ensure asset_open_status is a list/tuple of expected size before accessing index
            if isinstance(asset_open_status, (list, tuple)) and len(asset_open_status) >= 3:
                is_open = asset_open_status[2] # Assuming index 2 is the open status bool

                if is_open:
                    # Get payout using the specified timeframe
                    payout = client.get_payout_by_asset(asset_name, timeframe_payout.replace('M', ''))
                    if payout is not None and isinstance(payout, (int, float)):
                        if payout >= MIN_PAYOUT:
                            # Add the asset name and its payout as a tuple
                            open_otc_assets_with_payout.append((asset_name, payout))
                            logger.debug(f"Asset {asset_name} is open, payout {payout}% >= {MIN_PAYOUT}%. Included for further analysis.")
                        else:
                            logger.debug(f"Asset {asset_name} is open, but payout {payout}% < minimum {MIN_PAYOUT}%. Filtered out.")
                    else:
                        logger.warning(f"No valid numeric payout data available for {asset_name} (timeframe: {timeframe_payout}). Data: {payout}. Filtered out.")
                else:
                    logger.debug(f"Asset {asset_name} is not open at the moment. Filtered out.")
            else:
                logger.warning(f"Unexpected format for asset_open_status for {asset_name}. Expected list/tuple >= size 3. Data: {asset_open_status}. Skipping.")
        else:
            logger.warning(f"check_asset_open for {asset_name} returned unexpected result format. Expected tuple (instrument_data, status). Got: {result}. Skipping.")


    if not open_otc_assets_with_payout:
        logger.info(f"No open OTC assets meet the minimum payout criteria ({MIN_PAYOUT}%).")
        return [] # Return empty list if no assets meet payout criteria


    logger.info(f"{len(open_otc_assets_with_payout)} open OTC assets with payout >= {MIN_PAYOUT}% found.")

    # Extract asset names for fetching indicators and prices
    asset_names_for_analysis = [asset for asset, _ in open_otc_assets_with_payout]

    # --- Fetch Real-time Prices and Calculate Initial Indicators ---
    logger.debug("Fetching real-time prices for assets meeting payout criteria...")
    # get_realtime_prices is expected to return a dictionary {asset: price}
    prices = await get_realtime_prices(client, asset_names_for_analysis)
    logger.debug(f"Fetched prices for {len(prices)} assets.")

    # Use a default timeframe for initial indicator calculation if not specified elsewhere
    # The indicators.py might have a default, or you can add a setting for this.
    # For now, let's assume calculate_indicators handles the timeframe or uses a default.
    # indicator_timeframe = 60 # Example: 1 minute
    logger.debug(f"Calculating initial indicators for assets meeting payout criteria...")
    # calculate_indicators is expected to return a dictionary {asset: {indicator: value}}
    indicators = await calculate_indicators(client, asset_names_for_analysis) # Assuming timeframe is handled internally or has a default

    logger.debug(f"Calculated indicators for {len(indicators)} assets.")


    # --- Apply Initial Trading Criteria (RSI, Price vs SMA, ATR) ---
    tradable_assets_final = [] # This list will store (asset_name, payout) tuples for assets passing all criteria
    logger.debug("Applying initial trading criteria (RSI, Price vs SMA, ATR) to further filter assets...")

    # Iterate over assets that were open and met the minimum payout
    for asset, payout in open_otc_assets_with_payout:
        # Get indicator values and price for this asset
        indicator_values = indicators.get(asset, {})
        # Use .get for price dictionary, providing a default if asset not found (e.g., if price fetch failed)
        price = prices.get(asset)

        # Ensure indicators are fetched and are numeric/float, and price is also numeric/float
        # Check if necessary data is available and numeric for the initial trading criteria
        rsi = indicator_values.get("RSI")
        sma = indicator_values.get("SMA")
        atr = indicator_values.get("ATR")

        logger.debug(f"Checking {asset} for initial trading criteria: Price={price}, RSI={rsi}, SMA={sma}, ATR={atr}. Payout={payout}%.")

        # Check if all required indicators (RSI, SMA, ATR) and Price are numeric/float
        # Only proceed with criteria check if we have valid numeric data for all
        if (
            isinstance(rsi, (int, float)) and rsi is not None and
            isinstance(sma, (int, float)) and sma is not None and
            isinstance(atr, (int, float)) and atr is not None and
            isinstance(price, (int, float)) and price is not None
           ):

             meets_trading_criteria = False
             reason = "Initial criteria not met" # Default reason if criteria are not met

             # Trading criteria based on your existing logic:
             # CALL: RSI < RSI_BUY_THRESHOLD AND Price > SMA
             # PUT: RSI > RSI_SELL_THRESHOLD AND ATR < ATR_MAX

             if rsi < RSI_BUY_THRESHOLD and price > sma:
                 meets_trading_criteria = True
                 reason = f"Initial CALL criterion met (RSI={rsi:.2f} < {RSI_BUY_THRESHOLD} and Price={price:.5f} > SMA={sma:.5f})"
             elif rsi > RSI_SELL_THRESHOLD and atr < ATR_MAX:
                 meets_trading_criteria = True
                 reason = f"Initial PUT criterion met (RSI={rsi:.2f} > {RSI_SELL_THRESHOLD} and ATR={atr:.5f} < {ATR_MAX})"
             # If neither CALL nor PUT criteria are met, reason remains "Initial criteria not met"


             if meets_trading_criteria:
                 # Add the asset name and its payout as a tuple to the final list
                 tradable_assets_final.append((asset, payout))
                 logger.debug(f"Asset {asset} PASSED initial trading criteria check: {reason}. Included in final list.")
             else:
                 # Log when an asset fails the initial criteria check
                 logger.debug(f"Asset {asset} FAILED initial trading criteria check: {reason}. Filtered out.")

        else:
             # Log when an asset is skipped because required data is missing or not numeric
             logger.debug(f"Asset {asset} skipped for trading criteria check: Missing or non-numeric required data (RSI:{rsi}, SMA:{sma}, ATR:{atr}, Price:{price}).")


    # --- Sort the Final List of Tradable Assets ---
    reverse = (sort_order == 'desc')
    if sort_by == 'payout':
        # Sort by payout (index 1 in the tuple)
        tradable_assets_final.sort(key=lambda x: x[1], reverse=reverse)
        logger.debug(f"Final tradable assets sorted by payout {'descending' if reverse else 'ascending'}.")
    elif sort_by == 'price':
        # Sort by price. Need to use the fetched price, handling cases where price might be missing.
        # Use get() with a default value that respects the sort order for missing prices.
        # For descending, missing price should be treated as lowest. For ascending, as highest.
        tradable_assets_final.sort(key=lambda x: prices.get(x[0], float('-inf') if reverse else float('inf')) if isinstance(prices.get(x[0]), (int, float)) else (float('-inf') if reverse else float('inf')), reverse=reverse)
        logger.debug(f"Final tradable assets sorted by price {'descending' if reverse else 'ascending'}.")


    # --- Return the Final List of Tradable Assets ---
    # Return the list of (asset_name, payout) tuples
    return tradable_assets_final # CORRECTED: Return the list of tuples