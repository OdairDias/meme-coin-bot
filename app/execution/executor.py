"""
Executor de trades via PumpPortal API + Jupiter V6 (fallback para tokens graduados)
Documentação: https://pumpportal.fun/local-trading-api/trading-api
Jupiter: fallback obrigatório para 400 (token migrou Pump→Raydium).
Saldo real via getTokenAccountBalance antes de vender; sem cache para decisão de venda (evita 6022 e gas).
Erros on-chain: 6005 = bonding curve migrou para Raydium; 6024 = SlippageExceeded/Overflow; 6022 = Sell zero amount.
"""
import asyncio
import base64
import time
import httpx
from typing import Dict, Any, Union, Optional, Tuple

from app.core.config import settings
from app.core.security import get_wallet_keypair
from app.core.logger import setup_logger

logger = setup_logger(__name__)

# Tempo máximo para aguardar confirmação da tx (segundos)
_TX_CONFIRM_TIMEOUT = 45
# Intervalo entre polls de status (segundos)
_TX_CONFIRM_POLL_INTERVAL = 2
# Códigos de erro do programa Pump.fun (on-chain)
_PUMP_ERR_BONDING_CURVE_COMPLETE = 6005
_PUMP_ERR_SLIPPAGE_OR_OVERFLOW = 6024
_PUMP_ERR_SELL_ZERO_AMOUNT = 6022

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
        payload = {
            "publicKey": self.wallet_address,
            "action": action,
            "mint": mint,
            "amount": amount,
            "denominatedInSol": "true" if denominated_in_sol else "false",
            "slippage": slippage,
            "priorityFee": priority_fee,
            "pool": pool,
        }
        # Log do payload para debug
        logger.debug(f"📤 PumpPortal payload: action={action} amount={amount} slippage={slippage}% pool={pool}")
        return payload

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

    def _parse_tx_error_code(self, meta_err: Any) -> Optional[int]:
        """
        Extrai código de erro custom (ex: 6005, 6024) de meta.err da transação.
        meta.err pode ser: null, {"InstructionError": [index, {"Custom": code}]}, ou string.
        """
        if meta_err is None:
            return None
        if isinstance(meta_err, dict):
            instr_err = meta_err.get("InstructionError")
            if isinstance(instr_err, (list, tuple)) and len(instr_err) >= 2:
                inner = instr_err[1]
                if isinstance(inner, dict) and "Custom" in inner:
                    return int(inner["Custom"])
        return None

    async def _confirm_tx(self, txid: str) -> Tuple[bool, Optional[str]]:
        """
        Aguarda a tx ser finalizada e verifica se executou com sucesso.
        Retorna (True, None) se sucesso, (False, mensagem) se falhou on-chain (ex: 6005, 6024).
        """
        rpc_url = settings.get_rpc_url()
        deadline = time.monotonic() + _TX_CONFIRM_TIMEOUT
        while time.monotonic() < deadline:
            try:
                body = {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "getSignatureStatuses",
                    "params": [[txid]],
                }
                async with httpx.AsyncClient(timeout=10.0) as client:
                    r = await client.post(rpc_url, json=body)
                    r.raise_for_status()
                    data = r.json()
                if "error" in data:
                    await asyncio.sleep(_TX_CONFIRM_POLL_INTERVAL)
                    continue
                result = data.get("result", {})
                value = (result.get("value") or [None])[0]
                if value is None:
                    await asyncio.sleep(_TX_CONFIRM_POLL_INTERVAL)
                    continue
                confirmation_status = (value.get("confirmationStatus") or "").lower()
                if confirmation_status == "finalized":
                    break
                if value.get("err") is not None:
                    # Tx já rejeitada; buscar detalhe via getTransaction
                    break
                await asyncio.sleep(_TX_CONFIRM_POLL_INTERVAL)
            except Exception as e:
                logger.debug(f"getSignatureStatuses: {e}")
                await asyncio.sleep(_TX_CONFIRM_POLL_INTERVAL)

        try:
            body = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "getTransaction",
                "params": [
                    txid,
                    {"encoding": "json", "maxSupportedTransactionVersion": 0},
                ],
            }
            async with httpx.AsyncClient(timeout=15.0) as client:
                r = await client.post(rpc_url, json=body)
                r.raise_for_status()
                data = r.json()
            if "error" in data:
                return False, data.get("error", {}).get("message", "RPC error")
            result = data.get("result")
            if not result:
                return False, "Tx não encontrada (timeout ou não finalizada)"
            meta = result.get("meta")
            if not meta:
                return True, None
            err = meta.get("err")
            if err is None:
                return True, None
            code = self._parse_tx_error_code(err)
            if code == _PUMP_ERR_BONDING_CURVE_COMPLETE:
                return False, "6005: Bonding curve completou; liquidez migrou para Raydium"
            if code == _PUMP_ERR_SLIPPAGE_OR_OVERFLOW:
                return False, "6024: Slippage excedido ou Overflow (preço moveu demais)"
            if code == _PUMP_ERR_SELL_ZERO_AMOUNT:
                return False, "6022: Sell zero amount (saldo zero na chain)"
            return False, str(err)[:200]
        except Exception as e:
            logger.warning(f"Erro ao confirmar tx {txid[:16]}...: {e}")
            return False, str(e)[:200]

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
                if not txid:
                    return False, "Falha ao assinar/enviar tx"
                logger.info(f"⏳ Aguardando confirmação on-chain da tx {txid[:20]}...")
                confirmed, confirm_err = await self._confirm_tx(txid)
                if confirmed:
                    logger.info(f"✅ {action.upper()} executada: {token_address} tx={txid}")
                    return True, None
                logger.error(f"❌ {action.upper()} falhou on-chain: {confirm_err}")
                return False, confirm_err or "Tx falhou na blockchain"

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

        if (pool or "auto").lower() == "raydium":
            logger.info(f"🔄 Compra via Raydium (token já migrado da bonding curve): {token_address[:12]}...")

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
            logger.info(f"⏳ tx enviada. Atestando recebimento do token {token_address[:12]} em background (pode demorar)...")
            
            async def _check_balance_async():
                # Loop de verificação não-bloqueante de até 60 segundos
                for j in range(20):
                    await asyncio.sleep(3.0)
                    try:
                        balance_raw = await self._get_real_token_balance_raw(token_address)
                        if balance_raw and balance_raw > 0:
                            logger.info(f"✅ Saldo confirmado na blockchain! {token_address[:12]} está na carteira.")
                            return
                        logger.debug(f"Aguardando indexação do {token_address[:12]} na carteira... {j+1}/20")
                    except Exception as ex:
                        logger.debug(f"Erro ao checar saldo de {token_address[:12]}: {ex}")
                logger.warning(f"⚠️ Aviso: O saldo de {token_address[:12]} não apareceu após 60s, mas a tx de compra foi iniciada.")

            # Roda a verificação de saldo em background
            asyncio.create_task(_check_balance_async())

            # Se _execute() retornou success = True, assumimos que a compra foi feita e registramos na PositionManager agora
            return True

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

    def _is_sell_zero_error(self, err: Optional[str]) -> bool:
        """Detecta erro 6022 (Sell zero amount). Não reenviar tx — fechar posição e evitar mais gas."""
        if not err:
            return False
        return "6022" in str(err) or "sell zero" in (str(err) or "").lower()

    async def _get_real_token_balance_raw(self, token_address: str, use_fallback: bool = True) -> Optional[int]:
        """
        Consulta saldo real na blockchain.
        use_fallback=False: não usa positions.json (evita vender com saldo 0 e queimar gas em 6022).
        """
        from app.execution.jupiter_swap import get_token_balance_raw
        from app.execution.positions_persistence import get_position_amount_raw, update_amount_raw

        rpc_url = settings.get_rpc_url()
        fallback = get_position_amount_raw(token_address) if use_fallback else None
        result = await get_token_balance_raw(
            rpc_url, self.wallet_address, token_address, fallback_amount_raw=fallback
        )
        if result:
            amount_raw, _ = result
            if use_fallback:
                update_amount_raw(token_address, amount_raw)
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
        Vende tokens: PumpPortal → Raydium → Jupiter V6 (fallback para 400/graduados).
        amount: "100%" (recomendado) ou quantidade em tokens.
        Saldo real consultado antes de vender.
        """
        if settings.DRY_RUN:
            logger.info(f"[DRY_RUN] SELL {token_address} amount={amount} slippage={slippage}%")
            return True

        # 1) Resolver amount: 100% = saldo total
        amount_to_use = "100%" if (amount in ("100%", "100") or (isinstance(amount, str) and "100" in str(amount))) else amount
        amount_raw_to_sell: Optional[int] = None
        if amount_to_use == "100%":
            balance_raw = await self._get_real_token_balance_raw(token_address, use_fallback=False)
            if not balance_raw or balance_raw <= 0:
                logger.warning(f"Saldo zero ou conta inexistente para {token_address[:12]}... (não enviando tx de venda)")
                raise ValueError("ZERO_BALANCE")
            amount_raw_to_sell = balance_raw

        slippage_first = 10.0
        slippage = slippage if slippage > 0 else slippage_first
        slippage_retry = 20.0
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

            # 6022 = Sell zero amount: saldo já é 0 na chain
            if self._is_sell_zero_error(error):
                logger.warning("6022 detectado: saldo zero na chain, fechando posição sem reenviar tx")
                return True

            # 3) Retry PumpPortal com pool=raydium (slippage 20%)
            if pool != "raydium":
                if self._is_bonding_curve_error(error):
                    logger.info("🔄 Token migrou para Raydium, tentando pool=raydium (slippage 20%)")
                else:
                    logger.info("🔄 Venda falhou, tentando pool=raydium")
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

            # 6022 após retry raydium: não tentar Jupiter
            if self._is_sell_zero_error(error):
                logger.warning("6022 detectado (após raydium): fechando posição sem Jupiter")
                return True

            # 4) Jupiter V6 quando PumpPortal falha (400, graduação)
            if amount_raw_to_sell is None:
                amount_raw_to_sell = await self._get_real_token_balance_raw(token_address, use_fallback=True)
            if amount_raw_to_sell and amount_raw_to_sell > 0:
                logger.info(f"🔄 Jupiter V6: vendendo {token_address[:12]}... (slippage 20%)")
                from app.execution.jupiter_swap import sell_via_jupiter
                ok, _ = await sell_via_jupiter(
                    self.wallet_address,
                    self.wallet_kp,
                    token_address,
                    amount_raw_to_sell,
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
