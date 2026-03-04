"""
Gerenciador de posições — abre e fecha posições
"""
from typing import Dict, Any, Optional
from datetime import datetime, timezone
import asyncio

from app.core.config import settings
from app.core.logger import setup_logger
from app.execution.executor import Executor
from app.execution.risk import MemeRiskManager

logger = setup_logger(__name__)


class PositionManager:
    """Gerencia ciclo de vida das posições (abrir, monitorar, fechar)."""

    def __init__(
        self,
        executor: Executor,
        risk_manager: MemeRiskManager,
        price_fetcher=None,
        alerter=None,
    ):
        self.executor = executor
        self.risk_manager = risk_manager
        self.price_fetcher = price_fetcher  # DexScreener primário, Jupiter fallback (SL/TP)
        self.alerter = alerter  # TelegramAlerter para notificações
        self.running = False
        self.monitor_task: asyncio.Task | None = None

    async def start(self):
        """Inicia monitoramento de posições."""
        self.running = True
        self.monitor_task = asyncio.create_task(self._monitor_loop())
        logger.info("PositionManager started")

    async def stop(self):
        """Para monitoramento."""
        self.running = False
        if self.monitor_task:
            self.monitor_task.cancel()
            try:
                await self.monitor_task
            except asyncio.CancelledError:
                pass
        logger.info("PositionManager stopped")

    async def open_position(self, signal: Dict[str, Any]) -> bool:
        """
        Abre nova posição.
        Retorna True se sucesso.
        """
        # Validar com risk manager
        validation = self.risk_manager.validate_signal(signal, current_equity=100.0)  # banca fixa por enquanto
        if not validation["valid"]:
            reasons = ", ".join(validation["reasons"])
            logger.warning(f"❌ Sinal rejeitado: {reasons}")
            return False

        # Executar compra: SOL (recomendado) ou tokens
        buy_in_sol = signal.get("buy_in_sol", False)
        buy_amount = signal.get("buy_amount_sol", 0) if buy_in_sol else signal["quantity"]
        try:
            success = await self.executor.buy(
                token_address=signal["address"],
                amount=buy_amount,
                denominated_in_sol=buy_in_sol,
                slippage=0,  # 0 = deixar executor calcular dinamicamente via _get_dynamic_slippage
                pool=signal.get("pool", "auto"),
                liquidity_usd=signal.get("liquidity_usd", 0),
            )
            if not success:
                logger.error(f"Falha ao comprar {signal['symbol']}")
                return False

            signal_entry = signal["entry_price"]

            # Busca o preço REAL pós-compra via DexScreener/Jupiter.
            # O sinal é gerado com o preço do momento da detecção, mas o OHLCV
            # leva 120-300s para indexar — nesse tempo o token pode ter subido muito.
            # Usar entry stale causa ganhos/perdas fantasmas (ex: +8198% com gain real de 3%).
            actual_entry = signal_entry
            if self.price_fetcher:
                try:
                    fetched_info = await self.price_fetcher.get_token_info(signal["address"])
                    fetched_price = float(fetched_info.get("price_usd", 0)) if fetched_info else 0.0
                    if fetched_price > 0:
                        actual_entry = fetched_price
                        diff_pct = (actual_entry - signal_entry) / max(signal_entry, 1e-18) * 100
                        if abs(diff_pct) <= 1.0:
                            logger.warning(
                                f"⚠️ Entry pós-compra igual ao sinal (possível cache DexScreener): "
                                f"${actual_entry:.8f} ≈ sinal=${signal_entry:.8f} — PnL pode estar inflado"
                            )
                        elif diff_pct > 10:
                            logger.info(
                                f"Entry real (pós-compra): ${actual_entry:.8f} vs sinal=${signal_entry:.8f} "
                                f"(token subiu {diff_pct:.0f}% durante delay de OHLCV)"
                            )
                        else:
                            logger.info(f"Entry confirmado pós-compra: ${actual_entry:.8f} (sinal=${signal_entry:.8f})")
                except Exception as e:
                    logger.debug(f"Fetch entry pós-compra falhou: {e}")

            if settings.USE_CONSERVATIVE_ENTRY:
                entry_for_sl_tp = actual_entry * (1.0 + settings.DEFAULT_SLIPPAGE / 100.0)
                logger.info(
                    f"Entry conservador: atual=${actual_entry:.8f} → entry_sl_tp=${entry_for_sl_tp:.8f} "
                    f"(+{settings.DEFAULT_SLIPPAGE:.0f}% slippage)"
                )
            else:
                entry_for_sl_tp = actual_entry

            qty_for_record = "100%" if buy_in_sol else signal["quantity"]
            await self.risk_manager.record_position_open(
                token=signal["address"],
                entry_price=entry_for_sl_tp,
                quantity=qty_for_record,
                side="BUY",
                symbol=signal.get("symbol", ""),
                buy_amount_sol=buy_amount if buy_in_sol else 0,
            )

            log_qty = f"{buy_amount} SOL" if buy_in_sol else f"qty={signal['quantity']:.6f}"
            logger.info(f"✅ Posição aberta: {signal['symbol']} {log_qty} @ ${entry_for_sl_tp:.8f} (sinal=${signal_entry:.8f})")
            if self.alerter:
                try:
                    qty_alert = buy_amount if buy_in_sol else signal["quantity"]
                    await self.alerter.send_trade(
                        symbol=signal["symbol"],
                        side="BUY",
                        price=entry_for_sl_tp,
                        quantity=qty_alert,
                    )
                except Exception as e:
                    logger.debug(f"Telegram (trade): {e}")
            return True

        except Exception as e:
            logger.error(f"Erro ao abrir posição: {e}", exc_info=True)
            return False

    async def close_position(self, token: str, reason: str = "MANUAL", slippage: float = 10.0):
        """Fecha posição existente."""
        if token not in self.risk_manager.open_positions:
            logger.warning(f"Posição não encontrada: {token}")
            return False

        pos = self.risk_manager.open_positions[token]
        current_price = pos.get("current_price", pos["entry_price"])
        entry = pos["entry_price"]
        quantity = pos["quantity"]
        side = pos.get("side", "BUY")
        symbol = pos.get("symbol") or token[:8]
        symbol = symbol.decode() if isinstance(symbol, bytes) else str(symbol)

        # Sempre vender 100% — vendas parciais (50%) falham com tokens graduados (PumpPortal 400)
        amount_to_sell = "100%"

        # Executar venda (sempre 100% — parciais falham com tokens graduados)
        try:
            try:
                success = await self.executor.sell(
                    token_address=token,
                    amount=amount_to_sell,
                    denominated_in_sol=False,
                    slippage=slippage,
                )
            except ValueError as e:
                if str(e) == "ZERO_BALANCE":
                    logger.error(f"ERRO CRÍTICO: Saldo zero para {token}, tokens NÃO foram vendidos! Posição mantida.")
                    if self.alerter:
                        try:
                            await self.alerter.send_alert("critical", f"FALHA AO VENDER {symbol}: saldo zero. Posição mantida!")
                        except Exception:
                            pass
                    return False
                else:
                    raise
            if not success:
                logger.error(f"Falha ao vender {token}")
                return False

            if isinstance(quantity, str):
                # Calcular PnL percent primeiro
                if side == "BUY":
                    pnl_percent = ((current_price - entry) / entry * 100) if entry > 0 else 0
                else:
                    pnl_percent = ((entry - current_price) / entry * 100) if entry > 0 else 0

                # Desconto do slippage pago na saída (reduz PnL exibido para refletir valor real recebido)
                slippage_paid = getattr(settings, 'DEFAULT_SLIPPAGE', 15.0)
                pnl_percent_net = pnl_percent - slippage_paid

                buy_amount_sol = pos.get("buy_amount_sol", 0)
                sol_price_usd = 100.0
                try:
                    from app.scanners.jupiter import get_sol_price_usd
                    fetched = await get_sol_price_usd()
                    if fetched and fetched > 0:
                        sol_price_usd = fetched
                except Exception:
                    pass

                buy_amount_usd = buy_amount_sol * sol_price_usd
                if "50" in quantity:
                    buy_amount_usd = buy_amount_usd * 0.5

                if buy_amount_usd > 0:
                    pnl = (pnl_percent_net / 100) * buy_amount_usd
                else:
                    pnl = 0.0

                logger.info(
                    f"PnL bruto={pnl_percent:.1f}% | slippage_saída=-{slippage_paid:.0f}% | PnL líquido={pnl_percent_net:.1f}%"
                )
                pnl_percent = pnl_percent_net
            elif isinstance(quantity, (int, float)) and quantity > 0:
                if side == "BUY":
                    pnl = (current_price - entry) * quantity
                    pnl_percent = ((current_price - entry) / entry * 100) if entry > 0 else 0
                else:
                    pnl = (entry - current_price) * quantity
                    pnl_percent = ((entry - current_price) / entry * 100) if entry > 0 else 0
            else:
                pnl = 0.0
                pnl_percent = 0.0

            # Registrar fechamento
            await self.risk_manager.record_position_close(token, current_price, reason)
            logger.info(f"✅ Posição fechada: {token} motivo={reason}")

            if self.alerter:
                try:
                    await self.alerter.send_position_closed(symbol, pnl, pnl_percent, reason)
                except Exception as e:
                    logger.debug(f"Telegram (fechamento): {e}")
            return True

        except Exception as e:
            logger.error(f"Erro ao fechar posição {token}: {e}", exc_info=True)
            return False

    async def _partial_close_position(self, token: str) -> bool:
        """Fecha 50% da posição (take profit parcial). Mantém a posição com quantity=50%.
        Limite de 3 tentativas; após isso, faz close total."""
        _MAX_PARTIAL_ATTEMPTS = 3

        if token not in self.risk_manager.open_positions:
            logger.warning(f"Posição não encontrada para parcial: {token}")
            return False

        pos = self.risk_manager.open_positions[token]
        attempts = pos.get("_partial_attempts", 0) + 1
        pos["_partial_attempts"] = attempts

        if attempts > _MAX_PARTIAL_ATTEMPTS:
            logger.warning(f"Parcial falhou {_MAX_PARTIAL_ATTEMPTS}x para {token[:12]}. Vendendo 100%.")
            return await self.close_position(token, reason="TAKE_PROFIT_PARTIAL_FALLBACK")

        current_price = pos.get("current_price", pos["entry_price"])
        entry = pos["entry_price"]
        side = pos.get("side", "BUY")
        symbol = pos.get("symbol") or token[:8]
        symbol = symbol.decode() if isinstance(symbol, bytes) else str(symbol)

        try:
            success = await self.executor.sell(
                token_address=token,
                amount="50%",
                denominated_in_sol=False,
                slippage=0,
            )
            if not success:
                logger.error(f"Falha ao vender 50% de {token} (tentativa {attempts}/{_MAX_PARTIAL_ATTEMPTS})")
                return False

            pnl_percent_gross = ((current_price - entry) / entry * 100) if (side == "BUY" and entry > 0) else 0
            # Desconto do slippage pago na saída parcial
            slippage_paid = getattr(settings, 'DEFAULT_SLIPPAGE', 15.0)
            pnl_percent = pnl_percent_gross - slippage_paid
            buy_amount_sol = pos.get("buy_amount_sol", 0)
            sol_price_usd = 100.0
            try:
                from app.scanners.jupiter import get_sol_price_usd
                fetched = await get_sol_price_usd()
                if fetched and fetched > 0:
                    sol_price_usd = fetched
            except Exception:
                pass

            if buy_amount_sol > 0:
                buy_amount_usd = buy_amount_sol * sol_price_usd
                pnl_usd = (pnl_percent / 100) * (buy_amount_usd * 0.5)  # 50% da posição
            else:
                pnl_usd = 0.0
            logger.info(
                f"PnL bruto TP1={pnl_percent_gross:.1f}% | slippage_saída=-{slippage_paid:.0f}% | PnL líquido={pnl_percent:.1f}%"
            )

            self.risk_manager.open_positions[token]["quantity"] = "50%"
            try:
                from app.execution.positions_persistence import update_position_quantity
                update_position_quantity(token, "50%")
            except Exception as e:
                logger.warning(f"Erro ao persistir quantity 50%: {e}")

            try:
                from app.execution.positions_persistence import record_closed_position
                record_closed_position(
                    token=token,
                    symbol=symbol,
                    entry_price=entry,
                    exit_price=current_price,
                    quantity="50%",
                    side=side,
                    opened_at=pos.get("opened_at"),
                    reason="TAKE_PROFIT_PARTIAL",
                    pnl_usd=pnl_usd,
                    pnl_percent=pnl_percent,
                )
            except Exception as e:
                logger.debug(f"record_closed_position (parcial): {e}")

            logger.info(f"✅ Fechamento parcial: {token} 50% vendido @ ${current_price:.6f} (gain ~{pnl_percent:.1f}%)")
            if self.alerter:
                try:
                    await self.alerter.send_position_closed(symbol, pnl_usd, pnl_percent, "TAKE_PROFIT_PARTIAL")
                except Exception as e:
                    logger.debug(f"Telegram (parcial): {e}")
            return True

        except ValueError as e:
            if str(e) == "ZERO_BALANCE":
                logger.warning(f"Saldo zero para parcial {token}, fechando posição inteira.")
                await self.close_position(token, reason="TAKE_PROFIT_PARTIAL_ZERO_BALANCE")
            else:
                raise
        except Exception as e:
            logger.error(f"Erro no fechamento parcial {token}: {e}", exc_info=True)
            return False

    async def _monitor_loop(self):
        """Loop que monitora preços (DexScreener primário, Jupiter fallback) e verifica SL/TP/timeout."""
        import time as _time
        interval = max(3, settings.MONITOR_PRICE_INTERVAL_SECONDS)
        logger.info("Iniciando monitoramento de posições... (intervalo %ds)", interval)
        emergency_threshold = getattr(settings, "EMERGENCY_SELL_THRESHOLD", 15.0)
        heartbeat_interval = getattr(settings, "HEARTBEAT_INTERVAL_MINUTES", 30) * 60
        _last_heartbeat = _time.time()
        while self.running:
            try:
                await asyncio.sleep(interval)

                for token, pos in list(self.risk_manager.open_positions.items()):
                    current_price = pos["entry_price"]
                    if self.price_fetcher:
                        try:
                            info = await self.price_fetcher.get_token_info(token)
                            if info and (info.get("price_usd") or 0) > 0:
                                current_price = float(info["price_usd"])
                                self.risk_manager.open_positions[token]["current_price"] = current_price
                        except Exception as e:
                            logger.debug(f"Preço {token}: {e}")

                    entry = pos["entry_price"]
                    pnl_now = ((current_price - entry) / entry * 100) if entry > 0 else 0

                    # Emergency sell: queda muito acima do SL em um único tick (crash rápido)
                    emergency_trigger = -(settings.STOP_LOSS_PERCENT + emergency_threshold)
                    if pnl_now <= emergency_trigger:
                        logger.warning(
                            f"🚨 EMERGENCY SELL {token[:8]}: pnl={pnl_now:.1f}% "
                            f"(limite emergency={emergency_trigger:.0f}%) — slippage 50%"
                        )
                        await self.close_position(token, reason="STOP_LOSS_EMERGENCY", slippage=50.0)
                        continue

                    exit_reason = self.risk_manager.check_exit_conditions(token, current_price)
                    if exit_reason:
                        logger.info(f"🔍 Condição de saída para {token}: {exit_reason}")
                        if exit_reason == "TAKE_PROFIT_PARTIAL":
                            await self._partial_close_position(token)
                        else:
                            await self.close_position(token, reason=exit_reason)

                # Heartbeat periódico — confirma que o loop está vivo
                now_hb = _time.time()
                if now_hb - _last_heartbeat >= heartbeat_interval:
                    _last_heartbeat = now_hb
                    n_pos = len(self.risk_manager.open_positions)
                    logger.info(f"💓 Heartbeat: bot ativo — {n_pos} posição(ões) monitorada(s)")
                    if self.alerter:
                        try:
                            await self.alerter.send_alert(
                                "info",
                                f"Heartbeat: bot ativo.\nPosições abertas: {n_pos}\nIntervalo monitor: {interval}s",
                            )
                        except Exception as e:
                            logger.debug(f"Heartbeat Telegram: {e}")

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Erro no monitoramento: {e}", exc_info=True)

        logger.info("Monitoramento encerrado")