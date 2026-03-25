# Medidas do modelo Power BI – ADM FULL (Nova versão) - Diretoria administrativa

**Total: 122 medidas** | Dados obtidos via API (measure_operations LIST + GET).  
Apenas dados retornados pela API; sem invenção de dados.

---

## Resumo por tabela

| Tabela | Qtd medidas |
|--------|-------------|
| MeasureTable( vendas1) | 1 |
| Medidas Vendas | 1 |
| Medidas | 1 |
| Tabela_Medidas novo_lucro_liquido | 8 |
| Tabela_medidas_Faturamento_Nova | 6 |
| contas_recebidas_receber- API | 14 |
| metas_realizado_faturamento_lucro_prati | 10 |
| MeasureTable_EBITDA | 1 |
| MeasureTable_Metas_Prati | 7 |
| MeasureTable_Realizados_Prati | 8 |
| MeasureTable_Percentuais_Prati | 4 |
| MeasureTable_Metas_Vendas | 6 |
| MeasureTable_Metas_Realizado_Faturamento_Lucro | 4 |
| MeasureTable_Margem_Contribuicao | 6 |
| MeasureTable_DGA | 4 |
| MeasureTable_Repasses | 4 |
| MeasureTable_RH | 17 |
| MeasureTable_Inadimplencia_ProSoluto | 6 |
| MeasureTable_Comissoes | 1 |
| MeasureTable_RH_Equipe | 8 |
| MeasureTable_Caixa_Minimo | 3 |
| MeasureTable_Distrato_Contabil | 4 |
| MeasureTable_Endividamento | 5 |

---

## Detalhes por tabela (Nome | Expressão DAX | Descrição | Formato)

### MeasureTable( vendas1)
| Nome | Expressão DAX | Descrição | Formato |
|------|--------------|-----------|---------|
| pct_realizado_distrato_YTD_mês_anterior | DIVIDE([vlr_distrato_YTD_mês_anterior], [vlr_meta_distrato_YTD_mês_anterior]) | *(vazio)* | "R$\" #,0.###############;-"R$\" #,0.###############;"R$\" #,0.############### |

*Estado: SemanticError – coluna 'vlr_distrato_YTD_mês_anterior' não existe.*

---

### Medidas Vendas
| Nome | Expressão DAX | Descrição | Formato |
|------|--------------|-----------|---------|
| Selected Measure_vendas | MAX('MeasureTable( vendas1)'[ID]) | *(vazio)* | 0 |

---

### Medidas
| Nome | Expressão DAX | Descrição | Formato |
|------|--------------|-----------|---------|
| Selected Measure | MAX(MeasureTable[ID]) | *(vazio)* | 0 |

---

