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
    # Delay (s) após detectar token antes de consultar OHLCV — Bitquery leva 3-8 min para indexar
    BIRDEYE_DELAY_SECONDS: int = Field(default=300, env="BIRDEYE_DELAY_SECONDS")
    # Market cap mínimo (SOL) — tokens >55 SOL indexados mais rápido pela Bitquery
    MIN_MARKET_CAP_SOL: float = Field(default=60.0, env="MIN_MARKET_CAP_SOL")
    # Re-scan: segundos entre tentativas — 120s economiza API e permite mais candles
    RESCAN_DELAY_SECONDS: int = Field(default=120, env="RESCAN_DELAY_SECONDS")
    # Anti-clone: ignorar tokens com mesmo symbol por N segundos (evita spam AGENC x50)
    ANTI_CLONE_SYMBOL_SECONDS: int = Field(default=600, env="ANTI_CLONE_SYMBOL_SECONDS")
    # Mínimo de candles para análise (3 = explosão inicial, 4 = mais confirmação)
    MIN_CANDLES: int = Field(default=3, env="MIN_CANDLES")
    # Máximo de re-scans por token (1 inicial + N rescans)
    MAX_RESCAN_ATTEMPTS: int = Field(default=4, env="MAX_RESCAN_ATTEMPTS")
    # Padrão: picos/valles mínimos (1 = mais permissivo, 2 = conservador)
    MIN_PATTERN_STEPS: int = Field(default=1, env="MIN_PATTERN_STEPS")
    # Volume: último candle >= X da média (0.2 = 20%)
    PATTERN_VOLUME_MIN_RATIO: float = Field(default=0.2, env="PATTERN_VOLUME_MIN_RATIO")
    # Se True, ignora checagem de volume (memecoins = volume caótico)
    PATTERN_SKIP_VOLUME_CHECK: bool = Field(default=True, env="PATTERN_SKIP_VOLUME_CHECK")
    # Score mínimo para gerar sinal (40 = mais agressivo)
    MIN_SCORE: float = Field(default=40.0, env="MIN_SCORE")

    # Telegram
    TELEGRAM_BOT_TOKEN: str | None = Field(default=None, env="TELEGRAM_BOT_TOKEN")
    TELEGRAM_CHAT_ID: str | None = Field(default=None, env="TELEGRAM_CHAT_ID")

    # Risk parameters
    MAX_POSITION_SIZE_USD: float = Field(default=2.0, env="MAX_POSITION_SIZE_USD")
    # Compra em SOL (prioridade): quando > 0, usa este valor em vez de USD (evita erro de conversão)
    MAX_POSITION_SIZE_SOL: float = Field(default=0.01, env="MAX_POSITION_SIZE_SOL")
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
    # Preferir Helius: HELIUS_RPC (URL completa) ou HELIUS_API_KEY para construir URL; senão SOLANA_RPC_URL
    SOLANA_RPC_URL: str = Field(default="https://api.mainnet-beta.solana.com", env="SOLANA_RPC_URL")
    HELIUS_API_KEY: str | None = Field(default=None, env="HELIUS_API_KEY")
    HELIUS_RPC: str | None = Field(default=None, env="HELIUS_RPC")  # URL completa, ex: https://mainnet.helius-rpc.com/?api-key=XXX
    # Slippage padrão para compra/venda (%); 15% reduz risco de overflow em picos
    DEFAULT_SLIPPAGE: float = Field(default=15.0, env="DEFAULT_SLIPPAGE")
    # Nível de priority fee para Helius (Min, Low, Medium, High, VeryHigh, UnsafeMax)
    PRIORITY_FEE_LEVEL: str = Field(default="high", env="PRIORITY_FEE_LEVEL")
    # Intervalo (s) entre checagens de preço no monitoramento (Jupiter); 15s economiza créditos e é suficiente para SL/TP
    MONITOR_PRICE_INTERVAL_SECONDS: int = Field(default=15, env="MONITOR_PRICE_INTERVAL_SECONDS")
    # Ao iniciar: vender tokens na carteira que não estão em positions.json (resíduos)
    AUTO_CLEANUP_ON_STARTUP: bool = Field(default=False, env="AUTO_CLEANUP_ON_STARTUP")

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

    def get_rpc_url(self) -> str:
        """RPC URL efetiva: HELIUS_RPC > URL construída com HELIUS_API_KEY > SOLANA_RPC_URL."""
        if self.HELIUS_RPC and self.HELIUS_RPC.strip():
            return self.HELIUS_RPC.strip()
        if self.HELIUS_API_KEY and self.HELIUS_API_KEY.strip():
            return f"https://mainnet.helius-rpc.com/?api-key={self.HELIUS_API_KEY.strip()}"
        return self.SOLANA_RPC_URL


settings = Settings()