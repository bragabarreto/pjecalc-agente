# modules/document_collector.py — Coleta de Documentos e Informações Auxiliares
# Manual Técnico PJE-Calc, Seção 4

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from modules.ingestion import normalizar_valor, normalizar_data


# ── Mapeamento de documentos por tipo de verba (Manual, Seção 4.1) ────────────

DOCUMENTOS_POR_VERBA: dict[str, dict[str, Any]] = {
    "Horas Extras": {
        "nome": "Cartão de Ponto",
        "formatos": [".xlsx", ".csv", ".pdf", ".jpg", ".png"],
        "obrigatorio": False,
        "uso_pjecalc": "Importar na página Cartão de Ponto; usar como Divisor e/ou Quantidade",
    },
    "Adicional Noturno": {
        "nome": "Cartão de Ponto",
        "formatos": [".xlsx", ".csv", ".pdf", ".jpg", ".png"],
        "obrigatorio": False,
        "uso_pjecalc": "Importar na página Cartão de Ponto",
    },
    "Histórico Salarial": {
        "nome": "Contracheques ou TRCT",
        "formatos": [".pdf", ".jpg", ".png"],
        "obrigatorio": False,
        "uso_pjecalc": "Lançar mês a mês na página Histórico Salarial (Base Informada)",
    },
    "FGTS": {
        "nome": "Extrato FGTS (FGTS Digital ou Caixa Econômica)",
        "formatos": [".pdf"],
        "obrigatorio": False,
        "uso_pjecalc": "Verificar valores já recolhidos para abatimento",
    },
    "Aviso Prévio": {
        "nome": "Cálculo do prazo (Lei 12.506/2011)",
        "formatos": [],
        "obrigatorio": False,
        "uso_pjecalc": "Definir campo Prazo do Aviso Prévio: Calculado / Informado / Não Apurar",
    },
    "Salário-Família": {
        "nome": "Certidão de Nascimento / Número de Dependentes",
        "formatos": [],
        "obrigatorio": False,
        "uso_pjecalc": "Informar na página Salário-Família",
    },
    "Contribuição Social": {
        "nome": "Tabela de alíquotas INSS e salários de contribuição",
        "formatos": [],
        "obrigatorio": False,
        "uso_pjecalc": "Configurar na página Contribuição Social",
    },
    "Imposto de Renda": {
        "nome": "Quantidade de meses tributáveis e deduções",
        "formatos": [],
        "obrigatorio": False,
        "uso_pjecalc": "Preencher página Imposto de Renda",
    },
    "Férias": {
        "nome": "Período de gozo efetivo e abonos concedidos",
        "formatos": [],
        "obrigatorio": False,
        "uso_pjecalc": "Confirmar Situação, Dobra e Período de Gozo na página Férias",
    },
    "CCT/ACT": {
        "nome": "Convenção Coletiva de Trabalho",
        "formatos": [".pdf"],
        "obrigatorio": False,
        "uso_pjecalc": "Verificar pisos salariais, adicionais e outras cláusulas aplicáveis",
    },
    "Pensão Alimentícia": {
        "nome": "Percentual e base fixados na sentença",
        "formatos": [],
        "obrigatorio": False,
        "uso_pjecalc": "Preencher página Pensão Alimentícia",
    },
    "Previdência Privada": {
        "nome": "Regulamento do plano e alíquota",
        "formatos": [".pdf"],
        "obrigatorio": False,
        "uso_pjecalc": "Preencher página Previdência Privada",
    },
}


# ── Perguntas padrão por campo ausente (Manual, Seção 4.2) ───────────────────