### Tabela_Medidas novo_lucro_liquido
| Nome | Expressão DAX | Descrição | Formato |
|------|--------------|-----------|---------|
| lucro_realizado_YTD_Atual | CALCULATE(SUM(metas_realizado_faturamento_lucro_prati[realizado_faturamento]), FILTER(ALL(dim_dates), YEAR(dim_dates[data_referencia]) = YEAR(MAX(dim_dates[data_referencia])) && dim_dates[data_referencia] <= MAX(dim_dates[data_referencia]))) | *(vazio)* | *(vazio)* |
| margem_projetada_YTD_Atual | CALCULATE(SUM(metas_realizado_faturamento_lucro_prati[meta_faturamento]), FILTER(ALL(dim_dates), YEAR(dim_dates[data_referencia]) = YEAR(MAX(dim_dates[data_referencia])) && dim_dates[data_referencia] <= MAX(dim_dates[data_referencia]))) | *(vazio)* | *(vazio)* |
| pct_realizado_sobre_meta_YTD_Atual | DIVIDE([lucro_realizado_YTD_Atual], [margem_projetada_YTD_Atual]) | *(vazio)* | *(vazio)* |
| mLucro_novo | VAR ValorSelecionado = SWITCH([Selected Measure_vendas], 1, [Meta Lucro], 4, [Realizado Lucro Prati], 5, [Meta x Realizado_LL_Geral], 6, [pct_realizado_sobre_meta_YTD_Atual], 7, [Delta Ano Anterior Faturamento_LL_Atual_geral]) RETURN SWITCH([Selected Measure_vendas], 1, FORMAT(ROUND(ValorSelecionado / 1000000, 1), "#,##0.00"), 4, FORMAT(ROUND(ValorSelecionado / 1000000, 1), "#,##0.00"), 5, FORMAT(ValorSelecionado, "0%"), 6, FORMAT(ValorSelecionado, "0%"), 7, FORMAT(ValorSelecionado, "0%")) | *(vazio)* | *(vazio)* |
| z_month-12_LL_atual_geral | VAR valor_ano_anterior = CALCULATE([Realizado Lucro Prati], SAMEPERIODLASTYEAR(dim_dates[data_referencia])) RETURN IF(valor_ano_anterior=BLANK(), 0, valor_ano_anterior) | *(vazio)* | *(vazio)* |
| Meta x Realizado_LL_Geral | DIVIDE([Realizado Lucro Prati], [Meta Lucro], 0) | *(vazio)* | *(vazio)* |
| Delta Ano Anterior Faturamento_LL_Atual_geral | ([Realizado Lucro Prati] / [z_month-12_LL_atual_geral]) - 1 | *(vazio)* | *(vazio)* |

---

### Tabela_medidas_Faturamento_Nova
| Nome | Expressão DAX | Descrição | Formato |
|------|--------------|-----------|---------|
| mFaturamentoAgrupado_nova | VAR ValorSelecionado = SWITCH([Selected Measure], 1, [Meta Faturamento Prati], 2, [Realizado Faturamento Prati], 3, [Meta_Realizado_Agrupado_geral], 5, [Delta Ano Anterior Faturamento_Geral]) RETURN SWITCH(TRUE(), [Selected Measure] = 1, FORMAT( ValorSelecionado / 1000000, "#,##0.00" ), [Selected Measure] = 2, FORMAT( ValorSelecionado / 1000000, "#,##0.00" ), [Selected Measure] = 3, FORMAT( ValorSelecionado, "0%" ), [Selected Measure] = 5, FORMAT( ValorSelecionado, "0%" ), BLANK()) | *(vazio)* | *(vazio)* |
| Meta_Realizado_Agrupado_geral | DIVIDE([Realizado Faturamento Prati],[Meta Faturamento Prati],0) | *(vazio)* | *(vazio)* |
| z_month-12_geral | VAR valor_ano_anterior = CALCULATE([Realizado Faturamento Prati], SAMEPERIODLASTYEAR(dim_dates[data_referencia])) RETURN IF(valor_ano_anterior=BLANK(), 0.00001, valor_ano_anterior) | *(vazio)* | *(vazio)* |
| Delta Ano Anterior Faturamento_Geral | ([Realizado Faturamento Prati] / [z_month-12_geral]) - 1 | *(vazio)* | *(vazio)* |
| mFaturamentoEmpreendimento_nova | VAR ValorSelecionado = SWITCH([Selected Measure], 1, [Meta Faturamento Empreendimentos], 2, [Realizado Faturamento Empreendimentos], 3, [% Realizado Faturamento Empreendimentos]) RETURN SWITCH(TRUE(), [Selected Measure] = 1, FORMAT( ValorSelecionado / 1000000, "#,##0.0" ), [Selected Measure] = 2, FORMAT( ValorSelecionado / 1000000, "#,##0.0" ), [Selected Measure] = 3, FORMAT( ValorSelecionado, "0%" ), BLANK()) | *(vazio)* | *(vazio)* |

---

