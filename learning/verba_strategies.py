# learning/verba_strategies.py — Motor de aprendizado de estratégias de preenchimento de verbas
#
# Aprende, a cada execução de automação, qual a melhor estratégia para preencher
# cada tipo de verba (parcela) no PJE-Calc: Expresso Direto, Expresso Adaptado, ou Manual.

from __future__ import annotations

import json
import logging
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from sqlalchemy.orm import Session

# Flag para indicar se o matching LLM está habilitado (requer LLMOrchestrator)
_LLM_MATCHING_AVAILABLE = True

logger = logging.getLogger(__name__)

# Caminho do catálogo de verbas estático
_CATALOGO_PATH = Path(__file__).parent.parent / "knowledge" / "catalogo_verbas_pjecalc.json"

# Cache do catálogo em memória
_catalogo_cache: dict | None = None


def _normalizar(texto: str) -> str:
    """Normaliza texto para matching: remove acentos, minúsculas, strip."""
    if not texto:
        return ""
    nfkd = unicodedata.normalize("NFD", texto.lower())
    sem_acento = nfkd.encode("ascii", "ignore").decode("ascii")
    # Remover caracteres especiais exceto espaços
    limpo = "".join(c for c in sem_acento if c.isalnum() or c == " ")
    return " ".join(limpo.split())


def _carregar_catalogo() -> dict:
    """Carrega o catálogo de verbas do JSON (com cache em memória)."""
    global _catalogo_cache
    if _catalogo_cache is not None:
        return _catalogo_cache
    try:
        with open(_CATALOGO_PATH, "r", encoding="utf-8") as f:
            _catalogo_cache = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        logger.warning(f"Catálogo de verbas não encontrado ou inválido: {e}")
        _catalogo_cache = {"expresso": [], "adaptaveis": [], "somente_manual": []}
    return _catalogo_cache


def _similaridade_nome(nome_normalizado: str, candidato_normalizado: str) -> float:
    """Calcula similaridade simples entre dois nomes normalizados (0.0 a 1.0)."""
    if not nome_normalizado or not candidato_normalizado:
        return 0.0
    if nome_normalizado == candidato_normalizado:
        return 1.0
    # Containment
    if nome_normalizado in candidato_normalizado or candidato_normalizado in nome_normalizado:
        menor = min(len(nome_normalizado), len(candidato_normalizado))
        maior = max(len(nome_normalizado), len(candidato_normalizado))
        return menor / maior if maior > 0 else 0.0
    # Word overlap (Jaccard)
    words_a = set(nome_normalizado.split())
    words_b = set(candidato_normalizado.split())
    if not words_a or not words_b:
        return 0.0
    intersec = words_a & words_b
    uniao = words_a | words_b
    return len(intersec) / len(uniao)