PERGUNTAS_PADRAO: dict[str, dict[str, Any]] = {
    "contrato.admissao": {
        "campo": "Data de Admissão",
        "tela_pjecalc": "Parâmetros do Cálculo",
        "tipo": "data",
        "instrucao": "Informe a data de admissão no formato DD/MM/AAAA:",
    },
    "contrato.demissao": {
        "campo": "Data de Demissão",
        "tela_pjecalc": "Parâmetros do Cálculo",
        "tipo": "data",
        "instrucao": "Informe a data de demissão no formato DD/MM/AAAA:",
    },
    "contrato.ajuizamento": {
        "campo": "Data de Ajuizamento",
        "tela_pjecalc": "Parâmetros do Cálculo",
        "tipo": "data",
        "instrucao": "Informe a data de ajuizamento da ação no formato DD/MM/AAAA:",
    },
    "contrato.maior_remuneracao": {
        "campo": "Maior Remuneração",
        "tela_pjecalc": "Parâmetros do Cálculo",
        "tipo": "valor",
        "instrucao": "Informe a maior remuneração mensal do trabalhador (ex: 3500,00):",
    },
    "contrato.carga_horaria": {
        "campo": "Carga Horária Padrão",
        "tela_pjecalc": "Parâmetros do Cálculo",
        "tipo": "inteiro",
        "instrucao": "Informe a carga horária mensal em horas (padrão: 220):",
        "valor_sugerido": "220",
    },
    "processo.estado": {
        "campo": "Estado (UF)",
        "tela_pjecalc": "Parâmetros do Cálculo",
        "tipo": "uf",
        "instrucao": "Informe a sigla do estado da Vara do Trabalho (ex: SP, MG, RJ):",
    },
    "processo.municipio": {
        "campo": "Município",
        "tela_pjecalc": "Parâmetros do Cálculo",
        "tipo": "texto",
        "instrucao": "Informe o município da Vara do Trabalho:",
    },
    "aviso_previo.tipo": {
        "campo": "Prazo do Aviso Prévio",
        "tela_pjecalc": "Parâmetros do Cálculo",
        "tipo": "opcoes",
        "instrucao": "Qual opção para o Aviso Prévio?",
        "opcoes": [
            "1 — Calculado automaticamente (Lei 12.506/2011)",
            "2 — Informado manualmente (especificar dias)",
            "3 — Não Apurar",
        ],
    },
    "fgts.aliquota": {
        "campo": "Alíquota FGTS",
        "tela_pjecalc": "FGTS",
        "tipo": "percentual",
        "instrucao": "Informe a alíquota de FGTS (padrão: 8%; para aprendiz: 2%):",
        "valor_sugerido": "8",
    },
}


# ── Funções públicas ──────────────────────────────────────────────────────────

def identificar_documentos_necessarios(
    verbas_mapeadas: dict[str, Any],
    dados_extraidos: dict[str, Any],
) -> list[dict[str, Any]]:
    """
    Analisa as verbas e os dados extraídos para identificar
    quais documentos adicionais o usuário deve fornecer.
    """
    documentos_necessarios: list[dict[str, Any]] = []
    verbas_vistas: set[str] = set()

    todas_verbas = (
        verbas_mapeadas.get("predefinidas", [])
        + verbas_mapeadas.get("personalizadas", [])
    )

    for verba in todas_verbas:
        nome = verba.get("nome_pjecalc", verba.get("nome_sentenca", ""))

        # Horas Extras / Adicional Noturno → Cartão de Ponto
        if "Horas Extras" in nome or "Adicional Noturno" in nome:
            if "cartao_ponto" not in verbas_vistas:
                verbas_vistas.add("cartao_ponto")
                doc = DOCUMENTOS_POR_VERBA.get("Horas Extras", {}).copy()
                doc["verba"] = nome
                documentos_necessarios.append(doc)

        # Histórico Salarial variável → contracheques
        base = verba.get("base_calculo", "")
        if base == "Historico Salarial" and "historico" not in verbas_vistas:
            verbas_vistas.add("historico")
            doc = DOCUMENTOS_POR_VERBA.get("Histórico Salarial", {}).copy()
            documentos_necessarios.append(doc)

    # FGTS → extrato se multa 40%
    if dados_extraidos.get("fgts", {}).get("multa_40"):
        doc = DOCUMENTOS_POR_VERBA.get("FGTS", {}).copy()
        doc["motivo"] = "Necessário para verificar recolhimentos e calcular multa 40%"
        documentos_necessarios.append(doc)

    return documentos_necessarios


def processar_cartao_ponto(caminho: str | Path) -> dict[str, Any]:
    """
    Extrai dados de cartão de ponto para uso no PJE-Calc.
    Suporta .xlsx, .csv e PDF/imagem (via OCR).

    Retorna: {"colunas": [...], "linhas": [...], "alertas": [...]}
    """
    caminho = Path(caminho)
    sufixo = caminho.suffix.lower()
    alertas: list[str] = []

    if sufixo in (".xlsx", ".xls"):
        return _processar_cartao_excel(caminho, alertas)
    elif sufixo == ".csv":
        return _processar_cartao_csv(caminho, alertas)
    elif sufixo == ".pdf":
        return _processar_cartao_pdf(caminho, alertas)
    else:
        alertas.append(f"Formato {sufixo} não suportado para cartão de ponto.")
        return {"colunas": [], "linhas": [], "alertas": alertas}


