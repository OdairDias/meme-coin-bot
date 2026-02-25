"""
Configurações centralizadas do MemeCoin Bot
"""
from pydantic import BaseSettings, Field


class Settings(BaseSettings):
    """Configurações da aplicação"""

    # Wallet Solana
    WALLET_PRIVATE_KEY: str = Field(..., env="WALLET_PRIVATE_KEY")

    # APIs
    BIRDEYE_API_KEY: str | None = Field(default=None, env="BIRDEYE_API_KEY")
    BITQUERY_API_KEY: str | None = Field(default=None, env="BITQUERY_API_KEY")
    # Delay (segundos) após detectar token antes de chamar Birdeye (permite 1-2 candles)
    BIRDEYE_DELAY_SECONDS: int = Field(default=75, env="BIRDEYE_DELAY_SECONDS")
    # Market cap mínimo (SOL) no pré-filtro — 40 permite mais tokens que 50
    MIN_MARKET_CAP_SOL: float = Field(default=40.0, env="MIN_MARKET_CAP_SOL")
    # Re-scan: segundos para re-analisar token que não gerou sinal (90s = decisão no pump inicial)
    RESCAN_DELAY_SECONDS: int = Field(default=90, env="RESCAN_DELAY_SECONDS")
    # Anti-clone: ignorar tokens com mesmo symbol por N segundos (evita spam AGENC x50)
    ANTI_CLONE_SYMBOL_SECONDS: int = Field(default=600, env="ANTI_CLONE_SYMBOL_SECONDS")
    # Mínimo de candles para análise (4 = entrada no pump inicial)
    MIN_CANDLES: int = Field(default=4, env="MIN_CANDLES")
    # Máximo de re-scans por token (1 inicial + N rescans)
    MAX_RESCAN_ATTEMPTS: int = Field(default=4, env="MAX_RESCAN_ATTEMPTS")

    # Telegram
    TELEGRAM_BOT_TOKEN: str | None = Field(default=None, env="TELEGRAM_BOT_TOKEN")
    TELEGRAM_CHAT_ID: str | None = Field(default=None, env="TELEGRAM_CHAT_ID")

    # Risk parameters
    MAX_POSITION_SIZE_USD: float = Field(default=2.0, env="MAX_POSITION_SIZE_USD")
    STOP_LOSS_PERCENT: float = Field(default=20.0, env="STOP_LOSS_PERCENT")
    TAKE_PROFIT_PERCENT1: float = Field(default=100.0, env="TAKE_PROFIT_PERCENT1")
    TAKE_PROFIT_PERCENT2: float = Field(default=300.0, env="TAKE_PROFIT_PERCENT2")
    MAX_HOLDING_MINUTES: int = Field(default=30, env="MAX_HOLDING_MINUTES")
    MAX_CONCURRENT_POSITIONS: int = Field(default=3, env="MAX_CONCURRENT_POSITIONS")
    MAX_DAILY_LOSS_USD: float = Field(default=10.0, env="MAX_DAILY_LOSS_USD")

    # PumpPortal
    PUMP_PORTAL_WS: str = Field(default="wss://pumpportal.fun/api/data", env="PUMP_PORTAL_WS")
    PUMP_PORTAL_API: str = Field(default="https://pumpportal.fun/api/trade-local", env="PUMP_PORTAL_API")
    # RPC Solana (obrigatório para trade-local: assinar e enviar tx)
    SOLANA_RPC_URL: str = Field(default="https://api.mainnet-beta.solana.com", env="SOLANA_RPC_URL")

    # Redis
    REDIS_URL: str = Field(default="redis://localhost:6379", env="REDIS_URL")

    # Logging
    LOG_LEVEL: str = Field(default="INFO", env="LOG_LEVEL")

    # Environment
    ENVIRONMENT: str = Field(default="production", env="ENVIRONMENT")
    DRY_RUN: bool = Field(default=True, env="DRY_RUN")  # Se True, não executa trades reais

    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()