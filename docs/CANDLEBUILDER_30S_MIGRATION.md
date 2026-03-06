# Migração para CandleBuilder 30s — Documentação Técnica

## Resumo Executivo

Migração da fonte de OHLCV de **Bitquery API (candles de 1 minuto)** para **CandleBuilder local (candles de 30 segundos)** via polling DexScreener. Inclui filtros anti-ruído para proteger contra falsos sinais em timeframes menores.

**Data**: 2026-03-06
**Status**: Em observação (DRY_RUN)

---

## 1. O Que Fizemos

### 1.1 CandleBuilder ativado como fonte primária de OHLCV

| Parâmetro | Antes | Depois |
|-----------|:-----:|:------:|
| `USE_REALTIME_CANDLES` | `false` | **`true`** |
| `CANDLE_TIMEFRAME_SECONDS` | `15` | **`30`** |
| `CANDLE_BUILD_TIMEOUT_SECONDS` | `90` | **`180`** |

**Resultado**: 180s / 30s = **6 candles de 30 segundos**, com 6 data points por candle (polling a cada 5s).

### 1.2 Filtro anti-ruído: `MIN_STEP_PERCENT`

Nova variável de configuração adicionada em `config.py`:

| Parâmetro | Valor | Função |
|-----------|:-----:|--------|
| `MIN_STEP_PERCENT` | `3.0` | Variação mínima (%) para considerar padrão válido |

Aplicação no `pattern.py`:
- **Fast mode** (3-5 candles): exige variação total >= 3% entre primeiro e último close
- **Full mode** (6+ candles, escadinha completa): exige step height >= 1.5% no último degrau

### 1.3 Score e filtros mais conservadores

| Parâmetro | Antes | Depois | Motivo |
|-----------|:-----:|:------:|--------|
| `MIN_SCORE` | `40` | **`50`** | Menos sinais, mais qualidade |
| `MIN_CANDLES` | `3` | **`4`** | Mais dados antes de decidir |
| `MIN_MARKET_CAP_SOL` | `50` | **`30`** | 99.8% dos tokens eram filtrados com 50 |

### 1.4 Arquivos modificados

| Arquivo | Mudança |
|---------|---------|
| `app/core/config.py` | Novos defaults + `MIN_STEP_PERCENT` |
| `app/strategies/pattern.py` | Filtro anti-ruído em fast mode e full mode |
| `app/scanners/candle_builder.py` | Documentação atualizada |
| `.env.example` | Novos defaults + seção CandleBuilder |

---

## 2. Como Fizemos

### 2.1 Análise do pipeline atual

Mapeamos o fluxo completo de um token desde a detecção até a execução:

```
PumpPortal WebSocket → Anti-clone → Fila de prioridade → Worker
  → CandleBuilder (ou Bitquery/Birdeye) → Pattern Detection
    → Score → Signal → Executor → Position Manager → Monitor SL/TP
```

### 2.2 Avaliação de timeframes

Comparamos 3 cenários com a matemática real do `_build_ohlcv`:

| Cenário | Candles (timeout 180s) | Data points/candle | Modo padrão |
|---------|:----------------------:|:------------------:|:-----------:|
| 1 min (Bitquery) | 3 | N/A (API) | Rápido (permissivo) |
| 45s (CandleBuilder) | 4 | 9 | Rápido (permissivo) |
| **30s (CandleBuilder)** | **6** | **6** | **Escadinha completa** |

**30s foi escolhido** porque no mesmo intervalo de 180s fornece 6 candles (vs 3 do Bitquery), habilitando o modo escadinha completa que é mais robusto.

### 2.3 Diagnóstico com logs de produção

Após o primeiro deploy, analisamos 1h15min de logs do Railway:

```
1701 tokens detectados no WebSocket
  → 4 passaram MIN_MARKET_CAP_SOL=50    (99.8% filtrado!)
    → 4 entraram no CandleBuilder (ainda com 90s/15s antigo)
      → 4 rejeitados: "Preço não subindo"
        → 0 sinais gerados
```

