# DOM Mapping — Páginas Secundárias do Cálculo

**Versão**: PJE-Calc 2.15.1  
**Auditado em**: 2026-05-04 via Chrome MCP no cálculo 262818  

⚠️ **Limitação observada**: a sessão Seam do PJE-Calc é frágil — clicar em links
do menu lateral exige cálculo aberto + estado consistente. A navegação via URL
direta (`?conversationId=N`) só funciona se o conversationId for o atual.
Em caso de "Erro Interno no Servidor", retornar a `principal.jsf` e re-abrir
o cálculo via dblclick em "Cálculos Recentes".

## 1. Dados do Cálculo (calculo.jsf)

**URL**: `/pjecalc/pages/calculo/calculo.jsf`  
**Tabs**: "Dados do Processo" | "Parâmetros do Cálculo"

### Cabeçalho (sempre visível)
| Campo | DOM ID | Tipo |
|---|---|---|
| Número Cálculo | `formulario:idCalculo` | text (readonly) |
| Tipo | `formulario:tipo` | text (readonly) |
| Data de Criação | `formulario:dataCriacao` | text (readonly) |

### Tab "Dados do Processo"
| Campo | DOM ID | Tipo | Valores |
|---|---|---|---|
| Informar Manualmente / PJe | `formulario:processoInformadoManualmente` | radio | true/false |
| Número Processo | `formulario:numero` | text | |
| Dígito | `formulario:digito` | text | |
| Ano | `formulario:ano` | text | |
| Justiça | `formulario:justica` | text | (5=Trabalhista) |
| Tribunal | `formulario:regiao` | text | |
| Vara | `formulario:vara` | text | |
| Valor da Causa | `formulario:valorDaCausa` | text | |
| Autuado em | `formulario:autuadoEm` | text | DD/MM/YYYY |
| Reclamante Nome | `formulario:reclamanteNome` | text | |
| Doc Fiscal Reclamante | `formulario:documentoFiscalReclamante` | radio | CPF/CNPJ/CEI |
| Nº Doc Fiscal | `formulario:reclamanteNumeroDocumentoFiscal` | text | |
| Doc Previd Reclamante | `formulario:reclamanteTipoDocumentoPrevidenciario` | radio | PIS/PASEP/NIT |
| Nº Doc Previd | `formulario:reclamanteNumeroDocumentoPrevidenciario` | text | |
| Advogado Reclamante (nome+OAB+doc) | `formulario:nomeAdvogadoReclamante` etc + `formulario:incluirAdvogadoReclamante` (anchor +) | | |
| Reclamado Nome | `formulario:reclamadoNome` | text | |
| Doc Fiscal Reclamado | `formulario:tipoDocumentoFiscalReclamado` | radio | CPF/CNPJ/CEI |
| Nº Doc Fiscal Reclamado | `formulario:reclamadoNumeroDocumentoFiscal` | text | |
| Advogado Reclamado | similar ao reclamante + `formulario:incluirAdvogadoReclamado` | | |

