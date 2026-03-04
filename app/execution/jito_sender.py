"""
Jito Bundle Sender — proteção MEV via Jito Block Engine.
Docs: https://jito-labs.gitbook.io/mev/searcher-resources/json-rpc-api-reference

Apenas ativo quando USE_JITO=true (Railway var). Padrão: false.

Fluxo:
1. PumpPortal devolve tx não-assinada (trade-local)
2. Assinamos a tx principal
3. Construímos uma tip tx (SOL → conta Jito aleatória, JITO_TIP_LAMPORTS)
4. Submetemos bundle [main_tx, tip_tx] ao block engine
5. Retornamos o txid da tx principal para confirmação normal via _confirm_tx
"""
import base64
import random
import struct
from typing import Optional

import httpx

from app.core.config import settings
from app.core.logger import setup_logger

logger = setup_logger(__name__)

_JITO_BUNDLE_URL = "https://mainnet.block-engine.jito.wtf/api/v1/bundles"

# Tip accounts oficiais do Jito (rotação aleatória para evitar colisões)
_TIP_ACCOUNTS = [
    "96gYZGLnJYVFmbjzopPSU6QiEV5fGqZNyN9nmNhvrZU5",
    "HFqU5x63VTqvB8BoaaumPZMm1bN5DhKGpxJNiBFyTBGN",
    "Cw8CFyM9FkoMi7K7Crf6HNQqf4uEMzpKw6QNghXLvLkY",
    "ADaUMid9yfUytqMBgopwjb2DTLSokTSzL1nt5HuZDR5zE",
    "DfXygSm4jCyNCybVYYK6DwvWqjKee8pbDmJGcLWNDXjh",
    "ADuUkR4vqLUMWXxW9gh6D6L8pMSawimctcNZ5pGwDcEt",
    "DttWaMuVvTiduZRnguLF7jNxTgiMBZ1hyAumKUiL2KRL",
]

_SYSTEM_PROGRAM_ID = "11111111111111111111111111111111"


class JitoSender:
    """Submete compras como bundles ao Jito Block Engine para proteção MEV."""

    def __init__(self, rpc_url: str, wallet_keypair):
        self.rpc_url = rpc_url
        self.keypair = wallet_keypair

    async def _get_recent_blockhash(self) -> Optional[str]:
        """Retorna o blockhash recente do RPC Solana."""
        body = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "getLatestBlockhash",
            "params": [{"commitment": "confirmed"}],
        }
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                r = await client.post(self.rpc_url, json=body)
                r.raise_for_status()
                data = r.json()
            return data["result"]["value"]["blockhash"]
        except Exception as e:
            logger.warning(f"Jito getLatestBlockhash: {e}")
            return None

    @staticmethod
    def _encode_transfer_data(lamports: int) -> bytes:
        """Encode instrução SystemProgram.Transfer: index=2 (u32 LE) + amount (u64 LE)."""
        return struct.pack("<IQ", 2, lamports)

    async def send_bundle(self, unsigned_tx_bytes: bytes) -> Optional[str]:
        """
        Assina a tx principal, constrói tip tx e submete bundle ao Jito.
        Retorna o txid da tx principal (para confirmar via _confirm_tx normal).
        Retorna None se falhar.
        """
        try:
            from solders.transaction import VersionedTransaction
            from solders.pubkey import Pubkey
            from solders.hash import Hash
            from solders.instruction import Instruction, AccountMeta
            from solders.message import MessageV0
        except ImportError as e:
            logger.error(f"Jito: solders não disponível — {e}")
            return None

        tip_lamports = getattr(settings, "JITO_TIP_LAMPORTS", 50000)
        tip_account_str = random.choice(_TIP_ACCOUNTS)

        try:
            # 1) Assinar transação principal
            main_tx = VersionedTransaction.from_bytes(unsigned_tx_bytes)
            signed_main = VersionedTransaction(main_tx.message, [self.keypair])
            txid = str(signed_main.signatures[0])

            # 2) Blockhash fresco para a tip tx
            blockhash_str = await self._get_recent_blockhash()
            if not blockhash_str:
                logger.warning("Jito: sem blockhash — abortando bundle, enviando tx diretamente")
                return None

            # 3) Construir e assinar tip transaction
            wallet_pk = self.keypair.pubkey()
            tip_pk = Pubkey.from_string(tip_account_str)
            sys_pk = Pubkey.from_string(_SYSTEM_PROGRAM_ID)
            tip_ix = Instruction(
                program_id=sys_pk,
                data=self._encode_transfer_data(tip_lamports),
                accounts=[
                    AccountMeta(pubkey=wallet_pk, is_signer=True, is_writable=True),
                    AccountMeta(pubkey=tip_pk, is_signer=False, is_writable=True),
                ],
            )
            recent_hash = Hash.from_string(blockhash_str)
            tip_message = MessageV0.try_compile(
                payer=wallet_pk,
                instructions=[tip_ix],
                address_lookup_table_accounts=[],
                recent_blockhash=recent_hash,
            )
            tip_tx = VersionedTransaction(tip_message, [self.keypair])

            # 4) Serializar ambas as txs em base64
            main_b64 = base64.b64encode(bytes(signed_main)).decode()
            tip_b64 = base64.b64encode(bytes(tip_tx)).decode()

            # 5) Submeter bundle [main_tx, tip_tx]
            bundle_payload = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "sendBundle",
                "params": [[main_b64, tip_b64]],
            }
            async with httpx.AsyncClient(timeout=15.0) as client:
                r = await client.post(_JITO_BUNDLE_URL, json=bundle_payload)
                r.raise_for_status()
                resp_data = r.json()

            if "error" in resp_data:
                logger.error(f"Jito bundle recusado: {resp_data['error']}")
                return None

            bundle_id = resp_data.get("result", "?")
            logger.info(
                f"✅ Jito bundle submetido: id={bundle_id} | tip={tip_lamports} lamports "
                f"→ {tip_account_str[:12]}... | txid={txid[:16]}..."
            )
            return txid

        except Exception as e:
            logger.error(f"Jito send_bundle: {e}", exc_info=True)
            return None
