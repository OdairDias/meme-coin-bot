-- Posições abertas (substitui data/positions.json)
CREATE TABLE IF NOT EXISTS positions (
    token TEXT PRIMARY KEY,
    symbol TEXT NOT NULL DEFAULT '',
    entry_price DOUBLE PRECISION NOT NULL,
    quantity TEXT NOT NULL DEFAULT '100%',
    side TEXT NOT NULL DEFAULT 'BUY',
    opened_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    current_price DOUBLE PRECISION NOT NULL DEFAULT 0,
    amount_raw BIGINT
);

-- Histórico de posições fechadas (PnL, motivo, auditoria)
CREATE TABLE IF NOT EXISTS closed_positions (
    id BIGSERIAL PRIMARY KEY,
    token TEXT NOT NULL,
    symbol TEXT NOT NULL DEFAULT '',
    entry_price DOUBLE PRECISION NOT NULL,
    exit_price DOUBLE PRECISION NOT NULL,
    quantity TEXT NOT NULL DEFAULT '100%',
    side TEXT NOT NULL DEFAULT 'BUY',
    opened_at TIMESTAMPTZ NOT NULL,
    closed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    reason TEXT NOT NULL,
    pnl_usd DOUBLE PRECISION NOT NULL DEFAULT 0,
    pnl_percent DOUBLE PRECISION NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_closed_positions_token ON closed_positions(token);
CREATE INDEX IF NOT EXISTS idx_closed_positions_closed_at ON closed_positions(closed_at DESC);
