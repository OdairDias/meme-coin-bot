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
        """Carrega estado: positions.json (primeiro) + Redis (daily_loss)."""
        # 1) Posições de data/positions.json (persiste entre reinícios)
        try:
            from app.execution.positions_persistence import load_positions, _use_db

            file_positions = load_positions()
            for token, pos in file_positions.items():
                try:
                    qty = pos.get("quantity", "100%")
                    if isinstance(qty, (int, float)):
                        pass
                    elif isinstance(qty, str) and "100" in qty:
                        qty = "100%"
                    else:
                        try:
                            qty = float(qty)
                        except (TypeError, ValueError):
                            qty = "100%"
                    opened_at = pos.get("opened_at")

                    if isinstance(opened_at, str):
                        opened_at = datetime.fromisoformat(opened_at.replace("Z", "+00:00"))
                    self.open_positions[token] = {
                        "token": token,
                        "symbol": pos.get("symbol", token[:8] if isinstance(token, str) else ""),
                        "entry_price": float(pos.get("entry_price", 0)),
                        "quantity": qty,
                        "side": pos.get("side", "BUY"),
                        "opened_at": opened_at or datetime.now(timezone.utc),
                        "current_price": float(pos.get("current_price", pos.get("entry_price", 0))),
                        "pnl": 0.0,
                        "pnl_percent": 0.0,
                        "amount_raw": pos.get("amount_raw"),
                    }
                except Exception as e:
                    logger.debug(f"Posição {token} ignorada: {e}")
            if file_positions:
                logger.info(f"Carregadas {len(file_positions)} posição(ões) de {'Postgres' if _use_db() else 'positions.json'}")
        except Exception as e:
            logger.warning(f"Erro ao carregar positions.json: {e}")

        # 2) Redis: daily_loss e merge de posições (se Redis tiver mais recente)
        if self.redis:
            try:
                daily_loss = self.redis.get("meme:daily_loss")
                if daily_loss:
                    self.daily_loss = float(daily_loss)
            except Exception as e:
                logger.debug(f"Redis daily_loss: {e}")

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

        # 2. Verificar daily loss limit (só bloqueia se a PERDA acumulada do dia >= limite)
        # BUGFIX: abs() disparava o bloqueio em lucros também (ex: +$245 bloqueava o bot)
        if self.daily_loss <= -abs(settings.MAX_DAILY_LOSS_USD):
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

    async def record_position_open(self, token: str, entry_price: float, quantity: float | str, side: str = "BUY", symbol: str = "", buy_amount_sol: float = 0):
        """Registra nova posição aberta (memória + Redis + positions.json)."""
        pos_id = f"meme:position:{token}"
        position = {
            "token": token,
            "symbol": symbol or token[:8],
            "entry_price": entry_price,
            "quantity": quantity,
            "side": side,
            "opened_at": datetime.now(timezone.utc).isoformat(),
            "current_price": entry_price,
            "pnl": 0.0,
            "pnl_percent": 0.0,
            "buy_amount_sol": buy_amount_sol,  # Quanto gastamos em SOL (para calcular PnL real)
        }

        # Persistência em positions.json (sobrevive reinício)
        try:
            from app.execution.positions_persistence import add_position
            add_position(token, entry_price, quantity, symbol or token[:8], amount_raw=None, buy_amount_sol=buy_amount_sol)
        except Exception as e:
            logger.warning(f"Erro ao salvar posição em positions.json: {e}")

        if self.redis:
            self.redis.hset(pos_id, mapping={
                "token": token,
                "symbol": symbol or token[:8],
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
        qty_log = f"{quantity:.6f}" if isinstance(quantity, (int, float)) else str(quantity)
        logger.info(f"📈 Posição aberta: {token} qty={qty_log} @ ${entry_price:.6f}")

    async def record_position_close(self, token: str, exit_price: float, reason: str):
        """Registra fechamento de posição e calcula PnL."""
        if token not in self.open_positions:
            logger.warning(f"Tentativa de fechar posição inexistente: {token}")
            return

        pos = self.open_positions[token]
        entry = pos["entry_price"]
        quantity = pos["quantity"]
        side = pos["side"]
        buy_amount_sol = pos.get("buy_amount_sol", 0)

        # Calcular PnL - usar buy_amount_sol quando quantity é string
        if isinstance(quantity, (int, float)) and quantity > 0:
            if side == "BUY":
                pnl = (exit_price - entry) * quantity
                pnl_percent = ((exit_price - entry) / entry) * 100 if entry > 0 else 0
            else:
                pnl = (entry - exit_price) * quantity
                pnl_percent = ((entry - exit_price) / entry) * 100 if entry > 0 else 0
        elif isinstance(quantity, str) and buy_amount_sol > 0:
            if side == "BUY":
                pnl_percent = ((exit_price - entry) / entry) * 100 if entry > 0 else 0
            else:
                pnl_percent = ((entry - exit_price) / entry) * 100 if entry > 0 else 0
            sol_price_usd = 100.0
            try:
                from app.scanners.jupiter import get_sol_price_usd
                fetched = await get_sol_price_usd()
                if fetched and fetched > 0:
                    sol_price_usd = fetched
            except Exception as e:
                logger.debug(f"Preço SOL fallback: {e}")

            buy_amount_usd = buy_amount_sol * sol_price_usd
            # TP1 fecha apenas 50% — base de cálculo do PnL deve ser metade da posição
            if "50" in str(quantity):
                buy_amount_usd *= 0.5
            pnl = (pnl_percent / 100) * buy_amount_usd
        else:
            pnl = 0.0
            pnl_percent = 0.0

        # Atualizar daily loss
        self.daily_loss += pnl

        # Histórico em Postgres (quando DATABASE_URL)
        try:
            from app.execution.positions_persistence import record_closed_position
            sym = pos.get("symbol") or token[:8]
            sym = sym.decode() if isinstance(sym, bytes) else str(sym)
            record_closed_position(
                token=token,
                symbol=sym,
                entry_price=entry,
                exit_price=exit_price,
                quantity=quantity,
                side=side,
                opened_at=pos.get("opened_at"),
                reason=reason,
                pnl_usd=pnl,
                pnl_percent=pnl_percent,
            )
        except Exception as e:
            logger.debug(f"record_closed_position: {e}")

        # Remover posição (memória + Redis + positions/Postgres)
        pos_id = f"meme:position:{token}"
        try:
            from app.execution.positions_persistence import remove_position
            remove_position(token)
        except Exception as e:
            logger.warning(f"Erro ao remover posição de positions.json: {e}")
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
            logger.info(f"🔴 SL: {token[:8]} entry={entry:.8f} current={current_price:.8f} pnl={pnl_percent:.1f}%")
            return "STOP_LOSS"

        # Take profit 1 (parcial): só dispara se ainda temos 100% (não fechamos parcial antes)
        # Verificar ANTES do TP2 para garantir que 50% seja vendido no TP1
        # Buffer: permite pegar o TP1 com slight antecipação (ex: 80% do target)
        tp1_threshold = settings.TAKE_PROFIT_PERCENT1 * getattr(settings, 'TAKE_PROFIT_BUFFER', 1.0)
        qty = pos.get("quantity", "100%")
        is_full_position = qty == "100%" or (isinstance(qty, str) and "100" in qty)
        if is_full_position and pnl_percent >= tp1_threshold:
            logger.info(f"🟢 TP1: {token[:8]} entry={entry:.8f} current={current_price:.8f} pnl={pnl_percent:.1f}% (target={tp1_threshold:.1f}%)")
            return "TAKE_PROFIT_PARTIAL"

        # Take profit 2 (full): só após TP1 ter fechado 50%
        if pnl_percent >= settings.TAKE_PROFIT_PERCENT2:
            logger.info(f"🟢 TP2: {token[:8]} entry={entry:.8f} current={current_price:.8f} pnl={pnl_percent:.1f}%")
            return "TAKE_PROFIT_FULL"

        # Timeout
        opened_at = pos["opened_at"]
        if isinstance(opened_at, str):
            opened_at = datetime.fromisoformat(opened_at)
        holding_minutes = (datetime.now(timezone.utc) - opened_at).total_seconds() / 60
        if holding_minutes >= settings.MAX_HOLDING_MINUTES:
            return "MAX_HOLDING_TIME"

        return None