import asyncio
import sys
import logging
from core import QuotexBot
import logging_config  # inicializa o logging

logger = logging.getLogger(__name__)

async def main():
    bot = QuotexBot()
    try:
        await bot.run()
    except Exception as e:
        logger.exception("Erro não tratado: %s", e)
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())