class VerbaStrategyEngine:
    """
    Escolhe e registra a melhor estratégia de preenchimento de verbas no PJE-Calc.

    Estratégias:
    - expresso_direto: Correspondência exata na tabela Expresso
    - expresso_adaptado: Usa verba Expresso genérica como base, depois ajusta
    - manual: Preenchimento completo via botão Manual (formulario:incluir)

    O engine consulta:
    1. Histórico de sucesso/falha na tabela EstrategiaVerba (DB)
    2. Catálogo estático em knowledge/catalogo_verbas_pjecalc.json
    3. Classificação do modules/classification.py (VERBAS_PREDEFINIDAS)
    """

    def __init__(self, db: Session | None = None, llm_orchestrator: Any = None):
        self._db = db
        self._llm = llm_orchestrator
        self._catalogo = _carregar_catalogo()
        # Índice rápido: nome_normalizado → entrada Expresso
        self._indice_expresso: dict[str, dict] = {}
        self._indice_aliases: dict[str, dict] = {}
        self._construir_indices()
        # Lista de nomes Expresso para prompt LLM (cachear para não reconstruir)
        self._nomes_expresso_lista: list[str] = [
            e["nome_pjecalc"] for e in self._catalogo.get("expresso", [])
        ]

    def _construir_indices(self) -> None:
        """Constrói índices de busca rápida a partir do catálogo."""
        for entrada in self._catalogo.get("expresso", []):
            nome_norm = _normalizar(entrada["nome_pjecalc"])
            self._indice_expresso[nome_norm] = entrada
            for alias in entrada.get("aliases", []):
                self._indice_aliases[_normalizar(alias)] = entrada

    def _buscar_historico(self, nome_normalizado: str, tipo: str = "principal") -> Optional[dict]:
        """Busca estratégia com melhor taxa de sucesso no histórico (DB)."""
        if not self._db:
            return None
        try:
            from infrastructure.database import EstrategiaVerba
            # Buscar por nome normalizado exato
            estrategias = (
                self._db.query(EstrategiaVerba)
                .filter(
                    EstrategiaVerba.nome_normalizado == nome_normalizado,
                    EstrategiaVerba.tipo == tipo,
                    EstrategiaVerba.tentativas > 0,
                )
                .all()
            )
            if not estrategias:
                return None
            # Ordenar por taxa de sucesso (sucessos/tentativas), depois por tentativas
            melhor = max(
                estrategias,
                key=lambda e: (
                    e.sucessos / e.tentativas if e.tentativas > 0 else 0,
                    e.tentativas,
                ),
            )
            if melhor.tentativas > 0 and melhor.sucessos / melhor.tentativas >= 0.5:
                return {
                    "estrategia": melhor.estrategia,
                    "expresso_nome": melhor.expresso_nome,
                    "expresso_base": melhor.expresso_base,
                    "campos_alterar": melhor.campos_alterados_dict,
                    "parametros": melhor.parametros_dict,
                    "incidencias": melhor.incidencias_dict,
                    "confianca": melhor.sucessos / melhor.tentativas,
                    "tentativas": melhor.tentativas,
                    "baseado_em": "historico",
                }
            return None
        except Exception as e:
            logger.debug(f"Erro ao buscar histórico de estratégia: {e}")
            return None

    def _buscar_expresso_direto(self, nome_normalizado: str) -> Optional[dict]:
        """Busca correspondência direta na tabela Expresso."""
        # Match exato por nome PJE-Calc normalizado
        if nome_normalizado in self._indice_expresso:
            entrada = self._indice_expresso[nome_normalizado]
            return {
                "estrategia": "expresso_direto",
                "expresso_nome": entrada["nome_pjecalc"],
                "expresso_base": None,
                "campos_alterar": None,
                "parametros": {
                    "caracteristica": entrada.get("caracteristica"),
                    "ocorrencia": entrada.get("ocorrencia"),
                },
                "incidencias": entrada.get("incidencias"),
                "confianca": 0.95,
                "baseado_em": "catalogo",
            }
        # Match por alias
        if nome_normalizado in self._indice_aliases:
            entrada = self._indice_aliases[nome_normalizado]
            return {
                "estrategia": "expresso_direto",
                "expresso_nome": entrada["nome_pjecalc"],
                "expresso_base": None,
                "campos_alterar": None,
                "parametros": {
                    "caracteristica": entrada.get("caracteristica"),
                    "ocorrencia": entrada.get("ocorrencia"),
                },
                "incidencias": entrada.get("incidencias"),
                "confianca": 0.90,
                "baseado_em": "catalogo",
            }
        # Match fuzzy
        melhor_sim = 0.0
        melhor_entrada = None
        for nome_exp, entrada in self._indice_expresso.items():
            sim = _similaridade_nome(nome_normalizado, nome_exp)
            if sim > melhor_sim:
                melhor_sim = sim
                melhor_entrada = entrada
        for alias_norm, entrada in self._indice_aliases.items():
            sim = _similaridade_nome(nome_normalizado, alias_norm)
            if sim > melhor_sim:
                melhor_sim = sim
                melhor_entrada = entrada

        if melhor_sim >= 0.75 and melhor_entrada:
            return {
                "estrategia": "expresso_direto",
                "expresso_nome": melhor_entrada["nome_pjecalc"],
                "expresso_base": None,
                "campos_alterar": None,
                "parametros": {
                    "caracteristica": melhor_entrada.get("caracteristica"),
                    "ocorrencia": melhor_entrada.get("ocorrencia"),
                },
                "incidencias": melhor_entrada.get("incidencias"),
                "confianca": round(melhor_sim * 0.85, 2),
                "baseado_em": "catalogo_fuzzy",
            }
        return None

    def _buscar_expresso_adaptavel(self, nome_normalizado: str, verba: dict) -> Optional[dict]:
        """Busca se a verba pode ser adaptada a partir de uma base Expresso."""
        for adaptavel in self._catalogo.get("adaptaveis", []):
            base_norm = _normalizar(adaptavel["base_expresso"])
            for padrao in adaptavel.get("aplica_para", []):
                padrao_norm = _normalizar(padrao)
                # Padrão com wildcard
                if padrao_norm.endswith("*"):
                    prefixo = padrao_norm[:-1].strip()
                    if nome_normalizado.startswith(prefixo):
                        return {
                            "estrategia": "expresso_adaptado",
                            "expresso_nome": None,
                            "expresso_base": adaptavel["base_expresso"],
                            "campos_alterar": {
                                "nome": verba.get("nome_pjecalc") or verba.get("nome_sentenca", ""),
                                **{campo: verba.get(campo) for campo in adaptavel.get("campos_editaveis", []) if verba.get(campo)},
                            },
                            "parametros": {
                                "caracteristica": verba.get("caracteristica"),
                                "ocorrencia": verba.get("ocorrencia"),
                            },
                            "incidencias": {
                                "fgts": verba.get("incidencia_fgts", True),
                                "inss": verba.get("incidencia_inss", True),
                                "irpf": verba.get("incidencia_ir", True),
                            },
                            "confianca": 0.75,
                            "baseado_em": "catalogo_adaptavel",
                        }
                # Match exato
                elif _similaridade_nome(nome_normalizado, padrao_norm) >= 0.8:
                    return {
                        "estrategia": "expresso_adaptado",
                        "expresso_nome": None,
                        "expresso_base": adaptavel["base_expresso"],
                        "campos_alterar": {
                            "nome": verba.get("nome_pjecalc") or verba.get("nome_sentenca", ""),
                            **{campo: verba.get(campo) for campo in adaptavel.get("campos_editaveis", []) if verba.get(campo)},
                        },
                        "parametros": {
                            "caracteristica": verba.get("caracteristica"),
                            "ocorrencia": verba.get("ocorrencia"),
                        },
                        "incidencias": {
                            "fgts": verba.get("incidencia_fgts", True),
                            "inss": verba.get("incidencia_inss", True),
                            "irpf": verba.get("incidencia_ir", True),
                        },
                        "confianca": 0.70,
                        "baseado_em": "catalogo_adaptavel",
                    }
        return None

    def _buscar_cache_llm(self, nome_normalizado: str) -> Optional[dict]:
        """Busca resultado de matching LLM previamente cacheado na tabela EstrategiaVerba."""
        if not self._db:
            return None
        try:
            from infrastructure.database import EstrategiaVerba
            registro = (
                self._db.query(EstrategiaVerba)
                .filter(
                    EstrategiaVerba.nome_normalizado == nome_normalizado,
                    EstrategiaVerba.estrategia.in_(["expresso_direto", "expresso_adaptado"]),
                )
                .filter(
                    EstrategiaVerba.parametros.contains('"baseado_em": "llm_matching"'),
                )
                .first()
            )
            if not registro:
                return None

            params = registro.parametros_dict
            return {
                "estrategia": registro.estrategia,
                "expresso_nome": registro.expresso_nome,
                "expresso_base": registro.expresso_base,
                "campos_alterar": registro.campos_alterados_dict or None,
                "parametros": {
                    k: v for k, v in params.items()
                    if k in ("caracteristica", "ocorrencia")
                },
                "incidencias": registro.incidencias_dict,
                "confianca": params.get("confianca_llm", 0.85),
                "baseado_em": "cache_llm_matching",
            }
        except Exception as e:
            logger.debug(f"Erro ao buscar cache LLM: {e}")
            return None

    def _match_verba_via_llm(self, nome_verba: str) -> Optional[dict]:
        """
        Usa LLM para determinar se uma verba da sentença corresponde a alguma
        verba do catálogo Expresso do PJE-Calc, mesmo com variação terminológica.

        Este é o fallback final antes de classificar uma verba como "manual".
        Usa Gemini Flash (TaskType.VERBA_MATCHING) por ser rápido e barato,
        com Claude como fallback automático.

        Returns: dict com resultado do matching ou None se LLM indisponível/sem match
        """
        if not self._llm or not _LLM_MATCHING_AVAILABLE:
            logger.debug("LLM Orchestrator não disponível para matching de verbas")
            return None

        try:
            from core.llm_orchestrator import TaskType
        except ImportError:
            logger.debug("core.llm_orchestrator não importável")
            return None

        verbas_lista = "\n".join(
            f"- {nome}" for nome in self._nomes_expresso_lista
        )

        prompt = (
            f'Você é um especialista em direito trabalhista brasileiro.\n'
            f'Dada a verba "{nome_verba}" extraída de uma sentença judicial, '
            f'determine se ela corresponde a alguma das verbas abaixo do PJE-Calc Cidadão:\n\n'
            f'{verbas_lista}\n\n'
            f'Responda SOMENTE em JSON válido, sem markdown:\n'
            f'{{\n'
            f'  "match": true ou false,\n'
            f'  "verba_expresso": "NOME EXATO da verba Expresso correspondente (se match=true, null se false)",\n'
            f'  "confianca": 0.0 a 1.0,\n'
            f'  "justificativa": "breve explicação",\n'
            f'  "estrategia": "expresso_direto" se é a mesma verba, "expresso_adaptado" se similar mas precisa ajustes\n'
            f'}}'
        )

        try:
            resultado = self._llm.complete(
                TaskType.VERBA_MATCHING,
                prompt=prompt,
                inject_knowledge=False,
                inject_learned_rules=False,
                timeout=30,
            )

            if isinstance(resultado, str):
                import re
                match = re.search(r"\{.*\}", resultado, re.DOTALL)
                if match:
                    resultado = json.loads(match.group())
                else:
                    logger.warning(f"LLM retornou resposta não-JSON para matching: {resultado[:200]}")
                    return None

            if not isinstance(resultado, dict):
                logger.warning(f"LLM retornou tipo inesperado: {type(resultado)}")
                return None

            is_match = resultado.get("match", False)
            if not is_match:
                logger.info(
                    f"LLM matching: '{nome_verba}' NÃO corresponde a nenhuma verba Expresso. "
                    f"Justificativa: {resultado.get('justificativa', 'N/A')}"
                )
                return None

            verba_expresso = resultado.get("verba_expresso")
            if not verba_expresso:
                logger.warning("LLM retornou match=true mas sem verba_expresso")
                return None

            # Validar que o nome retornado realmente existe no catálogo
            nome_exp_norm = _normalizar(verba_expresso)
            entrada_catalogo = None
            for entrada in self._catalogo.get("expresso", []):
                if _normalizar(entrada["nome_pjecalc"]) == nome_exp_norm:
                    entrada_catalogo = entrada
                    break

            if not entrada_catalogo:
                # LLM pode ter retornado nome inexato — tentar fuzzy
                melhor_sim = 0.0
                for entrada in self._catalogo.get("expresso", []):
                    sim = _similaridade_nome(nome_exp_norm, _normalizar(entrada["nome_pjecalc"]))
                    if sim > melhor_sim:
                        melhor_sim = sim
                        entrada_catalogo = entrada
                if melhor_sim < 0.7:
                    logger.warning(
                        f"LLM retornou verba_expresso='{verba_expresso}' que não existe no catálogo"
                    )
                    return None

            confianca = min(float(resultado.get("confianca", 0.85)), 1.0)
            estrategia = resultado.get("estrategia", "expresso_direto")
            if estrategia not in ("expresso_direto", "expresso_adaptado"):
                estrategia = "expresso_direto"

            resultado_final = {
                "estrategia": estrategia,
                "expresso_nome": entrada_catalogo["nome_pjecalc"],
                "expresso_base": None if estrategia == "expresso_direto" else entrada_catalogo["nome_pjecalc"],
                "campos_alterar": None,
                "parametros": {
                    "caracteristica": entrada_catalogo.get("caracteristica"),
                    "ocorrencia": entrada_catalogo.get("ocorrencia"),
                },
                "incidencias": entrada_catalogo.get("incidencias"),
                "confianca": round(confianca, 2),
                "baseado_em": "llm_matching",
                "justificativa_llm": resultado.get("justificativa", ""),
            }

            # Cachear resultado no banco para consultas futuras
            self._salvar_cache_llm(nome_verba, resultado_final)

            logger.info(
                f"LLM matching: '{nome_verba}' → '{entrada_catalogo['nome_pjecalc']}' "
                f"({estrategia}, confianca={confianca:.0%}). "
                f"Justificativa: {resultado.get('justificativa', 'N/A')}"
            )
            return resultado_final

        except Exception as e:
            logger.warning(f"Erro no matching via LLM para '{nome_verba}': {e}")
            return None

    def _salvar_cache_llm(self, nome_verba: str, resultado: dict) -> None:
        """Salva resultado do matching LLM na tabela EstrategiaVerba como cache."""
        if not self._db:
            return
        try:
            from infrastructure.database import EstrategiaVerba

            nome_norm = _normalizar(nome_verba)
            registro = EstrategiaVerba(
                nome_verba=nome_verba,
                nome_normalizado=nome_norm,
                tipo="principal",
                estrategia=resultado["estrategia"],
                expresso_nome=resultado.get("expresso_nome"),
                expresso_base=resultado.get("expresso_base"),
                tentativas=0,
                sucessos=0,
                falhas=0,
            )
            registro.parametros_dict = {
                "caracteristica": resultado.get("parametros", {}).get("caracteristica"),
                "ocorrencia": resultado.get("parametros", {}).get("ocorrencia"),
                "baseado_em": "llm_matching",
                "confianca_llm": resultado.get("confianca", 0.85),
                "justificativa_llm": resultado.get("justificativa_llm", ""),
            }
            registro.incidencias_dict = resultado.get("incidencias") or {}
            self._db.add(registro)
            self._db.commit()
            logger.debug(f"Cache LLM salvo para '{nome_verba}' → '{resultado.get('expresso_nome')}'")
        except Exception as e:
            logger.debug(f"Erro ao salvar cache LLM: {e}")
            try:
                self._db.rollback()
            except Exception:
                pass

    def _is_verba_expresso(self, nome_normalizado: str) -> Optional[dict]:
        """Verifica se uma verba pertence ao catalogo Expresso.

        REGRA FUNDAMENTAL: Se a verba EXISTE na tabela Expresso do PJE-Calc,
        ela JAMAIS pode ser preenchida manualmente. Deve SEMPRE usar Expresso.
        """
        # Match exato por nome PJE-Calc
        if nome_normalizado in self._indice_expresso:
            return self._indice_expresso[nome_normalizado]
        # Match por alias
        if nome_normalizado in self._indice_aliases:
            return self._indice_aliases[nome_normalizado]
        # Match fuzzy com threshold alto
        for nome_exp, entrada in self._indice_expresso.items():
            if _similaridade_nome(nome_normalizado, nome_exp) >= 0.80:
                return entrada
        for alias_norm, entrada in self._indice_aliases.items():
            if _similaridade_nome(nome_normalizado, alias_norm) >= 0.80:
                return entrada
        return None

    def _construir_manual(self, verba: dict) -> dict:
        """Constroi estrategia Manual a partir dos dados da verba.

        IMPORTANTE: Antes de retornar "manual", valida que a verba NAO
        pertence ao catalogo Expresso. Se pertencer, forca para expresso_direto.
        """
        nome_norm = _normalizar(verba.get("nome_pjecalc") or verba.get("nome_sentenca", ""))

        # -- GUARD: Nunca retornar "manual" para uma verba Expresso --
        entrada_expresso = self._is_verba_expresso(nome_norm)
        if entrada_expresso:
            logger.warning(
                f"BLOQUEIO: Verba '{verba.get('nome_pjecalc') or verba.get('nome_sentenca')}' "
                f"pertence ao Expresso ('{entrada_expresso['nome_pjecalc']}') -- "
                f"forcando estrategia expresso_direto em vez de manual"
            )
            return {
                "estrategia": "expresso_direto",
                "expresso_nome": entrada_expresso["nome_pjecalc"],
                "expresso_base": None,
                "campos_alterar": None,
                "parametros": {
                    "caracteristica": entrada_expresso.get("caracteristica"),
                    "ocorrencia": entrada_expresso.get("ocorrencia"),
                },
                "incidencias": entrada_expresso.get("incidencias"),
                "confianca": 0.90,
                "baseado_em": "guard_expresso_bloqueio_manual",
            }

        # Verificar se existe no catalogo de somente_manual
        for manual_entry in self._catalogo.get("somente_manual", []):
            entry_norm = _normalizar(manual_entry["nome"])
            if nome_norm == entry_norm or any(
                _similaridade_nome(nome_norm, _normalizar(a)) >= 0.8
                for a in manual_entry.get("aliases", [])
            ):
                return {
                    "estrategia": "manual",
                    "expresso_nome": None,
                    "expresso_base": None,
                    "campos_alterar": None,
                    "parametros": manual_entry.get("parametros_tipicos", {}),
                    "incidencias": manual_entry.get("incidencias", {}),
                    "confianca": 0.80,
                    "baseado_em": "catalogo_manual",
                    "pagina_pjecalc": manual_entry.get("pagina_pjecalc"),
                }
        # Fallback genérico com dados da verba
        return {
            "estrategia": "manual",
            "expresso_nome": None,
            "expresso_base": None,
            "campos_alterar": None,
            "parametros": {
                "caracteristica": verba.get("caracteristica", "COMUM"),
                "ocorrencia": verba.get("ocorrencia", "MENSAL"),
                "base_calculo": verba.get("base_calculo"),
                "tipo_valor": verba.get("tipo_valor"),
            },
            "incidencias": {
                "fgts": verba.get("incidencia_fgts", False),
                "inss": verba.get("incidencia_inss", False),
                "irpf": verba.get("incidencia_ir", False),
            },
            "confianca": 0.50,
            "baseado_em": "fallback_manual",
            "pagina_pjecalc": verba.get("pagina_pjecalc"),
        }

    def escolher_estrategia(self, verba: dict) -> dict:
        """
        Dado uma verba extraída da sentença, retorna a melhor estratégia
        de preenchimento baseada no histórico de sucesso/falha e no catálogo.

        Args:
            verba: dict com campos da verba (nome_pjecalc, nome_sentenca,
                   caracteristica, ocorrencia, incidencia_fgts, etc.)

        Returns: {
            "estrategia": "expresso_direto"|"expresso_adaptado"|"manual",
            "expresso_nome": "SALDO DE SALÁRIO",  # se expresso
            "expresso_base": "DIFERENÇAS SALARIAIS",  # se adaptado
            "campos_alterar": {...},  # se adaptado
            "parametros": {...},  # detalhes de preenchimento
            "incidencias": {"fgts": bool, "inss": bool, "irpf": bool},
            "confianca": 0.95,
            "baseado_em": "historico"|"catalogo"|"catalogo_fuzzy"|"catalogo_adaptavel"|"catalogo_manual"|"fallback_manual"
        }
        """
        nome = verba.get("nome_pjecalc") or verba.get("nome_sentenca") or ""
        nome_norm = _normalizar(nome)
        tipo = verba.get("tipo", "principal").lower()
        if "reflex" in tipo or verba.get("eh_reflexa"):
            tipo = "reflexa"
        else:
            tipo = "principal"

        # 1. Consultar historico de sucesso/falha (aprendizado)
        resultado_hist = self._buscar_historico(nome_norm, tipo)
        if resultado_hist and resultado_hist["confianca"] >= 0.7:
            # GUARD: Se o historico diz "manual" mas a verba e Expresso, forcar Expresso
            if resultado_hist["estrategia"] == "manual":
                entrada_exp = self._is_verba_expresso(nome_norm)
                if entrada_exp:
                    logger.warning(
                        f"OVERRIDE: Historico sugere 'manual' para '{nome}', "
                        f"mas e verba Expresso '{entrada_exp['nome_pjecalc']}' -- forcando expresso_direto"
                    )
                    resultado_hist = {
                        "estrategia": "expresso_direto",
                        "expresso_nome": entrada_exp["nome_pjecalc"],
                        "expresso_base": None,
                        "campos_alterar": None,
                        "parametros": {
                            "caracteristica": entrada_exp.get("caracteristica"),
                            "ocorrencia": entrada_exp.get("ocorrencia"),
                        },
                        "incidencias": entrada_exp.get("incidencias"),
                        "confianca": 0.95,
                        "baseado_em": "guard_expresso_override_historico",
                    }
            logger.info(
                f"Estrategia para '{nome}': {resultado_hist['estrategia']} "
                f"(historico, confianca={resultado_hist['confianca']:.0%})"
            )
            return resultado_hist

        # 2. Buscar correspondência direta no catálogo Expresso
        resultado_exp = self._buscar_expresso_direto(nome_norm)
        if resultado_exp:
            logger.info(
                f"Estratégia para '{nome}': expresso_direto → {resultado_exp['expresso_nome']} "
                f"({resultado_exp['baseado_em']}, confianca={resultado_exp['confianca']:.0%})"
            )
            return resultado_exp

        # 3. Buscar se é adaptável a partir de uma base Expresso
        resultado_adapt = self._buscar_expresso_adaptavel(nome_norm, verba)
        if resultado_adapt:
            logger.info(
                f"Estratégia para '{nome}': expresso_adaptado → base {resultado_adapt['expresso_base']} "
                f"(confianca={resultado_adapt['confianca']:.0%})"
            )
            return resultado_adapt

        # 4. Buscar no cache de matching LLM anterior
        resultado_cache_llm = self._buscar_cache_llm(nome_norm)
        if resultado_cache_llm:
            logger.info(
                f"Estratégia para '{nome}': {resultado_cache_llm['estrategia']} → "
                f"{resultado_cache_llm.get('expresso_nome')} "
                f"(cache_llm, confianca={resultado_cache_llm['confianca']:.0%})"
            )
            return resultado_cache_llm

        # 5. Fallback: Matching semântico via LLM (última linha de defesa antes de manual)
        resultado_llm = self._match_verba_via_llm(nome)
        if resultado_llm:
            logger.info(
                f"Estratégia para '{nome}': {resultado_llm['estrategia']} → "
                f"{resultado_llm.get('expresso_nome')} "
                f"(llm_matching, confianca={resultado_llm['confianca']:.0%})"
            )
            return resultado_llm

        # 6. Fallback final: Manual completo
        resultado_manual = self._construir_manual(verba)
        logger.info(
            f"Estratégia para '{nome}': manual "
            f"({resultado_manual['baseado_em']}, confianca={resultado_manual['confianca']:.0%})"
        )
        return resultado_manual

    def registrar_resultado(
        self,
        verba: dict,
        estrategia: str,
        sucesso: bool,
        erro: str | None = None,
        detalhes: dict | None = None,
    ) -> None:
        """
        Registra resultado de uma tentativa de preenchimento no banco de dados.

        Args:
            verba: dict da verba preenchida
            estrategia: "expresso_direto", "expresso_adaptado", ou "manual"
            sucesso: se o preenchimento funcionou
            erro: mensagem de erro (se falha)
            detalhes: dados extras (expresso_nome, expresso_base, campos_alterados, etc.)
        """
        if not self._db:
            logger.debug("DB não disponível — resultado de estratégia não registrado")
            return

        try:
            from infrastructure.database import EstrategiaVerba

            nome = verba.get("nome_pjecalc") or verba.get("nome_sentenca") or ""
            nome_norm = _normalizar(nome)
            tipo = "reflexa" if verba.get("eh_reflexa") or "reflex" in verba.get("tipo", "").lower() else "principal"

            detalhes = detalhes or {}

            # Buscar ou criar registro
            registro = (
                self._db.query(EstrategiaVerba)
                .filter(
                    EstrategiaVerba.nome_normalizado == nome_norm,
                    EstrategiaVerba.tipo == tipo,
                    EstrategiaVerba.estrategia == estrategia,
                )
                .first()
            )

            if not registro:
                registro = EstrategiaVerba(
                    nome_verba=nome,
                    nome_normalizado=nome_norm,
                    tipo=tipo,
                    estrategia=estrategia,
                    expresso_nome=detalhes.get("expresso_nome"),
                    expresso_base=detalhes.get("expresso_base"),
                )
                registro.campos_alterados_dict = detalhes.get("campos_alterar") or {}
                registro.parametros_dict = detalhes.get("parametros") or {}
                registro.incidencias_dict = detalhes.get("incidencias") or {}
                self._db.add(registro)

            registro.tentativas = (registro.tentativas or 0) + 1
            if sucesso:
                registro.sucessos = (registro.sucessos or 0) + 1
            else:
                registro.falhas = (registro.falhas or 0) + 1
                registro.ultimo_erro = (erro or "")[:500]
            registro.ultima_execucao = datetime.utcnow()
            registro.updated_at = datetime.utcnow()

            self._db.commit()
            logger.info(
                f"Estratégia registrada: '{nome}' [{estrategia}] "
                f"{'OK' if sucesso else 'FALHA'} "
                f"(total: {registro.tentativas}t/{registro.sucessos}s/{registro.falhas}f)"
            )
        except Exception as e:
            logger.warning(f"Erro ao registrar resultado de estratégia: {e}")
            try:
                self._db.rollback()
            except Exception:
                pass

    def obter_estatisticas(self) -> list[dict]:
        """Retorna estatísticas de todas as estratégias registradas."""
        if not self._db:
            return []
        try:
            from infrastructure.database import EstrategiaVerba
            estrategias = (
                self._db.query(EstrategiaVerba)
                .order_by(EstrategiaVerba.tentativas.desc())
                .all()
            )
            return [
                {
                    "id": e.id,
                    "nome_verba": e.nome_verba,
                    "nome_normalizado": e.nome_normalizado,
                    "tipo": e.tipo,
                    "estrategia": e.estrategia,
                    "expresso_nome": e.expresso_nome,
                    "expresso_base": e.expresso_base,
                    "tentativas": e.tentativas or 0,
                    "sucessos": e.sucessos or 0,
                    "falhas": e.falhas or 0,
                    "taxa_sucesso": (
                        round(e.sucessos / e.tentativas, 2)
                        if e.tentativas and e.tentativas > 0
                        else 0
                    ),
                    "ultimo_erro": e.ultimo_erro,
                    "ultima_execucao": e.ultima_execucao.isoformat() if e.ultima_execucao else None,
                }
                for e in estrategias
            ]
        except Exception as e:
            logger.warning(f"Erro ao obter estatísticas de estratégias: {e}")
            return []

    def exportar_catalogo(self) -> list[dict]:
        """Exporta o catálogo completo de estratégias aprendidas (para compartilhar entre instâncias)."""
        if not self._db:
            return []
        try:
            from infrastructure.database import EstrategiaVerba
            estrategias = self._db.query(EstrategiaVerba).filter(
                EstrategiaVerba.sucessos > 0
            ).all()
            return [
                {
                    "nome_verba": e.nome_verba,
                    "nome_normalizado": e.nome_normalizado,
                    "tipo": e.tipo,
                    "estrategia": e.estrategia,
                    "expresso_nome": e.expresso_nome,
                    "expresso_base": e.expresso_base,
                    "campos_alterados": e.campos_alterados,
                    "parametros": e.parametros,
                    "incidencias": e.incidencias,
                    "tentativas": e.tentativas,
                    "sucessos": e.sucessos,
                    "falhas": e.falhas,
                    "versao_pjecalc": e.versao_pjecalc,
                }
                for e in estrategias
            ]
        except Exception as e:
            logger.warning(f"Erro ao exportar catálogo: {e}")
            return []

    def importar_catalogo(self, catalogo: list[dict]) -> int:
        """
        Importa catálogo de estratégias (para compartilhar entre instâncias).

        Returns: número de registros importados/atualizados
        """
        if not self._db:
            return 0
        try:
            from infrastructure.database import EstrategiaVerba
            count = 0
            for item in catalogo:
                nome_norm = item.get("nome_normalizado") or _normalizar(item.get("nome_verba", ""))
                if not nome_norm:
                    continue
                existente = (
                    self._db.query(EstrategiaVerba)
                    .filter(
                        EstrategiaVerba.nome_normalizado == nome_norm,
                        EstrategiaVerba.tipo == item.get("tipo", "principal"),
                        EstrategiaVerba.estrategia == item.get("estrategia", "manual"),
                    )
                    .first()
                )
                if existente:
                    # Somar métricas
                    existente.tentativas = (existente.tentativas or 0) + (item.get("tentativas") or 0)
                    existente.sucessos = (existente.sucessos or 0) + (item.get("sucessos") or 0)
                    existente.falhas = (existente.falhas or 0) + (item.get("falhas") or 0)
                    existente.updated_at = datetime.utcnow()
                else:
                    novo = EstrategiaVerba(
                        nome_verba=item.get("nome_verba", ""),
                        nome_normalizado=nome_norm,
                        tipo=item.get("tipo", "principal"),
                        estrategia=item.get("estrategia", "manual"),
                        expresso_nome=item.get("expresso_nome"),
                        expresso_base=item.get("expresso_base"),
                        tentativas=item.get("tentativas", 0),
                        sucessos=item.get("sucessos", 0),
                        falhas=item.get("falhas", 0),
                        versao_pjecalc=item.get("versao_pjecalc"),
                    )
                    novo.campos_alterados_dict = item.get("campos_alterados") or {}
                    novo.parametros_dict = item.get("parametros") or {}
                    novo.incidencias_dict = item.get("incidencias") or {}
                    self._db.add(novo)
                count += 1
            self._db.commit()
            logger.info(f"Catálogo importado: {count} registros")
            return count
        except Exception as e:
            logger.warning(f"Erro ao importar catálogo: {e}")
            try:
                self._db.rollback()
            except Exception:
                pass
            return 0
