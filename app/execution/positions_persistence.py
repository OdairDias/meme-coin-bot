"""
Persistência de posições: PostgreSQL (se DATABASE_URL) ou data/positions.json (fallback).
Garante que posições sobrevivam a reinícios do bot.
"""
import json
import os
from typing import Dict, Any, List, Optional

from app.core.config import settings
from app.core.logger import setup_logger

logger = setup_logger(__name__)

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data")
POSITIONS_FILE = os.path.join(DATA_DIR, "positions.json")


def _use_db() -> bool:
    return bool((settings.DATABASE_URL or "").strip())


def _ensure_data_dir():
    os.makedirs(DATA_DIR, exist_ok=True)


def load_positions() -> Dict[str, Dict[str, Any]]:
    """
    Carrega posições: do Postgres se DATABASE_URL, senão do JSON.
    Retorna dict mint -> posição.
    """
    if _use_db():
        try:
            from app.db.postgres import load_positions_from_db
            return load_positions_from_db()
        except Exception as e:
            logger.warning(f"Fallback para JSON após erro Postgres: {e}")
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
    """Salva posições no JSON (usado apenas quando não há DATABASE_URL)."""
    if _use_db():
        return  # Postgres gerencia por add/remove/update
    _ensure_data_dir()
    try:
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
    """Adiciona ou atualiza posição (Postgres ou JSON)."""
    if _use_db():
        try:
            from app.db.postgres import add_position_to_db
            if add_position_to_db(token, entry_price, quantity, symbol or token[:8], amount_raw):
                logger.debug(f"Posição salva (Postgres): {token[:12]}...")
                return
        except Exception as e:
            logger.warning(f"Erro ao salvar posição no Postgres: {e}")
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
        "amount_raw": amount_raw,
    }
    save_positions(positions)
    logger.debug(f"Posição salva em positions.json: {token[:12]}...")


def remove_position(token: str):
    """Remove posição (Postgres ou JSON)."""
    if _use_db():
        try:
            from app.db.postgres import remove_position_from_db
            if remove_position_from_db(token):
                logger.debug(f"Posição removida (Postgres): {token[:12]}...")
                return
        except Exception as e:
            logger.warning(f"Erro ao remover posição do Postgres: {e}")
    positions = load_positions()
    if token in positions:
        del positions[token]
        save_positions(positions)
        logger.debug(f"Posição removida de positions.json: {token[:12]}...")


def update_amount_raw(token: str, amount_raw: int):
    """Atualiza amount_raw da posição (Postgres ou JSON)."""
    if _use_db():
        try:
            from app.db.postgres import update_amount_raw_in_db
            update_amount_raw_in_db(token, amount_raw)
            return
        except Exception as e:
            logger.warning(f"Erro ao atualizar amount_raw no Postgres: {e}")
    positions = load_positions()
    if token in positions:
        positions[token]["amount_raw"] = amount_raw
        save_positions(positions)


def get_position_amount_raw(token: str) -> Optional[int]:
    """Retorna amount_raw da posição (fallback para Jupiter). Postgres ou JSON."""
    if _use_db():
        try:
            from app.db.postgres import get_position_amount_raw_from_db
            return get_position_amount_raw_from_db(token)
        except Exception as e:
            logger.debug(f"get_position_amount_raw Postgres: {e}")
    positions = load_positions()
    pos = positions.get(token)
    if not pos:
        return None
    return pos.get("amount_raw")


def update_position_quantity(token: str, quantity: str | float) -> None:
    """Atualiza quantity da posição (ex.: após fechamento parcial 50% → '50%')."""
    if _use_db():
        try:
            from app.db.postgres import update_quantity_in_db
            update_quantity_in_db(token, quantity)
            return
        except Exception as e:
            logger.warning(f"Erro ao atualizar quantity no Postgres: {e}")
    positions = load_positions()
    if token in positions:
        positions[token]["quantity"] = quantity if isinstance(quantity, str) else str(quantity)
        save_positions(positions)
        logger.debug(f"Quantity atualizada em positions.json: {token[:12]}... → {quantity}")


def record_closed_position(
    token: str,
    symbol: str,
    entry_price: float,
    exit_price: float,
    quantity,
    side: str,
    opened_at,
    reason: str,
    pnl_usd: float,
    pnl_percent: float,
):
    """Registra posição fechada no histórico (Postgres quando DATABASE_URL; senão só log)."""
    if _use_db():
        try:
            from app.db.postgres import insert_closed_position
            insert_closed_position(
                token=token,
                symbol=symbol,
                entry_price=entry_price,
                exit_price=exit_price,
                quantity=quantity,
                side=side,
                opened_at=opened_at,
                reason=reason,
                pnl_usd=pnl_usd,
                pnl_percent=pnl_percent,
            )
        except Exception as e:
            logger.warning(f"Erro ao salvar closed_position no Postgres: {e}")
