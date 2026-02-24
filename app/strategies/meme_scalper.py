"""
Estratégia principal de scalper para memecoins
"""
import asyncio
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone, timedelta

from app.core.config import settings
from app.core.logger import setup_logger
from app.strategies.filters import apply_initial_filters
from app.strategies.pattern import detect_stairs_pattern
from app.scanners.birdeye import BirdeyeScanner

logger = setup_logger(__name__)


class MemeScalperStrategy:
    """Estratégia de scalping para memecoins na Pump.fun."""

    def __init__(self, birdeye: BirdeyeScanner):
        self.birdeye = birdeye
        self.logger = logger
        self._recent_tokens: Dict[str, datetime] = {}  # cache de tokens vistos

    async def scan_assets(self) -> List[Dict[str, Any]]:
        """
        Escaneia candidatos — aqui usamos o PumpPortal que chama analyze_token diretamente.
        Este método é mais para compatibilidade, mas o work principal é via callbacks.
        """
        return []

    async def generate_signals(self, assets: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Gera sinais a partir de assets pré-filtrados."""
        signals = []

        for asset in assets:
            token_address = asset.get("address") or asset.get("mint")
            if not token_address:
                continue

            # 1) Filtros iniciais (regras afrouxadas; volume/liquidez 0 deixam passar)
            passed, reason = apply_initial_filters(asset)
            if not passed:
                logger.debug(f"Token {asset.get('symbol')} rejeitado: {reason}")
                continue

            # 2) Buscar OHLCV primeiro (1 chamada Birdeye) — reduz 429
            ohlcv_data = await self.birdeye.get_ohlcv(token_address, interval="5m", limit=50)
            if not ohlcv_data or not ohlcv_data.get("ohlcv"):
                logger.debug(f"Sem OHLCV para {token_address}")
                continue

            ohlcv = ohlcv_data["ohlcv"]

            # 3) Detectar padrão escadinha (min_steps=2 aceita mais candidatos)
            detected, pattern_meta = detect_stairs_pattern(ohlcv, min_steps=2)
            if not detected:
                continue

            # 4) Só agora enriquecer com token_overview (volume/holders para score) — evita chamadas desnecessárias
            try:
                info = await self.birdeye.get_token_info(token_address)
                if info:
                    asset["volume_24h"] = info.get("volume_24h") or asset.get("volume_24h", 0)
                    asset["liquidity_usd"] = info.get("liquidity_usd") or asset.get("liquidity_usd", 0)
                    asset["holders"] = info.get("holders") if info.get("holders") is not None else asset.get("holders", 0)
                    asset["price_usd"] = info.get("price_usd") or asset.get("price_usd")
                    asset["market_cap"] = info.get("market_cap") or asset.get("market_cap")
            except Exception:
                pass

            # 5) Calcular score simples (pode ser melhorado depois)
            score = self._calculate_score(asset, pattern_meta)

            if score < 55:  # threshold afrouxado (era 70) para gerar mais sinais
                continue

            # 6) Calcular preços (entry, SL, TP)
            current_price = asset.get("price_usd") or pattern_meta["last_price"]
            if not current_price or current_price <= 0:
                continue

            # Position size em USD → quantidade de tokens
            position_size_usd = min(settings.MAX_POSITION_SIZE_USD, 2.0)  # max $2
            quantity = position_size_usd / current_price

            # Stop loss
            stop_price = current_price * (1 - settings.STOP_LOSS_PERCENT / 100)

            # Take profits
            tp1_price = current_price * (1 + settings.TAKE_PROFIT_PERCENT1 / 100)
            tp2_price = current_price * (1 + settings.TAKE_PROFIT_PERCENT2 / 100)

            signal = {
                "symbol": asset["symbol"],
                "address": token_address,
                "side": "BUY",
                "entry_price": current_price,
                "quantity": quantity,
                "stop_loss": stop_price,
                "take_profit_1": tp1_price,
                "take_profit_2": tp2_price,
                "tp1_percent": settings.TAKE_PROFIT_PERCENT1,
                "tp2_percent": settings.TAKE_PROFIT_PERCENT2,
                "score": score,
                "strategy": "meme_scalper",
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "expires_at": (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat(),
                "metadata": {
                    "market_cap": asset.get("market_cap"),
                    "volume_24h": asset.get("volume_24h"),
                    "holders": asset.get("holders"),
                    "pattern": pattern_meta
                }
            }

            signals.append(signal)
            self.logger.info(f"📈 Sinal gerado: {asset['symbol']} score={score:.0f} preço=${current_price:.6f}")

        return signals

    def _calculate_score(self, asset: Dict[str, Any], pattern_meta: Dict[str, Any]) -> float:
        """Calcula score 0-100 para o token."""
        score = 0.0

        # Volume (máx 30 pts)
        volume = asset.get("volume_24h", 0)
        if volume > 10000:
            score += 30
        elif volume > 5000:
            score += 20
        elif volume > 1000:
            score += 10
        else:
            score += 5

        # Holders (máx 20 pts)
        holders = asset.get("holders", 0)
        if holders > 20:
            score += 20
        elif holders > 10:
            score += 15
        elif holders > 5:
            score += 10
        else:
            score += 5

        # Liquidez (máx 20 pts)
        liquidity = asset.get("liquidity_usd", 0)
        if liquidity > 20000:
            score += 20
        elif liquidity > 10000:
            score += 15
        elif liquidity > 5000:
            score += 10
        else:
            score += 5

        # Padrão escadinha (máx 30 pts)
        step_percent = pattern_meta.get("step_percent", 0)
        if step_percent > 10:
            score += 30
        elif step_percent > 5:
            score += 20
        else:
            score += 10

        return min(score, 100.0)