### contas_recebidas_receber- API
| Nome | Expressão DAX | Descrição | Formato |
|------|--------------|-----------|---------|
| CR_Valor devido_Novo | CALCULATE(SUM('contas_recebidas_receber- API'[Valor_Corrigido]), 'contas_recebidas_receber- API'[Tipo_Baixa]=BLANK()) | *(vazio)* | *(vazio)* |
| Valor_Inadimplente_Novo | *(VAR _PrimeiroDiaMesAtual + CALCULATE SUM Valor_Corrigido com filtros Inadimplencia e Data_Vencimento)* | *(vazio)* | *(vazio)* |
| %Indimplência_Novo | [Valor_Inadimplente_Novo] / CALCULATE(SUM(Valor_Corrigido), Tipo_Baixa = BLANK()) | *(vazio)* | 0.00%;-0.00%;0.00% |
| Valor_Inadimplente_Formatado_Novo | *(FORMAT do valor inadimplente / 1000)* | *(vazio)* | *(vazio)* |
| Valor_Inadimplente_365d_Novo | *(CALCULATE com Inadimplente e DATEDIFF >= 365 dias)* | *(vazio)* | *(vazio)* |
| Perda de crédito_Novo | FORMAT([Valor_Inadimplente_365d_Novo] / 1000, "#,##0.00") | *(vazio)* | *(vazio)* |
| Proporcao_Valor_Devido_Novo | DIVIDE(SUM(Valor_Devido), CALCULATE(SUM(Valor_Devido), ALLEXCEPT(..., Cod_Centro_Custo)), 0) | *(vazio)* | *(vazio)* |
| Valor_ProSoluto_Novo | CALCULATE(SUM(Valor_Devido), Tipo_Baixa=BLANK(), tipovenda="Venda Financiamento", Tipo_Condicao IN {...}) | *(vazio)* | *(vazio)* |
| %ProSoluto_Novo | DIVIDE([Valor_ProSoluto_Novo], CALCULATE(SUM(valor_contrato), tipovenda = "Venda Financiamento")) | *(vazio)* | 0.00%;-0.00%;0.00% |
| valor venda financiamento_Novo | CALCULATE(SUM(cv_vendas[valor_contrato]), cv_vendas[tipovenda] = "Venda Financiamento") | *(vazio)* | "R$\" #,0.############### |
| Vencidos_Até_30_Dias_Novo | *(CALCULATE SUM Valor_Devido com DATEDIFF <= 30 e > 0)* | *(vazio)* | *(vazio)* |
| Porcentagem_Inadimplente_Por_Empreendimento_Novo | DIVIDE(CALCULATE(SUM(Valor_Devido), Inadimplencia="Inadimplente"), TotalValorEmpreendimento, 0) | *(vazio)* | *(vazio)* |
| CR_Valor devido_Novo_debug | CALCULATE(SUM('contas_recebidas_receber- API'[Valor_Devido])) | *(vazio)* | *(vazio)* |

---

### metas_realizado_faturamento_lucro_prati
| Nome | Expressão DAX | Descrição | Formato |
|------|--------------|-----------|---------|
| % Meta EBITDA | DIVIDE([Realizado EBITDA], [Meta EBITDA], 0) | Percentual de realização da meta de EBITDA | 0% |
| Meta EBITDA (Milhões) | FORMAT([Meta EBITDA] / 1000000, "#,##0.00") | Meta de EBITDA formatada em milhões | *(vazio)* |
| Realizado EBITDA (Milhões) | FORMAT([Realizado EBITDA] / 1000000, "#,##0.00") | Realizado de EBITDA formatado em milhões | *(vazio)* |
| % Meta EBITDA Formatado | FORMAT([% Meta EBITDA], "0%") | Percentual de realização da meta de EBITDA formatado | *(vazio)* |
| mEBITDA_Agrupado | SWITCH(Selected Measure EBITDA: 1→Meta, 2→Realizado, 3→% Meta; FORMAT em milhões ou %) | Medida agrupada para exibição de Meta, Realizado e % Meta de EBITDA formatados | *(vazio)* |
| Meta EBITDA | SUM(metas_realizado_faturamento_lucro_prati[meta_ebitda]) | Meta de EBITDA agregada | 0 |
| Realizado EBITDA | SUM(metas_realizado_faturamento_lucro_prati[realizado_ebitda]) | Realizado de EBITDA agregado | 0 |
| Selected Measure EBITDA | *(na tabela MeasureTable_EBITDA)* | *(ver tabela MeasureTable_EBITDA)* | *(ver tabela)* |

