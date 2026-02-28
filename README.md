# 🚀 MemeCoin Scalper Bot

Bot de scalping para memecoins na Solana via Pump.fun.

## ⚠️ Aviso de Risco

**Especulação extrema.** Você pode perder 100% do capital em minutos. Use apenas valores que está disposto a perder.

## 🎯 Funcionamento

1. **Scanner** — Conecta ao PumpPortal WebSocket para detectar novos tokens em tempo real
2. **Filtros** — Volume > $500, holders > 5, liquidez > $5k, idade < 30 min
3. **Padrão** — Detecta "escadinha" de alta (higher highs/lows) em candles de 5 min
4. **Sinal** — Score > 70 gera entrada (position size $1-2, SL 20%, TP 100%/300%)
5. **Execution** — Executa via PumpPortal API
6. **Risk** — Max 3 posições simultâneas, daily loss limit $10, max holding 30 min

## 🛠️ Setup

### 1. Variáveis de Ambiente

Copie `.env.example` para `.env` e configure:

| Variável | Obrigatório | Descrição |
|----------|-------------|-----------|
| `WALLET_PRIVATE_KEY` | ✅ | Private key da wallet Solana (base58) |
| `BIRDEYE_API_KEY` | ⚠️ | Recomendado para dados OHLCV |
| `TELEGRAM_BOT_TOKEN` | ⚠️ | Para alertas |
| `TELEGRAM_CHAT_ID` | ⚠️ | Seu chat ID |
| `DRY_RUN` | ✅ | `true` para simulação, `false` para real |
| `MAX_POSITION_SIZE_USD` | ✅ | Position size em USD (padrão: 2) |
| `STOP_LOSS_PERCENT` | ✅ | Stop loss % (padrão: 20) |
| `TAKE_PROFIT_PERCENT1` | ✅ | TP parcial 1 % (padrão: 100) |
| `TAKE_PROFIT_PERCENT2` | ✅ | TP final % (padrão: 300) |
| `MAX_HOLDING_MINUTES` | ✅ | Max holding (padrão: 30) |
| `MAX_CONCURRENT_POSITIONS` | ✅ | Posições simultâneas (padrão: 3) |
| `MAX_DAILY_LOSS_USD` | ✅ | Loss diário limite (padrão: 10) |

### 2. Wallet

Crie uma wallet dedicada (Phantom/Backpack). NÃO use a mesma do seu banco.

- Exporte a **private key** (base58)
- Adicione ao `.env` como `WALLET_PRIVATE_KEY`
- Envie ~0.5 SOL para testes

### 3. Deploy (Railway)

```bash
# Railway
1. Novo projeto → Connect → GitHub repo
2. Variáveis de ambiente (copiar do .env)
3. Start command: uvicorn main:app --host 0.0.0.0 --port $PORT
```

Healthcheck: `/health`
Metrics: `:9090/metrics` (Prometheus)

### 4. Testar em Dry-Run

```bash
DRY_RUN=true
```

O bot vai simular trades sem gastar SOL. Verifique logs e alertas.

## 📊 Monitoramento

- **Healthcheck:** `/health` retorna JSON com status
- **Métricas:** `http://localhost:9090/metrics` (Prometheus)
- **Logs:** Railway logs ou arquivos em `logs/`

## 🚨 Alertas

Configure Telegram para receber:
- 📢 Novos trades
- ✅ Posições fechadas (lucro/prejuízo)
- ⚠️ Erros e avisos

## 🔧 Ajustes

Ajuste os parâmetros no `.env` conforme sua banca:

- Banca $50 → `MAX_POSITION_SIZE_USD=1.5`
- Mais conservador → aumentar `STOP_LOSS_PERCENT` e/ou reduzir posições simultâneas
- Mais agressivo → aumentar `MAX_POSITION_SIZE_USD` (cuidado!)

## 📝 Estrutura do Projeto

```
memecoin-bot/
├── app/
│   ├── core/
│   │   ├── config.py      # Configurações
│   │   ├── security.py    # Wallet KPA
│   │   └── logger.py      # Logging
│   ├── scanners/
│   │   ├── pump_portal.py # WS novos tokens
│   │   ├── birdeye.py     # Dados OHLCV
│   │   └── dex_screener.py# Fonte alternativa
│   ├── strategies/
│   │   ├── meme_scalper.py# Estratégia principal
│   │   ├── filters.py     # Filtros
│   │   └── pattern.py     # Detecção escadinha
│   ├── execution/
│   │   ├── executor.py    # PumpPortal API calls
│   │   ├── risk.py        # Gestão de risco
│   │   └── manager.py     # Ciclo de vida posições
│   ├── monitoring/
│   │   ├── health.py      # Healthcheck
│   │   ├── metrics.py     # Prometheus
│   │   └── alerts.py      # Telegram
│   └── main.py            # FastAPI app
├── .env.example
├── requirements.txt
├── Dockerfile
├── railway.toml
└── README.md
```

## ⚡ Considerações

- **Rate limits:** PumpPortal tem limitações? Não documentado, use com moderação
- **Slippage:** Use 10-15% devido à alta volatilidade
- **Priority fee:** Adicionar para evitar frontrun (0.0001-0.001 SOL)
- **Gas:** PumpPortal cobra taxa em SOL por trade (~0.01 SOL)
- **Rug pulls:** Filtros minimizam, mas não evitam 100%

### Erros on-chain Pump.fun

O bot confirma cada transação na blockchain antes de abrir posição. Se a tx falhar:

| Código | Significado | O que o bot faz |
|--------|-------------|------------------|
| **6005** | Bonding curve completou; liquidez migrou para Raydium | Não abre posição; evita comprar token já graduado. Tokens com `pool=raydium` no WebSocket são ignorados antes de analisar. |
| **6024** | Slippage excedido ou Overflow (preço moveu demais) | Não abre posição. Aumente `DEFAULT_SLIPPAGE` no `.env` (ex.: `35` ou `40`) e use `PRIORITY_FEE_LEVEL=veryHigh` para reduzir ocorrências. |

**Entrada via Raydium:** Se o sinal foi gerado na Pump.fun mas o token já migrou para Raydium (`pool=raydium` no WebSocket), o bot **não perde a entrada**: analisa do mesmo jeito e, ao dar sinal, compra com `pool=raydium` na API PumpPortal. A venda já usa Jupiter/Raydium quando necessário.

## 🧪 Testes

1. Dry-run por 24h: observe sinais gerados, postura da estratégia, logs
2. Real com 0.001 SOL por trade: veja fills e latência
3. Ajuste parâmetros conforme comportamento do mercado

---

**Boa sorte!** Lembre-se: isso é cassino, não investimento. Nunca arrisque dinheiro que precisa.