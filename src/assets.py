import logging
import asyncio
from quotexapi.stable_api import Quotex
from settings import TIMEFRAME, MIN_PAYOUT, ASSETS, SORT_BY, SORT_ORDER, RSI_BUY_THRESHOLD, RSI_SELL_THRESHOLD, ATR_MAX
from indicators import calculate_indicators

logger = logging.getLogger(__name__)

async def get_realtime_prices(client: Quotex, assets: list) -> dict:
    prices = {}
    if not assets:
        logger.debug("No assets provided to get_realtime_prices. Returning empty dict.")
        return {}

    logger.debug(f"Starting real-time price stream for assets: {assets}")

    # Start price streams
    for asset in assets:
        # Assuming start_realtime_price internally handles if a stream is already started
        # and starts the real-time tick data stream (period=0 for candles/ticks)
        await client.start_realtime_price(asset) # Awaiting based on stable_api definition


    logger.debug("Real-time price streams initiated. Waiting a moment for initial data...")
    await asyncio.sleep(1) # Give some time for initial data to arrive via websocket


    logger.debug("Attempting to retrieve latest real-time prices from internal client data.")
    for asset in assets:
        try:
            price_data = await client.get_realtime_price(asset) # Awaiting based on stable_api

            # --- Start of Fix for 'list' object error ---
            price = None
            timestamp = None

            if isinstance(price_data, list) and len(price_data) > 0:
                # If it's a list, find the latest entry (assuming entries have a 'time' key)
                try:
                    latest_entry = max(price_data, key=lambda x: x.get('time', 0)) # Use .get safely
                    price = latest_entry.get('price') # Use .get safely
                    timestamp = latest_entry.get('time') # Use .get safely
                    if price is not None and timestamp is not None:
                        logger.debug(f"Price data for {asset} was a list. Extracted latest price.")
                except Exception as e:
                    logger.warning(f"Could not process price data list for {asset}: {e}. Data: {price_data}", exc_info=False)


            elif isinstance(price_data, dict) and price_data:
                 # If it's a dictionary (the expected format)
                 price = price_data.get('price')
                 timestamp = price_data.get('time')
                 if price is not None and timestamp is not None:
                      logger.debug(f"Price data for {asset} was a dictionary. Extracted price.")

            else:
                # Handle other unexpected types or empty data
                logger.debug(f"No real-time data available internally for {asset} after initial wait, or data format unexpected. Data: {price_data}")

            # --- End of Fix ---


            if price is not None and timestamp is not None:
                 prices[asset] = price
                 # logger.debug(f"Latest real-time price obtained for {asset} (at {timestamp}): {price}") # Can re-enable if needed
            else:
                 logger.debug(f"Valid price/timestamp not found for {asset}. Price data was: {price_data}")


        except Exception as e:
            logger.warning(f"Failed to retrieve latest price for {asset} from client data: {e}", exc_info=False)

    logger.debug(f"Real-time price retrieval attempt concluded. Prices obtained for {len(prices)} assets.")
    return prices


