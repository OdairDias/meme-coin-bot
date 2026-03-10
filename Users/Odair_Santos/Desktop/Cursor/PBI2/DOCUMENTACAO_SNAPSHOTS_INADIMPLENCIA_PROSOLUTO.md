# Snapshots Mensais – Inadimplência e Pró-Soluto

Documentação dos snapshots mensais que persistem no MotherDuck o estado histórico de inadimplência e pró-soluto, replicando a lógica das medidas padrão do Power BI.

---

## Histórico de alterações

| Data | Alteração |
|------|-----------|
| 2026-03-10 | **Inadimplência**: Alinhamento com medida Power BI `Valor_Inadimplente_Novo`. Valor Inadimplente passa a usar **Data_Vencimento < primeiro dia do mês seguinte ao mes_referencia** (não mais `Data_Vencimento <= hoje`). Incluído filtro Tipo_Condicao NOT IN (CP, MC, FI, FG). Ver INADIMPLENCIA_SNAPSHOT_ALINHAMENTO_PBI.md. |
| 2026-03-04 | **ProSoluto**: Join id2 = id1. **Substituição**: Se existir dado para o mes_referencia, ao rodar no dia 10 os valores são substituídos; histórico de meses anteriores preservado. |
| 2026-03-02 | Nomes das tabelas com underscore final: `snapshot_prosoluto_mensal_`, `snapshot_inadimplencia_mensal_`. Identificação por `codigointerno_empreendimento` (ProSoluto) e `cod_centro_custo` (Inadimplência). |

---

## Visão geral

- **mes_referencia**: sempre o mês anterior (fechamento). Ex: rodando em 10/mar, grava fechamento de fev (2026-02).
- **Linha geral**: `Geral Prati` (antes "TOTAL").
- **Substituição no dia 10**: Se já existir dado para o mes_referencia (ex.: rodou manualmente antes), ao rodar no dia 10 os valores são **substituídos** (DELETE + INSERT apenas do mês atual). **Histórico de meses anteriores é preservado** (não é alterado).

