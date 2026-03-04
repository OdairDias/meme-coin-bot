"""
Análise de performance das operações — conecta ao PostgreSQL do Railway e exibe métricas.

Uso (local, com DATABASE_URL do Railway):
    set DATABASE_URL=postgresql://postgres:<senha>@ballast.proxy.rlwy.net:39541/railway
    python scripts/analyze_trades.py

Ou com argumento direto:
    python scripts/analyze_trades.py "postgresql://postgres:...@.../railway"

Métricas calculadas:
  - Total de trades, win rate, ROI médio, ROI máximo/mínimo
  - PnL total em USD
  - Max drawdown (sequência de perdas consecutivas)
  - Performance por motivo de fechamento (STOP_LOSS, TAKE_PROFIT, EMERGENCY, TIMEOUT...)
  - Performance por hora do dia (UTC) — para identificar janelas lucrativas
  - Últimas 20 operações fechadas
"""

import os
import sys
from collections import defaultdict
from datetime import timezone
from typing import Any, Dict, List, Optional


def connect(url: str):
    try:
        import psycopg2
    except ImportError:
        print("ERRO: psycopg2 não instalado. Execute: pip install psycopg2-binary")
        sys.exit(1)
    try:
        return psycopg2.connect(url)
    except Exception as e:
        print(f"ERRO ao conectar ao Postgres: {e}")
        sys.exit(1)


def fetch_closed_positions(conn) -> List[Dict[str, Any]]:
    cur = conn.cursor()
    cur.execute("""
        SELECT
            token, symbol, entry_price, exit_price, quantity, side,
            opened_at, closed_at, reason, pnl_usd, pnl_percent
        FROM closed_positions
        ORDER BY closed_at DESC
        LIMIT 2000
    """)
    cols = [d[0] for d in cur.description]
    rows = [dict(zip(cols, row)) for row in cur.fetchall()]
    cur.close()
    return rows


def pct(value: float, total: float) -> str:
    if total == 0:
        return "0.0%"
    return f"{100 * value / total:.1f}%"


def fmt_pnl(val: float) -> str:
    sign = "+" if val >= 0 else ""
    return f"{sign}{val:.4f}"


