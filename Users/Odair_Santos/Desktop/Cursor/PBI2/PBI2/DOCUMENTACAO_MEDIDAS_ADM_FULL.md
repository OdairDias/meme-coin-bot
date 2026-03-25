# Documentação de Medidas – ADM FULL (Diretoria Administrativa)

**Arquivo Power BI:** ADM FULL (Nova versão) - Diretoria administrativa  
**Objetivo:** Permitir que qualquer pessoa entenda **de onde vêm** os dados, **para onde vão** (quem usa cada medida) e **por que** cada medida existe, facilitando manutenção e evolução do modelo.

---

## Como usar esta documentação

| Campo | Significado |
|-------|-------------|
| **Propósito** | Por que a medida existe; qual pergunta de negócio ela responde. |
| **Origem** | Tabelas e colunas do modelo das quais a medida lê dados (fonte dos números). |
| **Destino** | Outras medidas ou contextos que usam esta medida (impacto ao alterá-la). |
| **Expressão DAX** | Fórmula completa; alterações devem manter a lógica aqui descrita. |
| **Formato** | Formatação de exibição (%, R$, inteiro, etc.). |

---

## Glossário de tabelas de dados (fontes)

| Tabela | Conteúdo resumido |
|--------|-------------------|
| **dim_dates** | Dimensão de datas (data_referencia, Flag_Mes_Passado, etc.). Usada para filtrar por período. |
| **dim_empreendimentos_dinamica** | Empreendimentos (id_empreendimento_sienge, nome). |
| **metas_realizado_faturamento_lucro_prati** | Metas e realizados consolidados Prati: faturamento, lucro, receita financeira, EBITDA, DGA, distrato contábil, endividamento (por data). |
| **metas_realizado_faturamento_lucro_empreendimentos** | Metas e realizados por empreendimento: meta_faturamento, realizado_faturamento, realizado_lucro, data. |
| **metas_vendas** | Meta de vendas geral (Valor, Data, codigo_empreendimento). |
| **metas_vendas_internas** / **metas_vendas_externas** | Metas de vendas internas e externas (Valor_Meta, etc.). |
| **metas_margem_contribuicao_empreendimentos** | Percentual de margem de contribuição por empreendimento e data (meta_margem_contribuicao, data, codigo_empreendimento). |
| **contas_recebidas_receber- API** | Contas a receber (Valor_Corrigido, Valor_Devido, Tipo_Baixa, Data_Vencimento, inadimplência, etc.). |
| **cv_vendas** | Vendas CV (valor_contrato, tipovenda, codigointerno_empreendimento, datas). |
| **cv_repasses_MD** | Repasses (valor_contrato, situacao, data_alteracao_status, codigointerno_empreendimento). |
| **Metas_Repasse** | Meta de repasses (Valor_Meta, Data_Original, codigo_empreendimento). |
| **DGA** | Dados DGA (valor, ligado a dim_dates). |
| **Indicadores_RH_Geral** | Indicadores RH (headcount, turnover, absenteísmo, atestados, etc.). |
| **Indicadores_RH_Equipe** | Mesmos indicadores por equipe. |
| **Metas_RH** | Metas de RH (Headcount, Turnover, Absenteismo, Atestados, Treinamento, etc.). |
| **metas_horas_treinamentos** | Realizado de horas de treinamento. |
| **Saldo_bancario_caixa_minimo** | Saldo bancário para indicador de caixa mínimo (Data_Transacao, valor). |

---

## 1. Medidas de Vendas / Seletor (MeasureTable vendas1, Medidas Vendas, Medidas)

### 1.1 pct_realizado_distrato_YTD_mês_anterior  
**Tabela:** MeasureTable( vendas1)

