import logging
import asyncio
import time
from quotexapi.stable_api import Quotex
from settings import (
    TRADE_ENABLED, TRADE_PERCENTAGE, TRADE_PERCENTAGE_MIN, TRADE_PERCENTAGE_MAX,
    TRADE_DURATION, RSI_BUY_THRESHOLD, RSI_SELL_THRESHOLD, ATR_MAX, TRADE_COOLDOWN,
    DAILY_LOSS_LIMIT, CONSECUTIVE_LOSSES_THRESHOLD, CONSECUTIVE_WINS_THRESHOLD
)

logger = logging.getLogger(__name__)

class TradingState:
    """Classe para gerenciar o estado do trading de forma segura."""
    def __init__(self):
        self.open_orders = []
        self.last_trade_time = {}
        self.daily_loss = 0.0
        self.initial_daily_balance = 0.0
        self.last_reset_time = None
        self.consecutive_losses = 0
        self.consecutive_wins = 0
        self.current_trade_percentage = TRADE_PERCENTAGE

    def reset_daily(self, balance: float, current_time: int):
        """Reinicia o estado para um novo dia de trading."""
        self.daily_loss = 0.0
        self.initial_daily_balance = balance
        self.last_reset_time = current_time
        self.consecutive_losses = 0
        self.consecutive_wins = 0
        self.current_trade_percentage = TRADE_PERCENTAGE
        logger.info(f"Initial balance for the day: {self.initial_daily_balance:.2f} USD. Daily loss reset.")

    def add_order(self, order_details: dict):
        """Adiciona uma ordem à lista de ordens abertas."""
        self.open_orders.append(order_details)
        logger.debug(f"Added order {order_details.get('id')} to open_orders list. Current count: {len(self.open_orders)}")

    def remove_order(self, order: dict):
        """Remove uma ordem da lista de ordens abertas."""
        try:
            self.open_orders.remove(order)
            logger.debug(f"Removed processed order ID {order.get('id')} from open_orders list.")
        except ValueError:
            logger.warning(f"Attempted to remove order ID {order.get('id')} but it was not found in open_orders list.")

    def update_trade_time(self, asset: str, current_time: int):
        """Atualiza o tempo do último trade para um ativo."""
        self.last_trade_time[asset] = current_time

    def update_loss(self, amount: float):
        """Aumenta a perda diária."""
        self.daily_loss += amount
        self.consecutive_losses += 1
        self.consecutive_wins = 0
        logger.debug(f"LOSS recorded. Consecutive wins: {self.consecutive_wins}, losses: {self.consecutive_losses}. Daily loss: {self.daily_loss:.2f}")

    def update_win(self, profit: float):
        """Reduz a perda diária com um lucro."""
        self.daily_loss -= profit
        self.consecutive_wins += 1
        self.consecutive_losses = 0
        logger.debug(f"WIN recorded. Consecutive wins: {self.consecutive_wins}, losses: {self.consecutive_losses}. Daily loss: {self.daily_loss:.2f}")

    def adjust_trade_percentage(self):
        """Ajusta o percentual de trading com base em vitórias/derrotas consecutivas."""
        old_percentage = self.current_trade_percentage
        if self.consecutive_losses >= CONSECUTIVE_LOSSES_THRESHOLD and self.current_trade_percentage > TRADE_PERCENTAGE_MIN:
            self.current_trade_percentage = max(TRADE_PERCENTAGE_MIN, self.current_trade_percentage * 0.8)
            logger.debug(f"Reducing trade percentage due to {self.consecutive_losses} consecutive losses. New percentage: {self.current_trade_percentage:.2f}%")
        elif self.consecutive_wins >= CONSECUTIVE_WINS_THRESHOLD and self.current_trade_percentage < TRADE_PERCENTAGE_MAX:
            self.current_trade_percentage = min(TRADE_PERCENTAGE_MAX, self.current_trade_percentage * 1.2)
            logger.debug(f"Increasing trade percentage due to {self.consecutive_wins} consecutive wins. New percentage: {self.current_trade_percentage:.2f}%")
        else:
            self.current_trade_percentage = TRADE_PERCENTAGE
            self.current_trade_percentage = max(TRADE_PERCENTAGE_MIN, min(TRADE_PERCENTAGE_MAX, self.current_trade_percentage))

        if self.current_trade_percentage != old_percentage:
            logger.info(f"Trade percentage adjusted from {old_percentage:.2f}% to {self.current_trade_percentage:.2f}% (Wins: {self.consecutive_wins}, Losses: {self.consecutive_losses}).")

    def check_daily_loss_limit(self, balance: float) -> bool:
        """Verifica se o limite de perda diária foi atingido."""
        if self.initial_daily_balance > 0:
            loss_percentage = (self.daily_loss / self.initial_daily_balance) * 100
            logger.debug(f"Current daily loss: {self.daily_loss:.2f} USD ({loss_percentage:.2f}% of initial {self.initial_daily_balance:.2f} USD). Limit: {DAILY_LOSS_LIMIT:.2f}%.")
            if loss_percentage >= DAILY_LOSS_LIMIT:
                logger.warning(f"Daily loss limit of {DAILY_LOSS_LIMIT:.2f}% reached (current loss: {loss_percentage:.2f}%). Trading disabled until next day.")
                return False
        elif DAILY_LOSS_LIMIT > 0:
            logger.warning("Daily loss limit is active but initial_daily_balance is not set or is zero. Loss limit check skipped.")
        return True

