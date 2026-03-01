# Slippage e taxas (derrapagem)

Resumo do que o bot usa hoje e até quanto pode “pagar” de derrapagem em cada operação.

## Compra (BUY)

| Origem | Valor | Observação |
|--------|--------|------------|
| **DEFAULT_SLIPPAGE** (config) | **30%** (padrão) | Usado quando o manager não passa slippage (sempre). Pode alterar no `.env`: `DEFAULT_SLIPPAGE=25` (ex.: 25%). |
| Mínimo no código | 15% | Se `DEFAULT_SLIPPAGE` for menor que 15, o executor usa 15% na compra. |

**Resposta direta:** na compra estamos pagando até **30%** de slippage (ou o valor que você definir em `DEFAULT_SLIPPAGE` no `.env`).

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

- **Compra:** até **30%** (config `DEFAULT_SLIPPAGE`).
- **Venda 1ª tentativa:** **10%**.
- **Venda retry/Jupiter:** **20%**.
- **Cleanup / force-sell:** **25%**.

Se quiser reduzir o custo de derrapagem na compra, baixe o `DEFAULT_SLIPPAGE` no `.env` (ex.: 25); em memecoins muito voláteis, valores muito baixos podem aumentar a quantidade de ordens que falham por slippage (6024).

---

## Como a derrapagem afeta o stop loss e o take profit

O bot registra **entry_price** = preço do sinal (cotação **antes** da ordem de compra). Não usamos o preço de execução real após o fill. Por isso:

- **Na compra:** com 30% de slippage você pode **pagar até 30% a mais** que esse `entry_price`. Ou seja, seu custo real pode ser até ~**1,30 × entry_price**.
- **Na venda:** com 10–20% de slippage você pode **receber até 10–20% a menos** que a cotação no momento do gatilho.

### Stop loss (ex.: 30%)

- O bot dispara o stop quando **PnL ≤ -30%**, usando `(preço_atual - entry_price) / entry_price`.
- Como o custo real pode ser até 30% maior que `entry_price`, quando o bot acha que você está em **-30%**, seu prejuízo **real** pode ser da ordem de **-46%** (ex.: pagou 1,30×, preço caiu para 0,70× → perda real (0,70 - 1,30)/1,30 ≈ -46%).
- Na saída, a venda com 10–20% de slippage piora um pouco mais o preço realizado.

**Conclusão:** o stop nominal de 30% pode corresponder a um **prejuízo real maior** (por volta de 40–50% no pior caso de derrapagem na entrada e na saída).

### Take profit (ex.: 50% e 200%)

- O bot dispara TP quando **PnL ≥ 50%** ou **≥ 200%** em relação ao `entry_price`.
- Como o custo real pode ser até 30% maior, quando o bot acha **+50%**, seu ganho **real** pode ser bem menor (ex.: pagou 1,30×, preço em 1,50× → ganho real (1,50 - 1,30)/1,30 ≈ **+15%**). Na saída, a derrapagem na venda reduz um pouco o valor realizado.
- No TP de 200% o efeito é menor em %, mas ainda assim o ganho realizado fica abaixo do nominal.

**Conclusão:** os take profits nominais (50% e 200%) podem corresponder a **ganhos reais menores** por causa da derrapagem na entrada e na saída.

### Entry conservador (implementado)

O bot passou a usar **entry_price conservador** por padrão: `entry_price = preço_do_sinal × (1 + DEFAULT_SLIPPAGE/100)`. Assim o PnL e os gatilhos de SL/TP são calculados em cima de um custo “pior caso”, alinhado ao que você pode pagar na compra com derrapagem.

- **Ativar/desativar:** no `.env`, `USE_CONSERVATIVE_ENTRY=true` (padrão) ou `false`.
- Com `true`: o stop de 30% nominal se aproxima de um prejuízo real de ~30%; os TPs exigem mais alta de preço para disparar, refletindo melhor o ganho real.
- Com `false`: volta ao comportamento antigo (entry = preço do sinal, com a discrepância descrita acima).
