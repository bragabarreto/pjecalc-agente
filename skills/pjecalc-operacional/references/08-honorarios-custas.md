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

### 8.4. Parametros Especificos e Justica Gratuita
Caso o processamento dos dados da sentenca (via arquivo JSON) identifique que o **Reclamante e beneficiario da justica gratuita**, a automacao deve realizar o seguinte procedimento adicional:

1.  Navegar ate a aba **Dados do Calculo**.
2.  Acessar a sub-aba **Parametros do Calculo**.
3.  No campo **Comentarios**, inserir obrigatoriamente o texto:
    > *"SUSPENSA A EXIGIBILIDADE DA COBRANCA DOS HONORARIOS DEVIDOS PELA PARTE BENEFICIARIA DA GRATUIDADE JUDICIARIA, POR FORCA DO ART. 791-A, Par.4o DA CLT E ADI 5.766."*

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
