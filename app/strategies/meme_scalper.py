"""
Estratégia principal de scalper para memecoins
OHLCV: CandleBuilder (tempo real, Fase 1) > Bitquery (primário) > Birdeye (fallback).
Preço SOL: Jupiter. Volume/liquidez: DexScreener. Filtro de risco: RugCheck (Fase 1).
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
from app.scanners.jupiter import get_sol_price_usd
from app.scanners import dexscreener

logger = setup_logger(__name__)


class MemeScalperStrategy:
    """Estratégia de scalping para memecoins na Pump.fun."""

    def __init__(self, birdeye: BirdeyeScanner):
        self.birdeye = birdeye
        self.logger = logger
        self._recent_tokens: Dict[str, datetime] = {}  # cache de tokens vistos
        self._sol_price_cache: float = 0.0

    async def scan_assets(self) -> List[Dict[str, Any]]:
        """
        Escaneia candidatos — aqui usamos o PumpPortal que chama analyze_token diretamente.
        Este método é mais para compatibilidade, mas o work principal é via callbacks.
        """
        return []

    async def generate_signals(
        self,
        assets: List[Dict[str, Any]],
        prebuilt_ohlcv: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Gera sinais a partir de assets pré-filtrados.
        prebuilt_ohlcv: candles já construídos pelo CandleBuilder (Fase 1).
                        Quando fornecido, pula a chamada ao Bitquery/Birdeye.
        """
        signals = []

        for asset in assets:
            token_address = asset.get("address") or asset.get("mint")
            if not token_address:
                continue

            # 1) Filtros iniciais (regras afrouxadas; volume/liquidez 0 deixam passar)
            passed, reason = apply_initial_filters(asset)
            if not passed:
                logger.info(f"❌ {asset.get('symbol')} rejeitado (filtro): {reason}")
                continue

            # 1b) RugCheck: verifica score de risco antes de consumir quota do Bitquery
            if getattr(settings, "RUGCHECK_ENABLED", False):
                try:
                    from app.scanners.rugcheck import check_token
                    rc_pass, rc_score, rc_reason = await check_token(token_address)
                    if not rc_pass:
                        logger.info(f"❌ {asset.get('symbol')} rejeitado (RugCheck): {rc_reason}")
                        continue
                    if rc_score > 0:
                        logger.debug(f"RugCheck {asset.get('symbol')}: score={rc_score} OK")
                except Exception as e:
                    logger.debug(f"RugCheck erro (ignorado): {e}")

            # 2) OHLCV: usar candles pré-construídos (CandleBuilder) ou buscar Bitquery/Birdeye
            if prebuilt_ohlcv and prebuilt_ohlcv.get("ohlcv"):
                ohlcv_data = prebuilt_ohlcv
                logger.info(f"📊 Usando candles em tempo real para {asset.get('symbol')} ({len(prebuilt_ohlcv['ohlcv'])} candles)")
            else:
                ohlcv_data = await self.birdeye.get_ohlcv(token_address, interval="1m", limit=10)
            if not ohlcv_data or not ohlcv_data.get("ohlcv"):
                logger.info(f"❌ {asset.get('symbol')} rejeitado: sem OHLCV")
                continue

            ohlcv = ohlcv_data["ohlcv"]

            # 3) Detectar padrão escadinha (min_steps via config, default 1)
            detected, pattern_meta = detect_stairs_pattern(ohlcv)
            if not detected:
                reason = pattern_meta.get("reason", "padrão não detectado")
                logger.info(f"❌ {asset.get('symbol')} rejeitado (pattern): {reason} ({len(ohlcv)} candles)")
                continue

            # 4) Enriquecer para score: marketCapSol*SOL, volume do OHLCV, DexScreener (fallback)
            sol_price = await get_sol_price_usd()
            if sol_price and sol_price > 0:
                self._sol_price_cache = sol_price
            else:
                sol_price = self._sol_price_cache or 1.0  # fallback conservador

            # Market cap USD = marketCapSol (PumpPortal) * preço SOL
            market_cap_sol = asset.get("market_cap", 0) or 0
            if market_cap_sol > 0:
                asset["market_cap"] = market_cap_sol * sol_price

            # Volume USD: soma dos candles (volume*close em SOL) * sol_price
            volume_sol = sum(
                (c.get("volume", 0) or 0) * (c.get("close", 0) or c.get("high", 0) or 0)
                for c in ohlcv
            )
            volume_usd = volume_sol * sol_price
            if volume_usd > 0:
                asset["volume_24h"] = volume_usd

            # DexScreener: SEMPRE busca para obter o preço atual de mercado.
            # O preço do OHLCV (last_price) pode ser de minutos atrás — para tokens que já
            # subiram muito durante o delay de indexação, usar preço stale como entry causa
            # ganhos/perdas fantasmas (ex: +8198% reportado mas gain real de 3%).
            try:
                info = await dexscreener.get_token_info(token_address)
                if info:
                    # Preço atual: DexScreener é a fonte mais confiável para entry
                    dex_price = info.get("price_usd") or 0
                    if dex_price > 0:
                        asset["price_usd"] = dex_price
                    asset["volume_24h"] = info.get("volume_24h") or asset.get("volume_24h", 0)
                    asset["liquidity_usd"] = info.get("liquidity_usd") or asset.get("liquidity_usd", 0)
                    if info.get("market_cap"):
                        asset["market_cap"] = info.get("market_cap")
            except Exception:
                pass

            # Fallback: OHLCV last_price * sol_price (caso DexScreener não tenha o token ainda)
            last_price_sol = pattern_meta.get("last_price", 0) or 0
            if last_price_sol > 0 and not asset.get("price_usd"):
                asset["price_usd"] = last_price_sol * sol_price
            # holders: manter do asset (PumpPortal) ou 0

            # 5) Calcular score simples (pode ser melhorado depois)
            score = self._calculate_score(asset, pattern_meta)

            min_score = getattr(settings, "MIN_SCORE", 50.0)
            if score < min_score:
                logger.info(f"❌ {asset.get('symbol')} rejeitado (score): {score:.0f} < {min_score:.0f}")
                continue

            # 6) Calcular preços (entry, SL, TP) — sempre em USD
            current_price = asset.get("price_usd")
            if not current_price or current_price <= 0:
                current_price = (pattern_meta.get("last_price", 0) or 0) * sol_price
            if not current_price or current_price <= 0:
                logger.info(f"❌ {asset.get('symbol')} rejeitado: preço inválido")
                continue

            # Position size: prioridade SOL (evita erro de conversão USD→tokens)
            buy_amount_sol = getattr(settings, "MAX_POSITION_SIZE_SOL", 0) or 0
            if buy_amount_sol > 0:
                quantity = 0  # não usado quando buy_in_sol=True
                buy_in_sol = True
            else:
                position_size_usd = min(settings.MAX_POSITION_SIZE_USD, 2.0)
                quantity = position_size_usd / current_price
                buy_amount_sol = 0
                buy_in_sol = False

            # Stop loss e Take profits: usar preço ORIGINAL do sinal (não conservador)
            # O slippage já está factored no preço de entrada real do trade
            # As % de SL/TP são aplicadas sobre o preço do sinal, garantindo % real
            # Exemplo: SL 30% = preço cai 30% do entry, independente do slippage
            
            # Stop loss: 30% de queda do preço do sinal
            stop_price = current_price * (1 - settings.STOP_LOSS_PERCENT / 100)
            
            # Take profits: % de subida do preço do sinal
            tp1_price = current_price * (1 + settings.TAKE_PROFIT_PERCENT1 / 100)
            tp2_price = current_price * (1 + settings.TAKE_PROFIT_PERCENT2 / 100)

            signal = {
                "symbol": asset["symbol"],
                "address": token_address,
                "side": "BUY",
                "entry_price": current_price,
                "quantity": quantity,
                "buy_amount_sol": buy_amount_sol,
                "buy_in_sol": buy_in_sol,
                "stop_loss": stop_price,
                "take_profit_1": tp1_price,
                "take_profit_2": tp2_price,
                "tp1_percent": settings.TAKE_PROFIT_PERCENT1,
                "tp2_percent": settings.TAKE_PROFIT_PERCENT2,
                "score": score,
                "strategy": "meme_scalper",
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "expires_at": (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat(),
                "pool": "raydium" if asset.get("on_bonding_curve") is False else "auto",
                "liquidity_usd": asset.get("liquidity_usd", 0),
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