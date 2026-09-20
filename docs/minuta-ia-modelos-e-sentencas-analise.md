# MinutaIA — estudo dos modelos salvos e das sentenças recentes (19/09/2026)

> Complementa `docs/minuta-ia-funcionamento.md` (mecânica da ferramenta) e
> `docs/prompt-minuta-ia-revisao-sentenca-liquidavel.md` (prompt de revisão). Fonte: leitura
> direta, na conta do usuário, dos modelos da Biblioteca e de duas sentenças geradas no Histórico
> (0001279-84.2026.5.07.0003, de 18/09/2026, e 0001065-93.2026.5.07.0003, de 15/09/2026), além
> dos dois mapas de julgamento mais recentes.

## 1. Inventário da Biblioteca (146 modelos, 17 prompts)

| Pasta | Itens | Natureza |
|---|---|---|
| Elaboração de sentença sem modelo | 19 | **modelos estruturais** (Rigoroso): Relatório, Preliminares, Prejudiciais, Revelia, Confissão ficta, Forma de organizar os pedidos em capítulos, Orientações para o julgamento dos capítulos, Instruções para análise dos depoimentos, Julgamentos — verbas rescisórias / duração do trabalho / responsabilidade solidária ou subsidiária, Indenização por danos morais, Justiça gratuita, Honorários advocatícios, Dispositivo da sentença, **Dispositivo — sentença líquida**, limitação aos valores da inicial, Tema 1389 (2 versões) |
| modelos novos | 66 | modelos temáticos por capítulo, `.md`, todos de 12/08/2026 (multa 477 em 4 variantes, multa 467, 40% do FGTS, rescisão indireta, justa causa/abandono, vínculo em 4 variantes, periculosidade em 3, HE em 5 variantes, 12x36, intervalo, turnos, estabilidade CIPA, dano moral em 4 variantes, terceirização/tomador, grupo econômico, TRCT/quitação, prescrição do FGTS, **reflexos de parcelas deferidas na base das rescisórias**…) |
| Modelos para casos específicos | 36 (+3 Caixa) | decisões inteiras reutilizadas como Rigoroso/Molde (Uber, iFood, Petrobras, BB, Bradesco, Serpro, Cagece, Ematerce, bancário, gestante art. 500, consignação, acordo parcial, embargos de declaração…) e 2 jurisprudências |
| Elaboração de sentença de embargos à execução… | 10 | fase de execução |
| Precedentes | 2 | |

Prompts personalizados (17): pipeline em três tempos — *ANÁLISE INICIAL — MAPA DE JULGAMENTO* →
*Elaborar sentença* (DETALHADO / MODO AGÊNTICO / COM BASE EM MODELO / genérico / sem alucinação /
julgamento em lote) → *Conferência de minuta de sentença* + *Verificação final de completude*.
Perfil ativo: "André — Sentenças Trabalhistas".

## 2. Como a sentença é construída (estrutura observada)

1. **Mapa de julgamento** (prompt, ~1 700 palavras): seções Identificação/rito → Questões
   processuais (preliminares, de ofício, prejudiciais, requerimentos, protestos, penalidades) →
   Capítulos de mérito com cinco blocos (pedidos, teses, ônus, provas, decisão recomendada + *parâmetros
   de liquidação*) → Verificação final e quadro-resumo. Regra da casa já embutida: "a sentença não apura
   valores… Não fixe valores nem os avos de férias e 13º".
2. **Sistema de elaboração de sentenças** (prompt DETALHADO): Relatório → Preliminares → Prejudiciais →
   Mérito em capítulos (romanos; prosa contínua sem subtítulos; IDs de 7 dígitos; jurisprudência só a
   selecionada) → Justiça gratuita (sempre após o mérito) → Honorários (sempre após a JG; sucumbência
   por **capítulo**, não por pedido) → Dispositivo (modelo "Dispositivo da sentença" ou
   "Dispositivo — sentença líquida", este com custas de 2 % "nos termos da planilha anexa").
