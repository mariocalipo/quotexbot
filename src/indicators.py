import logging
import asyncio
import time
from quotexapi.stable_api import Quotex
from settings import (
    RSI_INDICATOR, RSI_PERIOD, RSI_MIN, RSI_MAX,
    SMA_INDICATOR, SMA_PERIOD, SMA_MIN, SMA_MAX,
    EMA_INDICATOR, EMA_PERIOD, EMA_MIN, EMA_MAX,
    ATR_INDICATOR, ATR_PERIOD, ATR_MIN, ATR_MAX,
    MACD_INDICATOR, MACD_FAST_PERIOD, MACD_SLOW_PERIOD, MACD_SIGNAL_PERIOD
)
from cachetools import TTLCache

# Initialize logger for this module
logger = logging.getLogger(__name__)

def get_indicator_cache(timeframe: int):
    """Create a TTL cache with expiration proportional to the timeframe."""
    ttl = timeframe * 5  # TTL is 5x the timeframe (e.g., 300s for timeframe=60s)
    return TTLCache(maxsize=100, ttl=ttl)

async def calculate_indicators(client: Quotex, assets: list, timeframe: int = 60) -> dict:
    """Calculate technical indicators for the specified assets and timeframe."""
    if not assets:
        logger.debug("No assets provided for indicator calculation. Returning empty dictionary.")
        return {}

    # Create cache specific to the timeframe
    indicator_cache = get_indicator_cache(timeframe)

    # Generate cache key based on timeframe and sorted assets
    cache_key = f"{timeframe}_{','.join(sorted(assets))}"
    
    # Check if results are in cache
    if cache_key in indicator_cache:
        logger.debug(f"Returning cached indicators for key: {cache_key}")
        return indicator_cache[cache_key]

    # Configure indicators based on settings
    indicators_config = []
    if RSI_INDICATOR:
        try:
            params = {'period': int(RSI_PERIOD)}
            indicators_config.append(('RSI', params, float(RSI_MIN), float(RSI_MAX)))
            logger.debug(f"RSI enabled: period={params['period']}")
        except ValueError as e:
            logger.error(f"Invalid RSI configuration: {e}. Check .env. RSI skipped.")
        except Exception as e:
            logger.error(f"Unexpected error configuring RSI: {e}. RSI skipped.")

    if SMA_INDICATOR:
        try:
            params = {'period': int(SMA_PERIOD)}
            indicators_config.append(('SMA', params, float(SMA_MIN), float(SMA_MAX)))
            logger.debug(f"SMA enabled: period={params['period']}")
        except ValueError as e:
            logger.error(f"Invalid SMA configuration: {e}. Check .env. SMA skipped.")
        except Exception as e:
            logger.error(f"Unexpected error configuring SMA: {e}. SMA skipped.")

    if EMA_INDICATOR:
        try:
            params = {'period': int(EMA_PERIOD)}
            indicators_config.append(('EMA', params, float(EMA_MIN), float(EMA_MAX)))
            logger.debug(f"EMA enabled: period={params['period']}")
        except ValueError as e:
            logger.error(f"Invalid EMA configuration: {e}. Check .env. EMA skipped.")
        except Exception as e:
            logger.error(f"Unexpected error configuring EMA: {e}. EMA skipped.")

    if ATR_INDICATOR:
        try:
            params = {'period': int(ATR_PERIOD)}
            indicators_config.append(('ATR', params, float(ATR_MIN), float(ATR_MAX)))
            logger.debug(f"ATR enabled: period={params['period']}")
        except ValueError as e:
            logger.error(f"Invalid ATR configuration: {e}. Check .env. ATR skipped.")
        except Exception as e:
            logger.error(f"Unexpected error configuring ATR: {e}. ATR skipped.")

    if MACD_INDICATOR:
        try:
            params = {
                'fast_period': int(MACD_FAST_PERIOD),
                'slow_period': int(MACD_SLOW_PERIOD),
                'signal_period': int(MACD_SIGNAL_PERIOD)
            }
            indicators_config.append(('MACD', params, float('-inf'), float('inf')))
            logger.debug(f"MACD enabled: fast_period={params['fast_period']}, slow_period={params['slow_period']}, signal_period={params['signal_period']}")
        except ValueError as e:
            logger.error(f"Invalid MACD configuration: {e}. Check .env. MACD skipped.")
        except Exception as e:
            logger.error(f"Unexpected error configuring MACD: {e}. MACD skipped.")

    if not indicators_config:
        logger.warning("No indicators enabled or configured correctly. Returning empty results.")
        return {asset: {} for asset in assets}

    results = {asset: {} for asset in assets}
    logger.debug(f"Calculating {len(indicators_config)} indicators for {len(assets)} assets with timeframe {timeframe}s...")

    # Determine maximum period for candle history size
    max_period = 0
    for indicator_name, params, _, _ in indicators_config:
        if indicator_name == 'MACD':
            period = max(params.get('slow_period', 0), params.get('signal_period', 0))
        else:
            period = params.get('period', 0)
        max_period = max(max_period, period)
    history_size = max(7200, timeframe * (max_period + 100))  # Increased to ensure sufficient data

    logger.debug(f"Fetching candle history (size: {history_size}s) for indicator calculation.")

    for asset in assets:
        try:
            candles = await client.get_candles(asset, time.time(), history_size, timeframe)
            if not candles or len(candles) < max_period:
                logger.warning(f"Insufficient candle data for {asset} (timeframe {timeframe}s, history {history_size}s, got {len(candles) if candles else 0} candles). Skipping.")
                continue

            prices = [float(candle["close"]) for candle in candles]
            highs = [float(candle["high"]) for candle in candles]
            lows = [float(candle["low"]) for candle in candles]

            logger.debug(f"Calculating indicators for {asset} ({len(candles)} candles)...")

            for indicator_name, params, min_val_filter, max_val_filter in indicators_config:
                try:
                    indicator_result = await client.calculate_indicator(
                        asset=asset,
                        indicator=indicator_name,
                        params=params,
                        history_size=history_size,
                        timeframe=timeframe
                    )

                    if 'error' in indicator_result:
                        logger.warning(f"Error calculating {indicator_name} for {asset}: {indicator_result['error']}. Setting value to None.")
                        results[asset][indicator_name] = None
                    else:
                        if indicator_name == 'MACD':
                            value = {
                                'macd': indicator_result.get('macd')[-1] if indicator_result.get('macd') else None,
                                'signal': indicator_result.get('signal')[-1] if indicator_result.get('signal') else None
                            }
                            if value['macd'] is not None and value['signal'] is not None and isinstance(value['macd'], (int, float)) and isinstance(value['signal'], (int, float)):
                                results[asset][indicator_name] = value
                                logger.debug(f"Calculated {indicator_name} for {asset}: MACD={value['macd']:.5f}, Signal={value['signal']:.5f}")
                            else:
                                logger.debug(f"No valid MACD values for {asset}. Setting to None.")
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
                                    logger.debug(f"Calculated {indicator_name} for {asset}: {value:.5f} (within filter)")
                                else:
                                    logger.debug(f"Calculated {indicator_name} for {asset}: {value:.5f} (outside filter). Setting to None.")
                                    results[asset][indicator_name] = None
                            else:
                                logger.debug(f"No valid numeric value for {indicator_name} on {asset}. Setting to None.")
                                results[asset][indicator_name] = None

                except Exception as e:
                    logger.error(f"Error calculating {indicator_name} for {asset}: {e}", exc_info=True)
                    results[asset][indicator_name] = None

        except Exception as e:
            logger.error(f"Error fetching candles or processing data for {asset}: {e}", exc_info=True)

    # Store results in cache
    indicator_cache[cache_key] = results
    logger.debug(f"Cached indicators for key: {cache_key} with TTL={indicator_cache.ttl} seconds")

    logger.debug("Completed indicator calculation process.")
    return results