# Instância única do estado do trading
trading_state = TradingState()

async def execute_trades(client: Quotex, assets: list, indicators: dict):
    logger.debug(f"--- Entering execute_trades function ---")
    logger.debug(f"Received assets list: {assets}")
    logger.debug(f"Received indicators dictionary keys: {indicators.keys()}")

    if not TRADE_ENABLED:
        logger.info("Trading is disabled (TRADE_ENABLED=false). Skipping trade execution.")
        logger.debug(f"--- Exiting execute_trades ---")
        return

    if not assets:
        logger.info("No tradable assets provided for this cycle. Skipping trade execution.")
        logger.debug(f"--- Exiting execute_trades ---")
        return

    current_time = int(time.time())

    # Obter saldo atual
    current_balance = None
    try:
        current_balance = await client.get_balance()
        if current_balance is not None and isinstance(current_balance, (int, float)):
            logger.debug(f"Current balance at the start of execute_trades: {current_balance:.2f} USD")
        else:
            logger.warning(f"Could not retrieve valid initial balance. Received: {current_balance}")
            current_balance = 0.0
    except Exception as e:
        logger.error(f"Failed to retrieve initial balance: {e}", exc_info=True)
        current_balance = 0.0

    # Reset diário
    if trading_state.last_reset_time is None or (current_time - trading_state.last_reset_time) >= 86400:
        logger.info("-" * 30)
        logger.info("Starting a new trading day.")
        trading_state.reset_daily(current_balance, current_time)
    else:
        logger.debug(f"Continuing trading day. Daily loss: {trading_state.daily_loss:.2f}, Initial daily balance: {trading_state.initial_daily_balance:.2f}, Consecutive wins: {trading_state.consecutive_wins}, losses: {trading_state.consecutive_losses}")

    # Processar ordens abertas
    orders_to_remove = []
    logger.debug(f"Checking {len(trading_state.open_orders)} existing open orders...")
    for order in trading_state.open_orders:
        order_id = order.get('id')
        asset = order.get('asset')
        direction = order.get('direction')
        amount = order.get('amount')
        openTimestamp = order.get('openTimestamp')
        percent_profit = order.get('percentProfit', 0)

        logger.debug(f"Checking status for order ID: {order_id} on {asset} (Opened at {openTimestamp}, Amount: {amount:.2f})")

        try:
            result_data = await client.check_win(order_id)
            if result_data and isinstance(result_data, dict):
                game_state = result_data.get("game_state")
                if game_state == 1:
                    win_status_raw = result_data.get("win")
                    api_profit_amount = result_data.get("profitAmount", 0.0)
                    close_price = result_data.get("closePrice", "N/A")
                    logger.debug(f"Order {order_id} raw data: {result_data}")

                    profit_loss_amount = 0.0
                    outcome_status = "Unknown"
                    if win_status_raw is True:
                        profit_loss_amount = amount * (percent_profit / 100.0)
                        outcome_status = "WIN"
                        trading_state.update_win(profit_loss_amount)
                        logger.info(f"Order {order_id} ({asset} {direction}, {amount:.2f} USD) FINISHED. Status: WIN. Profit: {profit_loss_amount:.2f} USD. Close Price: {close_price}. API P/L: {api_profit_amount:.2f}")
                    elif win_status_raw is False:
                        profit_loss_amount = -amount
                        outcome_status = "LOSS"
                        trading_state.update_loss(amount)
                        logger.info(f"Order {order_id} ({asset} {direction}, {amount:.2f} USD) FINISHED. Status: LOSS. Loss: {amount:.2f} USD. Close Price: {close_price}. API P/L: {api_profit_amount:.2f}")
                    elif win_status_raw is None and api_profit_amount == 0.0:
                        outcome_status = "DRAW"
                        logger.info(f"Order {order_id} ({asset} {direction}, {amount:.2f} USD) FINISHED. Status: DRAW (assumed). P/L: {api_profit_amount:.2f} USD. Close Price: {close_price}")
                    else:
                        logger.warning(f"Order {order_id} ({asset}) finished with UNEXPECTED raw win_status: {win_status_raw}. Data: {result_data}. Cannot reliably determine outcome.")
                    orders_to_remove.append(order)
                else:
                    logger.debug(f"Order {order_id} for {asset} is still OPEN (game_state: {game_state}). Keeping in list.")
            elif result_data is None:
                logger.debug(f"check_win for order ID {order_id} returned None. Order may still be processing or data unavailable. Keeping in list.")
            elif result_data is False:
                logger.warning(f"check_win for order ID {order_id} returned False. Order data might not be available or an API error occurred. Keeping in list temporarily.")
            else:
                logger.error(f"check_win for order ID {order_id} returned unexpected data type: {type(result_data)}. Data: {result_data}. Keeping in list temporarily.")
        except Exception as e:
            logger.error(f"Error during check_win processing for order ID {order.get('id')}: {e}", exc_info=True)
            logger.error(f"Removing order ID {order.get('id')} from open_orders due to processing error.")
            orders_to_remove.append(order)

    for order in orders_to_remove:
        trading_state.remove_order(order)

    # Ajustar percentual de trading
    trading_state.adjust_trade_percentage()

    # Verificar limite de perda diária
    if not trading_state.check_daily_loss_limit(current_balance):
        logger.debug(f"--- Exiting execute_trades due to daily loss limit ---")
        return

    # Executar novas ordens
    logger.debug("Checking for new trade opportunities...")
    trade_executed_in_this_cycle = False
    balance = current_balance

    if balance is None or not isinstance(balance, (int, float)) or balance <= 0:
        logger.warning("Account balance is zero, negative, or could not be retrieved. Cannot place new trades.")
        logger.debug(f"--- Exiting execute_trades ---")
        return

    logger.debug(f"Iterating through {len(assets)} tradable assets to find a signal...")
    for asset in assets:
        logger.debug(f"Processing asset: {asset}")
        if any(order.get('asset') == asset for order in trading_state.open_orders):
            logger.debug(f"Skipping trade for {asset}: Already has an open order.")
            continue

        current_time = int(time.time())
        last_trade = trading_state.last_trade_time.get(asset, 0)
        if current_time - last_trade < TRADE_COOLDOWN:
            logger.debug(f"Skipping trade for {asset}: still in cooldown (last trade at {last_trade}, cooldown={TRADE_COOLDOWN}s, current time={current_time}).")
            continue

        asset_indicators = indicators.get(asset, {})
        rsi = asset_indicators.get("RSI")
        sma = asset_indicators.get("SMA")
        atr = asset_indicators.get("ATR")

        logger.debug(f"Indicators for {asset}: RSI={rsi}, SMA={sma}, ATR={atr}")
        if not all(isinstance(val, (int, float)) for val in [rsi, sma, atr]) or any(val is None for val in [rsi, sma, atr]):
            logger.debug(f"Skipping trade for {asset}: Missing or non-numeric indicators (RSI:{rsi}, SMA:{sma}, ATR:{atr}).")
            continue

        try:
            price_data = await client.get_realtime_price(asset)
            current_price = None
            if isinstance(price_data, list) and len(price_data) > 0:
                try:
                    latest_entry = max(price_data, key=lambda x: x.get('time', 0))
                    current_price = latest_entry.get('price')
                except Exception as e:
                    logger.warning(f"Could not process real-time price list for {asset} in trade.py (signal check): {e}. Data: {price_data}", exc_info=False)
            elif isinstance(price_data, dict) and price_data:
                current_price = price_data.get('price')
            if current_price is None or not isinstance(current_price, (int, float)):
                logger.debug(f"Skipping trade for {asset} (signal check): Unable to fetch or process current real-time price. Price data was: {price_data}")
                continue
            logger.debug(f"Current price for {asset} (signal check): {current_price}")
        except Exception as e:
            logger.error(f"Error fetching real-time price for {asset} in trade.py (signal check): {e}", exc_info=True)
            continue

        direction = None
        trade_condition_met = False
        condition_reason = "No trade condition met"
        if isinstance(rsi, (int, float)) and isinstance(current_price, (int, float)) and isinstance(sma, (int, float)) and isinstance(atr, (int, float)):
            if rsi < RSI_BUY_THRESHOLD and current_price > sma:
                direction = "call"
                trade_condition_met = True
                condition_reason = f"CALL condition met (RSI={rsi:.2f} < {RSI_BUY_THRESHOLD} and Price={current_price:.5f} > SMA={sma:.5f})"
            elif rsi > RSI_SELL_THRESHOLD and atr < ATR_MAX:
                direction = "put"
                trade_condition_met = True
                condition_reason = f"PUT condition met (RSI={rsi:.2f} > {RSI_SELL_THRESHOLD} and ATR={atr:.5f} < {ATR_MAX})"
            else:
                condition_reason = f"Criteria not met (RSI={rsi:.2f}, Price={current_price:.5f}, SMA={sma:.5f}, ATR={atr:.5f}, BUY_RSI={RSI_BUY_THRESHOLD}, SELL_RSI={RSI_SELL_THRESHOLD}, ATR_MAX={ATR_MAX})"
        else:
            condition_reason = f"Indicator or price values are not numeric (RSI:{rsi}, Price:{current_price}, SMA:{sma}, ATR:{atr})"
            logger.warning(f"Non-numeric indicator/price values for {asset} during condition check: {condition_reason}")

        if not trade_condition_met:
            logger.debug(f"No trade signal for {asset}. {condition_reason}")
            continue

        logger.info(f"Trade signal found for {asset}: {direction.upper()}. {condition_reason}")
        if balance is None or not isinstance(balance, (int, float)) or balance <= 0:
            logger.error(f"Cannot calculate trade amount: Invalid or zero current balance ({balance}). Skipping trade for {asset}.")
            continue

        amount = (trading_state.current_trade_percentage / 100) * balance
        amount = max(1.0, amount)
        amount = min(amount, 5000.0)
        amount = round(amount, 2)

        if amount < 1.0:
            logger.warning(f"Calculated trade amount ({amount:.2f} USD) is less than minimum trade amount (1.00 USD). Skipping trade for {asset}.")
            continue

        duration = TRADE_DURATION
        time_mode = "TIME"
        logger.info(f"Attempting to place {direction.upper()} order for {asset}: Amount={amount:.2f} USD (calculated based on balance {balance:.2f}), Duration={duration}s...")

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
                    logger.info(f"Successfully placed {direction.upper()} order for {asset}. Order ID: {order_id}. Response message: {response.get('message', 'No message')}")
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
                    logger.debug(f"Trade execution flag set for this cycle.")
                    reported_balance = response.get('accountBalance')
                    if reported_balance is not None and isinstance(reported_balance, (int, float)):
                        balance = reported_balance
                        logger.debug(f"Balance updated after placing order {order_id}: New balance = {balance:.2f} USD (from API response)")
                    else:
                        balance -= amount
                        logger.debug(f"Balance updated by estimating after placing order {order_id}: Estimated new balance = {balance:.2f} USD (API balance not in response)")
                else:
                    logger.warning(f"Order placed for {asset}, but no Order ID in response: {response}. Cannot reliably track outcome.")
                    trading_state.update_trade_time(asset, current_time)
                    trade_executed_in_this_cycle = True
            else:
                logger.error(f"Failed to place {direction.upper()} order for {asset}. Success status: {success}. Response: {response}")
        except Exception as e:
            logger.error(f"Exception while trying to place {direction.upper()} trade for {asset}: {e}", exc_info=True)
            trading_state.update_trade_time(asset, current_time)

    if trade_executed_in_this_cycle:
        logger.info(f"One or more new trades were executed in this cycle.")
    else:
        logger.info(f"No new trades were executed in this cycle for any asset that passed initial filters.")
    logger.debug(f"Trade execution loop finished.")
    logger.debug(f"--- Exiting execute_trades ---")