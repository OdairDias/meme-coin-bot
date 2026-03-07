# Checklist do Usuário — Variáveis Railway e ações manuais

Este documento lista tudo que precisa ser feito **do seu lado** para o bot funcionar corretamente.
Todas as variáveis devem ser configuradas no painel do Railway → seu serviço → aba **Variables**.

---

## Variáveis obrigatórias (bot não sobe sem elas)

| Variável | Descrição | Exemplo |
|----------|-----------|---------|
| `WALLET_PRIVATE_KEY` | Chave privada da carteira Solana (base58). **Nunca compartilhe.** | `4Rk7...` |
| `PUMP_PORTAL_API` | URL do endpoint trade-local do PumpPortal | `https://pumpportal.fun/api/trade-local` |
| `HELIUS_RPC` | RPC Solana (URL completa). **Nome exato da variável** — `HELIUS_RPC_URL` não é lido pelo código. | `https://mainnet.helius-rpc.com/?api-key=...` |

> ⚠️ Se você criou a variável como `HELIUS_RPC_URL` no Railway, o bot está usando o RPC público (`api.mainnet-beta.solana.com`) e ignorando o Helius. **Renomeie para `HELIUS_RPC`.**

---

## Banco de dados (PostgreSQL Railway)

| Ação | Como fazer |
|------|-----------|
| Criar serviço Postgres no Railway | Painel Railway → New → Database → PostgreSQL |
| Copiar `DATABASE_URL` | Aba Variables do serviço Postgres → copiar `DATABASE_URL` e colar no serviço do bot |

> O schema (tabelas `positions` e `closed_positions`) é criado automaticamente no startup. Se precisar recriar, conecte via psycopg2 ou Railway shell e execute `DROP TABLE IF EXISTS positions CASCADE; DROP TABLE IF EXISTS closed_positions CASCADE;` — o bot recria no próximo deploy.

---

## Telegram

