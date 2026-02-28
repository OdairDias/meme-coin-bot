"""
Persistência em PostgreSQL quando DATABASE_URL está definido.
"""
from app.db.postgres import (
    init_schema,
    load_positions_from_db,
    add_position_to_db,
    remove_position_from_db,
    update_amount_raw_in_db,
    get_position_amount_raw_from_db,
    insert_closed_position,
    close_connection,
)

__all__ = [
    "init_schema",
    "load_positions_from_db",
    "add_position_to_db",
    "remove_position_from_db",
    "update_amount_raw_in_db",
    "get_position_amount_raw_from_db",
    "insert_closed_position",
    "close_connection",
]
