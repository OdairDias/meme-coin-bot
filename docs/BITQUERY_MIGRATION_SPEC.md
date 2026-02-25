# Especificação para Migração Birdeye → Bitquery (OHLCV)

Documento para suporte à pesquisa com Perpexyty sobre migração para Bitquery.

---

## 1. Timeframe de OHLCV usado hoje (Birdeye)

| Parâmetro | Valor |
|-----------|-------|
| **Intervalo** | **1 minuto** (1m) |
| **Candles por request** | **10** (janela de 10 min) |
| **Janela de tempo** | `time_from = now - 10 min` |

**Motivo:** Tokens recém-nascidos (Pump.fun) — pedir mais que 10 min causa 400 (time_from antes da criação do pool).

---

## 2. Volume de tokens monitorados

### Fluxo do bot
- **Descoberta:** PumpPortal WebSocket (~18 tokens/min detectados)
- **Pré-filtro:** Market cap > 40 SOL + anti-clone (mesmo symbol por 10 min)
- **Após filtros:** ~30–60 tokens únicos/hora chegam à análise Birdeye

### Chamadas Birdeye por token
Cada token que passa o pré-filtro:
1. **1ª tentativa** (após 75s): 1× OHLCV
2. **Re-scans** (até 3x, 90s entre cada): 1× OHLCV por tentativa
3. **Token overview:** só quando padrão é detectado (1× por token que passa)

### Estimativa de volume
| Métrica | Valor |
|---------|-------|
| Tokens analisados/hora | ~40–60 |
| OHLCV calls/token | 1–4 (média ~2) |
| **OHLCV calls/hora** | **~80–120** |
| **OHLCV calls/dia** | **~2.000–2.900** |
| Token overview/dia | ~50–150 (só quando pattern passa) |

### Posições abertas (monitoramento de preço)
- **Máx. posições simultâneas:** 3
- **Intervalo de checagem:** 5 segundos
- **Chamada:** `get_token_info` (não OHLCV) para SL/TP
- Quando há 3 posições: ~36 calls/min = ~2.160/hora (apenas durante hold)

---

## 3. Requisitos da query Bitquery (OHLCV)

### Por token, por request
- **1 token** (mint address)
- **Intervalo:** 1m
- **Janela:** últimos 10–15 min (`time_gt: now - 15m`)
- **Limit:** 10–15 candles
- **Campos:** O, H, L, C, V (volume), timestamp

### Formato esperado pelo bot
```python
# Lista de candles com:
{
    "open": float,
    "high": float,
    "low": float,
    "close": float,
    "volume": float,
    "timestamp": int  # unix
}
```

### Chain
- **Solana** (tokens Pump.fun)

---

## 4. Resumo para a Perpexyty

**Perguntas a responder:**

1. **Qual timeframe de OHLCV você usa hoje no Birdeye?**  
   → **1 minuto (1m)**

2. **Quantos tokens, em média, você monitora ao mesmo tempo?**  
   → **~40–60 tokens/hora** passam pelos filtros e são analisados (não simultâneos — são sequenciais com rate limit 1.5s).  
   → **0–3 posições abertas** em monitoramento de preço (usa token_overview, não OHLCV).

3. **Volume de requests OHLCV/dia?**  
   → **~2.000–2.900** calls OHLCV/dia (estimativa conservadora).

4. **Query ideal Bitquery:**  
   - 1 token por request  
   - `time_gt: now - 15m`  
   - `limit: 10` ou 15 candles  
   - Campos: O, H, L, C, V, timestamp  

---

## 5. Observações

- O bot **não** precisa de SMA/EMA pré-calculado — calcula padrões internamente.
- **Pump.fun** — tokens na bonding curve (Solana).
- Endereços vêm com sufixo `...pump` (PDA Pump.fun).