### Tab "Parâmetros do Cálculo"
| Campo | DOM ID | Tipo | Valores |
|---|---|---|---|
| Estado | `formulario:estado` | select | UF (AC..TO via id 0-26) |
| Município | `formulario:municipio` | select | (carregado AJAX após estado) |
| Data Admissão | `formulario:dataAdmissaoInputDate` | text | DD/MM/YYYY |
| Data Demissão | `formulario:dataDemissaoInputDate` | text | DD/MM/YYYY |
| Data Ajuizamento | `formulario:dataAjuizamentoInputDate` | text | DD/MM/YYYY |
| Data Início Cálculo | `formulario:dataInicioCalculoInputDate` | text | DD/MM/YYYY |
| Data Término Cálculo | `formulario:dataTerminoCalculoInputDate` | text | DD/MM/YYYY |
| Prescrição Quinquenal | `formulario:prescricaoQuinquenal` | checkbox | |
| Prescrição FGTS | `formulario:prescricaoFgts` | checkbox | |
| Tipo Base Tabelada | `formulario:tipoDaBaseTabelada` | select | INTEGRAL / PARCIAL / INTERMITENTE |
| Maior Remuneração | `formulario:valorMaiorRemuneracao` | text | |
| Última Remuneração | `formulario:valorUltimaRemuneracao` | text | |
| Apuração Aviso Prévio | `formulario:apuracaoPrazoDoAvisoPrevio` | select | NAO_APURAR / APURACAO_CALCULADA / APURACAO_INFORMADA |
| Projetar Aviso Indenizado | `formulario:projetaAvisoIndenizado` | checkbox | |
| Limitar Avos | `formulario:limitarAvos` | checkbox | |
| Zerar Valor Negativo | `formulario:zeraValorNegativo` | checkbox | |
| Considerar Feriado Estadual | `formulario:consideraFeriadoEstadual` | checkbox | |
| Considerar Feriado Municipal | `formulario:consideraFeriadoMunicipal` | checkbox | |
| Carga Horária Padrão | `formulario:valorCargaHorariaPadrao` | text | |
| Exceção CH — Início | `formulario:dataInicioExcecaoInputDate` | text | DD/MM/YYYY |
| Exceção CH — Fim | `formulario:dataTerminoExcecaoInputDate` | text | DD/MM/YYYY |
| Valor Carga Horária (exceção) | `formulario:valorCargaHoraria` | text | |
| Adicionar exceção CH | `formulario:incluirExcecaoCH` | anchor (+) | |
| Sábado dia útil | `formulario:sabadoDiaUtil` | checkbox | |
| Exceção Sábado — Início | `formulario:dataInicioExcecaoSabadoInputDate` | text | |
| Exceção Sábado — Fim | `formulario:dataTerminoExcecaoSabadoInputDate` | text | |
| Adicionar exceção Sábado | `formulario:incluirExcecaoSab` | anchor (+) | |
| Ponto Facultativo | `formulario:pontoFacultativo` | select | (lista de feriados regionais) |
| Adicionar Ponto Facultativo | `formulario:cmdAdicionarPontoFacultativo` | anchor | |
| Remover Ponto Facultativo (linha N) | `formulario:listagemPontosFacultativos:N:excluirPontoFacultativo` | anchor (X) | |
| Comentários | `formulario:comentarios` | textarea | |

### Botões finais
| Função | DOM ID |
|---|---|
| Salvar | `formulario:salvar` |
| Fechar / Cancelar | `formulario:cancelar` |

---

## 2. Cartão de Ponto (apuracao-cartaodeponto.jsf)

**URL**: `/pjecalc/pages/cartaodeponto/apuracao-cartaodeponto.jsf`  
**Listagem** tem 3 botões: Novo, Grade de Ocorrências, Visualizar Cartão.

