#!/usr/bin/env python
# main.py — Orquestrador Principal do Agente PJE-Calc
# Manual Técnico PJE-Calc v1.0 — 2026
#
# USO:
#   python main.py --sentenca caminho/sentenca.pdf [--backend pyautogui|playwright]
#   python main.py --sessao ID_SESSAO  (retomar sessão interrompida)

from __future__ import annotations

import argparse
import json
import logging
import sys
import uuid
from datetime import datetime
from pathlib import Path

# Garantir que o diretório do projeto está no sys.path
sys.path.insert(0, str(Path(__file__).parent))

from config import (
    ANTHROPIC_API_KEY,
    AUTOMATION_BACKEND,
    LOG_LEVEL,
    SESSIONS_DIR,
)
from modules.ingestion import ler_documento
from modules.extraction import extrair_dados_sentenca
from modules.classification import mapear_para_pjecalc
from modules.document_collector import (
    identificar_documentos_necessarios,
    formatar_pergunta_dado_ausente,
)
from modules.preview import gerar_previa, exibir_previa, aplicar_edicao_usuario
from modules.automation import PJECalcAutomation
from modules.human_loop import GestorHITL, CategoriaSituacao, gerar_log_rastreabilidade
from modules.export import finalizar_calculo, notificar_conclusao

# ── Logging ───────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler()],
)
logger = logging.getLogger("pjecalc_agent")


# ── Orquestrador ──────────────────────────────────────────────────────────────