| Item | Inadimplência | Pró-Soluto |
|------|---------------|------------|
| **Banco** | `administracao` (MotherDuck) | `administracao` (MotherDuck) |
| **Tabela** | `snapshot_inadimplencia_mensal_` | `snapshot_prosoluto_mensal_` |
| **Quando roda** | Dia 10 de cada mês, 06:00 UTC (03:00 BRT) | Dia 10 de cada mês, 06:30 UTC (03:30 BRT) |
| **Lógica** | Sem data de corte – estado atual do banco | Sem data de corte – estado atual do banco |
| **Repositório** | [Prati-Emp/Vendas-consolidas](https://github.com/Prati-Emp/Vendas-consolidas) | Idem |

---

## Snapshot de Inadimplência

### Fontes de dados
- **`contas_recebidas_receber`** (banco `administracao`)
- **Não utiliza** a tabela de vendas (`cv_vendas`)

### Lógica de cálculo (alinhada à medida Power BI Valor_Inadimplente_Novo)
- **CR Valor Devido** = soma de `Valor_Corrigido` de parcelas com `Tipo_Baixa IS NULL` e `Tipo_Condicao NOT IN ('CP','MC','FI','FG')` (sem filtro de data)
- **Valor Inadimplente** = soma de `Valor_Corrigido` de parcelas abertas, mesmo filtro de Tipo_Condicao, com **`Data_Vencimento < primeiro dia do mês seguinte ao mes_referencia`** (ex.: mes_referencia 2026-02 → corte 2026-03-01). Não usar `Data_Vencimento <= hoje`.
- **% Inadimplência** = Valor_Inadimplente / CR_Valor_Devido

Ver detalhes em **INADIMPLENCIA_SNAPSHOT_ALINHAMENTO_PBI.md**.

### Estrutura da tabela
| Coluna | Tipo | Descrição |
|--------|------|-----------|
| `data_snapshot` | DATE | Data em que o snapshot foi gerado |
| `mes_referencia` | VARCHAR | Ano-mês do fechamento (ex: 2026-02 = fechamento de fevereiro) |
| `cod_centro_custo` | INTEGER | NULL = Geral Prati; preenchido = linha por centro de custo |
| `centro_custo` | VARCHAR | Nome do centro de custo ou 'Geral Prati' |
| `cr_valor_devido` | DOUBLE | Valor devido (parcelas abertas) |
| `valor_inadimplente` | DOUBLE | Valor inadimplente (vencido e aberto) |
| `pct_inadimplencia` | DOUBLE | Percentual (0–1) |

---

## Snapshot de Pró-Soluto

### Fontes de dados
- **`contas_recebidas_receber`** (banco `administracao`)
- **`reservas.cv_vendas`** (schema `reservas` no banco `administracao`)

### Lógica de cálculo
- **Valor ProSoluto** = soma de `Valor_Devido` de parcelas abertas (`Tipo_Baixa IS NULL`) com:
  - `Tipo_Condicao IN ('12','PM','AT','PB','PA','PI','PQ','PS')`
  - vinculadas a `cv_vendas` com `tipovenda = 'Venda Financiamento'` via **id2 = id1** (chave composta do Power BI)
- **Valor Venda Financiamento** = soma de `valor_contrato` em `cv_vendas` onde `tipovenda = 'Venda Financiamento'`
- **% ProSoluto** = Valor_ProSoluto / Valor_Venda_Financiamento

### Relacionamento contas ↔ cv_vendas (id2 = id1)
O join replica exatamente o relacionamento do Power BI:
- **id1** (cv_vendas): `codigointerno_empreendimento` & `unidade`
- **id2** (contas_recebidas_receber): `Cod_Centro_Custo` & `Unidade`
- Condição: `(Cod_Centro_Custo || Unidade) = (codigointerno_empreendimento || unidade)`

### Estrutura da tabela
| Coluna | Tipo | Descrição |
|--------|------|-----------|
| `data_snapshot` | DATE | Data em que o snapshot foi gerado |
| `mes_referencia` | VARCHAR | Ano-mês do fechamento (ex: 2026-02 = fechamento de fevereiro) |
| `codigointerno_empreendimento` | VARCHAR | NULL = Geral Prati; preenchido = identificador do empreendimento (chave para join com inadimplência) |
| `empreendimento` | VARCHAR | Nome do empreendimento ou 'Geral Prati' |
| `valor_prosoluto` | DOUBLE | Valor pró-soluto |
| `valor_venda_financiamento` | DOUBLE | Valor total de vendas financiamento |
| `pct_prosoluto` | DOUBLE | Percentual (0–1) |

---

## Diferença entre Inadimplência e Pró-Soluto

| Aspecto | Inadimplência | Pró-Soluto |
|---------|---------------|------------|
| **Tabela de vendas** | Não usa | Usa `reservas.cv_vendas` |
| **Filtro de tipo** | Todas as parcelas abertas | Apenas parcelas de Venda Financiamento |
| **Tipo_Condicao** | Não filtra | Filtra por ('12','PM','AT','PB','PA','PI','PQ','PS') |
| **Agrupamento** | Por Centro de Custo | Por Empreendimento |

---

## Workflows GitHub Actions

- **Snapshot Mensal - Inadimplencia**: `.github/workflows/snapshot-mensal-inadimplencia.yml`
- **Snapshot Mensal - Pro-Soluto**: `.github/workflows/snapshot-mensal-prosoluto.yml`

Execução manual: **Actions** → selecionar o workflow → **Run workflow**.

---

## Scripts Python

- **Inadimplência**: `scripts/snapshot_inadimplencia.py`
- **Pró-Soluto**: `scripts/snapshot_prosoluto.py`

Ambos usam `concurrency_control`, `asyncio` e `load_dotenv`, seguindo o padrão do repositório.
