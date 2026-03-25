# ✅ Replicação Completa - Contas a Receber → contas_recebidas_receber

## 🎯 Status: CONCLUÍDO (exceto 1 relacionamento)

### ✅ Tabela Criada
- ✅ Tabela `contas_recebidas_receber` criada
- ✅ Query M corrigida com renomeação `Data_Baixa` → `Data_Recebimento`
- ✅ Dados carregados após refresh

---

## ✅ Colunas Calculadas (5/5 criadas)

| # | Nome | Fórmula | Status |
|---|------|---------|--------|
| 1 | **Dias para Recebimento** | `DATEDIFF(Data_Vencimento, EOMONTH(TODAY(),-1), DAY)` | ✅ Criada |
| 2 | **Categoria_Dias** | Categoriza em faixas: "1. - 30", "2. 31/60", etc. | ✅ Criada |
| 3 | **id2** | `[Cod_Centro_Custo] & [Unidade]` | ✅ Criada e corrigida |
| 4 | **Inadimplencia** | `IF(Data_Vencimento < TODAY() && Tipo_Baixa <> "Recebimento", "Inadimplente", "Adimplente")` | ✅ Criada e corrigida |
| 5 | **Receita financeira** | `Acrescimos + Valor_Correcao` | ✅ Criada e corrigida |

---

## ✅ Medidas (12/12 criadas)

| # | Nome | Fórmula Principal | Status |
|---|------|-------------------|--------|
| 1 | **CR_Valor devido_Novo** | `CALCULATE(SUM([Valor_Devido]), [Tipo_Baixa]=BLANK())` | ✅ Criada |
| 2 | **Valor_Inadimplente_Novo** | Filtra por `Inadimplencia = "Inadimplente"` | ✅ Criada |
| 3 | **%Indimplência_Novo** | `[Valor_Inadimplente_Novo] / [CR_Valor devido_Novo]` | ✅ Criada |
| 4 | **Valor_Inadimplente_Formatado_Novo** | Formato: `#,##0.00` (em milhares) | ✅ Criada |
| 5 | **Valor_Inadimplente_365d_Novo** | Filtra inadimplentes com >= 365 dias | ✅ Criada |
| 6 | **Perda de crédito_Novo** | Formata `Valor_Inadimplente_365d_Novo` | ✅ Criada |
| 7 | **Proporcao_Valor_Devido_Novo** | `DIVIDE(SUM([Valor_Devido]), CALCULATE(..., ALLEXCEPT))` | ✅ Criada |
| 8 | **Valor_ProSoluto_Novo** | Filtra `Tipo_Condicao` e `tipovenda = "Venda Financiamento"` | ✅ Criada |
| 9 | **%ProSoluto_Novo** | `[Valor_ProSoluto_Novo] / [valor venda financiamento_Novo]` | ✅ Criada |
| 10 | **valor venda financiamento_Novo** | `CALCULATE(SUM(cv_vendas[valor_contrato]), ...)` | ✅ Criada |
| 11 | **Vencidos_Até_30_Dias_Novo** | Filtra `DATEDIFF <= 30 dias` | ✅ Criada |
| 12 | **Porcentagem_Inadimplente_Por_Empreendimento_Novo** | `DIVIDE(..., ALLEXCEPT([Centro_Custo]))` | ✅ Criada |

---

## ✅ Relacionamentos (2/3 criados)

| # | De → Para | Colunas | Status |
|---|-----------|---------|--------|
| 1 | `contas_recebidas_receber` → `dim_empreendimentos` | `Cod_Centro_Custo` → `id_empreendimento_sienge` | ✅ Criado |
| 2 | `contas_recebidas_receber` → `dim_dates` | `Data_Vencimento` → `data_referencia` | ✅ Criado |
| 3 | `contas_recebidas_receber` → `cv_vendas` | `id2` → `id1` | ❌ **Erro: Caminho ambíguo** |

### ⚠️ Problema do Relacionamento #3:

**Erro:** "Há caminhos ambíguos entre 'contas_recebidas_receber' e 'dim_empreendimentos'"

**Causa:** O relacionamento `id2` → `id1` cria um caminho alternativo:
- Caminho 1 (direto): `contas_recebidas_receber` → `dim_empreendimentos`
- Caminho 2 (indireto): `contas_recebidas_receber` → `cv_vendas` → `dim_empreendimentos`

**Opções de solução:**
1. **Manter relacionamento direto** com `dim_empreendimentos` e **não criar** `id2` → `id1`
2. **Criar** `id2` → `id1` e **desativar** relacionamento com `dim_empreendimentos`
3. Usar **FILTER** nas medidas para relacionar sem relacionamento direto

**Recomendação:** Opção 1 (atual) — As medidas ProSoluto já usam `cv_vendas[tipovenda]` que funcionará via:
- `contas_recebidas_receber` → `dim_empreendimentos` ← `cv_vendas`

---

## 📋 Próximos Passos

1. **Testar medidas** — Validar se os valores estão corretos
2. **Comparar** com tabela antiga "Contas a Receber"
3. **Decidir** sobre o relacionamento `id2` → `id1` (se realmente necessário)

---

## 🔗 Relacionamentos da Tabela Antiga

Da tabela "Contas a Receber", tínhamos:
- ✅ `id2` → `Vendas[id1]` (existe na tabela antiga)
- ✅ Relacionamento com `dim_empreendimentos` (inativo na tabela antiga)
- ✅ Relacionamento com `dim_dates` via `Data da baixa`

**Na nova tabela:**
- ✅ Relacionamento com `dim_empreendimentos` (ativo)
- ✅ Relacionamento com `dim_dates` via `Data_Vencimento`
- ❌ `id2` → `cv_vendas[id1]` (não criado devido a caminho ambíguo)
