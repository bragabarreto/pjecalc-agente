# modules/playwright_script_builder.py
# Gerador de script Playwright standalone para automação do PJE-Calc Cidadão.
# O script gerado é um arquivo .py independente que o usuário executa localmente
# ou que é lançado automaticamente pelo launcher .bat (duplo-clique).

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from config import OUTPUT_DIR

# ── Template do script gerado ─────────────────────────────────────────────────
# NOTAS:
#  - Template usa r'''...''' (aspas simples triplas).
#  - JSON é embutido entre """...""" (aspas DUPLAS triplas) para não conflitar.
#  - Marcadores: $$$DADOS_JSON$$$  $$$VERBAS_JSON$$$  $$$NUMERO$$$
#                $$$DATA$$$  $$$SESSAO_ID$$$  $$$NOME_ARQUIVO$$$

_TEMPLATE = r'''#!/usr/bin/env python3
"""
Script de Automação PJE-Calc Cidadão
Gerado em: $$$DATA$$$
Processo:  $$$NUMERO$$$
Sessão:    $$$SESSAO_ID$$$

Execução: este script é iniciado pelo launcher .bat (duplo-clique).
Também pode ser executado diretamente: python $$$NOME_ARQUIVO$$$

O script:
  1. Verifica se o PJE-Calc Cidadão está rodando (localhost:9257)
  2. Inicia o PJE-Calc Cidadão automaticamente se necessário
  3. Abre o browser e navega para o formulário
  4. Preenche todos os campos automaticamente
  5. Em caso de campo não encontrado, pausa e aguarda ação manual
"""

import json
import re
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

# ── DADOS DO CÁLCULO ─────────────────────────────────────────────────────────
DADOS = json.loads("""$$$DADOS_JSON$$$""")
VERBAS_MAPEADAS = json.loads("""$$$VERBAS_JSON$$$""")

# ── CONFIGURAÇÃO ──────────────────────────────────────────────────────────────
PJECALC_BASE    = "http://localhost:9257/pjecalc"
PJECALC_INICIO  = r"C:\Program Files\pjecalc-windows64-2.14.0\iniciarPjeCalc.bat"
HEADLESS        = False
SLOW_MO         = 120       # ms — aumentar se o sistema for lento
T_SEL           = 6000      # ms para localizar elemento
T_NAV           = 12000     # ms para carregar página

# ── UTILITÁRIOS ───────────────────────────────────────────────────────────────

def _fmt_br(valor) -> str:
    """Converte float para formato BR: 1234.56 → '1.234,56'"""
    s = f"{float(valor):,.2f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


def _log(msg: str):
    print(msg, flush=True)


def _pausar(msg: str = "") -> None:
    if msg:
        print(f"\n  ⚠  {msg}", flush=True)
    input("     → Preencha manualmente e pressione Enter para continuar  "
          "(ou 'q'+Enter para sair): ").strip().lower()


def _parse_numero(numero: str) -> dict:
    """Extrai partes do número CNJ: 0000027-46.2026.5.07.0003"""
    m = re.match(r"(\d{7})-(\d{2})\.(\d{4})\.(\d)\.(\d{2})\.(\d{4})", numero or "")
    if m:
        return {"numero": m.group(1), "digito": m.group(2), "ano": m.group(3),
                "justica": m.group(4), "regiao": m.group(5), "vara": m.group(6)}
    # Fallback: tentar extrair apenas os dígitos na ordem
    digitos = re.sub(r"[^0-9]", "", numero or "")
    if len(digitos) >= 20:
        return {"numero": digitos[:7], "digito": digitos[7:9], "ano": digitos[9:13],
                "justica": digitos[13:14], "regiao": digitos[14:16], "vara": digitos[16:20]}
    return {}


# ── INICIALIZAÇÃO DO PJE-CALC LOCAL ──────────────────────────────────────────

def _pjecalc_rodando() -> bool:
    """Verifica se o PJE-Calc Cidadão está acessível em localhost:9257."""
    try:
        urllib.request.urlopen(PJECALC_BASE + "/pages/principal.jsf", timeout=3)
        return True
    except Exception:
        return False


def _iniciar_pjecalc() -> bool:
    """Localiza e executa o PJE-Calc Cidadão."""
    candidatos = [
        PJECALC_INICIO,
        str(Path.home() / "AppData/Local/pjecalc/iniciarPjeCalc.bat"),
        str(Path("C:/Program Files (x86)/pjecalc-windows64-2.14.0/iniciarPjeCalc.bat")),
        "iniciarPjeCalc.bat",
    ]
    bat = next((p for p in candidatos if Path(p).exists()), None)
    if not bat:
        _log("  ⚠  Arquivo iniciarPjeCalc.bat não encontrado.")
        _log("     Inicie o PJE-Calc Cidadão manualmente e aguarde.")
        input("     → Pressione Enter quando o PJE-Calc estiver aberto: ")
        return _pjecalc_rodando()

    _log(f"\n  Iniciando PJE-Calc Cidadão: {bat}")
    subprocess.Popen([bat], shell=True,
                     creationflags=subprocess.CREATE_NEW_CONSOLE if sys.platform == "win32" else 0)
    _log("  Aguardando servidor iniciar", end="")
    for _ in range(90):
        time.sleep(1)
        print(".", end="", flush=True)
        if _pjecalc_rodando():
            _log(" OK\n")
            return True
    _log("\n  ⚠  PJE-Calc não respondeu em 90s. Verifique manualmente.")
    return False


def _garantir_pjecalc():
    """Garante que o PJE-Calc local está rodando antes de começar."""
    if _pjecalc_rodando():
        _log("  ✓  PJE-Calc Cidadão já está em execução.")
        return
    _log("\n  PJE-Calc Cidadão não está rodando. Iniciando automaticamente...")
    if not _iniciar_pjecalc():
        _log("  ⚠  PJE-Calc não iniciou. Tente iniciar manualmente.")


# ── PRIMITIVAS JSF / RICHFACES ────────────────────────────────────────────────

def _fill(page, field_id: str, value, descricao: str, obrigatorio: bool = True) -> bool:
    """Preenche campo de texto JSF.
    Tenta:  #formulario\\:ID_input  (RichFaces calendar)
            [id='formulario:ID']
            input[id$='ID']
    """
    if value is None or str(value).strip() == "":
        if not obrigatorio:
            _log(f"    ○  {descricao}: vazio (opcional)")
        return False
    value = str(value).strip()
    sels = [
        f"#formulario\\:{field_id}_input",
        f"[id='formulario:{field_id}']",
        f"input[id$=':{field_id}']",
        f"input[id$='{field_id}']",
    ]
    for sel in sels:
        try:
            el = page.wait_for_selector(sel, timeout=T_SEL)
            if el and el.is_visible():
                el.click(); time.sleep(0.12)
                el.fill(""); el.fill(value)
                _log(f"    ✓  {descricao}: {value}")
                return True
        except Exception:
            continue
    if obrigatorio:
        _pausar(f"{descricao} ({value!r}) — campo não encontrado")
    else:
        _log(f"    ○  {descricao}: campo não encontrado (opcional)")
    return False


def _select(page, field_id: str, value, descricao: str, obrigatorio: bool = False) -> bool:
    """Seleciona opção em <select> JSF."""
    if not value:
        return False
    value = str(value).strip()
    sels = [
        f"[id='formulario:{field_id}']",
        f"select[id$=':{field_id}']",
        f"select[id$='{field_id}']",
    ]
    for sel in sels:
        for metodo in ("label", "value"):
            try:
                page.select_option(sel, **{metodo: value}, timeout=2000)
                _log(f"    ✓  {descricao}: {value}")
                return True
            except Exception:
                continue
    if obrigatorio:
        _pausar(f"{descricao} ({value!r}) — seleção não encontrada")
    else:
        _log(f"    ○  {descricao}: opção não encontrada (opcional)")
    return False


def _radio(page, field_id: str, value, descricao: str) -> bool:
    """Seleciona radio button JSF pelo valor do option."""
    try:
        page.click(
            f"[id='formulario:{field_id}'] input[value='{value}']",
            timeout=T_SEL)
        _log(f"    ✓  {descricao}: {value}")
        return True
    except Exception:
        try:
            page.click(
                f"table[id='formulario:{field_id}'] input[value='{value}']",
                timeout=2000)
            _log(f"    ✓  {descricao}: {value}")
            return True
        except Exception:
            _log(f"    ○  {descricao}: radio não encontrado (opcional)")
            return False


def _checkbox(page, field_id: str, marcar: bool, descricao: str,
              obrigatorio: bool = False) -> bool:
    """Marca/desmarca checkbox JSF."""
    sels = [
        f"[id='formulario:{field_id}']",
        f"input[id$=':{field_id}']",
        f"input[id$='{field_id}']",
    ]
    for sel in sels:
        try:
            checked = page.is_checked(sel, timeout=T_SEL)
            if checked != marcar:
                page.click(sel)
            _log(f"    ✓  {descricao}: {'marcado' if marcar else 'desmarcado'}")
            return True
        except Exception:
            continue
    if obrigatorio:
        _pausar(f"Checkbox '{descricao}' não encontrado")
    return False


def _clicar_menu(page, texto: str) -> bool:
    """Clica em link do menu lateral pelo texto exato."""
    sels = [
        f"a[class*='menu']:has-text('{texto}')",
        f"#menuesq a:has-text('{texto}')",
        f"a:has-text('{texto}')",
        f"span:has-text('{texto}')",
    ]
    for sel in sels:
        try:
            page.click(sel, timeout=T_SEL)
            page.wait_for_load_state("networkidle", timeout=T_NAV)
            time.sleep(0.5)
            _log(f"    ✓  Menu: {texto}")
            return True
        except Exception:
            continue
    return False


def _clicar_aba(page, aba_id: str) -> bool:
    """Clica em aba RichFaces (switchType=client) pelo ID."""
    try:
        page.click(f"[id='formulario:{aba_id}_lbl']", timeout=T_SEL)
        time.sleep(0.4)
        return True
    except Exception:
        # Tentar pelo label visível
        try:
            page.click(f"#{aba_id}_lbl", timeout=2000)
            time.sleep(0.4)
            return True
        except Exception:
            return False


def _salvar(page) -> bool:
    """Clica no botão Salvar do formulário."""
    sels = [
        "[id='formulario:salvar']",
        "input[value='Salvar']",
        "button:has-text('Salvar')",
        "a:has-text('Salvar')",
    ]
    for sel in sels:
        try:
            page.click(sel, timeout=T_SEL)
            page.wait_for_load_state("networkidle", timeout=T_NAV)
            time.sleep(0.5)
            _log("    ✓  Salvo")
            return True
        except Exception:
            continue
    _log("    ⚠  Botão Salvar não encontrado")
    return False


def _novo(page) -> bool:
    """Clica em 'Novo' para criar novo registro."""
    sels = [
        "[id='formulario:novo']",
        "input[value='Novo']",
        "button:has-text('Novo')",
        ".sprite-novo",
    ]
    for sel in sels:
        try:
            page.click(sel, timeout=3000)
            page.wait_for_load_state("networkidle", timeout=T_NAV)
            time.sleep(0.5)
            return True
        except Exception:
            continue
    return False


# ── FASE 1 — CRIAR NOVO CÁLCULO ───────────────────────────────────────────────

def fase_01_novo_calculo(page) -> bool:
    _log("\n[FASE 1] Criando Novo Cálculo...")

    # Navegar via menu lateral "Novo" (primeira liquidação de sentença).
    # NÃO usar "Cálculo Externo" — só serve para atualizar cálculos existentes.
    # NÃO navegar por URL direta — ViewState do JSF seria inválido.
    if not _clicar_menu(page, "Novo"):
        _pausar("Clique no menu lateral 'Novo' e pressione Enter")
    page.wait_for_load_state("networkidle", timeout=T_NAV)
    time.sleep(1.0)

    time.sleep(0.8)

    proc = DADOS.get("processo", {})
    partes = _parse_numero(proc.get("numero", ""))

    # ── Aba: Dados do Processo ────────────────────────────────────────────────
    _clicar_aba(page, "tabDadosProcesso")
    time.sleep(0.3)

    # Selecionar "Informar processo manualmente"
    try:
        # Radio: primeiro option = buscar no PJE; segundo = informar manualmente
        radios = page.locator("[id='formulario:processoInformadoManualmente'] input").all()
        if len(radios) >= 2:
            radios[1].click()      # index 1 = manual
            time.sleep(0.6)
    except Exception:
        pass

    # Número do processo (campos separados)
    _fill(page, "numero",  partes.get("numero"),  "Nº (7 dígitos)")
    _fill(page, "digito",  partes.get("digito"),  "Dígito (2)")
    _fill(page, "ano",     partes.get("ano"),     "Ano (4)")
    _fill(page, "regiao",  partes.get("regiao"),  "Tribunal (2)")
    _fill(page, "vara",    partes.get("vara"),    "Vara (4)")

    # Reclamante
    _fill(page, "reclamanteNome", proc.get("reclamante"), "Reclamante")
    if proc.get("cpf_reclamante"):
        _radio(page, "documentoFiscalReclamante", "CPF", "Tipo doc reclamante")
        _fill(page, "reclamanteNumeroDocumentoFiscal",
              proc.get("cpf_reclamante"), "CPF Reclamante", obrigatorio=False)

    # Reclamado
    _fill(page, "reclamadoNome", proc.get("reclamado"), "Reclamado")
    if proc.get("cnpj_reclamado"):
        _radio(page, "tipoDocumentoFiscalReclamado", "CNPJ", "Tipo doc reclamado")
        _fill(page, "reclamadoNumeroDocumentoFiscal",
              proc.get("cnpj_reclamado"), "CNPJ Reclamado", obrigatorio=False)

    # ── Aba: Parâmetros do Cálculo ───────────────────────────────────────────
    _clicar_aba(page, "tabParametrosCalculo")
    time.sleep(0.3)

    cont = DADOS.get("contrato", {})
    cj   = DADOS.get("correcao_juros", {})
    ir   = DADOS.get("imposto_renda", {})

    # Data de liquidação (usar ajuizamento ou demissão como referência)
    data_liq = cont.get("ajuizamento") or cont.get("demissao") or ""
    _fill(page, "dataUltimaAtualizacao", data_liq, "Data Última Atualização", obrigatorio=False)

    # Índice de correção → mapeamento para os valores do enum local
    _MAPA_INDICE = {
        "Tabela JT Unica Mensal": "TRABALHISTA",
        "IPCA-E":                 "IPCA_E",
        "Selic":                  "SELIC",
        "TRCT":                   "TRCT",
    }
    indice_raw = cj.get("indice_correcao") or "Tabela JT Unica Mensal"
    indice_val = _MAPA_INDICE.get(indice_raw, "TRABALHISTA")
    _select(page, "indiceTrabalhista", indice_val, "Índice de Correção")

    # Tabela de juros
    _MAPA_JUROS = {
        "Juros Padrao": "TRABALHISTA",
        "Selic":        "SELIC",
    }
    juros_raw = cj.get("taxa_juros") or "Juros Padrao"
    juros_val = _MAPA_JUROS.get(juros_raw, "TRABALHISTA")
    _select(page, "juros", juros_val, "Tabela de Juros")

    # Base dos juros
    _MAPA_BASE = {
        "Verbas":         "VERBAS",
        "Credito Total":  "CREDITO_TOTAL",
    }
    base_raw = cj.get("base_juros") or "Verbas"
    _select(page, "baseDeJurosDasVerbas", _MAPA_BASE.get(base_raw, "VERBAS"), "Base dos Juros")

    # Imposto de Renda
    if ir.get("apurar"):
        _checkbox(page, "apurarImpostoRenda", True, "Apurar IR")
        if ir.get("meses_tributaveis"):
            _fill(page, "qtdMesesRendimento",
                  str(ir["meses_tributaveis"]), "Meses tributáveis", obrigatorio=False)
        if ir.get("dependentes"):
            _checkbox(page, "possuiDependentes", True, "Possui dependentes")
            _fill(page, "quantidadeDependentes",
                  str(ir["dependentes"]), "Qtd dependentes", obrigatorio=False)

    _salvar(page)
    return True


# ── FASE 2 — HISTÓRICO SALARIAL ───────────────────────────────────────────────

def fase_02_historico_salarial(page) -> bool:
    _log("\n[FASE 2] Preenchendo Histórico Salarial...")

    if not _clicar_menu(page, "Histórico Salarial"):
        page.goto(PJECALC_BASE + "/pages/calculo/historico-salarial.xhtml")
        page.wait_for_load_state("networkidle", timeout=T_NAV)

    cont     = DADOS.get("contrato", {})
    historico = DADOS.get("historico_salarial") or []

    # Montar histórico a partir de dados disponíveis
    if not historico:
        ult = cont.get("ultima_remuneracao")
        if ult:
            historico = [{
                "data_inicio": cont.get("admissao") or "",
                "data_fim":    cont.get("demissao")  or "",
                "valor":       ult,
                "nome":        "Salário",
            }]

    if not historico:
        _log("    ○  Histórico salarial: sem dados — preencher manualmente")
        return True

    for i, entrada in enumerate(historico):
        nome_sal = entrada.get("nome") or (
            f"Salário Período {i+1}" if len(historico) > 1 else "Salário"
        )
        _log(f"\n    → Entrada {i+1}: {nome_sal} — R$ {float(entrada['valor']):.2f}")

        if not _novo(page):
            _pausar("Clique em 'Novo' para adicionar salário e pressione Enter")

        time.sleep(0.5)

        _fill(page, "nome", nome_sal, "Nome do salário", obrigatorio=False)

        # Tipo de valor → Fixo
        _radio(page, "tipoValor", "FIXO", "Tipo de valor")

        # Tipo de variação → Monetário
        _radio(page, "tipoVariacaoDaParcela", "MONETARIO", "Tipo variação")

        _fill(page, "valorParaBaseDeCalculo",
              _fmt_br(float(entrada["valor"])), "Valor (R$)")

        if entrada.get("data_inicio"):
            _fill(page, "competenciaInicial", entrada["data_inicio"],
                  "Competência inicial", obrigatorio=False)
        if entrada.get("data_fim"):
            _fill(page, "competenciaFinal", entrada["data_fim"],
                  "Competência final", obrigatorio=False)

        # Incidências (padrão: FGTS e INSS marcados)
        # Não alterar defaults do sistema — apenas desmarcar se necessário
        _salvar(page)
        time.sleep(0.4)

    return True


# ── FASE 3 — VERBAS ───────────────────────────────────────────────────────────

def _lancar_verba(page, verba: dict) -> bool:
    """Lança uma verba no formulário."""
    nome = verba.get("nome_pjecalc") or verba.get("nome_sentenca", "?")

    if not _novo(page):
        _pausar(f"Clique em 'Novo' para adicionar verba '{nome}' e pressione Enter")

    time.sleep(0.5)

    _fill(page, "descricao", nome, "Nome da verba")

    # Característica
    _MAPA_CARAC = {
        "Comum":       "COMUM",
        "13o Salario": "DECIMO_TERCEIRO",
        "Aviso Previo": "AVISO_PREVIO",
        "Ferias":      "FERIAS",
    }
    carac = _MAPA_CARAC.get(verba.get("caracteristica", "Comum"), "COMUM")
    _radio(page, "caracteristicaVerba", carac, "Característica")
    time.sleep(0.3)

    # Ocorrência
    _MAPA_OCORR = {
        "Mensal":              "MENSAL",
        "Dezembro":            "DEZEMBRO",
        "Periodo Aquisitivo":  "PERIODO_AQUISITIVO",
        "Desligamento":        "DESLIGAMENTO",
    }
    ocorr = _MAPA_OCORR.get(verba.get("ocorrencia", "Mensal"), "MENSAL")
    _radio(page, "ocorrenciaPagto", ocorr, "Ocorrência")
    time.sleep(0.3)

    # Valor ou percentual
    if verba.get("valor_informado") is not None:
        _radio(page, "valor", "INFORMADO", "Forma de cálculo")
        _fill(page, "valorDevidoInformado",
              _fmt_br(float(verba["valor_informado"])), "Valor informado")
    elif verba.get("percentual") is not None:
        _radio(page, "valor", "CALCULADO", "Forma de cálculo")

    # Incidências
    if verba.get("incidencia_fgts") is not None:
        _checkbox(page, "fgts", verba["incidencia_fgts"], "Incide FGTS")
    if verba.get("incidencia_inss") is not None:
        _checkbox(page, "inss", verba["incidencia_inss"], "Incide INSS")
    if verba.get("incidencia_ir") is not None:
        _checkbox(page, "irpf", verba["incidencia_ir"], "Incide IRPF")

    _salvar(page)
    time.sleep(0.4)
    return True


def fase_03_verbas(page) -> bool:
    _log("\n[FASE 3] Preenchendo Verbas Deferidas...")

    if not _clicar_menu(page, "Verbas"):
        page.goto(PJECALC_BASE + "/pages/calculo/verba/verba-calculo.xhtml")
        page.wait_for_load_state("networkidle", timeout=T_NAV)

    todas = (
        VERBAS_MAPEADAS.get("predefinidas", [])
        + VERBAS_MAPEADAS.get("personalizadas", [])
    )
    nao_rec = VERBAS_MAPEADAS.get("nao_reconhecidas", [])

    for v in todas:
        try:
            _lancar_verba(page, v)
        except Exception as e:
            _pausar(f"Erro em '{v.get('nome_sentenca')}': {e}. Preencha manualmente.")

    if nao_rec:
        _log(f"\n    ⚠  {len(nao_rec)} verba(s) NÃO RECONHECIDA(s):")
        for v in nao_rec:
            _log(f"       – {v.get('nome_sentenca')}")
        _pausar("Lance as verbas acima manualmente e pressione Enter.")

    return True


# ── FASE 4 — FGTS ─────────────────────────────────────────────────────────────

def fase_04_fgts(page) -> bool:
    _log("\n[FASE 4] Configurando FGTS...")

    if not _clicar_menu(page, "FGTS"):
        page.goto(PJECALC_BASE + "/pages/calculo/fgts.xhtml")
        page.wait_for_load_state("networkidle", timeout=T_NAV)

    fgts = DADOS.get("fgts", {})
    aliq = fgts.get("aliquota")
    if aliq is not None:
        # Selecionar linha da alíquota (8% ou 2%)
        try:
            # A tabela exibe linhas; clicar na que corresponde à alíquota
            pct = int(float(aliq) * 100)
            page.click(f"td:has-text('{pct}%')", timeout=3000)
            _log(f"    ✓  Alíquota FGTS: {pct}%")
        except Exception:
            _log(f"    ○  Alíquota FGTS: configurar manualmente ({aliq})")

    if fgts.get("multa_40") is not None:
        _checkbox(page, "multa", fgts["multa_40"], "Multa 40% (art. 18 §1°)")

    if fgts.get("multa_467") is not None:
        _checkbox(page, "multaDoArtigo467", fgts["multa_467"],
                  "Multa Art. 467 CLT", obrigatorio=False)

    _salvar(page)
    return True


# ── FASE 5 — HONORÁRIOS ───────────────────────────────────────────────────────

def fase_05_honorarios(page) -> bool:
    hon = DADOS.get("honorarios", {})
    if not hon.get("percentual") and not hon.get("valor_fixo"):
        _log("\n[FASE 5] Honorários: sem dados — fase ignorada")
        return True

    _log("\n[FASE 5] Preenchendo Honorários Advocatícios...")

    if not _clicar_menu(page, "Honorários"):
        page.goto(PJECALC_BASE + "/pages/calculo/honorarios.xhtml")
        page.wait_for_load_state("networkidle", timeout=T_NAV)

    if not _novo(page):
        _pausar("Clique em 'Novo' para adicionar honorário e pressione Enter")
    time.sleep(0.5)

    # Tipo de honorário
    _select(page, "tpHonorario", "SUCUMBENCIA", "Tipo honorário", obrigatorio=False)

    # Descrição
    _fill(page, "descricao", "Honorários Advocatícios", "Descrição", obrigatorio=False)

    # Parte devedora
    _MAPA_DEVEDOR = {
        "Reclamado":   "RECLAMADO",
        "Reclamante":  "RECLAMANTE",
        "Ambos":       "AMBOS",
    }
    devedor = _MAPA_DEVEDOR.get(hon.get("parte_devedora", "Reclamado"), "RECLAMADO")
    _radio(page, "tipoDeDevedor", devedor, "Parte devedora")
    time.sleep(0.3)

    if hon.get("percentual"):
        _radio(page, "tipoValor", "CALCULADO", "Tipo (percentual)")
        _fill(page, "aliquota",
              f"{hon['percentual'] * 100:.2f}".rstrip("0").rstrip("."),
              "Alíquota (%)")
    elif hon.get("valor_fixo"):
        _radio(page, "tipoValor", "INFORMADO", "Tipo (fixo)")
        _fill(page, "valor", _fmt_br(hon["valor_fixo"]), "Valor fixo")

    _salvar(page)
    return True


# ── FASE 6 — CONTRIBUIÇÃO SOCIAL ──────────────────────────────────────────────

def fase_06_inss(page) -> bool:
    _log("\n[FASE 6] Contribuição Social (INSS)...")
    # O PJE-Calc Cidadão calcula INSS automaticamente com base nas verbas.
    # Não há aba específica de INSS no cálculo externo.
    _log("    ○  INSS calculado automaticamente pelo PJE-Calc — fase OK")
    return True


# ── ORQUESTRAÇÃO PRINCIPAL ────────────────────────────────────────────────────

def main():
    proc   = DADOS.get("processo", {})
    numero = proc.get("numero", "N/A")
    rec    = proc.get("reclamante", "")

    _log("=" * 62)
    _log("  AGENTE PJE-CALC — Automação de Preenchimento")
    _log(f"  Processo:   {numero}")
    if rec:
        _log(f"  Reclamante: {rec}")
    _log("=" * 62)

    # Garantir PJE-Calc Cidadão rodando
    _garantir_pjecalc()

    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=HEADLESS, slow_mo=SLOW_MO)
        ctx  = browser.new_context(viewport={"width": 1440, "height": 900})
        page = ctx.new_page()

        _log(f"\n  Abrindo PJE-Calc Cidadão: {PJECALC_BASE}/pages/principal.jsf")
        page.goto(PJECALC_BASE + "/pages/principal.jsf")
        page.wait_for_load_state("networkidle", timeout=T_NAV)
        _log("  ✓  PJE-Calc carregado — iniciando preenchimento\n")

        fases = [
            ("01 — Novo Cálculo",          fase_01_novo_calculo),
            ("02 — Histórico Salarial",    fase_02_historico_salarial),
            ("03 — Verbas",                fase_03_verbas),
            ("04 — FGTS",                  fase_04_fgts),
            ("05 — Honorários",            fase_05_honorarios),
            ("06 — INSS",                  fase_06_inss),
        ]

        resultados: dict = {}
        for nome_fase, func_fase in fases:
            _log(f"\n{'─' * 62}")
            try:
                func_fase(page)
                resultados[nome_fase] = "✓"
            except Exception as e:
                resultados[nome_fase] = f"⚠ {e}"
                _log(f"  Fase '{nome_fase}' teve erro: {e}")
                _pausar(f"Complete '{nome_fase}' manualmente e pressione Enter.")

        _log("\n" + "=" * 62)
        _log("  RESULTADO FINAL:")
        for nome, res in resultados.items():
            _log(f"    {res}  {nome}")
        _log("=" * 62)
        _log("\n  Preenchimento concluído!")
        _log("  Revise os dados no PJE-Calc e clique em Liquidar.\n")
        input("  Pressione Enter para fechar o browser: ")
        browser.close()


if __name__ == "__main__":
    main()
'''

