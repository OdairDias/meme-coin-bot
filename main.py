"""
MemeCoin Scalper Bot — Main Application
"""
import asyncio
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.core.logger import setup_logger
from app.scanners.pump_portal import PumpPortalScanner
from app.scanners.birdeye import BirdeyeScanner
from app.strategies.meme_scalper import MemeScalperStrategy
from app.execution.executor import Executor
from app.execution.risk import MemeRiskManager
from app.execution.manager import PositionManager
from app.monitoring.health import healthcheck
from app.monitoring.metrics import init_metrics, open_positions, daily_pnl, trades_total
from app.monitoring.alerts import TelegramAlerter

logger = setup_logger(__name__)


# Instâncias globais
pump_scanner: PumpPortalScanner | None = None
birdeye: BirdeyeScanner | None = None
executor: Executor | None = None
risk_manager: MemeRiskManager | None = None
position_manager: PositionManager | None = None
alerter: TelegramAlerter | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle do FastAPI."""
    global pump_scanner, birdeye, executor, risk_manager, position_manager, alerter

    # Startup
    logger.info("🚀 Iniciando MemeCoin Bot...")

    # 1) Inicializar scanners
    pump_scanner = PumpPortalScanner()
    birdeye = BirdeyeScanner()

    # 2) Inicializar executor e risk manager
    executor = Executor()
    risk_manager = MemeRiskManager()
    alerter = TelegramAlerter()

    # 3) Inicializar strategy
    strategy = MemeScalperStrategy(birdeye)

    # 4) Registrar callback do scanner
    async def on_new_token(token_data: dict):
        """Processa novo token do PumpPortal."""
        try:
            # Pré-filtro leve: só descarta market cap muito baixo (regras pesadas na estratégia)
            market_cap = token_data.get("market_cap", 0) or 0
            if market_cap > 0 and market_cap < 50:
                return

            # Gerar sinal pela estratégia (síncrono, mas vamos rodar async)
            assets = [token_data]
            signals = await strategy.generate_signals(assets)

            for signal in signals:
                # Validar e abrir posição
                await position_manager.open_position(signal)

        except Exception as e:
            logger.error(f"Erro ao processar novo token: {e}")

    pump_scanner.register_callback(on_new_token)

    # 5) Inicializar PositionManager (Birdeye como price feed para SL/TP; Telegram para alertas)
    position_manager = PositionManager(executor, risk_manager, price_fetcher=birdeye, alerter=alerter)

    # 6) Iniciar serviços em background
    await pump_scanner.connect()
    asyncio.create_task(pump_scanner.start())  # loop que recebe mensagens do WebSocket
    await position_manager.start()

    # 7) Iniciar métricas Prometheus
    init_metrics(port=9090)

    logger.info("✅ Bot iniciado com sucesso")

    yield

    # Shutdown
    logger.info("🛑 Encerrando bot...")
    if position_manager:
        await position_manager.stop()
    if pump_scanner:
        await pump_scanner.stop()
    await executor.close()
    await birdeye.close()
    logger.info("✅ Bot encerrado")


app = FastAPI(title="MemeCoin Bot", lifespan=lifespan)


@app.get("/health")
async def health():
    """Health check endpoint."""
    status = healthcheck()
    return JSONResponse(content=status, status_code=200 if status["status"] == "healthy" else 503)


@app.get("/metrics")
async def metrics():
    """Prometheus metrics endpoint."""
    from fastapi.responses import PlainTextResponse
    return PlainTextResponse(content="")  # O servidor de métricas roda separado