### Form "Novo"
| Seção | Campo | DOM ID | Tipo | Valores |
|---|---|---|---|---|
| Período | Data Inicial | `formulario:competenciaInicialInputDate` | text | DD/MM/YYYY |
| | Data Final | `formulario:competenciaFinalInputDate` | text | DD/MM/YYYY |
| Forma Apuração | Tipo | `formulario:tipoApuracaoHorasExtras` | radio | NAO_APURAR_HORAS_EXTRAS, HORAS_EXTRAS_EXCEDENTES_DA_JORNADA_DIARIA, HORAS_EXTRAS_PELO_CRITERIO_MAIS_FAVORAVEL, HORAS_EXTRAS_CONFORME_SUMULA_85, APURA_PRIMEIRAS_HORAS_EXTRAS_SEPARADO, HORAS_EXTRAS_EXCEDENTES_DA_JORNADA_SEMANAL, HORAS_EXTRAS_EXCEDENTES_DA_JORNADA_MENSAL |
| | Qtd Súmula 85 | `formulario:qtsumulatst` | text | (HH:MM) |
| | Qtd Hora Separado | `formulario:qthoraseparado` | text | (HH:MM) |
| | Considerar Feriado | `formulario:considerarFeriado` | checkbox | |
| | Extras feriado em separado | `formulario:extraFeriadoSeparado` | checkbox | |
| | Extras domingos em separado | `formulario:extraDescansoSeparado` | checkbox | |
| | Extras sábados+domingos | `formulario:extraSabadoDomingoSeparado` | checkbox | |
| | Tolerância | `formulario:tolerancia` (checkbox) + `formulario:toleranciaPorTurno` + `formulario:toleranciaPorDia` | | (HH:MM) |
| Jornada Padrão | Seg | `formulario:valorJornadaSegunda` | text | HH:MM |
| | Ter | `formulario:valorJornadaTerca` | text | |
| | Qua | `formulario:valorJornadaQuarta` | text | |
| | Qui | `formulario:valorJornadaQuinta` | text | |
| | Sex | `formulario:valorJornadaSexta` | text | |
| | Sáb | `formulario:valorJornadaDiariaSabado` | text | |
| | Dom | `formulario:valorJornadaDiariaDom` | text | |
| | Jornada Semanal | `formulario:qtJornadaSemanal` | text | (calculada/editável) |
| | Jornada Mensal Média | `formulario:qtJornadaMensal` | text | |
| | Considerar jornada feriado trabalhado | `formulario:jornadaDiariaFeriadoTrabalhado` | checkbox | |
| | Considerar jornada feriado não-trabalhado | `formulario:jornadaDiariaFeriadoNaoTrabalhado` | checkbox | |
| Períodos Descanso | Apurar feriados trabalhados | `formulario:apurarFeriadosTrabalhados` | checkbox | |
| | Apurar domingos trabalhados | `formulario:apurarDomingosTrabalhados` | checkbox | |
| | Apurar sábados+domingos | `formulario:apurarSabadosDomingosTrabalhados` | checkbox | |
| | Supressão Art 384 CLT | `formulario:apurarSupressaoIntervalo384` | checkbox | |
| | Supressão Art 72 CLT | `formulario:apurarSupressaoIntervalo72` | checkbox | |
| | Supressão Art 253 CLT (insalubridade) | `formulario:apurarSupressaoIntervaloArt253` (checkbox) + `valorTrabalhoArt253` + `valorDescansoArt253` | | |
| | Intervalo Interjornadas | `formulario:descansoEntreJornadas` (checkbox) + `valorDescansoEntreJornadas` (select) + `valorDescansoEntreSemanas` (select) | | |
| | Intra >4h e <=6h | `formulario:intervaloIntraJornadaSupQuatroSeis` + `valorIntervaloIntraJornadaSupQuatroSeis` | checkbox+text | |
| | Intra >6h | `formulario:intervalorIntraJornadaSupSeis` + `valorIntervalorIntraJornadaSupSeis` + `toleranciaIntervaloIntraJornadaSupSeis` | | |
| | Considerar fracionamento intra | `formulario:considerarFracionamentoIntra` | checkbox | |
| | Apurar supressão integral | `formulario:apurarSupressaoIntervaloIntraIntegral` | checkbox | |
| | Apurar supressão (Reforma §4º Art 71) | `formulario:apurarSupressaoIntervaloIntraReforma` | checkbox | |
| | Apurar excesso intra (Súmula 118) | `formulario:apurarExcessoIntervaloIntra` (checkbox) + `valorIntervaloIntrajornadaMaximo` (text) | | |
| | Apurar apenas excesso jornada | `formulario:apurarApenasExcessoAcimaJornada` | checkbox | |
| Horário Noturno | Atividade | `formulario:horarioNoturnoApuracaroCartao` | radio | ATIVIDADE_AGRICOLA / ATIVIDADE_PECUARIA / ATIVIDADE_URBANA |
| | Apurar horas noturnas | `formulario:apurarHorasNoturnas` | checkbox | |
| | Apurar horas extras noturnas | `formulario:apurarHorasExtrasNoturnas` | checkbox | |
| | Considerar redução ficta | `formulario:considerarReducaoFictaDaHoraNoturna` | checkbox | |
| | Prorrogação Súmula 60 | `formulario:horarioProrrogadoSumula60` | checkbox | |
| | Forçar prorrogação | `formulario:forcarProrrogacao` | checkbox | |
| Preenchimento Jornadas | Tipo | `formulario:preenchimentoJornadasCartao` | radio | LIVRE / PROGRAMACAO / ESCALA |

