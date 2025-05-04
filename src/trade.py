import logging
import asyncio
import time
from quotexapi.stable_api import Quotex
from settings import TRADE_ENABLED, TRADE_PERCENTAGE, TRADE_DURATION, RSI_BUY_THRESHOLD, RSI_SELL_THRESHOLD

logger = logging.getLogger(__name__)

# Lista para armazenar ordens abertas
open_orders = []

async def execute_trades(client: Quotex, assets: list, indicators: dict):
    """Execute trades based on indicator values for the specified assets and manage open orders."""
    if not TRADE_ENABLED:
        logger.info("Trading is disabled (TRADE_ENABLED=false). Skipping trade execution.")
        return

    if not assets:
        logger.info("No assets available for trading.")
        return

    # Get the initial balance
    try:
        balance = await client.get_balance()
        logger.debug(f"Initial balance: {balance} USD")
    except Exception as e:
        logger.error(f"Failed to retrieve initial balance: {e}")
        return

    # Monitor open orders
    current_time = int(time.time())  # Use local system time as a reference
    orders_to_remove = []
    for order in open_orders:
        try:
            order_id = order['id']
            asset = order['asset']
            direction = order['direction']
            amount = order['amount']
            open_timestamp = order['openTimestamp']
            duration = order['duration']

            # Estimate when the order should have closed (open_timestamp + duration + buffer)
            estimated_close_time = open_timestamp + duration + 10  # 10 seconds buffer
            logger.debug(f"Checking order {order_id} for {asset}: current_time={current_time}, estimated_close_time={estimated_close_time}")

            # Check if enough time has passed to consider the order closed
            if current_time >= estimated_close_time:
                # Check the result of the order
                success, result = await client.check_win(order_id)
                if success:
                    if result == "win":
                        profit = amount * (order['percentProfit'] / 100)
                        logger.info(f"Order for {asset} ({direction}) closed: profit={profit:.2f} USD (percentProfit={order['percentProfit']}%)")
                    elif result == "loss":
                        logger.info(f"Order for {asset} ({direction}) closed: loss={amount:.2f} USD (percentLoss={order['percentLoss']}%)")
                    else:
                        logger.info(f"Order for {asset} ({direction}) closed: result=draw, no profit/loss")
                    # Mark the order for removal
                    orders_to_remove.append(order)
                else:
                    logger.error(f"Failed to check result for order {order_id} on {asset}: {result}")
                    # If the order can't be checked, assume it's closed after a reasonable time and remove it
                    orders_to_remove.append(order)
        except Exception as e:
            logger.error(f"Error checking order {order.get('id')} for {order.get('asset')}: {e}")

    # Remove closed orders
    for order in orders_to_remove:
        open_orders.remove(order)
        logger.debug(f"Removed closed order: {order['id']} for {order['asset']}")

    # Execute new trades
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
            logger.info(f"Placing {direction} order for {asset}: amount={amount} USD (calculated as {TRADE_PERCENTAGE}% of balance={balance} USD), duration={duration} seconds")

            # Place the trade
            success, response = await client.buy(
                asset=asset,
                amount=amount,
                direction=direction,
                duration=duration
            )

            if success:
                logger.info(f"Successfully placed {direction} order for {asset}: {response}")
                # Store the order details for monitoring
                order_details = {
                    'id': response['id'],
                    'asset': asset,
                    'direction': direction,
                    'amount': amount,
                    'openTimestamp': response['openTimestamp'],
                    'duration': duration,  # Store duration to estimate close time
                    'percentProfit': response['percentProfit'],
                    'percentLoss': response['percentLoss']
                }
                open_orders.append(order_details)
                logger.debug(f"Added order to open_orders: {order_details}")

                # Update the balance using the response's accountBalance
                new_balance = response.get('accountBalance')
                if new_balance is not None:
                    balance = new_balance
                    logger.debug(f"Updated balance from response after order for {asset}: {balance} USD")
                else:
                    # Fallback to manual calculation
                    balance -= amount
                    logger.debug(f"Fallback: Manually updated balance after order for {asset}: {balance} USD")
            else:
                logger.error(f"Failed to place {direction} order for {asset}: {response}")

            # Small delay to avoid rate limiting
            await asyncio.sleep(1)

        except Exception as e:
            logger.error(f"Error executing trade for {asset}: {e}")