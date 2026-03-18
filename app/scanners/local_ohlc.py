"""Fallback local de OHLC para tokens sem candles oficiais."""
from __future__ import annotations

import asyncio
import time
from typing import Dict, Any, List, Optional

from app.core.config import settings
from app.core.logger import setup_logger
from app.scanners.dexscreener import get_token_info

logger = setup_logger(__name__)


class LocalOhlcBuilder:
    """Constrói candles simples usando DexScreener ou estimativas internas."""

    def __init__(self) -> None:
        self.enabled = settings.USE_LOCAL_OHLC_FALLBACK
        self.candle_interval = settings.LOCAL_OHLC_CANDLE_INTERVAL_SECONDS
        self.candle_count = settings.LOCAL_OHLC_CANDLES
        self.lock = asyncio.Lock()

    async def build(self, token_address: str, hint_price: float | None = None) -> Optional[Dict[str, Any]]:
        """Gera OHLCV com base no preço atual e na janela configurada."""
        if not self.enabled:
            return None

        async with self.lock:
            info = await get_token_info(token_address)
            price = hint_price or (info and info.get("price_usd"))
            if not price or price <= 0:
                logger.debug("Local OHLC fallback sem preço válido", token=token_address[:12])
                return None

            volume_24h = (info or {}).get("volume_24h") or 0.0
            per_candle_volume = (volume_24h / max(self.candle_count, 1)) if volume_24h else 0.0
            now = int(time.time())
            candles: List[Dict[str, Any]] = []
            for i in range(self.candle_count):
                ts = now - (self.candle_count - 1 - i) * self.candle_interval
                candles.append(
                    {
                        "open": price,
                        "high": price,
                        "low": price,
                        "close": price,
                        "volume": per_candle_volume,
                        "timestamp": ts,
                    }
                )

            logger.info(
                "Local OHLC fallback gerado",
                token=token_address[:12],
                candles=len(candles),
                price=price,
            )
            return {"address": token_address, "ohlcv": candles}


local_ohlc_builder = LocalOhlcBuilder()
