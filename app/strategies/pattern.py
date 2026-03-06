"""
Detecção de padrão "escadinha" (higher highs e higher lows) em OHLCV
"""
from typing import List, Dict, Any
import numpy as np
from datetime import datetime, timezone

from app.core.config import settings


def detect_stairs_pattern(ohlcv: List[Dict[str, Any]], min_steps: int | None = None) -> tuple[bool, Dict[str, Any]]:
    """
    Detecta se há padrão de escadinha de alta (staircase to heaven).
    Com 3-5 candles: usa uptrend simples. Com 6+: usa escadinha completa.

    Args:
        ohlcv: lista de candles com keys: close, high, low, timestamp
        min_steps: número mínimo de degraus para considerar padrão (6+ candles)

    Returns:
        (detectado, metadata)
    """
    min_candles = getattr(settings, "MIN_CANDLES", 4)
    min_steps = min_steps if min_steps is not None else getattr(settings, "MIN_PATTERN_STEPS", 1)
    if len(ohlcv) < min_candles:
        return False, {"reason": f"OHLCV muito curto: {len(ohlcv)} candles (mín {min_candles})"}

    # Modo rápido (3-5 candles): uptrend simples (preço subindo)
    if len(ohlcv) < 6:
        closes = np.array([c["close"] for c in ohlcv])
        # Exige: close atual > anterior (mínimo de momentum)
        if len(closes) >= 2 and closes[-1] <= closes[-2]:
            return False, {"reason": "Preço não subindo (4-5 candles)"}
        # Opcional: últimos 3 não-descendentes
        # Com 3+ candles: rejeitar só se queda clara (evita ser sensível demais)
        if len(closes) >= 3:
            last_n = closes[-3:]
            if any(last_n[i] > last_n[i + 1] for i in range(len(last_n) - 1)):
                return False, {"reason": "Correção recente (3-5 candles)"}
        last_price = float(closes[-1])
        first_price = float(closes[0])
        step_percent = ((last_price - first_price) / first_price * 100) if first_price > 0 else 0

        # Anti-ruído: rejeitar micro-bounces que não representam tendência real
        min_step_pct = getattr(settings, "MIN_STEP_PERCENT", 3.0)
        if step_percent < min_step_pct:
            return False, {"reason": f"Variação insuficiente: {step_percent:.1f}% < {min_step_pct}% (3-5 candles)"}

        recent_volumes = [c.get("volume", 0) for c in ohlcv[-5:]]
        avg_volume = np.mean(recent_volumes) if recent_volumes else 0
        return True, {
            "steps_up": 1,
            "last_price": last_price,
            "last_trough": float(closes[-2]) if len(closes) >= 2 else first_price,
            "last_peak": last_price,
            "step_height_usd": last_price - first_price,
            "step_percent": step_percent,
            "avg_volume": avg_volume,
        }

    # Extrair closes e highs/lows
    closes = np.array([c["close"] for c in ohlcv])
    highs = np.array([c["high"] for c in ohlcv])
    lows = np.array([c["low"] for c in ohlcv])

    # Detectar picos (highs) e vales (lows)
    # Simples: comparar com vizinhos
    high_peaks = []
    low_troughs = []

    for i in range(2, len(ohlcv) - 2):
        # High é pico se for maior que os vizinhos
        if highs[i] > highs[i-1] and highs[i] > highs[i+1]:
            high_peaks.append((i, highs[i]))
        # Low é vale se for menor que os vizinhos
        if lows[i] < lows[i-1] and lows[i] < lows[i+1]:
            low_troughs.append((i, lows[i]))

    if len(high_peaks) < min_steps or len(low_troughs) < min_steps:
        return False, {"reason": f"Picos/valles insuficientes: {len(high_peaks)}/{len(low_troughs)}"}

    # Verificar se últimos N picos são ascendentes (N = min_steps ou quantos temos)
    steps_use = min(min_steps, len(high_peaks), len(low_troughs))
    if steps_use < 1:
        steps_use = 1
    recent_peaks = high_peaks[-steps_use:]
    peak_prices = [p[1] for p in recent_peaks]
    if len(peak_prices) >= 1 and (len(peak_prices) == 1 or all(peak_prices[i] < peak_prices[i+1] for i in range(len(peak_prices)-1))):
        # Últimos vales também ascendentes?
        recent_troughs = low_troughs[-steps_use:]
        if len(recent_troughs) >= 1:
            trough_prices = [t[1] for t in recent_troughs]
            if len(trough_prices) == 1 or all(trough_prices[i] < trough_prices[i+1] for i in range(len(trough_prices)-1)):
                # Padrão válido!
                last_price = closes[-1]
                last_peak = peak_prices[-1]
                last_trough = trough_prices[-1]

                # Calcular "força" do padrão (height do último degrau)
                step_height = last_peak - last_trough
                step_percent = (step_height / last_trough) * 100 if last_trough > 0 else 0

                # Anti-ruído: último degrau precisa ter variação mínima
                min_step_pct = getattr(settings, "MIN_STEP_PERCENT", 3.0) * 0.5
                if step_percent < min_step_pct:
                    return False, {"reason": f"Step insuficiente: {step_percent:.1f}% < {min_step_pct:.1f}% (escadinha)"}

                # Verificar volume (pode ser desativado — memecoins = volume caótico)
                recent_volumes = [c.get("volume", 0) for c in ohlcv[-5:]]
                avg_volume = np.mean(recent_volumes) if recent_volumes else 0
                skip_vol = getattr(settings, "PATTERN_SKIP_VOLUME_CHECK", False)
                if not skip_vol:
                    vol_ratio = getattr(settings, "PATTERN_VOLUME_MIN_RATIO", 0.2)
                    volume_ok = avg_volume == 0 or recent_volumes[-1] >= avg_volume * vol_ratio
                    if not volume_ok:
                        return False, {"reason": "Volume decrescendo"}

                return True, {
                    "steps_up": min_steps,
                    "last_price": last_price,
                    "last_trough": last_trough,
                    "last_peak": last_peak,
                    "step_height_usd": step_height,
                    "step_percent": step_percent,
                    "avg_volume": avg_volume
                }

    return False, {"reason": "Sem escadinha ascendente"}