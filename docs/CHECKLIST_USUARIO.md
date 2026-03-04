# Checklist do Usuário — Variáveis Railway e ações manuais

Este documento lista tudo que precisa ser feito **do seu lado** para o bot funcionar corretamente.
Todas as variáveis devem ser configuradas no painel do Railway → seu serviço → aba **Variables**.

---

## Variáveis obrigatórias (bot não sobe sem elas)

| Variável | Descrição | Exemplo |
|----------|-----------|---------|
| `WALLET_PRIVATE_KEY` | Chave privada da carteira Solana (base58). **Nunca compartilhe.** | `4Rk7...` |
| `PUMP_PORTAL_API` | URL do endpoint trade-local do PumpPortal | `https://pumpportal.fun/api/trade-local` |
| `SOLANA_RPC_URL` ou `HELIUS_RPC_URL` | RPC Solana. Helius recomendado para priority fee. | `https://mainnet.helius-rpc.com/?api-key=...` |

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
| `CANDLE_TIMEFRAME_SECONDS` | `15` | Tamanho de cada candle em segundos |
| `CANDLE_BUILD_TIMEOUT_SECONDS` | `90` | Tempo total de coleta de preços para montar os candles |
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

## Outras variáveis importantes (já existem no Railway)

| Variável | Padrão código | Descrição |
|----------|---------------|-----------|
| `MIN_MARKET_CAP_SOL` | `50` | Market cap mínimo (SOL) para analisar um token |
| `STOP_LOSS_PERCENT` | `20` | % de queda para disparar stop loss |
| `TAKE_PROFIT_PERCENT1` | `50` | % de ganho para TP1 (fecha 50% da posição) |
| `TAKE_PROFIT_PERCENT2` | `200` | % de ganho para TP2 (fecha os 50% restantes) |
| `MAX_CONCURRENT_POSITIONS` | `3` | Máximo de posições abertas simultaneamente |
| `MAX_HOLDING_MINUTES` | `30` | Tempo máximo de holding antes de fechar por timeout |
| `USE_CONSERVATIVE_ENTRY` | `true` | Usar entry_price corrigido pelo slippage de compra |
| `MONITOR_PRICE_INTERVAL_SECONDS` | `3` | Frequência de verificação SL/TP em segundos |
| `BITQUERY_API_KEY` | — | Chave API Bitquery para OHLCV (free tier funciona) |

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
