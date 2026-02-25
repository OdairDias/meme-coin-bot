"""
Bitquery Scanner — OHLCV para tokens Pump.fun (Solana)
Documentação: https://docs.bitquery.io/docs/blockchain/Solana/Pumpfun/Pump-Fun-API/
"""
import asyncio
import time
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional
import httpx

from app.core.config import settings
from app.core.logger import setup_logger

logger = setup_logger(__name__)

# SOL mint (quote currency)
SOL_MINT = "So11111111111111111111111111111111111111112"
# Pump.fun program address (Solana)
PUMP_FUN_PROGRAM = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
BITQUERY_GRAPHQL = "https://streaming.bitquery.io/graphql"
MIN_REQUEST_INTERVAL = 1.0  # Bitquery free tier: evitar spam


class BitqueryScanner:
    """Busca OHLCV de tokens Pump.fun via Bitquery GraphQL."""

    def __init__(self):
        self.api_key = settings.BITQUERY_API_KEY
        self.client = httpx.AsyncClient(timeout=20.0)
        self._last_request = 0.0

    def _headers(self) -> Dict[str, str]:
        return {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }

    async def _rate_limit(self):
        elapsed = time.monotonic() - self._last_request
        if elapsed < MIN_REQUEST_INTERVAL:
            await asyncio.sleep(MIN_REQUEST_INTERVAL - elapsed)
        self._last_request = time.monotonic()

    async def get_ohlcv(
        self, token_address: str, interval: str = "1m", limit: int = 15
    ) -> Optional[Dict[str, Any]]:
        """
        Obtém OHLCV via Bitquery DEXTradeByTokens (Pump.fun).
        Janela: now - 15 min, limit 10-15 candles.
        """
        if not self.api_key:
            return None

        try:
            await self._rate_limit()

            # Janela: últimos 15 min (tokens novos)
            # Bitquery DateTime: RFC 3339 com milissegundos (ex: 2025-02-25T15:30:00.000Z)
            now = datetime.now(timezone.utc)
            since = (now - timedelta(minutes=15)).strftime("%Y-%m-%dT%H:%M:%S.000Z")
            till = now.strftime("%Y-%m-%dT%H:%M:%S.000Z")

            # Intervalo: 1m ou 5m
            interval_min = 1 if interval in ("1m", "1") else 5

            # Query 1: ProgramAddress Pump.fun (mais específico que ProtocolName)
            query = """
            query ($mint: String!, $since: DateTime!, $till: DateTime!, $limit: Int!) {
              Solana(dataset: combined) {
                DEXTradeByTokens(
                  orderBy: { descendingByField: "Block_Timefield" }
                  where: {
                    Trade: {
                      Dex: { ProgramAddress: { is: "%s" } }
                      Currency: { MintAddress: { is: $mint } }
                      Side: { Currency: { MintAddress: { is: "So11111111111111111111111111111111111111112" } } }
                    }
                    Block: { Time: { since: $since, till: $till } }
                  }
                  limit: { count: $limit }
                ) {
                  Block {
                    Timefield: Time(interval: { in: minutes, count: %d })
                  }
                  volume: sum(of: Trade_Amount)
                  Trade {
                    high: Price(maximum: Trade_Price)
                    low: Price(minimum: Trade_Price)
                    open: Price(minimum: Block_Slot)
                    close: Price(maximum: Block_Slot)
                  }
                }
              }
            }
            """ % (
                PUMP_FUN_PROGRAM,
                interval_min,
            )

            variables = {
                "mint": token_address,
                "since": since,
                "till": till,
                "limit": min(limit, 20),
            }

            response = await self.client.post(
                BITQUERY_GRAPHQL,
                json={"query": query, "variables": variables},
                headers=self._headers(),
            )

            if response.status_code >= 400:
                try:
                    err = response.json().get("errors", response.text)[:200]
                except Exception:
                    err = response.text[:200] or str(response.status_code)
                logger.warning(f"Bitquery {response.status_code}: {err}")
                return None

            data = response.json()
            errors = data.get("errors", [])
            raw = data.get("data", {}).get("Solana", {}).get("DEXTradeByTokens", [])

            # Se erro (ex: ProgramAddress inválido), tentar fallback sem filtro DEX
            if errors and not raw:
                err_msg = str(errors[0]) if errors else "Unknown"
                logger.debug(f"Bitquery query1 erro: {err_msg[:200]}, tentando fallback...")
                query_fb = """
                query ($mint: String!, $since: DateTime!, $till: DateTime!, $limit: Int!) {
                  Solana(dataset: combined) {
                    DEXTradeByTokens(
                      orderBy: { descendingByField: "Block_Timefield" }
                      where: {
                        Trade: {
                          Currency: { MintAddress: { is: $mint } }
                          Side: { Currency: { MintAddress: { is: "So11111111111111111111111111111111111111112" } } }
                        }
                        Block: { Time: { since: $since, till: $till } }
                      }
                      limit: { count: $limit }
                    ) {
                      Block { Timefield: Time(interval: { in: minutes, count: %d }) }
                      volume: sum(of: Trade_Amount)
                      Trade {
                        high: Price(maximum: Trade_Price)
                        low: Price(minimum: Trade_Price)
                        open: Price(minimum: Block_Slot)
                        close: Price(maximum: Block_Slot)
                      }
                    }
                  }
                }
                """ % interval_min
                await self._rate_limit()
                resp2 = await self.client.post(
                    BITQUERY_GRAPHQL,
                    json={"query": query_fb, "variables": variables},
                    headers=self._headers(),
                )
                if resp2.status_code < 400:
                    data2 = resp2.json()
                    if not data2.get("errors"):
                        raw = data2.get("data", {}).get("Solana", {}).get("DEXTradeByTokens", [])
                else:
                    logger.warning(f"Bitquery GraphQL errors: {err_msg[:300]}")
                    return None
            elif errors and raw:
                logger.warning(f"Bitquery GraphQL errors (parcial): {str(errors[0])[:200]}")
            if not raw:
                # Fallback: sem filtro DEX — qualquer trade do mint vs SOL (Pump, Raydium, etc.)
                logger.debug(f"Bitquery vazio com ProgramAddress, tentando sem filtro DEX...")
                query_fallback = """
                query ($mint: String!, $since: DateTime!, $till: DateTime!, $limit: Int!) {
                  Solana(dataset: combined) {
                    DEXTradeByTokens(
                      orderBy: { descendingByField: "Block_Timefield" }
                      where: {
                        Trade: {
                          Currency: { MintAddress: { is: $mint } }
                          Side: { Currency: { MintAddress: { is: "So11111111111111111111111111111111111111112" } } }
                        }
                        Block: { Time: { since: $since, till: $till } }
                      }
                      limit: { count: $limit }
                    ) {
                      Block {
                        Timefield: Time(interval: { in: minutes, count: %d })
                      }
                      volume: sum(of: Trade_Amount)
                      Trade {
                        high: Price(maximum: Trade_Price)
                        low: Price(minimum: Trade_Price)
                        open: Price(minimum: Block_Slot)
                        close: Price(maximum: Block_Slot)
                      }
                    }
                  }
                }
                """ % interval_min
                await self._rate_limit()
                resp2 = await self.client.post(
                    BITQUERY_GRAPHQL,
                    json={"query": query_fallback, "variables": variables},
                    headers=self._headers(),
                )
                if resp2.status_code < 400:
                    data2 = resp2.json()
                    if not data2.get("errors"):
                        raw = data2.get("data", {}).get("Solana", {}).get("DEXTradeByTokens", [])
                        if raw:
                            logger.info(f"Bitquery fallback (sem DEX) retornou {len(raw)} candles para {token_address[:12]}...")
            if not raw:
                logger.info(
                    f"Bitquery OHLCV vazio para {token_address[:12]}... | since={since} till={till}"
                )
                return {"address": token_address, "ohlcv": []}

            def _to_float(v) -> float:
                if v is None:
                    return 0.0
                if isinstance(v, (int, float)):
                    return float(v)
                if isinstance(v, dict) and "value" in v:
                    return float(v.get("value", 0))
                try:
                    return float(v)
                except (TypeError, ValueError):
                    return 0.0

            def _norm(c: dict) -> dict:
                block = c.get("Block", {}) or {}
                trade = c.get("Trade", {}) or {}
                ts = block.get("Timefield")
                if isinstance(ts, str):
                    try:
                        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                        ts = int(dt.timestamp())
                    except Exception:
                        ts = 0
                elif ts is None:
                    ts = 0
                return {
                    "open": _to_float(trade.get("open")),
                    "high": _to_float(trade.get("high")),
                    "low": _to_float(trade.get("low")),
                    "close": _to_float(trade.get("close")),
                    "volume": _to_float(c.get("volume")),
                    "timestamp": ts,
                }

            ohlcv = [_norm(c) for c in reversed(raw)]
            logger.debug(f"Bitquery OHLCV para {token_address[:12]}...: {len(ohlcv)} candles")
            return {"address": token_address, "ohlcv": ohlcv}

        except Exception as e:
            logger.error(f"Erro ao buscar OHLCV de {token_address} no Bitquery: {e}")
            return None

    async def close(self):
        await self.client.aclose()