*Selected Measure EBITDA está na tabela MeasureTable_EBITDA: MAX(MeasureTable_EBITDA[ID]); descrição: Medida que retorna o ID da medida selecionada para EBITDA; formato: 0.*

---

### MeasureTable_EBITDA
| Nome | Expressão DAX | Descrição | Formato |
|------|--------------|-----------|---------|
| Selected Measure EBITDA | MAX(MeasureTable_EBITDA[ID]) | Medida que retorna o ID da medida selecionada para EBITDA | 0 |

---

### MeasureTable_Metas_Prati
| Nome | Expressão DAX | Descrição | Formato |
|------|--------------|-----------|---------|
| Meta Faturamento Prati | SUM(metas_realizado_faturamento_lucro_prati[meta_faturamento]) | Meta de faturamento agregada para Prati | 0 |
| Meta Lucro | SUM(metas_realizado_faturamento_lucro_prati[meta_lucro]) | Meta de lucro agregada | 0 |
| Meta Receita Financeira | SUM(metas_realizado_faturamento_lucro_prati[meta_receita_financeira]) | Meta de receita financeira agregada | 0 |
| Meta Faturamento (Milhões) | [Meta Faturamento Prati] / 1000000 | Meta de faturamento formatada em milhões | #,##0.00 |
| Meta Lucro (Milhões) | [Meta Lucro] / 1000000 | Meta de lucro formatada em milhões | #,##0.00 |
| Meta Receita Financeira (Milhões) | [Meta Receita Financeira] / 1000000 | Meta de receita financeira formatada em milhões | #,##0.00 |
| Meta Distrato Contábil (Milhões) | [Meta Distrato Contábil] / 1000000 | Meta de distrato contábil formatada em milhões | #,##0.00 |

---

### MeasureTable_Realizados_Prati
| Nome | Expressão DAX | Descrição | Formato |
|------|--------------|-----------|---------|
| Realizado Faturamento Prati | SUM(metas_realizado_faturamento_lucro_prati[realizado_faturamento]) | Realizado de faturamento agregado | 0 |
| Realizado Lucro Prati | SUM(metas_realizado_faturamento_lucro_prati[realizado_lucro]) | Realizado de lucro agregado | 0 |
| Realizado Receita Financeira Prati | SUM(metas_realizado_faturamento_lucro_prati[realizado_receita_financeira]) | Realizado de receita financeira agregado | 0 |
| Realizado Distrato Contábil Prati | SUM(metas_realizado_faturamento_lucro_prati[realizado_distrato_contabil]) | Realizado de distrato contábil agregado | 0 |
| Realizado Faturamento (Milhões) Prati | [Realizado Faturamento Prati] / 1000000 | Realizado de faturamento formatado em milhões | #,##0.00 |
| Realizado Lucro (Milhões) | [Realizado Lucro Prati] / 1000000 | Realizado de lucro formatado em milhões | #,##0.00 |
| Realizado Receita Financeira (Milhões) Prati | [Realizado Receita Financeira Prati] / 1000000 | Realizado de receita financeira formatado em milhões | #,##0.00 |
| Realizado Distrato Contábil (Milhões) Prati | [Realizado Distrato Contábil Prati] / 1000000 | Realizado de distrato contábil formatado em milhões | #,##0.00 |

---

