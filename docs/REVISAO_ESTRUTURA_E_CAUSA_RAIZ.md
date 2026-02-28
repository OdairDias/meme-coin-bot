# Revisão da estrutura do MemeCoin Bot e causa raiz do erro 6022 / gas em cancelamentos

## 1. Estrutura do projeto

```
meme-coin-bot/
├── main.py                    # Entrada FastAPI, lifespan, registro de callbacks
├── app/
│   ├── core/
│   │   ├── config.py          # Settings (RPC, PumpPortal, SL/TP, MIN_MARKET_CAP_SOL, etc.)
│   │   ├── logger.py
│   │   └── security.py        # get_wallet_keypair
│   ├── scanners/
│   │   ├── pump_portal.py     # WebSocket novos tokens (PumpPortal)
│   │   ├── birdeye.py         # OHLCV (fallback quando Bitquery não usado)
│   │   ├── bitquery.py        # OHLCV primário quando BITQUERY_API_KEY configurado
│   │   ├── jupiter.py         # Preço SOL, PriceFetcherWithFallback
│   │   ├── dexscreener.py     # Preço/volume/liquidez (SL/TP e enriquecimento)
│   │   └── dex_screener.py    # (alias/outro módulo)
│   ├── strategies/
│   │   ├── meme_scalper.py    # Gera sinais (filtros, padrão escadinha, score)
│   │   ├── filters.py         # apply_initial_filters
│   │   └── pattern.py         # detect_stairs_pattern
│   ├── execution/
│   │   ├── executor.py         # Compra/venda PumpPortal + Jupiter fallback; saldo on-chain
│   │   ├── manager.py        # PositionManager: open_position, close_position, _monitor_loop
│   │   ├── risk.py           # MemeRiskManager: validação, SL/TP/timeout, positions.json + Redis
│   │   ├── positions_persistence.py  # data/positions.json (add, remove, amount_raw)
│   │   ├── jupiter_swap.py   # get_token_balance_raw, sell_via_jupiter
│   │   ├── startup_cleanup.py # AUTO_CLEANUP_ON_STARTUP
│   │   └── force_sell.py     # /force-sell-all
│   └── monitoring/
│       ├── health.py
│       ├── metrics.py        # Prometheus
│       └── alerts.py         # TelegramAlerter
├── data/
│   └── positions.json        # Posições persistentes (token, quantity, amount_raw, ...)
└── docs/
    └── REVISAO_ESTRUTURA_E_CAUSA_RAIZ.md  # Este arquivo
```

---

## 2. Fluxo de entrada (do novo token até abrir posição)

1. **main.py (lifespan)**
   - Inicializa: `PumpPortalScanner`, `BirdeyeScanner`, `Executor`, `MemeRiskManager`, `MemeScalperStrategy`, `PositionManager` (com `price_fetcher`, `alerter`).
   - Registra callback: `on_new_token` no `pump_scanner`.
   - Chama `pump_scanner.connect()` e `pump_scanner.start()` (loop WebSocket).
   - Chama `position_manager.start()` (loop de monitoramento).

2. **PumpPortalScanner (WebSocket)**
   - Recebe mensagem de novo token → chama `on_new_token(token_data)`.

3. **on_new_token (main.py)**
   - Pré-filtro: `market_cap >= MIN_MARKET_CAP_SOL` (ex.: 45 SOL).
   - Anti-clone: ignora mesmo `symbol` dentro de `ANTI_CLONE_SYMBOL_SECONDS`.
   - Agenda `process_after_delay(rescan_count=0)` em task assíncrona (não bloqueia).

4. **process_after_delay**
   - Espera `BIRDEYE_DELAY_SECONDS` (OHLCV ficar disponível).
   - Chama `strategy.generate_signals([token_data])`.
   - Para cada sinal: `await position_manager.open_position(signal)`.
   - Re-scan: se 0 sinais e ainda há tentativas, agenda novo `process_after_delay(rescan_count+1)`.

5. **MemeScalperStrategy.generate_signals**
   - Filtros iniciais (`apply_initial_filters`).
   - OHLCV 1m: Birdeye (ou Bitquery se configurado).
   - Padrão escadinha (`detect_stairs_pattern`).
   - Enriquecimento: SOL price, DexScreener (volume/liquidez/preço).
   - Score; se `score >= MIN_SCORE` monta sinal com `entry_price`, `buy_amount_sol`, `buy_in_sol`, `pool`, etc.

