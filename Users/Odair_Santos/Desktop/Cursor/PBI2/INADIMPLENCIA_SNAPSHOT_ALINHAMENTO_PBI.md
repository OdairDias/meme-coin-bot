# Alinhamento: Valor_Inadimplente_Novo (Power BI) × snapshot_inadimplencia_mensal_

## Objetivo

Replicar exatamente a lógica da medida **Valor_Inadimplente_Novo** do Power BI no snapshot que alimenta `snapshot_inadimplencia_mensal_` no banco. A inadimplência do snapshot estava maior que a do Power BI porque o **filtro de data** não estava alinhado.

---

## Medida Power BI – Valor_Inadimplente_Novo

**Tabela:** `contas_recebidas_receber- API`

**Expressão DAX:**
```dax
VAR _PrimeiroDiaMesAtual = DATE(YEAR(TODAY()), MONTH(TODAY()), 1)
RETURN
CALCULATE(
    SUM('contas_recebidas_receber- API'[Valor_Corrigido]),
    'contas_recebidas_receber- API'[Inadimplencia] = "Inadimplente",
    'contas_recebidas_receber- API'[Data_Vencimento] < _PrimeiroDiaMesAtual,
    NOT('contas_recebidas_receber- API'[Tipo_Condicao] IN {"CP","MC","FI","FG"})
)
```

**Regras (resumo):**

| Regra | Condição |
|-------|----------|
| Parcelas abertas | Implícito em `Inadimplencia = "Inadimplente"` (vencida e não baixada) |
| Data | **Data_Vencimento &lt; primeiro dia do mês atual** |
| Tipo | **Tipo_Condicao** fora de CP, MC, FI, FG |

Ou seja: no Power BI só entra como inadimplente o que **já estava vencido antes do mês atual**. Parcelas que vencem no mês atual (ex.: dia 5) não entram enquanto o “hoje” for nesse mês.

---

## Medida Power BI – CR_Valor devido_Novo (referência)

```dax
CALCULATE(
    SUM('contas_recebidas_receber- API'[Valor_Corrigido]),
    'contas_recebidas_receber- API'[Tipo_Baixa] = BLANK(),
    NOT('contas_recebidas_receber- API'[Tipo_Condicao] IN {"CP","MC","FI","FG"})
)
```

- Sem filtro de data.
- Parcelas abertas: `Tipo_Baixa = BLANK()`.
- Mesmo filtro de `Tipo_Condicao`.

---

## Lógica do snapshot (antes da correção)

Conforme documentação atual:

- **CR Valor Devido:** soma de `Valor_Corrigido` com `Tipo_Baixa IS NULL` (parcelas abertas).
- **Valor Inadimplente:** soma de `Valor_Corrigido` com parcelas abertas e **`Data_Vencimento <= hoje`**.

Problema: **`Data_Vencimento <= hoje`** inclui todo vencido até o dia em que a cron roda (ex.: dia 10). No Power BI usamos **`Data_Vencimento < primeiro dia do mês atual`**, então o snapshot acabava contando **mais** inadimplência (toda a do mês até o dia 10).

---

## Regra de data correta (replicar o Power BI)

- No Power BI, “mês atual” é o mês de **TODAY()**.
- O snapshot é de **fechamento do mês anterior** (`mes_referencia` = ex.: `2026-02`).

Para o snapshot representar o mesmo critério “só o que estava vencido antes do mês X”:

- Para **mes_referencia = 2026-02** (fechamento de fevereiro), o “mês atual” na lógica do PBI seria **março**.
- Portanto: considerar inadimplente apenas **Data_Vencimento &lt; primeiro dia do mês seguinte ao mes_referencia**.

Definição:

- **data_corte_inadimplente** = primeiro dia do mês **seguinte** a `mes_referencia`  
  - Ex.: `mes_referencia = '2026-02'` → `data_corte_inadimplente = '2026-03-01'`.
- **Valor Inadimplente (snapshot)** = soma de `Valor_Corrigido` onde:
  - `Tipo_Baixa IS NULL`
  - **`Data_Vencimento < data_corte_inadimplente`**
  - `Tipo_Condicao NOT IN ('CP','MC','FI','FG')` (e eventualmente `Tipo_Condicao IS NULL` conforme regra de negócio).

Assim o snapshot replica a mesma regra de data que a medida **Valor_Inadimplente_Novo** no Power BI.

---

## Ajuste no script (repositório Vendas-consolidas)

No script que popula `snapshot_inadimplencia_mensal_` (ex.: `scripts/snapshot_inadimplencia.py`):

1. **Calcular a data de corte**
   - A partir de `mes_referencia` (ex.: `'2026-02'`), obter o primeiro dia do mês seguinte: `'2026-03-01'`.

2. **Valor inadimplente**
   - Trocar a condição de **`Data_Vencimento <= data_hoje`** por **`Data_Vencimento < data_corte_inadimplente`**.

3. **CR Valor Devido**
   - Manter como está: parcelas abertas (`Tipo_Baixa IS NULL`) e mesmo filtro de `Tipo_Condicao` (excluir CP, MC, FI, FG), **sem** filtro de data.

4. **Exclusão de tipos**
   - Garantir que **Valor Inadimplente** e **CR Valor Devido** usem o mesmo filtro: `Tipo_Condicao NOT IN ('CP','MC','FI','FG')` (e tratar `NULL` se aplicável).

Exemplo em SQL (conceitual) para **uma** linha de `mes_referencia` e centro de custo:

```sql
-- mes_referencia = '2026-02' → data_corte = '2026-03-01'
-- CR (parcelas abertas, sem filtro de data)
SUM(Valor_Corrigido) WHERE Tipo_Baixa IS NULL
  AND (Tipo_Condicao NOT IN ('CP','MC','FI','FG') OR Tipo_Condicao IS NULL)

-- Valor inadimplente (replicar Valor_Inadimplente_Novo)
SUM(Valor_Corrigido) WHERE Tipo_Baixa IS NULL
  AND Data_Vencimento < '2026-03-01'
  AND (Tipo_Condicao NOT IN ('CP','MC','FI','FG') OR Tipo_Condicao IS NULL)
```

---

## Resumo

| Aspecto | Power BI (Valor_Inadimplente_Novo) | Snapshot (antes) | Snapshot (correto) |
|---------|-------------------------------------|------------------|--------------------|
| Parcelas abertas | Inadimplencia = "Inadimplente" | Tipo_Baixa IS NULL | Tipo_Baixa IS NULL |
| Data inadimplente | Data_Vencimento **<** 1º dia mês atual | Data_Vencimento **<=** hoje | Data_Vencimento **<** 1º dia mês **seguinte** ao mes_referencia |
| Tipo_Condicao | Exclui CP, MC, FI, FG | (verificar no script) | Excluir CP, MC, FI, FG |

Com isso, o snapshot passa a seguir a mesma lógica de data que a medida **Valor_Inadimplente_Novo** e a inadimplência do snapshot tende a coincidir com a do Power BI para o mesmo fechamento (mes_referencia).
