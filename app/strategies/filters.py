"""
Filtros de pré-entrada para memecoins (regras afrouxadas para tokens recém-listados)
"""
from typing import Dict, Any


# Limiares configuráveis — tokens do PumpPortal muitas vezes vêm sem volume/liquidez
MIN_VOLUME_24H = 0       # 0 = aceitar quando não temos dado (Birdeye pode preencher depois)
MIN_HOLDERS = 0           # 0 = aceitar recém-listados
MIN_LIQUIDITY_USD = 0     # 0 = aceitar quando não temos dado
MAX_DEV_SUPPLY_PERCENT = 30   # rejeitar só se dev > 30%
MAX_SNIPERS = 50          # rejeitar só se muitos snipers
MAX_AGE_MINUTES = 60      # aceitar tokens até 60 min de vida


def apply_initial_filters(token_data: Dict[str, Any]) -> tuple[bool, str]:
    """
    Aplica filtros iniciais para decidir se o token é candidato.
    Regras afrouxadas: quando volume/liquidez/holders vêm zerados (WS),
    deixamos passar e a estratégia usa OHLCV/score para decidir.

    Returns:
        (passou, motivo_rejeicao)
    """
    # Volume mínimo (só exige quando temos dado)
    volume = token_data.get("volume_24h", 0) or 0
    if MIN_VOLUME_24H > 0 and volume > 0 and volume < MIN_VOLUME_24H:
        return False, f"Volume muito baixo: {volume:.0f} < {MIN_VOLUME_24H}"

    # Holders mínimo
    holders = token_data.get("holders", 0) or 0
    if holders < MIN_HOLDERS:
        return False, f"Holders muito poucos: {holders} < {MIN_HOLDERS}"

    # Liquidez mínima (só exige quando temos dado)
    liquidity = token_data.get("liquidity_usd", 0) or 0
    if MIN_LIQUIDITY_USD > 0 and liquidity > 0 and liquidity < MIN_LIQUIDITY_USD:
        return False, f"Liquidez muito baixa: ${liquidity:.0f} < ${MIN_LIQUIDITY_USD}"

    # Dev supply (se disponível)
    dev_supply = token_data.get("dev_holding_percent", 0) or 0
    if dev_supply > MAX_DEV_SUPPLY_PERCENT:
        return False, f"Dev com {dev_supply:.0f}% do supply (max {MAX_DEV_SUPPLY_PERCENT}%)"

    # Snipers count
    snipers = token_data.get("snipers_count", token_data.get("snipers", 0)) or 0
    if snipers > MAX_SNIPERS:
        return False, f"Muitos snipers: {snipers} > {MAX_SNIPERS}"

    # Idade máxima (em minutos) — tokens mais velhos que isso não entram
    created_at = token_data.get("created_at")
    if created_at:
        try:
            from datetime import datetime, timezone
            created = datetime.fromisoformat(str(created_at).replace("Z", "+00:00"))
            age_minutes = (datetime.now(timezone.utc) - created).total_seconds() / 60
            if age_minutes > MAX_AGE_MINUTES:
                return False, f"Token muito velho: {age_minutes:.0f}min > {MAX_AGE_MINUTES}min"
        except Exception:
            pass

    return True, "OK"