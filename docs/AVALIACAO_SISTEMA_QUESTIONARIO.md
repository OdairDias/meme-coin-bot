# Avaliação do sistema MemeCoin Bot — Respostas ao questionário

Documento gerado a partir da análise da estrutura local (`meme-coin-bot`) e do histórico de chat (`cursor_log_analysis_and_tuning_history.md`). Use como base para o plano de melhoria priorizado.

---

## 1. Estrutura e tecnologia atual

### Qual linguagem principal o projeto usa hoje?
**Python** (única linguagem do bot). FastAPI para HTTP/health, asyncio para WebSocket e loops.

### Como está organizado o repositório?
**Monorepo** com tudo junto em `meme-coin-bot/`:
- **Detector:** `app/scanners/` (PumpPortal WebSocket, Birdeye, Bitquery, DexScreener, Jupiter)
- **Executor:** `app/execution/` (executor, manager, risk, positions_persistence, jupiter_swap, force_sell, startup_cleanup)
- **Análise/Estratégia:** `app/strategies/` (meme_scalper, filters, pattern)
- **Dashboard/observabilidade:** `app/monitoring/` (health, metrics Prometheus, alerts Telegram) + endpoint `/health` e `:9090/metrics`

Não há submódulos separados; um único serviço (FastAPI + uvicorn) que sobe tudo no `lifespan`.

### Tem algum orquestrador ou tudo roda num script sequencial?
**Orquestração por eventos/tasks assíncronas:**
- **Loop principal:** FastAPI lifespan; dentro dele: `pump_scanner.start()` (loop WebSocket) e `position_manager.start()` (loop de monitoramento).
- **Novo token:** callback `on_new_token` → `asyncio.create_task(process_after_delay())` — cada token vira uma task; não há fila explícita, mas várias tasks podem rodar em paralelo (limitadas por `MAX_CONCURRENT_POSITIONS` e anti-clone por symbol).
- **Sem filas de mensagens** (Redis/RabbitMQ); sem workers separados. Tudo no mesmo processo.

### Onde o bot está hospedado hoje? E em qual região?
**Railway** (deploy via GitHub; `railway.toml` com nixpacks, 1 réplica, restart always). Região geográfica não está explícita no código — depende da configuração do projeto no painel Railway.

### Usa Docker/containers ou roda direto no ambiente?
**Docker disponível** (`Dockerfile` com Python 3.11-slim, healthcheck em `/health`). No Railway o build é feito com **Nixpacks** (builder definido no `railway.toml`), não obrigatoriamente com o Dockerfile; na prática pode ser container (Nixpacks gera imagem) ou ambiente gerenciado.

---

## 2. Detecção e entrada de dados

### Como você detecta tokens novos hoje?
**PumpPortal WebSocket** (`wss://pumpportal.fun/api/data`). Inscrição via `subscribeNewToken`; mensagens em 3 formatos suportados: `createEventNotification`, `newToken` (legado) e objeto direto com `mint`. Payload normalizado inclui `mint`, `symbol`, `market_cap`, `pool`, `on_bonding_curve`, etc.

### Qual é a latência média entre o token “nascer” e o bot saber que ele existe?
**Imediata** no recebimento (WebSocket). O atraso relevante é **depois** de saber que o token existe: o bot espera **BIRDEYE_DELAY_SECONDS** (default 60 s, configurável) para consultar OHLCV (Bitquery ou Birdeye). Ou seja, latência “até análise” ≈ 60 s (+ tempo da API Bitquery/Birdeye). No histórico houve ajuste de 300 s → 60 s quando passaram a usar Bitquery (indexação mais rápida).

