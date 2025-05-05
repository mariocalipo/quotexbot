import logging
import asyncio
import time
from quotexapi.stable_api import Quotex
from settings import (
    TRADE_ENABLED, TRADE_PERCENTAGE, TRADE_PERCENTAGE_MIN, TRADE_PERCENTAGE_MAX,
    TRADE_DURATION, RSI_BUY_THRESHOLD, RSI_SELL_THRESHOLD, ATR_MAX, TRADE_COOLDOWN,
    DAILY_LOSS_LIMIT, CONSECUTIVE_LOSSES_THRESHOLD, CONSECUTIVE_WINS_THRESHOLD
)

# Initialize logger for this module
logger = logging.getLogger(__name__)

class TradingState:
    """Class to manage trading state safely."""
    def __init__(self):
        self.open_orders = []  # List of open orders
        self.last_trade_time = {}  # Last trade time per asset
        self.daily_loss = 0.0  # Accumulated daily loss
        self.initial_daily_balance = 0.0  # Initial balance for the day
        self.last_reset_time = None  # Last daily reset timestamp
        self.consecutive_losses = 0  # Count of consecutive losses
        self.consecutive_wins = 0  # Count of consecutive wins
        self.current_trade_percentage = TRADE_PERCENTAGE  # Current trade size percentage

    def reset_daily(self, balance: float, current_time: int):
        """Reset state for a new trading day."""
        self.daily_loss = 0.0
        self.initial_daily_balance = balance
        self.last_reset_time = current_time
        self.consecutive_losses = 0
        self.consecutive_wins = 0
        self.current_trade_percentage = TRADE_PERCENTAGE
        logger.info(f"Daily reset: Initial balance {self.initial_daily_balance:.2f} USD. Daily loss cleared.")

    def add_order(self, order_details: dict):
        """Add an order to the open orders list."""
        self.open_orders.append(order_details)
        logger.debug(f"Added order {order_details.get('id')} to open orders. Current count: {len(self.open_orders)}")

    def remove_order(self, order: dict):
        """Remove an order from the open orders list."""
        try:
            self.open_orders.remove(order)
            logger.debug(f"Removed order ID {order.get('id')} from open orders.")
        except ValueError:
            logger.warning(f"Failed to remove order ID {order.get('id')}: Not found in open orders.")

    def update_trade_time(self, asset: str, current_time: int):
        """Update the last trade time for an asset."""
        self.last_trade_time[asset] = current_time

    def update_loss(self, amount: float):
        """Increase daily loss and update loss streak."""
        self.daily_loss += amount
        self.consecutive_losses += 1
        self.consecutive_wins = 0
        logger.debug(f"Loss recorded. Wins: {self.consecutive_wins}, Losses: {self.consecutive_losses}. Daily loss: {self.daily_loss:.2f}")

    def update_win(self, profit: float):
        """Reduce daily loss with profit and update win streak."""
        self.daily_loss -= profit
        self.consecutive_wins += 1
        self.consecutive_losses = 0
        logger.debug(f"Win recorded. Wins: {self.consecutive_wins}, Losses: {self.consecutive_losses}. Daily loss: {self.daily_loss:.2f}")

    def adjust_trade_percentage(self):
        """Adjust trade percentage based on consecutive wins/losses."""
        old_percentage = self.current_trade_percentage
        if self.consecutive_losses >= CONSECUTIVE_LOSSES_THRESHOLD and self.current_trade_percentage > TRADE_PERCENTAGE_MIN:
            self.current_trade_percentage = max(TRADE_PERCENTAGE_MIN, self.current_trade_percentage * 0.8)
            logger.debug(f"Reduced trade percentage due to {self.consecutive_losses} losses. New: {self.current_trade_percentage:.2f}%")
        elif self.consecutive_wins >= CONSECUTIVE_WINS_THRESHOLD and self.current_trade_percentage < TRADE_PERCENTAGE_MAX:
            self.current_trade_percentage = min(TRADE_PERCENTAGE_MAX, self.current_trade_percentage * 1.2)
            logger.debug(f"Increased trade percentage due to {self.consecutive_wins} wins. New: {self.current_trade_percentage:.2f}%")
        else:
            self.current_trade_percentage = TRADE_PERCENTAGE
            self.current_trade_percentage = max(TRADE_PERCENTAGE_MIN, min(TRADE_PERCENTAGE_MAX, self.current_trade_percentage))

        if self.current_trade_percentage != old_percentage:
            logger.info(f"Trade percentage adjusted from {old_percentage:.2f}% to {self.current_trade_percentage:.2f}% (Wins: {self.consecutive_wins}, Losses: {self.consecutive_losses})")

    def check_daily_loss_limit(self, balance: float) -> bool:
        """Check if the daily loss limit has been reached."""
        if self.initial_daily_balance > 0:
            loss_percentage = (self.daily_loss / self.initial_daily_balance) * 100
            logger.debug(f"Daily loss: {self.daily_loss:.2f} USD ({loss_percentage:.2f}% of initial {self.initial_daily_balance:.2f} USD). Limit: {DAILY_LOSS_LIMIT:.2f}%")
            if loss_percentage >= DAILY_LOSS_LIMIT:
                logger.warning(f"Daily loss limit of {DAILY_LOSS_LIMIT:.2f}% reached ({loss_percentage:.2f}%). Trading disabled until next day.")
                return False
        elif DAILY_LOSS_LIMIT > 0:
            logger.warning("Daily loss limit active but initial balance not set or zero. Skipping limit check.")
        return True

