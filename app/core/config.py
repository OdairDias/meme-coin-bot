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