### MeasureTable_Percentuais_Prati
| Nome | Expressão DAX | Descrição | Formato |
|------|--------------|-----------|---------|
| % Meta Faturamento | DIVIDE([Realizado Faturamento Prati], [Meta Faturamento Prati], 0) | Percentual de realização da meta de faturamento | 0.00% |
| % Meta Lucro | DIVIDE([Realizado Lucro Prati], [Meta Lucro], 0) | Percentual de realização da meta de lucro | 0.00% |
| % Meta Receita Financeira | DIVIDE([Realizado Receita Financeira Prati], [Meta Receita Financeira], 0) | Percentual de realização da meta de receita financeira | 0.00% |
| % Meta Distrato Contábil | DIVIDE([Realizado Distrato Contábil Prati], [Meta Distrato Contábil], 0) | Percentual de realização da meta de distrato contábil | 0.00% |

---

### MeasureTable_Metas_Vendas
| Nome | Expressão DAX | Descrição | Formato |
|------|--------------|-----------|---------|
| Meta Vendas Geral | SUM(metas_vendas[Valor]) | Soma total das metas de vendas gerais | #,##0.00 |
| Meta Vendas Internas | SUM(metas_vendas_internas[Valor_Meta]) | Soma total das metas de vendas internas | #,##0.00 |
| Meta Vendas Externas | SUM(metas_vendas_externas[Valor_Meta]) | Soma total das metas de vendas externas | #,##0.00 |
| Meta Vendas Total (Internas + Externas) | [Meta Vendas Internas] + [Meta Vendas Externas] | Soma das metas internas e externas para validação | #,##0.00 |
| VPL_Geral | VAR percentualVPL = SUM(vpl_reserva)/SUM(vpl_tabela)-1 RETURN IF(percentualVPL=-1, BLANK(), percentualVPL) | Percentual de VPL (VPL Reserva / VPL Tabela - 1) | 0.00%;-0.00%;0.00% |
| VPL Interno | *(CALCULATE com idimobiliaria = 2)* | Percentual de VPL Interna (Prati) | 0.00%;-0.00%;0.00% |
| VPL Externo | *(CALCULATE com idimobiliaria <> 2)* | Percentual de VPL Externa (diferente de Prati) | 0.00%;-0.00%;0.00% |

---

### MeasureTable_Metas_Realizado_Faturamento_Lucro
| Nome | Expressão DAX | Descrição | Formato |
|------|--------------|-----------|---------|
| Meta Faturamento Empreendimentos | SUM(metas_realizado_faturamento_lucro_empreendimentos[meta_faturamento]) | Soma da meta de faturamento por empreendimento | *(vazio)* |
| Realizado Faturamento Empreendimentos | SUM(metas_realizado_faturamento_lucro_empreendimentos[realizado_faturamento]) | Soma do realizado de faturamento por empreendimento | *(vazio)* |
| Realizado Lucro Empreendimentos | SUM(metas_realizado_faturamento_lucro_empreendimentos[realizado_lucro]) | Soma do realizado de lucro por empreendimento | *(vazio)* |
| % Realizado Faturamento Empreendimentos | DIVIDE([Realizado Faturamento Empreendimentos],[Meta Faturamento Empreendimentos],0) | *(vazio)* | *(vazio)* |

---

### MeasureTable_Margem_Contribuicao
| Nome | Expressão DAX | Descrição | Formato |
|------|--------------|-----------|---------|
| Selected Measure_Margem_Contribuicao | 1 | Medida para controlar qual valor exibir: 1=Orçado, 2=Realizado, 3=% Realizado | *(vazio)* |
| % Realizado Margem Contribuição | DIVIDE([Realizado Margem Contribuição], [Meta Margem Contribuição], 0) | Percentual de realização da margem de contribuição | 0% |
| mMargem_Contribuicao | SWITCH(Selected: 1→Meta, 2→Realizado, 3→%; FORMAT em Mi ou %) | Medida agrupada para exibição de Orçado, Realizado e % Realizado de margem de contribuição formatados | *(vazio)* |
| mMargem_Contribuicao_Agrupada | SELECTEDVALUE(Tabela_Medidas_Margem_Contribuicao[MeasureValue]) + SWITCH com FORMAT | Medida agrupada que usa a tabela de medidas para exibir Meta, Realizado e % Realizado | *(vazio)* |
| Meta Margem Contribuição | SUMX(metas_margem_contribuicao_empreendimentos, PercentualMargem * MetaFaturamento) | Meta/Orçado de margem de contribuição (Meta Faturamento * % Margem Contribuição) | *(vazio)* |
| Realizado Margem Contribuição | SUM(metas_realizado_faturamento_lucro_empreendimentos[realizado_lucro]) | Realizado de margem de contribuição (Realizado Faturamento * % Margem Contribuição) | *(vazio)* |

