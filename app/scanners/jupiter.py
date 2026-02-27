"""
Jupiter Price API — Preço em tempo real (gratuito, sem API key)
Usado para: Manager SL/TP, preço do SOL (market cap USD)
Docs: https://dev.jup.ag/docs/api/price-api/v2
"""
import time
from typing import Optional
import httpx

from app.core.logger import setup_logger

logger = setup_logger(__name__)

JUPITER_PRICE_URL = "https://api.jup.ag/price/v2"
SOL_MINT = "So11111111111111111111111111111111111111112"
# Cache SOL price 5 min (evita chamadas desnecessárias)
SOL_PRICE_CACHE_SECONDS = 300
_sol_price_cache: tuple[float, float] = (0.0, 0.0)  # (price, timestamp)


async def get_price_usd(mint_address: str) -> Optional[float]:
    """
    Obtém preço em USD de um token via Jupiter Price API v2.
    Gratuito, sem API key, rápido.
    """
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(JUPITER_PRICE_URL, params={"ids": mint_address})
            if resp.status_code != 200:
                if resp.status_code == 401:
                    logger.warning("Jupiter 401 Unauthorized — fallback DexScreener será usado")
                else:
                    logger.debug(f"Jupiter price {resp.status_code} para {mint_address[:12]}...")
                return None
            data = resp.json()
            token_data = data.get("data", {}).get(mint_address)
            if not token_data:
                return None
            price_str = token_data.get("price")
            if price_str is None:
                return None
            return float(price_str)
    except Exception as e:
        logger.debug(f"Jupiter price erro {mint_address[:12]}...: {e}")
        return None


async def get_sol_price_usd() -> Optional[float]:
    """
    Obtém preço do SOL em USD. Cache de 5 min para economizar chamadas.
    """
    global _sol_price_cache
    now = time.monotonic()
    cached_price, cached_ts = _sol_price_cache
    if cached_price > 0 and (now - cached_ts) < SOL_PRICE_CACHE_SECONDS:
        return cached_price
    price = await get_price_usd(SOL_MINT)
    if price and price > 0:
        _sol_price_cache = (price, now)
    return price


class JupiterPriceFetcher:
    """
    Fetcher de preço via Jupiter. Interface compatível com BirdeyeScanner.get_token_info
    para o PositionManager (SL/TP).
    """

    async def get_token_info(self, token_address: str) -> Optional[dict]:
        """
        Retorna dict com price_usd para compatibilidade com o Manager.
        """
        price = await get_price_usd(token_address)
        if price is not None and price > 0:
            return {"price_usd": price}
        return None


class PriceFetcherWithFallback:
    """
    Jupiter primeiro; DexScreener como fallback quando Jupiter falha (401, rate limit, etc).
    Evita bot "cego" durante monitoramento SL/TP.
    """

    async def get_token_info(self, token_address: str) -> Optional[dict]:
        # 1) Tentar Jupiter
        try:
            price = await get_price_usd(token_address)
            if price is not None and price > 0:
                return {"price_usd": price}
        except Exception as e:
            logger.debug(f"Jupiter falhou para {token_address[:12]}..., fallback DexScreener: {e}")

        # 2) Fallback: DexScreener (gratuito, sem 401 nos logs)
        try:
            from app.scanners.dexscreener import get_token_info as dexscreener_info
            info = await dexscreener_info(token_address)
            if info and (info.get("price_usd") or 0) > 0:
                logger.debug(f"Preço via DexScreener (fallback) para {token_address[:12]}...")
                return {"price_usd": float(info["price_usd"])}
        except Exception as e:
            logger.debug(f"DexScreener fallback falhou: {e}")

        return None
