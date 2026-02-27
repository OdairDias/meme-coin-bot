"""
Jupiter Swap V6 — Venda de tokens para SOL (Pump.fun e Raydium)
Usado como fallback quando PumpPortal retorna 400 (token graduado).
API: https://quote-api.jup.ag/v6/quote e https://api.jup.ag/swap/v1/swap
"""
import base64
from typing import Optional, Tuple
import httpx

from solders.pubkey import Pubkey

from app.core.config import settings
from app.core.logger import setup_logger

logger = setup_logger(__name__)

SOL_MINT = "So11111111111111111111111111111111111111112"
# Quote v6 e Swap v1 (compatíveis)
JUPITER_QUOTE_URL = "https://quote-api.jup.ag/v6/quote"
JUPITER_SWAP_URL = "https://api.jup.ag/swap/v1/swap"
ATO_PROGRAM = Pubkey.from_string("ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJA8knL")
TOKEN_PROGRAM = Pubkey.from_string("TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA")


def get_associated_token_address(owner: Pubkey, mint: Pubkey) -> Pubkey:
    """Deriva o endereço da Associated Token Account."""
    addr, _ = Pubkey.find_program_address(
        [bytes(owner), bytes(TOKEN_PROGRAM), bytes(mint)],
        ATO_PROGRAM,
    )
    return addr


async def get_token_balance_raw(
    rpc_url: str,
    wallet_pubkey: str,
    mint: str,
    fallback_amount_raw: Optional[int] = None,
) -> Optional[Tuple[int, int]]:
    """
    Obtém saldo real do token na carteira.
    1) getTokenAccountsByOwner com filtro mint (encontra conta real, evita -32602)
    2) getTokenAccountBalance na ATA derivada
    3) getAccountInfo na ATA
    4) fallback_amount_raw (ex: positions.json) como último recurso
    Retorna (amount_raw, decimals) ou None.
    """
    # 1) getTokenAccountsByOwner com filtro mint — encontra conta independente de ATA
    try:
        body = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "getTokenAccountsByOwner",
            "params": [
                wallet_pubkey,
                {"mint": mint},
                {"encoding": "jsonParsed"},
            ],
        }
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.post(rpc_url, json=body)
            r.raise_for_status()
            data = r.json()

        if "error" in data:
            logger.debug(f"getTokenAccountsByOwner erro: {data['error']}")
        else:
            total_raw = 0
            decimals = 6
            for item in data.get("result", {}).get("value", []):
                try:
                    parsed = item.get("account", {}).get("data", {}).get("parsed", {}).get("info", {})
                    token_amount = parsed.get("tokenAmount", {})
                    amount_str = token_amount.get("amount", "0")
                    decimals = int(token_amount.get("decimals", 6))
                    amt = int(amount_str)
                    if amt > 0:
                        total_raw += amt
                except Exception:
                    continue
            if total_raw > 0:
                return total_raw, decimals
    except Exception as e:
        logger.debug(f"getTokenAccountsByOwner erro: {e}")

    # 2) getTokenAccountBalance na ATA derivada
    try:
        owner = Pubkey.from_string(wallet_pubkey)
        mint_pk = Pubkey.from_string(mint)
        ata = get_associated_token_address(owner, mint_pk)
        ata_str = str(ata)

        body = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "getTokenAccountBalance",
            "params": [ata_str],
        }
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.post(rpc_url, json=body)
            r.raise_for_status()
            data = r.json()

        if "error" in data:
            logger.debug(f"getTokenAccountBalance ATA erro: {data['error']}")
        else:
            value = data.get("result", {}).get("value")
            if value:
                amount_str = value.get("amount", "0")
                decimals = int(value.get("decimals", 6))
                amount_raw = int(amount_str)
                if amount_raw > 0:
                    return amount_raw, decimals
    except Exception as e:
        logger.debug(f"getTokenAccountBalance erro: {e}")

    # 3) getAccountInfo na ATA (parse manual se necessário)
    try:
        owner = Pubkey.from_string(wallet_pubkey)
        mint_pk = Pubkey.from_string(mint)
        ata = get_associated_token_address(owner, mint_pk)
        ata_str = str(ata)

        body = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "getAccountInfo",
            "params": [ata_str, {"encoding": "jsonParsed"}],
        }
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.post(rpc_url, json=body)
            r.raise_for_status()
            data = r.json()

        if "error" not in data:
            parsed = data.get("result", {}).get("value", {}).get("data", {}).get("parsed", {}).get("info", {})
            token_amount = parsed.get("tokenAmount", {})
            amount_str = token_amount.get("amount", "0")
            decimals = int(token_amount.get("decimals", 6))
            amount_raw = int(amount_str)
            if amount_raw > 0:
                return amount_raw, decimals
    except Exception as e:
        logger.debug(f"getAccountInfo ATA erro: {e}")

    # 4) Último recurso: saldo do positions.json
    if fallback_amount_raw and fallback_amount_raw > 0:
        logger.info(f"Usando amount_raw do positions.json para {mint[:12]}... (chain indisponível)")
        return fallback_amount_raw, 6  # decimals default

    return None


