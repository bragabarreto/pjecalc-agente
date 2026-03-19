# modules/playwright_script_builder.py
# Gerador de script Playwright standalone para automação do PJE-Calc.
# O script gerado é um arquivo .py independente (sem imports do projeto)
# que o usuário baixa e executa localmente para preencher o PJE-Calc.

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from config import OUTPUT_DIR

# ── Template do script gerado ─────────────────────────────────────────────────
# Marcadores: $$$DADOS_JSON$$$, $$$VERBAS_JSON$$$, $$$NUMERO$$$, $$$DATA$$$,
#             $$$SESSAO_ID$$$, $$$NOME_ARQUIVO$$$

_TEMPLATE = r'''#!/usr/bin/env python3
"""
Script de Automação PJE-Calc
Gerado em: $$$DATA$$$
Processo:  $$$NUMERO$$$
Sessão:    $$$SESSAO_ID$$$

USO:
  1. Instalar dependências (apenas uma vez):
       pip install playwright
       playwright install chromium

  2. Executar este script:
       python $$$NOME_ARQUIVO$$$

  3. O browser Chromium abre automaticamente navegando para o PJE-Calc.
     Faça login normalmente e pressione Enter no terminal quando concluído.

  4. O script preenche todos os campos. Em caso de campo não encontrado,
     o script pausa e aguarda preenchimento manual. Pressione Enter para continuar.
"""

import json
import sys
import time

# ── DADOS DO CÁLCULO (gerados pelo Agente PJE-Calc) ──────────────────────────

DADOS = json.loads('''$$$DADOS_JSON$$$''')
VERBAS_MAPEADAS = json.loads('''$$$VERBAS_JSON$$$''')

# ── CONFIGURAÇÃO ──────────────────────────────────────────────────────────────

PJECALC_URL  = "https://pje.trt7.jus.br/pjecalc"
HEADLESS     = False   # manter False — usuário vê o browser
SLOW_MO      = 80      # ms entre ações (aumentar se o sistema for lento)
T_SELECTOR   = 5000    # ms para encontrar elemento
T_NAVIGATION = 8000    # ms para carregar página

# ── UTILITÁRIOS ───────────────────────────────────────────────────────────────

def _fmt_br(valor: float) -> str:
    """Converte float para formato BR: 1234.56 → '1.234,56'"""
    s = f"{valor:,.2f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")

def _log(msg: str):
    print(msg, flush=True)

def _pausar(msg: str = "") -> str:
    if msg:
        print(f"\n  ⚠  {msg}", flush=True)
    resposta = input("     → Pressione Enter para continuar  (ou 'q' para sair): ").strip()
    if resposta.lower() == "q":
        print("\nSaindo. Retome o preenchimento manualmente no PJE-Calc.")
        sys.exit(0)
    return resposta

def _aguardar_login(page):
    """Aguarda o usuário fazer login no PJE-Calc."""
    _log("\n" + "="*60)
    _log("  LOGIN NECESSÁRIO")
    _log("  O browser abriu o PJE-Calc. Faça login normalmente.")
    _log("  Após o login, pressione Enter aqui para iniciar o preenchimento.")
    _log("="*60)
    input("  → Login concluído? Pressione Enter: ")
    time.sleep(1.5)
    _log("\nIniciando preenchimento automático...\n")

# ── PRIMITIVAS DE INTERAÇÃO ───────────────────────────────────────────────────

def _preencher(page, seletores: list, valor: str, descricao: str,
               obrigatorio: bool = True) -> bool:
    """Tenta preencher campo com múltiplos seletores alternativos."""
    if valor is None or str(valor).strip() == "":
        return False
    valor = str(valor).strip()
    for sel in seletores:
        try:
            el = page.wait_for_selector(sel, timeout=T_SELECTOR)
            if el and el.is_visible():
                el.click()
                time.sleep(0.15)
                el.fill("")
                el.fill(valor)
                _log(f"    ✓  {descricao}: {valor}")
                return True
        except Exception:
            continue
    if obrigatorio:
        _pausar(f"{descricao} ({repr(valor)}) — campo não encontrado. "
                f"Preencha manualmente.")
    else:
        _log(f"    ○  {descricao}: campo não encontrado (opcional)")
    return False


def _selecionar(page, seletores: list, valor: str, descricao: str,
                obrigatorio: bool = True) -> bool:
    """Tenta selecionar opção em <select> nativo ou PrimeFaces dropdown."""
    if not valor:
        return False
    valor = str(valor).strip()

    # 1. Tentar <select> HTML nativo
    for sel in seletores:
        try:
            page.select_option(sel, label=valor, timeout=T_SELECTOR)
            _log(f"    ✓  {descricao}: {valor}")
            return True
        except Exception:
            pass

    # 2. Tentar PrimeFaces SelectOneMenu
    for sel in seletores:
        try:
            # Clicar no wrapper PrimeFaces para abrir a lista
            pf_sel = re.sub(r"select\[", "div.ui-selectonemenu[", sel)
            page.click(pf_sel, timeout=T_SELECTOR)
            time.sleep(0.4)
            page.click(f".ui-selectonemenu-item[data-label='{valor}']",
                       timeout=T_SELECTOR)
            _log(f"    ✓  {descricao}: {valor}")
            return True
        except Exception:
            try:
                # Fallback: clicar por texto
                page.click(f".ui-selectonemenu-item:has-text('{valor}')",
                           timeout=2000)
                _log(f"    ✓  {descricao}: {valor}")
                return True
            except Exception:
                pass

    if obrigatorio:
        _pausar(f"{descricao} ({repr(valor)}) — seleção não encontrada. "
                "Selecione manualmente.")
    else:
        _log(f"    ○  {descricao}: opção não encontrada (opcional)")
    return False


def _marcar_checkbox(page, seletores: list, marcar: bool, descricao: str,
                     obrigatorio: bool = False) -> bool:
    """Marca ou desmarca checkbox (suporte a HTML nativo e PrimeFaces)."""
    for sel in seletores:
        try:
            checked = page.is_checked(sel, timeout=T_SELECTOR)
            if checked != marcar:
                page.click(sel)
            estado = "marcado" if marcar else "desmarcado"
            _log(f"    ✓  {descricao}: {estado}")
            return True
        except Exception:
            pass
    # PrimeFaces: div.ui-chkbox-box
    for sel in seletores:
        try:
            pf_sel = sel.replace("input[id", "div.ui-chkbox-box[id"
                                  ).replace("]", "_chkbox]")
            page.click(pf_sel, timeout=2000)
            _log(f"    ✓  {descricao}")
            return True
        except Exception:
            pass
    if obrigatorio:
        _pausar(f"Checkbox '{descricao}' não encontrado. Marque manualmente.")
    return False


def _clicar_menu(page, menu_pai: str, item: str) -> bool:
    """Navega menu principal (barra superior do PJE-Calc)."""
    tentativas_pai = [
        f".ui-menubar-item a:has-text('{menu_pai}')",
        f"a.ui-menuitem-link:has-text('{menu_pai}')",
        f"[role='menuitem']:has-text('{menu_pai}')",
        f"li:has-text('{menu_pai}') > a",
    ]
    for sel_pai in tentativas_pai:
        try:
            page.click(sel_pai, timeout=T_SELECTOR)
            time.sleep(0.5)
            page.click(f"a.ui-menuitem-link:has-text('{item}')",
                       timeout=T_SELECTOR)
            _log(f"    ✓  Menu: {menu_pai} → {item}")
            time.sleep(0.8)
            return True
        except Exception:
            pass
    return False


def _navegar_aba(page, aba: str) -> bool:
    """Navega para aba/seção lateral do PJE-Calc."""
    tentativas = [
        f"li.ui-tabmenuitem a:has-text('{aba}')",
        f"a.ui-menuitem-link:has-text('{aba}')",
        f".ui-menuitem a:has-text('{aba}')",
        f"[class*='menu'] a:has-text('{aba}')",
        f"a:has-text('{aba}')",
    ]
    for sel in tentativas:
        try:
            page.click(sel, timeout=T_SELECTOR)
            page.wait_for_load_state("networkidle", timeout=T_NAVIGATION)
            _log(f"    ✓  Aba: {aba}")
            time.sleep(0.6)
            return True
        except Exception:
            pass
    _pausar(f"Aba '{aba}' não encontrada. Navegue manualmente.")
    return False


def _clicar_botao(page, texto: str) -> bool:
    """Clica em botão pelo texto."""
    tentativas = [
        f"button:has-text('{texto}')",
        f"a.ui-button:has-text('{texto}')",
        f"input[type='submit'][value='{texto}']",
        f"span.ui-button-text:has-text('{texto}')",
        f"button[title='{texto}']",
    ]
    for sel in tentativas:
        try:
            page.click(sel, timeout=3000)
            _log(f"    ✓  Botão '{texto}'")
            time.sleep(0.5)
            return True
        except Exception:
            pass
    return False


# ── FASE 1 — NOVO CÁLCULO ────────────────────────────────────────────────────

def fase_01_novo_calculo(page) -> bool:
    _log("\n[FASE 1] Criando novo cálculo...")
    proc = DADOS.get("processo", {})

    if not _clicar_menu(page, "Cálculo", "Novo"):
        _pausar("Crie um novo cálculo manualmente (Cálculo → Novo) "
                "e pressione Enter quando o formulário abrir.")

    time.sleep(1.0)

    _preencher(page, [
        "input[id$='reclamante']", "input[id*='reclamante']",
        "input[name*='reclamante']", "input[placeholder*='Reclamante']",
    ], proc.get("reclamante") or "", "Reclamante")

    _preencher(page, [
        "input[id$='cpfReclamante']", "input[id*='cpf']",
        "input[name*='cpf']", "input[placeholder*='CPF']",
    ], proc.get("cpf_reclamante") or "", "CPF do Reclamante", obrigatorio=False)

    _preencher(page, [
        "input[id$='reclamado']", "input[id*='reclamado']",
        "input[name*='reclamado']", "input[placeholder*='Reclamado']",
    ], proc.get("reclamado") or "", "Reclamado")

    _preencher(page, [
        "input[id$='cnpjReclamado']", "input[id*='cnpj']",
        "input[name*='cnpj']", "input[placeholder*='CNPJ']",
    ], proc.get("cnpj_reclamado") or "", "CNPJ do Reclamado", obrigatorio=False)

    _preencher(page, [
        "input[id$='numeroProcesso']", "input[id*='processo']",
        "input[name*='processo']", "input[placeholder*='processo']",
    ], proc.get("numero") or "", "Número do Processo")

    _clicar_botao(page, "Confirmar") or \
    _clicar_botao(page, "Salvar") or \
    _clicar_botao(page, "Próximo")
    return True


# ── FASE 2 — PARÂMETROS DO CONTRATO ──────────────────────────────────────────

def fase_02_parametros(page) -> bool:
    _log("\n[FASE 2] Preenchendo parâmetros do contrato...")
    _navegar_aba(page, "Parâmetros")

    cont = DADOS.get("contrato", {})
    proc = DADOS.get("processo", {})
    pres = DADOS.get("prescricao", {})
    avp  = DADOS.get("aviso_previo", {})

    _selecionar(page, [
        "select[id$='estado']", "select[id*='estado']",
        "div.ui-selectonemenu[id*='estado']",
    ], proc.get("estado") or "", "Estado", obrigatorio=False)

    _selecionar(page, [
        "select[id$='municipio']", "select[id*='municipio']",
        "div.ui-selectonemenu[id*='municipio']",
    ], proc.get("municipio") or "", "Município", obrigatorio=False)

    _preencher(page, [
        "input[id$='dataAdmissao']", "input[id*='admissao']",
        "input[name*='admissao']",
    ], cont.get("admissao") or "", "Data de Admissão")

    _preencher(page, [
        "input[id$='dataAjuizamento']", "input[id*='ajuizamento']",
        "input[name*='ajuizamento']",
    ], cont.get("ajuizamento") or "", "Data de Ajuizamento")

    if cont.get("demissao"):
        _preencher(page, [
            "input[id$='dataDemissao']", "input[id*='demissao']",
            "input[name*='demissao']",
        ], cont["demissao"], "Data de Demissão")

    if cont.get("maior_remuneracao"):
        _preencher(page, [
            "input[id$='maiorRemuneracao']", "input[id*='maiorRem']",
        ], _fmt_br(cont["maior_remuneracao"]), "Maior Remuneração", obrigatorio=False)

    if cont.get("ultima_remuneracao"):
        _preencher(page, [
            "input[id$='ultimaRemuneracao']", "input[id*='ultimaRem']",
        ], _fmt_br(cont["ultima_remuneracao"]), "Última Remuneração", obrigatorio=False)

    regime = cont.get("regime") or "Tempo Integral"
    _selecionar(page, [
        "select[id$='regimeTrabalho']", "select[id*='regime']",
        "div.ui-selectonemenu[id*='regime']",
    ], regime, "Regime de Trabalho", obrigatorio=False)

    if cont.get("carga_horaria"):
        _preencher(page, [
            "input[id$='cargaHoraria']", "input[id*='cargaHoraria']",
        ], str(cont["carga_horaria"]), "Carga Horária (h/mês)", obrigatorio=False)

    if pres.get("quinquenal") is not None:
        _marcar_checkbox(page, [
            "input[id$='prescricaoQuinquenal']", "input[id*='quinquenal']",
        ], pres["quinquenal"], "Prescrição Quinquenal")

    if pres.get("fgts") is not None:
        _marcar_checkbox(page, [
            "input[id$='prescricaoFgts']", "input[id*='prescricaoFgts']",
        ], pres["fgts"], "Prescrição FGTS (30 anos)")

    tipo_avp = avp.get("tipo") or "Calculado"
    _selecionar(page, [
        "select[id$='tipoAvisoPrevio']", "select[id*='aviso']",
        "div.ui-selectonemenu[id*='aviso']",
    ], tipo_avp, "Tipo Aviso Prévio", obrigatorio=False)

    if avp.get("prazo_dias") and tipo_avp == "Informado":
        _preencher(page, [
            "input[id$='prazoAvisoPrevio']", "input[id*='prazo']",
        ], str(avp["prazo_dias"]), "Prazo Aviso Prévio (dias)", obrigatorio=False)

    if avp.get("projetar") is not None:
        _marcar_checkbox(page, [
            "input[id$='projetarAvisoPrevio']", "input[id*='projetar']",
        ], avp["projetar"], "Projetar Aviso Prévio")

    _clicar_botao(page, "Salvar") or _clicar_botao(page, "Confirmar")
    return True


# ── FASE 3 — HISTÓRICO SALARIAL ───────────────────────────────────────────────

def fase_03_historico_salarial(page) -> bool:
    _log("\n[FASE 3] Preenchendo histórico salarial...")
    _navegar_aba(page, "Histórico Salarial")

    historico = DADOS.get("historico_salarial") or []
    cont = DADOS.get("contrato", {})

    if not historico and cont.get("ultima_remuneracao"):
        historico = [{
            "data_inicio": cont.get("admissao") or "",
            "data_fim":    cont.get("demissao")  or "",
            "valor":       cont["ultima_remuneracao"],
        }]

    if not historico:
        _log("    ○  Histórico salarial: sem dados — pule esta fase")
        return True

    for i, entrada in enumerate(historico):
        nome_base = f"Salário Período {i+1}" if len(historico) > 1 else "Salário"
        _log(f"    → Entrada {i+1}: {nome_base} — R$ {entrada['valor']:.2f}")

        _clicar_botao(page, "Novo") or _clicar_botao(page, "+")
        time.sleep(0.5)

        _preencher(page, [
            "input[id$='nomeSalario']", "input[id*='nomeSalario']",
            "input[placeholder*='Nome']",
        ], nome_base, "Nome da base salarial", obrigatorio=False)

        _selecionar(page, [
            "select[id$='tipoValor']", "div.ui-selectonemenu[id*='tipoValor']",
        ], "Fixo", "Tipo de valor", obrigatorio=False)

        _preencher(page, [
            "input[id$='valorSalario']", "input[id*='valorSalario']",
            "input[placeholder*='Valor']",
        ], _fmt_br(float(entrada["valor"])), "Valor")

        if entrada.get("data_inicio"):
            _preencher(page, [
                "input[id$='dataInicioSalario']", "input[id*='inicioSalario']",
            ], entrada["data_inicio"], "Início do período", obrigatorio=False)

        if entrada.get("data_fim"):
            _preencher(page, [
                "input[id$='dataFimSalario']", "input[id*='fimSalario']",
            ], entrada["data_fim"], "Fim do período", obrigatorio=False)

        _clicar_botao(page, "Salvar") or _clicar_botao(page, "Confirmar")
        time.sleep(0.5)

    return True


# ── FASE 4 — VERBAS ───────────────────────────────────────────────────────────

def _lancar_verba_manual(page, verba: dict) -> bool:
    """Lança uma verba individualmente pelo formulário."""
    nome = verba.get("nome_pjecalc") or verba.get("nome_sentenca", "?")

    _clicar_botao(page, "Novo") or _clicar_botao(page, "+")
    time.sleep(0.5)

    _preencher(page, [
        "input[id$='nomeVerba']", "input[id*='nomeVerba']",
        "input[placeholder*='Nome']",
    ], nome, f"Nome da verba")

    tipo = verba.get("tipo", "Principal")
    _selecionar(page, [
        "select[id$='tipoVerba']", "div.ui-selectonemenu[id*='tipo']",
    ], tipo, "Tipo", obrigatorio=False)

    carac = verba.get("caracteristica") or "Comum"
    _selecionar(page, [
        "select[id$='caracteristica']", "div.ui-selectonemenu[id*='caracteristica']",
    ], carac, "Característica", obrigatorio=False)

    ocorr = verba.get("ocorrencia") or "Mensal"
    _selecionar(page, [
        "select[id$='ocorrencia']", "div.ui-selectonemenu[id*='ocorrencia']",
    ], ocorr, "Ocorrência", obrigatorio=False)

    if verba.get("periodo_inicio"):
        _preencher(page, [
            "input[id$='periodoInicio']", "input[id*='inicio']",
        ], verba["periodo_inicio"], "Período início", obrigatorio=False)

    if verba.get("periodo_fim"):
        _preencher(page, [
            "input[id$='periodoFim']", "input[id*='fim']",
        ], verba["periodo_fim"], "Período fim", obrigatorio=False)

    if verba.get("valor_informado") is not None:
        _selecionar(page, [
            "select[id$='formaCalculo']", "div.ui-selectonemenu[id*='formaCalculo']",
        ], "Informado", "Forma de cálculo", obrigatorio=False)
        _preencher(page, [
            "input[id$='valorVerba']", "input[id*='valor']",
        ], _fmt_br(float(verba["valor_informado"])), "Valor informado")
    elif verba.get("percentual") is not None:
        _selecionar(page, [
            "select[id$='formaCalculo']", "div.ui-selectonemenu[id*='formaCalculo']",
        ], "Calculado", "Forma de cálculo", obrigatorio=False)
        _preencher(page, [
            "input[id$='percentualVerba']", "input[id*='percentual']",
        ], f"{verba['percentual'] * 100:.4f}".rstrip("0").rstrip("."),
           "Percentual", obrigatorio=False)

    if verba.get("base_calculo"):
        _selecionar(page, [
            "select[id$='baseCalculo']", "div.ui-selectonemenu[id*='base']",
        ], verba["base_calculo"], "Base de cálculo", obrigatorio=False)

    if verba.get("incidencia_fgts") is not None:
        _marcar_checkbox(page, [
            "input[id$='incideFgts']", "input[id*='fgts']",
        ], verba["incidencia_fgts"], "Incide FGTS")

    if verba.get("incidencia_inss") is not None:
        _marcar_checkbox(page, [
            "input[id$='incideInss']", "input[id*='inss']",
        ], verba["incidencia_inss"], "Incide INSS")

    if verba.get("incidencia_ir") is not None:
        _marcar_checkbox(page, [
            "input[id$='incideIr']", "input[id*='imposto']",
        ], verba["incidencia_ir"], "Incide IR")

    _clicar_botao(page, "Salvar") or _clicar_botao(page, "Confirmar")
    time.sleep(0.5)
    return True


def fase_04_verbas(page) -> bool:
    _log("\n[FASE 4] Preenchendo verbas deferidas...")
    _navegar_aba(page, "Verbas")

    verbas_pred = VERBAS_MAPEADAS.get("predefinidas", [])
    verbas_pers = VERBAS_MAPEADAS.get("personalizadas", [])
    verbas_nrec = VERBAS_MAPEADAS.get("nao_reconhecidas", [])

    # Lançamento expresso: verbas pré-definidas sem detalhes especiais
    simples = [v for v in verbas_pred
               if not v.get("periodo_inicio") and not v.get("percentual")
               and not v.get("valor_informado")]
    if simples:
        _log(f"    → Tentando lançamento expresso: {len(simples)} verba(s)")
        try:
            if _clicar_botao(page, "Expresso") or \
               _clicar_botao(page, "Lançamento Expresso"):
                time.sleep(0.5)
                for v in simples:
                    nome = v.get("nome_pjecalc") or v.get("nome_sentenca", "")
                    if nome:
                        try:
                            page.click(
                                f"label:has-text('{nome}') input[type='checkbox']",
                                timeout=2000)
                            _log(f"      ✓  Expresso: {nome}")
                        except Exception:
                            _log(f"      ○  Expresso: {nome} não encontrado")
                _clicar_botao(page, "Confirmar") or _clicar_botao(page, "Salvar")
        except Exception as e:
            _log(f"    ○  Expresso indisponível ({e})")

    # Verbas que precisam de detalhes: lançamento manual
    detalhadas = [v for v in verbas_pred
                  if v.get("periodo_inicio") or v.get("percentual")
                  or v.get("valor_informado")]
    for v in detalhadas:
        _log(f"    → Manual (detalhada): {v.get('nome_pjecalc') or v.get('nome_sentenca')}")
        try:
            _lancar_verba_manual(page, v)
        except Exception as e:
            _pausar(f"Erro em '{v.get('nome_sentenca')}': {e}. Preencha manualmente.")

    # Verbas personalizadas
    for v in verbas_pers:
        _log(f"    → Personalizada: {v.get('nome_sentenca')}")
        try:
            _lancar_verba_manual(page, v)
        except Exception as e:
            _pausar(f"Erro em '{v.get('nome_sentenca')}': {e}. Preencha manualmente.")

    if verbas_nrec:
        _log(f"\n    ⚠  {len(verbas_nrec)} verba(s) NÃO RECONHECIDA(s):")
        for v in verbas_nrec:
            _log(f"       – {v.get('nome_sentenca')}")
        _pausar("Lançe as verbas acima manualmente e pressione Enter.")

    return True


# ── FASE 5 — FGTS ─────────────────────────────────────────────────────────────

def fase_05_fgts(page) -> bool:
    _log("\n[FASE 5] Preenchendo FGTS...")
    _navegar_aba(page, "FGTS")

    fgts = DADOS.get("fgts", {})
    aliquota = fgts.get("aliquota") or 0.08

    _selecionar(page, [
        "select[id$='aliquotaFgts']", "div.ui-selectonemenu[id*='aliquota']",
    ], f"{int(aliquota * 100)}%", "Alíquota FGTS", obrigatorio=False)

    if fgts.get("multa_40") is not None:
        _marcar_checkbox(page, [
            "input[id$='multa40']", "input[id*='multa40']",
        ], fgts["multa_40"], "Multa 40% (art. 18 §1º)")

    if fgts.get("multa_467") is not None:
        _marcar_checkbox(page, [
            "input[id$='multa467']", "input[id*='467']",
        ], fgts["multa_467"], "Multa Art. 467 CLT", obrigatorio=False)

    _clicar_botao(page, "Salvar") or _clicar_botao(page, "Confirmar")
    return True


# ── FASE 6 — CONTRIBUIÇÃO SOCIAL (INSS) ──────────────────────────────────────

def fase_06_inss(page) -> bool:
    _log("\n[FASE 6] Preenchendo Contribuição Social (INSS)...")
    _navegar_aba(page, "Contribuição Social")

    cs   = DADOS.get("contribuicao_social", {})
    resp = cs.get("responsabilidade") or "Ambos"

    _selecionar(page, [
        "select[id$='responsabilidade']", "div.ui-selectonemenu[id*='responsabilidade']",
    ], resp, "Responsabilidade INSS", obrigatorio=False)

    if cs.get("lei_11941") is not None:
        _marcar_checkbox(page, [
            "input[id$='lei11941']", "input[id*='11941']",
        ], cs["lei_11941"], "Lei 11.941/2009", obrigatorio=False)

    _clicar_botao(page, "Salvar") or _clicar_botao(page, "Confirmar")
    return True


# ── FASE 7 — IMPOSTO DE RENDA ─────────────────────────────────────────────────

def fase_07_irpf(page) -> bool:
    _log("\n[FASE 7] Preenchendo Imposto de Renda (IRPF)...")

    ir = DADOS.get("imposto_renda", {})
    if not ir.get("apurar", False):
        _log("    ○  IRPF: não apurar — fase ignorada")
        return True

    _navegar_aba(page, "Imposto de Renda")

    _marcar_checkbox(page, [
        "input[id$='apurarIr']", "input[id*='apurarIr']",
    ], True, "Apurar Imposto de Renda")

    if ir.get("meses_tributaveis"):
        _preencher(page, [
            "input[id$='mesesTributaveis']", "input[id*='meses']",
        ], str(ir["meses_tributaveis"]), "Meses tributáveis", obrigatorio=False)

    if ir.get("dependentes"):
        _preencher(page, [
            "input[id$='dependentes']", "input[id*='dependentes']",
        ], str(ir["dependentes"]), "Dependentes", obrigatorio=False)

    _clicar_botao(page, "Salvar") or _clicar_botao(page, "Confirmar")
    return True


# ── FASE 8 — HONORÁRIOS ───────────────────────────────────────────────────────

def fase_08_honorarios(page) -> bool:
    _log("\n[FASE 8] Preenchendo Honorários Advocatícios...")

    hon = DADOS.get("honorarios", {})
    if not hon.get("percentual") and not hon.get("valor_fixo"):
        _log("    ○  Honorários: sem dados — fase ignorada")
        return True

    _navegar_aba(page, "Honorários")

    if hon.get("parte_devedora"):
        _selecionar(page, [
            "select[id$='parteDevedora']", "div.ui-selectonemenu[id*='parte']",
        ], hon["parte_devedora"], "Parte devedora", obrigatorio=False)

    if hon.get("percentual"):
        _selecionar(page, [
            "select[id$='formaHonorarios']", "div.ui-selectonemenu[id*='forma']",
        ], "Percentual", "Forma honorários", obrigatorio=False)
        _preencher(page, [
            "input[id$='percentualHonorarios']", "input[id*='percentual']",
        ], _fmt_br(hon["percentual"] * 100), "Percentual honorários")
    elif hon.get("valor_fixo"):
        _selecionar(page, [
            "select[id$='formaHonorarios']", "div.ui-selectonemenu[id*='forma']",
        ], "Valor fixo", "Forma honorários", obrigatorio=False)
        _preencher(page, [
            "input[id$='valorHonorarios']", "input[id*='valor']",
        ], _fmt_br(hon["valor_fixo"]), "Valor honorários")

    if hon.get("periciais"):
        _preencher(page, [
            "input[id$='honorariosPericiais']", "input[id*='periciais']",
        ], _fmt_br(hon["periciais"]), "Honorários periciais", obrigatorio=False)

    _clicar_botao(page, "Salvar") or _clicar_botao(page, "Confirmar")
    return True


# ── FASE 9 — CORREÇÃO MONETÁRIA E JUROS ──────────────────────────────────────

def fase_09_correcao_juros(page) -> bool:
    _log("\n[FASE 9] Preenchendo Correção Monetária e Juros...")
    _navegar_aba(page, "Correção e Juros")

    cj     = DADOS.get("correcao_juros", {})
    indice = cj.get("indice_correcao") or "Tabela JT Única Mensal"
    juros  = cj.get("taxa_juros")      or "Juros Padrão"
    base   = cj.get("base_juros")      or "Verbas"

    _selecionar(page, [
        "select[id$='indiceCorrecao']", "div.ui-selectonemenu[id*='indice']",
    ], indice, "Índice de correção", obrigatorio=False)

    _selecionar(page, [
        "select[id$='taxaJuros']", "div.ui-selectonemenu[id*='juros']",
    ], juros, "Taxa de juros", obrigatorio=False)

    _selecionar(page, [
        "select[id$='baseJuros']", "div.ui-selectonemenu[id*='base']",
    ], base, "Base dos juros", obrigatorio=False)

    if cj.get("jam_fgts") is not None:
        _marcar_checkbox(page, [
            "input[id$='jamFgts']", "input[id*='jam']",
        ], cj["jam_fgts"], "JAM FGTS", obrigatorio=False)

    _clicar_botao(page, "Salvar") or _clicar_botao(page, "Confirmar")
    return True


# ── ORQUESTRAÇÃO PRINCIPAL ────────────────────────────────────────────────────

def main():
    from playwright.sync_api import sync_playwright

    proc   = DADOS.get("processo", {})
    numero = proc.get("numero", "N/A")
    rec    = proc.get("reclamante", "")

    _log("=" * 60)
    _log("  AGENTE PJE-CALC — Automação de Preenchimento")
    _log(f"  Processo:   {numero}")
    if rec:
        _log(f"  Reclamante: {rec}")
    _log("=" * 60)
    _log(f"\n  URL: {PJECALC_URL}")
    _log("  O browser abre em modo visível — você poderá ver e intervir.\n")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=HEADLESS, slow_mo=SLOW_MO)
        ctx  = browser.new_context(viewport={"width": 1440, "height": 900})
        page = ctx.new_page()
        page.goto(PJECALC_URL)
        page.wait_for_load_state("networkidle", timeout=15000)

        _aguardar_login(page)

        fases = [
            ("01 — Novo Cálculo",      fase_01_novo_calculo),
            ("02 — Parâmetros",        fase_02_parametros),
            ("03 — Hist. Salarial",    fase_03_historico_salarial),
            ("04 — Verbas",            fase_04_verbas),
            ("05 — FGTS",              fase_05_fgts),
            ("06 — INSS",              fase_06_inss),
            ("07 — IRPF",              fase_07_irpf),
            ("08 — Honorários",        fase_08_honorarios),
            ("09 — Correção e Juros",  fase_09_correcao_juros),
        ]

        resultados: dict[str, str] = {}
        for nome_fase, func_fase in fases:
            _log(f"\n{'─'*60}")
            try:
                func_fase(page)
                resultados[nome_fase] = "✓"
            except Exception as e:
                resultados[nome_fase] = f"⚠ {e}"
                _log(f"  Fase '{nome_fase}' teve erro: {e}")
                _pausar(f"Complete '{nome_fase}' manualmente e pressione Enter.")

        _log("\n" + "="*60)
        _log("  RESULTADO FINAL:")
        for nome, res in resultados.items():
            _log(f"    {res}  {nome}")
        _log("="*60)
        _log("\n  Preenchimento concluído!")
        _log("  Revise os dados no PJE-Calc e clique em Operações → Liquidar.\n")
        input("  Pressione Enter para fechar o browser: ")
        browser.close()


if __name__ == "__main__":
    main()
'''


# ── Função pública: gerar script ──────────────────────────────────────────────

def gerar_script(
    dados: dict[str, Any],
    verbas_mapeadas: dict[str, Any],
    sessao_id: str,
) -> Path:
    """
    Gera um script Python standalone para automação do PJE-Calc.

    Parâmetros:
        dados: dicionário completo extraído da sentença (campos processo, contrato, etc.)
        verbas_mapeadas: saída de classification.mapear_para_pjecalc()
        sessao_id: UUID da sessão

    Retorna: Path do arquivo .py gerado em OUTPUT_DIR/{sessao_id}/
    """
    numero_raw = dados.get("processo", {}).get("numero") or sessao_id[:8]
    numero     = re.sub(r"[^0-9A-Za-z]", "", numero_raw)
    data_str   = datetime.now().strftime("%d/%m/%Y %H:%M")
    data_arq   = datetime.now().strftime("%d%m%Y_%H%M%S")
    nome       = f"auto_pjecalc_{numero}_{data_arq}.py"

    # Serializar dados como JSON compacto e bem formatado
    dados_json   = json.dumps(dados,          ensure_ascii=False, indent=2)
    verbas_json  = json.dumps(verbas_mapeadas, ensure_ascii=False, indent=2)

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