| Campo | Conteúdo |
|-------|----------|
| **Propósito** | Percentual realizado de distrato YTD até o mês anterior (distrato realizado / meta distrato). Usado em visuais de vendas quando o seletor aponta para “% Meta Acumulada” ou equivalente. |
| **Origem** | Depende de **vlr_distrato_YTD_mês_anterior** e **vlr_meta_distrato_YTD_mês_anterior** (essas medidas não existem no modelo atual). |
| **Destino** | Pode ser usada por **mLucro_novo** ou visuais que usam Selected Measure_vendas (se o ID corresponder). |
| **Expressão DAX** | `DIVIDE([vlr_distrato_YTD_mês_anterior], [vlr_meta_distrato_YTD_mês_anterior])` |
| **Formato** | Moeda (R$). |
| **Observações** | **Erro semântico:** as medidas referenciadas não existem. Corrigir criando as duas medidas base ou removendo/alterando esta. |

---

### 1.2 Selected Measure_vendas  
**Tabela:** Medidas Vendas

| Campo | Conteúdo |
|-------|----------|
| **Propósito** | Controlar qual indicador de vendas/lucro exibir no visual (1=Meta Lucro, 4=Realizado Lucro, 5=Meta x Realizado, 6=% Realizado YTD, 7=Delta ano anterior). Valor vem do seletor (slicer) na tabela MeasureTable( vendas1). |
| **Origem** | Coluna **ID** da tabela **MeasureTable( vendas1)** (MAX do ID selecionado). |
| **Destino** | Usada por **mLucro_novo** e possivelmente por visuais de vendas. |
| **Expressão DAX** | `MAX('MeasureTable( vendas1)'[ID])` |
| **Formato** | Inteiro (0). |

---

### 1.3 Selected Measure  
**Tabela:** Medidas

| Campo | Conteúdo |
|-------|----------|
| **Propósito** | Controlar qual indicador de faturamento exibir (Meta, Realizado, % Realizado, Delta ano anterior, etc.) quando o relatório usa a tabela de medidas “Medidas” / MeasureTable. |
| **Origem** | Coluna **ID** da tabela **MeasureTable** (MAX do ID selecionado). |
| **Destino** | Usada por **mFaturamentoAgrupado_nova** e **mFaturamentoEmpreendimento_nova**. |
| **Expressão DAX** | `MAX(MeasureTable[ID])` |
| **Formato** | Inteiro (0). |

---

## 2. Lucro e Faturamento – Tabela_Medidas novo_lucro_liquido

### 2.1 faturamento_realizado_YTD_atual  
**Tabela:** Tabela_Medidas novo_lucro_liquido

| Campo | Conteúdo |
|-------|----------|
| **Propósito** | Faturamento realizado acumulado no ano (YTD) no contexto de data atual. Base para % realizado sobre meta YTD. |
| **Origem** | **metas_realizado_faturamento_lucro_prati**[realizado_faturamento], filtrado por **dim_dates** (ano = ano do contexto, data ≤ data máxima do contexto). |
| **Destino** | Usada por **pct_realizado_sobre_meta_YTD_Atual** e por **mLucro_novo** (opção 6). |
| **Expressão DAX** | `CALCULATE(SUM(metas_realizado_faturamento_lucro_prati[realizado_faturamento]), FILTER(ALL(dim_dates), YEAR(dim_dates[data_referencia]) = YEAR(MAX(dim_dates[data_referencia])) && dim_dates[data_referencia] <= MAX(dim_dates[data_referencia])))` |
| **Formato** | (vazio). |

---

### 2.2 faturamento_meta_YTD_atual  
**Tabela:** Tabela_Medidas novo_lucro_liquido

| Campo | Conteúdo |
|-------|----------|
| **Propósito** | Meta de faturamento acumulada no ano (YTD). Denominador do % realizado sobre meta YTD. |
| **Origem** | **metas_realizado_faturamento_lucro_prati**[meta_faturamento], filtrado por **dim_dates** (mesmo critério YTD). |
| **Destino** | Usada por **pct_realizado_sobre_meta_YTD_Atual** e por **mLucro_novo** (opção 6). |
| **Expressão DAX** | `CALCULATE(SUM(metas_realizado_faturamento_lucro_prati[meta_faturamento]), FILTER(ALL(dim_dates), YEAR(dim_dates[data_referencia]) = YEAR(MAX(dim_dates[data_referencia])) && dim_dates[data_referencia] <= MAX(dim_dates[data_referencia])))` |
| **Formato** | (vazio). |

