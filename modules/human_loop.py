# modules/human_loop.py — Supervisão Humana (HITL) e Tratamento de Incertezas
# Manual Técnico PJE-Calc, Seção 7

from __future__ import annotations

import json
import logging
import time
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Callable

from config import WAIT_USER_TIMEOUT, SESSIONS_DIR

logger = logging.getLogger(__name__)


# ── Taxonomia de situações HITL (Manual, Seção 7.1) ──────────────────────────

class NivelUrgencia(str, Enum):
    BLOQUEANTE = "BLOQUEANTE"
    REQUER_DECISAO = "REQUER_DECISAO"
    REQUER_CONFIRMACAO = "REQUER_CONFIRMACAO"
    CONFIRMACAO_OBRIGATORIA = "CONFIRMACAO_OBRIGATORIA"


class CategoriaSituacao(str, Enum):
    DADOS_AUSENTES = "DADOS_AUSENTES"
    DADOS_AMBIGUOS = "DADOS_AMBIGUOS"
    VERBA_NAO_RECONHECIDA = "VERBA_NAO_RECONHECIDA"
    PARAMETROS_CONFLITANTES = "PARAMETROS_CONFLITANTES"
    ERRO_AUTOMACAO = "ERRO_AUTOMACAO"
    CONFIANCA_BAIXA = "CONFIANCA_BAIXA"
    ACAO_IRREVERSIVEL = "ACAO_IRREVERSIVEL"


# Mapeamento categoria → nível de urgência
URGENCIA_POR_CATEGORIA: dict[CategoriaSituacao, NivelUrgencia] = {
    CategoriaSituacao.DADOS_AUSENTES: NivelUrgencia.BLOQUEANTE,
    CategoriaSituacao.DADOS_AMBIGUOS: NivelUrgencia.BLOQUEANTE,
    CategoriaSituacao.VERBA_NAO_RECONHECIDA: NivelUrgencia.REQUER_DECISAO,
    CategoriaSituacao.PARAMETROS_CONFLITANTES: NivelUrgencia.BLOQUEANTE,
    CategoriaSituacao.ERRO_AUTOMACAO: NivelUrgencia.BLOQUEANTE,
    CategoriaSituacao.CONFIANCA_BAIXA: NivelUrgencia.REQUER_CONFIRMACAO,
    CategoriaSituacao.ACAO_IRREVERSIVEL: NivelUrgencia.CONFIRMACAO_OBRIGATORIA,
}


# ── Gestor HITL ───────────────────────────────────────────────────────────────