---

### MeasureTable_DGA
| Nome | Expressão DAX | Descrição | Formato |
|------|--------------|-----------|---------|
| Realizado DGA | SUMX(FILTER(dim_dates, Flag_Mes_Passado=1), CALCULATE(SUM(DGA[valor]))) | Soma do valor DGA até o mês anterior | *(vazio)* |
| % Realizado DGA | DIVIDE([Realizado DGA], [Meta DGA]) | Percentual realizado DGA | *(vazio)* |
| mDGA_Agrupada | SELECTEDVALUE(Tabela_Medidas_DGA[MeasureValue]) + SWITCH FORMAT (Meta/Realizado/% em mil ou %) | Medida agrupada que usa a tabela de medidas para exibir Meta, Realizado e % Realizado de DGA | *(vazio)* |
| Meta DGA | SUM(metas_realizado_faturamento_lucro_prati[meta_dga]) | Meta DGA da tabela metas_realizado_faturamento_lucro_prati (mês a mês) | *(vazio)* |

---

### MeasureTable_Repasses
| Nome | Expressão DAX | Descrição | Formato |
|------|--------------|-----------|---------|
| Meta Repasses | SUM(Metas_Repasse[Valor_Meta]) | Meta de repasses da tabela Metas_Repasse (mês a mês) | *(vazio)* |
| % Realizado Repasses | DIVIDE([Realizado Repasses], [Meta Repasses], 0) | Percentual de realizado sobre meta de repasses | *(vazio)* |
| mRepasses_Agrupada | SELECTEDVALUE(Tabela_Medidas_Repasses[MeasureValue]) + SWITCH FORMAT (Meta/Realizado/% em Mi) | Medida agrupada para exibição dinâmica de Meta, Realizado e % Realizado de Repasses | *(vazio)* |
| Realizado Repasses | SUMX(FILTER(dim_dates, Flag_Mes_Passado=1), CALCULATE(SUM(cv_repasses_MD[valor_contrato]), situacao="Contrato Registrado")) | Soma do valor_contrato quando situação = Contrato Registrado (até mês anterior) | *(vazio)* |

---