| Variável | Como obter |
|----------|-----------|
| `TELEGRAM_BOT_TOKEN` | Crie um bot com [@BotFather](https://t.me/BotFather) no Telegram → `/newbot` → copie o token |
| `TELEGRAM_CHAT_ID` | Envie uma mensagem para o bot e acesse `https://api.telegram.org/bot<TOKEN>/getUpdates` → campo `chat.id` |

**Comandos disponíveis após configuração:**
- `/report` — métricas de performance (win rate, PnL, breakdown por motivo)
- `/status` — posições abertas e estado atual do bot

---

## Fase 0 — Variáveis criadas

| Variável | Valor sugerido | Descrição |
|----------|----------------|-----------|
| `EMERGENCY_SELL_THRESHOLD` | `15.0` | % adicional além do SL para acionar venda de emergência com slippage 50% |
| `BUY_RETRY_ON_TIMEOUT` | `true` | Retentar compra quando a tx não é encontrada (retry com priority_fee +50%) |

---

## Fase 1 — Variáveis criadas

| Variável | Valor sugerido | Descrição |
|----------|----------------|-----------|
| `USE_REALTIME_CANDLES` | `true` | Usar CandleBuilder em vez de sleep fixo + Bitquery para OHLCV |
| `CANDLE_TIMEFRAME_SECONDS` | `30` | Tamanho de cada candle em segundos (30s cobre mais movimento que 15s) |
| `CANDLE_BUILD_TIMEOUT_SECONDS` | `180` | Tempo total de coleta de preços (180s = 6 candles de 30s; mais confiável que 90s) |
| `RUGCHECK_ENABLED` | `true` | Verificar score de risco no RugCheck antes de cada análise |
| `RUGCHECK_MIN_SCORE` | `500` | Score mínimo para aprovação (0–1000, maior = mais seguro) |
| `NO_TOKEN_ALERT_SECONDS` | `300` | Enviar alerta Telegram se nenhum token chegar em X segundos |
| `HEARTBEAT_INTERVAL_MINUTES` | `30` | Frequência do heartbeat "bot ativo" via Telegram |

---

## Fase 2 — Variáveis criadas

| Variável | Valor sugerido | Descrição |
|----------|----------------|-----------|
| `USE_JITO` | `false` | Habilitar Jito Bundles para proteção MEV (manter `false` por enquanto) |
| `JITO_TIP_LAMPORTS` | `50000` | Taxa paga ao Jito (50.000 lamports ≈ 0,00005 SOL ≈ $0,004) |
| `SLIPPAGE_TIER_LOW` | `25` | Slippage % para tokens com liquidez < $5k ou desconhecida |
| `SLIPPAGE_TIER_MID` | `15` | Slippage % para tokens com liquidez $5k–$30k |
| `SLIPPAGE_TIER_HIGH` | `10` | Slippage % para tokens com liquidez > $30k |

---

## Fase 3 — Variáveis opcionais (padrão já configurado no código)

| Variável | Valor padrão | Descrição |
|----------|--------------|-----------|
| `TOKEN_QUEUE_WORKERS` | `3` | Número de workers processando tokens da fila de prioridade simultaneamente |
| `TOKEN_QUEUE_MAX_AGE_SECONDS` | `600` | Tempo máximo (segundos) que um token pode aguardar na fila antes de ser descartado |

> Estas variáveis só precisam ser criadas no Railway se quiser sobrescrever os padrões.

---

## Outras variáveis importantes (verificar no Railway)

| Variável | Padrão código | Valor recomendado | Descrição |
|----------|---------------|-------------------|-----------|
| `DRY_RUN` | `true` | **`false`** para trades reais | Simulação: `true` não executa ordens. Confirme que está `false` em produção. |
| `MIN_MARKET_CAP_SOL` | `50` | **`50`** | Market cap mínimo (SOL). Abaixo de 50 SOL os tokens são instáveis demais. |
| `STOP_LOSS_PERCENT` | `30` | **`20`** | ⚠️ 30% é muito largo para memecoins. Cada perda fica 50% maior. Recomendado: `20`. |
| `TAKE_PROFIT_PERCENT1` | `50` | `50` | % de ganho para TP1 (fecha 50% da posição) |
| `TAKE_PROFIT_BUFFER` | `0.8` | `0.8` | Redutor do threshold de TP1. Com 50% × 0.8 = **TP1 dispara a 40%**, não 50%. Defina `1.0` para desabilitar. |
| `TAKE_PROFIT_PERCENT2` | `200` | `200` | % de ganho para TP2 (fecha os 50% restantes) |
| `MAX_CONCURRENT_POSITIONS` | `3` | `3` | Máximo de posições abertas simultaneamente |
| `MAX_HOLDING_MINUTES` | `30` | **`20`** | Reduzir para 20 min: tokens que não se movem em 20 min geralmente já perderam o momentum. |
| `USE_CONSERVATIVE_ENTRY` | `false` | **`false`** | ⚠️ Manter `false`. Valor `true` inflava o entry em 30%, atrasava o SL e causava perdas maiores. |
| `MIN_SCORE` | `40` | **`60`** | Elevar para 60: exige volume + liquidez + pattern mais fortes antes de entrar. |
| `MAX_ENTRY_PUMP_PERCENT` | `0` | **`50`** | ✨ **Nova variável.** Rejeita entrada se o preço DexScreener já subiu >50% acima do OHLCV analisado — evita comprar no topo do pump. `0` = desabilitado. |
| `DEFAULT_SLIPPAGE` | `15` | `15` | Slippage de compra %. Valor `30` (do .env.example antigo) dobrava o custo de entrada. |
| `PRIORITY_FEE_LEVEL` | `veryHigh` | `veryHigh` | Nível de priority fee Helius. `veryHigh` garante melhor inclusão em memecoins. |
| `MONITOR_PRICE_INTERVAL_SECONDS` | `3` | `3` | Frequência de verificação SL/TP em segundos |
| `BITQUERY_API_KEY` | — | obrigatório | Chave API Bitquery para OHLCV (free tier funciona) |

---

## Script de análise (local)

Para rodar o script de análise de performance no seu computador:

```powershell
# No PowerShell
$env:DATABASE_URL = "postgresql://postgres:<senha>@ballast.proxy.rlwy.net:39541/railway"
python scripts/analyze_trades.py
```

Ou passe a URL como argumento:
```powershell
python scripts/analyze_trades.py "postgresql://postgres:<senha>@ballast.proxy.rlwy.net:39541/railway"
```

---

## Checklist de deploy (após qualquer mudança de código)

1. Fazer push para o branch `main` do GitHub
2. Railway detecta o push e faz deploy automático
3. Verificar logs no painel Railway (aba Deployments → View Logs)
4. Confirmar mensagem `✅ Bot iniciado com sucesso` nos logs
5. Aguardar alerta Telegram confirmando atividade (heartbeat em 30 min ou tokens chegando)
