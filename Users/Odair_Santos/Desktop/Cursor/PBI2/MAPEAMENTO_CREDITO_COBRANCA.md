# Mapeamento de Migração - Crédito e Cobrança

## 📋 Resumo da Migração

Este documento descreve o mapeamento entre as tabelas antigas e novas para a área de Crédito e Cobrança.

**Data da Migração:** Janeiro 2026  
**Status:** ✅ Medidas Criadas (21/01/2026)

---

## 🗄️ Mapeamento de Tabelas

### 1. Contas a Receber → contas_recebidas_receber

| Coluna Antiga (Contas a Receber) | Coluna Nova (contas_recebidas_receber) | Observações |
|-----------------------------------|----------------------------------------|-------------|
| `Valor devido` | `Valor_Saldo` ou `Valor_SaldoCorrigido` | Usar `Valor_SaldoCorrigido` se disponível |
| `Data vencimento` | `Data_Vencimento` | Mesmo nome, verificar tipo |
| `Inadimplencia` | `Situacao_Inadimplencia` | Verificar valores possíveis |
| `Tipo de baixa` | `Status` ou verificar `Valor_Recebido` | Se `Valor_Recebido` = 0 ou null, não foi baixado |
| `Data emissão` | `Data_Emissao` | Mesmo nome |
| `Cód. centro de custo` | `ID_Empresa` | Relacionar com `dim_empreendimentos` |
| `Data da baixa` | `Data_Recebimento` | Quando houve recebimento |

### 2. Vendas → cv_vendas

| Coluna Antiga (Vendas) | Coluna Nova (cv_vendas) | Observações |
|------------------------|-------------------------|-------------|
| `Valor do contrato` | `valor_contrato` | Mesmo conceito |
| `Tipo de Venda` | `tipovenda` | Verificar valores possíveis |
| `Data Venda` | `data_venda` | Mesmo conceito |
| `Código interno do empreendimento` | `idempreendimento` ou `codigointerno_empreendimento` | Relacionar com `dim_empreendimentos` |

---

## 📊 Medidas Replicadas

### ✅ Medidas de Contas a Receber (12 medidas criadas em `contas_recebidas_receber`)

Todas as medidas foram criadas com sufixo "_Novo" na tabela `contas_recebidas_receber`:

1. ✅ `CR_Valor devido_Novo` - Calcula valor total devido (contas abertas)
   - **Fonte:** `contas_recebidas_receber[Valor_SaldoCorrigido]` filtrado por `Status="ABERTA"`
   - **Adaptação:** `Tipo de baixa` (vazio) → `Status="ABERTA"`

2. ✅ `Valor_Inadimplente_Novo` - Calcula valor inadimplente (vencido antes do mês atual)
   - **Fonte:** `contas_recebidas_receber[Valor_SaldoCorrigido]` filtrado por `Situacao_Inadimplencia="Inadimplente"` e `Data_Vencimento < primeiro dia do mês atual`
   - **Adaptação:** `Inadimplencia` → `Situacao_Inadimplencia`, `Data vencimento` → `Data_Vencimento`

3. ✅ `%Indimplência_Novo` - Percentual de inadimplência
   - **Fonte:** `Valor_Inadimplente_Novo` / `CR_Valor devido_Novo`

4. ✅ `Valor_Inadimplente_Formatado_Novo` - Valor inadimplente formatado em milhares
   - **Fonte:** `Valor_Inadimplente_Novo` / 1000 formatado

5. ✅ `Valor_Inadimplente_365d_Novo` - Valor inadimplente com mais de 365 dias
   - **Fonte:** `contas_recebidas_receber[Valor_SaldoCorrigido]` filtrado por inadimplentes vencidos há mais de 365 dias

6. ✅ `Perda de crédito_Novo` - Perda de crédito formatada em milhares
   - **Fonte:** `Valor_Inadimplente_365d_Novo` formatado

7. ✅ `Proporcao_Valor_Devido_Novo` - Proporção do valor devido sobre total por centro de custo
   - **Fonte:** `contas_recebidas_receber[Valor_SaldoCorrigido]` / `Valor_Total_Por_CentroDeCusto`

