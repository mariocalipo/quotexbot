import logging
from quotexapi.stable_api import Quotex

logger = logging.getLogger(__name__)

async def run(email: str, password: str, is_demo: bool):
    logger.info("Conectando à Quotex...")
    client = Quotex(email, password)
    result = await client.connect()
    if isinstance(result, tuple):
        success, reason = result
    else:
        success, reason = result, None
    if not success:
        logger.error(f"Falha no login: {reason}")
        return
    assets = await client.get_all_assets()
    logger.info(f"Ativos disponíveis ({len(assets)}): {assets}")