"""
Alertas via Telegram
"""
import asyncio
import httpx
from app.core.config import settings
from app.core.logger import setup_logger

logger = setup_logger(__name__)


class TelegramAlerter:
    """Envia mensagens para Telegram."""

    def __init__(self):
        self.bot_token = settings.TELEGRAM_BOT_TOKEN
        self.chat_id = settings.TELEGRAM_CHAT_ID
        self.client = httpx.AsyncClient(timeout=10.0)

    async def send(self, message: str):
        """Envia mensagem simples."""
        if not self.bot_token or not self.chat_id:
            return

        try:
            url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
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