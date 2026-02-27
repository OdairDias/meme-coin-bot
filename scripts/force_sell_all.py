#!/usr/bin/env python3
"""
Force Sell All — Emergência: vende todos os tokens da carteira para SOL via Jupiter.
Ignora estratégia, SL/TP, etc. Varre getTokenAccountsByOwner e executa swap para cada token.
Uso: python scripts/force_sell_all.py [--dry-run]
"""
import argparse
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()


async def main():
    parser = argparse.ArgumentParser(description="Force Sell All — vende todos os tokens para SOL")
    parser.add_argument("--dry-run", action="store_true", help="Apenas lista tokens, não executa venda")
    args = parser.parse_args()

    from app.core.config import settings
    from app.core.security import get_wallet_keypair
    from app.execution.force_sell import run_force_sell_all

    wallet = str(get_wallet_keypair(settings.WALLET_PRIVATE_KEY).pubkey())
    print(f"Carteira: {wallet[:16]}...")
    if args.dry_run:
        print("[DRY-RUN] Apenas listando tokens\n")

    result = await run_force_sell_all(dry_run=args.dry_run)
    if "error" in result:
        print(f"Erro: {result['error']}")
        return
    print(result.get("message", ""))
    if result.get("tokens"):
        for i, t in enumerate(result["tokens"], 1):
            print(f"  {i}. {t['mint'][:24]}... amount_raw={t['amount_raw']}")
    if result.get("results"):
        for r in result["results"]:
            status = "✅" if r.get("status") == "ok" else "❌"
            print(f"  {status} {r['mint'][:16]}... {r.get('txid', r.get('error', ''))}")


if __name__ == "__main__":
    asyncio.run(main())
