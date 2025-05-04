import logging
import asyncio
from quotexapi.stable_api import Quotex
from settings import TRADE_ENABLED, TRADE_AMOUNT, TRADE_DURATION, RSI_BUY_THRESHOLD, RSI_SELL_THRESHOLD

logger = logging.getLogger(__name__)

async def execute_trades(client: Quotex, assets: list, indicators: dict):
    """Execute trades based on indicator values for the specified assets."""
    if not TRADE_ENABLED:
        logger.info("Trading is disabled (TRADE_ENABLED=false). Skipping trade execution.")
        return

    if not assets:
        logger.info("No assets available for trading.")
        return

    for asset in assets:
        try:
            # Get indicator values for the asset
            asset_indicators = indicators.get(asset, {})
            rsi = asset_indicators.get("RSI")

            if rsi is None:
                logger.debug(f"Skipping trade for {asset}: RSI not available.")
                continue

            # Determine trade direction based on RSI
            if rsi < RSI_BUY_THRESHOLD:
                direction = "call"  # Buy (call option)
                logger.info(f"RSI {rsi} < {RSI_BUY_THRESHOLD} for {asset}. Placing buy order.")
            elif rsi > RSI_SELL_THRESHOLD:
                direction = "put"  # Sell (put option)
                logger.info(f"RSI {rsi} > {RSI_SELL_THRESHOLD} for {asset}. Placing sell order.")
            else:
                logger.debug(f"No trade condition met for {asset}: RSI={rsi} (buy threshold={RSI_BUY_THRESHOLD}, sell threshold={RSI_SELL_THRESHOLD})")
                continue

            # Place the trade
            amount = TRADE_AMOUNT
            duration = TRADE_DURATION
            logger.info(f"Placing {direction} order for {asset}: amount={amount} USD, duration={duration} seconds")

            success, response = await client.buy(
                asset=asset,
                amount=amount,
                direction=direction,
                duration=duration
            )

            if success:
                logger.info(f"Successfully placed {direction} order for {asset}: {response}")
            else:
                logger.error(f"Failed to place {direction} order for {asset}: {response}")

            # Small delay to avoid rate limiting
            await asyncio.sleep(1)

        except Exception as e:
            logger.error(f"Error executing trade for {asset}: {e}")