6. **PositionManager.open_position(signal)**
   - `risk_manager.validate_signal(signal)` (max posições, daily loss, etc.).
   - `executor.buy(token_address, amount, denominated_in_sol, pool)`.
   - Se sucesso: `risk_manager.record_position_open(token, entry_price, quantity="100%" se buy_in_sol, ...)`.
   - `record_position_open` chama `add_position(..., amount_raw=None)` → **na abertura nunca gravamos amount_raw**.

Conclusão da entrada: a decisão de compra e o tamanho são baseados em sinal e config; o saldo em tokens **não** é escrito em `positions.json` na abertura (só depois, quando o executor lê o saldo na chain e chama `update_amount_raw`).

---

## 3. Fluxo de saída (monitor → venda)

1. **PositionManager._monitor_loop**
   - A cada `MONITOR_PRICE_INTERVAL_SECONDS` (ex.: 5s):
     - Para cada `(token, pos)` em `risk_manager.open_positions`:
       - Atualiza `current_price` via `price_fetcher.get_token_info(token)` (DexScreener/Jupiter).
       - `exit_reason = risk_manager.check_exit_conditions(token, current_price)` (SL, TP, timeout).
       - Se `exit_reason`: `await self.close_position(token, reason=exit_reason)`.

2. **PositionManager.close_position(token, reason)**
   - Lê `pos` de `risk_manager.open_positions[token]`; `quantity = pos["quantity"]` (geralmente `"100%"`).
   - Chama `executor.sell(token_address=token, amount=pos["quantity"], ...)`.
   - Se `ValueError("ZERO_BALANCE")`: trata como sucesso e fecha posição localmente (`success = True`, `reason = ..._ZERO_BALANCE`).
   - Se `success`: `record_position_close(token, current_price, reason)` (remove de memória, Redis e positions.json).

3. **Executor.sell**
   - Se `amount == "100%"`: chama `_get_real_token_balance_raw(token, use_fallback=False)` para decidir se pode vender.
   - Se saldo on-chain 0 ou inexistente → `raise ValueError("ZERO_BALANCE")` → **nenhuma tx enviada** (zero gas).
   - Caso contrário: `_execute("sell", ...)` (PumpPortal); se falhar, retry com pool=raydium; se falhar de novo e erro for 6022 → retorna `True` (fecha posição sem mais txs); senão tenta Jupiter com saldo de novo só da chain (`use_fallback=False`).

Ou seja: a **decisão de venda** e o **valor usado para vender** passaram a depender só do saldo on-chain quando `use_fallback=False`, evitando usar `positions.json` para “quanto tenho” e assim evitando enviar tx de venda com saldo 0.

---

## 4. Causa raiz do erro 6022 e do gas em “cancelamentos”

### O que acontecia

- Várias vendas **falhavam on-chain** com **erro 6022 — “Sell zero amount”**.
- Cada tentativa de venda (mesmo falhada) **cobrava gas** (~0,0003 SOL por tx), somando quase **US$ 20** em taxas.

### Por que a tx era “vender 0”?

O programa on-chain (Pump.fun) rejeita instrução de venda com **valor zero**. Ou seja, em algum momento o bot (ou a API que monta a tx) estava mandando **vender 0 tokens**, e a chain executava a tx (e cobrava gas) até a instrução que falhava com 6022.

### Onde estava o bug

- **Fonte do saldo para a decisão de venda:** o executor, ao vender com `amount="100%"`, precisava saber “quanto tenho” para:
  - Decidir se envia ou não a tx de venda.
  - (Em fluxos antigos) Informar valor à API/Jupiter.
- **Função `get_token_balance_raw` (jupiter_swap.py):**
  1. Tenta saldo via RPC (getTokenAccountsByOwner, getTokenAccountBalance, getAccountInfo).
  2. Se **tudo** retornar 0 ou falhar (conta inexistente, RPC lento, etc.), usa **último recurso**: `fallback_amount_raw` passado por quem chamou.
- **Quem chamava:** `_get_real_token_balance_raw(token)` no executor **sempre** passava `fallback_amount_raw = get_position_amount_raw(token)` (valor lido de **positions.json**).

Assim:

- Se a **chain** retornasse **0** (ou não retornasse conta), mas em **positions.json** existisse um `amount_raw` antigo > 0 (de uma leitura anterior, ou de sessão anterior), a função devolvia esse valor antigo.
- O executor entendia: “tenho saldo X” e enviava a ordem de venda “100%”.
- Na prática, na chain o saldo já era **0** (token já vendido em outro lugar, ou posição fechada por outra tx, ou conta zerada). A API/chain montava uma tx de **venda com quantidade 0** → **6022**.
- Cada nova tentativa (incluindo retentativas do monitor ou retry raydium/Jupiter) gerava **nova tx** → **novo gas**, mesmo com saldo zero.