⚠️ **Atenção** — após selecionar "Programação Semanal" ou "Escala", aparecem mais
campos para preenchimento dos dias específicos da semana com Turnos T1/T2.
A automação atual já trata isso (ver `playwright_pjecalc.py` fase 5b).

---

## 3. Faltas (falta.jsf)

**URL**: `/pjecalc/pages/calculo/falta.jsf`  
**Estrutura**: form direto (sem listagem separada — cada falta é adicionada
via botão "Incluir" e a lista aparece abaixo).

| Campo | DOM ID | Tipo |
|---|---|---|
| Data Início | `formulario:dataInicioPeriodoFaltaInputDate` | text DD/MM/YYYY |
| Data Término | `formulario:dataTerminoPeriodoFaltaInputDate` | text DD/MM/YYYY |
| Falta Justificada | `formulario:faltaJustificada` | checkbox |
| Reinicia Férias | `formulario:reiniciaFerias` | checkbox |
| Justificativa | `formulario:justificativaDaFalta` | textarea |
| Botão Incluir | `formulario:cmdIncluirFalta` | anchor |
| Importação CSV | `arquivo:file` (file) + `confirmarImportacao` (submit) | | |

---

## 4. Férias (ferias.jsf)

**URL**: `/pjecalc/pages/calculo/ferias.jsf`  
**Layout**: Importação CSV + "Regerar Períodos de Férias" + Tabela de Períodos
Aquisitivos (com colunas Aquisitivo, Concessivo, Prazo, Situação, Dobra, Abono,
Dias Abono, Gozo 1 (Período + Dobra), Gozo 2 ...) + campo opcional "Prazo das
Férias Proporcionais".

### Campos de cabeçalho
| Campo | DOM ID | Tipo |
|---|---|---|
| Importação CSV | `arquivo:file` (file) + `j_id96` (button "Confirmar") | | |
| Data Início Férias Coletivas | `formulario:inicioFeriasColetivasInputDate` | text DD/MM/YYYY |
| Botão "Regerar Férias" | `formulario:regerarFeriasColetivas` | button |
| **Prazo das Férias Proporcionais** | `formulario:prazoFeriasProporcionais` | text (3 dígitos, integer) |

### 💡 Tooltip do "?" do `prazoFeriasProporcionais` (capturado empiricamente)
Span `formulario:j_id210content`:
> "Preencha esse campo somente se deseja informar um valor de prazo de férias proporcionais. Se desejar utilizar o valor padrão, que depende do regime de trabalho e do número de faltas não justificadas, mantenha o campo em branco."

**Implicação para a prévia**: o campo `prazo_ferias_proporcionais` é
**OPCIONAL**. Default vem do PJE-Calc considerando jornada + faltas
não-justificadas. Só preencher se a sentença determinou prazo
diferente do legal (ex: convenção coletiva específica).

### Tabela de Períodos Aquisitivos
Cada linha tem campos editáveis:
- `Relativas` (texto exibido — derivado)
- `Aquisitivo / Concessivo` (datas — derivadas das datas do contrato)
- `Prazo*` (text editável — número de dias)
- `Situação` (select — Indenizadas / Gozadas / etc.)
- `Dobra` (checkbox)
- `Abono` (checkbox)
- `Dias Abono` (text — número)
- `Gozo 1: Período (de+a) + Dobra` (text de+a + checkbox)
- `Gozo 2: Período + Dobra` (idem)

⚠️ Os IDs específicos das linhas seguem padrão `formulario:listagem:N:*`
(precisa inspecionar via DOM em runtime — não capturei nesta sessão).

| Botão | DOM ID |
|---|---|
| Salvar | `formulario:salvar` (provável — não capturado neste DOM) |

---

## 5. FGTS (fgts.jsf)

**URL**: `/pjecalc/pages/calculo/fgts.jsf`

