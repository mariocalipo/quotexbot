import asyncio
import logging
from quotexapi.stable_api import Quotex
import settings
import logging_config  # configura logging

logger = logging.getLogger(__name__)

class QuotexBot:
    def __init__(self):
        self.client = Quotex(
            email=settings.EMAIL,
            password=settings.PASSWORD,
            lang=settings.LANG
        )
        self.client.debug_ws_enable = settings.DEBUG_WS

    async def connect(self):
        backoff = settings.INITIAL_BACKOFF
        for attempt in range(1, settings.MAX_RETRIES + 1):
            try:
                connected, reason = await self.client.connect()
            except Exception as e:
                logger.error("Erro ao conectar (tentativa %d/%d): %s", attempt, settings.MAX_RETRIES, e)
            else:
                if connected:
                    # Seleciona conta demo ou real
                    account = "PRACTICE" if settings.IS_DEMO else "REAL"
                    try:
                        self.client.change_account(account)
                        logger.info("Conta selecionada: %s", account)
                    except Exception:
                        logger.warning("Não foi possível alterar para conta %s; prosseguindo na conta padrão", account)

                    logger.info("Conectado ao Quotex na tentativa %d", attempt)
                    return
                logger.warning("Falha ao conectar (tentativa %d/%d): %s", attempt, settings.MAX_RETRIES, reason)

            if attempt < settings.MAX_RETRIES:
                await asyncio.sleep(backoff)
                backoff *= 2

        raise RuntimeError(f"Não foi possível conectar após {settings.MAX_RETRIES} tentativas")

    async def execute_trades(self):
        # Lista e filtra ativos OTC
        assets = await self.client.get_available_assets()
        active = [
            a for a in assets
            if a.get("is_otc") and a.get("is_open") and a.get("payout", 0) >= settings.MIN_PAYOUT
        ]

        balance = await self.client.get_balance()
        trade_amount = min(
            int(balance * settings.RISK_PERCENT / 100),
            settings.MAX_TRADE_AMOUNT
        )
        logger.info("Saldo: %s | Valor por trade: %s", balance, trade_amount)

        for asset in active:
            code = asset[0] if isinstance(asset, (list, tuple)) else asset.get("instrument_id")
            logger.info(
                "Enviando ordem → %s | Valor: %s | Duração: %ss", 
                code, trade_amount, settings.DURATION
            )
            try:
                status, info = await self.client.buy(
                    amount=trade_amount,
                    asset_id=code,
                    direction="call",
                    duration=settings.DURATION
                )
            except Exception as e:
                logger.error("Erro ao enviar ordem para %s: %s", code, e)
            else:
                if status:
                    logger.info("Ordem enviada com sucesso: %s", info)
                else:
                    logger.error("Operação rejeitada: %s", info)

            await asyncio.sleep(1)

    async def run(self):
        await self.connect()
        try:
            await self.execute_trades()
        finally:
            await self.client.close()
            logger.info("Conexão encerrada")
