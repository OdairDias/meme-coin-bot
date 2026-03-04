# Slippage e taxas (derrapagem)

Resumo atualizado após Fase 2 — o slippage de compra agora é **dinâmico por liquidez**.

---

## Compra (BUY) — Slippage dinâmico por liquidez (Fase 2)

O `DEFAULT_SLIPPAGE` fixo foi substituído por um sistema de tiers baseado na liquidez USD do token (via DexScreener). Variáveis configuráveis no Railway:

| Tier | Liquidez USD do token | Variável Railway | Valor padrão |
|------|-----------------------|-----------------|--------------|
| Baixa / desconhecida | < $5.000 ou sem dado | `SLIPPAGE_TIER_LOW` | **25%** |
| Média | $5.000 – $30.000 | `SLIPPAGE_TIER_MID` | **15%** |
| Alta | > $30.000 | `SLIPPAGE_TIER_HIGH` | **10%** |

**Resposta direta:** na compra pagamos entre **10% e 25%** dependendo da liquidez do token. Tokens novos (liquidez desconhecida) usam o tier mais alto (25%) por segurança.

> `DEFAULT_SLIPPAGE` permanece no código como fallback para o `sell()`, mas não é mais usado na compra direta via `executor.buy()`.

---

## Venda (SELL)

| Etapa | Slippage | Observação |
|-------|----------|------------|
| 1ª tentativa (PumpPortal) | **10%** | Fixo no código. |
| Retry com pool=raydium | **20%** | Fixo. |
| Fallback Jupiter V6 | **20%** (2000 bps) | Fixo. |
| Emergency sell | **50%** | Acionado quando queda > SL + `EMERGENCY_SELL_THRESHOLD` numa checagem. |

**Resposta direta:** na venda normal, primeira tentativa até **10%**; em retries e Jupiter até **20%**. Emergency sell usa 50% para garantir execução.

---

## Outros fluxos

| Fluxo | Slippage | Arquivo |
|-------|----------|---------|
| Auto-cleanup no startup | 25% | `startup_cleanup.py` |
| Force-sell-all (emergência) | 25% | `force_sell.py` |

---

## Parciais e stop (suas configurações no Railway)

- **Stop loss:** `STOP_LOSS_PERCENT` (Railway).
- **Emergency sell:** `EMERGENCY_SELL_THRESHOLD` — threshold adicional além do SL para acionar venda imediata com slippage 50%.
- **1ª parcial (TP1):** `TAKE_PROFIT_PERCENT1` — fecha 50% da posição.
- **2ª parcial / full (TP2):** `TAKE_PROFIT_PERCENT2` — fecha o restante (50%).

---

## Resumo rápido

| Operação | Slippage |
|----------|----------|
| Compra — liq < $5k ou desconhecida | **25%** (`SLIPPAGE_TIER_LOW`) |
| Compra — liq $5k–$30k | **15%** (`SLIPPAGE_TIER_MID`) |
| Compra — liq > $30k | **10%** (`SLIPPAGE_TIER_HIGH`) |
| Venda 1ª tentativa | **10%** |
| Venda retry / Jupiter | **20%** |
| Emergency sell | **50%** |
| Cleanup / force-sell | **25%** |

---

## Como a derrapagem afeta o stop loss e o take profit

O bot registra `entry_price` = preço pós-compra (fetched via DexScreener logo após a ordem). Com `USE_CONSERVATIVE_ENTRY=true` (padrão), usa `entry_price × (1 + slippage/100)` como base — assim o PnL já desconta a derrapagem de entrada.

### Stop loss
- Disparado quando **PnL ≤ -STOP_LOSS_PERCENT**.
- Com entry conservador, o stop nominal já se aproxima do prejuízo real.

### Take profit
- TP1 disparado quando **PnL ≥ TAKE_PROFIT_PERCENT1** → vende 50%.
- TP2 disparado quando **PnL ≥ TAKE_PROFIT_PERCENT2** → vende o restante (50%).
- Com entry conservador, os TPs exigem uma alta maior de preço para disparar, refletindo o ganho real após slippage de entrada.

### Entry conservador
- Ativar/desativar: `USE_CONSERVATIVE_ENTRY=true` (padrão) ou `false` no Railway.
