import logging
import asyncio
from quotexapi.stable_api import Quotex
from settings import TIMEFRAME, MIN_PAYOUT, ASSETS

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
    """Fetch and list specified open OTC assets with payout percentages and real-time prices meeting the minimum threshold."""
    # Validate timeframe
    valid_timeframes = ['1M', '5M', '24H']
    timeframe = TIMEFRAME if TIMEFRAME in valid_timeframes else '1M'
    if TIMEFRAME != timeframe:
        logger.warning(f"Invalid TIMEFRAME '{TIMEFRAME}' in .env. Using default '1M'.")

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

    # Fetch real-time prices for open OTC assets
    asset_names = [asset for asset, _ in open_otc_assets]
    prices = await get_realtime_prices(client, asset_names)

    # Log the list of open OTC assets with payouts and prices
    if open_otc_assets:
        logger.info(f"Available open OTC assets ({len(open_otc_assets)}) for timeframe {timeframe} with minimum payout {MIN_PAYOUT}%:")
        for asset, payout in open_otc_assets:
            price = prices.get(asset, "N/A")
            logger.info(f"  - {asset}: {payout}% payout, Price: {price}")
    else:
        logger.info(f"No open OTC assets meet the minimum payout of {MIN_PAYOUT}% for timeframe {timeframe}.")

    return [asset for asset, _ in open_otc_assets]