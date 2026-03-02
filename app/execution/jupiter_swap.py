"""
Jupiter Swap V6 — Venda de tokens para SOL (Pump.fun e Raydium)
Fallback quando PumpPortal retorna 400 (token graduado).
"""
import base64
from typing import Optional, Tuple
import httpx

from solders.pubkey import Pubkey

from app.core.config import settings
from app.core.logger import setup_logger

logger = setup_logger(__name__)

SOL_MINT = "So11111111111111111111111111111111111111112"
JUPITER_QUOTE_URL = "https://quote-api.jup.ag/v6/quote"
JUPITER_SWAP_URL = "https://api.jup.ag/swap/v1/swap"
ATO_PROGRAM = Pubkey.from_string("ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJA8knL")
TOKEN_PROGRAM = Pubkey.from_string("TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA")


def get_associated_token_address(owner: Pubkey, mint: Pubkey) -> Pubkey:
    addr, _ = Pubkey.find_program_address(
        [bytes(owner), bytes(TOKEN_PROGRAM), bytes(mint)],
        ATO_PROGRAM,
    )
    return addr


async def get_token_balance_raw(rpc_url: str, wallet_pubkey: str, mint: str) -> Optional[Tuple[int, int]]:
    """
    1) getTokenAccountsByOwner com filtro mint (evita -32602)
    2) getTokenAccountBalance na ATA
    """
    # 1) getTokenAccountsByOwner
    try:
        body = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "getTokenAccountsByOwner",
            "params": [wallet_pubkey, {"mint": mint}, {"encoding": "jsonParsed"}],
        }
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.post(rpc_url, json=body)
            r.raise_for_status()
            data = r.json()
        if "error" not in data:
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
        logger.debug(f"getTokenAccountsByOwner: {e}")

    # 2) getTokenAccountBalance na ATA
    try:
        owner = Pubkey.from_string(wallet_pubkey)
        mint_pk = Pubkey.from_string(mint)
        ata = get_associated_token_address(owner, mint_pk)
        body = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "getTokenAccountBalance",
            "params": [str(ata)],
        }
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.post(rpc_url, json=body)
            r.raise_for_status()
            data = r.json()
        if "error" not in data:
            value = data.get("result", {}).get("value")
            if value:
                amount_str = value.get("amount", "0")
                decimals = int(value.get("decimals", 6))
                amount_raw = int(amount_str)
                if amount_raw > 0:
                    return amount_raw, decimals
    except Exception as e:
        logger.debug(f"getTokenAccountBalance: {e}")

    return None


async def get_sell_quote(input_mint: str, amount_raw: int, slippage_bps: int = 2000) -> Optional[dict]:
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
                return None
            return r.json()
    except Exception:
        return None


async def sell_via_jupiter(
    wallet_pubkey: str,
    wallet_keypair,
    mint: str,
    amount_raw: int,
    slippage_bps: int = 2000,
) -> Tuple[bool, Optional[str]]:
    quote = await get_sell_quote(mint, amount_raw, slippage_bps)
    if not quote:
        return False, "Jupiter quote falhou"
    try:
        payload = {
            "quoteResponse": quote,
            "userPublicKey": wallet_pubkey,
            "dynamicComputeUnitLimit": True,
            "prioritizationFeeLamports": "auto",
        }
        async with httpx.AsyncClient(timeout=20.0) as client:
            r = await client.post(JUPITER_SWAP_URL, json=payload)
            if r.status_code != 200:
                return False, f"Jupiter swap {r.status_code}"
            data = r.json()
        swap_tx_b64 = data.get("swapTransaction")
        if not swap_tx_b64:
            return False, "Sem swapTransaction"
        tx_bytes = base64.b64decode(swap_tx_b64)

        from solders.transaction import VersionedTransaction

        raw_tx = VersionedTransaction.from_bytes(tx_bytes)
        signed_tx = VersionedTransaction(raw_tx.message, [wallet_keypair])
        b64 = base64.b64encode(bytes(signed_tx)).decode("ascii")

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
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.post(rpc_url, json=body)
            r.raise_for_status()
            data = r.json()
        if "error" in data:
            return False, str(data["error"].get("message", data["error"]))
        txid = data.get("result")
        if txid:
            logger.info(f"✅ Jupiter SELL: {mint[:12]}... tx={txid}")
            return True, txid
        return False, "RPC sem txid"
    except Exception as e:
        logger.error(f"Jupiter sell: {e}")
        return False, str(e)