async def list_open_otc_assets(client: Quotex):
    valid_timeframes_payout = ['1M', '5M', '24H']
    timeframe_payout = TIMEFRAME if TIMEFRAME in valid_timeframes_payout else '1M'
    if TIMEFRAME not in valid_timeframes_payout:
        logger.warning(f"TIMEFRAME '{TIMEFRAME}' in .env is not a standard payout timeframe. Using '1M'.")

    valid_sort_by = ['payout', 'price']
    sort_by = SORT_BY if SORT_BY in valid_sort_by else 'payout'
    if SORT_BY not in valid_sort_by:
        logger.warning(f"SORT_BY '{SORT_BY}' in .env invalid. Using default 'payout'.")

    valid_sort_order = ['asc', 'desc']
    sort_order = SORT_ORDER if SORT_ORDER in valid_sort_order else 'desc'
    if SORT_ORDER not in valid_sort_order:
        logger.warning(f"SORT_ORDER '{SORT_ORDER}' in .env invalid. Using default 'desc'.")

    logger.debug("Waiting for instruments from API to load...")
    attempt = 0
    max_attempts_instruments = 20
    while client.api.instruments is None and attempt < max_attempts_instruments:
        logger.debug(f"Instruments not yet loaded, waiting 0.5s (attempt {attempt + 1}/{max_attempts_instruments})...")
        await asyncio.sleep(0.5)
        attempt += 1

    if client.api.instruments is None:
        logger.error("Failed to load instruments from API after multiple attempts. Cannot proceed with asset listing.")
        return []

    logger.debug(f"{len(client.api.instruments)} instruments loaded from API.")

    try:
        all_assets = await client.get_all_assets()
        logger.debug(f"{len(all_assets)} assets available (mapped by name:code).")
    except Exception as e:
        logger.error(f"Failed to get all assets from client: {e}", exc_info=True)
        return []


    # Ensure all_assets is a dict before proceeding
    if not isinstance(all_assets, dict):
        logger.error(f"client.get_all_assets did not return a dictionary. Received type: {type(all_assets)}. Cannot proceed.")
        return []

    otc_assets_names = [asset for asset in all_assets.keys() if asset.lower().endswith('_otc')]
    logger.debug(f"{len(otc_assets_names)} assets identified as OTC.")

    assets_to_process = []
    if ASSETS:
        selected_assets = [asset.strip() for asset in ASSETS if asset.strip()]
        logger.info(f"Assets specified in .env: {selected_assets}")
        assets_to_process = [asset for asset in selected_assets if asset in otc_assets_names]
        invalid_assets = [asset for asset in selected_assets if asset and asset not in otc_assets_names]
        if invalid_assets:
            logger.warning(f"Invalid or non-OTC assets specified in .env (will be ignored): {invalid_assets}")
        if not assets_to_process:
            logger.info("None of the assets specified in .env are valid OTC assets or currently available.")
            return []
    else:
        logger.info("No assets specified in .env. Processing all open OTC assets.")
        assets_to_process = otc_assets_names

    logger.debug(f"Candidate OTC assets for processing ({len(assets_to_process)}): {assets_to_process}")

    open_otc_assets_with_payout = []
    logger.debug("Checking if candidate assets are open and meet minimum payout...")
    for asset_name in assets_to_process:
        try:
            instrument_data, asset_open_status = await client.check_asset_open(asset_name)
            # Ensure asset_open_status is a list/tuple of expected size before accessing index
            if not isinstance(asset_open_status, (list, tuple)) or len(asset_open_status) < 3:
                logger.warning(f"Unexpected format for asset_open_status for {asset_name}. Data: {asset_open_status}. Skipping.")
                continue # Skip this asset if status format is wrong

            is_open = asset_open_status[2]

            if is_open:
                 payout = client.get_payout_by_asset(asset_name, timeframe_payout.replace('M', ''))
                 if payout is not None:
                     if payout >= MIN_PAYOUT:
                         open_otc_assets_with_payout.append((asset_name, payout))
                         logger.debug(f"Asset {asset_name} is open, payout {payout}% >= {MIN_PAYOUT}%. Included for further analysis.")
                     else:
                         logger.debug(f"Asset {asset_name} is open, but payout {payout}% < minimum {MIN_PAYOUT}%. Filtered out.")
                 else:
                     logger.warning(f"No payout data available for {asset_name} (timeframe: {timeframe_payout}). Filtered out.")
            else:
                logger.debug(f"Asset {asset_name} is not open at the moment. Filtered out.")

        except Exception as e:
            logger.error(f"Error while checking asset {asset_name} status/payout: {e}", exc_info=True)


    if not open_otc_assets_with_payout:
         logger.info(f"No open OTC assets meet the minimum payout criteria ({MIN_PAYOUT}%).")
         return []

    logger.info(f"{len(open_otc_assets_with_payout)} open OTC assets with payout >= {MIN_PAYOUT}% found.")

    asset_names_for_analysis = [asset for asset, _ in open_otc_assets_with_payout]

    prices = await get_realtime_prices(client, asset_names_for_analysis)

    indicator_timeframe = 60

    from indicators import calculate_indicators
    logger.debug(f"Calculating required indicators for initial criteria check (timeframe {indicator_timeframe}s)...")
    indicators = await calculate_indicators(client, asset_names_for_analysis, timeframe=indicator_timeframe)

    tradable_assets_final = []
    logger.debug("Applying initial trading criteria (RSI, Price vs SMA, ATR) to further filter assets...")
    for asset, payout in open_otc_assets_with_payout:
        indicator_values = indicators.get(asset, {})
        price = prices.get(asset) # Use .get for safety in case price wasn't fetched

        # Ensure indicators are fetched and are numeric/float
        rsi = indicator_values.get("RSI")
        sma = indicator_values.get("SMA")
        atr = indicator_values.get("ATR")


        logger.debug(f"Checking {asset} for initial trading criteria: Price={price}, RSI={rsi}, SMA={sma}, ATR={atr}. Payout={payout}%.")

        # Check if necessary data is available and numeric for the criteria
        # Now check if price is also numeric
        if not all(isinstance(val, (int, float)) for val in [rsi, sma, atr]) or price is None or not isinstance(price, (int, float)):
             logger.debug(f"Asset {asset} skipped for trading criteria check: Missing or non-numeric data (RSI:{rsi}, SMA:{sma}, ATR:{atr}, Price:{price}).")
             continue

        meets_trading_criteria = False
        reason = "No criteria met"

        # Trading criteria based on original assets.py logic:
        # CALL: RSI < RSI_BUY_THRESHOLD AND Price > SMA
        # PUT: RSI > RSI_SELL_THRESHOLD AND ATR < ATR_MAX

        if rsi < RSI_BUY_THRESHOLD and price > sma:
            meets_trading_criteria = True
            reason = f"Initial CALL criterion met (RSI={rsi:.2f} < {RSI_BUY_THRESHOLD} and Price={price:.5f} > SMA={sma:.5f})"
        elif rsi > RSI_SELL_THRESHOLD and atr < ATR_MAX:
            meets_trading_criteria = True
            reason = f"Initial PUT criterion met (RSI={rsi:.2f} > {RSI_SELL_THRESHOLD} and ATR={atr:.5f} < {ATR_MAX})"
        else:
             reason = f"Initial criteria not met (RSI={rsi:.2f}, Price={price:.5f}, SMA={sma:.5f}, ATR={atr:.5f})"


        if meets_trading_criteria:
            tradable_assets_final.append((asset, payout))
            logger.debug(f"Asset {asset} PASSED initial trading criteria check: {reason}. Included in final list.")
        else:
            logger.debug(f"Asset {asset} FAILED initial trading criteria check: {reason}. Filtered out.")


    reverse = (sort_order == 'desc')
    if sort_by == 'payout':
        tradable_assets_final.sort(key=lambda x: x[1], reverse=reverse)
        logger.debug(f"Final tradable assets sorted by payout {'descending' if reverse else 'ascending'}.")
    elif sort_by == 'price':
        # Sorting by price requires price data to be available and numeric
        # Use a large/small number as a default key if price is missing/not numeric
        tradable_assets_final.sort(key=lambda x: prices.get(x[0], float('-inf') if reverse else float('inf')) if isinstance(prices.get(x[0]), (int, float)) else (float('-inf') if reverse else float('inf')), reverse=reverse)
        logger.debug(f"Final tradable assets sorted by price {'descending' if reverse else 'ascending'}.")


    if tradable_assets_final:
        logger.info(f"--- Final list of assets for trade execution ({len(tradable_assets_final)}) ---")
        for asset, payout in tradable_assets_final:
            price = prices.get(asset, "N/A")
            indicator_values_log = indicators.get(asset, {})
            indicator_str = ", ".join(f"{ind}: {val:.2f}" if isinstance(val, (int, float)) and val is not None else f"{ind}: N/A" for ind, val in indicator_values_log.items())
            logger.info(f"  - {asset}: Payout {payout}%, Price: {price}, Initial Indicators: [{indicator_str}]")
        logger.info("---------------------------------------------------")
    else:
        logger.info("No assets passed all filtering and initial trading criteria in this cycle.")

    return [asset for asset, _ in tradable_assets_final]