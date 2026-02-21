"""
Filtros de pré-entrada para memecoins
"""
from typing import Dict, Any


def apply_initial_filters(token_data: Dict[str, Any]) -> tuple[bool, str]:
    """
    Aplica filtros iniciais para decidir se o token é candidato.

    Returns:
        (passou, motivo_rejeicao)
    """
    # Volume mínimo
    volume = token_data.get("volume_24h", 0)
    if volume < 500:
        return False, f"Volume muito baixo: {volume:.0f} < 500"

    # Holders mínimo
    holders = token_data.get("holders", 0)
    if holders < 5:
        return False, f"Holders muito poucos: {holders} < 5"

    # Liquidez mínima
    liquidity = token_data.get("liquidity_usd", 0)
    if liquidity < 5000:
        return False, f"Liquidez muito baixa: ${liquidity:.0f} < $5k"

    # Dev supply (se disponível)
    dev_supply = token_data.get("dev_holding_percent", 0)
    if dev_supply > 20:
        return False, f"Dev com {dev_supply:.0f}% do supply (alto)"

    # Snipers count
    snipers = token_data.get("snipers_count", 0)
    if snipers > 20:
        return False, f"Muitos snipers: {snipers}"

    # Idade máxima (em minutos)
    created_at = token_data.get("created_at")
    if created_at:
        # Se for timestamp recente, pule
        try:
            from datetime import datetime, timezone
            created = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
            age_minutes = (datetime.now(timezone.utc) - created).total_seconds() / 60
            if age_minutes > 30:
                return False, f"Token muito velho: {age_minutes:.0f}min > 30min"
        except:
            pass

    return True, "OK"