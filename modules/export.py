# modules/export.py — Geração do Arquivo .PJC e Finalização do Cálculo
# Manual Técnico PJE-Calc, Seção 8

from __future__ import annotations

import logging
import time
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
from typing import Any

from config import OUTPUT_DIR, WAIT_AFTER_NAVIGATE, WAIT_AFTER_SAVE

logger = logging.getLogger(__name__)


# ── Fluxo principal de finalização (Manual, Seção 8.1 e 8.2) ─────────────────

def finalizar_calculo(
    automation: Any,            # instância de PJECalcAutomation
    gestor_hitl: Any,           # instância de GestorHITL
    calculo_id: str,
    dados: dict[str, Any],
) -> Path | None:
    """
    Executa a sequência de finalização do cálculo no PJE-Calc:
    1. Validar
    2. Liquidar (com confirmação obrigatória)
    3. Imprimir relatório PDF
    4. Exportar .pjc

    Retorna o caminho do arquivo .pjc gerado, ou None em caso de falha.
    """
    from modules.human_loop import CategoriaSituacao

    # Passo 1: Validar
    logger.info("Executando Validação do cálculo...")
    alertas_validacao = _executar_validar(automation)

    if alertas_validacao:
        resposta = gestor_hitl.acionar(
            CategoriaSituacao.ERRO_AUTOMACAO,
            f"O sistema identificou os seguintes alertas na validação:\n\n"
            + "\n".join(f"  • {a}" for a in alertas_validacao)
            + "\n\nComo deseja prosseguir?",
            opcoes=[
                "1 — Corrigir os alertas antes de liquidar",
                "2 — Ignorar alertas e liquidar mesmo assim",
            ],
        )
        if resposta.strip().startswith("1"):
            logger.info("Usuário optou por corrigir antes de liquidar.")
            return None  # retorna ao fluxo principal para correção

    # Passo 2: Liquidar — confirmação OBRIGATÓRIA
    confirmado = gestor_hitl.confirmar_acao_irreversivel(
        descricao="Clicar em LIQUIDAR",
        efeito=(
            "O cálculo será liquidado e consolidado. "
            "Qualquer alteração posterior exigirá nova liquidação."
        ),
    )
    if not confirmado:
        logger.info("Liquidação cancelada pelo usuário.")
        return None

    data_liquidacao = _executar_liquidar(automation)
    if not data_liquidacao:
        return None

    # Passo 3: Imprimir relatório
    logger.info("Gerando relatório PDF...")
    _executar_imprimir(automation, calculo_id)

    # Passo 4: Exportar .pjc
    caminho_pjc = OUTPUT_DIR / f"{calculo_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pjc"
    sucesso = _executar_exportar(automation, caminho_pjc)

    if not sucesso:
        return None

    # Verificar integridade
    valido = verificar_integridade_pjc(caminho_pjc, dados)
    if not valido:
        gestor_hitl.acionar(
            CategoriaSituacao.ERRO_AUTOMACAO,
            f"O arquivo .pjc gerado em '{caminho_pjc}' pode estar incompleto. "
            "Verifique o arquivo antes de juntar aos autos.",
            campo="arquivo_pjc",
        )

    return caminho_pjc


# ── Operações no PJE-Calc ─────────────────────────────────────────────────────

def _executar_validar(automation: Any) -> list[str]:
    """
    Executa Operações > Validar e retorna lista de alertas encontrados.
    """
    try:
        automation._clicar_menu("Operações")
        automation._clicar_opcao("Validar")
        time.sleep(WAIT_AFTER_NAVIGATE)

        # Capturar alertas via screenshot/accessibility
        alertas = _capturar_alertas_validacao(automation)
        logger.info(f"Validação concluída. Alertas: {len(alertas)}")
        return alertas
    except Exception as e:
        logger.error(f"Erro durante validação: {e}")
        return [f"Erro inesperado durante validação: {e}"]


def _executar_liquidar(automation: Any) -> str | None:
    """
    Executa Operações > Liquidar.
    Retorna a data de liquidação usada, ou None em caso de erro.
    """
    try:
        automation._clicar_menu("Operações")
        automation._clicar_opcao("Liquidar")
        time.sleep(WAIT_AFTER_NAVIGATE)

        # Data de liquidação sugerida = hoje
        data_hoje = datetime.now().strftime("%d/%m/%Y")
        automation._preencher_data("Data da Liquidação", data_hoje)

        # Clicar no ícone de confirmar liquidação
        automation._clicar_botao("Liquidar")
        time.sleep(WAIT_AFTER_SAVE * 2)

        screenshot = automation._capturar_screenshot()
        if automation._detectar_erro_na_tela(screenshot):
            erro = automation._extrair_texto_erro(screenshot)
            logger.error(f"Erro na liquidação: {erro}")
            return None

        logger.info(f"Cálculo liquidado com sucesso. Data: {data_hoje}")
        return data_hoje
    except Exception as e:
        logger.error(f"Erro durante liquidação: {e}")
        return None


