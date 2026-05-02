# modules/previa_validator.py — Validação pré-confirmação da Prévia
#
# Identifica problemas que fariam a automação Playwright falhar OU a
# Liquidação do PJE-Calc bloquear com pendências do tipo "Erro".
#
# Política: erros bloqueantes IMPEDEM a confirmação da Prévia. Avisos
# (warnings) são apenas informativos.
#
# Categorias de checagem:
# 1. Estrutura básica (processo, contrato, datas)
# 2. Históricos salariais (existência, períodos, valores)
# 3. Verbas (períodos, bases, característica/ocorrência)
# 4. Cross-refs (verba.bases_calculo.historico_subtipo aponta para histórico existente?)
# 5. Coerências legais (prescrição, aviso prévio, etc.)

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class ValidationResult:
    """Resultado de validação da Prévia."""
    erros: list[dict[str, str]] = field(default_factory=list)  # bloqueantes
    avisos: list[dict[str, str]] = field(default_factory=list)  # informativos

    @property
    def valido(self) -> bool:
        """True se NÃO há erros bloqueantes (avisos são permitidos)."""
        return len(self.erros) == 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "valido": self.valido,
            "erros": self.erros,
            "avisos": self.avisos,
            "total_erros": len(self.erros),
            "total_avisos": len(self.avisos),
        }


def _erro(secao: str, campo: str, mensagem: str) -> dict[str, str]:
    return {"severidade": "erro", "secao": secao, "campo": campo, "mensagem": mensagem}


def _aviso(secao: str, campo: str, mensagem: str) -> dict[str, str]:
    return {"severidade": "aviso", "secao": secao, "campo": campo, "mensagem": mensagem}


def _parse_data(d: str | None) -> datetime | None:
    if not d:
        return None
    try:
        return datetime.strptime(d, "%d/%m/%Y")
    except (ValueError, TypeError):
        return None


# 3 históricos default sempre disponíveis no PJE-Calc após preencher
# valorUltimaRemuneracao na Fase 1
_HISTORICOS_DEFAULT = {
    "ULTIMA_REMUNERACAO",
    "ÚLTIMA REMUNERAÇÃO",
    "ULTIMA REMUNERACAO",
    "SALARIO_BASE",
    "SALÁRIO BASE",
    "SALARIO BASE",
    "ADICIONAL_INSALUBRIDADE_PAGO",
    "ADICIONAL DE INSALUBRIDADE PAGO",
}


def _norm_nome_hist(nome: str) -> str:
    """Normaliza nome de histórico para comparação (upper, sem acento)."""
    if not nome:
        return ""
    s = nome.upper().strip()
    return (s.replace("Á", "A").replace("É", "E").replace("Í", "I")
             .replace("Ó", "O").replace("Ú", "U").replace("Ç", "C"))


