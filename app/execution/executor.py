"""
Executor de trades via PumpPortal API + Jupiter V6 (fallback para tokens graduados)
Documentação: https://pumpportal.fun/local-trading-api/trading-api
Jupiter: fallback obrigatório para 400 (token migrou Pump→Raydium).
Saldo real via getTokenAccountBalance antes de vender.
"""
import base64
import httpx
from typing import Dict, Any, Union, Optional

from app.core.config import settings
from app.core.security import get_wallet_keypair
from app.core.logger import setup_logger

logger = setup_logger(__name__)

# Compute units típicos para uma swap (conversão priority fee Helius microlamports → SOL)
_DEFAULT_CU_SWAP = 200_000


def _is_trade_local() -> bool:
    """True se estiver usando o endpoint trade-local (resposta = tx serializada em bytes)."""
    return "trade-local" in (settings.PUMP_PORTAL_API or "")


class Executor:
    """Executa ordens de compra/venda via PumpPortal (trade-local ou Lightning)."""

    def __init__(self):
        self.client = httpx.AsyncClient(timeout=30.0)
        self.wallet_kp = get_wallet_keypair(settings.WALLET_PRIVATE_KEY)
        self.wallet_address = str(self.wallet_kp.pubkey())
        self._helius_rpc = "helius" in (settings.get_rpc_url() or "").lower()
        logger.info(f"Executor inicializado. Wallet: {self.wallet_address[:8]}... (RPC: {'Helius' if self._helius_rpc else 'público'})")

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

    async def _get_helius_priority_fee_sol(self) -> float:
        """
        Obtém taxa de prioridade recomendada da Helius (getPriorityFeeEstimate).
        Retorno em SOL para o PumpPortal. Fallback competitivo: 0.0001 SOL.
        """
        url = settings.get_rpc_url()
        base_fallback = getattr(settings, "PRIORITY_FEE_FALLBACK_SOL", 0.0001)
        if "helius" not in url.lower():
            return base_fallback
        level = (getattr(settings, "PRIORITY_FEE_LEVEL", "veryhigh") or "veryhigh").strip().lower() # Default para veryHigh em memecoins
        level_map = {"min": "min", "low": "low", "medium": "medium", "high": "high", "veryhigh": "veryHigh", "unsafemax": "unsafeMax"}
        level_key = level_map.get(level) or "veryHigh"
        try:
            body = {
                "jsonrpc": "2.0",
                "id": "1",
                "method": "getPriorityFeeEstimate",
                "params": [
                    {
                        "accountKeys": [self.wallet_address],
                        "options": {"includeAllPriorityFeeLevels": True},
                    }
                ],
            }
            async with httpx.AsyncClient(timeout=10.0) as client:
                r = await client.post(url, json=body)
                r.raise_for_status()
                data = r.json()
            if "error" in data:
                logger.debug(f"Helius priority fee error: {data['error']}")
                return base_fallback
            result = data.get("result") or {}
            levels = result.get("priorityFeeLevels") or {}
            microlamports = levels.get(level_key) or result.get("priorityFeeEstimate") or 500_000
            # microlamports per CU → SOL para _DEFAULT_CU_SWAP CUs
            lamports = float(microlamports) * 1e-6 * _DEFAULT_CU_SWAP
            fee_sol = lamports / 1e9
            return max(0.00005, min(0.003, fee_sol)) # Max teto aumentado para 0.003 para garantir snipes rápidos
        except Exception as e:
            logger.debug(f"Helius priority fee fallback: {e}")
            return base_fallback

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
                    {
                        "encoding": "base64",
                        # Helius e outros RPCs privados não suportam preflight; enviamos direto
                        "skipPreflight": True,
                        "preflightCommitment": "confirmed",
                    },
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
        slippage: float = 0,
        priority_fee: float = 0,
        pool: str = "auto",
    ) -> bool:
        """
        Compra token via PumpPortal e verifica na blockchain o recebimento saldo antes de fechar o loop.
        amount: SOL se denominated_in_sol=True, tokens se False.
        """
        if settings.DRY_RUN:
            unit = "SOL" if denominated_in_sol else "tokens"
            logger.info(f"[DRY_RUN] BUY {token_address} amount={amount} {unit} slippage={slippage}%")
            return True

        # Memecoins requerem um slippage mais solto para compra inicial. Vamos garantir ao menos 15%.
        def_slippage = getattr(settings, 'DEFAULT_SLIPPAGE', 15.0)
        slippage = slippage if slippage > 0 else max(15.0, def_slippage)
        
        priority_fee = priority_fee if priority_fee > 0 else (
            await self._get_helius_priority_fee_sol() if self._helius_rpc else getattr(settings, "PRIORITY_FEE_FALLBACK_SOL", 0.0001)
        )
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
            if not success:
                return False

            import asyncio
            logger.info(f"⏳ Aguardando confirmação da blockchain para entrega do saldo de {token_address[:12]}...")
            
            # Ajuste de rate-limit: 8 checagens com 2.5s de intervalo (~20s max) para evitar bloqueio da RPC
            for i in range(8):
                await asyncio.sleep(2.5)
                balance_raw = await self._get_real_token_balance_raw(token_address)
                if balance_raw and balance_raw > 0:
                    logger.info(f"✅ Compra confirmada na blockchain! tokens recebidos na carteira: {token_address[:12]}...")
                    return True
                logger.debug(f"Confirmando saldo de {token_address[:12]} na carteira... tentativa {i+1}/8")

            logger.error(f"❌ COMPRA FALHADA (Timeout): O token {token_address[:12]} não entrou na carteira após timeout. Provável cancelamento por Slippage na rede Solana.")
            return False

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

    def _is_400_or_graduation_error(self, err: Optional[str], status_code: int) -> bool:
        """Qualquer 400 ou erro de graduação → Jupiter fallback."""
        if status_code == 400:
            return True
        return self._is_bonding_curve_error(err)

    async def _get_real_token_balance_raw(self, token_address: str) -> Optional[int]:
        """Consulta saldo real na blockchain (getTokenAccountsByOwner, ATA, positions.json)."""
        from app.execution.jupiter_swap import get_token_balance_raw
        from app.execution.positions_persistence import get_position_amount_raw, update_amount_raw

        rpc_url = settings.get_rpc_url()
        fallback = get_position_amount_raw(token_address)
        result = await get_token_balance_raw(
            rpc_url, self.wallet_address, token_address, fallback_amount_raw=fallback
        )
        if result:
            amount_raw, _ = result
            update_amount_raw(token_address, amount_raw)  # cache para próximo fallback
            return amount_raw
        return None

    async def sell(
        self,
        token_address: str,
        amount: Union[float, str],
        denominated_in_sol: bool = False,
        slippage: float = 0,
        priority_fee: float = 0,
        pool: str = "auto",
    ) -> bool:
        """
        Vende tokens via PumpPortal; se 400 (token graduado) → Jupiter V6.
        Saldo real consultado antes de vender (getTokenAccountBalance).
        Slippage: 10% primeira tentativa, 20% retry/Jupiter.
        """
        if settings.DRY_RUN:
            logger.info(f"[DRY_RUN] SELL {token_address} amount={amount} slippage={slippage}%")
            return True

        # 1) Consultar saldo real quando amount="100%"
        amount_to_use = amount
        if amount == "100%" or (isinstance(amount, str) and "100" in str(amount)):
            balance_raw = await self._get_real_token_balance_raw(token_address)
            if not balance_raw or balance_raw <= 0:
                logger.warning(f"Saldo zero ou conta inexistente para {token_address[:12]}...")
                raise ValueError("ZERO_BALANCE")
            amount_to_use = "100%"  # PumpPortal aceita "100%"; Jupiter usa balance_raw

        slippage_first = 10.0  # 10% primeira tentativa
        slippage = slippage if slippage > 0 else slippage_first
        slippage_retry = 20.0  # 20% para retry/Jupiter (Raydium)
        priority_fee = priority_fee if priority_fee > 0 else (
            await self._get_helius_priority_fee_sol() if self._helius_rpc else 0.00005
        )

        try:
            # 2) Tentar PumpPortal (slippage 10%)
            success, error = await self._execute(
                action="sell",
                token_address=token_address,
                amount=amount_to_use,
                denominated_in_sol=denominated_in_sol,
                slippage=slippage,
                priority_fee=priority_fee,
                pool=pool,
            )
            if success:
                return True

            # 3) Retry PumpPortal com pool=raydium (slippage 20%)
            if pool != "raydium":
                if self._is_bonding_curve_error(error):
                    logger.info(f"🔄 Token migrou para Raydium, tentando pool=raydium (slippage 20%)")
                else:
                    logger.info(f"🔄 Venda falhou, tentando pool=raydium (fallback)")
                success2, error2 = await self._execute(
                    action="sell",
                    token_address=token_address,
                    amount=amount_to_use,
                    denominated_in_sol=denominated_in_sol,
                    slippage=slippage_retry,
                    priority_fee=priority_fee,
                    pool="raydium",
                )
                if success2:
                    return True
                error = error2

            # 4) Jupiter V6 obrigatório quando PumpPortal falha (400, graduação, etc.)
            balance_raw = await self._get_real_token_balance_raw(token_address)
            if balance_raw and balance_raw > 0:
                logger.info(f"🔄 Jupiter V6: vendendo {token_address[:12]}... (saldo real, slippage 20%)")
                from app.execution.jupiter_swap import sell_via_jupiter

                ok, _ = await sell_via_jupiter(
                    self.wallet_address,
                    self.wallet_kp,
                    token_address,
                    balance_raw,
                    slippage_bps=2000,  # 20%
                )
                return ok
            logger.warning("Jupiter: saldo zero, não há o que vender")

            return False
        except Exception as e:
            logger.error(f"Erro ao executar VENDA: {e}", exc_info=True)
            return False

    async def close(self):
        """Fecha cliente HTTP."""
        await self.client.aclose()
