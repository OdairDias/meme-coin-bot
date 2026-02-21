"""
Executor de trades via PumpPortal API
Documentação: https://pumpportal.fun/local-trading-api/trading-api
Suporta trade-local (recebe tx serializada → assina → envia ao RPC) e Lightning (resposta JSON).
"""
import base64
import httpx
from typing import Dict, Any, Union, Optional

from app.core.config import settings
from app.core.security import get_wallet_keypair
from app.core.logger import setup_logger

logger = setup_logger(__name__)


def _is_trade_local() -> bool:
    """True se estiver usando o endpoint trade-local (resposta = tx serializada em bytes)."""
    return "trade-local" in (settings.PUMP_PORTAL_API or "")


class Executor:
    """Executa ordens de compra/venda via PumpPortal (trade-local ou Lightning)."""

    def __init__(self):
        self.client = httpx.AsyncClient(timeout=30.0)
        self.wallet_kp = get_wallet_keypair(settings.WALLET_PRIVATE_KEY)
        self.wallet_address = str(self.wallet_kp.pubkey())
        logger.info(f"Executor inicializado. Wallet: {self.wallet_address[:8]}...")

    def _payload(
        self,
        action: str,
        mint: str,
        amount: Union[float, str],
        denominated_in_sol: bool,
        slippage: float = 10.0,
        priority_fee: float = 0.00005,
        pool: str = "auto",
    ) -> dict:
        """Monta body conforme documentação PumpPortal."""
        return {
            "publicKey": self.wallet_address,
            "action": action,
            "mint": mint,
            "amount": amount,
            "denominatedInSol": "true" if denominated_in_sol else "false",
            "slippage": slippage,
            "priorityFee": priority_fee,
            "pool": pool,
        }

    async def _sign_and_send_tx(self, tx_bytes: bytes) -> Optional[str]:
        """
        Deserializa a tx recebida do PumpPortal, assina com a keypair e envia ao RPC.
        Retorna a assinatura (txid) ou None em caso de erro.
        """
        try:
            from solders.transaction import VersionedTransaction

            raw_tx = VersionedTransaction.from_bytes(tx_bytes)
            signed_tx = VersionedTransaction(raw_tx.message, [self.wallet_kp])
            serialized = bytes(signed_tx)
            b64 = base64.b64encode(serialized).decode("ascii")

            rpc_url = settings.SOLANA_RPC_URL
            body = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "sendTransaction",
                "params": [
                    b64,
                    {"encoding": "base64", "skipPreflight": False, "preflightCommitment": "confirmed"},
                ],
            }
            async with httpx.AsyncClient(timeout=30.0) as rpc_client:
                rpc_resp = await rpc_client.post(rpc_url, json=body)
                rpc_resp.raise_for_status()
                data = rpc_resp.json()
            if "error" in data:
                logger.error(f"RPC erro: {data['error']}")
                return None
            txid = data.get("result")
            if txid:
                logger.info(f"Tx enviada ao RPC: {txid}")
            return txid
        except Exception as e:
            logger.error(f"Erro ao assinar/enviar tx: {e}", exc_info=True)
            return None

    async def _execute(
        self,
        action: str,
        token_address: str,
        amount: Union[float, str],
        denominated_in_sol: bool,
        slippage: float,
        priority_fee: float,
        pool: str,
    ) -> bool:
        """Envia ordem ao PumpPortal e trata resposta (JSON Lightning ou bytes trade-local)."""
        payload = self._payload(
            action=action,
            mint=token_address,
            amount=amount,
            denominated_in_sol=denominated_in_sol,
            slippage=slippage,
            priority_fee=priority_fee,
            pool=pool,
        )
        # trade-local na doc usa form data; Lightning pode usar JSON
        if _is_trade_local():
            form = {k: str(v) for k, v in payload.items()}
            response = await self.client.post(settings.PUMP_PORTAL_API, data=form)
        else:
            response = await self.client.post(
                settings.PUMP_PORTAL_API,
                json=payload,
                headers={"Content-Type": "application/json"},
            )
        response.raise_for_status()

        content_type = (response.headers.get("content-type") or "").lower()
        if "application/json" in content_type:
            result = response.json()
            if result.get("success"):
                tx_id = result.get("txid", "N/A")
                logger.info(f"✅ {action.upper()} executada: {token_address} tx={tx_id}")
                return True
            logger.error(f"❌ {action.upper()} falhou: {result.get('error', 'Unknown')}")
            return False

        if _is_trade_local() and response.content:
            txid = await self._sign_and_send_tx(response.content)
            if txid:
                logger.info(f"✅ {action.upper()} executada: {token_address} tx={txid}")
                return True
            return False

        logger.error("Resposta inesperada do PumpPortal (nem JSON nem tx bytes)")
        return False

    async def buy(
        self,
        token_address: str,
        amount: float,
        denominated_in_sol: bool = False,
        slippage: float = 10.0,
        priority_fee: float = 0.00005,
        pool: str = "auto",
    ) -> bool:
        """
        Compra token via PumpPortal.
        amount: SOL se denominated_in_sol=True, tokens se False.
        """
        if settings.DRY_RUN:
            unit = "SOL" if denominated_in_sol else "tokens"
            logger.info(f"[DRY_RUN] BUY {token_address} amount={amount} {unit} slippage={slippage}%")
            return True

        try:
            return await self._execute(
                action="buy",
                token_address=token_address,
                amount=amount,
                denominated_in_sol=denominated_in_sol,
                slippage=slippage,
                priority_fee=priority_fee,
                pool=pool,
            )
        except Exception as e:
            logger.error(f"Erro ao executar COMPRA: {e}", exc_info=True)
            return False

    async def sell(
        self,
        token_address: str,
        amount: Union[float, str],
        denominated_in_sol: bool = False,
        slippage: float = 10.0,
        priority_fee: float = 0.00005,
        pool: str = "auto",
    ) -> bool:
        """
        Vende tokens via PumpPortal.
        amount: quantidade em tokens ou "100%" para vender tudo.
        """
        if settings.DRY_RUN:
            logger.info(f"[DRY_RUN] SELL {token_address} amount={amount} slippage={slippage}%")
            return True

        try:
            return await self._execute(
                action="sell",
                token_address=token_address,
                amount=amount,
                denominated_in_sol=denominated_in_sol,
                slippage=slippage,
                priority_fee=priority_fee,
                pool=pool,
            )
        except Exception as e:
            logger.error(f"Erro ao executar VENDA: {e}", exc_info=True)
            return False

    async def close(self):
        """Fecha cliente HTTP."""
        await self.client.aclose()