| Campo | DOM ID | Tipo | Valores |
|---|---|---|---|
| Tipo (Pagar/Depositar) | `formulario:tipoDeVerba` | radio | PAGAR / DEPOSITAR |
| Compor Principal | `formulario:comporPrincipal` | radio | SIM / NAO |
| Multa | `formulario:multa` | checkbox | |
| Tipo Valor da Multa | `formulario:tipoDoValorDaMulta` | radio | CALCULADA / INFORMADA |
| Multa FGTS (%) | `formulario:multaDoFgts` | radio | VINTE_POR_CENTO / QUARENTA_POR_CENTO |
| Incidência FGTS | `formulario:incidenciaDoFgts` | select | SOBRE_O_TOTAL_DEVIDO, SOBRE_DEPOSITADO_SACADO, SOBRE_DIFERENCA, SOBRE_TOTAL_DEVIDO_MAIS_SAQUE_E_OU_SALDO, SOBRE_TOTAL_DEVIDO_MENOS_SAQUE_E_OU_SALDO |
| Excluir Aviso da Multa | `formulario:excluirAvisoDaMulta` | checkbox | |
| Multa Art. 467 | `formulario:multaDoArtigo467` | checkbox | |
| Multa 10% (LC 110) | `formulario:multa10` | checkbox | |
| Contribuição Social | `formulario:contribuiçãoSocial` | checkbox | |
| Incidência Pensão Alimentícia | `formulario:incidenciaPensaoAlimenticia` | checkbox | |
| **Período de Recolhimento** Início | `formulario:periodoInicial` | text | |
| Período Final | `formulario:periodoFinal` | text | |
| Alíquota | `formulario:aliquota` | radio | DOIS_POR_CENTO / OITO_POR_CENTO |
| Deduzir do FGTS | `formulario:deduzirDoFGTS` | checkbox | |
| Competência (linha de recolhimento) | `formulario:competenciaInputDate` | text MM/YYYY |
| Valor (recolhimento) | `formulario:valor` | text | |
| Botão "Incluir" recolhimento | `formulario:cmdIncluir` | anchor | |
| Botão "Salvar" | `formulario:salvar` | button | |
| Botão "Ocorrências" → parametrizar-fgts.jsf | `formulario:ocorrencias` | button | |

### Sub-página: parametrizar-fgts.jsf

URL: `/pjecalc/pages/calculo/parametrizar-fgts.jsf`  
Acesso: clicar `formulario:ocorrencias` na página FGTS.

Tabela de ocorrências FGTS com cabeçalho de Alteração em Lote:
| Campo | DOM ID |
|---|---|
| Período Inicial / Final | `formulario:periodoInicialInputDate` / `formulario:periodoFinalInputDate` |
| Alíquota (lote) | `formulario:aliquota:N` (radio DOIS / OITO) |
| Data Inicial / Final do lote | `formulario:dataInicialInputDate` / `formulario:dataFinalInputDate` |
| Valor Base | `formulario:valorBase` |
| Valor Recolhido | `formulario:valorRecolhido` |
| Botão "Recuperar" | `formulario:recuperar` (button) |
| Selecionar Todos (cabeçalho) | `formulario:selecionarTodos` (checkbox) |
| Linha N — Base Histórico | `formulario:listagem:N:baseHistorico` |
| Linha N — Base Verba | `formulario:listagem:N:baseVerba` |
| Linha N — Depositado | `formulario:listagem:N:depositado` |
| Linha N — Selecionar | `formulario:listagem:N:selecionar` |
| Botão "Regerar" | `formulario:regerar` |
| Botão "Salvar" | `formulario:salvar` |
| Botão "Cancelar" | `formulario:cancelar` |

---

## 6-12. ⚠ Páginas com mapeamento parcial (verificação pendente)

Devido à fragilidade da sessão Seam durante esta auditoria (frequentes
"Erro Interno no Servidor" ao alternar páginas), as seguintes páginas
**não foram totalmente capturadas via Chrome MCP** nesta sessão.

Referência atual está no código `modules/playwright_pjecalc.py` que
contém os IDs usados na automação ativa (fonte secundária confiável,
mas pode ter omissões):

