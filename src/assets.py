import logging
import asyncio
from quotexapi.stable_api import Quotex
from settings import TIMEFRAME, MIN_PAYOUT, ASSETS, SORT_BY, SORT_ORDER, RSI_BUY_THRESHOLD, RSI_SELL_THRESHOLD, ATR_MAX
from indicators import calculate_indicators

logger = logging.getLogger(__name__)

async def get_realtime_prices(client: Quotex, assets: list) -> dict:
    """Fetch real-time prices for the specified assets."""
    prices = {}
    
    tasks = [client.start_realtime_price(asset) for asset in assets]
    await asyncio.gather(*tasks, return_exceptions=True)
    
    for attempt in range(2):
        for asset in assets:
            try:
                price_data = await client.get_realtime_price(asset)
                if price_data and isinstance(price_data, list) and len(price_data) > 0:
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
            break
        await asyncio.sleep(0.5)

    return prices

async def list_open_otc_assets(client: Quotex):
    """Fetch and list only open OTC assets that meet trading criteria (RSI, SMA, ATR) with payout percentages, real-time prices, and technical indicators, sorted by specified criteria."""
    valid_timeframes = ['1M', '5M', '24H']
    timeframe = TIMEFRAME if TIMEFRAME in valid_timeframes else '1M'
    if TIMEFRAME != timeframe:
        logger.warning(f"Invalid TIMEFRAME '{TIMEFRAME}' in .env. Using default '1M'.")

    valid_sort_by = ['payout', 'price']
    sort_by = SORT_BY if SORT_BY in valid_sort_by else 'payout'
    if SORT_BY != sort_by:
        logger.warning(f"Invalid SORT_BY '{SORT_BY}' in .env. Using default 'payout'.")
    
    valid_sort_order = ['asc', 'desc']
    sort_order = SORT_ORDER if SORT_ORDER in valid_sort_order else 'desc'
    if SORT_ORDER != sort_order:
        logger.warning(f"Invalid SORT_ORDER '{SORT_ORDER}' in .env. Using default 'desc'.")

    while client.api.instruments is None:
        logger.waiting("Waiting for instruments to load...")
        await asyncio.sleep(0.2)

    assets = await client.get_all_assets()
    otc_assets = [asset for asset in assets.keys() if asset.lower().endswith('_otc')]

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

    open_otc_assets = []
    for asset in otc_assets:
        try:
            is_open = await client.check_asset_open(asset)
            if is_open:
                timeframe_key = timeframe.replace('M', '')
                payout = client.get_payout_by_asset(asset, timeframe_key)
                if payout is not None and payout >= MIN_PAYOUT:
                    open_otc_assets.append((asset, payout))
                else:
                    if payout is None:
                        logger.warning(f"No payout data available for {asset} (timeframe: {timeframe})")
                    else:
                        logger.debug(f"Asset {asset} filtered out: payout {payout}% < minimum {MIN_PAYOUT}%")
        except Exception as e:
            logger.warning(f"Failed to check asset {asset}: {e}")

    asset_names = [asset for asset, _ in open_otc_assets]
    prices = await get_realtime_prices(client, asset_names)
    indicators = await calculate_indicators(client, asset_names)

    tradable_assets = []
    for asset, payout in open_otc_assets:
        indicator_values = indicators.get(asset, {})
        price = prices.get(asset)
        rsi = indicator_values.get("RSI")
        sma = indicator_values.get("SMA")
        atr = indicator_values.get("ATR")

        if rsi is None or sma is None or atr is None:
            logger.debug(f"Skipping asset {asset} due to missing indicators: RSI={rsi}, SMA={sma}, ATR={atr}")
            continue

        if price is None:
            logger.debug(f"Skipping asset {asset} due to missing price")
            continue

        meets_trading_criteria = (
            (rsi < RSI_BUY_THRESHOLD and price > sma) or
            (rsi > RSI_SELL_THRESHOLD and atr < ATR_MAX)
        )

        if meets_trading_criteria:
            tradable_assets.append((asset, payout))
        else:
            logger.debug(f"Asset {asset} does not meet trading criteria: RSI={rsi} (buy: {RSI_BUY_THRESHOLD}, sell: {RSI_SELL_THRESHOLD}), price={price}, SMA={sma}, ATR={atr}")

    reverse = (sort_order == 'desc')
    if sort_by == 'payout':
        tradable_assets.sort(key=lambda x: x[1], reverse=reverse)
    elif sort_by == 'price':
        tradable_assets.sort(key=lambda x: prices.get(x[0], float('-inf') if reverse else float('inf')), reverse=reverse)

    if tradable_assets:
        logger.info(f"Tradable open OTC assets ({len(tradable_assets)}) for timeframe {timeframe} with minimum payout {MIN_PAYOUT}%, sorted by {sort_by} ({sort_order}):")
        for asset, payout in tradable_assets:
            price = prices.get(asset, "N/A")
            indicator_values = indicators.get(asset, {})
            indicator_str = ", ".join(f"{ind}: {val if val is not None else 'N/A'}" for ind, val in indicator_values.items())
            logger.info(f"  - {asset}: {payout}% payout, Price: {price}, {indicator_str}")
    else:
        logger.info(f"No open OTC assets meet trading criteria for timeframe {timeframe} with minimum payout {MIN_PAYOUT}%.")

    return [asset for asset, _ in tradable_assets]