**Problemas encontrados**:
1. Railway ainda rodava com config antiga (90s/15s)
2. `MIN_MARKET_CAP_SOL=50` filtrava 99.8% dos tokens
3. Tokens com >50 SOL já estavam em declínio pós-pump

**Correções aplicadas**:
- Config atualizada no Railway (180s/30s)
- `MIN_MARKET_CAP_SOL` reduzido de 50 para 30
- Variáveis `MIN_STEP_PERCENT` e `MIN_SCORE` adicionadas no Railway

---

## 3. Por Que Fizemos

### 3.1 Limitações do sistema anterior (Bitquery 1m)

| Problema | Impacto |
|----------|---------|
| **Delay de indexação**: Bitquery leva 60-300s para indexar tokens novos | Perda da janela de pump (tokens já caíram quando analisados) |
| **Poucos candles**: Com delay de 60s, token de 1 min = 1 candle (< MIN_CANDLES) | Primeiro scan sempre rejeitado, precisa de rescan (+120s) |
| **Dependência de API paga**: Bitquery tem rate limit e custa $ | Custo operacional + fragilidade |
| **Modo rápido (3 candles)**: Pattern detection permissiva | Falsos sinais com uptrend fraco |

### 3.2 Vantagens do CandleBuilder 30s

| Vantagem | Detalhe |
|----------|---------|
| **Coleta desde t=0** | Sem delay de indexação — dados do momento exato do nascimento |
| **6 candles vs 3** | Mesmo intervalo (180s), dobro de resolução → escadinha completa |
| **Escadinha completa** | Higher highs + higher lows com pullbacks — padrão muito mais robusto |
| **Sem API paga** | DexScreener é grátis e estável |
| **Sem rescan** | CandleBuilder coleta continuamente → fallback para Bitquery se falhar |

### 3.3 Proteção anti-ruído

Candles menores = mais ruído. Os filtros compensam:

| Filtro | O que faz | Por que |
|--------|-----------|---------|
| `MIN_STEP_PERCENT >= 3%` (fast) | Rejeita micro-bounces < 3% | Bounce de 1-2% em 2 min não é tendência |
| `MIN_STEP_PERCENT >= 1.5%` (full) | Rejeita degraus insignificantes | Step < 1.5% na escadinha = movimento lateral |
| `MIN_SCORE >= 50` | Exige score mais alto | Compensa mais tokens chegando ao pattern |
| `MIN_CANDLES >= 4` | Mais dados antes de decidir | Evita decisão com 3 pontos insuficientes |

---

## 4. Configuração Atual (Railway)

```env
# CandleBuilder
USE_REALTIME_CANDLES=true
CANDLE_TIMEFRAME_SECONDS=30
CANDLE_BUILD_TIMEOUT_SECONDS=180

# Filtros
MIN_MARKET_CAP_SOL=30
MIN_CANDLES=4
MIN_SCORE=50
MIN_STEP_PERCENT=3.0
MIN_PATTERN_STEPS=1
PATTERN_SKIP_VOLUME_CHECK=true

# Risk (inalterado)
MAX_POSITION_SIZE_SOL=0.01
STOP_LOSS_PERCENT=30.0
TAKE_PROFIT_PERCENT1=50.0
TAKE_PROFIT_PERCENT2=200.0
MAX_HOLDING_MINUTES=30
MAX_CONCURRENT_POSITIONS=3
MAX_DAILY_LOSS_USD=10.0

# Modo
DRY_RUN=true
```

---

## 5. Próximos Passos

### 5.1 Observação em DRY_RUN (imediato)

- [ ] Monitorar logs por 24-48h com a nova config (180s/30s, MIN_MARKET_CAP_SOL=30)
- [ ] Verificar quantos tokens passam pelo funil completo
- [ ] Analisar motivos de rejeição (distribuição entre "Preço não subindo", "Variação insuficiente", "Picos/valles insuficientes", etc.)
- [ ] Confirmar que sinais [DRY_RUN] estão sendo gerados
- [ ] Avaliar qualidade dos sinais: os tokens que geraram sinal realmente pumparam?