### Usa fila para processar múltiplos tokens ao mesmo tempo ou é sequencial?
**Paralelo por token, sem fila dedicada.** Cada novo token dispara uma `asyncio.create_task(process_after_delay())`. Vários tokens podem estar “em análise” ao mesmo tempo; o limite de **entrada** é por posições (`MAX_CONCURRENT_POSITIONS`, ex.: 3) e anti-clone por `symbol` (evita analisar o mesmo symbol de novo por `ANTI_CLONE_SYMBOL_SECONDS`, ex.: 600 s).

### Como identifica se um token veio do Pump.fun vs outro AMM?
Pelo **payload do PumpPortal**: campo **`pool`** (ex.: `"raydium"` quando já migrou) e lógica **`on_bonding_curve`** (True só se não for raydium). Tokens na bonding curve são comprados com `pool=auto`; já graduados com `pool=raydium` (entrada via Raydium pela própria API PumpPortal).

---

## 3. Análise e filtros

### Quais filtros você aplica hoje antes de decidir entrar?
- **Pré-filtro no main:** `market_cap >= MIN_MARKET_CAP_SOL` (50 SOL).
- **Filtros em `filters.apply_initial_filters`:** volume 24h (se dado presente), holders, liquidez USD (se presente), dev holding &lt; 30%, snipers &lt; 50, idade &lt; 60 min. Regras “afrouxadas”: volume/liquidez/holders em 0 podem passar.
- **Estratégia:** mínimo de candles OHLCV (Bitquery/Birdeye), padrão “escadinha” (higher highs/lows), score &gt;= MIN_SCORE (40).
- **Sem** filtro explícito de LP lock ou liquidez mínima rígida (valores em 0 são aceitos).

### Usa algum score de risco externo (RugCheck, Solana Sniffer, etc.) ou calcula tudo internamente?
**Tudo internamente.** Não há integração com RugCheck, Solana Sniffer ou similares. README cita que “rug pulls: filtros minimizam, mas não evitam 100%”.

### Quais métricas você calcula hoje para decidir entrar?
- OHLCV 1m (Bitquery primário, Birdeye fallback); padrão escadinha (pattern).
- **Score:** combinação de market cap (SOL→USD), volume (OHLCV + DexScreener), liquidez (DexScreener), preço atual (DexScreener sempre consultado para entry_price atual).
- MIN_SCORE (40), MIN_CANDLES (3), MIN_PATTERN_STEPS (1), PATTERN_VOLUME_MIN_RATIO / PATTERN_SKIP_VOLUME_CHECK.

### Como detecta rug pulls ou dumps rápidos? Tem lógica de alerta ou é reativo?
**Reativo.** Não há detector dedicado de rug/dump. A saída é por **stop loss** (% de queda em relação ao entry), **take profit** (parcial 50%, full 200%) e **tempo máximo** (MAX_HOLDING_MINUTES, ex.: 30). O monitor roda a cada MONITOR_PRICE_INTERVAL_SECONDS (5 s) e compara preço atual (DexScreener/Jupiter) com entry para SL/TP/timeout. Sem alerta proativo de “rug” além do SL.

---

## 4. Execução de trades

### Como você executa os swaps hoje?
- **Compra:** API PumpPortal **trade-local** (recebe tx serializada) → assina com keypair → envia ao RPC (Helius ou SOLANA_RPC_URL). Parâmetros: amount em SOL ou tokens, slippage (DEFAULT_SLIPPAGE 15%), priority fee (Helius getPriorityFeeEstimate ou fallback SOL), pool auto/raydium.
- **Venda:** mesma API PumpPortal para 100%; **parciais (50%):** primeiro tenta **Jupiter V6** (`jupiter_swap.sell_via_jupiter`); se falhar (ex.: bonding curve), fallback PumpPortal com quantidade raw. Venda total ainda usa retry com pool=raydium e depois Jupiter se 400/graduado.

### Usa Jito bundles para proteção MEV ou manda direto no RPC?
**Não.** Nenhuma referência a Jito/bundles/MEV no código. Envio direto ao RPC (Helius ou público) com `skipPreflight: True`, `preflightCommitment: "confirmed"`.

