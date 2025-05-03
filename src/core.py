import logging
from quotexapi.stable_api import Quotex

logger = logging.getLogger(__name__)

def connect_and_list_assets(email: str, password: str, demo: bool):
    logger.info("Conectando à Quotex...")
    client = Quotex(email, password, demo=demo)
    try:
        success = client.login()
    except Exception:
        return
    if not success:
        return
    assets = client.get_all_assets()
    logger.info(f"Ativos ({len(assets)}): {assets}")