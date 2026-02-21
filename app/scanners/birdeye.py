"""
Birdeye Scanner — Dados complementares (volume, liquidez, holders)
"""
import asyncio
import logging
from typing import Dict, Any, Optional
import httpx

from app.core.config import settings
from app.core.logger import setup_logger

logger = setup_logger(__name__)


class BirdeyeScanner:
    """Busca dados detalhados de tokens via Birdeye API."""

    BASE_URL = "https://public-api.birdeye.so"

    def __init__(self):
        self.api_key = settings.BIRDEYE_API_KEY
        self.client = httpx.AsyncClient(timeout=10.0)

    async def get_token_info(self, token_address: str) -> Optional[Dict[str, Any]]:
        """Obtém informações de um token (volume, liquidez, holders)."""
        if not self.api_key:
            logger.warning("BIRDEYE_API_KEY não configurada, pulando")
            return None

        try:
            headers = {"X-API-KEY": self.api_key}
            url = f"{self.BASE_URL}/v1/token/meta?address={token_address}"
            response = await self.client.get(url, headers=headers)
            response.raise_for_status()
            data = response.json()

            # Extrair dados relevantes
            meta = data.get("data", {})
            result = {
                "address": token_address,
                "symbol": meta.get("symbol"),
                "name": meta.get("name"),
                "market_cap": float(meta.get("market_cap", 0)),
                "volume_24h": float(meta.get("volume_24h", 0)),
                "liquidity_usd": float(meta.get("liquidity_usd", 0)),
                "holders": int(meta.get("holders", 0)),
                "price_usd": float(meta.get("price_usd", 0)),
                "price_change_24h": float(meta.get("price_change_24h", 0)),
                "description": meta.get("description"),
                "supply": float(meta.get("supply", 0)),
            }
            logger.debug(f"Birdeye data for {result['symbol']}: vol=${result['volume_24h']:.2f}, liq=${result['liquidity_usd']:.2f}")
            return result

        except Exception as e:
            logger.error(f"Erro ao buscar token {token_address} no Birdeye: {e}")
            return None

    async def get_ohlcv(self, token_address: str, interval: str = "5m", limit: int = 50) -> Optional[Dict[str, Any]]:
        """Obtém dados OHLCV para análise de padrão."""
        if not self.api_key:
            return None

        try:
            headers = {"X-API-KEY": self.api_key}
            # Birdeye endpoint para OHLCV (se disponível)
            url = f"{self.BASE_URL}/v1/ohlcv?address={token_address}&interval={interval}&limit={limit}"
            response = await self.client.get(url, headers=headers)
            response.raise_for_status()
            data = response.json()

            ohlcv = data.get("data", [])
            logger.debug(f"OHLCV para {token_address}: {len(ohlcv)} candles")
            return {"address": token_address, "ohlcv": ohlcv}

        except Exception as e:
            logger.error(f"Erro ao buscar OHLCV de {token_address}: {e}")
            return None

    async def close(self):
        """Fecha cliente HTTP."""
        await self.client.aclose()