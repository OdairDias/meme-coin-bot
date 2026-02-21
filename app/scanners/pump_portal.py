"""
PumpPortal Scanner — WebSocket para detectar novos tokens em tempo real
"""
import asyncio
import json
import logging
from typing import Callable, Dict, Any
from datetime import datetime, timezone
import websockets

from app.core.config import settings
from app.core.logger import setup_logger

logger = setup_logger(__name__)


class PumpPortalScanner:
    """Escaneia novos tokens via WebSocket da PumpPortal"""

    def __init__(self):
        self.websocket: websockets.WebSocketClientProtocol | None = None
        self.running = False
        self.callbacks: list[Callable[[Dict[str, Any]], None]] = []

    def register_callback(self, callback: Callable[[Dict[str, Any]], None]):
        """Registra callback para receber novos tokens."""
        self.callbacks.append(callback)

    async def connect(self):
        """Conecta ao WebSocket da PumpPortal."""
        try:
            self.websocket = await websockets.connect(settings.PUMP_PORTAL_WS)
            logger.info("Conectado ao PumpPortal WebSocket")

            # Inscrever para novos tokens
            subscribe_msg = {
                "method": "subscribeNewToken"
            }
            await self.websocket.send(json.dumps(subscribe_msg))
            logger.info("Inscrito em novos tokens")

        except Exception as e:
            logger.error(f"Erro ao conectar ao PumpPortal: {e}")
            raise

    async def start(self):
        """Inicia o loop de recebimento de mensagens."""
        if self.running:
            logger.warning("Scanner já está rodando")
            return

        self.running = True
        logger.info("Iniciando PumpPortal Scanner...")

        # Reconectar automaticamente
        while self.running:
            try:
                if not self.websocket or self.websocket.closed:
                    await self.connect()

                message = await self.websocket.recv()
                data = json.loads(message)
                method = data.get("method", "")
                logger.debug("Mensagem PumpPortal: method=%s", method)

                # Processar mensagem
                if method == "newToken":
                    token_data = data.get("data", {})
                    symbol = token_data.get("symbol", "?")
                    market_cap = float(token_data.get("market_cap", 0))
                    logger.info("📥 Novo token do mercado: %s (market_cap=%.0f)", symbol, market_cap)
                    logger.debug("Payload newToken: %s", token_data)
                    await self._handle_new_token(token_data)

            except websockets.exceptions.ConnectionClosed:
                logger.warning("WebSocket fechado, reconectando em 5s...")
                await asyncio.sleep(5)
            except Exception as e:
                logger.error(f"Erro no scanner: {e}")
                await asyncio.sleep(5)

    async def _handle_new_token(self, token_data: Dict[str, Any]):
        """Processa dados de um novo token e dispara callbacks."""
        # Normalizar dados
        normalized = {
            "address": token_data.get("mint"),  # contract address
            "symbol": token_data.get("symbol", "UNKNOWN"),
            "name": token_data.get("name", "Unknown"),
            "market_cap": float(token_data.get("market_cap", 0)),
            "volume_24h": float(token_data.get("volume_24h", 0)),
            "holders": int(token_data.get("holders", 0)),
            "dev_holding_percent": float(token_data.get("dev_holding_percent", 0)),
            "snipers_count": int(token_data.get("snipers", 0)),
            "created_at": token_data.get("created_at", datetime.now(timezone.utc).isoformat()),
            "raw": token_data
        }

        # Disparar callbacks
        for callback in self.callbacks:
            try:
                await callback(normalized)
            except Exception as e:
                logger.error(f"Erro em callback do scanner: {e}")

    async def stop(self):
        """Para o scanner."""
        self.running = False
        if self.websocket:
            await self.websocket.close()
        logger.info("Scanner parado")