---

### 2.3 pct_realizado_sobre_meta_YTD_Atual  
**Tabela:** Tabela_Medidas novo_lucro_liquido

| Campo | Conteúdo |
|-------|----------|
| **Propósito** | Percentual realizado sobre meta de faturamento no ano (YTD). Indicador de desempenho acumulado. |
| **Origem** | Medidas **faturamento_realizado_YTD_atual** e **faturamento_meta_YTD_atual** (que por sua vez vêm de metas_realizado_faturamento_lucro_prati e dim_dates). |
| **Destino** | Usada por **mLucro_novo** (opção 6). |
| **Expressão DAX** | `DIVIDE([faturamento_realizado_YTD_atual], [faturamento_meta_YTD_atual])` |
| **Formato** | (vazio). |

---

### 2.4 mLucro_novo  
**Tabela:** Tabela_Medidas novo_lucro_liquido

| Campo | Conteúdo |
|-------|----------|
| **Propósito** | Medida de exibição dinâmica: mostra Meta Lucro, Realizado Lucro, Meta x Realizado, % Realizado YTD ou Delta ano anterior, formatado (em milhões ou %), conforme o seletor de vendas. |
| **Origem** | **Selected Measure_vendas** (seletor); medidas **Meta Lucro**, **Realizado Lucro Prati**, **Meta x Realizado_LL_Geral**, **pct_realizado_sobre_meta_YTD_Atual**, **% Delta Ano Anterior Lucro Geral**. |
| **Destino** | Usada em visuais (cards/tabelas) que exibem indicador de lucro/faturamento selecionável. |
| **Expressão DAX** | VAR ValorSelecionado = SWITCH([Selected Measure_vendas], 1, [Meta Lucro], 4, [Realizado Lucro Prati], 5, [Meta x Realizado_LL_Geral], 6, [pct_realizado_sobre_meta_YTD_Atual], 7, [Delta Ano Anterior Faturamento_LL_Atual_geral]) RETURN SWITCH([Selected Measure_vendas], 1, FORMAT(ROUND(ValorSelecionado/1000000,1),"#,##0.00"), 4, idem, 5/6/7, FORMAT(ValorSelecionado,"0%"). |
| **Formato** | Texto (formatado em Mi ou %). |

---

### 2.5 z_month-12_LL_atual_geral  
**Tabela:** Tabela_Medidas novo_lucro_liquido

| Campo | Conteúdo |
|-------|----------|
| **Propósito** | Realizado de lucro do mesmo período do ano anterior (SAMEPERIODLASTYEAR). Base para cálculo do delta ano a ano. |
| **Origem** | Medida **Realizado Lucro Prati** no contexto de **dim_dates** (SAMEPERIODLASTYEAR). |
| **Destino** | Usada por **Delta Ano Anterior Faturamento_LL_Atual_geral**. |
| **Expressão DAX** | VAR valor_ano_anterior = CALCULATE([Realizado Lucro Prati], SAMEPERIODLASTYEAR(dim_dates[data_referencia])) RETURN IF(valor_ano_anterior=BLANK(), 0, valor_ano_anterior) |
| **Formato** | (vazio). |

---

### 2.6 Meta x Realizado_LL_Geral  
**Tabela:** Tabela_Medidas novo_lucro_liquido

| Campo | Conteúdo |
|-------|----------|
| **Propósito** | Razão realizado/meta de lucro (geral). Indicador de atingimento da meta de lucro. |
| **Origem** | Medidas **Realizado Lucro Prati** e **Meta Lucro**. |
| **Destino** | Usada por **mLucro_novo** (opção 5). |
| **Expressão DAX** | `DIVIDE([Realizado Lucro Prati], [Meta Lucro], 0)` |
| **Formato** | (vazio). |

---

### 2.7 % Delta Ano Anterior Lucro Geral  
**Tabela:** Tabela_Medidas novo_lucro_liquido

| Campo | Conteúdo |
|-------|----------|
| **Propósito** | Variação do realizado de lucro em relação ao mesmo período do ano anterior: (Realizado / Realizado ano anterior) - 1. |
| **Origem** | Medidas **Realizado Lucro Prati** e **z_month-12_LL_atual_geral**. |
| **Destino** | Usada por **mLucro_novo** (opção 7). |
| **Expressão DAX** | `([Realizado Lucro Prati] / [z_month-12_LL_atual_geral]) - 1` |
| **Formato** | (vazio). |

---

## 3. Faturamento – Tabela_medidas_Faturamento_Nova

### 3.1 mFaturamentoAgrupado_nova  
**Tabela:** Tabela_medidas_Faturamento_Nova

| Campo | Conteúdo |
|-------|----------|
| **Propósito** | Exibir de forma dinâmica Meta Faturamento, Realizado Faturamento, % Meta x Realizado ou Delta ano anterior (em milhões ou %), conforme **Selected Measure**. |
| **Origem** | **Selected Measure** (MeasureTable[ID]); medidas Meta Faturamento Prati, Realizado Faturamento Prati, **% Realizado Faturamento Geral**, **% Delta Ano Anterior Faturamento Geral**. |
| **Destino** | Usada em visuais de faturamento consolidado. |
| **Expressão DAX** | SWITCH(Selected Measure: 1→Meta, 2→Realizado, 3→%, 5→Delta; FORMAT em milhões ou %). |
| **Formato** | Texto. |

---

### 3.2 % Realizado Faturamento Geral  
**Tabela:** Tabela_medidas_Faturamento_Nova

| Campo | Conteúdo |
|-------|----------|
| **Propósito** | Percentual realizado sobre meta de faturamento (geral Prati). |
| **Origem** | Medidas **Realizado Faturamento Prati** e **Meta Faturamento Prati**. |
| **Destino** | Usada por **mFaturamentoAgrupado_nova** (opção 3). |
| **Expressão DAX** | `DIVIDE([Realizado Faturamento Prati],[Meta Faturamento Prati],0)` |
| **Formato** | (vazio). |

---

### 3.3 faturamento_realizado_ano_anterior_geral  
**Tabela:** Tabela_medidas_Faturamento_Nova

| Campo | Conteúdo |
|-------|----------|
| **Propósito** | Faturamento realizado no mesmo período do ano anterior (para delta). Evita divisão por zero usando 0,00001 se BLANK. |
| **Origem** | Medida **Realizado Faturamento Prati** + **dim_dates** (SAMEPERIODLASTYEAR). |
| **Destino** | Usada por **% Delta Ano Anterior Faturamento Geral**. |
| **Expressão DAX** | VAR valor_ano_anterior = CALCULATE([Realizado Faturamento Prati], SAMEPERIODLASTYEAR(dim_dates[data_referencia])) RETURN IF(valor_ano_anterior=BLANK(), 0.00001, valor_ano_anterior) |
| **Formato** | (vazio). |

---

### 3.4 % Delta Ano Anterior Faturamento Geral  
**Tabela:** Tabela_medidas_Faturamento_Nova

| Campo | Conteúdo |
|-------|----------|
| **Propósito** | Variação do faturamento realizado em relação ao mesmo período do ano anterior. |
| **Origem** | Medidas **Realizado Faturamento Prati** e **faturamento_realizado_ano_anterior_geral**. |
| **Destino** | Usada por **mFaturamentoAgrupado_nova** (opção 5). |
| **Expressão DAX** | `([Realizado Faturamento Prati] / [faturamento_realizado_ano_anterior_geral]) - 1` |
| **Formato** | (vazio). |

---

### 3.5 mFaturamentoEmpreendimento_nova  
**Tabela:** Tabela_medidas_Faturamento_Nova

| Campo | Conteúdo |
|-------|----------|
| **Propósito** | Exibir Meta, Realizado ou % Realizado de faturamento por empreendimento, formatado (milhões ou %), conforme **Selected Measure**. |
| **Origem** | **Selected Measure**; medidas **Meta Faturamento Empreendimentos**, **Realizado Faturamento Empreendimentos**, **% Realizado Faturamento Empreendimentos**. |
| **Destino** | Visuais por empreendimento. |
| **Expressão DAX** | SWITCH(Selected: 1→Meta, 2→Realizado, 3→%; FORMAT em milhões ou %). |
| **Formato** | Texto. |

---

## 4. Contas a receber / Inadimplência / ProSoluto – contas_recebidas_receber- API

Todas as medidas desta tabela usam como **origem** a própria tabela **contas_recebidas_receber- API** (colunas como Valor_Corrigido, Valor_Devido, Tipo_Baixa, Data_Vencimento, indicadores de inadimplência, tipo de venda, etc.) e, em alguns casos, **cv_vendas** (valor_contrato, tipovenda).  
**Destino:** usadas em painéis de inadimplência e ProSoluto e por medidas de **MeasureTable_Inadimplencia_ProSoluto** (Realizado Inadimplência = %Indimplência_Novo, Realizado ProSoluto = %ProSoluto_Novo).

| Medida | Propósito resumido |
|--------|--------------------|
| **CR_Valor devido_Novo** | Total a receber (Valor_Corrigido onde Tipo_Baixa em branco). |
| **Valor_Inadimplente_Novo** | Valor em atraso (inadimplente). |
| **%Indimplência_Novo** | % inadimplente sobre total devido. |
| **Valor_Inadimplente_Formatado_Novo** | Valor inadimplente em milhares (formatação). |
| **Valor_Inadimplente_365d_Novo** | Valor inadimplente há mais de 365 dias. |
| **Perda de crédito_Novo** | Formatação do valor 365d em milhares. |
| **Proporcao_Valor_Devido_Novo** | Proporção do valor devido por centro de custo. |
| **Valor_ProSoluto_Novo** | Valor devido em “Venda Financiamento” e condições ProSoluto. |
| **%ProSoluto_Novo** | % ProSoluto sobre valor total de vendas financiamento. |
| **valor venda financiamento_Novo** | Soma de valor_contrato (cv_vendas) para tipovenda = "Venda Financiamento". |
| **Vencidos_Até_30_Dias_Novo** | Valor vencido entre 1 e 30 dias. |
| **Porcentagem_Inadimplente_Por_Empreendimento_Novo** | % inadimplente por empreendimento. |
| **CR_Valor devido_Novo_debug** | Soma de Valor_Devido (uso em debug). |

---

## 5. EBITDA e Prati (metas_realizado_faturamento_lucro_prati + MeasureTables)

### 5.1 Meta EBITDA / Realizado EBITDA  
**Tabela:** metas_realizado_faturamento_lucro_prati

| Campo | Conteúdo |
|-------|----------|
| **Propósito** | Meta e realizado consolidados de EBITDA (Prati). |
| **Origem** | **metas_realizado_faturamento_lucro_prati**: colunas **meta_ebitda** e **realizado_ebitda**. |
| **Destino** | Usadas por **% Meta EBITDA**, **Meta EBITDA (Milhões)**, **Realizado EBITDA (Milhões)**, **mEBITDA_Agrupado**. |
| **Expressão** | SUM(meta_ebitda) e SUM(realizado_ebitda). |

---

### 5.2 % Meta EBITDA  
**Origem:** [Realizado EBITDA], [Meta EBITDA]. **Destino:** mEBITDA_Agrupado, % Meta EBITDA Formatado.

### 5.3 Selected Measure EBITDA (MeasureTable_EBITDA)  
**Propósito:** Retornar o ID da opção selecionada no seletor de EBITDA (1=Meta, 2=Realizado, 3=% Meta). **Origem:** MeasureTable_EBITDA[ID]. **Destino:** mEBITDA_Agrupado.

### 5.4 MeasureTable_Metas_Prati  
Metas agregadas a partir de **metas_realizado_faturamento_lucro_prati**: Meta Faturamento Prati, Meta Lucro, Meta Receita Financeira, Meta Distrato Contábil (e versões em milhões). **Destino:** várias medidas de realizados, percentuais e agrupadas.

### 5.5 MeasureTable_Realizados_Prati  
Realizados agregados: Realizado Faturamento/Lucro/Receita Financeira/Distrato Contábil Prati (e em milhões). **Origem:** colunas realizado_* da mesma tabela. **Destino:** % Meta Faturamento/Lucro/Receita/Distrato, mLucro_novo, mFaturamentoAgrupado_nova, etc.

### 5.6 MeasureTable_Percentuais_Prati  
% Meta Faturamento, % Meta Lucro, % Meta Receita Financeira, % Meta Distrato Contábil. Cada uma é DIVIDE(Realizado, Meta, 0). **Destino:** visuais e medidas agrupadas.

---

## 6. Metas de Vendas (MeasureTable_Metas_Vendas)

| Medida | Propósito | Origem | Destino |
|--------|-----------|--------|---------|
| **Meta Vendas Geral** | Soma das metas de vendas gerais. | metas_vendas[Valor] | Visuais de vendas. |
| **Meta Vendas Internas** | Soma das metas de vendas internas. | metas_vendas_internas[Valor_Meta] | Validação e visuais. |
| **Meta Vendas Externas** | Soma das metas de vendas externas. | metas_vendas_externas[Valor_Meta] | Validação e visuais. |
| **Meta Vendas Total (Internas + Externas)** | Soma interna + externa para checagem. | [Meta Vendas Internas] + [Meta Vendas Externas] | Validação. |
| **VPL_Geral / VPL Interno / VPL Externo** | Percentual VPL (reserva/tabela - 1); geral, só Prati (idimobiliaria=2) ou externo. | Tabela de vendas (vpl_reserva, vpl_tabela, idimobiliaria). | Visuais de VPL. |

---

## 7. Metas e Realizados por Empreendimento (MeasureTable_Metas_Realizado_Faturamento_Lucro)

Todas têm **origem** em **metas_realizado_faturamento_lucro_empreendimentos** (meta_faturamento, realizado_faturamento, realizado_lucro).  
**Destino:** **mFaturamentoEmpreendimento_nova** e visuais por empreendimento.

| Medida | Propósito |
|--------|-----------|
| **Meta Faturamento Empreendimentos** | Soma da meta de faturamento por empreendimento. |
| **Realizado Faturamento Empreendimentos** | Soma do realizado de faturamento por empreendimento. |
| **Realizado Lucro Empreendimentos** | Soma do realizado de lucro por empreendimento. |
| **% Realizado Faturamento Empreendimentos** | Realizado / Meta faturamento por empreendimento. |

---

## 8. Margem de Contribuição (MeasureTable_Margem_Contribuicao)

| Medida | Propósito | Origem | Destino |
|--------|-----------|--------|---------|
| **Selected Measure_Margem_Contribuicao** | Controla exibição: 1=Meta, 2=Realizado, 3=%. | Valor fixo 1 (ou seletor da Tabela_Medidas_Margem_Contribuicao). | mMargem_Contribuicao, mMargem_Contribuicao_Agrupada. |
| **Meta Margem Contribuição** | Meta de margem de contribuição (meta faturamento × % margem por empreendimento). | metas_margem_contribuicao_empreendimentos, metas_realizado_faturamento_lucro_empreendimentos (meta_faturamento). | % Realizado Margem Contribuição, mMargem_Contribuicao, mMargem_Contribuicao_Agrupada. |
| **Realizado Margem Contribuição** | Realizado de margem (realizado faturamento × % margem). | metas_realizado_faturamento_lucro_empreendimentos[realizado_lucro] (conforme versão atual do modelo). | % Realizado Margem Contribuição, mMargem_Contribuicao, mMargem_Contribuicao_Agrupada. |
| **% Realizado Margem Contribuição** | Realizado / Meta margem contribuição. | [Realizado Margem Contribuição], [Meta Margem Contribuição]. | mMargem_Contribuicao, mMargem_Contribuicao_Agrupada. |
| **mMargem_Contribuicao** | Exibe Meta, Realizado ou % formatado (milhões ou %) conforme seletor. | Selected Measure_Margem_Contribuicao + as 3 medidas acima. | Visuais. |
| **mMargem_Contribuicao_Agrupada** | Idem, usando Tabela_Medidas_Margem_Contribuicao[MeasureValue]. | Tabela_Medidas_Margem_Contribuicao + mesmas medidas base. | Visuais (matriz/linhas). |

---

## 9. DGA (MeasureTable_DGA)

| Medida | Propósito | Origem | Destino |
|--------|-----------|--------|---------|
| **Meta DGA** | Meta DGA (mês a mês). | metas_realizado_faturamento_lucro_prati[meta_dga] | % Realizado DGA, mDGA_Agrupada. |
| **Realizado DGA** | Soma do valor DGA até o mês anterior. | DGA[valor], dim_dates (Flag_Mes_Passado=1). | % Realizado DGA, mDGA_Agrupada. |
| **% Realizado DGA** | Realizado / Meta DGA. | [Realizado DGA], [Meta DGA]. | mDGA_Agrupada. |
| **mDGA_Agrupada** | Exibe Meta, Realizado ou % conforme Tabela_Medidas_DGA. | Tabela_Medidas_DGA[MeasureValue] + as 3 medidas acima. | Visuais. |

---

## 10. Repasses (MeasureTable_Repasses)

| Medida | Propósito | Origem | Destino |
|--------|-----------|--------|---------|
| **Meta Repasses** | Meta de repasses (mês a mês). | Metas_Repasse[Valor_Meta] | % Realizado Repasses, mRepasses_Agrupada. |
| **Realizado Repasses** | Valor com situação = "Contrato Registrado" até mês anterior. | cv_repasses_MD[valor_contrato], dim_dates (Flag_Mes_Passado=1). | % Realizado Repasses, mRepasses_Agrupada. |
| **% Realizado Repasses** | Realizado / Meta repasses. | [Realizado Repasses], [Meta Repasses]. | mRepasses_Agrupada. |
| **mRepasses_Agrupada** | Exibe Meta, Realizado ou % conforme Tabela_Medidas_Repasses. | Tabela_Medidas_Repasses + as 3 medidas acima. | Visuais. |

---

## 11. RH (MeasureTable_RH)

**Origem:** **Indicadores_RH_Geral**, **Metas_RH**, **metas_horas_treinamentos**.  
**Destino:** **mRH_Agrupada** e visuais de RH.

| Medida | Propósito |
|--------|-----------|
| **Realizado Headcount / Atestados / Turnover / Absenteismo / Turnover 90d, 1ano, +1ano** | Valores realizados dos indicadores (soma ou média conforme indicador). |
| **Meta Atestados / Turnover / Absenteismo / Headcount / Treinamentos** | Metas vindas de Metas_RH (por indicador). |
| **Realizado Treinamentos** | Horas de treinamento (metas_horas_treinamentos). |
| **mRH_Agrupada** | Exibe Meta ou Realizado conforme Tabela_Medidas_RH. |

---

## 12. Inadimplência e ProSoluto (MeasureTable_Inadimplencia_ProSoluto)

**Origem:** Meta fixa (1% e 8%); realizados = **%Indimplência_Novo** e **%ProSoluto_Novo** (contas_recebidas_receber- API). **Destino:** mInadimplencia_ProSoluto_Agrupada e visuais.

| Medida | Propósito |
|--------|-----------|
| **Meta Inadimplência** | 1% (fixo). |
| **Realizado Inadimplência** | [%Indimplência_Novo]. |
| **% Realizado Inadimplência** | Realizado / Meta. |
| **Meta ProSoluto** | 8% (fixo). |
| **Realizado ProSoluto** | [%ProSoluto_Novo]. |
| **% Realizado ProSoluto** | Realizado / Meta. |

---

## 13. Comissões (MeasureTable_Comissoes)

| Medida | Propósito | Observações |
|--------|-----------|-------------|
| **% Comissão por Imobiliária** | Percentual que cada imobiliária representa sobre o total de comissões. | **Erro semântico:** depende de "Valor Comissões YTD (Mês Anterior)", que não existe no modelo. Criar a medida base ou ajustar a fórmula. |

---

## 14. RH por Equipe (MeasureTable_RH_Equipe)

**Origem:** **Indicadores_RH_Equipe**. **Destino:** **mRH_Equipe_Agrupada** e visuais por equipe.  
Medidas: Realizado Headcount/Turnover (90d, 1ano, +1ano)/Absenteismo/Atestados Equipe; **mRH_Equipe_Agrupada** usa Tabela_Medidas_RH_Equipe para exibição dinâmica.

---

## 15. Caixa Mínimo (MeasureTable_Caixa_Minimo)

| Medida | Propósito | Origem | Destino |
|--------|-----------|--------|---------|
| **Meta Caixa Mínimo** | Valor fixo 8.375.000. | Constante 8375000 | mCaixa_Minimo_Agrupada, Realizado Caixa Mínimo. |
| **Realizado Caixa Mínimo** | "Sim" se realizado ≥ meta no mês passado, "Não" caso contrário. | Saldo_bancario_caixa_minimo, dim_dates (Flag_Mes_Passado=1). | mCaixa_Minimo_Agrupada. |
| **mCaixa_Minimo_Agrupada** | Exibe Meta (em milhões) ou Realizado (Sim/Não) conforme seletor. | Tabela_Medidas_Caixa_Minimo + as duas acima. | Visuais. |

---

## 16. Distrato Contábil (MeasureTable_Distrato_Contabil)

**Origem:** **metas_realizado_faturamento_lucro_prati** (meta_distrato_contabil, realizado_distrato_contabil). **Destino:** mDistrato_Contabil_Agrupada e visuais.  
Medidas: Meta Distrato Contábil, Realizado Distrato Contábil, % Realizado Distrato Contábil, mDistrato_Contabil_Agrupada.

---

## 17. Endividamento (MeasureTable_Endividamento)

**Origem:** **metas_realizado_faturamento_lucro_prati** (meta_endividamento, realizado_endividamento). **Destino:** mEndividamento_Agrupada e visuais.  
Medidas: Meta Endividamento, Realizado Endividamento, % Realizado Endividamento, mEndividamento_Agrupada.  
**Realziado endividadmento Bancario:** nome com typo; expressão vazia na API – definir fórmula ou remover.

---

## Resumo de dependências entre tabelas de medidas

- **metas_realizado_faturamento_lucro_prati** → alimenta EBITDA, Metas/Realizados Prati, Percentuais, DGA, Distrato, Endividamento, Margem (em parte).
- **metas_realizado_faturamento_lucro_empreendimentos** → alimenta Margem de Contribuição e medidas por empreendimento.
- **contas_recebidas_receber- API** → alimenta todas as medidas de inadimplência e ProSoluto.
- **dim_dates** → usado em quase todas as medidas que filtram por período ou YTD.
- **Selected Measure / Selected Measure_vendas / Selected Measure EBITDA / etc.** → controlam qual valor exibir nas medidas “agrupadas” (m*_Agrupada).

---

## Medidas com erro ou expressão vazia (ação recomendada)

| Medida | Problema | Ação sugerida |
|--------|----------|----------------|
| **pct_realizado_distrato_YTD_mês_anterior** | Referencia medidas inexistentes. | Criar vlr_distrato_YTD_mês_anterior e vlr_meta_distrato_YTD_mês_anterior ou remover/alterar. |
| **% Comissão por Imobiliária** | Referencia "Valor Comissões YTD (Mês Anterior)" inexistente. | Criar a medida base ou corrigir o nome na expressão. |
| **Realziado endividadmento Bancario** | Expressão vazia; nome com typo. | Incluir expressão DAX ou remover; corrigir nome se mantida. |

---

*Documento gerado para manutenção do modelo ADM FULL - Diretoria administrativa. Para alterar uma medida, verifique a seção "Destino" para avaliar impacto em outras medidas e visuais.*
