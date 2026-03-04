"""
Alertas via Telegram — envio de mensagens + polling de comandos (/report, /status).

Comandos suportados:
  /report  — métricas de performance do Postgres (win rate, ROI, PnL, breakdown por motivo)
  /status  — posições abertas e estado atual do bot
"""
import asyncio
import time as _time
from datetime import datetime, timezone
from typing import Any, Optional

import httpx

from app.core.config import settings
from app.core.logger import setup_logger

logger = setup_logger(__name__)

_BASE_API = "https://api.telegram.org/bot{token}/{method}"


class TelegramAlerter:
    """Envia mensagens para Telegram e processa comandos via long-polling."""

    def __init__(self):
        self.bot_token = settings.TELEGRAM_BOT_TOKEN
        self.chat_id = settings.TELEGRAM_CHAT_ID
        self.client = httpx.AsyncClient(timeout=10.0)
        self._update_offset: int = 0
        self._command_task: Optional[asyncio.Task] = None
        self._risk_manager: Optional[Any] = None  # injetado via set_risk_manager()

    async def set_risk_manager(self, risk_manager: Any) -> None:
        """Injeta referência ao MemeRiskManager para o /status."""
        self._risk_manager = risk_manager

    # -------------------------------------------------------------------------
    # Listener de comandos (Fase 3)
    # -------------------------------------------------------------------------

    async def start_command_listener(self) -> None:
        """Inicia o loop de long-polling para comandos Telegram."""
        if not self.bot_token or not self.chat_id:
            return
        self._command_task = asyncio.current_task()
        logger.info("💬 Telegram command listener ativo (/report, /status)")
        await self._poll_commands()

    async def stop_command_listener(self) -> None:
        if self._command_task and not self._command_task.done():
            self._command_task.cancel()

    async def _poll_commands(self) -> None:
        """Long-polling de getUpdates com timeout=30s."""
        while True:
            try:
                url = _BASE_API.format(token=self.bot_token, method="getUpdates")
                params = {
                    "offset": self._update_offset,
                    "timeout": 30,
                    "allowed_updates": ["message"],
                }
                async with httpx.AsyncClient(timeout=40.0) as client:
                    r = await client.get(url, params=params)
                    r.raise_for_status()
                    data = r.json()

                for update in data.get("result", []):
                    self._update_offset = update["update_id"] + 1
                    msg = update.get("message") or {}
                    text = (msg.get("text") or "").strip()
                    chat_id = str((msg.get("chat") or {}).get("id", ""))
                    if not text.startswith("/") or not chat_id:
                        continue
                    cmd = text.split()[0].lower().split("@")[0]
                    if cmd == "/report":
                        asyncio.create_task(self._handle_report(chat_id))
                    elif cmd == "/status":
                        asyncio.create_task(self._handle_status(chat_id))

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.debug(f"Telegram polling: {e}")
                await asyncio.sleep(5.0)

    # -------------------------------------------------------------------------
    # Handlers de comandos
    # -------------------------------------------------------------------------

    async def _handle_report(self, chat_id: str) -> None:
        """Consulta closed_positions e envia métricas formatadas."""
        await self._send_to(chat_id, "⏳ Gerando relatório...")
        try:
            text = await self._build_report_text()
        except Exception as e:
            await self._send_to(chat_id, f"🚨 Erro ao gerar relatório: {e}")
            return
        await self._send_to(chat_id, text)

    async def _handle_status(self, chat_id: str) -> None:
        """Retorna estado atual do bot: posições abertas e daily PnL."""
        try:
            lines = ["<b>📊 STATUS DO BOT</b>"]
            if self._risk_manager:
                n_pos = len(getattr(self._risk_manager, "open_positions", {}))
                daily = getattr(self._risk_manager, "_daily_loss", 0)
                lines.append(f"Posições abertas: <b>{n_pos}</b>")
                lines.append(f"Daily PnL: <b>{daily:+.4f} USD</b>")
            now_str = datetime.now(timezone.utc).strftime("%d/%m/%Y %H:%M UTC")
            lines.append(f"Hora: {now_str}")
            await self._send_to(chat_id, "\n".join(lines))
        except Exception as e:
            await self._send_to(chat_id, f"🚨 Erro ao obter status: {e}")

    async def _build_report_text(self) -> str:
        """Gera texto do /report consultando o Postgres."""
        import asyncio
        db_url = getattr(settings, "DATABASE_URL", None)
        if not db_url:
            return "⚠️ DATABASE_URL não configurada — relatório indisponível."

        # Executa consulta síncrona em thread para não bloquear o event loop
        loop = asyncio.get_event_loop()
        rows = await loop.run_in_executor(None, _fetch_closed_positions, db_url)

        if not rows:
            return "📊 <b>RELATÓRIO</b>\n\nNenhuma operação fechada ainda."

        total = len(rows)
        wins = [r for r in rows if r["pnl_usd"] > 0]
        total_pnl = sum(r["pnl_usd"] for r in rows)
        avg_pct = sum(r["pnl_percent"] for r in rows) / total
        max_pct = max(r["pnl_percent"] for r in rows)
        min_pct = min(r["pnl_percent"] for r in rows)
        win_rate = 100 * len(wins) / total

        # Breakdown por motivo
        from collections import defaultdict
        reasons: dict = defaultdict(lambda: {"cnt": 0, "pnl": 0.0, "wins": 0, "pct_sum": 0.0})
        for r in rows:
            k = r["reason"] or "UNKNOWN"
            reasons[k]["cnt"] += 1
            reasons[k]["pnl"] += r["pnl_usd"]
            reasons[k]["pct_sum"] += r["pnl_percent"]
            if r["pnl_usd"] > 0:
                reasons[k]["wins"] += 1

        lines = [
            "📊 <b>RELATÓRIO DE PERFORMANCE</b>",
            "",
            f"Total: <b>{total}</b> trades | Win rate: <b>{win_rate:.0f}%</b>",
            f"PnL total: <b>{total_pnl:+.4f} USD</b>",
            f"ROI médio: <b>{avg_pct:+.1f}%</b> | Máx: <b>+{max_pct:.1f}%</b> | Mín: <b>{min_pct:.1f}%</b>",
            "",
            "<b>Por motivo:</b>",
        ]

        reason_emoji = {
            "STOP_LOSS": "❌", "TAKE_PROFIT_PARTIAL": "🔄",
            "TAKE_PROFIT_FULL": "✅", "MAX_HOLDING_TIME": "⏰",
            "EMERGENCY_SELL": "🚨", "ZERO_BALANCE": "⚪",
        }
        for reason, s in sorted(reasons.items(), key=lambda x: -x[1]["pnl"]):
            emoji = reason_emoji.get(reason, "📌")
            wr = 100 * s["wins"] / s["cnt"] if s["cnt"] else 0
            avg_r = s["pct_sum"] / s["cnt"] if s["cnt"] else 0
            lines.append(
                f"{emoji} {reason}: {s['cnt']} trades, {wr:.0f}% win, "
                f"{s['pnl']:+.2f} USD, ROI médio {avg_r:+.1f}%"
            )

        # Últimas 5 operações
        lines += ["", "<b>Últimas 5 operações:</b>"]
        for r in rows[:5]:
            emoji = "✅" if r["pnl_usd"] > 0 else "❌"
            sym = (r["symbol"] or r["token"][:8])[:10]
            reason_short = (r["reason"] or "?")[:18]
            lines.append(
                f"{emoji} {sym} {r['pnl_percent']:+.1f}% ({r['pnl_usd']:+.2f} USD) — {reason_short}"
            )

        now_str = datetime.now(timezone.utc).strftime("%d/%m %H:%M UTC")
        lines += ["", f"<i>Gerado: {now_str}</i>"]
        return "\n".join(lines)

    async def _send_to(self, chat_id: str, message: str) -> None:
        """Envia mensagem para um chat_id específico (usado pelos handlers de comando)."""
        if not self.bot_token:
            return
        try:
            url = _BASE_API.format(token=self.bot_token, method="sendMessage")
            # Telegram limita mensagens a 4096 caracteres
            for chunk in _split_message(message, 4000):
                async with httpx.AsyncClient(timeout=10.0) as client:
                    await client.post(url, json={"chat_id": chat_id, "text": chunk, "parse_mode": "HTML"})
        except Exception as e:
            logger.debug(f"_send_to erro: {e}")

    async def send(self, message: str):
        """Envia mensagem simples para o chat configurado."""
        if not self.bot_token or not self.chat_id:
            return

        try:
            url = _BASE_API.format(token=self.bot_token, method="sendMessage")
            payload = {
                "chat_id": self.chat_id,
                "text": message,
                "parse_mode": "HTML"
            }
            await self.client.post(url, json=payload)
        except Exception as e:
            logger.error(f"Erro ao enviar Telegram: {e}")

    async def send_trade(self, symbol: str, side: str, price: float, quantity: float, tx_id: str = None):
        """Notifica trade executado."""
        msg = f"📢 <b>TRADE</b>\n" \
              f"🪙 {symbol}\n" \
              f"➡️ {side}\n" \
              f"💰 ${price:.6f}\n" \
              f"🔢 qty: {quantity:.6f}"
        if tx_id:
            msg += f"\n🔗 <a href=\"https://solscan.io/tx/{tx_id}\">tx</a>"
        await self.send(msg)

    async def send_position_closed(self, symbol: str, pnl: float, pnl_percent: float, reason: str):
        """Notifica fechamento de posição."""
        emoji = "✅" if pnl >= 0 else "❌"
        msg = f"{emoji} <b>POSIÇÃO FECHADA</b>\n" \
              f"🪙 {symbol}\n" \
              f"📊 PnL: ${pnl:.2f} ({pnl_percent:.1f}%)\n" \
              f"📝 Motivo: {reason}"
        await self.send(msg)

    async def send_alert(self, level: str, message: str):
        """Alerta genérico."""
        emoji_map = {
            "info": "ℹ️",
            "warning": "⚠️",
            "error": "🚨",
            "critical": "🔥"
        }
        emoji = emoji_map.get(level, "📢")
        msg = f"{emoji} <b>{level.upper()}</b>\n{message}"
        await self.send(msg)


