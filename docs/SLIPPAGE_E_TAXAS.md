# Slippage e taxas (derrapagem)

Resumo do que o bot usa hoje e até quanto pode “pagar” de derrapagem em cada operação.

## Compra (BUY)

| Origem | Valor | Observação |
|--------|--------|------------|
| **DEFAULT_SLIPPAGE** (config) | **40%** (padrão) | Usado quando o manager não passa slippage (sempre). Pode alterar no `.env`: `DEFAULT_SLIPPAGE=30` (ex.: 30%). |
| Mínimo no código | 15% | Se `DEFAULT_SLIPPAGE` for menor que 15, o executor usa 15% na compra. |

**Resposta direta:** na compra estamos pagando até **40%** de slippage (ou o valor que você definir em `DEFAULT_SLIPPAGE` no `.env`).

---

## Venda (SELL)

| Etapa | Slippage | Observação |
|--------|----------|------------|
| 1ª tentativa (PumpPortal) | **10%** | Fixo no código. |
| Retry com pool=raydium | **20%** | Fixo. |
| Fallback Jupiter V6 | **20%** (2000 bps) | Fixo. |

**Resposta direta:** na venda, primeira tentativa até **10%**; em retries e Jupiter até **20%**.

---

## Outros fluxos

| Fluxo | Slippage | Arquivo |
|--------|----------|---------|
| Auto-cleanup no startup | 25% | `startup_cleanup.py` |
| Force-sell-all (emergência) | 25% | `force_sell.py` |

---

## Parciais e stop (seus ajustes)

- **Stop loss:** `STOP_LOSS_PERCENT` — padrão no código agora **30%** (você comentou que 20% batia na cara e 40% ficava caro com a derrapagem; 30% é o novo default).
- **1ª parcial (TP1):** `TAKE_PROFIT_PERCENT1` — padrão **50%**.
- **2ª parcial / full (TP2):** `TAKE_PROFIT_PERCENT2` — padrão **200%**.

Tudo isso pode ser sobrescrito no `.env` (ex.: `STOP_LOSS_PERCENT=30`, `TAKE_PROFIT_PERCENT1=50`, `TAKE_PROFIT_PERCENT2=200`).

---

## Resumo rápido

- **Compra:** até **40%** (config `DEFAULT_SLIPPAGE`).
- **Venda 1ª tentativa:** **10%**.
- **Venda retry/Jupiter:** **20%**.
- **Cleanup / force-sell:** **25%**.

Se quiser reduzir o custo de derrapagem na compra, baixe o `DEFAULT_SLIPPAGE` no `.env` (ex.: 25 ou 30); em memecoins muito voláteis, valores muito baixos podem aumentar a quantidade de ordens que falham por slippage (6024).
