# Ajustes e Melhorias — Sessão de Avaliação (Mar/2026)

Documento gerado após avaliação completa do código, análise de logs de produção
(Railway, 07/03/2026) e diagnóstico de 7 perdas consecutivas sem ganhos.

---

## 1. Bugs corrigidos

### Bug 1 — `/status` sempre mostrava Daily PnL = $0.00

**Arquivo:** `app/monitoring/alerts.py`  
**Causa:** `getattr(self._risk_manager, "_daily_loss", 0)` — o atributo tem underscore
a mais; `MemeRiskManager` usa `self.daily_loss` (sem prefixo).  
**Correção:** `"_daily_loss"` → `"daily_loss"`.  
**Impacto:** o comando `/status` no Telegram agora exibe o PnL acumulado do dia corretamente.

---

### Bug 2 — Posição com saldo zero ficava presa em loop infinito

**Arquivo:** `app/execution/manager.py`  
**Causa:** Quando `executor.sell()` levantava `ValueError("ZERO_BALANCE")`, o
`close_position()` retornava `False` (posição mantida aberta). O `_monitor_loop`
verificava SL/TP novamente 3 segundos depois, encontrava a mesma condição de saída,
chamava `close_position()` de novo → loop infinito de alertas Telegram "FALHA AO
VENDER" a cada 3s, indefinidamente. `MAX_HOLDING_MINUTES` também não resolvia porque
o timeout disparava `close_position()` que falhava da mesma forma.  
**Correção:** ZERO_BALANCE agora fecha a posição localmente via
`record_position_close(reason="ZERO_BALANCE")` e retorna `True`. Alerta Telegram
enviado como `warning` (não `critical`) informando que o fechamento foi local.  
**Impacto:** elimina o loop de spam e garante que posições com saldo zero na chain
sejam encerradas corretamente no estado interno do bot.

---

### Bug 3 — PnL inconsistente entre notificação Telegram e Postgres (`/report`)

**Arquivos:** `app/execution/manager.py` + `app/execution/risk.py`  
**Causa:** `manager.close_position()` calculava `pnl_percent_net = pnl_percent -
DEFAULT_SLIPPAGE` (com desconto de slippage) para o Telegram. Mas chamava
`risk_manager.record_position_close(token, current_price, reason)` que recalculava
o PnL internamente **sem** o desconto. Resultado: o `/report` mostrava PnL maior
que as notificações individuais, e o `daily_loss` acumulava sem contabilizar o custo
de saída.  
**Correção:**
- `record_position_close` agora aceita `pnl_usd_override` e `pnl_percent_override`
  opcionais. Quando fornecidos, usa esses valores diretamente.
- `manager.close_position()` passa os valores já calculados (com slippage) para
  ambos Telegram e Postgres.  
**Impacto:** `/report`, `daily_loss` e notificações Telegram mostram o mesmo número.

---

### Bug 4 — Tokens com symbol vazio bypassavam anti-clone

**Arquivo:** `main.py`  
**Causa:** `(token_data.get("symbol") or "?").strip().upper()` — se o symbol era
`"  "` (espaços), `.strip()` retornava `""` (string vazia). A condição
`if symbol and symbol != "?"` era `False` para string vazia, então o anti-clone
por symbol não se aplicava. Múltiplos tokens sem nome com market cap idêntico
poderiam ser processados simultaneamente.  
**Correção:** `((token_data.get("symbol") or "").strip().upper()) or "?"` — qualquer
result vazio vira `"?"` e aciona o anti-clone normalmente.

---

## 2. Melhorias de manutenção

### `requirements.txt` — `websockets` declarado explicitamente

`pump_portal.py` usa `websockets` mas a lib não estava no `requirements.txt`.
Funcionava via dependência transitiva de `uvicorn[standard]`. Adicionado
`websockets>=10.0` para tornar a dependência explícita e evitar quebra silenciosa
se o `uvicorn` mudar de WebSocket provider.

### `pump_portal.py` — 4º formato de payload documentado