3. **Modelos Rigorosos por seção**, todos com texto-base entre colchetes e checklists. Os que mais
   importam para a liquidação:
   - *Julgamentos — verbas rescisórias*: tabela modalidade × verbas; regras das multas 467/477 com
     modelos de procedência/improcedência; item 6 manda inserir no parágrafo final "admissão, tipo de
     terminação, data da dispensa, data de terminação (se diversa) e remuneração para cálculo";
     parâmetros por verba (saldo 1/30 por dia; aviso 30 + 3/ano ≤ 90; férias por PA e espécie; 13º por
     ano; projeção do aviso — "a sentença deve apenas fixar a data de terminação"; "não precisa apurar
     os avos").
   - *Orientações para o julgamento dos capítulos*: bloco C "Parâmetros de liquidação" (base, período,
     critério, reflexos, deduções) com as mesmas regras de nomeação (13º pelo ano; férias pelo PA;
     saldo "março de 2024 (23 dias)"; salário retido + mês; aviso proporcional); modelo de frase para
     reflexos de HE (Tema 9 do TST). ⚠️ Contém contradição interna: pede "sem apurar valores" e, nas
     vedações/observações finais, "NÃO deixar de apurar os valores individualizados" e "busque sempre
     apurar o valor da condenação de cada parcela" (resíduo de versão anterior à regra da casa).
   - *Julgamentos — duração do trabalho*: modelos por situação (bancário 224 §2º, art. 62 I, empresa
     >20 sem controle, intervalo pré/pós-reforma, intervalo térmico, RSR em dobro, RSR após o 7º dia).
     Fecha com "condena-se… além da 8ª diária e 44ª semanal" mas **não tem bloco de parâmetros**
     (divisor, base, adicional, quantidade, reflexos, deduções).
   - *Honorários advocatícios*: 15 %; proporção por capítulos; 0 % ⇒ sucumbência TOTAL, nunca
     recíproca; base única na recíproca; jus postulandi (item 5); ADI 5.766 = condição suspensiva.
     ⚠️ Contradição interna: item 1 diz "base de cálculo ÚNICA na recíproca" e o complemento final diz
     "BASES DISTINTAS — pela ré sobre a condenação; pela autora sobre o pedido improcedente. Não
     unificar a base".
   - *Dispositivo — sentença líquida* (2 473 palavras): planilha PJe-Calc "parte integrante e
     indissociável"; tabela de natureza das parcelas para conferência no PJe-Calc; periciais
     R$ 1.000–2.000 (R$ 1.000 se JG → União); ADC 58 + Lei 14.905/2024 (IPCA-E + juros da Lei 8.177 na
     fase pré-judicial; IPCA + SELIC − IPCA na judicial); Fazenda Pública (EC 113); dano moral pela
     ADC 58 (superação da Súmula 439, E-RR 329600-62). Coerente com o que o agente aplica.
   - *Justiça gratuita*: Tema 21 do TST; sindicato (Súmula 463 II; microssistema LACP/CDC); ID da
     declaração obrigatório; repercussão nos honorários.

## 3. O que as sentenças geradas mostram (aderência à regra da casa e ao agente)

### 3.1 0001279-84 (dispensa imotivada revertida de justa causa; HE por 2 meses)

Pontos bons: parágrafo "Parâmetros de apuração" no capítulo das rescisórias (admissão, dispensa,
término projetado, remuneração-base); HE com período fechado, adicional, divisor 220, base, rol de
reflexos e dedução das 2 HE pagas; natureza das parcelas listada; correção/juros no padrão.

Desvios de liquidabilidade:
- **Avos no dispositivo** — "13º proporcional de 2026 (4/12 avos)", "férias proporcionais… (4/12
  avos)": viola a regra da casa e os modelos; o PJe-Calc conta a partir das datas.
