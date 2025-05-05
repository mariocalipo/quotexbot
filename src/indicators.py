import logging
import asyncio
import time
from quotexapi.stable_api import Quotex
from settings import (
    RSI_INDICATOR, RSI_PERIOD, RSI_MIN, RSI_MAX,
    SMA_INDICATOR, SMA_PERIOD, SMA_MIN, SMA_MAX,
    EMA_INDICATOR, EMA_PERIOD, EMA_MIN, EMA_MAX,
    ATR_INDICATOR, ATR_PERIOD, ATR_MIN, ATR_MAX
)
from cachetools import TTLCache

logger = logging.getLogger(__name__)

# Cache com TTL proporcional ao timeframe (5x timeframe) e tamanho máximo de 100 entradas
def get_indicator_cache(timeframe: int):
    ttl = timeframe * 5  # TTL = 5x o timeframe (ex.: 300s para timeframe=60s)
    return TTLCache(maxsize=100, ttl=ttl)

async def calculate_indicators(client: Quotex, assets: list, timeframe: int = 60) -> dict:
    if not assets:
        logger.debug("No assets provided to calculate_indicators. Returning empty dict.")
        return {}

    # Criar cache específico para o timeframe
    indicator_cache = get_indicator_cache(timeframe)

    # Criar chave de cache baseada nos ativos e timeframe
    cache_key = f"{timeframe}_{','.join(sorted(assets))}"
    
    # Verificar se o resultado está no cache
    if cache_key in indicator_cache:
        logger.debug(f"Returning cached indicators for key: {cache_key}")
        return indicator_cache[cache_key]

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

    if not indicators_config:
        logger.warning("No indicators enabled or configured correctly. No indicators calculated.")
        return {asset: {} for asset in assets}

    results = {asset: {} for asset in assets}
    logger.debug(f"Calculating {len(indicators_config)} indicators for {len(assets)} assets with timeframe {timeframe}s...")

    max_period = 0
    for _, params, _, _ in indicators_config:
        period = params.get('period', 0)
        max_period = max(max_period, period)
    history_size = max(3600, timeframe * (max_period + 50))

    logger.debug(f"Fetching candle history (size: {history_size}s) for indicator calculation.")

    for asset in assets:
        try:
            candles = await client.get_candles(asset, time.time(), history_size, timeframe)
            if not candles:
                logger.warning(f"No candle data available for {asset} (timeframe {timeframe}s, history {history_size}s). Cannot calculate indicators.")
                continue

            prices = [float(candle["close"]) for candle in candles]
            highs = [float(candle["high"]) for candle in candles]
            lows = [float(candle["low"]) for candle in candles]

            logger.debug(f"Calculating indicators for asset {asset} ({len(candles)} candles)...")

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
                                logger.debug(f"Calculated {indicator_name} for {asset}: {value:.5f} (within filter)")
                            else:
                                logger.debug(f"Calculated {indicator_name} for {asset}: {value:.5f} (outside filter). Filtered out.")
                                results[asset][indicator_name] = None
                        else:
                            logger.debug(f"No valid numeric value for {indicator_name} on {asset}. Value set to None.")
                            results[asset][indicator_name] = None

                except Exception as e:
                    logger.error(f"Error calculating {indicator_name} for {asset}: {e}", exc_info=True)
                    results[asset][indicator_name] = None

        except Exception as e:
            logger.error(f"Error fetching candles or processing data for {asset}: {e}", exc_info=True)

    # Armazenar resultado no cache
    indicator_cache[cache_key] = results
    logger.debug(f"Cached indicators for key: {cache_key} with TTL={indicator_cache.ttl} seconds")

    logger.debug("Indicator calculation process completed.")
    return results