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
strategy: MemeScalperStrategy | None = None

# Fase 3 — Fila de prioridade para processamento de tokens
# Items: (priority, queued_at, token_data, rescan_count)
# priority = -market_cap  →  maior market_cap é processado primeiro
_token_queue: asyncio.PriorityQueue = asyncio.PriorityQueue(maxsize=500)


async def _process_token(token_data: dict, rescan_count: int = 0) -> None:
    """
    Constrói OHLCV (CandleBuilder ou sleep+Bitquery) e gera sinais de compra.
    Chamado pelos workers da fila de prioridade (Fase 3).
    """
    if strategy is None or position_manager is None:
        return

    _sym = token_data.get("symbol", "?")
    _addr = token_data.get("address") or token_data.get("mint")
    prebuilt = None

    # RugCheck ANTES do CandleBuilder — evita desperdiçar 90s em tokens ruins.
    # Só no primeiro scan (rescan_count == 0): rescans já foram pré-aprovados.
    # Se reprovar: return imediato sem enfileirar rescan.
    _rugcheck_passed = False
    if getattr(settings, "RUGCHECK_ENABLED", False) and _addr and rescan_count == 0:
        try:
            from app.scanners.rugcheck import check_token
            rc_pass, _, rc_reason = await check_token(_addr)
            if not rc_pass:
                logger.info(f"⏭️ {_sym} rejeitado RugCheck (pré-CandleBuilder): {rc_reason}")
                return  # sem CandleBuilder, sem rescan
            _rugcheck_passed = True
        except Exception as e:
            logger.debug(f"RugCheck pré-check erro (ignorado): {e}")

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
        # skip_rugcheck=True quando:
        # - rescan_count == 0 e RugCheck já passou no pré-check acima (_rugcheck_passed)
        # - rescan_count > 0: token já foi aprovado no primeiro scan
        _skip_rc = _rugcheck_passed or rescan_count > 0
        signals = await strategy.generate_signals(
            [token_data], prebuilt_ohlcv=prebuilt, skip_rugcheck=_skip_rc
        )
        for signal in signals:
            await position_manager.open_position(signal)

        # Re-scan: se nenhum sinal, colocar de volta na fila com prioridade idêntica
        max_rescans = settings.MAX_RESCAN_ATTEMPTS
        if not signals and rescan_count < max_rescans - 1 and settings.RESCAN_DELAY_SECONDS > 0:
            mc = token_data.get("market_cap", 0) or 0
            try:
                _token_queue.put_nowait((-mc, time.time(), token_data, rescan_count + 1))
            except asyncio.QueueFull:
                logger.debug(f"Fila cheia — rescan de {_sym} descartado")
    except Exception as e:
        logger.error(f"Erro ao processar token {_sym}: {e}")


async def _token_queue_worker() -> None:
    """
    Worker da fila de prioridade — puxa tokens em ordem de market_cap (maior primeiro)
    e chama _process_token. Roda em background durante o ciclo de vida do bot.
    """
    while True:
        try:
            priority, queued_at, token_data, rescan_count = await asyncio.wait_for(
                _token_queue.get(), timeout=60.0
            )
            max_age = getattr(settings, "TOKEN_QUEUE_MAX_AGE_SECONDS", 600)
            age = time.time() - queued_at
            if age > max_age:
                sym = token_data.get("symbol", "?")
                logger.debug(f"⏭️ Token {sym} expirou na fila ({age:.0f}s > {max_age}s) — descartado")
                _token_queue.task_done()
                continue
            await _process_token(token_data, rescan_count)
            _token_queue.task_done()
        except asyncio.TimeoutError:
            continue
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Queue worker erro: {e}", exc_info=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle do FastAPI."""
    global pump_scanner, birdeye, candle_builder, executor, risk_manager, position_manager, alerter, strategy

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
    async def on_new_token(token_data: dict):  # noqa: E306
        """Processa novo token do PumpPortal (com delay para OHLCV na Bitquery/Birdeye)."""
        # Tokens já migrados (pool=raydium) continuam sendo analisados; a compra será feita via pool=raydium
        # Pré-filtro: market cap mínimo (50 SOL)
        market_cap = token_data.get("market_cap", 0) or 0
        min_mc = settings.MIN_MARKET_CAP_SOL
        if market_cap > 0 and market_cap < min_mc:
            return

        symbol = ((token_data.get("symbol") or "").strip().upper()) or "?"
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

        # Fase 3: Colocar na fila de prioridade (market_cap mais alto = processado primeiro)
        mc = market_cap or 0
        try:
            _token_queue.put_nowait((-mc, now, token_data, 0))
            logger.debug(
                f"📥 {symbol} adicionado à fila (mc={mc:.0f} SOL, fila={_token_queue.qsize()})"
            )
        except asyncio.QueueFull:
            logger.warning(f"⚠️ Fila de tokens cheia ({_token_queue.maxsize}) — {symbol} descartado")

    pump_scanner.register_callback(on_new_token)
    pump_scanner.set_alerter(alerter)

    # 5) Inicializar PositionManager (preço SL/TP: DexScreener primário, Jupiter fallback; Telegram para alertas)
    price_fetcher = PriceFetcherWithFallback()
    position_manager = PositionManager(executor, risk_manager, price_fetcher=price_fetcher, alerter=alerter)

    # 6) Iniciar serviços em background
    await pump_scanner.connect()
    asyncio.create_task(pump_scanner.start())  # loop que recebe mensagens do WebSocket
    await position_manager.start()

    # Fase 3: workers da fila de prioridade
    n_workers = getattr(settings, "TOKEN_QUEUE_WORKERS", 3)
    _queue_workers = [asyncio.create_task(_token_queue_worker()) for _ in range(n_workers)]
    logger.info(f"📥 Fila de prioridade ativa — {n_workers} worker(s) aguardando tokens")

    # Fase 3: listener de comandos Telegram (/report, /status)
    await alerter.set_risk_manager(risk_manager)
    asyncio.create_task(alerter.start_command_listener())

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
    # Cancelar workers da fila
    for w in _queue_workers:
        w.cancel()
    await alerter.stop_command_listener()
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