async def get_sell_quote(
    input_mint: str,
    amount_raw: int,
    slippage_bps: int = 1000,
) -> Optional[dict]:
    """
    Obtém quote da Jupiter para vender token → SOL.
    amount_raw = quantidade em unidades atômicas (sem decimals).
    slippage_bps: 1000 = 10%, 2000 = 20%.
    """
    try:
        params = {
            "inputMint": input_mint,
            "outputMint": SOL_MINT,
            "amount": str(amount_raw),
            "slippageBps": slippage_bps,
        }
        async with httpx.AsyncClient(timeout=15.0) as client:
            r = await client.get(JUPITER_QUOTE_URL, params=params)
            if r.status_code != 200:
                logger.warning(f"Jupiter quote {r.status_code}: {r.text[:200]}")
                return None
            return r.json()
    except Exception as e:
        logger.warning(f"Jupiter quote erro: {e}")
        return None


async def get_swap_transaction(
    quote: dict,
    user_public_key: str,
) -> Optional[bytes]:
    """
    Obtém transação serializada da Jupiter (swap v1).
    Retorna bytes da transação para assinar e enviar.
    """
    try:
        payload = {
            "quoteResponse": quote,
            "userPublicKey": user_public_key,
            "dynamicComputeUnitLimit": True,
            "prioritizationFeeLamports": "auto",
        }
        async with httpx.AsyncClient(timeout=20.0) as client:
            r = await client.post(JUPITER_SWAP_URL, json=payload)
            if r.status_code != 200:
                logger.warning(f"Jupiter swap {r.status_code}: {r.text[:300]}")
                return None
            data = r.json()
        swap_tx_b64 = data.get("swapTransaction")
        if not swap_tx_b64:
            return None
        return base64.b64decode(swap_tx_b64)
    except Exception as e:
        logger.warning(f"Jupiter swap erro: {e}")
        return None


async def sell_via_jupiter(
    wallet_pubkey: str,
    wallet_keypair,
    mint: str,
    amount_raw: int,
    slippage_bps: int = 1000,
) -> Tuple[bool, Optional[str]]:
    """
    Executa venda token → SOL via Jupiter.
    Retorna (success, txid ou error_message).
    """
    quote = await get_sell_quote(mint, amount_raw, slippage_bps)
    if not quote:
        return False, "Jupiter quote falhou"

    tx_bytes = await get_swap_transaction(quote, wallet_pubkey)
    if not tx_bytes:
        return False, "Jupiter swap tx falhou"

    try:
        from solders.transaction import VersionedTransaction

        raw_tx = VersionedTransaction.from_bytes(tx_bytes)
        signed_tx = VersionedTransaction(raw_tx.message, [wallet_keypair])
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
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.post(rpc_url, json=body)
            r.raise_for_status()
            data = r.json()

        if "error" in data:
            err = data["error"]
            err_msg = err.get("message", str(err))[:200]
            logger.error(f"Jupiter sell RPC erro: {err_msg}")
            return False, err_msg

        txid = data.get("result")
        if txid:
            logger.info(f"✅ Jupiter SELL executada: {mint[:12]}... tx={txid}")
            return True, txid
        return False, "RPC sem txid"
    except Exception as e:
        logger.error(f"Jupiter sell erro: {e}", exc_info=True)
        return False, str(e)
