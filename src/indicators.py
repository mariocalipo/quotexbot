import logging
import asyncio
from quotexapi.stable_api import Quotex
from settings import (
    RSI_INDICATOR, RSI_PERIOD, RSI_MIN, RSI_MAX,
    MACD_INDICATOR, MACD_FAST_PERIOD, MACD_SLOW_PERIOD, MACD_SIGNAL_PERIOD, MACD_MIN, MACD_MAX,
    SMA_INDICATOR, SMA_PERIOD, SMA_MIN, SMA_MAX
)

logger = logging.getLogger(__name__)

async def calculate_indicators(client: Quotex, assets: list, timeframe: int = 60) -> dict:
    """Calculate configured technical indicators for the specified assets."""
    valid_indicators = ['RSI', 'MACD', 'SMA', 'EMA', 'BOLLINGER', 'STOCHASTIC', 'ATR', 'ADX', 'ICHIMOKU']
    complex_indicators = ['MACD', 'BOLLINGER', 'STOCHASTIC', 'ADX', 'ICHIMOKU']
    indicators_config = []

    # Configure RSI if enabled
    if RSI_INDICATOR:
        try:
            params = {'period': RSI_PERIOD}
            indicators_config.append(('RSI', params, RSI_MIN, RSI_MAX))
        except Exception as e:
            logger.warning(f"Invalid RSI configuration in .env: {e}. Using default period=14.")
            indicators_config.append(('RSI', {'period': 14}, RSI_MIN, RSI_MAX))

    # Configure MACD if enabled
    if MACD_INDICATOR:
        try:
            params = {
                'fast_period': MACD_FAST_PERIOD,
                'slow_period': MACD_SLOW_PERIOD,
                'signal_period': MACD_SIGNAL_PERIOD
            }
            indicators_config.append(('MACD', params, MACD_MIN, MACD_MAX))
        except Exception as e:
            logger.warning(f"Invalid MACD configuration in .env: {e}. Using default fast_period=12,slow_period=26,signal_period=9.")
            indicators_config.append(('MACD', {'fast_period': 12, 'slow_period': 26, 'signal_period': 9}, MACD_MIN, MACD_MAX))

    # Configure SMA if enabled
    if SMA_INDICATOR:
        try:
            params = {'period': SMA_PERIOD}
            indicators_config.append(('SMA', params, SMA_MIN, SMA_MAX))
        except Exception as e:
            logger.warning(f"Invalid SMA configuration in .env: {e}. Using default period=20.")
            indicators_config.append(('SMA', {'period': 20}, SMA_MIN, SMA_MAX))

    # Add more indicators here as needed (EMA, BOLLINGER, etc.)

    if not indicators_config:
        logger.warning("No indicators enabled in .env. Using default RSI with period=14.")
        indicators_config.append(('RSI', {'period': 14}, float('-inf'), float('inf')))

    results = {asset: {} for asset in assets}
    for asset in assets:
        for indicator, params, min_val, max_val in indicators_config:
            try:
                result = await client.calculate_indicator(
                    asset=asset,
                    indicator=indicator,
                    params=params,
                    timeframe=timeframe
                )
                if 'error' in result:
                    logger.warning(f"Failed to calculate {indicator} for {asset}: {result['error']}")
                    results[asset][indicator] = None
                else:
                    # Extract the current indicator value
                    value = result.get('current')
                    if indicator in complex_indicators:
                        # For complex indicators, extract from 'value'
                        value_dict = result.get('value', {})
                        logger.debug(f"{indicator} raw result for {asset}: {result}")
                        logger.debug(f"{indicator} value dict for {asset}: {value_dict}")
                        if value is None:
                            # Handle specific indicators
                            if indicator == 'MACD':
                                # MACD returns {'macd': X, 'signal': Y, 'histogram': Z, 'current': W}
                                value = value_dict.get('macd')  # Use 'macd' as the primary value
                            elif indicator == 'BOLLINGER':
                                value = value_dict.get('middle')
                            elif indicator == 'STOCHASTIC':
                                value = value_dict.get('k')
                            elif indicator == 'ADX':
                                value = value_dict.get('adx')
                            elif indicator == 'ICHIMOKU':
                                value = value_dict.get('tenkan')
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