def analyze(trades: List[Dict[str, Any]]) -> None:
    total = len(trades)
    if total == 0:
        print("\n⚠️  Nenhuma operação fechada encontrada em closed_positions.")
        return

    wins = [t for t in trades if t["pnl_usd"] > 0]
    losses = [t for t in trades if t["pnl_usd"] <= 0]
    total_pnl_usd = sum(t["pnl_usd"] for t in trades)
    avg_pct = sum(t["pnl_percent"] for t in trades) / total
    max_pct = max(t["pnl_percent"] for t in trades)
    min_pct = min(t["pnl_percent"] for t in trades)

    # Max drawdown: maior sequência de perdas consecutivas (em ROI%)
    max_dd = 0.0
    running_dd = 0.0
    for t in sorted(trades, key=lambda x: x["closed_at"]):
        if t["pnl_percent"] < 0:
            running_dd += abs(t["pnl_percent"])
            max_dd = max(max_dd, running_dd)
        else:
            running_dd = 0.0

    # Breakdown por reason
    reason_stats: Dict[str, Dict] = defaultdict(lambda: {"count": 0, "pnl_usd": 0.0, "pnl_pct_sum": 0.0, "wins": 0})
    for t in trades:
        r = t["reason"] or "UNKNOWN"
        reason_stats[r]["count"] += 1
        reason_stats[r]["pnl_usd"] += t["pnl_usd"]
        reason_stats[r]["pnl_pct_sum"] += t["pnl_percent"]
        if t["pnl_usd"] > 0:
            reason_stats[r]["wins"] += 1

    # Breakdown por hora do dia (UTC)
    hour_stats: Dict[int, Dict] = defaultdict(lambda: {"count": 0, "pnl_usd": 0.0, "wins": 0})
    for t in trades:
        dt = t["closed_at"]
        if hasattr(dt, "astimezone"):
            hour = dt.astimezone(timezone.utc).hour
        else:
            hour = 0
        hour_stats[hour]["count"] += 1
        hour_stats[hour]["pnl_usd"] += t["pnl_usd"]
        if t["pnl_usd"] > 0:
            hour_stats[hour]["wins"] += 1

    # --- Output ---
    sep = "=" * 60

    print(f"\n{sep}")
    print("  ANÁLISE DE PERFORMANCE — MEME COIN BOT")
    print(sep)
    print(f"  Total de operações  : {total}")
    print(f"  Vencedoras          : {len(wins)}  ({pct(len(wins), total)})")
    print(f"  Perdedoras          : {len(losses)}  ({pct(len(losses), total)})")
    print(f"  ROI médio           : {fmt_pnl(avg_pct)}%")
    print(f"  ROI máximo          : +{max_pct:.2f}%")
    print(f"  ROI mínimo          : {min_pct:.2f}%")
    print(f"  PnL total (USD)     : {fmt_pnl(total_pnl_usd)} USD")
    print(f"  Max drawdown consec.: -{max_dd:.2f}% (soma de perdas consecutivas)")

    print(f"\n  BREAKDOWN POR MOTIVO DE FECHAMENTO")
    print(f"  {'Motivo':<28} {'Trades':>6}  {'Win%':>6}  {'PnL USD':>10}  {'ROI médio%':>11}")
    print("  " + "-" * 66)
    for reason, s in sorted(reason_stats.items(), key=lambda x: -x[1]["pnl_usd"]):
        cnt = s["count"]
        wr = pct(s["wins"], cnt)
        avg_r = s["pnl_pct_sum"] / cnt if cnt else 0
        print(f"  {reason:<28} {cnt:>6}  {wr:>6}  {fmt_pnl(s['pnl_usd']):>10}  {fmt_pnl(avg_r):>10}%")

    print(f"\n  PERFORMANCE POR HORA DO DIA (UTC)")
    print(f"  {'Hora':>5}  {'Trades':>6}  {'Win%':>6}  {'PnL USD':>10}")
    print("  " + "-" * 35)
    for hour in sorted(hour_stats.keys()):
        s = hour_stats[hour]
        cnt = s["count"]
        wr = pct(s["wins"], cnt)
        print(f"  {hour:02d}:00  {cnt:>6}  {wr:>6}  {fmt_pnl(s['pnl_usd']):>10}")

    print(f"\n  ÚLTIMAS 20 OPERAÇÕES FECHADAS")
    print(f"  {'Symbol':<12}  {'Reason':<22}  {'ROI%':>8}  {'PnL USD':>10}  {'Fechada em'}")
    print("  " + "-" * 76)
    for t in trades[:20]:
        closed_str = t["closed_at"].strftime("%d/%m %H:%M") if hasattr(t["closed_at"], "strftime") else str(t["closed_at"])[:16]
        row_pct = fmt_pnl(t["pnl_percent"])
        row_usd = fmt_pnl(t["pnl_usd"])
        reason_short = (t["reason"] or "?")[:22]
        sym = (t["symbol"] or t["token"][:8])[:12]
        marker = "✅" if t["pnl_usd"] > 0 else "❌"
        print(f"  {marker} {sym:<10}  {reason_short:<22}  {row_pct:>8}%  {row_usd:>10}  {closed_str}")

    print(f"\n{sep}\n")


def main() -> None:
    url: Optional[str] = None
    if len(sys.argv) > 1:
        url = sys.argv[1]
    else:
        url = os.environ.get("DATABASE_URL") or os.environ.get("PGURL")

    if not url:
        print(
            "ERRO: DATABASE_URL não definida.\n"
            "Use: set DATABASE_URL=postgresql://postgres:<senha>@ballast.proxy.rlwy.net:39541/railway\n"
            "  ou passe a URL como argumento: python scripts/analyze_trades.py \"<url>\""
        )
        sys.exit(1)

    print("Conectando ao banco...")
    conn = connect(url)
    print("Buscando operações fechadas...")
    trades = fetch_closed_positions(conn)
    conn.close()
    analyze(trades)


if __name__ == "__main__":
    main()
