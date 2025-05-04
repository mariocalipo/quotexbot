import os
from dotenv import load_dotenv

# Carrega variáveis de ambiente
load_dotenv()

# Conexão com a conta Quotex
EMAIL = os.getenv("EMAIL")
PASSWORD = os.getenv("PASSWORD")
if not EMAIL or not PASSWORD:
    raise ValueError("As variáveis de ambiente EMAIL e PASSWORD devem estar definidas")

# Ambiente: demo ou real
IS_DEMO = os.getenv("IS_DEMO", "true").lower() in ("true", "1", "yes")

# Retry de conexão
MAX_RETRIES = int(os.getenv("MAX_RETRIES", 5))
INITIAL_BACKOFF = float(os.getenv("INITIAL_BACKOFF", 1.0))

# Logging
LOG_LEVEL       = os.getenv("LOG_LEVEL", "INFO").upper()
LOG_DIR         = os.getenv("LOG_DIR", "logs")
LOG_FILE        = os.getenv("LOG_FILE", os.path.join(LOG_DIR, "quotexbot.log"))
LOG_MAX_BYTES   = int(os.getenv("LOG_MAX_BYTES", 10 * 1024 * 1024))
LOG_BACKUP_COUNT= int(os.getenv("LOG_BACKUP_COUNT", 5))

# Filtro de payout
MIN_PAYOUT = float(os.getenv("MIN_PAYOUT", 80.0))  # em porcentagem

# Gestão de risco
RISK_PERCENT     = float(os.getenv("RISK_PERCENT", 1.0))  # % do saldo por trade
MAX_TRADE_AMOUNT = int(os.getenv("MAX_TRADE_AMOUNT", 100)) # valor máximo por trade

# Parâmetros de trade
DURATION = int(os.getenv("DURATION", 60))  # segundos

# WebSocket
LANG      = os.getenv("LANG", "pt")
DEBUG_WS  = os.getenv("DEBUG_WS", "false").lower() in ("true", "1", "yes")
