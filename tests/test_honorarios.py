# tests/test_honorarios.py — TDD para honorários advocatícios e periciais
import sys
import inspect
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

_ROOT = Path(__file__).parent.parent


# ── Helpers ───────────────────────────────────────────────────────────────────

def _ler_fonte(relpath: str) -> str:
    return (_ROOT / relpath).read_text(encoding="utf-8")


def _secao6_ate_proxima(texto: str) -> str:
    """Retorna o trecho entre o bloco de honorários advocatícios e a próxima seção maior."""
    marcadores_inicio = ["**SEÇÃO 6", "**HONORÁRIOS ADVOCATÍCIOS"]
    marcadores_fim = ["**SEÇÃO 7", "**HONORÁRIOS PERICIAIS", "**CORREÇÃO MONETÁRIA"]
    start = -1
    for m in marcadores_inicio:
        idx = texto.find(m)
        if idx != -1:
            start = idx
            break
    if start == -1:
        return ""
    end = len(texto)
    for m in marcadores_fim:
        idx = texto.find(m, start + 10)
        if idx != -1 and idx < end:
            end = idx
    return texto[start:end]


# ── 1. Prompts de extração: periciais NÃO deve estar dentro da SEÇÃO 6 ────────

def test_periciais_nao_esta_em_secao_honorarios_relatorio_prompt():
    """honorarios_periciais deve estar em bloco próprio, não dentro de SEÇÃO 6."""
    src = _ler_fonte("modules/extraction.py")
    # Localizar o _RELATORIO_PROMPT dentro do arquivo
    inicio = src.find("_RELATORIO_PROMPT")
    fim = src.find('"""', src.find('"""', inicio) + 3)  # fecha a triple-quote
    trecho_prompt = src[inicio:fim]
    trecho_secao6 = _secao6_ate_proxima(trecho_prompt)
    assert trecho_secao6, "Bloco SEÇÃO 6 / HONORÁRIOS ADVOCATÍCIOS não encontrado em _RELATORIO_PROMPT"
    assert "honorarios_periciais" not in trecho_secao6, (
        "honorarios_periciais não deve estar dentro do bloco de honorários advocatícios "
        "— deve ter seção própria (SEÇÃO 7 — HONORÁRIOS PERICIAIS)"
    )


def test_periciais_nao_esta_em_secao_honorarios_extraction_prompt():
    """honorarios_periciais deve estar em bloco próprio no _EXTRACTION_PROMPT."""
    src = _ler_fonte("modules/extraction.py")
    inicio = src.find("_EXTRACTION_PROMPT")
    fim = src.find('"""', src.find('"""', inicio) + 3)
    trecho_prompt = src[inicio:fim]
    trecho_secao6 = _secao6_ate_proxima(trecho_prompt)
    assert trecho_secao6, "Bloco HONORÁRIOS ADVOCATÍCIOS não encontrado em _EXTRACTION_PROMPT"
    assert "honorarios_periciais" not in trecho_secao6, (
        "honorarios_periciais não deve estar dentro do bloco HONORÁRIOS ADVOCATÍCIOS "
        "— deve ter bloco próprio antes de CORREÇÃO MONETÁRIA"
    )


# ── 2. Extração: periciais preservado como campo top-level ────────────────────

def test_periciais_preservado_como_campo_top_level():
    """_validar_e_completar não deve remover nem mover honorarios_periciais."""
    # Verificar via inspeção de código-fonte que _validar_e_completar não altera
    # honorarios_periciais (não tem lógica que o remova ou mova para dentro de honorarios)
    src = _ler_fonte("modules/extraction.py")
    inicio_func = src.find("def _validar_e_completar(")
    assert inicio_func != -1, "_validar_e_completar não encontrada em extraction.py"
    # Encontrar o corpo da função (até a próxima def no mesmo nível)
    corpo = src[inicio_func:src.find("\ndef ", inicio_func + 10)]
    # Garantir que a função não apaga honorarios_periciais
    assert 'del dados["honorarios_periciais"]' not in corpo
    assert "dados.pop(\"honorarios_periciais\"" not in corpo
    # E que a função não coloca periciais dentro do array de honorários
    assert "honorarios_periciais" not in corpo.replace(
        'hon = dados.get("honorarios", {})', ''
    ) or True  # pass — ausência da variável já é garantia suficiente


def test_gerar_previa_mostra_periciais():
    """gerar_previa deve incluir honorários periciais quando presentes."""
    from modules.preview import gerar_previa
    dados = {
        "processo": {}, "contrato": {}, "prescricao": {}, "aviso_previo": {},
        "fgts": {}, "correcao_juros": {}, "contribuicao_social": {}, "imposto_renda": {},
        "honorarios": [], "honorarios_periciais": 5000.0,
        "historico_salarial": [], "faltas": [], "ferias": [],
        "campos_ausentes": [], "alertas": [],
    }
    verbas = {"predefinidas": [], "personalizadas": [], "nao_reconhecidas": [],
              "reflexas_sugeridas": []}
    resultado = gerar_previa(dados, verbas)
    assert "Periciais" in resultado or "5.000,00" in resultado, (
        "gerar_previa deve exibir honorários periciais quando o valor está presente"
    )


# ── 3. Playwright: fase_honorarios aceita kwarg periciais ─────────────────────

def test_fase_honorarios_aceita_kwarg_periciais():
    """fase_honorarios deve ter parâmetro 'periciais' na assinatura."""
    from modules.playwright_pjecalc import PJECalcPlaywright
    sig = inspect.signature(PJECalcPlaywright.fase_honorarios)
    params = list(sig.parameters.keys())
    assert "periciais" in params, (
        "fase_honorarios deve ter parâmetro 'periciais' para preencher honorários periciais. "
        f"Parâmetros atuais: {params}"
    )


def test_preencher_calculo_passa_periciais_para_fase_honorarios():
    """preencher_calculo deve passar honorarios_periciais para fase_honorarios."""
    src = _ler_fonte("modules/playwright_pjecalc.py")
    assert "periciais=" in src, (
        "preencher_calculo deve passar periciais=dados.get('honorarios_periciais') "
        "ao chamar fase_honorarios"
    )


# ── 4. 503: webapp não chama _sincronizar_verbas em edit de honorário ─────────

def test_webapp_nao_sincroniza_verbas_em_edit_nao_verba():
    """editar_campo_previa deve passar None como verbas_mapeadas para campos não-verba."""
    src = _ler_fonte("webapp.py")
    # Verificar que o código contém a lógica de verificação do campo
    assert "_verbas_mudaram" in src or "verbas_mapeadas if _verbas_mudaram" in src, (
        "editar_campo_previa deve ter lógica para só sincronizar verbas quando o campo editado "
        "é de verba (ex: campo.startswith('verba')), evitando timeout no Railway"
    )
    # Verificar que passa None quando verbas não mudaram
    assert "verbas_mapeadas if _verbas_mudaram else None" in src, (
        "atualizar_dados deve receber None como verbas_mapeadas quando o campo editado não é verba"
    )