# ---------------------------------------------------------------------------
# Funções auxiliares (módulo-nível)
# ---------------------------------------------------------------------------

def _split_message(text: str, max_len: int = 4000):
    """Divide texto em chunks respeitando o limite do Telegram (4096 chars)."""
    lines = text.split("\n")
    chunk: list[str] = []
    current_len = 0
    for line in lines:
        if current_len + len(line) + 1 > max_len and chunk:
            yield "\n".join(chunk)
            chunk = []
            current_len = 0
        chunk.append(line)
        current_len += len(line) + 1
    if chunk:
        yield "\n".join(chunk)


def _fetch_closed_positions(db_url: str) -> list:
    """
    Consulta síncrona ao Postgres (rodada via run_in_executor).
    Retorna lista de dicts com as últimas 500 operações fechadas.
    """
    try:
        import psycopg2
    except ImportError:
        return []
    try:
        conn = psycopg2.connect(db_url)
        cur = conn.cursor()
        cur.execute("""
            SELECT token, symbol, pnl_usd, pnl_percent, reason, closed_at
            FROM closed_positions
            ORDER BY closed_at DESC
            LIMIT 500
        """)
        cols = [d[0] for d in cur.description]
        rows = [dict(zip(cols, row)) for row in cur.fetchall()]
        cur.close()
        conn.close()
        return rows
    except Exception as e:
        logger.warning(f"_fetch_closed_positions: {e}")
        return []