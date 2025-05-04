import logging
import asyncio
import time
from quotexapi.stable_api import Quotex
from settings import TRADE_ENABLED, TRADE_PERCENTAGE, TRADE_PERCENTAGE_MIN, TRADE_PERCENTAGE_MAX, TRADE_DURATION, RSI_BUY_THRESHOLD, RSI_SELL_THRESHOLD, ATR_MAX, TRADE_COOLDOWN, DAILY_LOSS_LIMIT, CONSECUTIVE_LOSSES_THRESHOLD, CONSECUTIVE_WINS_THRESHOLD

logger = logging.getLogger(__name__)

open_orders = []
last_trade_time = {}
daily_loss = 0.0
initial_daily_balance = 0.0
last_reset_time = None
consecutive_losses = 0
consecutive_wins = 0
current_trade_percentage = TRADE_PERCENTAGE

async def execute_trades(client: Quotex, assets: list, indicators: dict):
    """Execute trades based on indicator values for the specified assets and manage open orders with risk management."""
    global daily_loss, initial_daily_balance, last_reset_time, consecutive_losses, consecutive_wins, current_trade_percentage

    if not TRADE_ENABLED:
        logger.info("Trading is disabled (TRADE_ENABLED=false). Skipping trade execution.")
        return

    if not assets:
        logger.info("No assets available for trading.")
        return

    current_time = int(time.time())
    if last_reset_time is None or (current_time - last_reset_time) >= 86400:
        try:
            initial_daily_balance = await client.get_balance()
            daily_loss = 0.0
            last_reset_time = current_time
            logger.info(f"New trading day started. Initial balance: {initial_daily_balance} USD")
        except Exception as e:
            logger.error(f"Failed to retrieve initial daily balance: {e}")
            return

    orders_to_remove = []
    for order in open_orders:
        try:
            order_id = order['id']
            asset = order['asset']
            direction = order['direction']
            amount = order['amount']
            open_timestamp = order['openTimestamp']
            duration = order['duration']

            estimated_close_time = open_timestamp + duration + 10
            logger.debug(f"Checking order {order_id} for {asset}: current_time={current_time}, estimated_close_time={estimated_close_time}")

            if current_time >= estimated_close_time:
                result = await client.check_win(order_id)
                if isinstance(result, tuple):
                    success, result = result
                else:
                    success = False
                    result = str(result) if result is not None else "Unknown result"

                if success:
                    if result == "win":
                        profit = amount * (order['percentProfit'] / 100)
                        logger.info(f"Order for {asset} ({direction}) closed: profit={profit:.2f} USD (percentProfit={order['percentProfit']}%)")
                        daily_loss -= profit
                        consecutive_wins += 1
                        consecutive_losses = 0
                    elif result == "loss":
                        logger.info(f"Order for {asset} ({direction}) closed: loss={amount:.2f} USD (percentLoss={order['percentLoss']}%)")
                        daily_loss += amount
                        consecutive_losses += 1
                        consecutive_wins = 0
                    else:
                        logger.info(f"Order for {asset} ({direction}) closed: result=draw, no profit/loss")
                        consecutive_losses = 0
                        consecutive_wins = 0
                    orders_to_remove.append(order)
                else:
                    logger.error(f"Failed to check result for order {order_id} on {asset}: {result}")
                    orders_to_remove.append(order)
        except Exception as e:
            logger.error(f"Error checking order {order_id} for {asset}: {e}")
            orders_to_remove.append(order)

    for order in orders_to_remove:
        open_orders.remove(order)
        logger.debug(f"Removed closed order: {order['id']} for {order['asset']}")

    if consecutive_losses >= CONSECUTIVE_LOSSES_THRESHOLD:
        current_trade_percentage = TRADE_PERCENTAGE_MIN
        logger.info(f"Reduced trade percentage to {current_trade_percentage}% due to {consecutive_losses} consecutive losses.")
    elif consecutive_wins >= CONSECUTIVE_WINS_THRESHOLD:
        current_trade_percentage = TRADE_PERCENTAGE_MAX
        logger.info(f"Increased trade percentage to {current_trade_percentage}% due to {consecutive_wins} consecutive wins.")
    else:
        current_trade_percentage = TRADE_PERCENTAGE

    if initial_daily_balance > 0:
        loss_percentage = (daily_loss / initial_daily_balance) * 100
        if loss_percentage >= DAILY_LOSS_LIMIT:
            logger.warning(f"Daily loss limit of {DAILY_LOSS_LIMIT}% reached (current loss: {loss_percentage:.2f}%). Disabling trading until tomorrow.")
            return

    balance = None
    try:
        balance = await client.get_balance()
        logger.debug(f"Initial balance for this trading cycle: {balance} USD")
    except Exception as e:
        logger.error(f"Failed to retrieve initial balance for trading cycle: {e}")
        return

    trade_executed = False
    for asset in assets:
        try:
            last_trade = last_trade_time.get(asset, 0)
            if current_time - last_trade < TRADE_COOLDOWN:
                logger.debug(f"Skipping trade for {asset}: still in cooldown (last trade at {last_trade}, cooldown={TRADE_COOLDOWN}s)")
                continue

            await asyncio.sleep(2)

            asset_indicators = indicators.get(asset, {})
            rsi = asset_indicators.get("RSI")
            sma = asset_indicators.get("SMA")
            atr = asset_indicators.get("ATR")

            if rsi is None or sma is None or atr is None:
                logger.debug(f"Skipping trade for {asset}: missing indicators (RSI={rsi}, SMA={sma}, ATR={atr})")
                continue

            price_data = await client.get_realtime_price(asset)
            if not price_data or not isinstance(price_data, list) or len(price_data) == 0:
                logger.debug(f"Skipping trade for {asset}: unable to fetch current price")
                continue
            latest_entry = max(price_data, key=lambda x: x['time'])
            current_price = latest_entry.get('price')
            if current_price is None:
                logger.debug(f"Skipping trade for {asset}: current price not available")
                continue

            direction = None
            if rsi < RSI_BUY_THRESHOLD and current_price > sma:
                direction = "call"
                logger.info(f"RSI {rsi} < {RSI_BUY_THRESHOLD} and price {current_price} > SMA {sma} for {asset}. Placing buy order.")
            elif rsi > RSI_SELL_THRESHOLD and atr < ATR_MAX:
                direction = "put"
                logger.info(f"RSI {rsi} > {RSI_SELL_THRESHOLD} and ATR {atr} < {ATR_MAX} for {asset}. Placing sell order.")
            else:
                logger.debug(f"No trade condition met for {asset}: RSI={rsi} (buy threshold={RSI_BUY_THRESHOLD}, sell threshold={RSI_SELL_THRESHOLD}), price={current_price}, SMA={sma}, ATR={atr}")
                continue

            amount = (current_trade_percentage / 100) * balance
            amount = max(1.0, min(5000.0, amount))
            amount = round(amount)
            duration = TRADE_DURATION
            logger.info(f"Placing {direction} order for {asset}: amount={amount} USD (calculated as {current_trade_percentage}% of balance={balance} USD), duration={duration} seconds")

            success, response = await client.buy(
                asset=asset,
                amount=amount,
                direction=direction,
                duration=duration
            )

            if success:
                logger.info(f"Successfully placed {direction} order for {asset}: {response}")
                order_details = {
                    'id': response['id'],
                    'asset': asset,
                    'direction': direction,
                    'amount': amount,
                    'openTimestamp': response['openTimestamp'],
                    'duration': duration,
                    'percentProfit': response['percentProfit'],
                    'percentLoss': response['percentLoss']
                }
                open_orders.append(order_details)
                logger.debug(f"Added order to open_orders: {order_details}")

                last_trade_time[asset] = current_time

                expected_balance = balance - amount
                new_balance = response.get('accountBalance')
                if new_balance is not None:
                    logger.debug(f"Expected balance after order for {asset}: {expected_balance:.2f} USD, API reported balance: {new_balance:.2f} USD")
                    balance = new_balance
                    logger.debug(f"Updated balance from response after order for {asset}: {balance} USD")
                else:
                    balance = expected_balance
                    logger.debug(f"Fallback: Manually updated balance after order for {asset}: {balance} USD")
            else:
                logger.error(f"Failed to place {direction} order for {asset}: {response}")

            trade_executed = True

        except Exception as e:
            logger.error(f"Error executing trade for {asset}: {e}")

    if not trade_executed:
        logger.info(f"No trades executed. Reasons: RSI thresholds (buy: {RSI_BUY_THRESHOLD}, sell: {RSI_SELL_THRESHOLD}), ATR limit ({ATR_MAX}), cooldown ({TRADE_COOLDOWN}s), or asset availability.")