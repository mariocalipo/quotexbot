import logging
import asyncio
from quotexapi.stable_api import Quotex
from settings import (
    RSI_INDICATOR, RSI_PERIOD, RSI_MIN, RSI_MAX,
    SMA_INDICATOR, SMA_PERIOD, SMA_MIN, SMA_MAX,
    EMA_INDICATOR, EMA_PERIOD, EMA_MIN, EMA_MAX,
    ATR_INDICATOR, ATR_PERIOD, ATR_MIN, ATR_MAX
)

logger = logging.getLogger(__name__)

async def calculate_indicators(client: Quotex, assets: list, timeframe: int = 60) -> dict:
    """Calculate configured technical indicators for the specified assets."""
    valid_indicators = ['RSI', 'SMA', 'EMA', 'ATR']
    indicators_config = []

    # Configure RSI if enabled
    if RSI_INDICATOR:
        try:
            params = {'period': RSI_PERIOD}
            indicators_config.append(('RSI', params, RSI_MIN, RSI_MAX))
        except Exception as e:
            logger.warning(f"Invalid RSI configuration in .env: {e}. Using default period=14.")
            indicators_config.append(('RSI', {'period': 14}, RSI_MIN, RSI_MAX))

    # Configure SMA if enabled
    if SMA_INDICATOR:
        try:
            params = {'period': SMA_PERIOD}
            indicators_config.append(('SMA', params, SMA_MIN, SMA_MAX))
        except Exception as e:
            logger.warning(f"Invalid SMA configuration in .env: {e}. Using default period=20.")
            indicators_config.append(('SMA', {'period': 20}, SMA_MIN, SMA_MAX))

    # Configure EMA if enabled
    if EMA_INDICATOR:
        try:
            params = {'period': EMA_PERIOD}
            indicators_config.append(('EMA', params, EMA_MIN, EMA_MAX))
        except Exception as e:
            logger.warning(f"Invalid EMA configuration in .env: {e}. Using default period=20.")
            indicators_config.append(('EMA', {'period': 20}, EMA_MIN, EMA_MAX))

    # Configure ATR if enabled
    if ATR_INDICATOR:
        try:
            params = {'period': ATR_PERIOD}
            indicators_config.append(('ATR', params, ATR_MIN, ATR_MAX))
        except Exception as e:
            logger.warning(f"Invalid ATR configuration in .env: {e}. Using default period=14.")
            indicators_config.append(('ATR', {'period': 14}, ATR_MIN, ATR_MAX))

    if not indicators_config:
        logger.warning("No indicators enabled in .env. Using default RSI with period=14.")
        indicators_config.append(('RSI', {'period': 14}, float('-inf'), float('inf')))

    results = {asset: {} for asset in assets}
    for asset in assets:
        for indicator, params, min_val, max_val in indicators_config:
            try:
                # Use a reasonable history_size (e.g., 1 hour = 3600 seconds)
                history_size = 3600  # 1 hour of data
                result = await client.calculate_indicator(
                    asset=asset,
                    indicator=indicator,
                    params=params,
                    history_size=history_size,
                    timeframe=timeframe
                )
                if 'error' in result:
                    logger.warning(f"Failed to calculate {indicator} for {asset}: {result['error']}")
                    results[asset][indicator] = None
                else:
                    # Extract the current indicator value
                    value = result.get('current')
                    if value is None:
                        # For indicators like ATR, the value may be a list
                        value_list = result.get('value', [])
                        if isinstance(value_list, list) and value_list:
                            value = value_list[-1]  # Last value in the list
                        else:
                            logger.warning(f"No valid {indicator} value for {asset}: value={value_list}")
                            value = None
                    # Ensure value is a number before comparison
                    if value is not None and isinstance(value, (int, float)) and min_val <= value <= max_val:
                        results[asset][indicator] = value
                    else:
                        logger.debug(f"{indicator} value {value} for {asset} is not a number or outside bounds [{min_val}, {max_val}]")
                        results[asset][indicator] = None
            except Exception as e:
                logger.warning(f"Failed to calculate {indicator} for {asset}: {e}")
                results[asset][indicator] = None

    return results