"""
Executor de trades via PumpPortal API
"""
import asyncio
import logging
import httpx
from typing import Dict, Any

from app.core.config import settings
from app.core.security import get_wallet_keypair
from app.core.logger import setup_logger

logger = setup_logger(__name__)


class Executor:
    """Executa ordens de compra/venda via PumpPortal."""

    def __init__(self):
        self.client = httpx.AsyncClient(timeout=30.0)
        self.wallet_kp = get_wallet_keypair(settings.WALLET_PRIVATE_KEY)
        self.wallet_address = str(self.wallet_kp.pubkey())
        logger.info(f"Executor inicializado. Wallet: {self.wallet_address[:8]}...")

    async def buy(self, token_address: str, amount_sol: float, slippage: float = 10.0) -> bool:
        """
        Compra token usando PumpPortal.
        Args:
            token_address: contrato do token
            amount_sol: quantidade de SOL para gastar
            slippage: slippage percentual (10 = 10%)
        """
        if settings.DRY_RUN:
            logger.info(f"[DRY_RUN] BUY {token_address} amount={amount_sol} SOL slippage={slippage}%")
            return True

        try:
            payload = {
                "action": "buy",
                "contract": token_address,
                "amount": amount_sol,
                "slippage": slippage,
                "priority_fee": 0.0001  # ~0.01 SOL, ajustar
            }
            headers = {"Content-Type": "application/json"}
            response = await self.client.post(settings.PUMP_PORTAL_API, json=payload, headers=headers)
            response.raise_for_status()
            result = response.json()

            if result.get("success"):
                tx_id = result.get("txid", "N/A")
                logger.info(f"✅ COMPRA executada: {token_address} tx={tx_id}")
                return True
            else:
                logger.error(f"❌ COMPRA falhou: {result.get('error', 'Unknown')}")
                return False

        except Exception as e:
            logger.error(f"Erro ao executar COMPRA: {e}", exc_info=True)
            return False

    async def sell(self, token_address: str, amount_tokens: float, slippage: float = 10.0) -> bool:
        """
        Vende tokens via PumpPortal.
        Args:
            token_address: contrato do token
            amount_tokens: quantidade de tokens a vender
            slippage: slippage percentual
        """
        if settings.DRY_RUN:
            logger.info(f"[DRY_RUN] SELL {token_address} amount={amount_tokens} tokens slippage={slippage}%")
            return True

        try:
            payload = {
                "action": "sell",
                "contract": token_address,
                "amount": amount_tokens,
                "slippage": slippage,
                "priority_fee": 0.0001
            }
            headers = {"Content-Type": "application/json"}
            response = await self.client.post(settings.PUMP_PORTAL_API, json=payload, headers=headers)
            response.raise_for_status()
            result = response.json()

            if result.get("success"):
                tx_id = result.get("txid", "N/A")
                logger.info(f"✅ VENDA executada: {token_address} qty={amount_tokens} tx={tx_id}")
                return True
            else:
                logger.error(f"❌ VENDA falhou: {result.get('error', 'Unknown')}")
                return False

        except Exception as e:
            logger.error(f"Erro ao executar VENDA: {e}", exc_info=True)
            return False

    async def close(self):
        """Fecha cliente HTTP."""
        await self.client.aclose()