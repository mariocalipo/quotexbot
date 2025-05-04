import logging
import asyncio
from settings import MAX_RETRIES, INITIAL_BACKOFF
from quotexapi.stable_api import Quotex

logger = logging.getLogger(__name__)

async def run(email: str, password: str, is_demo: bool):
    logger.info("Conectando à Quotex (demo=%s)...", is_demo)
    client = Quotex(email, password, is_demo)
    backoff = INITIAL_BACKOFF

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            result = await client.connect()
            if isinstance(result, tuple):
                success, reason = result
            else:
                success, reason = result, None

            if not success:
                logger.error("Falha no login (tentativa %d/%d): %s", attempt, MAX_RETRIES, reason)
                if attempt == MAX_RETRIES:
                    return
            else:
                break

        except Exception as e:
            logger.exception("Erro ao conectar (tentativa %d/%d): %s", attempt, MAX_RETRIES, e)
            if attempt == MAX_RETRIES:
                return

        await asyncio.sleep(backoff)
        backoff *= 2

    assets = await client.get_all_assets()
    logger.info("Ativos disponíveis (%d): %s", len(assets), assets)