### Como configura slippage e compute units? Fixos ou dinâmicos?
- **Slippage:** compra = DEFAULT_SLIPPAGE (15%); venda 1ª tentativa 10%, retry/Jupiter 20%. Fixos por tipo de operação (configurável por env).
- **Compute units:** fixo implícito no executor (`_DEFAULT_CU_SWAP = 200_000`) para converter priority fee Helius (microlamports/CU) em SOL. Não há CU dinâmico por condição de mercado.

### Quantas wallets usa? Rotação ou uma só?
**Uma única wallet.** `WALLET_PRIVATE_KEY` no config; mesmo keypair para todas as compras/vendas. Sem rotação.

### Tem retry automático quando a transação falha ou dá timeout?
- **Sim, com limites:** compra não repete; venda: retry com pool=raydium; se erro 6022 (sell zero), não reenvia (fecha posição sem nova tx). Parcial: até 3 tentativas, depois fallback para venda total.
- **Confirmação on-chain:** após sendTransaction, poll `getSignatureStatuses` até finalized ou erro (timeout 45 s); depois `getTransaction` para ler `meta.err` (6005, 6024, 6022). Só então considera sucesso/falha.
- Birdeye tem retry em 429 (rate limit); executor não tem retry genérico para timeout de RPC além do fluxo acima.

---

## 5. Gestão de risco e saída

### Qual é a lógica de saída hoje?
- **Stop loss:** quando PnL &lt;= -STOP_LOSS_PERCENT (ex.: 20% no Railway) em relação ao entry (ajustado por USE_CONSERVATIVE_ENTRY se ativo).
- **Take profit 1 (parcial):** quando PnL &gt;= TAKE_PROFIT_PERCENT1 (50%) com TAKE_PROFIT_BUFFER (0.8) — vende 50%, posição fica com quantity 50%.
- **Take profit 2 (full):** quando posição já está em 50% e PnL &gt;= TAKE_PROFIT_PERCENT2 (200%) — vende o restante.
- **Timeout:** MAX_HOLDING_MINUTES (30) — fecha por tempo.

### Tem stop-loss implementado? Baseado em quê?
**Sim.** Baseado em **% de queda** em relação ao preço de entrada (e opcionalmente entry “conservador” com slippage). Não há stop por tempo mínimo nem por volume de venda detectado.

### Tamanho máximo de posição por trade? Fixo em SOL ou dinâmico?
**Fixo em SOL** quando `MAX_POSITION_SIZE_SOL > 0` (default 0.01 SOL). Alternativa em USD: `MAX_POSITION_SIZE_USD` (default 2). O sinal traz `buy_amount_sol`; o executor usa amount em SOL para PumpPortal. Não há sizing dinâmico por volatilidade ou liquidez.

### Quando vários tokens passam nos filtros ao mesmo tempo, como decide qual priorizar?
**Ordem de chegada + limite de concorrência.** Não há fila de prioridade nem score para “quem entra primeiro”. Quem passar em `validate_signal` (vagas sobrando, daily loss ok, sem posição no mesmo token) e executar a compra primeiro fica com a vaga. Até MAX_CONCURRENT_POSITIONS (3); depois os demais são rejeitados por “Max posições simultâneas”.

---

## 6. Dados, persistência e observabilidade

### Você armazena histórico de trades em algum banco?
**Sim.** **PostgreSQL** (Railway) quando `DATABASE_URL` está definido:
- Tabela **positions** (abertas): token, symbol, entry_price, quantity, side, opened_at, current_price, amount_raw.
- Tabela **closed_positions**: token, symbol, entry_price, exit_price, quantity, reason, pnl_usd, pnl_percent, opened_at, closed_at.
- Se não houver DATABASE_URL, usa **data/positions.json** e não há histórico persistido de fechamentos (apenas log/Telegram).

