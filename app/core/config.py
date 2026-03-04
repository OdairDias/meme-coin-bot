"""
Configurações centralizadas do MemeCoin Bot
"""
try:
    from pydantic_settings import BaseSettings
except ImportError:
    from pydantic import BaseSettings

from pydantic import Field


class Settings(BaseSettings):
    """Configurações da aplicação"""

    # Wallet Solana
    WALLET_PRIVATE_KEY: str = Field(..., env="WALLET_PRIVATE_KEY")

    # APIs
    BIRDEYE_API_KEY: str | None = Field(default=None, env="BIRDEYE_API_KEY")
    BITQUERY_API_KEY: str | None = Field(default=None, env="BITQUERY_API_KEY")
    # Delay (s) após detectar token antes de consultar OHLCV (indexação):
    # Birdeye: ~300s (indexação lenta). Bitquery: ~60s (combined dataset é quase real-time).
    # Com Bitquery configurada, 300s desperdiça a janela de pump — reduza para 60.
    BIRDEYE_DELAY_SECONDS: int = Field(default=60, env="BIRDEYE_DELAY_SECONDS")
    # Market cap mínimo (SOL) — só analisa tokens com market cap >= este valor (50 SOL)
    MIN_MARKET_CAP_SOL: float = Field(default=50.0, env="MIN_MARKET_CAP_SOL")
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
    STOP_LOSS_PERCENT: float = Field(default=30.0, env="STOP_LOSS_PERCENT")
    TAKE_PROFIT_PERCENT1: float = Field(default=50.0, env="TAKE_PROFIT_PERCENT1")
    TAKE_PROFIT_PERCENT2: float = Field(default=200.0, env="TAKE_PROFIT_PERCENT2")
    # Buffer para TP1: reduz o threshold para garantir que pegue o movimento (ex: 80% = 0.8, 100% = desabilitado)
    TAKE_PROFIT_BUFFER: float = Field(default=0.8, env="TAKE_PROFIT_BUFFER")
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
    # Slippage padrão para compra (%). Ver docs/SLIPPAGE_E_TAXAS.md
    DEFAULT_SLIPPAGE: float = Field(default=15.0, env="DEFAULT_SLIPPAGE")
    # Se True, usa entry_price conservador (preço_sinal × (1 + DEFAULT_SLIPPAGE/100)) para SL/TP
    # DESLIGADO por padrão: inflava entry em 30%, atrasando SL e causando perdas maiores (-30% a -53% vs -20% target)
    USE_CONSERVATIVE_ENTRY: bool = Field(default=False, env="USE_CONSERVATIVE_ENTRY")
    # Nível de priority fee para Helius (Min, Low, Medium, High, VeryHigh, UnsafeMax)
    PRIORITY_FEE_LEVEL: str = Field(default="veryHigh", env="PRIORITY_FEE_LEVEL")
    # Fallback de Priority Fee em SOL caso não use RPC Helius (0.001 SOL = ~$0.15, super competitivo)
    PRIORITY_FEE_FALLBACK_SOL: float = Field(default=0.001, env="PRIORITY_FEE_FALLBACK_SOL")
    # Intervalo (s) entre checagens de preço no monitoramento (DexScreener + Jupiter fallback)
    # 3s = mais rápido para SL em memecoins voláteis (5s causava SL a -35%/-59% vs -20% target)
    MONITOR_PRICE_INTERVAL_SECONDS: int = Field(default=3, env="MONITOR_PRICE_INTERVAL_SECONDS")
    # Emergency sell: se o preço cair este % ALÉM do SL configurado em um único tick, vende com slippage alto (50%)
    # Exemplo: SL=20%, EMERGENCY=15% → se pnl < -35% em um tick, emergency sell ativa
    EMERGENCY_SELL_THRESHOLD: float = Field(default=15.0, env="EMERGENCY_SELL_THRESHOLD")
    # Se True, retentar compra com priority_fee * 1.5 quando tx não é encontrada por timeout (evita gas perdido)
    BUY_RETRY_ON_TIMEOUT: bool = Field(default=True, env="BUY_RETRY_ON_TIMEOUT")
    # Ao iniciar: vender tokens na carteira que não estão em positions.json (resíduos)
    AUTO_CLEANUP_ON_STARTUP: bool = Field(default=False, env="AUTO_CLEANUP_ON_STARTUP")

    # Fase 1 — CandleBuilder (substitui sleep fixo + Bitquery para construir OHLCV em tempo real)
    USE_REALTIME_CANDLES: bool = Field(default=False, env="USE_REALTIME_CANDLES")
    CANDLE_TIMEFRAME_SECONDS: int = Field(default=15, env="CANDLE_TIMEFRAME_SECONDS")
    CANDLE_BUILD_TIMEOUT_SECONDS: int = Field(default=90, env="CANDLE_BUILD_TIMEOUT_SECONDS")

    # Fase 1 — RugCheck (filtro de risco antes do OHLCV; free tier)
    RUGCHECK_ENABLED: bool = Field(default=False, env="RUGCHECK_ENABLED")
    RUGCHECK_MIN_SCORE: int = Field(default=500, env="RUGCHECK_MIN_SCORE")

    # Fase 1 — Heartbeat e alerta de inatividade via Telegram
    NO_TOKEN_ALERT_SECONDS: int = Field(default=300, env="NO_TOKEN_ALERT_SECONDS")
    HEARTBEAT_INTERVAL_MINUTES: int = Field(default=30, env="HEARTBEAT_INTERVAL_MINUTES")

    # Redis
    REDIS_URL: str = Field(default="redis://localhost:6379", env="REDIS_URL")

    # PostgreSQL (Railway ou local) — quando definido, posições e histórico usam o DB em vez de positions.json
    DATABASE_URL: str | None = Field(default=None, env="DATABASE_URL")

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