class GestorHITL:
    """
    Gerencia todas as interrupções para supervisão humana.
    Persiste o estado para permitir retomada após intervenção.
    Manual, Seção 7.
    """

    def __init__(
        self,
        sessao_id: str,
        interface_usuario: Callable[[str], str] | None = None,
    ):
        self.sessao_id = sessao_id
        self._interface = interface_usuario or self._cli_padrao
        self._historico: list[dict[str, Any]] = []
        self._arquivo_estado = SESSIONS_DIR / f"{sessao_id}_estado.json"
        self._arquivo_log_hitl = SESSIONS_DIR / f"{sessao_id}_hitl.jsonl"

    # ── Métodos públicos ──────────────────────────────────────────────────────

    def acionar(
        self,
        categoria: CategoriaSituacao,
        mensagem: str,
        opcoes: list[str] | None = None,
        campo: str | None = None,
        trecho_sentenca: str | None = None,
        contexto: dict[str, Any] | None = None,
    ) -> str:
        """
        Aciona o usuário para uma situação HITL.
        Formata a mensagem conforme o tipo de situação (Manual, Seção 7.2).
        Registra pergunta e resposta no log.
        Retorna a resposta do usuário (string).
        """
        urgencia = URGENCIA_POR_CATEGORIA.get(categoria, NivelUrgencia.REQUER_CONFIRMACAO)
        msg_formatada = self._formatar_mensagem(
            categoria, urgencia, mensagem, opcoes, campo, trecho_sentenca
        )

        print(msg_formatada)

        # Timeout
        inicio = time.time()
        resposta = ""
        try:
            resposta = self._interface(msg_formatada)
        except KeyboardInterrupt:
            logger.warning("Intervenção cancelada pelo usuário (Ctrl+C).")
            resposta = "cancelado"

        if time.time() - inicio > WAIT_USER_TIMEOUT:
            logger.warning(f"Timeout aguardando resposta do usuário para: {campo or mensagem[:50]}")

        self._registrar_interacao(
            categoria, urgencia, mensagem, opcoes, campo, trecho_sentenca, resposta
        )

        return resposta

    def confirmar_acao_irreversivel(self, descricao: str, efeito: str) -> bool:
        """
        Solicita confirmação explícita antes de executar ação irreversível.
        Manual, Seção 7.2.3.
        Retorna True se o usuário confirmou.
        """
        msg = self._formatar_confirmacao_irreversivel(descricao, efeito)
        resposta = self.acionar(
            CategoriaSituacao.ACAO_IRREVERSIVEL,
            msg,
            opcoes=["S — Sim, executar agora", "N — Não, quero revisar antes"],
            campo=descricao,
        )
        confirmado = resposta.upper().startswith("S")
        self._log_hitl({
            "tipo": "CONFIRMACAO_IRREVERSIVEL",
            "acao": descricao,
            "efeito": efeito,
            "confirmado": confirmado,
        })
        return confirmado

    def coletar_dado_ausente(
        self,
        campo: str,
        instrucao: str,
        tela_pjecalc: str,
        validador: Callable[[str], tuple[bool, Any, str]] | None = None,
        max_tentativas: int = 3,
    ) -> Any:
        """
        Coleta um dado ausente do usuário com validação.
        Manual, Seção 7.2.1.
        """
        msg = self._formatar_dado_ausente(campo, instrucao, tela_pjecalc)

        for tentativa in range(max_tentativas):
            resposta = self.acionar(
                CategoriaSituacao.DADOS_AUSENTES,
                msg,
                campo=campo,
            )

            if not validador:
                return resposta

            valido, valor, erro = validador(resposta)
            if valido:
                return valor
            else:
                if tentativa < max_tentativas - 1:
                    print(f"  Entrada inválida: {erro}. Tente novamente.")
                else:
                    logger.error(f"Campo '{campo}': máximo de tentativas atingido.")
                    return resposta  # retorna mesmo inválido

        return None

    def resolver_ambiguidade(
        self,
        trecho: str,
        descricao_duvida: str,
        opcoes: list[str],
        campo: str | None = None,
    ) -> str:
        """
        Apresenta uma ambiguidade ao usuário e obtém sua escolha.
        Manual, Seção 7.2.2.
        """
        msg = self._formatar_ambiguidade(trecho, descricao_duvida, opcoes)
        return self.acionar(
            CategoriaSituacao.DADOS_AMBIGUOS,
            msg,
            opcoes=opcoes,
            campo=campo,
            trecho_sentenca=trecho,
        )

    def salvar_estado(self, estado: dict[str, Any]) -> None:
        """Persiste o estado completo do agente para retomada."""
        with open(self._arquivo_estado, "w", encoding="utf-8") as f:
            json.dump(
                {"sessao_id": self.sessao_id, "timestamp": _agora(), **estado},
                f, ensure_ascii=False, indent=2
            )
        logger.info(f"Estado salvo em: {self._arquivo_estado}")

    def carregar_estado(self) -> dict[str, Any] | None:
        """Carrega estado salvo de uma sessão anterior."""
        if self._arquivo_estado.exists():
            with open(self._arquivo_estado, encoding="utf-8") as f:
                return json.load(f)
        return None

    def retomar(self, estado: dict[str, Any]) -> None:
        """Notifica o usuário que o processo foi retomado."""
        print(
            "\n" + "─" * 67 + "\n"
            "  Processo retomado. Continuando de onde paramos...\n"
            + "─" * 67
        )
        logger.info(f"Sessão {self.sessao_id} retomada.")

    def processar_campos_ausentes(
        self,
        dados: dict[str, Any],
        campos_ausentes: list[str],
    ) -> dict[str, Any]:
        """
        Itera pelos campos ausentes e coleta os valores do usuário.
        Atualiza o dicionário de dados in-place.
        """
        from modules.document_collector import (
            PERGUNTAS_PADRAO, validar_resposta_usuario
        )

        for campo in campos_ausentes:
            config = PERGUNTAS_PADRAO.get(campo, {})
            instrucao = config.get("instrucao") or f"Informe o valor para: {campo}"
            tela = config.get("tela_pjecalc") or "PJE-Calc"

            def validador(resposta: str, c=campo) -> tuple[bool, Any, str]:
                return validar_resposta_usuario(c, resposta)

            valor = self.coletar_dado_ausente(
                campo=config.get("campo") or campo,
                instrucao=instrucao,
                tela_pjecalc=tela,
                validador=validador,
            )

            # Atualizar dados
            partes = campo.split(".", 1)
            if len(partes) == 2:
                secao, subcampo = partes
                if secao not in dados:
                    dados[secao] = {}
                dados[secao][subcampo] = valor
                self._log_hitl({
                    "campo_pjecalc": campo,
                    "valor": valor,
                    "fonte": "USUARIO",
                    "pergunta_formulada": instrucao,
                    "timestamp": _agora(),
                })
            else:
                dados[campo] = valor

        return dados

    def processar_alertas(self, dados: dict[str, Any], alertas: list[str]) -> dict[str, Any]:
        """
        Para cada alerta de confiança baixa, confirma com o usuário.
        """
        for alerta in alertas:
            if "confiança baixa" in alerta.lower():
                secao = alerta.split("'")[1] if "'" in alerta else "desconhecida"
                resposta = self.acionar(
                    CategoriaSituacao.CONFIANCA_BAIXA,
                    f"Atenção: {alerta}\n"
                    "Deseja revisar esta seção? [S/N]",
                    campo=secao,
                )
                if resposta.upper().startswith("S"):
                    # Solicitar revisão manual dos campos da seção
                    dados = self._revisar_secao_interativamente(dados, secao)

        return dados

    def obter_historico(self) -> list[dict[str, Any]]:
        return self._historico

    # ── Formatação de mensagens (Manual, Seção 7.2) ───────────────────────────

    def _formatar_mensagem(
        self,
        categoria: CategoriaSituacao,
        urgencia: NivelUrgencia,
        mensagem: str,
        opcoes: list[str] | None,
        campo: str | None,
        trecho: str | None,
    ) -> str:
        if categoria == CategoriaSituacao.DADOS_AUSENTES:
            return self._formatar_dado_ausente(campo or "Campo", mensagem, "PJE-Calc")
        elif categoria == CategoriaSituacao.DADOS_AMBIGUOS:
            return self._formatar_ambiguidade(trecho or "", mensagem, opcoes or [])
        elif categoria == CategoriaSituacao.ACAO_IRREVERSIVEL:
            return mensagem  # já formatado pelo chamador
        else:
            return self._formatar_generico(urgencia, mensagem, opcoes)

    @staticmethod
    def _formatar_dado_ausente(campo: str, instrucao: str, tela: str) -> str:
        borda = "═" * 65
        return (
            f"╔{borda}╗\n"
            f"║  PARADA NECESSARIA — Informação Obrigatória Ausente{' ' * 13}║\n"
            f"╠{borda}╣\n"
            f"║  Campo     : {campo:<51}║\n"
            f"║  Onde usar : {tela:<51}║\n"
            f"║{' ' * 65}║\n"
            f"║  {instrucao[:61]:<63}║\n"
            f"║  > {' ' * 61}║\n"
            f"╚{borda}╝"
        )

    @staticmethod
    def _formatar_ambiguidade(trecho: str, duvida: str, opcoes: list[str]) -> str:
        borda = "═" * 65
        trecho_curto = trecho[:55] + "..." if len(trecho) > 55 else trecho
        linhas = [
            f"╔{borda}╗",
            f"║  ATENCAO — Trecho Ambíguo na Sentença{' ' * 27}║",
            f"╠{borda}╣",
            f"║  Trecho : '{trecho_curto}'",
            f"║  Dúvida : {duvida[:55]}",
            f"║{' ' * 65}║",
            "║  Qual interpretação está correta?",
        ]
        for i, op in enumerate(opcoes, 1):
            linhas.append(f"║  [{i}] {op[:59]}")
        linhas.append(f"╚{borda}╝")
        return "\n".join(linhas)

    @staticmethod
    def _formatar_confirmacao_irreversivel(descricao: str, efeito: str) -> str:
        borda = "═" * 65
        return (
            f"╔{borda}╗\n"
            f"║  CONFIRMACAO NECESSARIA{' ' * 42}║\n"
            f"╠{borda}╣\n"
            f"║  Ação   : {descricao[:54]:<54}║\n"
            f"║  Efeito : {efeito[:54]:<54}║\n"
            f"║{' ' * 65}║\n"
            f"║  Deseja prosseguir?{' ' * 45}║\n"
            f"║  [S] Sim, executar agora{' ' * 40}║\n"
            f"║  [N] Não, quero revisar antes{' ' * 35}║\n"
            f"╚{borda}╝"
        )

    @staticmethod
    def _formatar_generico(urgencia: NivelUrgencia, mensagem: str, opcoes: list[str] | None) -> str:
        simbolo = {
            NivelUrgencia.BLOQUEANTE: "PARADA",
            NivelUrgencia.REQUER_DECISAO: "DECISAO NECESSARIA",
            NivelUrgencia.REQUER_CONFIRMACAO: "CONFIRMACAO",
            NivelUrgencia.CONFIRMACAO_OBRIGATORIA: "CONFIRMACAO OBRIGATORIA",
        }.get(urgencia, "AVISO")

        borda = "─" * 67
        linhas = [f"\n{borda}", f"  [{simbolo}]", f"  {mensagem}"]
        if opcoes:
            for i, op in enumerate(opcoes, 1):
                linhas.append(f"  [{i}] {op}")
        linhas.append(borda)
        return "\n".join(linhas)

    # ── Log HITL (rastreabilidade) ────────────────────────────────────────────

    def _registrar_interacao(
        self,
        categoria: CategoriaSituacao,
        urgencia: NivelUrgencia,
        mensagem: str,
        opcoes: list[str] | None,
        campo: str | None,
        trecho: str | None,
        resposta: str,
    ) -> None:
        entrada = {
            "timestamp": _agora(),
            "sessao_id": self.sessao_id,
            "categoria": categoria.value,
            "urgencia": urgencia.value,
            "campo": campo,
            "trecho_sentenca": trecho,
            "mensagem": mensagem[:200],
            "opcoes": opcoes,
            "resposta_usuario": resposta,
        }
        self._historico.append(entrada)
        self._log_hitl(entrada)

    def _log_hitl(self, entrada: dict[str, Any]) -> None:
        with open(self._arquivo_log_hitl, "a", encoding="utf-8") as f:
            f.write(json.dumps(entrada, ensure_ascii=False) + "\n")

    # ── Revisão interativa de seção ───────────────────────────────────────────

    def _revisar_secao_interativamente(
        self, dados: dict[str, Any], secao: str
    ) -> dict[str, Any]:
        """Exibe campos de uma seção e permite edição um a um."""
        campos = dados.get(secao, {})
        if not isinstance(campos, dict):
            return dados

        print(f"\n  Revisando seção: {secao}")
        for subcampo, valor in campos.items():
            if subcampo == "confianca":
                continue
            resposta = input(f"  {subcampo} [{valor}]: ").strip()
            if resposta:
                dados[secao][subcampo] = resposta
        return dados

    # ── Interface CLI padrão ──────────────────────────────────────────────────

    @staticmethod
    def _cli_padrao(mensagem: str) -> str:
        return input("\nSua resposta: ").strip()


