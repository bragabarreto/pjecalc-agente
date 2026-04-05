# Honorarios Advocaticios e Custas Processuais
> Fonte: documento_operacional_pjecalc_maquina.md | Skill: pjecalc-operacional

---

## 8. Apuracao de Honorarios Advocaticios

Esta secao descreve o procedimento para a configuracao e calculo dos honorarios advocaticios no PJe Calc, devendo a automacao seguir rigorosamente os parametros extraidos da sentenca (arquivo JSON).

### 8.1. Configuracao Inicial
1.  **Acesso:** No menu lateral do PJe Calc, clique na aba **Honorarios**.
2.  **Novo Registro:** Clique no botao **Novo** para gerar uma nova verba de honorarios.
3.  **Descricao:** Manter o padrao "Honorarios Advocaticios" ou conforme especificado em sentenca.
4.  **Tipo de Valor:** Selecionar a opcao **Calculado**.
    *   *Nota:* Somente utilizar "Informado" caso o juiz tenha determinado um valor fixo especifico, o que nao e a regra geral.

### 8.2. Definicao de Aliquotas e Devedores
O sistema deve preencher **rigorosamente** o percentual (aliquota) descrito na sentenca, que geralmente varia entre 5% e 20%.

*   **Sucumbencia Total:**
    *   **Devedor:** Definir como **Reclamado** (se a procedencia for total) ou **Reclamante** (se a improcedencia for total).
    *   **Aliquota:** Conforme determinado no titulo executivo.
*   **Sucumbencia Reciproca:**
    *   Devem ser gerados dois registros de honorarios distintos (um para o advogado do reclamante e outro para o do reclamado).
    *   **Base de Calculo:** Em casos de sucumbencia reciproca, a **base de calculo para ambas as partes deve ser a mesma**.
    *   Se a base de calculo for a condenacao, deve-se selecionar obrigatoriamente a opcao **Bruto** (Condenacao Bruta).

### 8.3. Base de Apuracao e Credores
1.  **Base de Apuracao:** Selecionar a opcao **Bruto devido ao reclamante**.
    *   *Evitar:* As opcoes de "Bruto devido ao reclamante + outros debitos do reclamado" a menos que expressamente determinado.
2.  **Credor:** Preencher os dados do advogado beneficiario.
3.  **Imposto de Renda:**
    *   A opcao **Apurar Imposto de Renda** deve ser marcada apenas se houver orientacao para retencao na fonte.
    *   Caso marcada, o preenchimento do **CPF/Documento Fiscal** torna-se obrigatorio para a liquidacao.

### 8.4. Justica Gratuita e Exigibilidade Suspensa (art. 791-A, §4o, CLT)

Quando a sentença defere justiça gratuita a qualquer das partes, a exigibilidade dos honorários advocatícios aos quais essa parte foi condenada fica **suspensa**.

**Extração:** O campo `justica_gratuita` deve ser extraído com:
- `justica_gratuita.reclamante`: true/false
- `justica_gratuita.reclamado`: true/false

**Automação:** Na Fase 1 (Dados do Processo > Parâmetros do Cálculo), ANTES de salvar, inserir no campo **Comentários** (`formulario:comentarios`):

> "Honorários advocatícios devidos [descrição da(s) parte(s) beneficiária(s)] com exigibilidade suspensa, ante a gratuidade judiciária deferida, nos termos do art. 791-A, parágrafo 4o, da CLT."

Exemplos:
- Reclamante com JG: "Honorários advocatícios devidos pelo(a) reclamante (FULANO DE TAL) com exigibilidade suspensa..."
- Ambas as partes: "Honorários advocatícios devidos pelo(a) reclamante (FULANO) e pelo(a) reclamado(a) (EMPRESA X) com exigibilidade suspensa..."

**Implementação:** O campo é preenchido automaticamente em `fase_dados_processo()` quando `justica_gratuita.reclamante` ou `justica_gratuita.reclamado` é true.

### 8.5. Finalizacao e Liquidacao
1.  Apos o preenchimento, clicar em **Salvar**.
2.  Prosseguir para a aba **Operacoes** e clicar em **Liquidar**.
3.  Verificar se nao ha erros impeditivos e clicar em **Imprimir** para conferir o valor gerado na planilha de liquidacao (Honorarios Liquidos).

---

## 19. Custas Processuais

1. ESCOLHER SEMPRE A BASE DE CALCULO **"BRUTO DEVIDO AO RECLAMANTE"**

---

## Regras para Automacao

### Fluxo de preenchimento de honorarios
```
1. Aba Honorarios → Novo
2. Tipo: Calculado (padrao) ou Informado (valor fixo)
3. Aliquota: conforme sentenca (5%-20%)
4. Devedor: Reclamado ou Reclamante
5. Base: Bruto devido ao reclamante
6. Credor: dados do advogado
7. IR: marcar apenas se houver determinacao + CPF obrigatorio
8. Salvar
9. Se justica gratuita → inserir texto no campo Comentarios dos Parametros
10. Liquidar e conferir Honorarios Liquidos no relatorio
```

### Sucumbencia reciproca — checklist
- [ ] Criar dois registros separados de honorarios
- [ ] Mesma base de calculo para ambos
- [ ] Base = Bruto (Condenacao Bruta)
- [ ] Aliquotas conforme sentenca para cada parte

### Custas — regra unica
- Base de calculo: sempre **Bruto devido ao reclamante**