8. ✅ `Valor_ProSoluto_Novo` - Valor ProSoluto (contas abertas de vendas financiamento)
   - **Fonte:** `contas_recebidas_receber[Valor_SaldoCorrigido]` filtrado por `Status="ABERTA"`, `cv_vendas[tipovenda]="Venda Financiamento"` e `Condicao_Pagamento` específicas
   - **Adaptação:** `Vendas[Tipo de Venda]` → `cv_vendas[tipovenda]`

9. ✅ `%ProSoluto_Novo` - Percentual ProSoluto sobre vendas financiamento
   - **Fonte:** `Valor_ProSoluto_Novo` / valor total de vendas financiamento de `cv_vendas`

10. ✅ `valor venda financiamento_Novo` - Valor total de vendas financiamento
    - **Fonte:** `cv_vendas[valor_contrato]` filtrado por `tipovenda="Venda Financiamento"`
    - **Adaptação:** `Vendas[Valor do contrato]` → `cv_vendas[valor_contrato]`, `Vendas[Tipo de Venda]` → `cv_vendas[tipovenda]`

11. ✅ `Vencidos_Até_30_Dias_Novo` - Valor de contas vencidas entre 1 e 30 dias
    - **Fonte:** `contas_recebidas_receber[Valor_SaldoCorrigido]` filtrado por `Data_Vencimento` entre 1 e 30 dias
    - **Adaptação:** Adaptado para usar `contas_recebidas_receber` ao invés de `inadimplencia`

12. ✅ `Porcentagem_Inadimplente_Por_Empreendimento_Novo` - Percentual de inadimplência por empreendimento
    - **Fonte:** `contas_recebidas_receber[Valor_SaldoCorrigido]` filtrado por `Situacao_Inadimplencia="Inadimplente"` dividido pelo total por empreendimento
    - **Adaptação:** Adaptado para usar `contas_recebidas_receber` ao invés de `inadimplencia`

### Medidas de Vendas (0 medidas)
- A tabela `Vendas` não possui medidas próprias, mas é usada em medidas de `Contas a Receber` (já adaptadas para usar `cv_vendas`)

---

## 🔗 Relacionamentos Necessários

### ✅ Para contas_recebidas_receber (Criados):
1. ✅ `contas_recebidas_receber[ID_Empresa]` → `dim_empreendimentos[id_empreendimento_sienge]` (relacionamento: `contas_recebidas_receber_empresa`)
2. ✅ `contas_recebidas_receber[Data_Vencimento]` → `dim_dates[data_referencia]` (relacionamento: `contas_recebidas_receber_vencimento`)
3. ⏳ `contas_recebidas_receber[Data_Emissao]` → `dim_dates[data_referencia]` (opcional - não criado ainda)

### Para cv_vendas:
1. `cv_vendas[idempreendimento]` ou `cv_vendas[codigointerno_empreendimento]` → `dim_empreendimentos[id_empreendimento_sienge]`
2. `cv_vendas[data_venda]` → `dim_dates[data_referencia]` (para análises temporais)

---

## ⚠️ Observações Importantes

1. **Tabela `inadimplencia`**: Algumas medidas (`Vencidos_Até_30_Dias`, `Porcentagem_Inadimplente_Por_Empreendimento`) usam a tabela `inadimplencia` ao invés de `Contas a Receber`. Esta tabela pode não ter equivalente direto na nova estrutura.

2. **Tipo de baixa**: A coluna `Tipo de baixa` na tabela antiga indica se a parcela foi baixada. Na nova tabela, podemos usar `Status` ou verificar se `Valor_Recebido` > 0.

3. **Inadimplência**: Verificar os valores possíveis em `Situacao_Inadimplencia` para garantir que o filtro `= "Inadimplente"` funcione corretamente.

4. **Medidas que dependem de Vendas**: Algumas medidas (`valor venda financiamento`, `Valor_ProSoluto`, `%ProSoluto`) dependem da tabela `Vendas`. Essas precisarão ser atualizadas para usar `cv_vendas`.

---