- **Período aquisitivo errado** — admissão em 09/01/2026 gera PA **2026/2027**, não "2025/2026".
  É o tipo de erro que a nomeação por avos esconde e que a nomeação por datas evitaria.
- **Valores apurados** — "salário retido… no valor de R$ 1.772,00", "base de cálculo de
  R$ 1.772,00", "multa… (R$ 1.772,00)". Para o agente basta "último salário / salário-base dos
  contracheques"; o valor fixo impede a evolução salarial e é apuração no corpo da decisão.
- **FGTS "do pacto"** — condena "depósitos de FGTS do pacto e rescisório" sem dizer se os depósitos
  de jan–mar/2026 foram feitos, sobre quais competências e salários. Para o PJe-Calc, FGTS sobre
  salário já pago não deriva de verba condenada: exige competências + base, ou o extrato da conta.
- **Custas arbitradas** (R$ 500 sobre R$ 25.000) — a minuta usou o dispositivo *não* líquido; se a
  sentença vai ao agente antes da assinatura, o modelo a usar é o líquido.

### 3.2 0001065-93 (rescisão indireta, limbo, tempo à disposição, intervalo, dano moral)

Este é o caso que o agente já liquidou (regra #80-DR no `CLAUDE.md`): a sentença fixa a base das HE
como "salário-base + adicional noturno (Súmula 264)" e é silente sobre a Súmula 340 — o normalizer
dividia a verba indevidamente; corrigido no agente. A minuta traz **bloco "PARÂMETROS DE
LIQUIDAÇÃO" ao fim de cada capítulo condenatório**, com datas, remuneração-base, aviso, divisor,
adicional, base, reflexos, deduções e critério de apuração pelos cartões (com IDs). É o melhor
padrão observado e deve virar regra.

Desvios:
- **Avos** — "13º proporcional de 2026 (7/12)", "férias proporcionais PA 2025/2026 (12/12)".
- **Saldo × salário retido × aviso** — "saldo de salário de junho/2026 (30 dias)" com rescisão em
  09/06/2026 e aviso indenizado de 36 dias projetado a 15/07/2026. Para o agente, saldo é do 1º dia
  do mês da dispensa até a dispensa (9 dias); os dias 10–30/06 já estão no aviso. Ou a verba é
  "salário retido de junho/2026" com justificativa (à disposição), ou há dupla contagem. A minuta
  precisa decidir e nomear.
- **Quantidade não mensalizável** — "15 minutos por plantão efetivamente trabalhado" e "30 minutos
  por plantão" remetem aos cartões de ponto (ID 6c953ee) para contar plantões. O PJe-Calc apura
  mês a mês: ou a sentença fixa a quantidade mensal (ex.: 15 plantões/mês na 12x36 ⇒ 3h45 de HE
  e 7h30 de intervalo por mês), ou os cartões vão anexados ao agente como documento, com a regra
  para meses sem cartão.
- **Divisor 220 em escala 12x36** — verificar; a jurisprudência aplica 220 (Súmula 444 / OJ) mas o
  PJe-Calc precisa do valor expresso, e a carga mensal da escala é 180h (afeta o cartão de ponto
  se a apuração for pelo cartão).
- **40 % "sobre a totalidade dos depósitos (recolhidos e decorrentes da condenação)"** — a parcela
  sobre os recolhidos exige o **extrato do FGTS** anexado ao agente.
- **Honorários** — texto de sucumbência *recíproca* com "100 % para a reclamante e 0 % para a
  reclamada": o modelo manda usar sucumbência TOTAL quando uma parte tem 0 %. Além disso, a própria
  ementa citada (TRT-7, Tese Vinculante 242) reconhece sucumbência recíproca parcial quando há
  pedidos autônomos improcedentes — aqui férias 2024/2025 e multa 467. Ponto jurídico a decidir;
  para o agente, o que importa é que devedor, credor e base fiquem inequívocos.
- **Dedução "OJ 415 / Tema 252"** — exige contracheques anexados; sem eles, o agente não deduz.

### 3.3 Padrão recorrente

Os desvios se repetem nas duas sentenças e coincidem com os itens do §4 do prompt "Conferência de
minuta" ("valores apurados e avos… geram conflito com o PJe-Calc"). A regra existe nos modelos de
*fundamentação* (verbas rescisórias, orientações) mas **não nos modelos de dispositivo**, que são
os que a IA usa no modo Rigoroso na hora de listar as obrigações — e é no dispositivo que os avos
reaparecem.

## 4. Melhorias recomendadas

### 4.1 Nos modelos existentes (edições cirúrgicas)

1. **Dispositivo da sentença** e **Dispositivo — sentença líquida** — acrescentar ao "Checklist
   final obrigatório":
   > 7. Nenhuma obrigação do dispositivo traz valor apurado nem avos. 13º pelo ano de referência
   > e espécie; férias pelo período aquisitivo (datas) e espécie; saldo de salário pelo mês e dias;
   > salário retido pelo mês; aviso pelo nº de dias e data projetada; HE pela quantidade mensal
   > (ou pelo cartão anexo), adicional, divisor e base nominada (não em R$). Só constam valores que
   > o juízo arbitra (dano moral, multa diária, periciais).
2. **Orientações para o julgamento dos capítulos** — remover as duas frases que mandam "apurar os
   valores individualizados" (vedações e observação final), que contradizem o bloco C e a regra da
   casa; substituir por "fixar os parâmetros individualizados por parcela; a apuração é do PJe-Calc".
3. **Honorários advocatícios** — resolver a contradição "base única" × "bases distintas" (escolher
   uma e apagar a outra) e reforçar, no critério de decisão final, a verificação "alguma parte com
   0 % ⇒ modelo 3 ou 4, nunca o texto de recíproca". Decidir expressamente, no modelo, se a
   improcedência de pedido autônomo dentro de capítulo vencido configura sucumbência recíproca
   (Tese 242 do TST), pois hoje o modelo por capítulos e a ementa citada apontam em sentidos opostos.
4. **Julgamentos — verbas rescisórias** — no item 6 (parágrafo final de parâmetros), acrescentar:
   distinção saldo × salário retido; se aviso indenizado, "o saldo vai até a data da dispensa e os
   dias seguintes integram o aviso"; FGTS: destino (alvará/depósito), base (verbas da condenação
   e/ou competências do pacto), depósitos existentes a deduzir "conforme extrato ID …"; seguro-
   -desemprego só entra na liquidação se convertido em indenização.
