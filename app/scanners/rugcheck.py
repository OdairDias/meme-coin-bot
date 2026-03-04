"""
RugCheck — Verifica score de risco de tokens via RugCheck API (free tier).
Endpoint: GET https://api.rugcheck.xyz/v1/tokens/{mint}/report/summary

Score: 0-1000, onde maior = mais seguro.
RUGCHECK_MIN_SCORE define o limiar de aprovação (padrão 500).

Comportamento conservador: se a API falhar (timeout, 404, 5xx), o token PASSA
para não bloquear entradas por instabilidade da API de terceiro.
"""
import httpx
from typing import Tuple

from app.core.config import settings
from app.core.logger import setup_logger

logger = setup_logger(__name__)

_BASE_URL = "https://api.rugcheck.xyz/v1"
_TIMEOUT = 8.0


async def check_token(mint: str) -> Tuple[bool, int, str]:
    """
    Checa o score de risco do token no RugCheck.
    Retorna (passou, score, motivo).
    passed=True se score >= RUGCHECK_MIN_SCORE.

    Em caso de erro de API, retorna (True, 0, motivo) — falha aberta para não bloquear.
    """
    if not getattr(settings, "RUGCHECK_ENABLED", False):
        return True, 0, "RugCheck desabilitado"

    min_score = getattr(settings, "RUGCHECK_MIN_SCORE", 500)

    try:
        url = f"{_BASE_URL}/tokens/{mint}/report/summary"
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            r = await client.get(url)

        if r.status_code == 404:
            # Token muito novo — não indexado ainda; deixar passar
            logger.debug(f"RugCheck: {mint[:12]} não encontrado (novo demais) — passa")
            return True, 0, "Não encontrado (token novo)"

        if r.status_code != 200:
            logger.debug(f"RugCheck HTTP {r.status_code} para {mint[:12]} — falha aberta")
            return True, 0, f"HTTP {r.status_code}"

        data = r.json()

    except Exception as e:
        logger.debug(f"RugCheck timeout/erro para {mint[:12]}: {e} — falha aberta")
        return True, 0, f"Erro: {e}"

    # Score: normalizado 0-1000 (maior = mais seguro)
    # Campo pode vir como "score", "score_normalised" ou "normalizedScore"
    raw_score = (
        data.get("score_normalised")
        or data.get("normalizedScore")
        or data.get("score")
        or 0
    )
    try:
        score = int(float(raw_score))
    except (TypeError, ValueError):
        score = 0

    # Verificar flag de rug confirmado independente do score
    if data.get("rugged", False):
        logger.info(f"❌ RugCheck {mint[:12]}: RUGGED confirmado — rejeitado")
        return False, score, "Token marcado como RUGGED"

    if score < min_score:
        reason = f"score={score} < min={min_score}"
        logger.info(f"❌ RugCheck {mint[:12]}: {reason}")
        return False, score, reason

    logger.debug(f"✅ RugCheck {mint[:12]}: score={score} (min={min_score}) — aprovado")
    return True, score, "OK"