# ── Template do launcher .bat ─────────────────────────────────────────────────

_TEMPLATE_BAT = """\
@echo off
title Agente PJE-Calc
chcp 65001 > nul
cls

echo.
echo  ============================================================
echo    AGENTE PJE-CALC - Automacao de Preenchimento
echo    Processo: $$$NUMERO$$$
echo  ============================================================
echo.

:: ── 1. Verificar Python ──────────────────────────────────────────────────────
python --version > nul 2>&1
if %errorlevel% neq 0 (
    echo  [ERRO] Python nao encontrado no PATH.
    echo  Instale em: https://python.org/downloads
    echo  Marque "Add Python to PATH" durante a instalacao.
    echo.
    pause
    exit /b 1
)
echo  Python: OK
echo.

:: ── 2. Verificar/instalar Playwright ─────────────────────────────────────────
python -c "from playwright.sync_api import sync_playwright" > nul 2>&1
if %errorlevel% neq 0 (
    echo  Instalando Playwright - aguarde, pode demorar 1-2 minutos...
    pip install playwright
    if %errorlevel% neq 0 (
        echo  [ERRO] Falha ao instalar playwright via pip.
        echo  Tente manualmente: pip install playwright
        pause
        exit /b 1
    )
    python -m playwright install chromium
    if %errorlevel% neq 0 (
        echo  [ERRO] Falha ao instalar o browser Chromium.
        echo  Tente manualmente: python -m playwright install chromium
        pause
        exit /b 1
    )
    echo  Playwright instalado com sucesso.
    echo.
) else (
    echo  Playwright: OK
    echo.
)

:: ── 3. Baixar script de automacao ────────────────────────────────────────────
set SCRIPT_TEMP=%TEMP%\\pjecalc_auto_$$$SESSAO_CURTO$$$.py
echo  Baixando script de automacao...
python -c "import urllib.request, sys; urllib.request.urlretrieve('$$$SCRIPT_URL$$$', r'%SCRIPT_TEMP%')" 2>&1
if %errorlevel% neq 0 (
    echo.
    echo  [ERRO] Nao foi possivel baixar o script.
    echo  URL: $$$SCRIPT_URL$$$
    echo  Verifique a conexao com a internet e tente novamente.
    echo.
    pause
    exit /b 1
)
echo  Script baixado. Iniciando automacao...
echo.

:: ── 4. Executar automacao ────────────────────────────────────────────────────
python "%SCRIPT_TEMP%"
set SAIDA=%errorlevel%

del "%SCRIPT_TEMP%" > nul 2>&1

echo.
if %SAIDA% neq 0 (
    echo  [AVISO] O script encerrou com codigo de erro %SAIDA%.
    echo  Verifique o PJE-Calc e complete manualmente se necessario.
) else (
    echo  Automacao concluida com sucesso!
)
echo.
pause
"""


