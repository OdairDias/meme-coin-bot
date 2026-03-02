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

            rpc_url = settings.get_rpc_url()
            body = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "sendTransaction",
                "params": [
                    b64,
                    {"encoding": "base64", "skipPreflight": True, "preflightCommitment": "confirmed"},
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
    ) -> tuple[bool, Optional[str]]:
        """
        Envia ordem ao PumpPortal e trata resposta.
        Retorna (success, error_message).
        """
        payload = self._payload(
            action=action,
            mint=token_address,
            amount=amount,
            denominated_in_sol=denominated_in_sol,
            slippage=slippage,
            priority_fee=priority_fee,
            pool=pool,
        )
        try:
            if _is_trade_local():
                form = {k: str(v) for k, v in payload.items()}
                response = await self.client.post(settings.PUMP_PORTAL_API, data=form)
            else:
                response = await self.client.post(
                    settings.PUMP_PORTAL_API,
                    json=payload,
                    headers={"Content-Type": "application/json"},
                )

            content_type = (response.headers.get("content-type") or "").lower()

            # Erro HTTP (ex: 400 BondingCurveComplete)
            if response.status_code >= 400:
                err_msg = "Unknown"
                try:
                    if "application/json" in content_type:
                        data = response.json()
                        err_msg = data.get("error", data.get("message", str(response.text)))[:200]
                    else:
                        err_msg = response.text[:200] if response.text else str(response.status_code)
                except Exception:
                    pass
                logger.error(f"❌ {action.upper()} HTTP {response.status_code}: {err_msg}")
                return False, err_msg

            if "application/json" in content_type:
                result = response.json()
                if result.get("success"):
                    tx_id = result.get("txid", "N/A")
                    logger.info(f"✅ {action.upper()} executada: {token_address} tx={tx_id}")
                    return True, None
                err = result.get("error", "Unknown")
                logger.error(f"❌ {action.upper()} falhou: {err}")
                return False, str(err)

            if _is_trade_local() and response.content:
                txid = await self._sign_and_send_tx(response.content)
                if txid:
                    logger.info(f"✅ {action.upper()} executada: {token_address} tx={txid}")
                    return True, None
                return False, "Falha ao assinar/enviar tx"

        except httpx.HTTPStatusError as e:
            err_msg = str(e.response.text)[:200] if e.response else str(e)
            logger.error(f"❌ {action.upper()} HTTP error: {err_msg}")
            return False, err_msg
        except Exception as e:
            logger.error(f"❌ {action.upper()} erro: {e}", exc_info=True)
            return False, str(e)

        logger.error("Resposta inesperada do PumpPortal (nem JSON nem tx bytes)")
        return False, "Resposta inesperada"

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
            success, _ = await self._execute(
                action="buy",
                token_address=token_address,
                amount=amount,
                denominated_in_sol=denominated_in_sol,
                slippage=slippage,
                priority_fee=priority_fee,
                pool=pool,
            )
            return success
        except Exception as e:
            logger.error(f"Erro ao executar COMPRA: {e}", exc_info=True)
            return False

    def _is_bonding_curve_error(self, err: Optional[str]) -> bool:
        """Detecta se o erro indica que o token migrou para Raydium (bonding curve completa)."""
        if not err:
            return False
        err_lower = err.lower()
        return (
            "bondingcurve" in err_lower
            or "bonding curve" in err_lower
            or "curve complete" in err_lower
            or "migrated" in err_lower
            or "raydium" in err_lower
        )

    async def _get_balance_raw(self, token_address: str) -> Optional[int]:
        """Saldo real via getTokenAccountsByOwner (evita -32602)."""
        from app.execution.jupiter_swap import get_token_balance_raw
        rpc_url = settings.get_rpc_url()
        result = await get_token_balance_raw(rpc_url, self.wallet_address, token_address)
        return result[0] if result else None

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
        Vende tokens: PumpPortal → Raydium → Jupiter V6 (fallback para 400/graduados).
        amount: "100%" (recomendado) ou quantidade em tokens.
        """
        if settings.DRY_RUN:
            logger.info(f"[DRY_RUN] SELL {token_address} amount={amount} slippage={slippage}%")
            return True

        amount_use = amount
        if amount in ("100%", "100") or (isinstance(amount, str) and "100" in str(amount)):
            amount_use = "100%"

        try:
            success, error = await self._execute(
                action="sell",
                token_address=token_address,
                amount=amount_use,
                denominated_in_sol=denominated_in_sol,
                slippage=slippage,
                priority_fee=priority_fee,
                pool=pool,
            )
            if success:
                return True

            # Retry pool=raydium
            if pool != "raydium":
                if self._is_bonding_curve_error(error):
                    logger.info("🔄 Token migrou para Raydium, tentando pool=raydium")
                else:
                    logger.info("🔄 Venda falhou, tentando pool=raydium")
                success2, error2 = await self._execute(
                    action="sell",
                    token_address=token_address,
                    amount=amount_use,
                    denominated_in_sol=denominated_in_sol,
                    slippage=20.0,
                    priority_fee=priority_fee,
                    pool="raydium",
                )
                if success2:
                    return True
                error = error2

            # Jupiter V6 obrigatório (400 ou qualquer falha PumpPortal)
            is_400 = "400" in str(error) or "bad request" in (str(error) or "").lower()
            if is_400 or self._is_bonding_curve_error(error):
                balance_raw = await self._get_balance_raw(token_address)
                if balance_raw and balance_raw > 0:
                    logger.info(f"🔄 Jupiter V6: vendendo {token_address[:12]}... (slippage 20%)")
                    from app.execution.jupiter_swap import sell_via_jupiter
                    ok, _ = await sell_via_jupiter(
                        self.wallet_address,
                        self.wallet_kp,
                        token_address,
                        balance_raw,
                        slippage_bps=2000,
                    )
                    return ok
                logger.warning("Jupiter: saldo zero ou indisponível")

            return False
        except Exception as e:
            logger.error(f"Erro ao executar VENDA: {e}", exc_info=True)
            return False

    async def close(self):
        """Fecha cliente HTTP."""
        await self.client.aclose()
