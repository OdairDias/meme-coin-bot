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
        self.price_fetcher = price_fetcher  # ex.: BirdeyeScanner com get_token_info
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
            )
            if not success:
                logger.error(f"Falha ao comprar {signal['symbol']}")
                return False

            # Registrar posição (quantity="100%" quando buy_in_sol para vender tudo)
            qty_for_record = "100%" if buy_in_sol else signal["quantity"]
            await self.risk_manager.record_position_open(
                token=signal["address"],
                entry_price=signal["entry_price"],
                quantity=qty_for_record,
                side="BUY",
                symbol=signal.get("symbol", ""),
            )

            log_qty = f"{buy_amount} SOL" if buy_in_sol else f"qty={signal['quantity']:.6f}"
            logger.info(f"✅ Posição aberta: {signal['symbol']} {log_qty} @ ${signal['entry_price']:.6f}")
            if self.alerter:
                try:
                    qty_alert = buy_amount if buy_in_sol else signal["quantity"]
                    await self.alerter.send_trade(
                        symbol=signal["symbol"],
                        side="BUY",
                        price=signal["entry_price"],
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
            success = await self.executor.sell(
                token_address=token,
                amount=pos["quantity"],
                denominated_in_sol=False,
                slippage=0,
            )
            if not success:
                logger.error(f"Falha ao vender {token}")
                return False

            # PnL para notificação (0 quando quantity="100%")
            if isinstance(quantity, (int, float)) and quantity > 0:
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

    async def _monitor_loop(self):
        """Loop que monitora preços (Jupiter + DexScreener fallback) e verifica SL/TP/timeout."""
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
                        await self.close_position(token, reason=exit_reason)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Erro no monitoramento: {e}", exc_info=True)

        logger.info("Monitoramento encerrado")