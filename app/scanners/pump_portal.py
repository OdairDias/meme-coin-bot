"""
PumpPortal Scanner — WebSocket para detectar novos tokens em tempo real
"""
import asyncio
import json
import time
import logging
from typing import Callable, Dict, Any, Optional
from datetime import datetime, timezone
import websockets

from app.core.config import settings
from app.core.logger import setup_logger

logger = setup_logger(__name__)


class PumpPortalScanner:
    """Escaneia novos tokens via WebSocket da PumpPortal"""

    # Dedupe: mesmo mint não dispara callback de novo por este tempo (segundos)
    DEDUPE_SECONDS = 60

    def __init__(self):
        self.websocket: websockets.WebSocketClientProtocol | None = None
        self.running = False
        self.callbacks: list[Callable[[Dict[str, Any]], None]] = []
        self._last_mint_seen: Dict[str, float] = {}  # mint -> timestamp
        self._last_token_received_at: float = time.time()
        self._alerter: Optional[Any] = None  # TelegramAlerter injetado do main

    def register_callback(self, callback: Callable[[Dict[str, Any]], None]):
        """Registra callback para receber novos tokens."""
        self.callbacks.append(callback)

    def set_alerter(self, alerter) -> None:
        """Injeta TelegramAlerter para enviar alertas de inatividade."""
        self._alerter = alerter

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

    async def _no_token_alert_loop(self) -> None:
        """Verifica periodicamente se nenhum token foi recebido e alerta via Telegram.
        NO_TOKEN_ALERT_SECONDS=0 desabilita completamente o alerta."""
        check_interval = 60  # checar a cada 60s
        while self.running:
            await asyncio.sleep(check_interval)
            threshold = getattr(settings, "NO_TOKEN_ALERT_SECONDS", 300)
            if threshold <= 0:
                continue
            elapsed = time.time() - self._last_token_received_at
            if elapsed > threshold and self._alerter:
                try:
                    await self._alerter.send_alert(
                        "warning",
                        f"Nenhum token novo em {int(elapsed)}s (limite={threshold}s). "
                        "Verificar conexão PumpPortal WebSocket.",
                    )
                except Exception as e:
                    logger.debug(f"Heartbeat alert: {e}")

    async def start(self):
        """Inicia o loop de recebimento de mensagens."""
        if self.running:
            logger.warning("Scanner já está rodando")
            return

        self.running = True
        logger.info("Iniciando PumpPortal Scanner...")
        # Inicia task de alerta de inatividade em background
        asyncio.create_task(self._no_token_alert_loop())
        _logged_structure = False

        # Reconectar automaticamente
        recv_timeout = 55
        while self.running:
            try:
                if not self.websocket or self.websocket.closed:
                    await self.connect()

                try:
                    message = await asyncio.wait_for(self.websocket.recv(), timeout=recv_timeout)
                except asyncio.TimeoutError:
                    logger.info("PumpPortal: aguardando mensagens (conexão ativa)")
                    continue

                try:
                    data = json.loads(message)
                except json.JSONDecodeError:
                    logger.debug("Mensagem não-JSON ignorada: %.80s", message[:80] if isinstance(message, str) else "<bytes>")
                    continue
                # API pode enviar payload dentro de data["message"] (string JSON)
                if "message" in data and "method" not in data and "result" not in data:
                    try:
                        inner = json.loads(data["message"]) if isinstance(data["message"], str) else data["message"]
                        data = inner
                    except (json.JSONDecodeError, TypeError):
                        logger.debug("PumpPortal: mensagem texto/ack recebida (keys=%s)", list(data.keys()))
                        continue
                method = data.get("method", "") or data.get("type", "") or data.get("event", "")
                logger.debug("PumpPortal: method=%s keys=%s", method or "(vazio)", list(data.keys()))

                # Formato 1: createEventNotification (API atual PumpPortal) — dados em "result"
                if method == "createEventNotification":
                    raw = data.get("result") or {}
                    if not isinstance(raw, dict):
                        logger.debug("createEventNotification com result inválido: %s", type(raw).__name__)
                        continue
                    token_data = self._normalize_create_event(raw)
                    symbol = token_data.get("symbol", "?")
                    logger.info("📥 Novo token do mercado: %s (mint=%s)", symbol, (token_data.get("mint") or "")[:12] + "...")
                    await self._handle_new_token(token_data)
                    continue

                # Formato 2: newToken (legado) — dados em "data"
                if method == "newToken":
                    token_data = data.get("data", {})
                    symbol = token_data.get("symbol", "?")
                    market_cap = float(token_data.get("market_cap", 0))
                    logger.info("📥 Novo token do mercado: %s (market_cap=%.0f)", symbol, market_cap)
                    await self._handle_new_token(token_data)
                    continue

                # Formato 3: objeto direto sem "method" (mint, symbol, marketCapSol, etc.)
                # Variante 3a: keys padrão (bondingCurveKey, vTokensInBondingCurve, is_mayhem_mode, ...)
                # Variante 3b: keys alternativas (tokensInPool, newTokenBalance, sem bondingCurveKey)
                # Ambas são normalizadas por _normalize_raw_token — lê apenas campos comuns.
                if not method and isinstance(data, dict) and data.get("mint"):
                    mint = data.get("mint", "")
                    now = asyncio.get_event_loop().time()
                    if len(self._last_mint_seen) > 5000:
                        self._last_mint_seen = {k: v for k, v in self._last_mint_seen.items() if now - v < 300}
                    if mint and (mint not in self._last_mint_seen or (now - self._last_mint_seen[mint]) > self.DEDUPE_SECONDS):
                        self._last_mint_seen[mint] = now
                        token_data = self._normalize_raw_token(data)
                        symbol = token_data.get("symbol", "?")
                        market_cap = token_data.get("market_cap") or 0
                        logger.info("📥 Novo token do mercado: %s (mint=%s marketCapSol=%s)", symbol, (mint or "")[:12] + "...", market_cap)
                        await self._handle_new_token(token_data)

            except websockets.exceptions.ConnectionClosed:
                logger.warning("WebSocket fechado, reconectando em 5s...")
                await asyncio.sleep(5)
            except Exception as e:
                logger.exception("Erro no scanner PumpPortal: %s", e)
                await asyncio.sleep(5)

    def _normalize_create_event(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """Converte payload createEventNotification (result) para formato interno."""
        meta = result.get("metadata", {})
        creator = result.get("creator_wallet") or {}
        addr = creator.get("address", "") if isinstance(creator, dict) else ""
        return {
            "mint": result.get("mint"),
            "symbol": result.get("symbol", "UNKNOWN"),
            "name": result.get("name", "Unknown"),
            "market_cap": 0,  # evento não traz; estratégia/DexScreener podem preencher
            "volume_24h": 0,
            "holders": 0,
            "dev_holding_percent": 0,
            "snipers": 0,
            "created_at": result.get("timestamp", ""),
            "bondingCurve": result.get("bondingCurve"),
            "associatedBondingCurve": result.get("associatedBondingCurve"),
            "creator_address": addr,
            "raw": result,
        }

    def _normalize_raw_token(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Converte payload direto (mint, symbol, marketCapSol, ...) para formato interno."""
        market_cap_sol = data.get("marketCapSol")
        if market_cap_sol is not None:
            try:
                market_cap = float(market_cap_sol)
            except (TypeError, ValueError):
                market_cap = 0
        else:
            market_cap = float(data.get("market_cap", 0))
        return {
            "mint": data.get("mint"),
            "symbol": data.get("symbol", "UNKNOWN"),
            "name": data.get("name", "Unknown"),
            "market_cap": market_cap,
            "volume_24h": float(data.get("volume_24h", 0)),
            "holders": int(data.get("holders", 0)),
            "dev_holding_percent": float(data.get("dev_holding_percent", 0)),
            "snipers": data.get("snipers_count", data.get("snipers", 0)),
            "created_at": data.get("created_at", datetime.now(timezone.utc).isoformat()),
            "pool": (data.get("pool") or "").strip().lower(),
            "raw": data,
        }

    async def _handle_new_token(self, token_data: Dict[str, Any]):
        """Processa dados de um novo token e dispara callbacks."""
        self._last_token_received_at = time.time()
        # Normalizar dados
        pool = (token_data.get("pool") or "").strip().lower()
        on_bonding_curve = pool != "raydium"
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
            "pool": pool,
            "on_bonding_curve": on_bonding_curve,
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