def executar_agente(
    caminho_sentenca: str | Path,
    backend: str = AUTOMATION_BACKEND,
    sessao_id: str | None = None,
) -> None:
    """
    Fluxo completo em 6 fases conforme Manual Técnico, Seção 1.1:
    1. Ingestão       — leitura e normalização da sentença
    2. Extração       — NLP jurídico + regex → JSON estruturado
    3. Classificação  — mapeamento de verbas para PJE-Calc
    4. Solicitação    — coleta de campos ausentes do usuário
    5. Prévia         — exibição e confirmação pelo usuário
    6. Automação      — preenchimento do PJE-Calc + geração .pjc
    """
    sessao_id = sessao_id or str(uuid.uuid4())
    caminho_sentenca = Path(caminho_sentenca)

    _exibir_banner(sessao_id)

    # Inicializar gestor HITL
    gestor = GestorHITL(sessao_id=sessao_id)

    # ── Fase 1: Ingestão ──────────────────────────────────────────────────────
    print("\n[FASE 1/6] Lendo e normalizando a sentença...")
    try:
        resultado_leitura = ler_documento(caminho_sentenca)
    except Exception as e:
        logger.error(f"Erro na leitura da sentença: {e}")
        gestor.acionar(
            CategoriaSituacao.ERRO_AUTOMACAO,
            f"Não foi possível ler o arquivo '{caminho_sentenca}'.\nErro: {e}\n"
            "Verifique o arquivo e tente novamente.",
        )
        return

    if resultado_leitura.get("alertas"):
        for alerta in resultado_leitura["alertas"]:
            print(f"  ! {alerta}")

    texto_normalizado = resultado_leitura["texto"]
    print(f"  OK — {resultado_leitura['num_paginas']} páginas | formato: {resultado_leitura['formato']}")

    # ── Fase 2: Extração ──────────────────────────────────────────────────────
    print("\n[FASE 2/6] Extraindo dados jurídicos da sentença...")

    if not ANTHROPIC_API_KEY:
        print(
            "  AVISO: ANTHROPIC_API_KEY não configurada.\n"
            "  A extração usará apenas regex (precisão reduzida).\n"
            "  Configure a variável de ambiente ANTHROPIC_API_KEY para usar IA."
        )

    try:
        dados = extrair_dados_sentenca(texto_normalizado, sessao_id=sessao_id)
    except Exception as e:
        logger.error(f"Erro na extração: {e}")
        gestor.acionar(
            CategoriaSituacao.ERRO_AUTOMACAO,
            f"Erro durante a extração dos dados da sentença:\n{e}",
        )
        return

    num_verbas = len(dados.get("verbas_deferidas", []))
    num_ausentes = len(dados.get("campos_ausentes", []))
    print(f"  OK — {num_verbas} verba(s) identificada(s) | {num_ausentes} campo(s) ausente(s)")

    # Salvar estado após extração
    gestor.salvar_estado({"fase": "extracao", "dados": dados})

    # ── Fase 3: Classificação ─────────────────────────────────────────────────
    print("\n[FASE 3/6] Classificando verbas para o PJE-Calc...")
    verbas_mapeadas = mapear_para_pjecalc(dados.get("verbas_deferidas", []))

    n_pred = len(verbas_mapeadas["predefinidas"])
    n_pers = len(verbas_mapeadas["personalizadas"])
    n_nrec = len(verbas_mapeadas["nao_reconhecidas"])
    n_refl = len(verbas_mapeadas["reflexas_sugeridas"])

    print(
        f"  OK — Lançamento Expresso: {n_pred} | "
        f"Manual: {n_pers} | Não reconhecidas: {n_nrec} | "
        f"Reflexas sugeridas: {n_refl}"
    )

    if n_nrec > 0:
        nomes_nrec = [v.get("nome_sentenca", "?") for v in verbas_mapeadas["nao_reconhecidas"]]
        gestor.acionar(
            CategoriaSituacao.VERBA_NAO_RECONHECIDA,
            f"As seguintes verbas não foram reconhecidas automaticamente:\n"
            + "\n".join(f"  • {n}" for n in nomes_nrec)
            + "\nElas serão lançadas como verbas personalizadas (Lançamento Manual).\n"
            "Pressione Enter para continuar ou descreva ajustes necessários:",
        )

    gestor.salvar_estado({"fase": "classificacao", "dados": dados, "verbas_mapeadas": verbas_mapeadas})

    # ── Fase 4: Solicitação de dados ausentes ─────────────────────────────────
    print("\n[FASE 4/6] Coletando informações e documentos necessários...")

    # Processar alertas de confiança baixa
    if dados.get("alertas"):
        dados = gestor.processar_alertas(dados, dados["alertas"])

    # Coletar campos obrigatórios ausentes
    campos_ausentes = dados.get("campos_ausentes", [])
    if campos_ausentes:
        print(f"  {len(campos_ausentes)} campo(s) precisam ser informados:")
        dados = gestor.processar_campos_ausentes(dados, campos_ausentes)
        dados["campos_ausentes"] = []
    else:
        print("  OK — Todos os campos obrigatórios foram extraídos automaticamente.")

    # Identificar documentos auxiliares necessários
    docs_necessarios = identificar_documentos_necessarios(verbas_mapeadas, dados)
    if docs_necessarios:
        print(f"\n  Documentos opcionais que podem melhorar o cálculo:")
        for doc in docs_necessarios:
            print(f"  • {doc.get('nome')} — {doc.get('uso_pjecalc', '')}")

    gestor.salvar_estado({"fase": "dados_coletados", "dados": dados, "verbas_mapeadas": verbas_mapeadas})

    # ── Fase 5: Prévia ────────────────────────────────────────────────────────
    print("\n[FASE 5/6] Gerando prévia dos parâmetros...")
    confirmado = False

    while not confirmado:
        exibir_previa(dados, verbas_mapeadas)

        print("\nSua escolha: ", end="")
        escolha = input().strip().upper()

        if escolha == "C":
            confirmado = True

        elif escolha == "E":
            print("Informe o campo a editar (formato 'secao.campo', ex: contrato.admissao): ", end="")
            campo_editar = input().strip()
            print(f"Novo valor para '{campo_editar}': ", end="")
            novo_valor = input().strip()
            dados = aplicar_edicao_usuario(dados, campo_editar, novo_valor)
            print(f"  Campo '{campo_editar}' atualizado.")

            # Registrar na rastreabilidade
            _salvar_rastreabilidade(sessao_id, gerar_log_rastreabilidade(
                campo_pjecalc=campo_editar,
                valor=novo_valor,
                fonte="USUARIO",
                confirmado_usuario=True,
                pergunta=f"Edição manual do campo '{campo_editar}'",
                resposta_usuario=novo_valor,
            ))

        elif escolha == "A":
            print("Informe o nome da verba a adicionar: ", end="")
            nova_verba = input().strip()
            if nova_verba:
                verbas_mapeadas["nao_reconhecidas"].append({
                    "nome_sentenca": nova_verba,
                    "nome_pjecalc": nova_verba,
                    "tipo": "Principal",
                    "caracteristica": "Comum",
                    "ocorrencia": "Mensal",
                    "lancamento": "Manual",
                    "mapeada": False,
                    "confianca": 1.0,
                })
                print(f"  Verba '{nova_verba}' adicionada para lançamento manual.")

        elif escolha == "X":
            print("Operação cancelada pelo usuário.")
            return

        else:
            print("  Opção inválida. Use C, E, A ou X.")

    gestor.salvar_estado({"fase": "previa_confirmada", "dados": dados, "verbas_mapeadas": verbas_mapeadas})

    # ── Fase 6: Automação ─────────────────────────────────────────────────────
    print("\n[FASE 6/6] Iniciando preenchimento automatizado do PJE-Calc...")
    print(
        "\n  ATENCAO: O agente irá operar a interface do PJE-Calc.\n"
        "  Não mova o mouse nem interaja com o teclado durante o processo.\n"
        "  O agente pausará e solicitará sua intervenção quando necessário.\n"
    )
    input("  Pressione Enter quando o PJE-Calc estiver aberto e pronto...")

    try:
        automation = PJECalcAutomation(
            backend=backend,
            acionar_usuario=lambda msg, opts: gestor.acionar(
                CategoriaSituacao.ERRO_AUTOMACAO, msg, opts
            ),
        )
    except ImportError as e:
        print(f"\n  ERRO: {e}")
        print(
            "  Instale as dependências necessárias e execute novamente.\n"
            "  Veja requirements.txt para a lista completa."
        )
        return

    try:
        # 6.1 Criar novo cálculo
        automation.criar_novo_calculo(dados)

        # 6.2 Parâmetros do Cálculo
        automation.preencher_parametros_calculo(dados)

        # 6.3 Faltas (se houver)
        if dados.get("faltas"):
            automation.preencher_faltas(dados["faltas"])

        # 6.4 Férias
        if dados.get("ferias"):
            automation.verificar_ferias(dados["ferias"])

        # 6.5 Histórico Salarial
        if dados.get("historico_salarial"):
            automation.preencher_historico_salarial(dados["historico_salarial"])

        # 6.6 Verbas
        automation.preencher_verbas(verbas_mapeadas)

        # 6.7 FGTS
        automation.preencher_fgts(dados.get("fgts", {}))

        # 6.8 Contribuição Social
        automation.preencher_contribuicao_social(dados.get("contribuicao_social", {}))

        # 6.9 Imposto de Renda
        automation.preencher_imposto_renda(dados.get("imposto_renda", {}))

        # 6.10 Multas e Indenizações
        todas_verbas = (
            verbas_mapeadas.get("predefinidas", [])
            + verbas_mapeadas.get("personalizadas", [])
            + verbas_mapeadas.get("nao_reconhecidas", [])
        )
        verbas_indenizacoes = [
            v for v in todas_verbas
            if v.get("pagina_pjecalc") == "Multas e Indenizacoes"
        ]
        if verbas_indenizacoes:
            automation.preencher_multas_indenizacoes(verbas_indenizacoes)

        # 6.11 Honorários
        automation.preencher_honorarios(dados.get("honorarios", {}))

        # 6.12 Correção, Juros e Multa
        automation.preencher_correcao_juros(dados.get("correcao_juros", {}))

        print("\n  Preenchimento concluído! Iniciando finalização...")

        # Finalizar: Validar → Liquidar → Exportar .pjc
        calculo_id = f"{dados.get('processo', {}).get('numero', 'calculo').replace('-', '').replace('.', '')}"
        caminho_pjc = finalizar_calculo(automation, gestor, calculo_id, dados)

        if caminho_pjc:
            notificar_conclusao(caminho_pjc, dados, gestor)
            _salvar_log_final(sessao_id, dados, verbas_mapeadas, automation, caminho_pjc)
        else:
            print("\n  O cálculo foi preenchido mas a exportação não foi concluída.")
            print("  Verifique o PJE-Calc e exporte o arquivo .pjc manualmente.")

    except KeyboardInterrupt:
        print("\n\n  Processo interrompido pelo usuário (Ctrl+C).")
        gestor.salvar_estado({
            "fase": "automacao_interrompida",
            "dados": dados,
            "verbas_mapeadas": verbas_mapeadas,
        })
        print(f"  Estado salvo. Para retomar, execute:\n  python main.py --sessao {sessao_id}")

    except Exception as e:
        logger.error(f"Erro durante automação: {e}", exc_info=True)
        gestor.acionar(
            CategoriaSituacao.ERRO_AUTOMACAO,
            f"Erro inesperado durante o preenchimento:\n{e}\n\n"
            "O estado foi salvo. Você pode retomar a sessão após corrigir o problema.",
        )
        gestor.salvar_estado({
            "fase": "erro_automacao",
            "erro": str(e),
            "dados": dados,
            "verbas_mapeadas": verbas_mapeadas,
        })
    finally:
        try:
            automation.fechar()
        except Exception:
            pass


