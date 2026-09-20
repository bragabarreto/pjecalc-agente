# MinutaIA — como a ferramenta funciona (varredura de 19/09/2026)

> Levantamento feito na conta do usuário (www.minutaia.com.br, produto do Jusbrasil; é o mesmo
> produto que o TJSP disponibiliza como "MinutaIA"). Serve de base para o prompt em
> `docs/prompt-minuta-ia-revisao-sentenca-liquidavel.md` e para qualquer integração futura
> entre a minuta de sentença e o Agente PJE-Calc.

## 1. Arquitetura da tela

Uma única **barra de instruções** ("Instruções ao MinutaIA para geração da minuta…") mais um
painel de **contexto** em abas. Tudo o que estiver selecionado nas abas entra na janela de
contexto (até **3 M tokens**; o contador aparece na barra).

| Aba | O que é | Detalhes observados |
|---|---|---|
| **Documentos** | Autos, petições, decisões, peças | PDF, DOCX, ODT, TXT, HTML; PNG/JPG com OCR; MP3/WAV/MP4/WebM (transcrição); ZIP (extraído). Entrada por arquivo, URL, texto colado, transcrição ou Biblioteca. Toggle "OCR automático". Anonimização local (tarja-1). Integração com PJe/eproc via extensão Conecta. |
| **Modelos** | Exemplos de estilo/estrutura | Três modos: **Flexível** (referência de estilo), **Rigoroso** (preserva a estrutura, adapta o conteúdo), **Molde** (altera só os trechos necessários; o resto fica intacto). Até 300 k tokens por modelo; docx recomendado. |
| **Referências** | Legislação, Jurisprudência, PNCP, NatJus, **Habilidades** | buscas que viram contexto. |
| **Biblioteca** | Acervo pessoal em pastas | guarda documentos, modelos, **prompts** e jurisprudência; itens selecionados carregam nas abas respectivas. O usuário tem 146 modelos e 17 prompts. |
| **Bibliotecários** | Agrupamentos ativáveis com um clique | Informações + **Base de Conhecimento** (documentos, modelos, jurisprudência, legislação, prompts da Biblioteca) + **Habilidades** (máx. 4, fixadas automaticamente no chat). Compartilháveis (ver/editar). Nenhum criado ainda. |
| **Histórico** | Conversas, minutas e projetos | 566 minutas na conta; agrupáveis em projetos. |

Atalhos na barra: **`/`** abre os prompts (padrão + personalizados), **`@`** carrega itens da
Biblioteca ou ativa um Bibliotecário, **`#`** fixa Habilidades.

## 2. Prompts personalizados (o mecanismo relevante para este projeto)

- `/` → lista "Prompts Predefinidos" (PADRÃO, fornecidos pela plataforma) e PERSONALIZADO
  (do usuário), com filtro por texto, categoria e favoritos. Botão **Personalizar** abre
  "Gerenciar Prompts".
- Campos de um prompt: **Nome**, **Categoria** (Sentenças, Análise, Outros, Recursos, Peças
  Processuais, Decisões, Despachos, Consultivo, Documentos, Audiências, Acórdãos…),
  **Descrição** (uma linha, aparece na lista) e **Conteúdo** (até **50.000 caracteres**).
- Ao selecionar, o conteúdo é **inserido na barra** como instrução; o usuário pode complementar
  antes de enviar. O botão **"Salvar como prompt personalizado"** guarda o texto atual da barra.
- **"Analisar prompt"** dá nota 0–10 com diagnóstico (contradições, omissões, necessidade de
  reescrita).
- Prompts já existentes do usuário, na mesma linha do que se pede aqui:
  - *Conferência de minuta de sentença* (Análise, 06/08/2026, 6 013 chars): completude
    pedido×apreciação, dados residuais de outro processo, fundamentação×dispositivo,
    **parâmetros de liquidação** (§4), ordem/estrutura, aritmética de honorários, citações;
    relatório com gravidade (pronta / ajustes pontuais / revisão substancial).
  - *Verificação final de completude* (Sentenças): pedidos e arguições apreciados.
  - *ANÁLISE INICIAL DO PROCESSO — MAPA DE JULGAMENTO* (Análise): pré-julgamento por
    capítulos com "parâmetros de liquidação" ao fim de cada capítulo procedente.

### Regras da casa que esses prompts fixam (e que o prompt de revisão deve respeitar)

> "A sentença NÃO apura valores — quem apura é o PJe-Calc. […] não devem constar da sentença
> valores apurados, NEM os avos de férias e de 13º salário. Aponte-os como defeito — geram
> conflito com o PJe-Calc. Exceção: valores que o próprio juízo arbitra (dano moral, multa
> diária, honorários periciais)."

