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
from app.scanners.candle_builder import CandleBuilder
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
# Anti-clone por marketCapSol: mesmos clones aparecem com market_cap idêntico no mesmo segundo
_market_cap_seen: dict[str, float] = {}  # f"{mc:.3f}" -> timestamp

# Instâncias globais
pump_scanner: PumpPortalScanner | None = None
birdeye: BirdeyeScanner | None = None
candle_builder: CandleBuilder | None = None
executor: Executor | None = None
risk_manager: MemeRiskManager | None = None
position_manager: PositionManager | None = None
alerter: TelegramAlerter | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle do FastAPI."""
    global pump_scanner, birdeye, candle_builder, executor, risk_manager, position_manager, alerter

    # Startup
    logger.info("🚀 Iniciando MemeCoin Bot...")

    # 1) Inicializar scanners
    pump_scanner = PumpPortalScanner()
    birdeye = BirdeyeScanner()
    candle_builder = CandleBuilder()

    # 2) Postgres: criar tabelas ANTES de carregar posições (evita "column token does not exist")
    if getattr(settings, "DATABASE_URL", None) and str(settings.DATABASE_URL or "").strip():
        try:
            from app.db.postgres import init_schema
            if init_schema():
                logger.info("Banco de dados Postgres ativo (posições + histórico)")
        except Exception as e:
            logger.warning(f"Postgres init: {e}")

    # 3) Inicializar executor e risk manager (risk carrega posições do DB/JSON)
    executor = Executor()
    risk_manager = MemeRiskManager()
    alerter = TelegramAlerter()

    # 4) Inicializar strategy e registrar callback do scanner
    strategy = MemeScalperStrategy(birdeye)
    async def on_new_token(token_data: dict):
        """Processa novo token do PumpPortal (com delay para OHLCV na Bitquery/Birdeye)."""
        # Tokens já migrados (pool=raydium) continuam sendo analisados; a compra será feita via pool=raydium
        # Pré-filtro: market cap mínimo (50 SOL)
        market_cap = token_data.get("market_cap", 0) or 0
        min_mc = settings.MIN_MARKET_CAP_SOL
        if market_cap > 0 and market_cap < min_mc:
            return

        symbol = (token_data.get("symbol") or "?").strip().upper()
        now = time.time()

        # Anti-clone por marketCapSol: tokens "irmãos" têm market_cap idêntico no mesmo segundo
        if market_cap > 0:
            mc_key = f"{market_cap:.3f}"
            if mc_key in _market_cap_seen and (now - _market_cap_seen[mc_key]) < 10:
                logger.debug(f"⏭️ Ignorando clone por marketCapSol idêntico: {symbol} mc={market_cap:.3f} SOL")
                return
            _market_cap_seen[mc_key] = now
            if len(_market_cap_seen) > 1000:
                cutoff = now - 60
                for k in list(_market_cap_seen.keys()):
                    if _market_cap_seen[k] < cutoff:
                        del _market_cap_seen[k]

        # Anti-clone: ignorar tokens com mesmo symbol já em análise (evita spam AGENC x50)
        if symbol and symbol != "?":
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
            """Constrói OHLCV (CandleBuilder em tempo real ou sleep+Bitquery) e gera sinais."""
            _sym = token_data.get("symbol", "?")
            _addr = token_data.get("address") or token_data.get("mint")
            prebuilt: dict | None = None

            # CandleBuilder substitui o sleep fixo quando USE_REALTIME_CANDLES=True
            if getattr(settings, "USE_REALTIME_CANDLES", False) and rescan_count == 0 and _addr:
                logger.info(f"📊 CandleBuilder ativo para {_sym} — coletando preços em tempo real...")
                prebuilt = await candle_builder.build_candles(_addr)
                if prebuilt:
                    logger.info(f"✅ CandleBuilder: {len(prebuilt['ohlcv'])} candles para {_sym}")
                else:
                    logger.info(f"⚠️ CandleBuilder insuficiente para {_sym} — usando Bitquery/Birdeye como fallback")
            else:
                delay = settings.BIRDEYE_DELAY_SECONDS if rescan_count == 0 else settings.RESCAN_DELAY_SECONDS
                if delay > 0:
                    if rescan_count == 0:
                        logger.info(f"⏳ Aguardando {delay}s para {_sym} (OHLCV)")
                    else:
                        logger.info(f"🔄 Re-analisando {_sym} ({rescan_count}/{settings.MAX_RESCAN_ATTEMPTS}) em {delay}s")
                    await asyncio.sleep(delay)

            try:
                assets = [token_data]
                signals = await strategy.generate_signals(assets, prebuilt_ohlcv=prebuilt)
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
    pump_scanner.set_alerter(alerter)

    # 5) Inicializar PositionManager (preço SL/TP: DexScreener primário, Jupiter fallback; Telegram para alertas)
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
    try:
        from app.db.postgres import close_connection
        close_connection()
    except Exception:
        pass
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