### 5.2 Ajuste fino dos parâmetros (após dados de DRY_RUN)

- [ ] **MIN_STEP_PERCENT**: Se muitos sinais bons estão sendo filtrados, reduzir para 2.0%. Se muitos falsos sinais, aumentar para 4.0%
- [ ] **MIN_SCORE**: Ajustar conforme taxa de acerto observada
- [ ] **MIN_MARKET_CAP_SOL**: Se tokens com 30 SOL são predominantemente lixo, subir para 35-40
- [ ] **CANDLE_BUILD_TIMEOUT_SECONDS**: Se 180s é muito lento e tokens já pumparam, testar 120s (4 candles, fast mode com filtro)

### 5.3 Melhorias estruturais (backlog)

- [ ] **Volume no CandleBuilder**: Integrar volume de trades do DexScreener (endpoint de pairs tem volume) para enriquecer os candles com volume real
- [ ] **WebSocket de preço**: Substituir polling REST por WebSocket (Pyth Network ou stream de trades do PumpPortal) para resolução sub-segundo
- [ ] **Multi-timeframe confirmation**: Gerar sinal no 30s, confirmar no 1m (dupla validação)
- [ ] **Backtesting framework**: Salvar candles gerados pelo CandleBuilder em Postgres para análise posterior e otimização de parâmetros
- [ ] **Scoring dinâmico**: Ajustar pesos do score com base em dados históricos de trades (ML leve)

### 5.4 Transição para conta real

- [ ] Confirmar taxa de acerto >= 35% em DRY_RUN (mínimo para ser lucrativo com SL 30% / TP1 50%)
- [ ] Iniciar com `MAX_POSITION_SIZE_SOL=0.005` (metade do atual) nos primeiros dias
- [ ] Monitorar slippage real vs simulado
- [ ] Gradualmente aumentar position size conforme resultados

---

## 6. Referência: Fluxo Completo do Token (pós-migração)

```
t=0s     Token detectado no PumpPortal WebSocket
         ├── marketCapSol < 30? → DESCARTADO (silencioso)
         ├── Anti-clone: symbol duplicado? → DESCARTADO
         └── Entra na fila de prioridade (maior mc = primeiro)

t=0s     Worker pega token da fila
         ├── RugCheck (se habilitado) → reprovar? → DESCARTADO
         └── CandleBuilder inicia polling DexScreener

t=5s     Primeiro preço coletado
t=10s    ...
t=30s    Candle 1 fechado (6 data points)
t=60s    Candle 2 fechado
t=90s    Candle 3 fechado
t=120s   Candle 4 fechado (MIN_CANDLES atingido)
t=150s   Candle 5 fechado
t=180s   Candle 6 fechado → OHLCV pronto

t=180s   Pattern Detection (escadinha completa, 6+ candles)
         ├── Peaks não ascendentes? → REJEITADO
         ├── Troughs não ascendentes? → REJEITADO
         ├── Step height < 1.5%? → REJEITADO (anti-ruído)
         └── Padrão válido ✓

t=180s   Score calculado (volume + holders + liquidez + step_percent)
         ├── Score < 50? → REJEITADO
         └── Score >= 50 ✓

t=180s   Preço atual buscado no DexScreener
         └── Signal gerado: entry, SL (-30%), TP1 (+50%), TP2 (+200%)

t=180s   Risk Manager valida
         ├── Max posições atingido? → REJEITADO
         ├── Daily loss limit? → REJEITADO
         └── Validação OK ✓

t=181s   Executor compra via PumpPortal (trade-local)
         └── Posição aberta, monitoramento inicia (a cada 3s)

t=181s+  Monitor: DexScreener/Jupiter price check
         ├── PnL <= -30%? → STOP LOSS
         ├── PnL >= TP1 (50% × buffer)? → VENDA PARCIAL 50%
         ├── PnL >= TP2 (200%)? → VENDA TOTAL
         ├── Holding >= 30 min? → TIMEOUT
         └── PnL <= -(SL + 15%)? → EMERGENCY SELL (slippage 50%)
```