def processar_contracheques(caminho: str | Path) -> list[dict[str, Any]]:
    """
    Extrai histórico salarial de contracheques em PDF.
    Retorna lista de {'mes_ano': 'MM/AAAA', 'valor': float}.
    """
    import pdfplumber

    caminho = Path(caminho)
    historico: list[dict[str, Any]] = []

    with pdfplumber.open(str(caminho)) as pdf:
        for pagina in pdf.pages:
            texto = pagina.extract_text() or ""
            # Buscar padrão: mês/ano + valor
            for m in re.finditer(
                r"(\d{2}/\d{4})[^\n]*?R?\$?\s*([\d.]+,\d{2})", texto
            ):
                mes_ano = m.group(1)
                try:
                    valor = normalizar_valor(m.group(2))
                    historico.append({"mes_ano": mes_ano, "valor": valor})
                except ValueError:
                    pass

    return historico


def processar_extrato_fgts(caminho: str | Path) -> dict[str, Any]:
    """
    Extrai saldo e depósitos do extrato FGTS em PDF.
    """
    import pdfplumber

    caminho = Path(caminho)
    depositos: list[dict[str, Any]] = []
    saldo_total = 0.0

    with pdfplumber.open(str(caminho)) as pdf:
        for pagina in pdf.pages:
            texto = pagina.extract_text() or ""

            # Saldo total
            m = re.search(r"saldo\s+total[:\s]+([\d.]+,\d{2})", texto, re.IGNORECASE)
            if m:
                try:
                    saldo_total = normalizar_valor(m.group(1))
                except ValueError:
                    pass

            # Depósitos mensais
            for m in re.finditer(
                r"(\d{2}/\d{4})[^\n]*?([\d.]+,\d{2})", texto
            ):
                try:
                    depositos.append({
                        "mes_ano": m.group(1),
                        "valor": normalizar_valor(m.group(2)),
                    })
                except ValueError:
                    pass

    return {"saldo_total": saldo_total, "depositos": depositos}


def formatar_pergunta_dado_ausente(campo: str, contexto: dict[str, Any] | None = None) -> str:
    """
    Formata a pergunta ao usuário para campo ausente.
    Retorna string formatada conforme modelo do Manual, Seção 4.2.
    """
    config = PERGUNTAS_PADRAO.get(campo, {})
    nome_campo = config.get("campo", campo)
    tela = config.get("tela_pjecalc", "—")
    instrucao = config.get("instrucao", f"Informe o valor para: {campo}")
    opcoes = config.get("opcoes", [])
    sugestao = config.get("valor_sugerido", "")

    linhas = [
        "╔" + "═" * 62 + "╗",
        f"║  INFORMAÇÃO NECESSÁRIA — {nome_campo:<37}║",
        "╠" + "═" * 62 + "╣",
        f"║  Tela PJE-Calc : {tela:<44}║",
        "║" + " " * 62 + "║",
        f"║  {instrucao:<60}║",
    ]

    if sugestao:
        linhas.append(f"║  (sugestão: {sugestao})<{49 - len(sugestao)}║")

    if opcoes:
        linhas.append("║" + " " * 62 + "║")
        for opcao in opcoes:
            linhas.append(f"║  {opcao:<60}║")

    linhas += [
        "║" + " " * 62 + "║",
        "║  Sua resposta: ___" + " " * 43 + "║",
        "╚" + "═" * 62 + "╝",
    ]

    return "\n".join(linhas)


