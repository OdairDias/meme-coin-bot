"""Monitora o fallback de Bitquery/Birdeye do MemeCoin Bot."""
import json
import os
import subprocess
from datetime import datetime
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
WORKDIR = SCRIPT_DIR.parent
MONITOR_FILE = WORKDIR.parent / "monitoring" / "meme-coin-bot-monitor.md"
MONITOR_FILE.parent.mkdir(exist_ok=True)

LOG_LINES = 500
SERVICE_NAME = "meme-coin-bot"

PATTERNS = {
    "bitquery_empty": "Bitquery OHLCV vazio",
    "bitquery_fallback": "Bitquery fallback",
    "birdeye_fallback": "Birdeye data",
    "queue_overflow": "fila cheia",
    "deposit": "deposit",
}
ERROR_LEVEL_KEYS = ("level", "@level", "severity")


def fetch_logs() -> list[dict]:
    cmd = [
        "railway",
        "logs",
        "--service",
        SERVICE_NAME,
        "--lines",
        str(LOG_LINES),
        "--latest",
        "--json",
    ]
    result = subprocess.run(cmd, cwd=WORKDIR, capture_output=True, text=True, env=os.environ)
    if result.returncode != 0:
        raise RuntimeError(f"railway logs failed: {result.stderr.strip()}" )
    entries = []
    for line in result.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return entries


def summarize(entries: list[dict]) -> dict:
    counts = {name: 0 for name in PATTERNS}
    counts["errors"] = 0
    for entry in entries:
        text = entry.get("message") or entry.get("msg") or entry.get("line") or ""
        if not isinstance(text, str):
            try:
                text = str(text)
            except Exception:
                continue
        text_lower = text.lower()
        for name, pattern in PATTERNS.items():
            if pattern.lower() in text_lower:
                counts[name] += 1
        for key in ERROR_LEVEL_KEYS:
            level_value = entry.get(key)
            if isinstance(level_value, str) and level_value.lower() == "error":
                counts["errors"] += 1
                break
    return counts


def persist_report(counts: dict) -> None:
    MONITOR_FILE.parent.mkdir(exist_ok=True)
    timestamp = datetime.utcnow().replace(microsecond=0).isoformat() + "Z"
    header = f"## Monitoramento MemeCoin Bot — {timestamp}\n"
    lines = [header]
    lines.append(f"- Bitquery sem OHLCV (últimos {LOG_LINES} linhas): {counts['bitquery_empty']}")
    lines.append(f"- Bitquery fallback (sem DEX): {counts['bitquery_fallback']}")
    lines.append(f"- Logs com 'Birdeye data': {counts['birdeye_fallback']}")
    lines.append(f"- Mensagens de fila cheia (sinal de backlog): {counts['queue_overflow']}")
    lines.append(f"- Logs mencionando 'deposit': {counts['deposit']}")
    lines.append(f"- @level:error ou level=error registrados: {counts['errors']}\n")
    with MONITOR_FILE.open("a", encoding="utf-8") as f:
        f.write("\n".join(lines))
        f.write("\n")


def main() -> None:
    print("[monitor] coletando logs...", flush=True)
    entries = fetch_logs()
    counts = summarize(entries)
    print("[monitor] resumo:", counts, flush=True)
    persist_report(counts)


if __name__ == "__main__":
    main()