Os logs de produção revelaram uma variante do Formato 3 com keys diferentes
(`tokensInPool`, `newTokenBalance` em vez de `bondingCurveKey`, `vTokensInBondingCurve`).
O bot já processava corretamente via `_normalize_raw_token`, mas o formato
não estava documentado. Comentário adicionado no código.

---

## 3. Erros críticos no `CHECKLIST_USUARIO.md` — corrigidos

O checklist tinha quatro inconsistências que podiam causar problemas em produção:

| Problema | Valor antigo no checklist | Valor correto |
|---|---|---|
| Nome da variável Helius | `HELIUS_RPC_URL` | **`HELIUS_RPC`** |
| `USE_CONSERVATIVE_ENTRY` | recomendava `true` | **`false`** |
| `STOP_LOSS_PERCENT` | mostrava default `20` | default real é `30` |
| `TAKE_PROFIT_BUFFER` | ausente | **documentado** (dispara TP1 em 40%, não 50%) |

**O mais crítico:** `HELIUS_RPC_URL` vs `HELIUS_RPC`. O código lê exclusivamente
`HELIUS_RPC`. Se o Railway tinha `HELIUS_RPC_URL`, o Helius era ignorado
silenciosamente e o bot usava o RPC público (`api.mainnet-beta.solana.com`) para
todos os trades — prioridade de taxa não dinâmica, mais 429, menor inclusão de
transações.

---

## 4. `.env.example` — reescrito e alinhado com produção

O arquivo estava desatualizado em relação aos defaults do `config.py` e aos valores
confirmados nos logs Railway. Principais discrepâncias corrigidas:

| Variável | `.env.example` antigo | `.env.example` novo |
|---|---|---|
| `BIRDEYE_DELAY_SECONDS` | `300` | `60` |
| `USE_CONSERVATIVE_ENTRY` | `true` | `false` |
| `DEFAULT_SLIPPAGE` | `30` | `15` |
| `MONITOR_PRICE_INTERVAL_SECONDS` | `15` | `3` |
| `PRIORITY_FEE_LEVEL` | `high` | `veryHigh` |
| `CANDLE_BUILD_TIMEOUT_SECONDS` | ausente | `90` (padrão), `180` em produção |
| `MAX_ENTRY_PUMP_PERCENT` | ausente | `50` (nova variável) |
| `TAKE_PROFIT_BUFFER` | ausente | `0.8` |
| Variáveis Fase 1/2/3 | ausentes | incluídas todas |

---

## 5. Diagnóstico das 7 perdas + Nova feature `MAX_ENTRY_PUMP_PERCENT`

### Causa raiz identificada: entrada depois do pump

O bot detecta um padrão de escadinha no OHLCV, mas o OHLCV já tem 60-120s de
delay (Bitquery). Quando o sinal é gerado e a compra executada, o token pode ter
subido 50-100%+ desde que a análise viu o padrão. A compra ocorre no topo, e a
única direção possível é de queda.

Os logs confirmam: USAHHOUSE subiu +73% durante os 3 minutos do CandleBuilder
($0.00000507 → $0.00000877). Qualquer trade após essa janela seria no topo.

Um agravante: com `USE_CONSERVATIVE_ENTRY=true` (que estava ativo antes), o entry
inflado em 15% criava um SL efetivo de ~20%. Após a correção para `=false` e com
`STOP_LOSS_PERCENT=30`, cada perda ficou 50% maior sem alteração visível nos parâmetros.

### Feature nova: `MAX_ENTRY_PUMP_PERCENT`

**Arquivo:** `app/strategies/meme_scalper.py`  
**Config:** `config.py` — `MAX_ENTRY_PUMP_PERCENT: float = Field(default=0.0)`

Após o DexScreener enriquecer o asset com o preço atual, o filtro compara:

```
pump_desde_ohlcv = (preco_dexscreener - ohlcv_last_price_usd) / ohlcv_last_price_usd × 100
```

Se `pump_desde_ohlcv > MAX_ENTRY_PUMP_PERCENT`, o token é rejeitado com log:
```
❌ TOKEN rejeitado: preço subiu 73% desde a análise OHLCV — entrada seria no topo
```

Não se aplica quando `prebuilt_ohlcv` (CandleBuilder) está ativo, pois o
`last_price` do CandleBuilder já é quase real-time (DexScreener de segundos atrás).