Ou seja: a **causa raiz** foi **usar o cache de positions.json (amount_raw) como fonte de verdade para “quanto tenho” na hora de vender**, quando o saldo real on-chain já era zero. Isso levou a:

1. Envio de tx de venda com quantidade efetiva 0 → **erro 6022**.
2. Cobrança de **gas** em toda tentativa (incluindo “cancelamentos” / fechamentos que na prática eram vendas inválidas).

---

## 5. Onde o amount_raw entra no fluxo

| Momento                    | Quem escreve amount_raw | Quem lê |
|----------------------------|--------------------------|--------|
| Abertura de posição        | Não escreve (`add_position(..., amount_raw=None)`) | — |
| Carregamento (reinício)    | —                        | `risk._load_state()` carrega `pos.get("amount_raw")` em memória |
| Primeira leitura de saldo  | `executor._get_real_token_balance_raw(use_fallback=True)` → `update_amount_raw(token, amount_raw)` | `get_position_amount_raw(token)` como fallback em `get_token_balance_raw` |
| Venda (antes da correção)  | —                        | Fallback = `get_position_amount_raw(token)` → podia ser valor antigo com saldo já 0 na chain |

O problema não era “entrada” (compra) em si; era a **saída** (venda) usar um **cache** que não refletia o saldo real quando a chain já estava zerada.

---

## 6. Correções já implementadas (resumo)

1. **Decisão de venda só com saldo on-chain**
   - `_get_real_token_balance_raw(token, use_fallback=True)`.
   - Na venda com `amount="100%"`: chamada com **`use_fallback=False`** (não usa positions.json).
   - Se a chain retornar 0 ou conta inexistente → `ValueError("ZERO_BALANCE")` → **nenhuma tx enviada** (manager trata e fecha posição localmente).

2. **Fallback Jupiter na venda**
   - Antes de tentar Jupiter, o saldo é obtido de novo com **`use_fallback=False`**, para não vender com valor vindo do cache quando na chain já está 0.

3. **Tratamento do erro 6022**
   - Constante `_PUMP_ERR_SELL_ZERO_AMOUNT = 6022` e mensagem em `_confirm_tx`.
   - `_is_sell_zero_error(err)`: detecta "6022" ou "sell zero".
   - Em `sell()`: se após PumpPortal (ou retry raydium) o erro for 6022 → **retorna True** (posição fechada) e **não** tenta Jupiter nem nova tx → evita mais gas.

Com isso:
- **Não se envia mais tx de venda quando o saldo on-chain for 0.**
- **Se ainda assim uma tx falhar com 6022, o bot não reenvia** e considera a posição fechada, parando de queimar gas.

---

## 7. Diagrama simplificado do fluxo crítico (venda)

```
Monitor loop
    → check_exit_conditions → exit_reason (SL/TP/timeout)
    → close_position(token, reason)
        → executor.sell(token, amount="100%")
            → _get_real_token_balance_raw(token, use_fallback=False)  ← só chain
            → se 0/None → ZERO_BALANCE → sem tx
            → senão → _execute("sell") → (se 6022 → return True, sem retry)
            → (se falha) retry raydium → (se 6022 → return True)
            → (se falha) balance_raw = _get_real_token_balance_raw(use_fallback=False) → Jupiter só se > 0
        → record_position_close
```

Este documento serve como referência da estrutura, do fluxo de entrada/saída e da **causa raiz** do erro 6022 e do gas em cancelamentos, além das correções aplicadas.

---

## 8. Uso de banco de dados (PostgreSQL)

Quando **DATABASE_URL** está definido (ex.: Postgres no Railway), o bot usa o banco em vez de `data/positions.json`:

- **Posições abertas:** tabela `positions` (token, symbol, entry_price, quantity, side, opened_at, current_price, amount_raw).
- **Histórico de fechamentos:** tabela `closed_positions` (token, symbol, entry_price, exit_price, reason, pnl_usd, pnl_percent, closed_at) para auditoria e PnL.

**Configuração:** no Railway, copie a variável `DATABASE_URL` do seu projeto Postgres e defina no `.env` do bot. O schema (`positions` + `closed_positions`) é criado automaticamente no startup. Se `DATABASE_URL` não estiver definido, o comportamento permanece igual ao anterior (apenas `positions.json`). **Redis** continua opcional para cache e `daily_loss`; não é obrigatório migrar isso para o Postgres.

**Consulta ao histórico (exemplo SQL):**
```sql
SELECT token, symbol, reason, pnl_usd, pnl_percent, closed_at
FROM closed_positions
ORDER BY closed_at DESC
LIMIT 50;
```

