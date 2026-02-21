"""
Gestão de risco para memecoin bot
"""
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List
import redis
from app.core.config import settings
from app.core.logger import setup_logger

logger = setup_logger(__name__)


class MemeRiskManager:
    """Gerenciador de risco específico para memecoins."""

    def __init__(self, redis_client: redis.Redis | None = None):
        self.redis = redis_client
        self.daily_loss = 0.0
        self.open_positions: Dict[str, Dict[str, Any]] = {}
        self._load_state()

    def _load_state(self):
        """Carrega estado do Redis se disponível."""
        if self.redis:
            try:
                daily_loss = self.redis.get("meme:daily_loss")
                if daily_loss:
                    self.daily_loss = float(daily_loss)
                # Carregar posições abertas
                pos_keys = self.redis.keys("meme:position:*")
                for key in pos_keys:
                    pos_data = self.redis.hgetall(key)
                    if pos_data:
                        token = pos_data.get("token", "")
                        self.open_positions[token] = {
                            "id": key.decode(),
                            "token": token,
                            "entry_price": float(pos_data.get("entry_price", 0)),
                            "quantity": float(pos_data.get("quantity", 0)),
                            "side": pos_data.get("side", "BUY"),
                            "opened_at": datetime.fromisoformat(pos_data.get("opened_at"))
                        }
            except Exception as e:
                logger.error(f"Erro ao carregar estado do Redis: {e}")

    def validate_signal(self, signal: Dict[str, Any], current_equity: float) -> Dict[str, Any]:
        """Valida se um sinal pode ser executado."""
        validation = {
            "valid": True,
            "reasons": [],
            "position_size_usd": 0.0,
            "risk_amount_usd": 0.0
        }

        # 1. Verificar número máximo de posições
        if len(self.open_positions) >= settings.MAX_CONCURRENT_POSITIONS:
            validation["valid"] = False
            validation["reasons"].append(f"Max posições simultâneas ({settings.MAX_CONCURRENT_POSITIONS}) atingido")

        # 2. Verificar daily loss limit
        if abs(self.daily_loss) >= settings.MAX_DAILY_LOSS_USD:
            validation["valid"] = False
            validation["reasons"].append(f"Daily loss limit (${settings.MAX_DAILY_LOSS_USD}) atingido")

        # 3. Verificar se já temos posição nesse token (cooldown simples)
        token = signal.get("address")
        if token in self.open_positions:
            validation["valid"] = False
            validation["reasons"].append(f"Já temos posição aberta em {signal.get('symbol')}")

        # 4. Position sizing
        position_size_usd = min(settings.MAX_POSITION_SIZE_USD, 2.0)
        validation["position_size_usd"] = position_size_usd
        validation["risk_amount_usd"] = position_size_usd * (settings.STOP_LOSS_PERCENT / 100)

        return validation

    async def record_position_open(self, token: str, entry_price: float, quantity: float, side: str = "BUY"):
        """Registra nova posição aberta."""
        pos_id = f"meme:position:{token}"
        position = {
            "token": token,
            "entry_price": entry_price,
            "quantity": quantity,
            "side": side,
            "opened_at": datetime.now(timezone.utc).isoformat(),
            "current_price": entry_price,
            "pnl": 0.0,
            "pnl_percent": 0.0
        }

        if self.redis:
            self.redis.hset(pos_id, mapping={
                "token": token,
                "entry_price": entry_price,
                "quantity": quantity,
                "side": side,
                "opened_at": position["opened_at"],
                "current_price": entry_price,
                "pnl": 0.0,
                "pnl_percent": 0.0
            })
            self.redis.expire(pos_id, 86400 * 7)  # 7 dias

        self.open_positions[token] = position
        logger.info(f"📈 Posição aberta: {token} qty={quantity:.6f} @ ${entry_price:.6f}")

    async def record_position_close(self, token: str, exit_price: float, reason: str):
        """Registra fechamento de posição e calcula PnL."""
        if token not in self.open_positions:
            logger.warning(f"Tentativa de fechar posição inexistente: {token}")
            return

        pos = self.open_positions[token]
        entry = pos["entry_price"]
        quantity = pos["quantity"]
        side = pos["side"]

        if side == "BUY":
            pnl = (exit_price - entry) * quantity
            pnl_percent = ((exit_price - entry) / entry) * 100 if entry > 0 else 0
        else:
            pnl = (entry - exit_price) * quantity
            pnl_percent = ((entry - exit_price) / entry) * 100 if entry > 0 else 0

        # Atualizar daily loss
        self.daily_loss += pnl

        # Remover posição
        pos_id = f"meme:position:{token}"
        if self.redis:
            self.redis.delete(pos_id)
        del self.open_positions[token]

        # Salvar histórico (em produção, usar tabela de closed positions)
        logger.info(f"✅ Posição fechada: {token} PnL=${pnl:.2f} ({pnl_percent:.1f}%) motivo={reason}")

        # Persistir daily loss
        if self.redis:
            self.redis.set("meme:daily_loss", self.daily_loss, ex=86400)

    def get_open_positions(self) -> List[Dict[str, Any]]:
        """Retorna lista de posições abertas."""
        return list(self.open_positions.values())

    def check_exit_conditions(self, token: str, current_price: float) -> str | None:
        """
        Verifica se posição deve ser fechada (SL/TP/timeout).
        Retorna motivo ou None.
        """
        if token not in self.open_positions:
            return None

        pos = self.open_positions[token]
        entry = pos["entry_price"]
        side = pos["side"]

        # Calcular PnL atual
        if side == "BUY":
            pnl_percent = ((current_price - entry) / entry) * 100 if entry > 0 else 0
        else:
            pnl_percent = ((entry - current_price) / entry) * 100 if entry > 0 else 0

        # Stop loss
        if pnl_percent <= -settings.STOP_LOSS_PERCENT:
            return "STOP_LOSS"

        # Take profit 2
        if pnl_percent >= settings.TAKE_PROFIT_PERCENT2:
            return "TAKE_PROFIT_FULL"

        # Take profit 1 (parcial) — implementar lógica de parcial depois
        if pnl_percent >= settings.TAKE_PROFIT_PERCENT1:
            # Por enquanto, só retorna TP1 se não tiver fechado parcial antes
            # Precisamos de campo 'partial_taken' na posição
            return "TAKE_PROFIT_PARTIAL"

        # Timeout
        opened_at = pos["opened_at"]
        if isinstance(opened_at, str):
            opened_at = datetime.fromisoformat(opened_at)
        holding_minutes = (datetime.now(timezone.utc) - opened_at).total_seconds() / 60
        if holding_minutes >= settings.MAX_HOLDING_MINUTES:
            return "MAX_HOLDING_TIME"

        return None