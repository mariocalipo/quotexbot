import logging
import asyncio
import time
from quotexapi.stable_api import Quotex
from settings import (
    TRADE_ENABLED, TRADE_PERCENTAGE, TRADE_PERCENTAGE_MIN, TRADE_PERCENTAGE_MAX,
    TRADE_DURATION, RSI_BUY_THRESHOLD, RSI_SELL_THRESHOLD, ATR_MAX,
    TRADE_COOLDOWN, DAILY_LOSS_LIMIT, CONSECUTIVE_LOSSES_THRESHOLD,
    CONSECUTIVE_WINS_THRESHOLD, TRADE_MAX_AMOUNT, ORDER_PLACEMENT_DELAY,
    TRADE_PERCENTAGE_STEP
)

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
    global daily_loss, initial_daily_balance, last_reset_time, consecutive_losses, consecutive_wins, current_trade_percentage
    current_balance_at_start_of_function = None
    try:
        current_balance_at_start_of_function = await client.get_balance()
        if current_balance_at_start_of_function is not None and isinstance(current_balance_at_start_of_function, (int, float)):
             logger.debug(f"Balance fetched at start of execute_trades: {current_balance_at_start_of_function:.2f} USD")
        else:
             logger.warning(f"Could not retrieve valid initial balance at start of execute_trades.")
             current_balance_at_start_of_function = 0.0
    except Exception as e:
        logger.error(f"Failed to retrieve initial balance at start of execute_trades: {e}", exc_info=True)
        current_balance_at_start_of_function = 0.0


    logger.debug(f"--- Entering execute_trades ---")
    logger.debug(f"Received assets: {assets}")

    if not TRADE_ENABLED:
        logger.info("Trading disabled (TRADE_ENABLED=false). Skipping execution.")
        logger.debug(f"--- Exiting execute_trades ---")
        return

    if not assets:
        logger.info("No tradable assets for this cycle. Skipping execution.")
        logger.debug(f"--- Exiting execute_trades ---")
        return

    current_time = int(time.time())

    # Daily reset
    if last_reset_time is None or (current_time - last_reset_time) >= 86400:
        logger.info("-" * 30)
        logger.info("Starting new trading day.")
        initial_daily_balance = current_balance_at_start_of_function
        daily_loss = 0.0
        last_reset_time = current_time
        consecutive_losses = 0
        consecutive_wins = 0
        current_trade_percentage = TRADE_PERCENTAGE
        logger.info(f"Initial balance for the day: {initial_daily_balance:.2f} USD. Daily loss reset.")
    else:
         logger.debug(f"Continuing trading day. Daily loss: {daily_loss:.2f}, Wins: {consecutive_wins}, Losses: {consecutive_losses}")

    # Process existing open orders
    orders_to_remove = []
    logger.debug(f"Checking {len(open_orders)} open orders...")
    for order in open_orders:
        order_id = order.get('id')
        asset = order.get('asset')
        amount = order.get('amount')
        percent_profit = order.get('percentProfit', 0)

        try:
            result_data = await client.check_win(order_id)

            if result_data and isinstance(result_data, dict):
                game_state = result_data.get("game_state")

                if game_state == 1:
                    win_status_raw = result_data.get("win")
                    api_profit_amount = result_data.get("profitAmount", 0.0)
                    close_price = result_data.get("closePrice", "N/A")

                    profit_loss_amount = 0.0
                    outcome_status = "Unknown"

                    old_wins = consecutive_wins
                    old_losses = consecutive_losses

                    if win_status_raw is True:
                        profit_loss_amount = amount * (percent_profit / 100.0)
                        outcome_status = "WIN"
                        daily_loss -= profit_loss_amount
                        consecutive_wins += 1
                        consecutive_losses = 0
                        logger.info(f"Order {order_id} ({asset}, {amount:.2f} USD) FINISHED: WIN. Profit: {profit_loss_amount:.2f} USD. Close Price: {close_price}.")
                        logger.debug(f"Outcome: WIN. Old Wins: {old_wins}, New Wins: {consecutive_wins}. Old Losses: {old_losses}, New Losses: {consecutive_losses}. Daily loss: {daily_loss:.2f}")


                    elif win_status_raw is False:
                        profit_loss_amount = -amount
                        outcome_status = "LOSS"
                        daily_loss += amount
                        consecutive_losses += 1
                        consecutive_wins = 0
                        logger.info(f"Order {order_id} ({asset}, {amount:.2f} USD) FINISHED: LOSS. Loss: {amount:.2f} USD. Close Price: {close_price}.")
                        logger.debug(f"Outcome: LOSS. Old Wins: {old_wins}, New Wins: {consecutive_wins}. Old Losses: {old_losses}, New Losses: {consecutive_losses}. Daily loss: {daily_loss:.2f}")

                    elif win_status_raw is None and api_profit_amount == 0.0:
                        outcome_status = "DRAW"
                        logger.info(f"Order {order_id} ({asset}, {amount:.2f} USD) FINISHED: DRAW (assumed). P/L: {api_profit_amount:.2f} USD. Close Price: {close_price}")
                        logger.debug(f"Outcome: DRAW. Wins: {consecutive_wins}, Losses: {consecutive_losses}. Daily loss: {daily_loss:.2f}")


                    else:
                         logger.warning(f"Order {order_id} ({asset}) finished with unexpected win_status: {win_status_raw}. Data: {result_data}.")

                    orders_to_remove.append(order)

                else:
                    logger.debug(f"Order {order_id} for {asset} still OPEN (game_state: {game_state}).")

            elif result_data is None:
                 logger.debug(f"check_win for order ID {order_id} returned None. Data not ready? Keeping.")

            elif result_data is False:
                logger.warning(f"check_win for order ID {order_id} returned False. API error? Keeping temporarily.")

            else:
                 logger.error(f"check_win for order ID {order_id} returned unexpected type: {type(result_data)}. Keeping temporarily.")

        except Exception as e:
            logger.error(f"Error checking win status for order ID {order.get('id')}: {e}", exc_info=True)
            logger.error(f"Removing order ID {order.get('id')} due to processing error.")
            orders_to_remove.append(order)


    for order in list(open_orders):
        if order in orders_to_remove:
            try:
                open_orders.remove(order)
                logger.debug(f"Removed processed order ID {order.get('id')} from list.")
            except ValueError:
                 logger.warning(f"Attempted to remove order ID {order.get('id')} but not found.")


    # Adjust trade percentage based on new streak logic
    old_trade_percentage = current_trade_percentage

    if consecutive_wins > 0 and (consecutive_wins - 1) >= CONSECUTIVE_WINS_THRESHOLD:
        adjustment_steps = consecutive_wins - CONSECUTIVE_WINS_THRESHOLD
        current_trade_percentage += adjustment_steps * TRADE_PERCENTAGE_STEP
        logger.debug(f"Applying win streak adjustment: {adjustment_steps} steps of {TRADE_PERCENTAGE_STEP}%. New percentage before clamp: {current_trade_percentage:.2f}%")

    elif consecutive_losses > 0 and (consecutive_losses - 1) >= CONSECUTIVE_LOSSES_THRESHOLD:
         adjustment_steps = consecutive_losses - CONSECUTIVE_LOSSES_THRESHOLD
         current_trade_percentage -= adjustment_steps * TRADE_PERCENTAGE_STEP
         logger.debug(f"Applying loss streak adjustment: {adjustment_steps} steps of {TRADE_PERCENTAGE_STEP}%. New percentage before clamp: {current_trade_percentage:.2f}%")

    current_trade_percentage = max(TRADE_PERCENTAGE_MIN, current_trade_percentage)
    current_trade_percentage = min(TRADE_PERCENTAGE_MAX, current_trade_percentage)

    if abs(current_trade_percentage - old_trade_percentage) > 0.01:
         logger.info(f"Trade percentage adjusted: {old_trade_percentage:.2f}% to {current_trade_percentage:.2f}% (Wins: {consecutive_wins}, Losses: {consecutive_losses}).")
    else:
         logger.debug(f"Trade percentage remains {current_trade_percentage:.2f}% (Wins: {consecutive_wins}, Losses: {consecutive_losses}).")


    # Check daily loss limit
    if initial_daily_balance is not None and initial_daily_balance > 0:
        loss_percentage = (daily_loss / initial_daily_balance) * 100
        logger.debug(f"Daily loss: {daily_loss:.2f} USD ({loss_percentage:.2f}%). Limit: {DAILY_LOSS_LIMIT:.2f}%.")
        if loss_percentage >= DAILY_LOSS_LIMIT:
            logger.warning(f"Daily loss limit {DAILY_LOSS_LIMIT:.2f}% reached ({loss_percentage:.2f}%). Trading disabled until next day.")
            logger.debug(f"--- Exiting execute_trades due to daily loss limit ---")
            return
    elif DAILY_LOSS_LIMIT > 0:
         logger.warning("Daily loss limit active but initial_daily_balance zero. Limit check skipped.")


    # Execute new trades
    logger.debug("Checking for new trade opportunities...")
    trade_executed_in_this_cycle = False

    # --- Get the most recent balance before STARTING the new trade loop ---
    # Use this as a starting point, but update it with API response balance after trades
    current_balance = None
    try:
        current_balance = await client.get_balance()
        if current_balance is None or not isinstance(current_balance, (int, float)) or current_balance <= 0:
             logger.warning(f"Could not get valid initial balance ({current_balance}) for new trades. Skipping execution.")
             logger.debug(f"--- Exiting execute_trades due to insufficient initial balance ---")
             return
        logger.debug(f"Balance fetched at start of new trade checks: {current_balance:.2f} USD")
    except Exception as e:
         logger.error(f"Error getting balance at start of new trade checks: {e}", exc_info=True)
         logger.debug(f"--- Exiting execute_trades due to balance fetch error ---")
         return
    # --- End get balance at loop start ---


    logger.debug(f"Iterating through {len(assets)} assets to find a signal...")
    for asset in assets:
        logger.debug(f"Processing asset: {asset}")

        if any(order.get('asset') == asset for order in open_orders):
             logger.debug(f"Skipping {asset}: Already has an open order.")
             continue

        current_time = int(time.time())
        last_trade = last_trade_time.get(asset, 0)
        if current_time - last_trade < TRADE_COOLDOWN:
            logger.debug(f"Skipping {asset}: In cooldown (last trade {last_trade}, cooldown {TRADE_COOLDOWN}s).")
            continue

        asset_indicators = indicators.get(asset, {})
        rsi = asset_indicators.get("RSI")
        sma = asset_indicators.get("SMA")
        atr = asset_indicators.get("ATR")

        logger.debug(f"Indicators for {asset}: RSI={rsi}, SMA={sma}, ATR={atr}")

        if not all(isinstance(val, (int, float)) for val in [rsi, sma, atr]) or any(val is None for val in [rsi, sma, atr]):
             logger.debug(f"Skipping {asset}: Missing or non-numeric indicators (RSI:{rsi}, SMA:{sma}, ATR:{atr}).")
             continue

        try:
            price_data = await client.get_realtime_price(asset)
            current_price = None
            if isinstance(price_data, list) and len(price_data) > 0:
                 try:
                     latest_entry = max(price_data, key=lambda x: x.get('time', 0))
                     current_price = latest_entry.get('price')
                 except Exception as e:
                     logger.warning(f"Could not process price list for {asset}: {e}. Data: {price_data}")
            elif isinstance(price_data, dict) and price_data:
                 current_price = price_data.get('price')

            if current_price is None or not isinstance(current_price, (int, float)):
                logger.debug(f"Skipping {asset}: Cannot fetch or process current price. Data: {price_data}")
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
                 condition_reason = f"CALL met (RSI={rsi:.2f} < {RSI_BUY_THRESHOLD} and Price={current_price:.5f} > SMA={sma:.5f})"
             elif rsi > RSI_SELL_THRESHOLD and atr < ATR_MAX:
                 direction = "put"
                 trade_condition_met = True
                 condition_reason = f"PUT met (RSI={rsi:.2f} > {RSI_SELL_THRESHOLD} and ATR={atr:.5f} < {ATR_MAX})"
             else:
                  condition_reason = f"Criteria not met (RSI={rsi:.2f}, Price={current_price:.5f}, SMA={sma:.5f}, ATR={atr:.5f})"
        else:
             condition_reason = f"Indicator/price not numeric (RSI:{rsi}, Price:{current_price}, SMA:{sma}, ATR:{atr})"
             logger.warning(f"Non-numeric indicator/price for {asset}: {condition_reason}")


        if not trade_condition_met:
            logger.debug(f"No trade signal for {asset}. {condition_reason}")
            continue

        logger.info(f"Trade signal found for {asset}: {direction.upper()}. {condition_reason}")

        # --- Calculate amount using the CURRENT value of the 'current_balance' variable ---
        # This variable is updated with the API response balance after successful trades.
        amount = (current_trade_percentage / 100) * current_balance
        amount = max(1.0, amount)
        amount = min(amount, TRADE_MAX_AMOUNT)
        amount = round(amount, 2)

        if amount < 1.0:
             logger.warning(f"Calculated amount ({amount:.2f} USD) < min (1.00 USD) for {asset}. Skipping trade.")
             continue

        duration = TRADE_DURATION
        time_mode = "TIME"

        logger.info(f"Placing {direction.upper()} order for {asset}: Amount={amount:.2f} USD, Duration={duration}s...")

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
                     logger.info(f"Order placed for {asset}. ID: {order_id}.")
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
                     open_orders.append(order_details)
                     logger.debug(f"Added order {order_id} to open_orders. Count: {len(open_orders)}")

                     last_trade_time[asset] = current_time

                     trade_executed_in_this_cycle = True
                     logger.debug(f"Trade execution flag set.")

                     # --- Update the internal 'current_balance' variable with API reported balance ---
                     # This updated value will be used for subsequent trade calculations in THIS cycle.
                     reported_balance = response.get('accountBalance')
                     if reported_balance is not None and isinstance(reported_balance, (int, float)):
                        current_balance = reported_balance # Update the variable used for calculation
                        logger.debug(f"Internal balance updated from API response for next trade calculation: {current_balance:.2f} USD")
                     else:
                        # If API balance is not available in response, estimate
                        current_balance -= amount
                        logger.debug(f"Internal balance estimated after trade for next trade calculation: {current_balance:.2f} USD")
                     # --- End balance update ---

                else:
                     logger.warning(f"Order placed for {asset}, but no Order ID in response: {response}. Cannot reliably track outcome.")
                     last_trade_time[asset] = current_time
                     trade_executed_in_this_cycle = True

            else:
                logger.error(f"Failed to place {direction.upper()} order for {asset}. Success status: {success}. Response: {response}")
                # Optional: Apply cooldown on failure if appropriate
                # last_trade_time[asset] = current_time

        except Exception as e:
            logger.error(f"Exception while trying to place {direction.upper()} trade for {asset}: {e}", exc_info=True)
            last_trade_time[asset] = current_time

        # Add a delay after attempting to place an order before checking the next asset
        await asyncio.sleep(ORDER_PLACEMENT_DELAY)
        logger.debug(f"Waited {ORDER_PLACEMENT_DELAY}s after attempting trade for {asset}.")

        # If you want to trade only ONE asset per cycle, uncomment the next line:
        # if trade_executed_in_this_cycle:
        #    logger.debug("Trade placed in this cycle. Stopping check for other assets.")
        #    break

    # Modified Final Log
    if trade_executed_in_this_cycle:
         logger.info(f"One or more new trades were executed in this cycle.")
    else:
         logger.info(f"No new trades were executed in this cycle for any asset that passed initial filters.")
    logger.debug(f"Trade execution loop finished.")
    logger.debug(f"--- Exiting execute_trades ---")