5. **Julgamentos — duração do trabalho** — criar bloco final "PARÂMETROS DE LIQUIDAÇÃO" igual ao
   das rescisórias: jornada fixada dia a dia (entrada/saída/intervalo) ou quantidade **mensal**;
   escala e datas de alteração; carga horária/divisor; adicional; composição da base (Súmula 264:
   quais parcelas); reflexos (fórmula do Tema 9); dedução com referência aos contracheques; Súmula
   340 **somente** se a remuneração for variável e a sentença a determinar; intervalo: minutos ×
   plantões/mês, natureza, sem reflexos pós-reforma.
6. **Perfil "André — Sentenças Trabalhistas"** — acrescentar uma frase ao estilo de redação:
   "Parâmetros de liquidação sempre por datas, períodos, bases nominadas, percentuais e reflexos;
   nunca valores apurados nem avos; a planilha do PJe-Calc integra a sentença."
7. **Mapa de julgamento** — já está correto; apenas exigir, nos parâmetros, a quantidade mensal de
   HE/intervalo quando fixada por dia ou plantão, e a lista de documentos que a liquidação vai
   precisar (cartões, contracheques, extrato do FGTS, TRCT).

### 4.2 Novos itens

- **Modelo "Quadro de parâmetros de liquidação"** (Rigoroso), anexo ao fim do dispositivo — o Anexo B
  do prompt de revisão, uma linha por parcela: período · base · divisor · adicional/multiplicador ·
  quantidade (mensal ou "cartão anexo") · reflexos · natureza · deduções (documento) · observações.
  Torna a extração do agente determinística e substitui os "avos" por datas.