def validar_previa(
    dados: dict[str, Any],
    verbas_mapeadas: dict[str, Any] | None = None,
) -> ValidationResult:
    """Valida estrutura completa da Prévia antes de permitir confirmação.

    Retorna ValidationResult com:
    - erros: bloqueantes (impedem confirmar)
    - avisos: informativos (não bloqueiam)
    """
    res = ValidationResult()

    # ═══════════════════════════════════════════════════════════════
    # 1. PROCESSO
    # ═══════════════════════════════════════════════════════════════
    proc = dados.get("processo") or {}
    if not proc.get("numero"):
        res.erros.append(_erro("processo", "numero",
            "Número do processo ausente. Obrigatório para criar o cálculo."))
    else:
        # Validar formato CNJ
        m = re.match(r"^(\d{7})-(\d{2})\.(\d{4})\.(\d)\.(\d{2})\.(\d{4})$",
                     str(proc["numero"]).strip())
        if not m:
            res.erros.append(_erro("processo", "numero",
                f"Formato CNJ inválido: '{proc['numero']}'. Esperado: NNNNNNN-DD.AAAA.J.TR.OOOO"))
        else:
            # Validar dígito verificador via algoritmo módulo 97
            num, dv, ano, just, reg, vara = m.groups()
            try:
                key = num + ano + just + reg + vara + "00"
                dv_calc = 98 - (int(key) % 97)
                if int(dv) != dv_calc:
                    res.erros.append(_erro("processo", "digito_verificador",
                        f"Dígito verificador inválido: '{dv}'. Correto pelo módulo 97: '{dv_calc:02d}'."))
            except Exception:
                pass

    if not proc.get("reclamante"):
        res.avisos.append(_aviso("processo", "reclamante",
            "Nome do reclamante ausente — cálculo pode prosseguir mas dificulta identificação."))
    if not proc.get("reclamado"):
        res.avisos.append(_aviso("processo", "reclamado",
            "Nome do reclamado ausente — cálculo pode prosseguir mas dificulta identificação."))

    # CPF/CNPJ — apenas avisos (limpos automaticamente se inválidos)
    cpf = (proc.get("cpf_reclamante") or "").replace(".", "").replace("-", "").strip()
    if cpf:
        if not _validar_cpf(cpf):
            res.avisos.append(_aviso("processo", "cpf_reclamante",
                f"CPF do reclamante inválido (DV não confere): '{cpf}'. "
                "Será limpo na automação; obrigatório só ao enviar ao PJe."))
    cnpj = (proc.get("cnpj_reclamado") or "").replace(".", "").replace("-", "").replace("/", "").strip()
    if cnpj:
        if not _validar_cnpj(cnpj):
            res.avisos.append(_aviso("processo", "cnpj_reclamado",
                f"CNPJ do reclamado inválido (DV não confere): '{cnpj}'. "
                "Será limpo na automação; obrigatório só ao enviar ao PJe."))

    if not proc.get("estado"):
        res.erros.append(_erro("processo", "estado",
            "UF do estado ausente. Obrigatório para localizar a Vara no PJE-Calc."))
    if not proc.get("municipio"):
        res.erros.append(_erro("processo", "municipio",
            "Município ausente. Obrigatório para localizar a Vara no PJE-Calc."))

    # ═══════════════════════════════════════════════════════════════
    # 2. CONTRATO
    # ═══════════════════════════════════════════════════════════════
    cont = dados.get("contrato") or {}
    adm = cont.get("admissao")
    dem = cont.get("demissao")
    ajz = cont.get("ajuizamento") or proc.get("ajuizamento")

    if not adm:
        res.erros.append(_erro("contrato", "admissao",
            "Data de admissão ausente. Obrigatória para o cálculo."))
    if not dem:
        res.erros.append(_erro("contrato", "demissao",
            "Data de demissão ausente. Obrigatória para o cálculo."))
    if not ajz:
        res.erros.append(_erro("contrato", "ajuizamento",
            "Data de ajuizamento ausente. Obrigatória — sem ela a Fase 1 falha."))

    # Coerências de datas
    d_adm = _parse_data(adm)
    d_dem = _parse_data(dem)
    d_ajz = _parse_data(ajz)

    if d_adm and d_dem and d_adm > d_dem:
        res.erros.append(_erro("contrato", "datas",
            f"Admissão ({adm}) é POSTERIOR à demissão ({dem}). Datas incoerentes."))
    if d_dem and d_ajz and d_ajz < d_dem:
        res.avisos.append(_aviso("contrato", "ajuizamento",
            f"Ajuizamento ({ajz}) é ANTERIOR à demissão ({dem}). "
            "Possível em ações em curso de contrato; verificar."))

    # Salário
    if not cont.get("salario_base") and not cont.get("ultimo_salario"):
        # Histórico salarial pode suprir, mas é raro vir só por lá
        hs = dados.get("historico_salarial") or []
        if not hs:
            res.erros.append(_erro("contrato", "salario_base",
                "Salário não informado e sem histórico salarial. Sem isso a "
                "automação preenche zero e a Liquidação falha."))

    # Aviso prévio
    avp = dados.get("aviso_previo") or {}
    if avp.get("tipo") == "Calculado" and d_adm and d_dem:
        meses = (d_dem.year - d_adm.year) * 12 + (d_dem.month - d_adm.month)
        if meses < 12:
            res.avisos.append(_aviso("aviso_previo", "tipo",
                f"Aviso prévio Calculado (Lei 12.506) requer ≥ 1 ano de contrato. "
                f"Contrato tem {meses} meses; PJE-Calc ainda calcula o mínimo de 30 dias."))

    # Prescrição quinquenal só se contrato > 5 anos do ajuizamento
    presc = dados.get("prescricao") or {}
    if presc.get("quinquenal") and d_adm and d_ajz:
        dias = (d_ajz - d_adm).days
        if dias < 5 * 365:
            res.avisos.append(_aviso("prescricao", "quinquenal",
                f"Prescrição quinquenal marcada mas contrato tem menos de 5 anos. "
                "PJE-Calc rejeita; a automação desmarca automaticamente."))

    # ═══════════════════════════════════════════════════════════════
    # 3. HISTÓRICO SALARIAL
    # ═══════════════════════════════════════════════════════════════
    historico = dados.get("historico_salarial") or []
    nomes_historicos_disponiveis = set(_HISTORICOS_DEFAULT)  # 3 defaults sempre

    for i, h in enumerate(historico):
        prefix = f"historico_salarial[{i}]"
        nome = (h.get("nome") or "").strip()
        if not nome:
            res.erros.append(_erro(prefix, "nome",
                f"Histórico salarial #{i+1} sem nome. Obrigatório."))
            continue
        nomes_historicos_disponiveis.add(_norm_nome_hist(nome))

        valor = h.get("valor")
        try:
            valor_f = float(str(valor).replace(",", ".")) if valor else 0
        except (ValueError, TypeError):
            valor_f = 0
        if valor_f <= 0:
            res.avisos.append(_aviso(prefix, "valor",
                f"Histórico '{nome}' sem valor (R$ 0,00). Verbas baseadas nele "
                "calcularão zero."))

        di = _parse_data(h.get("data_inicio"))
        df = _parse_data(h.get("data_fim"))
        if di and df and di > df:
            res.erros.append(_erro(prefix, "datas",
                f"Histórico '{nome}': data_inicio ({h.get('data_inicio')}) "
                f"posterior à data_fim ({h.get('data_fim')})."))

    # ═══════════════════════════════════════════════════════════════
    # 4. VERBAS
    # ═══════════════════════════════════════════════════════════════
    if verbas_mapeadas:
        todas_verbas = (
            (verbas_mapeadas.get("predefinidas") or [])
            + (verbas_mapeadas.get("personalizadas") or [])
        )
        nomes_principais = {
            (v.get("nome_pjecalc") or v.get("nome_sentenca") or "").upper().strip()
            for v in todas_verbas
            if (v.get("tipo") or "").lower() != "reflexa" and not v.get("eh_reflexa")
        }

        for i, v in enumerate(todas_verbas):
            nome = v.get("nome_pjecalc") or v.get("nome_sentenca") or f"verba#{i}"
            prefix = f"verba[{i}] '{nome[:30]}'"

            # Verba reflexa precisa apontar para uma principal existente
            if (v.get("tipo") or "").lower() == "reflexa" or v.get("eh_reflexa"):
                ref = (v.get("verba_principal_ref") or "").upper().strip()
                if ref and ref not in nomes_principais:
                    # Match flexível em 3 níveis (ordem de relaxamento):
                    #   1. Substring direta (ex: "HORAS EXTRAS" in "HORAS EXTRAS 50%")
                    #   2. Tokens significativos (ignorando complementos entre parênteses
                    #      e variações singular/plural — DIFERENÇA ↔ DIFERENÇAS)
                    #   3. Sem match em nenhum nível → ERRO bloqueante
                    def _norma(s: str) -> str:
                        # Normaliza para comparação: upper, sem acentos/cedilhas,
                        # remove parênteses, remove plural/feminino simples, remove
                        # palavras curtas e stopwords.
                        import re as _re
                        s = (s or "").upper()
                        for a, b in [("Á","A"),("É","E"),("Í","I"),("Ó","O"),("Ú","U"),
                                     ("Â","A"),("Ê","E"),("Ô","O"),("Ã","A"),("Õ","O"),
                                     ("Ç","C")]:
                            s = s.replace(a, b)
                        s = _re.sub(r"\([^)]*\)", " ", s)  # remove parênteses
                        s = _re.sub(r"[^\w\s]", " ", s)
                        toks = []
                        for w in s.split():
                            if len(w) < 4 or w in {"PARA", "COM", "SOBRE", "DOS", "DAS"}:
                                continue
                            # Plural simples: termina em S e palavra > 4
                            if len(w) > 4 and w.endswith("S"):
                                w = w[:-1]
                            # Feminino plural: ais → al (SALARIAIS → SALARIAL → SALARIAI)
                            if w.endswith("I") and len(w) > 5:
                                w = w[:-1] + "L"
                            toks.append(w)
                        return " ".join(sorted(set(toks)))
                    _ref_norm = _norma(ref)
                    match_fuzzy = False
                    for p in nomes_principais:
                        if ref in p or p in ref:
                            match_fuzzy = True
                            break
                        _p_norm = _norma(p)
                        # Fuzzy por similaridade de strings normalizadas
                        if _ref_norm and _p_norm:
                            from difflib import SequenceMatcher
                            ratio = SequenceMatcher(None, _ref_norm, _p_norm).ratio()
                            # Match se ratio ≥ 0.7 OU principais tokens contidos na ref
                            if ratio >= 0.7 or all(
                                t in _ref_norm for t in _p_norm.split() if len(t) >= 5
                            ):
                                match_fuzzy = True
                                break
                    if not match_fuzzy:
                        # ERRO BLOQUEANTE: PJE-Calc gera pendência "verba reflexa
                        # sem principal" e impede Liquidar.
                        res.erros.append(_erro(prefix, "verba_principal_ref",
                            f"Verba reflexa aponta para '{ref}' que NÃO está cadastrada "
                            f"como principal. Adicione a principal primeiro OU remova "
                            f"esta reflexa. Disponíveis: {sorted(nomes_principais)[:5]}..."))
                continue

            # Verba principal: validar bases_calculo
            bases = v.get("bases_calculo") or []
            if not bases:
                res.avisos.append(_aviso(prefix, "bases_calculo",
                    "Verba sem bases_calculo definidas. Defaults serão aplicados; "
                    "considere revisar."))
            for j, base in enumerate(bases):
                tipo_base = (base.get("tipo_base") or "").upper()
                # Histórico subtipo deve existir
                if tipo_base == "HISTORICO_SALARIAL":
                    subt = base.get("historico_subtipo")
                    if subt:
                        subt_norm = _norm_nome_hist(subt)
                        if subt_norm not in {_norm_nome_hist(n) for n in nomes_historicos_disponiveis}:
                            res.erros.append(_erro(prefix, f"bases_calculo[{j}].historico_subtipo",
                                f"Verba '{nome}' base #{j+1} aponta para histórico "
                                f"'{subt}' que NÃO existe. Disponíveis: "
                                f"{sorted({n for n in nomes_historicos_disponiveis})}. "
                                "Liquidação falhará com 'Falta selecionar Histórico Salarial'."))
                # SALARIO_DA_CATEGORIA → aviso (tabela admin-only)
                if tipo_base == "SALARIO_DA_CATEGORIA":
                    res.avisos.append(_aviso(prefix, f"bases_calculo[{j}].tipo_base",
                        "Base SALARIO_DA_CATEGORIA (Piso) requer cadastro prévio na "
                        "Tabelas > Pisos Salariais (admin-only). Verificar antes de Liquidar."))

    # ═══════════════════════════════════════════════════════════════
    # 5. HONORÁRIOS
    # ═══════════════════════════════════════════════════════════════
    honorarios = dados.get("honorarios") or []
    if not isinstance(honorarios, list):
        honorarios = [honorarios] if honorarios else []
    for i, h in enumerate(honorarios):
        prefix = f"honorarios[{i}]"
        if not h.get("devedor"):
            res.erros.append(_erro(prefix, "devedor",
                f"Honorário #{i+1} sem devedor. Obrigatório (RECLAMANTE/RECLAMADO)."))
        if h.get("tipo_valor") == "CALCULADO" and not h.get("percentual"):
            res.erros.append(_erro(prefix, "percentual",
                f"Honorário #{i+1} é CALCULADO mas sem percentual. Obrigatório."))
        if h.get("tipo_valor") == "INFORMADO" and not h.get("valor_informado"):
            res.erros.append(_erro(prefix, "valor_informado",
                f"Honorário #{i+1} é INFORMADO mas sem valor_informado. Obrigatório."))

    return res