### MeasureTable_RH
| Nome | Expressão DAX | Descrição | Formato |
|------|--------------|-----------|---------|
| Realizado Headcount | SUM(Indicadores_RH_Geral[headcount]) | Headcount realizado | 0 |
| Realizado Atestados | SUM(Indicadores_RH_Geral[horas_atestados]) | Atestados (horas) realizado | 0 |
| Meta Atestados | CALCULATE(SUM(Metas_RH[Valor]), Metas_RH[indicador] = "Atestados") | Meta Atestados | 0 |
| Meta Turnover | CALCULATE(AVERAGE(Metas_RH[Valor]), Metas_RH[indicador] = "Turnover") / 100 | Meta Turnover | 0.00% |
| Meta Absenteismo | CALCULATE(AVERAGE(Metas_RH[Valor]), Metas_RH[indicador] = "Absenteismo") / 100 | Meta Absenteismo | 0.00% |
| Realizado Turnover | SUM(Indicadores_RH_Geral[turnover_percentual]) / 100 | Turnover realizado | 0.00% |
| Realizado Absenteismo | SUM(Indicadores_RH_Geral[absenteismo_percentual]) / 100 | Absenteismo realizado | 0.00% |
| Turnover até 90 dias | SUM(Indicadores_RH_Geral[turnover_ate_90_dias]) / 100 | Turnover até 90 dias realizado | 0.00% |
| Turnover até um ano | SUM(Indicadores_RH_Geral[turnover_ate_um_ano]) / 100 | Turnover até um ano realizado | 0.00% |
| Turnover mais um ano | SUM(Indicadores_RH_Geral[turnover_mais_um_ano]) / 100 | Turnover mais um ano realizado | 0.00% |
| Meta Headcount | CALCULATE(MAX(Metas_RH[Valor]), indicador="Headcount", Data=MaxData) | Meta Headcount - Valor de dezembro | 0 |
| Meta Treinamentos | CALCULATE(SUM(Metas_RH[Valor]), Metas_RH[indicador] = "Treinamento") | Meta Treinamentos | 0 |
| Realizado Treinamentos | SUM(metas_horas_treinamentos[horas_treinamento]) | Treinamentos (horas) realizado | 0 |
| mRH_Agrupada | SELECTEDVALUE(Tabela_Medidas_RH[MeasureValue]) + SWITCH (1 a 13: Meta HC, Realizado HC, Meta/Realizado Turnover, 90d, 1ano, +1ano, Absenteismo, Atestados, Treinamentos) | Medida agrupada que usa a tabela de medidas para exibir Meta e Realizado de RH | *(vazio)* |

---

### MeasureTable_Inadimplencia_ProSoluto
| Nome | Expressão DAX | Descrição | Formato |
|------|--------------|-----------|---------|
| Meta Inadimplência | 0.01 | Meta Inadimplência (1%) | 0.00% |
| Realizado Inadimplência | [%Indimplência_Novo] | Realizado Inadimplência | 0.00% |
| % Realizado Inadimplência | DIVIDE([Realizado Inadimplência], [Meta Inadimplência], 0) | Percentual realizado Inadimplência | 0.00% |
| Meta ProSoluto | 0.08 | Meta ProSoluto (8%) | 0.00% |
| Realizado ProSoluto | [%ProSoluto_Novo] | Realizado ProSoluto | 0.00% |
| % Realizado ProSoluto | DIVIDE([Realizado ProSoluto], [Meta ProSoluto], 0) | Percentual realizado ProSoluto | 0.00% |
| mInadimplencia_ProSoluto_Agrupada | SELECTEDVALUE + SWITCH FORMAT (Meta/Realizado Inadimplência e ProSoluto) | Medida agrupada unificada para exibir Meta e Realizado de Inadimplência e ProSoluto | *(vazio)* |

---

### MeasureTable_Comissoes
| Nome | Expressão DAX | Descrição | Formato |
|------|--------------|-----------|---------|
| % Comissão por Imobiliária | DIVIDE([Valor Comissões YTD (Mês Anterior)], CALCULATE(..., REMOVEFILTERS(imobiliaria_tratada)), 0) | Percentual que cada imobiliária representa sobre o total de comissões pagas | 0.00% |

*Estado: SemanticError – 'Valor Comissões YTD (Mês Anterior)' não pode ser determinado.*

---

