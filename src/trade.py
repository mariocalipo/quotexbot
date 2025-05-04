import logging
import asyncio
from quotexapi.stable_api import Quotex
from settings import TRADE_ENABLED, TRADE_PERCENTAGE, TRADE_DURATION, RSI_BUY_THRESHOLD, RSI_SELL_THRESHOLD

logger = logging.getLogger(__name__)

async def execute_trades(client: Quotex, assets: list, indicators: dict):
    """Execute trades based on indicator values for the specified assets."""
    if not TRADE_ENABLED:
        logger.info("Trading is disabled (TRADE_ENABLED=false). Skipping trade execution.")
        return

    if not assets:
        logger.info("No assets available for trading.")
        return

    # Get the current balance
    try:
        balance = await client.get_balance()
        logger.debug(f"Current balance: {balance} USD")
    except Exception as e:
        logger.error(f"Failed to retrieve balance: {e}")
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

            # Calculate trade amount as a percentage of the current balance
            amount = (TRADE_PERCENTAGE / 100) * balance
            # Ensure the amount is within bounds: minimum 1 USD, maximum 5000 USD
            amount = max(1.0, min(5000.0, amount))
            # Round to the nearest integer (no decimals)
            amount = round(amount)
            duration = TRADE_DURATION
            logger.info(f"Placing {direction} order for {asset}: amount={amount} USD (calculated as {TRADE_PERCENTAGE}% of balance), duration={duration} seconds")

            # Place the trade
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