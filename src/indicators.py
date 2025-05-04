import logging
import asyncio
import time
from quotexapi.stable_api import Quotex
from settings import (
    RSI_INDICATOR, RSI_PERIOD, RSI_MIN, RSI_MAX,
    SMA_INDICATOR, SMA_PERIOD, SMA_MIN, SMA_MAX,
    EMA_INDICATOR, EMA_PERIOD, EMA_MIN, EMA_MAX,
    ATR_INDICATOR, ATR_PERIOD, ATR_MIN, ATR_MAX,
    TIMEFRAME_SECONDS
)

logger = logging.getLogger(__name__)

async def calculate_indicators(client: Quotex, assets: list, timeframe: int) -> dict:
    if not assets:
        logger.debug("No assets provided.")
        return {}

    indicators_config = []

    if RSI_INDICATOR:
        try:
            params = {'period': int(RSI_PERIOD)}
            indicators_config.append(('RSI', params, float(RSI_MIN), float(RSI_MAX)))
        except Exception as e:
            logger.error(f"RSI config error: {e}. Skipped.")

    if SMA_INDICATOR:
        try:
            params = {'period': int(SMA_PERIOD)}
            indicators_config.append(('SMA', params, float(SMA_MIN), float(SMA_MAX)))
        except Exception as e:
             logger.error(f"SMA config error: {e}. Skipped.")

    if EMA_INDICATOR:
        try:
            params = {'period': int(EMA_PERIOD)}
            indicators_config.append(('EMA', params, float(EMA_MIN), float(EMA_MAX)))
        except Exception as e:
            logger.error(f"EMA config error: {e}. Skipped.")

    if ATR_INDICATOR:
        try:
            params = {'period': int(ATR_PERIOD)}
            indicators_config.append(('ATR', params, float(ATR_MIN), float(ATR_MAX)))
        except Exception as e:
            logger.error(f"ATR config error: {e}. Skipped.")

    if not indicators_config:
        logger.warning("No indicators enabled or configured. Skipping calculation.")
        return {asset: {} for asset in assets}

    results = {asset: {} for asset in assets}
    logger.debug(f"Calculating {len(indicators_config)} indicators for {len(assets)} assets ({timeframe}s).")

    max_period = 0
    for _, params, _, _ in indicators_config:
        period = params.get('period', 0)
        max_period = max(max_period, period)

    # Request history for double the max period duration, min 1 hour.
    requested_history_seconds = max(max_period * 2 * timeframe, 3600)

    for asset in assets:
        try:
            # Fetch candles with the specified timeframe and history size
            candles = await client.get_candles(asset, time.time(), requested_history_seconds, timeframe)

            if not candles:
                logger.warning(f"No candle data for {asset} ({timeframe}s, {requested_history_seconds}s history). Indicators skipped.")
                continue

            logger.debug(f"Calculating indicators for {asset} ({len(candles)} candles) ({timeframe}s)...")

            for indicator_name, params, min_val_filter, max_val_filter in indicators_config:
                try:
                    # Calculate indicator using the specified timeframe
                    indicator_result = await client.calculate_indicator(
                        asset=asset,
                        indicator=indicator_name,
                        params=params,
                        history_size=requested_history_seconds, # Passing for consistency
                        timeframe=timeframe # Use provided timeframe
                    )

                    if 'error' in indicator_result:
                        logger.warning(f"Calculation error for {indicator_name} on {asset}: {indicator_result['error']}. Value set to None.")
                        results[asset][indicator_name] = None
                    else:
                        value = indicator_result.get('current')
                        if value is None:
                             value_list = indicator_result.get('value')
                             if isinstance(value_list, list) and value_list:
                                 value = value_list[-1]

                        if value is not None and isinstance(value, (int, float)):
                             if min_val_filter <= value <= max_val_filter:
                                 results[asset][indicator_name] = value
                                 logger.debug(f"{indicator_name} for {asset}: {value:.5f} (within filter)")
                             else:
                                 logger.debug(f"{indicator_name} for {asset}: {value:.5f} (outside filter). Filtered.")
                                 results[asset][indicator_name] = None
                        else:
                             logger.debug(f"No valid numeric value for {indicator_name} on {asset}. Value set to None.")

                except Exception as e:
                    logger.error(f"Error calculating {indicator_name} for {asset}: {e}", exc_info=True)
                    results[asset][indicator_name] = None

        except Exception as e:
             logger.error(f"Error fetching candles or processing for {asset}: {e}", exc_info=True)

    logger.debug("Indicator calculation completed.")
    return results