| Página | URL | Onde encontrar IDs no código atual |
|---|---|---|
| **Contribuição Social (INSS)** | `inss.jsf` | `_configurar_parametros_ocorrencias_cs` |
| **parametrizar-inss.jsf** | (sub-página) | mesmo método — `recuperarDevidos`, `copiarDevidos`, `salariosPago`, `salariosDevidos`, `aplicar` |
| **Imposto de Renda (IRPF)** | `irpf.jsf` | `fase_irpf` |
| **Honorários** | `honorario*.jsf` | `fase_honorarios` (3 tipos) |
| **Custas Judiciais** | `custa-judicial.jsf` | `fase_custas_judiciais` |
| **Correção, Juros e Multa** | `parametros-atualizacao.jsf` | `fase_parametros_atualizacao` |
| **Liquidação** | `liquidacao.jsf` | `_clicar_liquidar` (mapeado parcial — `formulario:liquidar`, `formulario:acumularIndices`, `formulario:dataDeLiquidacao`) |
| **Histórico Salarial — modo CALCULADO** | `historico-salarial.jsf` com tipoValor=CALCULADO | (modo INFORMADO mapeado em doc 05) |

### Recomendação para próxima sessão de auditoria

Reabrir cada página com sessão Seam fresca (re-login se necessário) e
capturar os IDs sistematicamente, focando em:

1. **INSS**: alíquota do segurado (radio + select dependendo da opção),
   alíquota empregador (atividade econômica vs período vs fixa)
2. **IRPF**: tipo de tributação (mensal/anual), faixas, deduções
3. **Honorários**: 3 tipos (sucumbenciais, advocatícios, periciais),
   beneficiário, percentual, base, valor
4. **Custas**: base de cálculo, percentual padrão, isenção JG, prazo
5. **Correção/Juros**: TR/IPCA/Selic, juros mora pré/pós, multa
6. **Liquidação**: campos no header, lista de Pendências (com IDs reais),
   botões Liquidar e Exportar (já mapeado em `_clicar_liquidar`)
7. **Histórico CALCULADO**: clicar tipoValor=CALCULADO e mapear os campos
   dinâmicos (botão "+", select de % e referência)

---

## ETAPA 2 — Páginas de Média Prioridade (NÃO mapeadas via Chrome MCP)

A sessão Seam do PJE-Calc institucional tornou-se instável durante a auditoria,
com "Erro Interno no Servidor" ao tentar URLs diretas como `inss.jsf`, `irpf.jsf`,
`salario-familia.jsf`. Isso ocorre porque o JSF/Seam exige fluxo de navegação
controlado (links do menu lateral) ao invés de URL direta.

As 5 páginas seguintes NÃO foram mapeadas via Chrome MCP nesta sessão:

| Página | URL provável | Para mapear na próxima sessão |
|---|---|---|
| Salário-família | `salario-familia.jsf` | Cálculo com filhos menores |
| Seguro-desemprego | `seguro-desemprego.jsf` | Pleitos de habilitação |
| Previdência Privada | `previdencia-privada.jsf` | Plano PGBL/VGBL |
| Pensão Alimentícia | `pensao-alimenticia.jsf` | Descontos por dependente alimentar |
| Multas e Indenizações | `multa-indenizacao.jsf` | Multas convencionais avulsas |

⚠️ **Nota arquitetural**: estas páginas são **opcionais** e raramente usadas
em cálculos típicos trabalhistas. A automação atual já trata dessas páginas
como "skip se sem dados extraídos da sentença" (vide log: "Salário-família:
sem dados ou apurar=False — ignorado.").

**Para a Fase 2 (schema da prévia)**, estas páginas podem ser modeladas
como objetos opcionais:
```json
{
  "salario_familia": null,        // ou {filhos: [...]} se aplicável
  "seguro_desemprego": null,      // ou {parcelas: [...]}
  "previdencia_privada": null,
  "pensao_alimenticia": null,
  "multas_indenizacoes_avulsas": []
}
```

Quando vazio/null, a automação mantém o comportamento atual de "skip".