# ── Funções auxiliares ────────────────────────────────────────────────────────

def _exibir_banner(sessao_id: str) -> None:
    print(
        "\n" + "═" * 67 + "\n"
        "  AGENTE PJE-CALC — Automação de Liquidação de Sentenças\n"
        "  Trabalhistas — Powered by Claude (Anthropic)\n"
        + "═" * 67 + "\n"
        f"  Sessão: {sessao_id}\n"
        f"  Data  : {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}\n"
        + "═" * 67
    )


def _salvar_rastreabilidade(sessao_id: str, entrada: dict) -> None:
    """Append de entrada no arquivo de rastreabilidade da sessão."""
    caminho = SESSIONS_DIR / f"{sessao_id}_rastreabilidade.jsonl"
    with open(caminho, "a", encoding="utf-8") as f:
        f.write(json.dumps(entrada, ensure_ascii=False) + "\n")


def _salvar_log_final(
    sessao_id: str,
    dados: dict,
    verbas_mapeadas: dict,
    automation: PJECalcAutomation,
    caminho_pjc: Path,
) -> None:
    """Salva log completo da sessão ao final."""
    log_final = {
        "sessao_id": sessao_id,
        "timestamp_conclusao": datetime.utcnow().isoformat() + "Z",
        "arquivo_pjc": str(caminho_pjc),
        "processo": dados.get("processo", {}),
        "num_verbas": len(dados.get("verbas_deferidas", [])),
        "acoes_automacao": automation.obter_log_acoes(),
    }
    caminho_log = SESSIONS_DIR / f"{sessao_id}_final.json"
    with open(caminho_log, "w", encoding="utf-8") as f:
        json.dump(log_final, f, ensure_ascii=False, indent=2)
    logger.info(f"Log final salvo: {caminho_log}")