> "Férias, pelo período aquisitivo e a espécie (integral, proporcional ou em dobro); 13º, pelo
> ano de referência; saldo de salário, pelo mês e número de dias; aviso prévio, proporcional ao
> tempo de serviço (30 dias + 3 por ano completo, limite de 90), com projeção do término."

> Modelo "Dispositivo — sentença líquida": custas de 2 % sobre o valor da condenação "nos termos
> da planilha anexa" — a planilha do PJE-Calc integra a sentença. O Agente PJE-Calc é, portanto,
> o passo entre a minuta e a assinatura; o prompt de revisão é o **portão** antes desse passo.

## 3. Perfis, modos e controles de execução

- **Perfil** (combobox na barra): cargo, instituição e **estilo de redação**; funciona como
  persona/system prompt. Existe "André — Sentenças Trabalhistas" (Juiz do Trabalho, TRT), que
  pede parágrafos curtos, capítulos em romanos, "parâmetros claros de liquidação" e fidelidade
  total aos modelos selecionados, sobretudo no dispositivo.
- **Chat × Minuta**: Chat responde em conversa (sem documento); Minuta gera um documento no
  editor, salvo no Histórico, com versões. Conversas em Chat viram contexto ao trocar para Minuta.
- Só em Minuta aparecem: **Instantâneo × Planejado** (execução), painel "Como a IA trabalha"
  com **Pensamento** (Rápido / Equilibrado / Profundo), **Verbosidade** (Curto / Longo) e
  **ferramentas durante a redação**: Referência rastreável (origem de cada informação), Prints
  do processo, Jurisprudência, Legislação, Pesquisa web, Habilidades, **Contadoria** (cálculos
  judiciais e financeiros). A documentação descreve ainda um *slider* de esforço 1–5
  (nível 5 ativa limpeza inteligente acima de 1,5 M tokens).
- **Editor da minuta**: chat lateral (Chat / Minuta / Auto) para ajustes, edição manual
  preservada, versões, **Exportar**, **Salvar como Modelo**, Visual Law, Painel de estilos,
  compartilhamento. Timbrado próprio via marcador `(minuta)`.
- **Processamento em Lote** (beta) e "Julgamento em lote" para séries de casos.

## 4. Habilidades (skills)

Catálogo com 2 023 habilidades oficiais (297 "Forma" = tipo de documento; 1 726 "Matéria" =
área do direito; 92 pastas), versionadas, com **gatilhos** (palavras que as ativam
automaticamente quando "Habilidades" está ligado). "Descobrir com IA" sugere habilidades a
partir da descrição do que se vai redigir. O usuário pode criar as suas ("NOVA"): título,
identificador, categoria Forma/Matéria, tipo de documento, descrição (240 chars), gatilhos,
conteúdo (editor ou modo avançado). Um Bibliotecário fixa até 4.

## 5. Consequências para o prompt de revisão de liquidabilidade

1. **Instalar como prompt personalizado** (categoria Análise, conteúdo < 50 k chars) — mesma
   mecânica dos prompts que o usuário já usa; invocação por `/Revisão`.
2. **Contexto mínimo**: a minuta na aba Documentos (ou a minuta ativa no editor). Com os autos
   também carregados, o revisor pode conferir os dados contra as peças, mas o foco é a minuta.
3. **Configuração recomendada**: modo Minuta (o relatório vira documento versionado),
   Pensamento Profundo, Verbosidade Longo, Referência rastreável ligada, Jurisprudência /
   Legislação / Pesquisa web desligadas (não é tarefa de pesquisa), Contadoria desligada (o
   relatório não deve apurar valores — regra da casa).
4. **Formato do relatório** alinhado ao prompt "Conferência de minuta": itens "conforme" quando
   ok, gravidade em três níveis, apontamentos ordenados do mais grave, sem elogios.
5. **Regra da casa incorporada**: exigir parâmetros (datas, períodos, ano de referência, espécie
   das férias, dias do saldo e do aviso, base, percentuais, reflexos, natureza), e apontar como
   defeito valores apurados e avos de 13º/férias no corpo da sentença.
6. Opcional: criar uma **Habilidade** própria ("Liquidabilidade PJE-Calc", gatilhos:
   liquidação, PJe-Calc, parâmetros de liquidação, sentença líquida) com o checklist resumido,
   para que o agente a aplique também durante a *elaboração* da sentença, não só na revisão; e um
   **Bibliotecário** "Sentença líquida" que agrupe o prompt, os modelos de dispositivo e essa
   habilidade.
