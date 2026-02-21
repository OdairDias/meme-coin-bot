"""
DexScreener Scanner — Fonte alternativa de dados de tokens
"""
import asyncio
import logging
from typing import Dict, Any, Optional
import httpx

from app.core.logger import setup_logger

logger = setup_logger(__name__)


class DexScreenerScanner:
    """Busca dados de tokens via DexScreener API."""

    BASE_URL = "https://api.dexscreener.com/latest/dex"

    def __init__(self):
        self.client = httpx.AsyncClient(timeout=10.0)

    async def search_token(self, token_address: str) -> Optional[Dict[str, Any]]:
        """Busca token por contrato."""
        try:
            # DexScreener usa pair address, mas podemos buscar pelo token address
            url = f"{self.BASE_URL}/tokens?address={token_address}"
            response = await self.client.get(url)
            response.raise_for_status()
            data = response.json()

            pairs = data.get("pairs", [])
            if not pairs:
                logger.debug(f"Token {token_address} não encontrado no DexScreener")
                return None

            # Pegar o par com maior liquidez
            main_pair = max(pairs, key=lambda x: float(x.get("liquidity", {}).get("usd", 0)))

            result = {
                "address": token_address,
                "symbol": main_pair.get("baseToken", {}).get("symbol"),
                "price_usd": float(main_pair.get("priceUsd", 0)),
                "volume_24h": float(main_pair.get("volume24h", 0)),
                "liquidity_usd": float(main_pair.get("liquidity", {}).get("usd", 0)),
                "fdv": float(main_pair.get("fdv", 0)),
                "pair_address": main_pair.get("pairAddress"),
                "dex": main_pair.get("dexId"),
                "created_at": main_pair.get("createdAt"),
            }
            logger.debug(f"DexScreener {result['symbol']}: price=${result['price_usd']:.6f}, liq=${result['liquidity_usd']:.2f}")
            return result

        except Exception as e:
            logger.error(f"Erro ao buscar token {token_address} no DexScreener: {e}")
            return None

    async def get_ohlcv(self, pair_address: str, interval: str = "5m", limit: int = 50) -> Optional[Dict[str, Any]]:
        """Obtém OHLCV de um par."""
        try:
            # DexScreener não tem endpoint público de OHLCV sem autenticação
            # Usar outra fonte (Birdeye) para isso
            logger.debug("DexScreener não fornece OHLCV público, use Birdeye")
            return None
        except Exception as e:
            logger.error(f"Erro ao buscar OHLCV de {pair_address}: {e}")
            return None

    async def close(self):
        """Fecha cliente HTTP."""
        await self.client.aclose()