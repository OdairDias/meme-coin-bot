"""
DexScreener API — Volume, liquidez, FDV (gratuito, sem API key)
Endpoint: https://api.dexscreener.com/latest/dex/tokens/{mint}
"""
from typing import Dict, Any, Optional
import httpx

from app.core.logger import setup_logger

logger = setup_logger(__name__)

DEXSCREENER_URL = "https://api.dexscreener.com/latest/dex/tokens"


async def get_token_info(mint_address: str) -> Optional[Dict[str, Any]]:
    """
    Obtém volume, liquidez, FDV e preço de um token.
    Retorna None se falhar ou token não listado.
    """
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.get(f"{DEXSCREENER_URL}/{mint_address}")
            if resp.status_code != 200:
                logger.debug(f"DexScreener {resp.status_code} para {mint_address[:12]}...")
                return None
            data = resp.json()
            pairs = data.get("pairs", [])
            if not pairs:
                return None
            # Pegar o par com maior liquidez (geralmente Pump/Raydium)
            def _liq_usd(p):
                liq = p.get("liquidity") or {}
                if isinstance(liq, dict):
                    return _float(liq.get("usd"))
                return 0.0

            best = max(pairs, key=_liq_usd)
            liq = best.get("liquidity", {}) or {}
            vol = best.get("volume") or {}
            vol_h24 = vol.get("h24") if isinstance(vol, dict) else (vol if isinstance(vol, (int, float)) else 0)
            return {
                "address": mint_address,
                "price_usd": _float(best.get("priceUsd")),
                "volume_24h": _float(vol_h24),
                "liquidity_usd": _float(liq.get("usd") if isinstance(liq, dict) else 0),
                "market_cap": _float(best.get("fdv") or best.get("marketCap")),
                "holders": 0,  # DexScreener não traz holders
            }
    except Exception as e:
        logger.debug(f"DexScreener erro {mint_address[:12]}...: {e}")
        return None


def _float(v, default: float = 0.0) -> float:
    try:
        return float(v) if v is not None else default
    except (TypeError, ValueError):
        return default