---

## ✅ Status da Implementação

**Data de Criação das Medidas:** 21/01/2026

### Relacionamentos Criados:
- ✅ `contas_recebidas_receber_empresa`: `contas_recebidas_receber[ID_Empresa]` → `dim_empreendimentos[id_empreendimento_sienge]`
- ✅ `contas_recebidas_receber_vencimento`: `contas_recebidas_receber[Data_Vencimento]` → `dim_dates[data_referencia]`

### Medidas Criadas:
- ✅ Todas as 12 medidas foram criadas com sucesso na tabela `contas_recebidas_receber`
- ✅ Todas as medidas usam sufixo "_Novo" para diferenciar das medidas antigas
- ✅ Todas as fórmulas foram adaptadas para usar as novas colunas e tabelas

### Próximos Passos:
1. ⏳ Testar as medidas no Power BI Desktop após refresh
2. ⏳ Verificar se os valores estão corretos comparando com medidas antigas
3. ⏳ Criar relacionamento entre `contas_recebidas_receber` e `cv_vendas` (se necessário para medidas que usam ambas)
4. ⏳ Verificar formatação de tipos de dados nas novas tabelas

---

## 📝 Colunas Calculadas Replicadas

### ✅ Colunas Calculadas Criadas em `contas_recebidas_receber` (5 colunas)

1. ✅ **`Dias para Recebimento`** (Int64)
   - **Fórmula Original:** `DATEDIFF('Contas a Receber'[Data vencimento], EOMONTH(TODAY(), -1), DAY)`
   - **Fórmula Adaptada:** `DATEDIFF(contas_recebidas_receber[Data_Vencimento], EOMONTH(TODAY(), -1), DAY)`
   - **Descrição:** Calcula os dias entre a data de vencimento e o último dia do mês anterior

2. ✅ **`Categoria_Dias`** (String)
   - **Fórmula Original:** Categoriza `Dias para Recebimento` em faixas: "1. - 30", "2. 31/60", "3. 61/90", "4. + 90"
   - **Fórmula Adaptada:** Mesma lógica, usando a coluna `Dias para Recebimento` criada acima
   - **Descrição:** Categoriza os dias para recebimento em faixas

3. ✅ **`id2`** (String)
   - **Fórmula Original:** `[Cód. centro de custo] & [Unidade]`
   - **Fórmula Adaptada:** `[ID_Centro_Custo] & [Parcela]`
   - **Descrição:** Concatena ID_Centro_Custo com Parcela para criar identificador único
   - **Nota:** Adaptado de "Cód. centro de custo & Unidade" para "ID_Centro_Custo & Parcela"

4. ✅ **`Inadimplencia`** (String)
   - **Fórmula Original:** `IF('Contas a Receber'[Data vencimento] < TODAY() && 'Contas a Receber'[Tipo de baixa] <> "Recebimento", "Inadimplente", "Adimplente")`
   - **Fórmula Adaptada:** `IF(contas_recebidas_receber[Data_Vencimento] < TODAY() && contas_recebidas_receber[Status] <> "RECEBIDO", "Inadimplente", "Adimplente")`
   - **Descrição:** Identifica se a conta está inadimplente (vencida e não recebida)
   - **Nota:** A nova tabela já possui `Situacao_Inadimplencia`, mas esta coluna mantém compatibilidade com a lógica antiga

5. ✅ **`Receita financeira`** (Double)
   - **Fórmula Original:** `'Contas a Receber'[Acréscimos] + 'Contas a Receber'[Valor de correção]`
   - **Fórmula Adaptada:** `IF(ISBLANK(contas_recebidas_receber[Imposto]), 0, contas_recebidas_receber[Imposto]) + IF(ISBLANK(contas_recebidas_receber[Desconto]), 0, -contas_recebidas_receber[Desconto])`
   - **Descrição:** Calcula a receita financeira
   - **Nota:** Adaptado de "Acréscimos + Valor de correção" para "Imposto - Desconto". Pode precisar de ajuste se a lógica de negócio for diferente.

---

**Última Atualização:** 21/01/2026 (14:50)
