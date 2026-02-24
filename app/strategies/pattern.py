"""
Detecção de padrão "escadinha" (higher highs e higher lows) em OHLCV
"""
from typing import List, Dict, Any
import numpy as np
from datetime import datetime, timezone


def detect_stairs_pattern(ohlcv: List[Dict[str, Any]], min_steps: int = 3) -> tuple[bool, Dict[str, Any]]:
    """
    Detecta se há padrão de escadinha de alta (staircase to heaven).

    Args:
        ohlcv: lista de candles com keys: close, high, low, timestamp
        min_steps: número mínimo de degraus para considerar padrão

    Returns:
        (detectado, metadata)
    """
    # Mínimo 6 candles para min_steps=2 (range(2, len-2) precisa de 2+ índices)
    if len(ohlcv) < 6:
        return False, {"reason": f"OHLCV muito curto: {len(ohlcv)} candles (mín 6)"}

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

    # Verificar se últimos N picos são ascendentes
    recent_peaks = high_peaks[-min_steps:]
    peak_prices = [p[1] for p in recent_peaks]
    if all(peak_prices[i] < peak_prices[i+1] for i in range(len(peak_prices)-1)):
        # Últimos vales também ascendentes?
        recent_troughs = low_troughs[-min_steps:]
        if len(recent_troughs) >= min_steps:
            trough_prices = [t[1] for t in recent_troughs]
            if all(trough_prices[i] < trough_prices[i+1] for i in range(len(trough_prices)-1)):
                # Padrão válido!
                last_price = closes[-1]
                last_peak = peak_prices[-1]
                last_trough = trough_prices[-1]

                # Calcular "força" do padrão (height do último degrau)
                step_height = last_peak - last_trough
                step_percent = (step_height / last_trough) * 100 if last_trough > 0 else 0

                # Verificar volume nos últimos candles (afrouxado: 50% da média)
                recent_volumes = [c.get("volume", 0) for c in ohlcv[-5:]]
                avg_volume = np.mean(recent_volumes) if recent_volumes else 0
                volume_ok = avg_volume == 0 or recent_volumes[-1] >= avg_volume * 0.5

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