# Single instance of trading state
trading_state = TradingState()

async def execute_trades(client: Quotex, assets: list, indicators: dict):
    """Execute trades based on indicators and trading conditions."""
    logger.debug("--- Entering execute_trades ---")
    logger.debug(f"Assets: {assets}")
    logger.debug(f"Indicator keys: {indicators.keys()}")

    if not TRADE_ENABLED:
        logger.info("Trading disabled (TRADE_ENABLED=false). Skipping execution.")
        logger.debug("--- Exiting execute_trades ---")
        return

    if not assets:
        logger.info("No tradable assets provided. Skipping execution.")
        logger.debug("--- Exiting execute_trades ---")
        return

    current_time = int(time.time())

    # Fetch current balance
    current_balance = None
    try:
        current_balance = await client.get_balance()
        if current_balance is not None and isinstance(current_balance, (int, float)):
            logger.debug(f"Current balance: {current_balance:.2f} USD")
        else:
            logger.warning(f"Invalid initial balance: {current_balance}")
            current_balance = 0.0
    except Exception as e:
        logger.error(f"Failed to fetch initial balance: {e}", exc_info=True)
        current_balance = 0.0

    # Daily reset
    if trading_state.last_reset_time is None or (current_time - trading_state.last_reset_time) >= 86400:
        logger.info("-" * 30)
        logger.info("Starting new trading day.")
        trading_state.reset_daily(current_balance, current_time)
    else:
        logger.debug(f"Continuing trading day. Loss: {trading_state.daily_loss:.2f}, Initial balance: {trading_state.initial_daily_balance:.2f}, Wins: {trading_state.consecutive_wins}, Losses: {trading_state.consecutive_losses}")

    # Process open orders
    orders_to_remove = []
    logger.debug(f"Checking {len(trading_state.open_orders)} open orders...")
    for order in trading_state.open_orders:
        order_id = order.get('id')
        asset = order.get('asset')
        direction = order.get('direction')
        amount = order.get('amount')
        openTimestamp = order.get('openTimestamp')
        percent_profit = order.get('percentProfit', 0)

        logger.debug(f"Checking order ID: {order_id} on {asset} (Opened: {openTimestamp}, Amount: {amount:.2f})")

        try:
            result_data = await client.check_win(order_id)
            if result_data and isinstance(result_data, dict):
                game_state = result_data.get("game_state")
                if game_state == 1:
                    win_status_raw = result_data.get("win")
                    api_profit_amount = result_data.get("profitAmount", 0.0)
                    close_price = result_data.get("closePrice", "N/A")
                    logger.debug(f"Order {order_id} data: {result_data}")

                    profit_loss_amount = 0.0
                    outcome_status = "Unknown"
                    if win_status_raw is True:
                        profit_loss_amount = amount * (percent_profit / 100.0)
                        outcome_status = "WIN"
                        trading_state.update_win(profit_loss_amount)
                        logger.info(f"Order {order_id} ({asset} {direction}, {amount:.2f} USD) FINISHED. WIN. Profit: {profit_loss_amount:.2f} USD. Close: {close_price}. API P/L: {api_profit_amount:.2f}")
                    elif win_status_raw is False:
                        profit_loss_amount = -amount
                        outcome_status = "LOSS"
                        trading_state.update_loss(amount)
                        logger.info(f"Order {order_id} ({asset} {direction}, {amount:.2f} USD) FINISHED. LOSS. Loss: {amount:.2f} USD. Close: {close_price}. API P/L: {api_profit_amount:.2f}")
                    elif win_status_raw is None and api_profit_amount == 0.0:
                        outcome_status = "DRAW"
                        logger.info(f"Order {order_id} ({asset} {direction}, {amount:.2f} USD) FINISHED. DRAW. P/L: {api_profit_amount:.2f} USD. Close: {close_price}")
                    else:
                        logger.warning(f"Order {order_id} ({asset}) finished with unexpected win_status: {win_status_raw}. Data: {result_data}")
                    orders_to_remove.append(order)
                else:
                    logger.debug(f"Order {order_id} for {asset} is OPEN (game_state: {game_state}). Keeping in list.")
            elif result_data is None:
                logger.debug(f"check_win for order ID {order_id} returned None. Order still processing or unavailable. Keeping in list.")
            elif result_data is False:
                logger.warning(f"check_win for order ID {order_id} returned False. Data unavailable or API error. Keeping in list.")
            else:
                logger.error(f"check_win for order ID {order_id} returned unexpected type: {type(result_data)}. Data: {result_data}. Keeping in list.")
        except Exception as e:
            logger.error(f"Error processing check_win for order ID {order.get('id')}: {e}", exc_info=True)
            logger.error(f"Removing order ID {order.get('id')} due to processing error.")
            orders_to_remove.append(order)

    for order in orders_to_remove:
        trading_state.remove_order(order)

    # Adjust trade percentage
    trading_state.adjust_trade_percentage()

    # Check daily loss limit
    if not trading_state.check_daily_loss_limit(current_balance):
        logger.debug("--- Exiting execute_trades: Daily loss limit reached ---")
        return

    # Execute new trades
    logger.debug("Checking for new trade opportunities...")
    trade_executed_in_this_cycle = False
    balance = current_balance

    if balance is None or not isinstance(balance, (int, float)) or balance <= 0:
        logger.warning("Invalid or zero balance. Cannot place new trades.")
        logger.debug("--- Exiting execute_trades ---")
        return

    logger.debug(f"Processing {len(assets)} tradable assets for trade signals...")
    for asset in assets:
        logger.debug(f"Evaluating {asset}...")
        if any(order.get('asset') == asset for order in trading_state.open_orders):
            logger.debug(f"Skipping {asset}: Open order exists.")
            continue

        current_time = int(time.time())
        last_trade = trading_state.last_trade_time.get(asset, 0)
        if current_time - last_trade < TRADE_COOLDOWN:
            logger.debug(f"Skipping {asset}: In cooldown (last trade: {last_trade}, cooldown: {TRADE_COOLDOWN}s, current: {current_time}).")
            continue

        asset_indicators = indicators.get(asset, {})
        rsi = asset_indicators.get("RSI")
        sma = asset_indicators.get("SMA")
        atr = asset_indicators.get("ATR")

        logger.debug(f"Indicators for {asset}: RSI={rsi}, SMA={sma}, ATR={atr}")
        if not all(isinstance(val, (int, float)) for val in [rsi, sma, atr]) or any(val is None for val in [rsi, sma, atr]):
            logger.debug(f"Skipping {asset}: Invalid or missing indicators (RSI={rsi}, SMA={sma}, ATR={atr}).")
            continue

        try:
            price_data = await client.get_realtime_price(asset)
            current_price = None
            if isinstance(price_data, list) and len(price_data) > 0:
                try:
                    latest_entry = max(price_data, key=lambda x: x.get('time', 0))
                    current_price = latest_entry.get('price')
                except Exception as e:
                    logger.warning(f"Failed to process price list for {asset}: {e}. Data: {price_data}", exc_info=False)
            elif isinstance(price_data, dict) and price_data:
                current_price = price_data.get('price')
            if current_price is None or not isinstance(current_price, (int, float)):
                logger.debug(f"Skipping {asset}: Failed to fetch valid price. Data: {price_data}")
                continue
            logger.debug(f"Current price for {asset}: {current_price}")
        except Exception as e:
            logger.error(f"Error fetching price for {asset}: {e}", exc_info=True)
            continue

        direction = None
        trade_condition_met = False
        condition_reason = "No trade condition met"
        if isinstance(rsi, (int, float)) and isinstance(current_price, (int, float)) and isinstance(sma, (int, float)) and isinstance(atr, (int, float)):
            if rsi < RSI_BUY_THRESHOLD and current_price > sma:
                direction = "call"
                trade_condition_met = True
                condition_reason = f"CALL condition met (RSI={rsi:.2f} < {RSI_BUY_THRESHOLD}, Price={current_price:.5f} > SMA={sma:.5f})"
            elif rsi > RSI_SELL_THRESHOLD and atr < ATR_MAX:
                direction = "put"
                trade_condition_met = True
                condition_reason = f"PUT condition met (RSI={rsi:.2f} > {RSI_SELL_THRESHOLD}, ATR={atr:.5f} < {ATR_MAX})"
            else:
                condition_reason = f"Conditions not met (RSI={rsi:.2f}, Price={current_price:.5f}, SMA={sma:.5f}, ATR={atr:.5f}, BUY_RSI={RSI_BUY_THRESHOLD}, SELL_RSI={RSI_SELL_THRESHOLD}, ATR_MAX={ATR_MAX})"
        else:
            condition_reason = f"Non-numeric values (RSI={rsi}, Price={current_price}, SMA={sma}, ATR={atr})"
            logger.warning(f"Invalid indicator/price values for {asset}: {condition_reason}")

        if not trade_condition_met:
            logger.debug(f"No trade signal for {asset}: {condition_reason}")
            continue

        logger.info(f"Trade signal for {asset}: {direction.upper()}. {condition_reason}")
        if balance is None or not isinstance(balance, (int, float)) or balance <= 0:
            logger.error(f"Cannot calculate trade amount: Invalid balance ({balance}). Skipping {asset}.")
            continue

        amount = (trading_state.current_trade_percentage / 100) * balance
        amount = max(1.0, amount)
        amount = min(amount, 5000.0)
        amount = round(amount, 2)

        if amount < 1.0:
            logger.warning(f"Trade amount ({amount:.2f} USD) below minimum (1.00 USD). Skipping {asset}.")
            continue

        duration = TRADE_DURATION
        time_mode = "TIME"
        logger.info(f"Placing {direction.upper()} order for {asset}: Amount={amount:.2f} USD, Balance={balance:.2f}, Duration={duration}s...")

        try:
            success, response = await client.buy(
                asset=asset,
                amount=amount,
                direction=direction,
                duration=duration,
                time_mode=time_mode
            )
            if success and response and isinstance(response, dict):
                order_id = response.get('id')
                if order_id:
                    logger.info(f"Placed {direction.upper()} order for {asset}. Order ID: {order_id}. Message: {response.get('message', 'No message')}")
                    order_details = {
                        'id': order_id,
                        'asset': asset,
                        'direction': direction,
                        'amount': amount,
                        'openTimestamp': response.get('openTimestamp'),
                        'duration': duration,
                        'percentProfit': response.get('percentProfit', 0),
                        'percentLoss': response.get('percentLoss', 100)
                    }
                    trading_state.add_order(order_details)
                    trading_state.update_trade_time(asset, current_time)
                    trade_executed_in_this_cycle = True
                    logger.debug("Trade execution flag set.")
                    reported_balance = response.get('accountBalance')
                    if reported_balance is not None and isinstance(reported_balance, (int, float)):
                        balance = reported_balance
                        logger.debug(f"Balance updated after order {order_id}: {balance:.2f} USD (API)")
                    else:
                        balance -= amount
                        logger.debug(f"Balance estimated after order {order_id}: {balance:.2f} USD (no API balance)")
                else:
                    logger.warning(f"Order placed for {asset}, but no Order ID in response: {response}.")
                    trading_state.update_trade_time(asset, current_time)
                    trade_executed_in_this_cycle = True
            else:
                logger.error(f"Failed to place {direction.upper()} order for {asset}. Success: {success}. Response: {response}")
        except Exception as e:
            logger.error(f"Exception placing {direction.upper()} trade for {asset}: {e}", exc_info=True)
            trading_state.update_trade_time(asset, current_time)

    if trade_executed_in_this_cycle:
        logger.info("One or more trades executed in this cycle.")
    else:
        logger.info("No trades executed in this cycle.")
    logger.debug("Trade execution loop completed.")
    logger.debug("--- Exiting execute_trades ---")