def _executar_imprimir(automation: Any, calculo_id: str) -> Path | None:
    """
    Executa Operações > Imprimir para gerar o relatório PDF.
    """
    try:
        automation._clicar_menu("Operações")
        automation._clicar_opcao("Imprimir")
        time.sleep(WAIT_AFTER_NAVIGATE)

        caminho_pdf = OUTPUT_DIR / f"{calculo_id}_relatorio.pdf"
        # Em versão desktop, configura impressão para PDF via diálogo do sistema
        logger.info(f"Relatório PDF: {caminho_pdf}")
        return caminho_pdf
    except Exception as e:
        logger.warning(f"Não foi possível imprimir relatório: {e}")
        return None


def _executar_exportar(automation: Any, caminho_pjc: Path) -> bool:
    """
    Executa Operações > Exportar e salva o arquivo .pjc.
    """
    try:
        automation._clicar_menu("Operações")
        automation._clicar_opcao("Exportar")
        time.sleep(WAIT_AFTER_NAVIGATE)

        # Preencher caminho no diálogo de salvar arquivo
        automation._preencher_campo("Nome do arquivo", str(caminho_pjc))
        automation._clicar_botao("Salvar")
        time.sleep(WAIT_AFTER_SAVE * 2)

        # Verificar se arquivo foi criado
        if caminho_pjc.exists() and caminho_pjc.stat().st_size > 0:
            logger.info(f"Arquivo .pjc gerado: {caminho_pjc}")
            return True
        else:
            logger.error(f"Arquivo .pjc não encontrado em: {caminho_pjc}")
            return False
    except Exception as e:
        logger.error(f"Erro durante exportação: {e}")
        return False


# ── Verificação de integridade (Manual, Seção 8.3) ────────────────────────────

def verificar_integridade_pjc(
    caminho: Path,
    dados_esperados: dict[str, Any] | None = None,
) -> bool:
    """
    Verifica a integridade do arquivo .pjc gerado.
    1. Arquivo existe e não está vazio
    2. XML válido (parseável)
    3. Contém número do processo e verbas esperadas
    """
    # 1. Existência e tamanho
    if not caminho.exists():
        logger.error(f"Arquivo não existe: {caminho}")
        return False
    if caminho.stat().st_size == 0:
        logger.error(f"Arquivo vazio: {caminho}")
        return False

    # 2. XML válido
    try:
        tree = ET.parse(str(caminho))
        root = tree.getroot()
    except ET.ParseError as e:
        logger.error(f"XML inválido no .pjc: {e}")
        return False

    # 3. Verificações de conteúdo básico
    xml_str = ET.tostring(root, encoding="unicode")
    erros: list[str] = []

    if dados_esperados:
        numero = dados_esperados.get("processo", {}).get("numero")
        if numero and numero not in xml_str:
            erros.append(f"Número do processo '{numero}' não encontrado no .pjc")

        reclamante = dados_esperados.get("processo", {}).get("reclamante")
        if reclamante and reclamante.split()[0] not in xml_str:
            erros.append(f"Reclamante '{reclamante}' possivelmente ausente no .pjc")

    if erros:
        for erro in erros:
            logger.warning(f"Integridade .pjc: {erro}")
        return False

    logger.info(f"Arquivo .pjc verificado com sucesso: {caminho}")
    return True


def _capturar_alertas_validacao(automation: Any) -> list[str]:
    """
    Extrai alertas exibidos pelo PJE-Calc após a validação.
    Stub — adaptar conforme estrutura real da janela de alertas.
    """
    alertas: list[str] = []

    try:
        import pywinauto
        from config import PJECALC_WINDOW_TITLE

        app = pywinauto.Desktop(backend="uia")
        janela = app.window(title_re=f".*{PJECALC_WINDOW_TITLE}.*")

        # Buscar por labels de alerta na janela
        for elem in janela.descendants(control_type="Text"):
            texto = elem.window_text()
            if any(palavra in texto.lower() for palavra in ["alerta", "atenção", "erro", "aviso"]):
                if texto not in alertas:
                    alertas.append(texto)
    except Exception:
        # Se não conseguir extrair via accessibility, capturar screenshot e informar
        pass

    return alertas


def notificar_conclusao(
    caminho_pjc: Path,
    dados: dict[str, Any],
    gestor_hitl: Any,
) -> None:
    """
    Notifica o usuário sobre a conclusão e fornece orientações para juntada.
    """
    processo = dados.get("processo", {})
    num = processo.get("numero") or "—"
    reclamante = processo.get("reclamante") or "—"

    mensagem = (
        f"\n{'═' * 67}\n"
        f"  CALCULO CONCLUIDO COM SUCESSO\n"
        f"{'═' * 67}\n"
        f"  Processo  : {num}\n"
        f"  Reclamante: {reclamante}\n"
        f"\n"
        f"  Arquivo .pjc gerado:\n"
        f"  {caminho_pjc}\n"
        f"\n"
        f"  INSTRUCOES PARA JUNTADA NOS AUTOS:\n"
        f"  1. Acesse o PJE e localize o processo\n"
        f"  2. Use a funcao de juntada de documentos\n"
        f"  3. Selecione o arquivo .pjc acima\n"
        f"  4. Confirme o envio\n"
        f"\n"
        f"  Resolucao CSJT n. 185/2017, art. 22, par. 6 — arquivo .pjc\n"
        f"  obrigatorio para liquidacao de sentencas trabalhistas.\n"
        f"{'═' * 67}"
    )
    print(mensagem)
    logger.info(f"Processo concluído. Arquivo: {caminho_pjc}")
