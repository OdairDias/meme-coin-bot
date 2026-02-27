"""
Auto-cleanup no startup: vende tokens na carteira que não estão em positions.json.
"""
import asyncio
from typing import List, Set

from app.core.config import settings
from app.core.logger import setup_logger
from app.core.security import get_wallet_keypair
from app.execution.force_sell import get_all_token_accounts
from app.execution.positions_persistence import load_positions
from app.execution.jupiter_swap import sell_via_jupiter

logger = setup_logger(__name__)

SOL_MINT = "So11111111111111111111111111111111111111112"


async def run_startup_cleanup() -> dict:
    """
    Verifica se há tokens na carteira que não estão em positions.json.
    Se houver, vende-os via Jupiter (resíduos de sessões anteriores).
    Retorna dict com resultado.
    """
    if not getattr(settings, "AUTO_CLEANUP_ON_STARTUP", False):
        return {"skipped": True, "reason": "AUTO_CLEANUP_ON_STARTUP=false"}

    wallet_kp = get_wallet_keypair(settings.WALLET_PRIVATE_KEY)
    wallet = str(wallet_kp.pubkey())
    rpc_url = settings.get_rpc_url()

    try:
        # Tokens na carteira
        wallet_tokens = await get_all_token_accounts(rpc_url, wallet)
        wallet_mints: Set[str] = {t["mint"] for t in wallet_tokens}

        # Tokens em positions.json (posições ativas)
        positions = load_positions()
        known_mints: Set[str] = set(positions.keys())

        # Resíduos = na carteira mas não em positions
        residue_mints = wallet_mints - known_mints
        if not residue_mints:
            logger.info("Startup cleanup: nenhum resíduo na carteira")
            return {"skipped": False, "residues": 0, "sold": 0}

        residue_accounts = [t for t in wallet_tokens if t["mint"] in residue_mints]
        logger.info(f"Startup cleanup: {len(residue_accounts)} token(s) residual(is) — vendendo via Jupiter")

        ok_count = 0
        for acc in residue_accounts:
            mint = acc["mint"]
            amount_raw = acc["amount_raw"]
            try:
                ok, _ = await sell_via_jupiter(
                    wallet,
                    wallet_kp,
                    mint,
                    amount_raw,
                    slippage_bps=2500,  # 25%
                )
                if ok:
                    ok_count += 1
            except Exception as e:
                logger.warning(f"Cleanup {mint[:12]}... falhou: {e}")
            await asyncio.sleep(2)

        return {
            "skipped": False,
            "residues": len(residue_accounts),
            "sold": ok_count,
        }
    except Exception as e:
        logger.error(f"Startup cleanup erro: {e}", exc_info=True)
        return {"skipped": False, "error": str(e)}
