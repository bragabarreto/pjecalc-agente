# Fases 4-5: Pré-verificações e Automação Playwright

## Índice

1. [Pré-verificações (6 checks)](#1-pré-verificações-6-checks)
2. [Setup Playwright](#2-setup-playwright)
3. [As 9 fases de automação](#3-as-9-fases-de-automação)
4. [Padrões JSF obrigatórios](#4-padrões-jsf-obrigatórios)
5. [Retry e diagnóstico](#5-retry-e-diagnóstico)

---

## 1. Pré-verificações (6 checks)

Antes de iniciar qualquer automação, executar TODAS em sequência. Se qualquer uma falhar,
abortar com mensagem clara:

```python
async def pre_verificacoes(json_dados: dict) -> tuple[bool, str]:
    """
    Retorna (True, "") se OK, ou (False, "mensagem de erro") se falhou.
    """
    # Check 1: JSON válido?
    if not json_dados:
        return False, "Nenhum JSON de sentença fornecido"

    # Check 2: Salvamento automático
    # (em webapp: serializar formulário e persistir no banco)
    await salvar_json_banco(json_dados)

    # Check 3: Validação completa
    resultado = validar_json_sentenca(json_dados)
    if not resultado.valido:
        return False, f"Validação falhou: {'; '.join(resultado.erros)}"

    # Check 4: PJe-Calc disponível?
    if not await pjecalc_rodando():
        return False, "PJe-Calc não está respondendo em localhost:9257"

    # Check 5: CNJ válido?
    if not validar_cnj(json_dados["numero"], json_dados["digito"],
                       json_dados["ano"], json_dados["regiao"], json_dados["vara"]):
        # Aviso, não bloqueante — logar mas continuar
        pass

    # Check 6: Automação já em andamento?
    if automacao_em_andamento():
        return False, "Já existe uma automação em execução"

    return True, ""
```

## 2. Setup Playwright

```python
from playwright.async_api import async_playwright

async def criar_browser(headless: bool = True):
    """Cria browser Playwright para automação do PJe-Calc."""
    pw = await async_playwright().start()
    browser = await pw.chromium.launch(
        headless=headless,
        args=[
            "--no-sandbox",
            "--disable-setuid-sandbox",
            "--disable-dev-shm-usage",
        ]
    )
    context = await browser.new_context(
        viewport={"width": 1280, "height": 800},
        java_script_enabled=True,
    )
    # Timeout global generoso (JSF é lento)
    context.set_default_timeout(30000)
    page = await context.new_page()
    return pw, browser, page
```

## 3. As 9 fases de automação

Cada fase é executada em sequência estrita. Alterar a ordem causa erros de ViewState.

### Fase 1: Login / Navegação Inicial

```python
async def fase_1_login(page):
    """Navega para PJe-Calc e injeta monitor AJAX."""
    await page.goto("http://localhost:9257/pjecalc/pages/principal.jsf")
    await page.wait_for_load_state("networkidle")

    # Injetar monitor AJAX — OBRIGATÓRIO antes de qualquer interação
    await instalar_monitor_ajax(page)

    # Se tela de login, preencher credenciais (PJe-Calc Cidadão geralmente não tem)
    # Se já na tela principal, prosseguir
```

### Fase 2: Dados do Processo

```python
async def fase_2_dados_processo(page, dados: dict):
    """Menu Novo → preenche dados do processo."""
    # Clicar em "Novo" no menu
    await page.get_by_text("Novo").click()
    await aguardar_ajax(page)

    # Número do processo (campos separados no PJe-Calc)
    await preencher_campo(page, "[id$='numero']", dados["numero"])
    await preencher_campo(page, "[id$='digito']", dados["digito"])
    await preencher_campo(page, "[id$='ano']", dados["ano"])
    await preencher_campo(page, "[id$='regiao']", dados["regiao"])
    await preencher_campo(page, "[id$='vara']", dados["vara"])

    # Partes
    await preencher_campo(page, "[id$='reclamante']", dados["reclamante"])
    await preencher_campo(page, "[id$='reclamado']", dados["reclamado"])

    # Estado (dropdown — índice numérico)
    await selecionar_dropdown(page, "[id$='estado']", dados["estado"])

    # Município
    await preencher_campo(page, "[id$='municipio']", dados["municipio"])

    # Datas (usar press_sequentially, NUNCA fill)
    await preencher_data(page, "[id$='dataAdmissao']",
                         iso_para_br(dados["data_admissao"]))
    if dados.get("data_demissao"):
        await preencher_data(page, "[id$='dataDemissao']",
                             iso_para_br(dados["data_demissao"]))
    if dados.get("data_ajuizamento"):
        await preencher_data(page, "[id$='dataAjuizamento']",
                             iso_para_br(dados["data_ajuizamento"]))

    # Remuneração (formato BR: 2.163,00)
    await preencher_campo(page, "[id$='remuneracao']",
                          fmt_br(float(dados["remuneracao"])))
```

### Fase 3: Configurações

```python
async def fase_3_configuracoes(page, dados: dict):
    """Marca/desmarca checkboxes de configuração."""
    configs = {
        "aplicar prescricao": "[id$='prescricao']",
        "aviso indenizado": "[id$='avisoIndenizado']",
        "calcular multa do FGTS": "[id$='multaFgts']",
        "calcular_seguro_desemprego": "[id$='seguroDesemprego']",
        "ajustar ocorrencias fgts": "[id$='ajustarFgts']",
        "marcar ferias": "[id$='marcarFerias']",
    }
    for chave_json, seletor in configs.items():
        valor = dados.get(chave_json, "não")
        checkbox = page.locator(seletor)
        esta_marcado = await checkbox.is_checked()
        deve_marcar = valor == "sim"
        if esta_marcado != deve_marcar:
            await checkbox.click()
            await aguardar_ajax(page)
```

### Fase 4: Histórico Salarial

```python
async def fase_4_historico(page, dados: dict):
    """Preenche histórico salarial se habilitado."""
    if dados.get("cadastrar historico") != "sim":
        return

    historico = dados.get("remuneracao_mensal", [])
    if not historico:
        return

    # Navegar para aba Histórico Salarial
    await page.get_by_text("Histórico Salarial").click()
    await aguardar_ajax(page)

    for item in historico:
        await page.get_by_text("Adicionar").click()
        await aguardar_ajax(page)
        await preencher_data(page, "[id$='dataHistorico']",
                             iso_para_br(item["data"]))
        await preencher_campo(page, "[id$='valorHistorico']",
                              fmt_br(item["valor"]))
        await page.get_by_text("Confirmar").click()
        await aguardar_ajax(page)
```

### Fase 5: Verbas Rescisórias

```python
async def fase_5_verbas(page, dados: dict):
    """Marca checkboxes das verbas deferidas."""
    mapeamento_verbas = {
        "SALDO DE SALÁRIO": "[id$='saldoSalario']",
        "AVISO PRÉVIO": "[id$='avisoPrevio']",
        "FÉRIAS + 1/3": "[id$='ferias']",
        "13º SALÁRIO": "[id$='decimoTerceiro']",
        "MULTA DO ARTIGO 477 DA CLT": "[id$='multa477']",
    }
    for verba in dados.get("verbas", []):
        seletor = mapeamento_verbas.get(verba)
        if seletor:
            checkbox = page.locator(seletor)
            if not await checkbox.is_checked():
                await checkbox.click()
                await aguardar_ajax(page)
```

### Fase 6: Adicionais (Insalubridade/Periculosidade)

```python
async def fase_6_adicionais(page, dados: dict):
    """Preenche insalubridade e/ou periculosidade se aplicável."""
    insalubridade = dados.get("insalubridade", {})
    if insalubridade.get("calcular"):
        await page.locator("[id$='insalubridade']").click()
        await aguardar_ajax(page)
        # Preencher grau, base de cálculo, reflexos...

    periculosidade = dados.get("periculosidade", {})
    if periculosidade.get("calcular"):
        await page.locator("[id$='periculosidade']").click()
        await aguardar_ajax(page)
```

### Fase 7: Verbas Mensais + Jornada

```python
async def fase_7_verbas_mensais_jornada(page, dados: dict):
    """Preenche verbas mensais e jornada."""
    # Verbas mensais (gratificações, adicionais fixos)
    for verba in dados.get("verbas_mensais", []):
        await page.get_by_text("Adicionar Verba Mensal").click()
        await aguardar_ajax(page)
        # Preencher campos da verba...

    # Jornada (HE, adicional noturno, intrajornada)
    for jornada_item in dados.get("jornada", []):
        await page.get_by_text("Adicionar Jornada").click()
        await aguardar_ajax(page)
        # Preencher campos de jornada...
```

### Fase 8: Honorários + Danos + Contribuição Social

```python
async def fase_8_honorarios_danos_cs(page, dados: dict):
    """Preenche honorários, danos morais e contribuição social."""
    # Honorários (SEMPRE array, mesmo se apenas um)
    for hon in dados.get("honorarios", []):
        if not hon.get("calcular", True):
            continue
        await page.get_by_text("Adicionar Honorário").click()
        await aguardar_ajax(page)
        await selecionar_dropdown(page, "[id$='tipoHonorario']", hon["tipo"])
        await selecionar_dropdown(page, "[id$='tipoDevedor']", hon["tipo_devedor"])
        await preencher_campo(page, "[id$='aliquotaHonorario']",
                              str(hon["aliquota"]))
        await page.get_by_text("Confirmar").click()
        await aguardar_ajax(page)

    # Danos morais
    danos = dados.get("danos_morais", {})
    if danos.get("calcular"):
        await page.locator("[id$='danosMorais']").click()
        await aguardar_ajax(page)
        await preencher_campo(page, "[id$='valorDanosMorais']",
                              fmt_br(danos["valor"]))

    # Contribuição social
    cs = dados.get("contribuicao_social", {})
    if cs.get("calcular"):
        await page.locator("[id$='contribuicaoSocial']").click()
        await aguardar_ajax(page)
        await preencher_campo(page, "[id$='aliquotaEmpregador']",
                              str(cs.get("aliquota_empregador", 20)))
        await preencher_campo(page, "[id$='aliquotaSat']",
                              str(cs.get("aliquota_sat", 3)))
```

### Fase 9: Calcular + Exportar

```python
async def fase_9_calcular_exportar(page) -> str:
    """
    Executa cálculo e exporta .PJC.
    RETORNA: caminho do arquivo .PJC gerado pelo PJe-Calc.

    ATENÇÃO: O .PJC é gerado EXCLUSIVAMENTE pelo PJe-Calc.
    NUNCA gerar .PJC por fora (ZIP+XML). O PJe-Calc Institucional
    rejeita arquivos não gerados pelo PJe-Calc Cidadão.
    """
    # Clicar Calcular
    await page.get_by_text("Calcular").click()
    # Cálculo pode demorar — timeout generoso
    await page.wait_for_selector("[id$='resultadoCalculo']", timeout=120000)
    await aguardar_ajax(page)

    # Configurar handler de download ANTES de clicar Exportar
    async with page.expect_download() as download_info:
        await page.get_by_text("Exportar").click()
        await aguardar_ajax(page)

    download = await download_info.value
    caminho_pjc = f"/tmp/exports/{download.suggested_filename}"
    await download.save_as(caminho_pjc)

    return caminho_pjc
```

## 4. Padrões JSF obrigatórios

### Monitor AJAX

```python
async def instalar_monitor_ajax(page):
    """Injeta monitor AJAX global. Chamar UMA VEZ no início."""
    await page.evaluate("""
        if (!window._ajaxCompleted) {
            window._ajaxCompleted = true;
            jsf.ajax.addOnEvent(function(data) {
                if (data.status === "success") window._ajaxCompleted = true;
                if (data.status === "begin") window._ajaxCompleted = false;
            });
        }
    """)

async def aguardar_ajax(page, timeout=10000):
    """Aguarda conclusão do ciclo AJAX JSF."""
    await page.wait_for_function(
        "window._ajaxCompleted === true", timeout=timeout)
    await page.evaluate("window._ajaxCompleted = false")
```

### Campos de data

```python
async def preencher_data(page, seletor: str, valor_ddmmyyyy: str):
    """Preenche campo de data PrimeFaces. NUNCA usar fill()."""
    campo = page.locator(seletor)
    await campo.focus()
    await campo.press_sequentially(valor_ddmmyyyy, delay=50)
    await page.keyboard.press("Escape")  # fecha Calendar popup
    await campo.evaluate("el => el.blur()")
    await aguardar_ajax(page)
```

### Dropdowns PrimeFaces

```python
async def selecionar_dropdown(page, seletor: str, valor_texto: str):
    """Seleciona item em SelectOneMenu PrimeFaces. Não usar select_option()."""
    await page.locator(seletor).click()
    await page.wait_for_selector(".ui-selectonemenu-panel:visible", timeout=5000)
    await page.locator(f".ui-selectonemenu-item:text('{valor_texto}')").click()
    await aguardar_ajax(page)
```

### Campos texto comuns

```python
async def preencher_campo(page, seletor: str, valor: str):
    """Preenche campo texto e dispara postback JSF."""
    await page.fill(seletor, "")
    await page.fill(seletor, valor)
    await page.keyboard.press("Tab")
    await aguardar_ajax(page)
```

### Conversões

```python
def iso_para_br(data_iso: str) -> str:
    """Converte YYYY-MM-DD para DD/MM/YYYY."""
    partes = data_iso.split("-")
    return f"{partes[2]}/{partes[1]}/{partes[0]}"

def fmt_br(valor: float) -> str:
    """Converte float para formato BR. Ex: 1234.56 -> '1.234,56'"""
    return f"{valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
```

## 5. Retry e diagnóstico

```python
import functools, asyncio

def retry_fase(max_tentativas=3, backoff_base=2):
    """Decorator de retry por fase com diagnóstico."""
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(page, *args, **kwargs):
            for tentativa in range(1, max_tentativas + 1):
                try:
                    return await func(page, *args, **kwargs)
                except Exception as e:
                    erro_msg = str(e)

                    # Screenshot de diagnóstico
                    ts = int(asyncio.get_event_loop().time())
                    await page.screenshot(
                        path=f"screenshots/erro_{func.__name__}_{ts}.png")

                    # Chromium crash → reiniciar browser
                    if "Target closed" in erro_msg or "crashed" in erro_msg:
                        page = await reiniciar_browser_e_navegar(page)
                        await instalar_monitor_ajax(page)

                    # ViewExpired → reload página
                    elif "ViewExpired" in erro_msg:
                        await page.reload()
                        await page.wait_for_load_state("networkidle")
                        await instalar_monitor_ajax(page)

                    if tentativa < max_tentativas:
                        await asyncio.sleep(backoff_base * tentativa)
                    else:
                        raise

            return page
        return wrapper
    return decorator
```
