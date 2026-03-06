"""
CandleBuilder — Constrói OHLCV em tempo real via polling de preço (DexScreener).
Substitui o sleep(BIRDEYE_DELAY_SECONDS) + Bitquery/Birdeye como fonte de candles.

Configuração padrão (30s candles, 180s timeout):
  - Poll DexScreener a cada 5s → 6 data points por candle de 30s
  - 180s timeout → 6 candles → escadinha completa (6+ candles no pattern.py)
  - Fallback para Bitquery/Birdeye se dados insuficientes

Vantagem vs Bitquery 1m:
  - Coleta desde t=0 (sem delay de indexação de 60-300s)
  - 6 candles de 30s vs 3 candles de 1m no mesmo intervalo → mais resolução
  - Sem dependência de API paga (Bitquery) → usa DexScreener (grátis)
"""
import asyncio
import time
from typing import Optional, Dict, Any, List

from app.core.config import settings
from app.core.logger import setup_logger

logger = setup_logger(__name__)

# Intervalo entre polls de preço (s) — 5s evita rate limit no DexScreener.
# Com candles de 30s: 30/5 = 6 data points por candle (resolução suficiente para OHLC).
_POLL_INTERVAL_SECONDS = 5


class CandleBuilder:
    """Constrói candles OHLCV de forma síncrona via polling de preço."""

    async def build_candles(self, token_address: str) -> Optional[Dict[str, Any]]:
        """
        Faz polling de preço durante CANDLE_BUILD_TIMEOUT_SECONDS e constrói candles OHLCV.
        Cada candle cobre CANDLE_TIMEFRAME_SECONDS de dados.
        Retorna {"address": ..., "ohlcv": [...]} ou None se dados insuficientes.
        """
        from app.scanners import dexscreener

        timeout = getattr(settings, "CANDLE_BUILD_TIMEOUT_SECONDS", 90)
        timeframe = getattr(settings, "CANDLE_TIMEFRAME_SECONDS", 15)
        min_candles = getattr(settings, "MIN_CANDLES", 3)

        prices: List[tuple] = []  # (timestamp, price)
        deadline = time.monotonic() + timeout

        logger.info(
            f"📊 CandleBuilder: coletando preços de {token_address[:12]}... por {timeout}s "
            f"(candles de {timeframe}s)"
        )

        while time.monotonic() < deadline:
            try:
                info = await dexscreener.get_token_info(token_address)
                price = float(info.get("price_usd") or 0) if info else 0.0
                if price > 0:
                    ts = time.time()
                    prices.append((ts, price))
                    if len(prices) == 1:
                        logger.info(
                            f"📊 Primeiro preço coletado: ${price:.8f} ({token_address[:12]})"
                        )
            except Exception as e:
                logger.debug(f"CandleBuilder poll {token_address[:12]}: {e}")

            await asyncio.sleep(_POLL_INTERVAL_SECONDS)

        if not prices:
            logger.warning(f"CandleBuilder: nenhum preço obtido para {token_address[:12]}")
            return None

        ohlcv = self._build_ohlcv(prices, timeframe)
        n = len(ohlcv)
        if n < min_candles:
            logger.warning(
                f"CandleBuilder: {n} candle(s) insuficientes (min={min_candles}) — "
                f"fallback para Bitquery/Birdeye"
            )
            return None

        logger.info(
            f"📊 CandleBuilder: {n} candles prontos para {token_address[:12]} "
            f"(preço final: ${prices[-1][1]:.8f})"
        )
        return {"address": token_address, "ohlcv": ohlcv}

    def _build_ohlcv(self, prices: List[tuple], timeframe: int) -> List[Dict[str, Any]]:
        """Agrupa leituras de preço em candles de `timeframe` segundos."""
        if not prices:
            return []

        candles: List[Dict[str, Any]] = []
        candle_start = prices[0][0]
        bucket: List[float] = []

        for ts, price in prices:
            if ts >= candle_start + timeframe:
                if bucket:
                    candles.append(self._make_candle(candle_start, bucket))
                candle_start = ts
                bucket = [price]
            else:
                bucket.append(price)

        # Candle final (pode estar incompleto mas é válido como último dado)
        if bucket:
            candles.append(self._make_candle(candle_start, bucket))

        return candles

    @staticmethod
    def _make_candle(ts: float, bucket: List[float]) -> Dict[str, Any]:
        return {
            "open": bucket[0],
            "high": max(bucket),
            "low": min(bucket),
            "close": bucket[-1],
            "volume": 0.0,  # volume não disponível por polling de preço
            "timestamp": int(ts),
        }