### Tem dashboard ou log estruturado para acompanhar performance em tempo real?
- **Métricas Prometheus** em :9090 (trades_total, positions_opened/closed, open_positions, daily_pnl, equity, histograms de PnL % e duração). Não há dashboard gráfico no repo; só o endpoint de métricas.
- **Logs:** CSV/estruturados conforme o que o Railway coleta (ex.: logs.*.csv que você usou nas análises). Não há formato estruturado (ex.: JSON) definido no código para todos os eventos.

### Calcula métricas de performance (win rate, ROI médio, drawdown máximo)?
**Parcial.** Prometheus expõe `daily_pnl`, `trades_total` por side/status, `positions_closed` por reason e histograms de PnL % e duração. Cálculos agregados (win rate, ROI médio, drawdown) não estão implementados no bot; seria preciso consultar Postgres (`closed_positions`) ou métricas e calcular externamente (dashboard ou script).

### Como detecta quando o bot trava ou para de funcionar? Tem alertas?
- **Healthcheck:** endpoint `/health` (e HEALTHCHECK no Dockerfile). Railway pode usar para restart.
- **Telegram:** `TelegramAlerter` envia alertas de trades e erros (se TELEGRAM_BOT_TOKEN e TELEGRAM_CHAT_ID configurados). Não há heartbeat “bot vivo” nem alerta explícito de “parou de receber tokens” ou “monitor parou”.

---

## 7. Estratégia e backtesting

### Já fez algum backtest da estratégia com dados históricos?
**Não** no repositório. Nenhum módulo de backtest nem dados históricos de candles/trades para replay. Ajustes foram feitos com base em logs de produção e análise manual (ex.: histórico do chat).

### Quantos tokens em média você monitora simultaneamente após a detecção inicial?
Limitado por **MAX_CONCURRENT_POSITIONS** (3). Ou seja, no máximo 3 posições abertas; cada uma é monitorada no loop do PositionManager a cada 5 s. Tokens “em análise” (aguardando delay OHLCV ou em process_after_delay) podem ser vários ao mesmo tempo, mas só 3 viram posição.

### Tempo médio de holding?
Configurado **MAX_HOLDING_MINUTES = 30**. O tempo real varia por SL/TP/timeout; no histórico houve trades de 54 s até 30 min. Não há métrica automática de “holding médio” no código.

### Já identificou padrões de tokens que performam bem (hora do dia, tamanho de pool, velocidade de rampa)?
Não documentado no código. O padrão de entrada é “escadinha” + score; não há filtro por hora, tamanho de pool ou velocidade de rampa explícito. O histórico de chat menciona problemas de delay (OHLCV 300 s vs 60 s) e entry_price stale afetando performance — ou seja, a “velocidade” de entrada e o preço real de compra foram alvo de ajustes, mas não um modelo de “quando” ou “qual pool” performa melhor.

---

## 8. Resumo de gaps e pontos já corrigidos (do histórico)

- **Entrada:** confirmação on-chain (6005/6024/6022), entrada via Raydium quando já graduado, filtro por `on_bonding_curve`/pool.
- **Saída:** decisão de venda só com saldo on-chain (sem cache), tratamento 6022 para não reenviar tx, parcial 50% com Jupiter primeiro e PumpPortal fallback, limite de 3 tentativas para parcial.
- **Risco:** daily loss limit só para perda (não para lucro), entry conservador opcional, fetch de entry real pós-compra.
- **Dados:** Postgres para posições e closed_positions; Bitquery como primário OHLCV; DexScreener para preço atual; delay OHLCV 60 s.
- **Não implementado:** Jito/MEV, múltiplas wallets, score externo (RugCheck/Sniffer), backtest, dashboard de win rate/ROI/drawdown, alertas de “bot parado”.

Use este documento como base para priorizar: velocidade de entrada, redução de risco de perda de capital e melhorias “nice to have” quando o sistema estiver mais estável.
