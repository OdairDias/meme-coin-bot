"""
Force Sell All — Emergência: vende todos os tokens da carteira para SOL via Jupiter.
"""
import asyncio
from typing import Dict, Any, List

import httpx

from app.core.config import settings
from app.core.security import get_wallet_keypair
from app.core.logger import setup_logger
from app.execution.jupiter_swap import sell_via_jupiter

logger = setup_logger(__name__)

SOL_MINT = "So11111111111111111111111111111111111111112"


async def get_all_token_accounts(rpc_url: str, wallet: str) -> List[Dict[str, Any]]:
    """
    Lista todas as contas de token da carteira com saldo > 0.
    Varre SPL Token e Token-2022 (memecoins podem usar ambos).
    """
    TOKEN_PROGRAM = "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"
    TOKEN_2022_PROGRAM = "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb"
    seen_mints: Dict[str, int] = {}  # mint -> amount_raw (soma se múltiplas contas)

    for program_id in [TOKEN_PROGRAM, TOKEN_2022_PROGRAM]:
        body = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "getTokenAccountsByOwner",
            "params": [
                wallet,
                {"programId": program_id},
                {"encoding": "jsonParsed"},
            ],
        }
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                r = await client.post(rpc_url, json=body)
                r.raise_for_status()
                data = r.json()
        except Exception as e:
            logger.debug(f"getTokenAccountsByOwner {program_id[:8]}... erro: {e}")
            continue

        if "error" in data:
            continue

        for item in data.get("result", {}).get("value", []):
            try:
                parsed = item.get("account", {}).get("data", {}).get("parsed", {}).get("info", {})
                mint = parsed.get("mint")
                token_amount = parsed.get("tokenAmount", {})
                amount_raw = int(token_amount.get("amount", 0))
                if not mint or amount_raw <= 0:
                    continue
                if mint == SOL_MINT:
                    continue
                seen_mints[mint] = seen_mints.get(mint, 0) + amount_raw
            except Exception:
                continue

    return [{"mint": m, "amount_raw": amt} for m, amt in seen_mints.items()]


async def run_force_sell_all(dry_run: bool = False) -> Dict[str, Any]:
    """
    Varre carteira e vende todos os tokens para SOL via Jupiter.
    Retorna dict com tokens encontrados e resultados.
    """
    wallet_kp = get_wallet_keypair(settings.WALLET_PRIVATE_KEY)
    wallet = str(wallet_kp.pubkey())
    rpc_url = settings.get_rpc_url()

    # Force Sell ignora DRY_RUN — é comando de emergência explícito
    # (DRY_RUN só bloqueia operações automáticas do bot)

    try:
        accounts = await get_all_token_accounts(rpc_url, wallet)
    except Exception as e:
        logger.error(f"Force sell: erro ao listar tokens: {e}")
        return {"error": str(e), "tokens": [], "sold": 0}

    if not accounts:
        return {"message": "Nenhum token com saldo", "tokens": [], "sold": 0}

    tokens_info = [{"mint": a["mint"], "amount_raw": a["amount_raw"]} for a in accounts]

    if dry_run:
        return {
            "message": f"[DRY-RUN] {len(accounts)} token(s) seriam vendidos",
            "tokens": tokens_info,
            "sold": 0,
        }

    ok_count = 0
    results = []
    for acc in accounts:
        mint = acc["mint"]
        amount_raw = acc["amount_raw"]
        try:
            ok, txid = await sell_via_jupiter(
                wallet,
                wallet_kp,
                mint,
                amount_raw,
                slippage_bps=2500,  # 25% para Raydium/alta volatilidade
            )
            if ok:
                ok_count += 1
                results.append({"mint": mint, "status": "ok", "txid": txid})
            else:
                results.append({"mint": mint, "status": "fail", "error": txid})
        except Exception as e:
            results.append({"mint": mint, "status": "error", "error": str(e)})
        await asyncio.sleep(2)

    return {
        "message": f"Concluído: {ok_count}/{len(accounts)} vendas",
        "tokens": tokens_info,
        "sold": ok_count,
        "results": results,
    }
