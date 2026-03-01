"""
Acesso PostgreSQL (sync) para posições e histórico.
Railway: use DATABASE_URL (postgres:// ou postgresql://).
"""
import os
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone

from app.core.config import settings
from app.core.logger import setup_logger

logger = setup_logger(__name__)

_conn = None


def _get_url() -> str:
    url = (settings.DATABASE_URL or "").strip()
    if url.startswith("postgres://"):
        return "postgresql://" + url[len("postgres://"):]
    return url


def _get_connection():
    global _conn
    if _conn is None or _conn.closed:
        import psycopg2
        url = _get_url()
        if not url:
            return None
        try:
            _conn = psycopg2.connect(url)
            _conn.autocommit = False
        except Exception as e:
            logger.warning(f"Postgres connect: {e}")
            return None
    return _conn


def init_schema() -> bool:
    """Cria tabelas se não existirem. Retorna True se OK."""
    conn = _get_connection()
    if not conn:
        return False
    schema_path = os.path.join(os.path.dirname(__file__), "schema.sql")
    try:
        with open(schema_path, "r", encoding="utf-8") as f:
            sql = f.read()
        with conn.cursor() as cur:
            cur.execute(sql)
        conn.commit()
        logger.info("Schema Postgres aplicado (positions + closed_positions)")
        return True
    except Exception as e:
        logger.warning(f"Init schema: {e}")
        if conn:
            conn.rollback()
        return False


def load_positions_from_db() -> Dict[str, Dict[str, Any]]:
    """Carrega todas as posições abertas. Retorna dict token -> posição."""
    conn = _get_connection()
    if not conn:
        return {}
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT token, symbol, entry_price, quantity, side,
                       opened_at, current_price, amount_raw
                FROM positions
                """
            )
            rows = cur.fetchall()
        result = {}
        for r in rows:
            token, symbol, entry_price, quantity, side, opened_at, current_price, amount_raw = r
            opened_at = opened_at.isoformat() if hasattr(opened_at, "isoformat") else str(opened_at)
            result[token] = {
                "token": token,
                "symbol": symbol or token[:8],
                "entry_price": float(entry_price),
                "quantity": quantity or "100%",
                "side": side or "BUY",
                "opened_at": opened_at,
                "current_price": float(current_price or entry_price),
                "amount_raw": int(amount_raw) if amount_raw is not None else None,
            }
        return result
    except Exception as e:
        logger.warning(f"load_positions_from_db: {e}")
        if conn:
            conn.rollback()
        return {}


def add_position_to_db(
    token: str,
    entry_price: float,
    quantity: str | float,
    symbol: str = "",
    amount_raw: Optional[int] = None,
) -> bool:
    """Insere ou atualiza posição (upsert)."""
    conn = _get_connection()
    if not conn:
        return False
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO positions (token, symbol, entry_price, quantity, side, current_price, amount_raw)
                VALUES (%s, %s, %s, %s, 'BUY', %s, %s)
                ON CONFLICT (token) DO UPDATE SET
                    symbol = EXCLUDED.symbol,
                    entry_price = EXCLUDED.entry_price,
                    quantity = EXCLUDED.quantity,
                    current_price = EXCLUDED.current_price,
                    amount_raw = EXCLUDED.amount_raw
                """,
                (token, symbol or token[:8], entry_price, str(quantity), entry_price, amount_raw),
            )
        conn.commit()
        logger.debug(f"Posição salva no Postgres: {token[:12]}...")
        return True
    except Exception as e:
        logger.warning(f"add_position_to_db: {e}")
        if conn:
            conn.rollback()
        return False


def remove_position_from_db(token: str) -> bool:
    """Remove posição pelo token."""
    conn = _get_connection()
    if not conn:
        return False
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM positions WHERE token = %s", (token,))
        conn.commit()
        logger.debug(f"Posição removida do Postgres: {token[:12]}...")
        return True
    except Exception as e:
        logger.warning(f"remove_position_from_db: {e}")
        if conn:
            conn.rollback()
        return False


def update_amount_raw_in_db(token: str, amount_raw: int) -> bool:
    """Atualiza amount_raw da posição."""
    conn = _get_connection()
    if not conn:
        return False
    try:
        with conn.cursor() as cur:
            cur.execute("UPDATE positions SET amount_raw = %s WHERE token = %s", (amount_raw, token))
        conn.commit()
        return True
    except Exception as e:
        logger.warning(f"update_amount_raw_in_db: {e}")
        if conn:
            conn.rollback()
        return False


def update_quantity_in_db(token: str, quantity: str | float) -> bool:
    """Atualiza quantity da posição (ex.: após parcial '50%')."""
    conn = _get_connection()
    if not conn:
        return False
    try:
        with conn.cursor() as cur:
            cur.execute("UPDATE positions SET quantity = %s WHERE token = %s", (str(quantity), token))
        conn.commit()
        logger.debug(f"Quantity atualizada no Postgres: {token[:12]}... → {quantity}")
        return True
    except Exception as e:
        logger.warning(f"update_quantity_in_db: {e}")
        if conn:
            conn.rollback()
        return False


def get_position_amount_raw_from_db(token: str) -> Optional[int]:
    """Retorna amount_raw da posição (para fallback Jupiter)."""
    conn = _get_connection()
    if not conn:
        return None
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT amount_raw FROM positions WHERE token = %s", (token,))
            row = cur.fetchone()
        if row and row[0] is not None:
            return int(row[0])
        return None
    except Exception as e:
        logger.debug(f"get_position_amount_raw_from_db: {e}")
        return None


def insert_closed_position(
    token: str,
    symbol: str,
    entry_price: float,
    exit_price: float,
    quantity: str | float,
    side: str,
    opened_at,
    reason: str,
    pnl_usd: float,
    pnl_percent: float,
) -> bool:
    """Registra posição fechada no histórico."""
    conn = _get_connection()
    if not conn:
        return False
    try:
        if hasattr(opened_at, "isoformat"):
            opened_at = opened_at.isoformat()
        opened_at_parsed = datetime.fromisoformat(opened_at.replace("Z", "+00:00")) if isinstance(opened_at, str) else opened_at
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO closed_positions
                (token, symbol, entry_price, exit_price, quantity, side, opened_at, reason, pnl_usd, pnl_percent)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (token, symbol, entry_price, exit_price, str(quantity), side, opened_at_parsed, reason, pnl_usd, pnl_percent),
            )
        conn.commit()
        logger.debug(f"Closed position salva no Postgres: {token[:12]}...")
        return True
    except Exception as e:
        logger.warning(f"insert_closed_position: {e}")
        if conn:
            conn.rollback()
        return False


def close_connection():
    """Fecha conexão (chamar no shutdown se desejar)."""
    global _conn
    if _conn and not _conn.closed:
        try:
            _conn.close()
        except Exception:
            pass
        _conn = None
