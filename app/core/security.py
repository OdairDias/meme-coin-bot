"""
Gerenciamento de chaves privadas e segurança
"""
import os
from typing import Optional
from solders.keypair import Keypair
import base58


def get_wallet_keypair(private_key: str) -> Keypair:
    """
    Converte private key (base58) para Keypair da Solana.
    A chave deve estar em formato base58 (começa com 5...)
    """
    try:
        # Decodificar base58 para bytes
        secret_bytes = base58.b58decode(private_key)
        if len(secret_bytes) != 64:
            raise ValueError("Private key deve ter 64 bytes após decodificação")
        return Keypair.from_secret_key(secret_bytes)
    except Exception as e:
        raise ValueError(f"Falha ao carregar private key: {e}")


def validate_private_key_format(private_key: str) -> bool:
    """Valida se a chave está em formato base58 válido."""
    try:
        decoded = base58.b58decode(private_key)
        return len(decoded) == 64
    except:
        return False