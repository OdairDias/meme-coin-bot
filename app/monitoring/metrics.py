"""
Métricas Prometheus
"""
from prometheus_client import Counter, Gauge, Histogram, start_http_server

# Counters
trades_total = Counter('meme_trades_total', 'Total de trades', ['side', 'status'])
signals_generated = Counter('meme_signals_generated_total', 'Sinais gerados', ['symbol'])
positions_opened = Counter('meme_positions_opened_total', 'Posições abertas')
positions_closed = Counter('meme_positions_closed_total', 'Posições fechadas', ['reason'])

# Gauges
open_positions = Gauge('meme_open_positions', 'Posições abertas atualmente')
daily_pnl = Gauge('meme_daily_pnl_usd', 'PnL diário em USD')
current_equity = Gauge('meme_equity_usd', 'Equity atual em USD')

# Histograms
pnl_percent_hist = Histogram('meme_pnl_percent', 'PnL percentual por trade', buckets=[-20, -10, -5, -2, 0, 2, 5, 10, 20, 50, 100])
trade_duration_hist = Histogram('meme_trade_duration_seconds', 'Duração dos trades', buckets=[60, 300, 600, 1800, 3600, 7200])


def init_metrics(port: int = 9090):
    """Inicia servidor HTTP de métricas."""
    start_http_server(port)
    print(f"📊 Métricas disponíveis em :{port}/metrics")