# ── Funções públicas ──────────────────────────────────────────────────────────

def gerar_script(
    dados: dict[str, Any],
    verbas_mapeadas: dict[str, Any],
    sessao_id: str,
) -> Path:
    """
    Gera um script Python standalone para automação do PJE-Calc Cidadão.

    Retorna: Path do arquivo .py em OUTPUT_DIR/{sessao_id}/
    """
    numero_raw = dados.get("processo", {}).get("numero") or sessao_id[:8]
    numero     = re.sub(r"[^0-9A-Za-z]", "", numero_raw)
    data_str   = datetime.now().strftime("%d/%m/%Y %H:%M")
    data_arq   = datetime.now().strftime("%d%m%Y_%H%M%S")
    nome       = f"auto_pjecalc_{numero}_{data_arq}.py"

    dados_json  = json.dumps(dados,           ensure_ascii=False, indent=2)
    verbas_json = json.dumps(verbas_mapeadas, ensure_ascii=False, indent=2)

    conteudo = (
        _TEMPLATE
        .replace("$$$DADOS_JSON$$$",   dados_json)
        .replace("$$$VERBAS_JSON$$$",  verbas_json)
        .replace("$$$NUMERO$$$",       numero_raw)
        .replace("$$$DATA$$$",         data_str)
        .replace("$$$SESSAO_ID$$$",    sessao_id)
        .replace("$$$NOME_ARQUIVO$$$", nome)
    )

    pasta = OUTPUT_DIR / sessao_id
    pasta.mkdir(parents=True, exist_ok=True)
    caminho = pasta / nome
    caminho.write_text(conteudo, encoding="utf-8")
    return caminho


