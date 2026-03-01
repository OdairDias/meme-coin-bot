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
                slippage=0,
                pool=signal.get("pool", "auto"),
            )
            if not success:
                logger.error(f"Falha ao comprar {signal['symbol']}")
                return False

            # Entry price para SL/TP: conservador = preço_sinal × (1 + slippage%) para alinhar com custo real
            signal_entry = signal["entry_price"]
            if getattr(settings, "USE_CONSERVATIVE_ENTRY", True):
                entry_for_sl_tp = signal_entry * (1.0 + settings.DEFAULT_SLIPPAGE / 100.0)
                logger.debug(f"Entry conservador: {signal_entry:.6f} → {entry_for_sl_tp:.6f} (+{settings.DEFAULT_SLIPPAGE}%)")
            else:
                entry_for_sl_tp = signal_entry

            # Registrar posição (quantity="100%" quando buy_in_sol para vender tudo)
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
            logger.info(f"✅ Posição aberta: {signal['symbol']} {log_qty} @ ${entry_for_sl_tp:.6f} (custo ref)")
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

    async def close_position(self, token: str, reason: str = "MANUAL"):
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

        # Executar venda
        try:
            try:
                success = await self.executor.sell(
                    token_address=token,
                    amount=pos["quantity"],
                    denominated_in_sol=False,
                    slippage=0,
                )
            except ValueError as e:
                if str(e) == "ZERO_BALANCE":
                    logger.warning(f"Saldo zero para {token}, fechando localmente.")
                    success = True
                    reason = f"{reason}_ZERO_BALANCE"
                else:
                    raise

            if not success:
                logger.error(f"Falha ao vender {token}")
                return False

            # PnL para notificação - calcular baseado na quantidade real ou_estimada
            # Se quantity é string (100% ou 50%), estimar baseado no buy_amount_sol
            actual_quantity = quantity
            if isinstance(quantity, str):
                # Estimar tokens comprados: SOL gasto / preço de entrada (em USD)
                buy_amount_sol = pos.get("buy_amount_sol", 0)
                if buy_amount_sol > 0 and entry > 0:
                    # Converter entry para SOL (assumindo preço do SOL ~USD)
                    # entry é em USD, mas buy_amount_sol é em SOL
                    # PnL em USD = tokens * (exit_price - entry_price)
                    # tokens = buy_amount_sol_usd / entry_price (mas entry_price já tem slippage)
                    # Simplificado: PnL% = (exit/entry - 1) * 100
                    pass  # Vamos calcular % primeiro
                
                # Calcular PnL percent primeiro
                if side == "BUY":
                    pnl_percent = ((current_price - entry) / entry * 100) if entry > 0 else 0
                else:
                    pnl_percent = ((entry - current_price) / entry * 100) if entry > 0 else 0
                    
                # Se é 50%, usar metade do buy_amount_sol
                if "50" in quantity:
                    buy_amount_sol = buy_amount_sol * 0.5 if buy_amount_sol > 0 else 0
                
                # PnL em USD aproximado: % do valor que gastamos
                if buy_amount_sol > 0:
                    pnl = (pnl_percent / 100) * buy_amount_sol  # buy_amount_sol é近似 USD quando entry_price inclui slippage
                else:
                    pnl = 0.0
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
        """Fecha 50% da posição (take profit parcial). Mantém a posição com quantity=50%."""
        if token not in self.risk_manager.open_positions:
            logger.warning(f"Posição não encontrada para parcial: {token}")
            return False

        pos = self.risk_manager.open_positions[token]
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
                logger.error(f"Falha ao vender 50% de {token}")
                return False

            pnl_percent = ((current_price - entry) / entry * 100) if (side == "BUY" and entry > 0) else 0
            # Calcular PnL USD baseado no buy_amount_sol
            buy_amount_sol = pos.get("buy_amount_sol", 0)
            if buy_amount_sol > 0:
                pnl_usd = (pnl_percent / 100) * (buy_amount_sol * 0.5)  # 50% da posição
            else:
                pnl_usd = 0.0

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
        interval = max(5, settings.MONITOR_PRICE_INTERVAL_SECONDS)
        logger.info("Iniciando monitoramento de posições... (intervalo %ds)", interval)
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

                    exit_reason = self.risk_manager.check_exit_conditions(token, current_price)
                    if exit_reason:
                        logger.info(f"🔍 Condição de saída para {token}: {exit_reason}")
                        if exit_reason == "TAKE_PROFIT_PARTIAL":
                            await self._partial_close_position(token)
                        else:
                            await self.close_position(token, reason=exit_reason)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Erro no monitoramento: {e}", exc_info=True)

        logger.info("Monitoramento encerrado")