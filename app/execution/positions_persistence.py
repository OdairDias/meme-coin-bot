"""
Persistência de posições em data/positions.json
Garante que posições sobrevivam a reinícios do bot.
"""
import json
import os
from typing import Dict, Any, List, Optional

from app.core.logger import setup_logger

logger = setup_logger(__name__)

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data")
POSITIONS_FILE = os.path.join(DATA_DIR, "positions.json")


def _ensure_data_dir():
    os.makedirs(DATA_DIR, exist_ok=True)


def load_positions() -> Dict[str, Dict[str, Any]]:
    """
    Carrega posições do arquivo JSON.
    Retorna dict mint -> posição.
    """
    if not os.path.isfile(POSITIONS_FILE):
        return {}

    try:
        with open(POSITIONS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        positions = data.get("positions", data) if isinstance(data, dict) else {}
        if isinstance(positions, list):
            return {p["token"]: p for p in positions if p.get("token")}
        return positions
    except Exception as e:
        logger.warning(f"Erro ao carregar positions.json: {e}")
        return {}


def save_positions(positions: Dict[str, Dict[str, Any]]):
    """Salva posições no arquivo JSON."""
    _ensure_data_dir()
    try:
        # Converter para formato serializável (opened_at pode ser datetime)
        out = {}
        for token, pos in positions.items():
            p = dict(pos)
            if hasattr(p.get("opened_at"), "isoformat"):
                p["opened_at"] = p["opened_at"].isoformat()
            out[token] = p
        with open(POSITIONS_FILE, "w", encoding="utf-8") as f:
            json.dump({"positions": out}, f, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.error(f"Erro ao salvar positions.json: {e}")


def add_position(token: str, entry_price: float, quantity: str | float, symbol: str = "", amount_raw: Optional[int] = None):
    """Adiciona ou atualiza posição."""
    from datetime import datetime, timezone

    positions = load_positions()
    positions[token] = {
        "token": token,
        "symbol": symbol or token[:8],
        "entry_price": entry_price,
        "quantity": quantity,
        "side": "BUY",
        "opened_at": datetime.now(timezone.utc).isoformat(),
        "current_price": entry_price,
        "amount_raw": amount_raw,  # saldo em unidades atômicas (para fallback Jupiter)
    }
    save_positions(positions)
    logger.debug(f"Posição salva em positions.json: {token[:12]}...")


def remove_position(token: str):
    """Remove posição do arquivo."""
    positions = load_positions()
    if token in positions:
        del positions[token]
        save_positions(positions)
        logger.debug(f"Posição removida de positions.json: {token[:12]}...")


def update_amount_raw(token: str, amount_raw: int):
    """Atualiza amount_raw de uma posição (quando obtido da chain)."""
    positions = load_positions()
    if token in positions:
        positions[token]["amount_raw"] = amount_raw
        save_positions(positions)


def get_position_amount_raw(token: str) -> Optional[int]:
    """Retorna amount_raw armazenado como último recurso para Jupiter."""
    positions = load_positions()
    pos = positions.get(token)
    if not pos:
        return None
    return pos.get("amount_raw")