def validar_resposta_usuario(campo: str, resposta: str) -> tuple[bool, Any, str]:
    """
    Valida e converte a resposta do usuário conforme o tipo do campo.

    Retorna: (valido: bool, valor_convertido, mensagem_erro)
    """
    config = PERGUNTAS_PADRAO.get(campo, {})
    tipo = config.get("tipo", "texto")

    resposta = resposta.strip()

    if tipo == "data":
        data = normalizar_data(resposta)
        if data:
            return True, data, ""
        return False, None, "Data inválida. Use o formato DD/MM/AAAA."

    elif tipo == "valor":
        try:
            valor = normalizar_valor(resposta)
            if valor < 0:
                return False, None, "O valor não pode ser negativo."
            return True, valor, ""
        except ValueError:
            return False, None, "Valor inválido. Use formato numérico (ex: 3500,00)."

    elif tipo == "inteiro":
        try:
            valor = int(resposta)
            if valor <= 0:
                return False, None, "O valor deve ser maior que zero."
            return True, valor, ""
        except ValueError:
            return False, None, "Digite um número inteiro (ex: 220)."

    elif tipo == "percentual":
        try:
            valor = float(resposta.replace(",", ".").replace("%", ""))
            return True, valor / 100, ""
        except ValueError:
            return False, None, "Percentual inválido. Digite apenas o número (ex: 8)."

    elif tipo == "uf":
        if re.match(r"^[A-Za-z]{2}$", resposta):
            return True, resposta.upper(), ""
        return False, None, "UF inválida. Digite as 2 letras do estado (ex: SP)."

    elif tipo == "opcoes":
        opcoes = config.get("opcoes", [])
        try:
            idx = int(resposta) - 1
            if 0 <= idx < len(opcoes):
                return True, opcoes[idx], ""
        except ValueError:
            pass
        return False, None, f"Opção inválida. Escolha entre 1 e {len(opcoes)}."

    else:
        if resposta:
            return True, resposta, ""
        return False, None, "O campo não pode estar vazio."


# ── Processamento de documentos internos ─────────────────────────────────────

def _processar_cartao_excel(caminho: Path, alertas: list[str]) -> dict[str, Any]:
    try:
        import openpyxl
    except ImportError:
        alertas.append("Instale openpyxl para processar planilhas: pip install openpyxl")
        return {"colunas": [], "linhas": [], "alertas": alertas}

    wb = openpyxl.load_workbook(str(caminho), read_only=True, data_only=True)
    ws = wb.active

    linhas: list[list[Any]] = []
    colunas: list[str] = []

    for i, row in enumerate(ws.iter_rows(values_only=True)):
        if i == 0:
            colunas = [str(c) if c is not None else f"Col{j}" for j, c in enumerate(row)]
        else:
            if any(c is not None for c in row):
                linhas.append(list(row))

    wb.close()
    return {"colunas": colunas, "linhas": linhas, "alertas": alertas}


def _processar_cartao_csv(caminho: Path, alertas: list[str]) -> dict[str, Any]:
    try:
        import csv
        import chardet

        raw = caminho.read_bytes()
        enc = chardet.detect(raw).get("encoding", "utf-8")
        conteudo = raw.decode(enc, errors="replace")

        leitor = csv.reader(conteudo.splitlines())
        linhas_raw = list(leitor)

        if not linhas_raw:
            return {"colunas": [], "linhas": [], "alertas": alertas}

        colunas = linhas_raw[0]
        linhas = linhas_raw[1:]
        return {"colunas": colunas, "linhas": linhas, "alertas": alertas}

    except Exception as e:
        alertas.append(f"Erro ao processar CSV: {e}")
        return {"colunas": [], "linhas": [], "alertas": alertas}


def _processar_cartao_pdf(caminho: Path, alertas: list[str]) -> dict[str, Any]:
    """Tenta extrair tabela de cartão de ponto de PDF via pdfplumber."""
    try:
        import pdfplumber
    except ImportError:
        alertas.append("Instale pdfplumber: pip install pdfplumber")
        return {"colunas": [], "linhas": [], "alertas": alertas}

    todas_linhas: list[list[Any]] = []
    colunas: list[str] = []

    with pdfplumber.open(str(caminho)) as pdf:
        for pagina in pdf.pages:
            tabelas = pagina.extract_tables()
            for tabela in tabelas:
                if tabela and not colunas:
                    colunas = [str(c) for c in tabela[0]]
                    todas_linhas.extend(tabela[1:])
                elif tabela:
                    todas_linhas.extend(tabela)

    if not todas_linhas:
        alertas.append(
            "Não foi possível extrair tabela do PDF do cartão de ponto. "
            "Considere fornecer em formato .xlsx ou .csv."
        )

    return {"colunas": colunas, "linhas": todas_linhas, "alertas": alertas}