# ── Validações utilitárias ────────────────────────────────────────────────────

def _validar_cpf(cpf: str) -> bool:
    """Valida CPF pelo algoritmo de DV (módulo 11)."""
    cpf = re.sub(r"\D", "", cpf)
    if len(cpf) != 11 or cpf == cpf[0] * 11:
        return False
    try:
        # 1º DV
        soma = sum(int(cpf[i]) * (10 - i) for i in range(9))
        dv1 = (soma * 10) % 11
        if dv1 == 10:
            dv1 = 0
        if int(cpf[9]) != dv1:
            return False
        # 2º DV
        soma = sum(int(cpf[i]) * (11 - i) for i in range(10))
        dv2 = (soma * 10) % 11
        if dv2 == 10:
            dv2 = 0
        return int(cpf[10]) == dv2
    except (ValueError, IndexError):
        return False


def _validar_cnpj(cnpj: str) -> bool:
    """Valida CNPJ pelo algoritmo de DV (módulo 11 com pesos diferentes)."""
    cnpj = re.sub(r"\D", "", cnpj)
    if len(cnpj) != 14 or cnpj == cnpj[0] * 14:
        return False
    try:
        # 1º DV (pesos 5,4,3,2,9,8,7,6,5,4,3,2)
        pesos1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
        soma = sum(int(cnpj[i]) * pesos1[i] for i in range(12))
        dv1 = soma % 11
        dv1 = 0 if dv1 < 2 else 11 - dv1
        if int(cnpj[12]) != dv1:
            return False
        # 2º DV (pesos 6,5,4,3,2,9,8,7,6,5,4,3,2)
        pesos2 = [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
        soma = sum(int(cnpj[i]) * pesos2[i] for i in range(13))
        dv2 = soma % 11
        dv2 = 0 if dv2 < 2 else 11 - dv2
        return int(cnpj[13]) == dv2
    except (ValueError, IndexError):
        return False
