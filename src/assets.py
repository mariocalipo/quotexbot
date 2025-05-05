import logging
import asyncio
from quotexapi.stable_api import Quotex
from settings import TIMEFRAME, MIN_PAYOUT, ASSETS, SORT_BY, SORT_ORDER, RSI_BUY_THRESHOLD, RSI_SELL_THRESHOLD, ATR_MAX
from indicators import calculate_indicators

logger = logging.getLogger(__name__)

async def get_realtime_prices(client: Quotex, assets: list) -> dict:
    """Fetch real-time prices for the specified assets."""
    prices = {}
    if not assets:
        logger.debug("No assets provided to get_realtime_prices. Returning empty dict.")
        return {}

    price_stream_tasks = [client.start_realtime_price(asset) for asset in assets]
    await asyncio.gather(*price_stream_tasks, return_exceptions=True)

    logger.debug(f"Real-time price streams initiated for {len(assets)} assets. Waiting a moment for initial data...")
    await asyncio.sleep(2)

    logger.debug("Attempting to retrieve latest real-time prices from internal client data.")
    price_fetch_tasks = [client.get_realtime_price(asset) for asset in assets]
    price_data_list = await asyncio.gather(*price_fetch_tasks, return_exceptions=True)

    for i, asset in enumerate(assets):
        price_data = price_data_list[i]
        if isinstance(price_data, Exception):
            logger.warning(f"Exception fetching price for {asset}: {price_data}", exc_info=False)
            continue

        price = None
        if isinstance(price_data, list) and len(price_data) > 0:
            try:
                latest_entry = max(price_data, key=lambda x: x.get('time', 0))
                price = latest_entry.get('price')
            except Exception as e:
                logger.warning(f"Could not process price data list for {asset}: {e}. Data: {price_data}", exc_info=False)
        elif isinstance(price_data, dict) and price_data:
            price = price_data.get('price')
        else:
            logger.debug(f"No real-time price data available internally for {asset} after initial wait, or data format unexpected. Data: {price_data}")

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
    valid_timeframes_payout = ['1M', '5M', '24H']
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

    logger.debug("Waiting for instruments from API to load...")
    attempt = 0
    max_attempts_instruments = 30
    while client.api.instruments is None and attempt < max_attempts_instruments:
        logger.debug(f"Instruments not yet loaded, waiting 0.5s (attempt {attempt + 1}/{max_attempts_instruments})...")
        await asyncio.sleep(0.5)
        attempt += 1

    if client.api.instruments is None:
        logger.error("Failed to load instruments from API after multiple attempts. Cannot proceed with asset listing.")
        return []

    logger.debug(f"{len(client.api.instruments) if client.api.instruments else 0} instruments loaded from API.")

    try:
        all_assets_dict = await client.get_all_assets()
        if not isinstance(all_assets_dict, dict):
            logger.error(f"client.get_all_assets did not return a dictionary. Received type: {type(all_assets_dict)}. Cannot proceed.")
            return []
        logger.debug(f"{len(all_assets_dict)} assets available (mapped by name:code).")
    except Exception as e:
        logger.error(f"Failed to get all assets from client: {e}", exc_info=True)
        return []

    otc_assets_names = [asset for asset in all_assets_dict.keys() if asset and isinstance(asset, str) and asset.lower().endswith('_otc')]
    logger.debug(f"{len(otc_assets_names)} assets identified as OTC based on naming.")

    assets_to_process = []
    if ASSETS and isinstance(ASSETS, list):
        selected_assets = [asset.strip() for asset in ASSETS if isinstance(asset, str) and asset.strip()]
        logger.info(f"Assets specified in .env: {selected_assets if selected_assets else 'None'}")
        assets_to_process = [asset for asset in selected_assets if asset in otc_assets_names]

        invalid_assets = [asset for asset in selected_assets if asset and asset not in otc_assets_names]
        if invalid_assets:
            logger.warning(f"Invalid, non-OTC, or unavailable assets specified in .env (will be ignored): {invalid_assets}")

        if not assets_to_process and selected_assets:
            logger.info("None of the assets specified in .env are valid OTC assets or currently available based on initial listing.")
            return []
    elif ASSETS:
        logger.warning(f"ASSETS setting in .env is not in expected list format. Received type: {type(ASSETS)}. Processing all open OTC assets.")
        assets_to_process = otc_assets_names
    else:
        logger.info("No assets specified in .env. Processing all open OTC assets.")
        assets_to_process = otc_assets_names

    if not assets_to_process:
        logger.info("No assets to process after applying .env filters.")
        return []

    logger.debug(f"Candidate OTC assets for availability and payout check ({len(assets_to_process)}): {assets_to_process}")

    open_otc_assets_with_payout = []
    logger.debug("Checking if candidate assets are open and meet minimum payout...")
    check_tasks = [client.check_asset_open(asset_name) for asset_name in assets_to_process]
    results = await asyncio.gather(*check_tasks, return_exceptions=True)

    for i, asset_name in enumerate(assets_to_process):
        result = results[i]
        if isinstance(result, Exception):
            logger.error(f"Exception checking asset {asset_name} status/payout: {result}", exc_info=False)
            continue

        if isinstance(result, tuple) and len(result) == 2:
            instrument_data, asset_open_status = result
            if isinstance(asset_open_status, (list, tuple)) and len(asset_open_status) >= 3:
                is_open = asset_open_status[2]
                if is_open:
                    payout = client.get_payout_by_asset(asset_name, timeframe_payout.replace('M', ''))
                    if payout is not None and isinstance(payout, (int, float)):
                        if payout >= MIN_PAYOUT:
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
        return []

    logger.info(f"{len(open_otc_assets_with_payout)} open OTC assets with payout >= {MIN_PAYOUT}% found.")

    # Calcular indicadores apenas para ativos que passaram no filtro de payout
    asset_names_for_analysis = [asset for asset, _ in open_otc_assets_with_payout]
    indicators = {}
    prices = {}
    if asset_names_for_analysis:
        logger.debug("Fetching real-time prices for assets meeting payout criteria...")
        prices = await get_realtime_prices(client, asset_names_for_analysis)
        logger.debug(f"Fetched prices for {len(prices)} assets.")

        logger.debug(f"Calculating initial indicators for {len(asset_names_for_analysis)} assets meeting payout criteria...")
        indicators = await calculate_indicators(client, asset_names_for_analysis)
        logger.debug(f"Calculated indicators for {len(indicators)} assets.")
    else:
        logger.info("No assets meet payout criteria. Skipping indicator calculation.")

    tradable_assets_final = []
    logger.debug("Applying initial trading criteria (RSI, Price vs SMA, ATR) to further filter assets...")
    for asset, payout in open_otc_assets_with_payout:
        indicator_values = indicators.get(asset, {})
        price = prices.get(asset)
        rsi = indicator_values.get("RSI")
        sma = indicator_values.get("SMA")
        atr = indicator_values.get("ATR")

        logger.debug(f"Checking {asset} for initial trading criteria: Price={price}, RSI={rsi}, SMA={sma}, ATR={atr}. Payout={payout}%.")
        if (
            isinstance(rsi, (int, float)) and rsi is not None and
            isinstance(sma, (int, float)) and sma is not None and
            isinstance(atr, (int, float)) and atr is not None and
            isinstance(price, (int, float)) and price is not None
        ):
            meets_trading_criteria = False
            reason = "Initial criteria not met"
            if rsi < RSI_BUY_THRESHOLD and price > sma:
                meets_trading_criteria = True
                reason = f"Initial CALL criterion met (RSI={rsi:.2f} < {RSI_BUY_THRESHOLD} and Price={price:.5f} > SMA={sma:.5f})"
            elif rsi > RSI_SELL_THRESHOLD and atr < ATR_MAX:
                meets_trading_criteria = True
                reason = f"Initial PUT criterion met (RSI={rsi:.2f} > {RSI_SELL_THRESHOLD} and ATR={atr:.5f} < {ATR_MAX})"

            if meets_trading_criteria:
                tradable_assets_final.append((asset, payout))
                logger.debug(f"Asset {asset} PASSED initial trading criteria check: {reason}.")
            else:
                logger.debug(f"Asset {asset} FAILED initial trading criteria check: {reason}.")
        else:
            logger.debug(f"Asset {asset} skipped: Missing or non-numeric data (RSI:{rsi}, SMA:{sma}, ATR:{atr}, Price:{price}).")

    reverse = (sort_order == 'desc')
    if sort_by == 'payout':
        tradable_assets_final.sort(key=lambda x: x[1], reverse=reverse)
        logger.debug(f"Final tradable assets sorted by payout {'descending' if reverse else 'ascending'}.")
    elif sort_by == 'price':
        tradable_assets_final.sort(key=lambda x: prices.get(x[0], float('-inf') if reverse else float('inf')), reverse=reverse)
        logger.debug(f"Final tradable assets sorted by price {'descending' if reverse else 'ascending'}.")

    return tradable_assets_final