# ── Funções utilitárias ───────────────────────────────────────────────────────

def _agora() -> str:
    return datetime.utcnow().isoformat() + "Z"


def gerar_log_rastreabilidade(
    campo_pjecalc: str,
    valor: Any,
    fonte: str,
    confianca: float | None = None,
    trecho_sentenca: str | None = None,
    pagina_pdf: int | None = None,
    confirmado_usuario: bool = False,
    pergunta: str | None = None,
    resposta_usuario: str | None = None,
) -> dict[str, Any]:
    """
    Gera uma entrada de rastreabilidade sentença → parâmetro → PJE-Calc.
    Manual, Seção 9.3.
    """
    entrada: dict[str, Any] = {
        "campo_pjecalc": campo_pjecalc,
        "valor": valor,
        "fonte": fonte,
        "timestamp": _agora(),
    }
    if confianca is not None:
        entrada["confianca"] = confianca
    if trecho_sentenca:
        entrada["trecho_sentenca"] = trecho_sentenca
    if pagina_pdf is not None:
        entrada["pagina_pdf"] = pagina_pdf
    if confirmado_usuario:
        entrada["confirmado_usuario"] = True
    if pergunta:
        entrada["pergunta_formulada"] = pergunta
    if resposta_usuario:
        entrada["resposta_usuario"] = resposta_usuario
    return entrada