def gerar_launcher_bat(
    script_url: str,
    sessao_id: str,
    numero: str,
) -> Path:
    """
    Gera um .bat launcher que:
      1. Verifica/instala Playwright automaticamente
      2. Baixa o script .py do servidor Railway
      3. Executa o script — tudo com duplo-clique, sem terminal manual

    Parâmetros:
        script_url: URL completa do endpoint /download/{sessao_id}/script
        sessao_id:  UUID da sessão
        numero:     Número do processo (para nome do arquivo)

    Retorna: Path do arquivo .bat em OUTPUT_DIR/{sessao_id}/
    """
    numero_safe   = re.sub(r"[^0-9A-Za-z]", "", numero or sessao_id[:8])
    sessao_curto  = sessao_id[:8]
    nome          = f"PJECalc_Automacao_{numero_safe}.bat"

    conteudo = (
        _TEMPLATE_BAT
        .replace("$$$NUMERO$$$",       numero or sessao_id[:8])
        .replace("$$$SCRIPT_URL$$$",   script_url)
        .replace("$$$SESSAO_CURTO$$$", sessao_curto)
    )

    pasta = OUTPUT_DIR / sessao_id
    pasta.mkdir(parents=True, exist_ok=True)
    caminho = pasta / nome
    # Windows .bat precisa de encoding CP1252 (ANSI) para acentos no console
    caminho.write_text(conteudo, encoding="utf-8")
    return caminho