- **Prompt "Revisão de liquidabilidade — PJE-Calc"** (já escrito), a rodar entre a Conferência e a
  assinatura; a Conferência pega completude/dados residuais/coerência, o novo prompt pega o que o
  PJe-Calc precisa.
- **Habilidade própria** "Liquidabilidade PJE-Calc" com o checklist resumido e gatilhos
  (liquidação, PJe-Calc, parâmetros, sentença líquida) para agir também na elaboração; e um
  **Bibliotecário** "Sentença líquida" agrupando: os dois dispositivos, o quadro de parâmetros, os
  modelos de rescisórias e duração, o prompt de revisão e a habilidade.

### 4.3 Fluxo sugerido

Mapa de julgamento → Elaborar sentença (Rigoroso) → Conferência de minuta → **Revisão de
liquidabilidade** (corrigir a minuta) → Agente PJE-Calc (minuta + documentos apontados) → planilha →
trocar o dispositivo pelo "Dispositivo — sentença líquida" → assinatura.

## 5. Registro de aplicação (19/09/2026)

Edições aplicadas diretamente na conta MinutaIA, via editor de conteúdo dos modelos
(Markdown) e gerenciador de prompts/perfis:

| Item | Onde | O que mudou | Verificação |
|---|---|---|---|
| Checklist item 7 "Parâmetros, não resultados" | Dispositivo da sentença | apêndice ao checklist final | 3.348 → 3.496 palavras |
| Idem (+ menção à planilha) | Dispositivo — sentença líquida | apêndice ao checklist final | 2.473 → 2.634 palavras |
| Remoção da contradição "apurar valores" | Orientações para o julgamento dos capítulos | duas frases substituídas por "fixar parâmetros; apuração é do PJe-Calc" | 1.702 → 1.752 palavras |
| Seção 7-A "Dados que a liquidação exige" | Julgamentos — verbas rescisórias | inserida antes da seção 8 | 3.702 → 4.029 palavras |
| Bloco "Parâmetros de liquidação" obrigatório | Julgamentos — duração do trabalho | apêndice | 3.833 → 4.204 palavras |
| Alerta 100 % × 0 % ⇒ sucumbência total | Honorários advocatícios | inserido no critério de decisão final | 3.063 → 3.165 palavras |
| Regra de liquidação no estilo e nas restrições | Perfil "André — Sentenças Trabalhistas" | textareas 1.171 → 1.656 e 435 → 595 chars | salvo |
| Quantidade mensal + lista de documentos | Prompt "ANÁLISE INICIAL — MAPA DE JULGAMENTO" | frase dos parâmetros ampliada | 9.413 chars |
| Novo prompt "Revisão de liquidabilidade - PJE-Calc" | Gerenciar Prompts, categoria Análise | conteúdo integral do prompt (31.429 chars) | 18 prompts |
| Novo modelo "Quadro de parâmetros de liquidação (anexo ao dispositivo)" | Biblioteca, Rigoroso | instruções + quadro de 16 itens | 147 modelos |

| Base única na recíproca (decisão do usuário, 20/09/2026) | Honorários advocatícios | parágrafo "BASES DISTINTAS" substituído por "BASE ÚNICA — … mesma base (valor da condenação principal), variando só os percentuais; só na sucumbência total do autor a base é o valor da causa" | 3.165 → 3.198 palavras |

**Ainda em aberto (decisão jurídica do usuário):** a posição sobre sucumbência recíproca
parcial (Tese 242 do TST) quando há pedido autônomo improcedente dentro de capítulo vencido.