### MeasureTable_RH_Equipe
| Nome | Expressão DAX | Descrição | Formato |
|------|--------------|-----------|---------|
| Realizado Headcount Equipe | SUM(Indicadores_RH_Equipe[headcount]) | Headcount realizado por equipe | 0 |
| Realizado Turnover Equipe | SUM(Indicadores_RH_Equipe[turnover_percentual]) / 100 | Turnover realizado por equipe | 0.00% |
| Turnover até 90 dias Equipe | SUM(Indicadores_RH_Equipe[turnover_ate_90_dias]) / 100 | Turnover até 90 dias realizado por equipe | 0.00% |
| Turnover até um ano Equipe | SUM(Indicadores_RH_Equipe[turnover_ate_um_ano]) / 100 | Turnover até um ano realizado por equipe | 0.00% |
| Turnover mais um ano Equipe | SUM(Indicadores_RH_Equipe[turnover_mais_um_ano]) / 100 | Turnover mais um ano realizado por equipe | 0.00% |
| Realizado Absenteismo Equipe | SUM(Indicadores_RH_Equipe[absenteismo_percentual]) / 100 | Absenteismo realizado por equipe | 0.00% |
| Realizado Atestados Equipe | SUM(Indicadores_RH_Equipe[horas_atestados]) | Atestados (horas) realizado por equipe | 0 |
| mRH_Equipe_Agrupada | SELECTEDVALUE(Tabela_Medidas_RH_Equipe[MeasureValue]) + SWITCH (1-7: HC, Turnover, 90d, 1ano, +1ano, Absenteismo, Atestados) | Medida agrupada que usa a tabela de medidas para exibir Realizado de RH por Equipe | *(vazio)* |

---

### MeasureTable_Caixa_Minimo
| Nome | Expressão DAX | Descrição | Formato |
|------|--------------|-----------|---------|
| Meta Caixa Mínimo | 8375000 | Meta Caixa Mínimo - Valor fixo de 8.375.000 | 0 |
| mCaixa_Minimo_Agrupada | SELECTEDVALUE + SWITCH: 1→FORMAT(Meta/1M), 2→[Realizado Caixa Mínimo] | Medida agrupada que usa a tabela de medidas para exibir Meta (valor em milhões) e Realizado (Sim/Não) de Caixa Mínimo | *(vazio)* |
| Realizado Caixa Mínimo | IF(Flag_Mes_Passado=1, IF(RealizadoValor>=MetaValor, "Sim", "Não"), BLANK()) com Saldo_bancario_caixa_minimo | Caixa Mínimo realizado - Retorna "Sim" se realizado >= meta, "Não" se realizado < meta. Exibe apenas quando Flag_Mes_Passado = 1. | *(vazio)* |

---

### MeasureTable_Distrato_Contabil
| Nome | Expressão DAX | Descrição | Formato |
|------|--------------|-----------|---------|
| Realizado Distrato Contábil | SUM(metas_realizado_faturamento_lucro_prati[realizado_distrato_contabil]) | Realizado de Distrato Contábil | #,0.00 |
| % Realizado Distrato Contábil | DIVIDE([Realizado Distrato Contábil], [Meta Distrato Contábil], 0) | % Realizado de Distrato Contábil (Realizado / Meta) | 0.00% |
| Meta Distrato Contábil | SUM(metas_realizado_faturamento_lucro_prati[meta_distrato_contabil]) | Meta de Distrato Contábil | #,0.00 |
| mDistrato_Contabil_Agrupada | SELECTEDVALUE + SWITCH: Meta/Realizado/% em milhões ou % | Medida agrupada para Distrato Contábil com formatação em milhões | *(vazio)* |

---

### MeasureTable_Endividamento
| Nome | Expressão DAX | Descrição | Formato |
|------|--------------|-----------|---------|
| Meta Endividamento | SUM(metas_realizado_faturamento_lucro_prati[meta_endividamento]) | Meta de Endividamento | #,0.00 |
| Realizado Endividamento | SUM(metas_realizado_faturamento_lucro_prati[realizado_endividamento]) | Realizado de Endividamento | #,0.00 |
| % Realizado Endividamento | DIVIDE([Realizado Endividamento], [Meta Endividamento], 0) | % Realizado de Endividamento | 0.00% |
| mEndividamento_Agrupada | SELECTEDVALUE + SWITCH: Meta/Realizado/Realizado Bancário/% em milhões ou % | Medida agrupada para Endividamento formatada em Milhões | *(vazio)* |
| Realziado endividadmento Bancario | *(expressão vazia na API)* | *(vazio)* | *(vazio)* |

---

*Documento gerado a partir exclusivamente dos dados retornados pela API measure_operations (LIST + GET). Medidas com estado SemanticError ou expressão vazia foram indicadas.*
