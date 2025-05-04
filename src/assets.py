import logging
import asyncio
from quotexapi.stable_api import Quotex
from settings import TIMEFRAME, MIN_PAYOUT, ASSETS, SORT_BY, SORT_ORDER
from indicators import calculate_indicators

logger = logging.getLogger(__name__)

async def get_realtime_prices(client: Quotex, assets: list) -> dict:
    """Fetch real-time prices for the specified assets."""
    prices = {}
    
    # Start real-time price streaming for all assets in parallel
    tasks = [client.start_realtime_price(asset) for asset in assets]
    await asyncio.gather(*tasks, return_exceptions=True)
    
    # Wait for price data to be available (up to 2 attempts, 0.5 seconds each)
    for attempt in range(2):
        for asset in assets:
            try:
                price_data = await client.get_realtime_price(asset)
                logger.debug(f"Price data for {asset} (attempt {attempt + 1}): {price_data}")
                if price_data and isinstance(price_data, list) and len(price_data) > 0:
                    # Extract the latest price (highest timestamp)
                    latest_entry = max(price_data, key=lambda x: x['time'])
                    price = latest_entry.get('price')
                    if price is not None:
                        prices[asset] = price
                    else:
                        logger.warning(f"No price field available for {asset}")
                else:
                    logger.warning(f"Invalid or empty price data for {asset}")
            except Exception as e:
                logger.warning(f"Failed to fetch price for {asset}: {e}")
        if all(asset in prices for asset in assets):
            break  # All prices fetched successfully
        await asyncio.sleep(0.5)  # Wait before retrying

    return prices

async def list_open_otc_assets(client: Quotex):
    """Fetch and list specified open OTC assets with payout percentages, real-time prices, and technical indicators, sorted by specified criteria."""
    # Validate timeframe
    valid_timeframes = ['1M', '5M', '24H']
    timeframe = TIMEFRAME if TIMEFRAME in valid_timeframes else '1M'
    if TIMEFRAME != timeframe:
        logger.warning(f"Invalid TIMEFRAME '{TIMEFRAME}' in .env. Using default '1M'.")

    # Validate sort criteria
    valid_sort_by = ['payout', 'price']
    sort_by = SORT_BY if SORT_BY in valid_sort_by else 'payout'
    if SORT_BY != sort_by:
        logger.warning(f"Invalid SORT_BY '{SORT_BY}' in .env. Using default 'payout'.")
    
    valid_sort_order = ['asc', 'desc']
    sort_order = SORT_ORDER if SORT_ORDER in valid_sort_order else 'desc'
    if SORT_ORDER != sort_order:
        logger.warning(f"Invalid SORT_ORDER '{SORT_ORDER}' in .env. Using default 'desc'.")

    # Ensure instruments are loaded
    while client.api.instruments is None:
        logger.debug("Waiting for instruments to load...")
        await asyncio.sleep(0.2)

    # Fetch all assets and payment data
    assets = await client.get_all_assets()
    otc_assets = [asset for asset in assets.keys() if asset.lower().endswith('_otc')]

    # Filter by specified assets if provided, otherwise use all OTC assets
    if ASSETS:
        selected_assets = [asset.strip() for asset in ASSETS if asset.strip() in otc_assets]
        invalid_assets = [asset.strip() for asset in ASSETS if asset.strip() and asset.strip() not in otc_assets]
        if invalid_assets:
            logger.warning(f"Invalid assets specified in .env: {invalid_assets}")
        if not selected_assets:
            logger.info("No valid assets specified in .env match open OTC assets.")
            return []
        otc_assets = selected_assets
    else:
        logger.debug("No ASSETS specified in .env. Listing all open OTC assets.")

    # Check which OTC assets are open and get their payouts
    open_otc_assets = []
    for asset in otc_assets:
        try:
            is_open = await client.check_asset_open(asset)
            if is_open:
                # Get payout for the specified timeframe
                timeframe_key = timeframe.replace('M', '')  # Convert 1M to 1, 5M to 5
                payout = client.get_payout_by_asset(asset, timeframe_key)
                if payout is not None and payout >= MIN_PAYOUT:
                    open_otc_assets.append((asset, payout))
                else:
                    if payout is None:
                        logger.warning(f"No payout data available for {asset} (timeframe: {timeframe})")
                        logger.debug(f"Payment data for {asset}: {client.get_payment().get(asset)}")
                    else:
                        logger.debug(f"Asset {asset} filtered out: payout {payout}% < minimum {MIN_PAYOUT}%")
        except Exception as e:
            logger.warning(f"Failed to check asset {asset}: {e}")

    # Fetch real-time prices and indicators for open OTC assets
    asset_names = [asset for asset, _ in open_otc_assets]
    prices = await get_realtime_prices(client, asset_names)
    indicators = await calculate_indicators(client, asset_names)

    # Sort assets based on SORT_BY and SORT_ORDER
    reverse = (sort_order == 'desc')
    if sort_by == 'payout':
        open_otc_assets.sort(key=lambda x: x[1], reverse=reverse)
    elif sort_by == 'price':
        open_otc_assets.sort(key=lambda x: prices.get(x[0], float('-inf') if reverse else float('inf')), reverse=reverse)

    # Log the list of open OTC assets with payouts, prices, and indicators
    if open_otc_assets:
        logger.info(f"Available open OTC assets ({len(open_otc_assets)}) for timeframe {timeframe} with minimum payout {MIN_PAYOUT}%, sorted by {sort_by} ({sort_order}):")
        for asset, payout in open_otc_assets:
            price = prices.get(asset, "N/A")
            indicator_values = indicators.get(asset, {})
            indicator_str = ", ".join(f"{ind}: {val if val is not None else 'N/A'}" for ind, val in indicator_values.items())
            logger.info(f"  - {asset}: {payout}% payout, Price: {price}, {indicator_str}")
    else:
        logger.info(f"No open OTC assets meet the minimum payout of {MIN_PAYOUT}% for timeframe {timeframe}.")

    return [asset for asset, _ in open_otc_assets]