# ── Entrada de linha de comando ───────────────────────────────────────────────

def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Agente IA para preenchimento automatizado do PJE-Calc",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Exemplos:\n"
            "  python main.py --sentenca sentenca.pdf\n"
            "  python main.py --sentenca sentenca.pdf --backend playwright\n"
            "  python main.py --sessao abc123  # retomar sessão\n"
        ),
    )
    parser.add_argument(
        "--sentenca",
        type=str,
        help="Caminho para o arquivo de sentença (PDF, DOCX ou TXT)",
    )
    parser.add_argument(
        "--backend",
        type=str,
        default=AUTOMATION_BACKEND,
        choices=["pyautogui", "playwright"],
        help="Backend de automação (padrão: pyautogui para versão desktop)",
    )
    parser.add_argument(
        "--sessao",
        type=str,
        help="ID de sessão anterior para retomada",
    )
    parser.add_argument(
        "--apenas-extrair",
        action="store_true",
        help="Apenas extrair dados da sentença sem preencher o PJE-Calc",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()

    if args.sessao and not args.sentenca:
        # Retomar sessão
        sessao_id = args.sessao
        gestor = GestorHITL(sessao_id=sessao_id)
        estado = gestor.carregar_estado()
        if not estado:
            print(f"Sessão '{sessao_id}' não encontrada.")
            sys.exit(1)
        gestor.retomar(estado)
        dados = estado.get("dados", {})
        verbas_mapeadas = estado.get("verbas_mapeadas", {})
        print(f"Fase anterior: {estado.get('fase', 'desconhecida')}")
        print("Retomada de sessão requer verificação manual do estado — funcionalidade em desenvolvimento.")
        sys.exit(0)

    elif args.sentenca:
        if args.apenas_extrair:
            # Modo de apenas extração (para testes)
            resultado = ler_documento(args.sentenca)
            dados = extrair_dados_sentenca(resultado["texto"])
            verbas_mapeadas = mapear_para_pjecalc(dados.get("verbas_deferidas", []))
            print(gerar_previa(dados, verbas_mapeadas))
            sys.exit(0)
        else:
            executar_agente(
                caminho_sentenca=args.sentenca,
                backend=args.backend,
                sessao_id=args.sessao,
            )
    else:
        # Modo interativo — solicitar arquivo
        print("Agente PJE-Calc — Automação de Liquidação de Sentenças Trabalhistas")
        print("─" * 67)
        print("Informe o caminho para o arquivo de sentença (PDF, DOCX ou TXT):")
        caminho = input("  Caminho: ").strip().strip('"')
        if not caminho:
            print("Nenhum arquivo informado. Encerrando.")
            sys.exit(1)
        executar_agente(caminho_sentenca=caminho, backend=args.backend)
