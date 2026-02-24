"""
Birdeye Scanner — Dados complementares (volume, liquidez, holders)
Usa endpoints oficiais da API Birdeye: /defi/token_overview e /defi/ohlcv
"""
import time
from typing import Dict, Any, Optional
import httpx

from app.core.config import settings
from app.core.logger import setup_logger

logger = setup_logger(__name__)


class BirdeyeScanner:
    """Busca dados detalhados de tokens via Birdeye API."""

    BASE_URL = "https://public-api.birdeye.so"
    CHAIN = "solana"  # Tokens Pump.fun são Solana

    def __init__(self):
        self.api_key = settings.BIRDEYE_API_KEY
        self.client = httpx.AsyncClient(timeout=10.0)

    def _headers(self) -> Dict[str, str]:
        """Headers obrigatórios para a API Birdeye (inclui x-chain)."""
        return {
            "X-API-KEY": self.api_key,
            "x-chain": self.CHAIN,
            "accept": "application/json",
        }

    async def get_token_info(self, token_address: str) -> Optional[Dict[str, Any]]:
        """Obtém informações de um token via /defi/token_overview (volume, liquidez, etc)."""
        if not self.api_key:
            logger.warning("BIRDEYE_API_KEY não configurada, pulando")
            return None

        try:
            url = f"{self.BASE_URL}/defi/token_overview"
            params = {"address": token_address}
            response = await self.client.get(url, headers=self._headers(), params=params)
            response.raise_for_status()
            data = response.json()

            # Resposta pode vir em data ou na raiz
            meta = data.get("data", data)
            if isinstance(meta, dict) and "data" in meta:
                meta = meta.get("data", meta)

            # Mapear campos da API Birdeye (token_overview)
            def _float(v, default=0.0):
                try:
                    return float(v) if v is not None else default
                except (TypeError, ValueError):
                    return default

            def _int(v, default=0):
                try:
                    return int(v) if v is not None else default
                except (TypeError, ValueError):
                    return default

            result = {
                "address": token_address,
                "symbol": meta.get("symbol"),
                "name": meta.get("name"),
                "market_cap": _float(meta.get("mc") or meta.get("market_cap") or meta.get("fdv")),
                "volume_24h": _float(meta.get("v24h") or meta.get("volume_24h") or meta.get("volume")),
                "liquidity_usd": _float(meta.get("liquidity") or meta.get("liquidity_usd")),
                "holders": _int(meta.get("holders")),
                "price_usd": _float(meta.get("price") or meta.get("price_usd")),
                "price_change_24h": _float(meta.get("priceChange24h") or meta.get("price_change_24h")),
                "description": meta.get("description"),
                "supply": _float(meta.get("supply") or meta.get("circulating_supply")),
            }
            logger.debug(f"Birdeye data for {result['symbol']}: vol=${result['volume_24h']:.2f}, liq=${result['liquidity_usd']:.2f}")
            return result

        except Exception as e:
            logger.error(f"Erro ao buscar token {token_address} no Birdeye: {e}")
            return None

    async def get_ohlcv(self, token_address: str, interval: str = "5m", limit: int = 50) -> Optional[Dict[str, Any]]:
        """Obtém dados OHLCV via /defi/ohlcv (type, time_from, time_to)."""
        if not self.api_key:
            return None

        try:
            # Mapear interval para type da API (1m, 5m, 1h, 1d)
            type_map = {"1m": "1m", "5m": "5m", "15m": "5m", "30m": "5m", "1h": "1h", "4h": "1h", "1d": "1d"}
            ohlcv_type = type_map.get(interval, "5m")

            # Calcular time_from e time_to (API usa timestamps em segundos)
            now = int(time.time())
            # 50 candles de 5m = 250 min; 1h = 60 min; 1d = 1440 min
            mins_per_candle = {"1m": 1, "5m": 5, "1h": 60, "1d": 1440}.get(ohlcv_type, 5)
            time_from = now - (limit * mins_per_candle * 60)

            url = f"{self.BASE_URL}/defi/ohlcv"
            params = {
                "address": token_address,
                "type": ohlcv_type,
                "time_from": time_from,
                "time_to": now,
            }
            response = await self.client.get(url, headers=self._headers(), params=params)
            response.raise_for_status()
            data = response.json()

            # Resposta Birdeye: data.items (lista de candles com unixTime, o, h, l, c, v)
            raw = data.get("data", {})
            if isinstance(raw, dict):
                ohlcv = raw.get("items", raw.get("data", []))
            else:
                ohlcv = raw if isinstance(raw, list) else []

            # Normalizar para formato esperado pelo pattern (close, high, low, timestamp, volume)
            def _norm_candle(c: dict) -> dict:
                return {
                    "open": float(c.get("o", c.get("open", 0))),
                    "high": float(c.get("h", c.get("high", 0))),
                    "low": float(c.get("l", c.get("low", 0))),
                    "close": float(c.get("c", c.get("close", 0))),
                    "volume": float(c.get("v", c.get("volume", 0))),
                    "timestamp": c.get("unixTime", c.get("timestamp", 0)),
                }
            ohlcv = [_norm_candle(c) for c in ohlcv if isinstance(c, dict)]
            logger.debug(f"OHLCV para {token_address}: {len(ohlcv)} candles")
            return {"address": token_address, "ohlcv": ohlcv}

        except Exception as e:
            logger.error(f"Erro ao buscar OHLCV de {token_address}: {e}")
            return None

    async def close(self):
        """Fecha cliente HTTP."""
        await self.client.aclose()