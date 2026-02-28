"""
MemeCoin Scalper Bot — Main Application
"""
import asyncio
import time
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.core.logger import setup_logger
from app.scanners.pump_portal import PumpPortalScanner
from app.scanners.birdeye import BirdeyeScanner
from app.scanners.jupiter import PriceFetcherWithFallback
from app.strategies.meme_scalper import MemeScalperStrategy
from app.execution.executor import Executor
from app.execution.risk import MemeRiskManager
from app.execution.manager import PositionManager
from app.monitoring.health import healthcheck
from app.monitoring.metrics import init_metrics, open_positions, daily_pnl, trades_total
from app.monitoring.alerts import TelegramAlerter

logger = setup_logger(__name__)

# Anti-clone: symbol -> timestamp da última análise iniciada
_symbol_analyzing: dict[str, float] = {}

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
        """Processa novo token do PumpPortal (com delay para Birdeye ter candles)."""
        # Tokens já migrados (pool=raydium) continuam sendo analisados; a compra será feita via pool=raydium
        # Pré-filtro: market cap mínimo (60 SOL = indexação mais rápida na Bitquery)
        market_cap = token_data.get("market_cap", 0) or 0
        min_mc = settings.MIN_MARKET_CAP_SOL
        if market_cap > 0 and market_cap < min_mc:
            return

        # Anti-clone: ignorar tokens com mesmo symbol já em análise (evita spam AGENC x50)
        symbol = (token_data.get("symbol") or "?").strip().upper()
        if symbol and symbol != "?":
            now = time.time()
            window = settings.ANTI_CLONE_SYMBOL_SECONDS
            if symbol in _symbol_analyzing and (now - _symbol_analyzing[symbol]) < window:
                logger.debug(f"⏭️ Ignorando clone {symbol} (já em análise há {int(now - _symbol_analyzing[symbol])}s)")
                return
            _symbol_analyzing[symbol] = now
            # Limpar entradas antigas quando cache cresce
            if len(_symbol_analyzing) > 500:
                cutoff = now - window
                for k in list(_symbol_analyzing.keys()):
                    if _symbol_analyzing[k] < cutoff:
                        del _symbol_analyzing[k]

        async def process_after_delay(rescan_count: int = 0):
            """Aguarda delay para Birdeye ter candles; re-scan até MAX_RESCAN_ATTEMPTS vezes."""
            delay = settings.BIRDEYE_DELAY_SECONDS if rescan_count == 0 else settings.RESCAN_DELAY_SECONDS
            if delay > 0:
                symbol = token_data.get("symbol", "?")
                if rescan_count == 0:
                    logger.info(f"⏳ Aguardando {delay}s para {symbol} (OHLCV)")
                else:
                    logger.info(f"🔄 Re-analisando {symbol} ({rescan_count}/{settings.MAX_RESCAN_ATTEMPTS}) em {delay}s")
                await asyncio.sleep(delay)
            try:
                assets = [token_data]
                signals = await strategy.generate_signals(assets)
                for signal in signals:
                    await position_manager.open_position(signal)
                # Re-scan: se 0 sinais e ainda há tentativas, agendar retry
                max_rescans = settings.MAX_RESCAN_ATTEMPTS
                if not signals and rescan_count < max_rescans - 1 and settings.RESCAN_DELAY_SECONDS > 0:
                    asyncio.create_task(process_after_delay(rescan_count=rescan_count + 1))
            except Exception as e:
                logger.error(f"Erro ao processar novo token: {e}")

        # Rodar em task separada para não bloquear recebimento de novos tokens
        asyncio.create_task(process_after_delay(rescan_count=0))

    pump_scanner.register_callback(on_new_token)

    # 5) Inicializar PositionManager (Jupiter + DexScreener fallback para preço SL/TP; Telegram para alertas)
    price_fetcher = PriceFetcherWithFallback()
    position_manager = PositionManager(executor, risk_manager, price_fetcher=price_fetcher, alerter=alerter)

    # 6) Iniciar serviços em background
    await pump_scanner.connect()
    asyncio.create_task(pump_scanner.start())  # loop que recebe mensagens do WebSocket
    await position_manager.start()

    # 6b) Auto-cleanup: vender resíduos (tokens na carteira fora de positions.json)
    if getattr(settings, "AUTO_CLEANUP_ON_STARTUP", False):
        try:
            from app.execution.startup_cleanup import run_startup_cleanup
            cleanup_result = await run_startup_cleanup()
            if not cleanup_result.get("skipped") and cleanup_result.get("sold", 0) > 0:
                logger.info(f"Startup cleanup: {cleanup_result['sold']} resíduo(s) vendido(s)")
        except Exception as e:
            logger.warning(f"Startup cleanup: {e}")

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


@app.post("/force-sell-all")
async def force_sell_all(dry_run: bool = False):
    """
    Emergência: vende todos os tokens da carteira para SOL via Jupiter.
    Ignora estratégia. Varre getTokenAccountsByOwner e executa swap.
    dry_run=true: apenas lista tokens, não executa.
    """
    from app.execution.force_sell import run_force_sell_all
    result = await run_force_sell_all(dry_run=dry_run)
    return result