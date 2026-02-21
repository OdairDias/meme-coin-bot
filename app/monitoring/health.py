"""
Healthcheck endpoint
"""
from fastapi import FastAPI, HTTPException
from app.core.config import settings
from app.core.logger import setup_logger

logger = setup_logger(__name__)


def healthcheck() -> dict:
    """Retorna status de saúde do sistema."""
    status = {
        "status": "healthy",
        "timestamp": None,
        "services": {
            "executor": "ok",
            "risk_manager": "ok",
            "redis": "unknown"
        }
    }

    # Verificar Redis se configurado
    if settings.REDIS_URL:
        try:
            import redis
            r = redis.from_url(settings.REDIS_URL)
            r.ping()
            status["services"]["redis"] = "ok"
        except Exception as e:
            status["services"]["redis"] = f"error: {e}"
            status["status"] = "degraded"

    return status