**Valor `0` = desabilitado** (default conservador para não afetar instalações
existentes sem a variável no Railway).

---

## 6. Ajustes de parâmetros recomendados no Railway

Com base no diagnóstico das 7 perdas e na análise dos logs:

| Variável | Valor anterior | Valor recomendado | Justificativa |
|---|---|---|---|
| `STOP_LOSS_PERCENT` | `30` | **`20`** | Corta perdas mais rápido; 30% é muito largo para memecoins voláteis |
| `MIN_SCORE` | `40–50` | **`60`** | Exige volume + liquidez + pattern mais fortes antes de entrar |
| `MAX_HOLDING_MINUTES` | `30` | **`20`** | Tokens sem momentum em 20 min raramente recuperam |
| `MAX_ENTRY_PUMP_PERCENT` | não existia | **`50`** | Ativa o novo filtro anti-topo |
| `MIN_MARKET_CAP_SOL` | `30` | **`50`** | 30-40 SOL ainda traz tokens muito instáveis |

**Relação risco/retorno com os novos parâmetros:**
- SL = 20% | TP1 efetivo = 40% (50% × buffer 0.8) → ratio 1:2 por trade
- `MAX_ENTRY_PUMP_PERCENT=50` elimina entradas onde o upside restante é mínimo
- `MIN_SCORE=60` reduz frequência de trades mas aumenta qualidade

---

## 7. Estado atual do sistema (após todos os ajustes)

### Fluxo de detecção com todos os filtros ativos

```
PumpPortal WebSocket (Formato 3 — objeto direto com marketCapSol)
    │
    ├─ Filtro market_cap >= MIN_MARKET_CAP_SOL (50 SOL) ────────────── rejeita 90% dos tokens
    ├─ Anti-clone marketCapSol (janela 10s) ─────────────────────────── rejeita clones idênticos
    ├─ Anti-clone symbol uppercase (janela 600s) ────────────────────── rejeita spam de symbol
    │
    ▼ PriorityQueue (mc mais alto = processado primeiro)
    │
    ├─ [opcional] RugCheck score >= 500 ─────────────────────────────── rejeita tokens RUGGED
    ├─ [USE_REALTIME_CANDLES] CandleBuilder 180s / 30s por candle
    │  └─ ou sleep 60s + Bitquery OHLCV
    │
    ▼ generate_signals()
    │
    ├─ apply_initial_filters (dev% < 30, snipers < 50, idade < 60min)
    ├─ detect_stairs_pattern (higher highs + higher lows, MIN_CANDLES=4)
    ├─ DexScreener (preço atual)
    ├─ MAX_ENTRY_PUMP_PERCENT=50 ────────────────────────── ✨ NOVO: rejeita entrada no topo
    ├─ _calculate_score >= MIN_SCORE (60)
    │
    ▼ open_position()
    │
    ├─ validate_signal (max posições, daily loss)
    ├─ executor.buy() → PumpPortal trade-local → RPC Helius
    ├─ entry real pós-compra via DexScreener
    │
    ▼ _monitor_loop (a cada 3s)
    │
    ├─ SL: pnl <= -20% → close (slippage 10%)
    ├─ Emergency SL: pnl <= -35% (20+15) → close (slippage 50%)
    ├─ TP1: pnl >= +40% (50%×0.8) → fechar 50% (Jupiter V6 → PumpPortal fallback)
    ├─ TP2: pnl >= +200% → fechar restante
    └─ Timeout: > 20 min → close
```

### Commits desta sessão

| Hash | Descrição |
|---|---|
| `66bf77f` | fix: corrigir 6 bugs — daily_loss, ZERO_BALANCE, PnL, anti-clone, websockets |
| `be13fad` | fix(docs): erros críticos CHECKLIST_USUARIO — HELIUS_RPC, USE_CONSERVATIVE_ENTRY |
| `33e032d` | Merge branch 'cursor/avalia-o-melhorias-bot-427e' |
| `b839d0d` | feat: filtro MAX_ENTRY_PUMP_PERCENT + ajustes de parâmetros anti-perdas |
