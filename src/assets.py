import logging
import asyncio
from quotexapi.stable_api import Quotex

logger = logging.getLogger(__name__)

async def list_open_otc_assets(client: Quotex):
    """Fetch and list all open OTC assets available for trading."""
    # Fetch and filter OTC assets
    assets = await client.get_all_assets()
    otc_assets = [asset for asset in assets.keys() if asset.lower().endswith('_otc')]

    # Check which OTC assets are open
    open_otc_assets = []
    for asset in otc_assets:
        try:
            is_open = await client.check_asset_open(asset)
            if is_open:
                open_otc_assets.append(asset)
        except Exception as e:
            logger.warning(f"Failed to check asset {asset}: {e}")

    logger.info(f"Available open OTC assets ({len(open_otc_assets)}): {open_otc_assets}")
    return open_otc_assets