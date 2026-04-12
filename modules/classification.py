# modules/classification.py — Classificação e Mapeamento de Verbas para o PJE-Calc
# Manual Técnico PJE-Calc, Seção 3

from __future__ import annotations

import logging
from typing import Any

import anthropic

from config import ANTHROPIC_API_KEY, CLAUDE_MODEL, CLAUDE_EXTRACTION_TEMPERATURE


# ── Tabela de verbas pré-definidas no PJE-Calc (Manual, Seção 3.1) ────────────
# Formato: "nome_sentenca_normalizado" → configuração PJE-Calc

VERBAS_PREDEFINIDAS: dict[str, dict[str, Any]] = {
    # Chave: nome normalizado (minúsculo, sem acento)
    # ── Nomes Expresso = EXATAMENTE como aparecem na página verbas-para-calculo.jsf ──
    # Confirmado via screenshot da página Expresso do PJE-Calc v2.15.1
    "saldo de salario": {
        "nome_pjecalc": "SALDO DE SALÁRIO",
        "caracteristica": "Comum",
        "ocorrencia": "Desligamento",
        "incidencia_fgts": True,
        "incidencia_inss": True,
        "incidencia_ir": True,
        "tipo": "Principal",
        "compor_principal": True,
        "campos_criticos": ["maior_remuneracao", "periodo"],
    },
    "aviso previo indenizado": {
        "nome_pjecalc": "AVISO PRÉVIO",
        "caracteristica": "Aviso Previo",
        "ocorrencia": "Desligamento",
        "incidencia_fgts": True,
        "incidencia_inss": True,
        "incidencia_ir": True,
        "tipo": "Principal",
        "compor_principal": True,
        "campos_criticos": ["prazo_aviso_previo", "maior_remuneracao"],
    },
    "aviso previo": {
        "nome_pjecalc": "AVISO PRÉVIO",
        "caracteristica": "Aviso Previo",
        "ocorrencia": "Desligamento",
        "incidencia_fgts": True,
        "incidencia_inss": True,
        "incidencia_ir": True,
        "tipo": "Principal",
        "compor_principal": True,
        "campos_criticos": ["prazo_aviso_previo", "maior_remuneracao"],
    },
    "13 salario proporcional": {
        "nome_pjecalc": "13º SALÁRIO",
        "caracteristica": "13o Salario",
        "ocorrencia": "Desligamento",
        "incidencia_fgts": True,
        "incidencia_inss": True,
        "incidencia_ir": True,
        "tipo": "Principal",
        "compor_principal": True,
        "campos_criticos": ["avos", "base_calculo"],
    },
    "decimo terceiro salario proporcional": {
        "nome_pjecalc": "13º SALÁRIO",
        "caracteristica": "13o Salario",
        "ocorrencia": "Desligamento",
        "incidencia_fgts": True,
        "incidencia_inss": True,
        "incidencia_ir": True,
        "tipo": "Principal",
        "compor_principal": True,
        "campos_criticos": ["avos", "base_calculo"],
    },
    "13 salario": {
        "nome_pjecalc": "13º SALÁRIO",
        "caracteristica": "13o Salario",
        "ocorrencia": "Desligamento",
        "incidencia_fgts": True,
        "incidencia_inss": True,
        "incidencia_ir": True,
        "tipo": "Principal",
        "compor_principal": True,
        "campos_criticos": ["avos", "base_calculo"],
    },
    "decimo terceiro salario": {
        "nome_pjecalc": "13º SALÁRIO",
        "caracteristica": "13o Salario",
        "ocorrencia": "Desligamento",
        "incidencia_fgts": True,
        "incidencia_inss": True,
        "incidencia_ir": True,
        "tipo": "Principal",
        "compor_principal": True,
        "campos_criticos": ["avos", "base_calculo"],
    },
    "ferias proporcionais": {
        "nome_pjecalc": "FÉRIAS + 1/3",
        "caracteristica": "Ferias",
        "ocorrencia": "Periodo Aquisitivo",
        "incidencia_fgts": False,
        "incidencia_inss": True,
        "incidencia_ir": True,
        "tipo": "Principal",
        "compor_principal": True,
        "campos_criticos": ["avos", "situacao", "dobra"],
    },
    "ferias vencidas": {
        "nome_pjecalc": "FÉRIAS + 1/3",
        "caracteristica": "Ferias",
        "ocorrencia": "Periodo Aquisitivo",
        "incidencia_fgts": False,
        "incidencia_inss": True,
        "incidencia_ir": True,
        "tipo": "Principal",
        "compor_principal": True,
        "campos_criticos": ["avos", "situacao", "dobra"],
    },
    "ferias": {
        "nome_pjecalc": "FÉRIAS + 1/3",
        "caracteristica": "Ferias",
        "ocorrencia": "Periodo Aquisitivo",
        "incidencia_fgts": False,
        "incidencia_inss": True,
        "incidencia_ir": True,
        "tipo": "Principal",
        "compor_principal": True,
        "campos_criticos": ["avos", "situacao", "dobra"],
    },
    # Aliases para variantes comuns de férias que a extração pode gerar
    "ferias proporcionais + 1/3": {
        "nome_pjecalc": "FÉRIAS + 1/3",
        "caracteristica": "Ferias",
        "ocorrencia": "Periodo Aquisitivo",
        "incidencia_fgts": False,
        "incidencia_inss": True,
        "incidencia_ir": True,
        "tipo": "Principal",
        "compor_principal": True,
        "campos_criticos": ["avos", "situacao", "dobra"],
    },
    "ferias vencidas + 1/3": {
        "nome_pjecalc": "FÉRIAS + 1/3",
        "caracteristica": "Ferias",
        "ocorrencia": "Periodo Aquisitivo",
        "incidencia_fgts": False,
        "incidencia_inss": True,
        "incidencia_ir": True,
        "tipo": "Principal",
        "compor_principal": True,
        "campos_criticos": ["avos", "situacao", "dobra"],
    },
    "ferias + 1/3": {
        "nome_pjecalc": "FÉRIAS + 1/3",
        "caracteristica": "Ferias",
        "ocorrencia": "Periodo Aquisitivo",
        "incidencia_fgts": False,
        "incidencia_inss": True,
        "incidencia_ir": True,
        "tipo": "Principal",
        "compor_principal": True,
        "campos_criticos": ["avos", "situacao", "dobra"],
    },
    "horas extras": {
        "nome_pjecalc": "HORAS EXTRAS 50%",
        "caracteristica": "Comum",
        "ocorrencia": "Mensal",
        "incidencia_fgts": True,
        "incidencia_inss": True,
        "incidencia_ir": True,
        "tipo": "Principal",
        "compor_principal": True,
        "campos_criticos": ["percentual", "divisor", "periodo", "cartao_ponto"],
        "reflexas_tipicas": [
            "RSR sobre Horas Extras",
            "13º s/ Horas Extras",
            "Férias + 1/3 s/ Horas Extras",
        ],
    },
    "horas extras 50%": {
        "nome_pjecalc": "HORAS EXTRAS 50%",
        "caracteristica": "Comum",
        "ocorrencia": "Mensal",
        "incidencia_fgts": True,
        "incidencia_inss": True,
        "incidencia_ir": True,
        "tipo": "Principal",
        "compor_principal": True,
        "campos_criticos": ["percentual", "divisor", "periodo", "cartao_ponto"],
    },
    "horas extras 100%": {
        "nome_pjecalc": "HORAS EXTRAS 100%",
        "caracteristica": "Comum",
        "ocorrencia": "Mensal",
        "incidencia_fgts": True,
        "incidencia_inss": True,
        "incidencia_ir": True,
        "tipo": "Principal",
        "compor_principal": True,
        "campos_criticos": ["percentual", "divisor", "periodo", "cartao_ponto"],
    },
    "adicional de horas extras 50%": {
        "nome_pjecalc": "ADICIONAL DE HORAS EXTRAS 50%",
        "caracteristica": "Comum",
        "ocorrencia": "Mensal",
        "incidencia_fgts": True,
        "incidencia_inss": True,
        "incidencia_ir": True,
        "tipo": "Principal",
        "compor_principal": True,
        "campos_criticos": ["percentual", "divisor", "periodo", "cartao_ponto"],
    },
    "adicional noturno": {
        "nome_pjecalc": "ADICIONAL NOTURNO 20%",
        "caracteristica": "Comum",
        "ocorrencia": "Mensal",
        "incidencia_fgts": True,
        "incidencia_inss": True,
        "incidencia_ir": True,
        "tipo": "Principal",
        "compor_principal": True,
        "campos_criticos": ["percentual", "periodo"],
        "reflexas_tipicas": [
            "RSR sobre Adicional Noturno",
            "13º s/ Adicional Noturno",
            "Férias + 1/3 s/ Adicional Noturno",
        ],
    },
    "adicional noturno 20%": {
        "nome_pjecalc": "ADICIONAL NOTURNO 20%",
        "caracteristica": "Comum",
        "ocorrencia": "Mensal",
        "incidencia_fgts": True,
        "incidencia_inss": True,
        "incidencia_ir": True,
        "tipo": "Principal",
        "compor_principal": True,
        "campos_criticos": ["percentual", "periodo"],
    },
    "adicional de insalubridade": {
        "nome_pjecalc": "ADICIONAL DE INSALUBRIDADE 40%",
        "caracteristica": "Comum",
        "ocorrencia": "Mensal",
        "incidencia_fgts": True,
        "incidencia_inss": True,
        "incidencia_ir": True,
        "tipo": "Principal",
        "compor_principal": True,
        "campos_criticos": ["percentual", "base_calculo", "periodo"],
    },
    "adicional de insalubridade 40%": {
        "nome_pjecalc": "ADICIONAL DE INSALUBRIDADE 40%",
        "caracteristica": "Comum",
        "ocorrencia": "Mensal",
        "incidencia_fgts": True,
        "incidencia_inss": True,
        "incidencia_ir": True,
        "tipo": "Principal",
        "compor_principal": True,
        "campos_criticos": ["percentual", "base_calculo", "periodo"],
    },
    "adicional de insalubridade 20%": {
        "nome_pjecalc": "ADICIONAL DE INSALUBRIDADE 20%",
        "caracteristica": "Comum",
        "ocorrencia": "Mensal",
        "incidencia_fgts": True,
        "incidencia_inss": True,
        "incidencia_ir": True,
        "tipo": "Principal",
        "compor_principal": True,
        "campos_criticos": ["percentual", "base_calculo", "periodo"],
    },
    "adicional de insalubridade 10%": {
        "nome_pjecalc": "ADICIONAL DE INSALUBRIDADE 10%",
        "caracteristica": "Comum",
        "ocorrencia": "Mensal",
        "incidencia_fgts": True,
        "incidencia_inss": True,
        "incidencia_ir": True,
        "tipo": "Principal",
        "compor_principal": True,
        "campos_criticos": ["percentual", "base_calculo", "periodo"],
    },
    "adicional de periculosidade": {
        "nome_pjecalc": "ADICIONAL DE PERICULOSIDADE 30%",
        "caracteristica": "Comum",
        "ocorrencia": "Mensal",
        "incidencia_fgts": True,
        "incidencia_inss": True,
        "incidencia_ir": True,
        "tipo": "Principal",
        "compor_principal": True,
        "campos_criticos": ["periodo"],
    },
    "adicional de periculosidade 30%": {
        "nome_pjecalc": "ADICIONAL DE PERICULOSIDADE 30%",
        "caracteristica": "Comum",
        "ocorrencia": "Mensal",
        "incidencia_fgts": True,
        "incidencia_inss": True,
        "incidencia_ir": True,
        "tipo": "Principal",
        "compor_principal": True,
        "campos_criticos": ["periodo"],
    },
    "adicional de transferencia": {
        "nome_pjecalc": "ADICIONAL DE TRANSFERÊNCIA 25%",
        "caracteristica": "Comum",
        "ocorrencia": "Mensal",
        "incidencia_fgts": True,
        "incidencia_inss": True,
        "incidencia_ir": True,
        "tipo": "Principal",
        "compor_principal": True,
        "campos_criticos": ["percentual", "base_calculo", "periodo"],
    },
    "multa art 477": {
        "nome_pjecalc": "MULTA DO ARTIGO 477 DA CLT",
        "caracteristica": "Comum",
        "ocorrencia": "Desligamento",
        "incidencia_fgts": False,
        "incidencia_inss": False,
        "incidencia_ir": False,
        "tipo": "Principal",
        "compor_principal": True,
        "campos_criticos": ["maior_remuneracao"],
    },
    "multa do artigo 477 da clt": {
        "nome_pjecalc": "MULTA DO ARTIGO 477 DA CLT",
        "caracteristica": "Comum",
        "ocorrencia": "Desligamento",
        "incidencia_fgts": False,
        "incidencia_inss": False,
        "incidencia_ir": False,
        "tipo": "Principal",
        "compor_principal": True,
        "campos_criticos": ["maior_remuneracao"],
    },
    # ATENÇÃO: Multa Art. 467 CLT NÃO é verba Expresso nem Manual.
    # No PJE-Calc ela aparece em DOIS lugares:
    #   1. Aba FGTS: checkbox `multaDoArtigo467` (sub-checkbox da Multa 40%)
    #   2. Aba Verbas: reflexa automática sob cada verba principal
    #      (ex: "MULTA DO ARTIGO 467 DA CLT SOBRE SALDO DE SALÁRIO")
    # A extração deve mapear para fgts.multa_467 = true/false.
    # Mantido aqui APENAS para reconhecimento na classificação — o campo
    # `_apenas_fgts` impede criação como verba na automação.
    "multa art 467": {
        "nome_pjecalc": "Multa Art. 467 CLT",
        "caracteristica": "Comum",
        "ocorrencia": "Desligamento",
        "incidencia_fgts": False,
        "incidencia_inss": False,
        "incidencia_ir": False,
        "tipo": "Principal",
        "compor_principal": True,
        "campos_criticos": [],
        "_apenas_fgts": True,  # NÃO criar como verba — é checkbox FGTS + reflexa automática
    },
    "vale transporte": {
        "nome_pjecalc": "VALE TRANSPORTE",
        "caracteristica": "Comum",
        "ocorrencia": "Mensal",
        "incidencia_fgts": False,
        "incidencia_inss": False,
        "incidencia_ir": False,
        "tipo": "Principal",
        "compor_principal": True,
        "campos_criticos": ["linhas_onibus", "desconto_6"],
    },
    "salario familia": {
        "nome_pjecalc": "Salário-Família",
        "caracteristica": "Comum",
        "ocorrencia": "Mensal",
        "incidencia_fgts": False,
        "incidencia_inss": False,
        "incidencia_ir": False,
        "tipo": "Principal",
        "compor_principal": True,
        "campos_criticos": ["num_dependentes"],
    },
    "dano moral": {
        "nome_pjecalc": "INDENIZAÇÃO POR DANO MORAL",
        "caracteristica": "Comum",
        "ocorrencia": "Desligamento",
        "incidencia_fgts": False,
        "incidencia_inss": False,
        "incidencia_ir": False,
        "tipo": "Principal",
        "compor_principal": True,
        "lancamento": "Expresso",
        "campos_criticos": ["valor_informado"],
    },
    "danos morais": {
        "nome_pjecalc": "INDENIZAÇÃO POR DANO MORAL",
        "caracteristica": "Comum",
        "ocorrencia": "Desligamento",
        "incidencia_fgts": False,
        "incidencia_inss": False,
        "incidencia_ir": False,
        "tipo": "Principal",
        "compor_principal": True,
        "lancamento": "Expresso",
        "campos_criticos": ["valor_informado"],
    },
    "indenizacao por danos morais": {
        "nome_pjecalc": "INDENIZAÇÃO POR DANO MORAL",
        "caracteristica": "Comum",
        "ocorrencia": "Desligamento",
        "incidencia_fgts": False,
        "incidencia_inss": False,
        "incidencia_ir": False,
        "tipo": "Principal",
        "compor_principal": True,
        "lancamento": "Expresso",
        "campos_criticos": ["valor_informado"],
    },
    "indenizacao por dano moral": {
        "nome_pjecalc": "INDENIZAÇÃO POR DANO MORAL",
        "caracteristica": "Comum",
        "ocorrencia": "Desligamento",
        "incidencia_fgts": False,
        "incidencia_inss": False,
        "incidencia_ir": False,
        "tipo": "Principal",
        "compor_principal": True,
        "lancamento": "Expresso",
        "campos_criticos": ["valor_informado"],
    },
    "dano material": {
        "nome_pjecalc": "INDENIZAÇÃO POR DANO MATERIAL",
        "caracteristica": "Comum",
        "ocorrencia": "Desligamento",
        "incidencia_fgts": False,
        "incidencia_inss": False,
        "incidencia_ir": False,
        "tipo": "Principal",
        "compor_principal": True,
        "lancamento": "Expresso",
        "campos_criticos": ["valor_informado"],
    },
    "danos materiais": {
        "nome_pjecalc": "INDENIZAÇÃO POR DANO MATERIAL",
        "caracteristica": "Comum",
        "ocorrencia": "Desligamento",
        "incidencia_fgts": False,
        "incidencia_inss": False,
        "incidencia_ir": False,
        "tipo": "Principal",
        "compor_principal": True,
        "lancamento": "Expresso",
        "campos_criticos": ["valor_informado"],
    },
    "indenizacao por danos materiais": {
        "nome_pjecalc": "INDENIZAÇÃO POR DANO MATERIAL",
        "caracteristica": "Comum",
        "ocorrencia": "Desligamento",
        "incidencia_fgts": False,
        "incidencia_inss": False,
        "incidencia_ir": False,
        "tipo": "Principal",
        "compor_principal": True,
        "lancamento": "Expresso",
        "campos_criticos": ["valor_informado"],
    },
    # ── Verbas Expresso adicionais (completando 54/54 do PJE-Calc v2.15.1) ──
    "indenizacao pis": {
        "nome_pjecalc": "INDENIZAÇÃO PIS - ABONO SALARIAL",
        "caracteristica": "Comum",
        "ocorrencia": "Desligamento",
        "incidencia_fgts": False,
        "incidencia_inss": False,
        "incidencia_ir": False,
        "tipo": "Principal",
        "compor_principal": True,
        "lancamento": "Expresso",
        "campos_criticos": ["valor_informado"],
    },
    "abono salarial pis": {
        "nome_pjecalc": "INDENIZAÇÃO PIS - ABONO SALARIAL",
        "caracteristica": "Comum",
        "ocorrencia": "Desligamento",
        "incidencia_fgts": False,
        "incidencia_inss": False,
        "incidencia_ir": False,
        "tipo": "Principal",
        "compor_principal": True,
        "lancamento": "Expresso",
        "campos_criticos": ["valor_informado"],
    },
    "premio producao": {
        "nome_pjecalc": "PRÊMIO PRODUÇÃO",
        "caracteristica": "Comum",
        "ocorrencia": "Mensal",
        "incidencia_fgts": True,
        "incidencia_inss": True,
        "incidencia_ir": True,
        "tipo": "Principal",
        "compor_principal": True,
        "lancamento": "Expresso",
        "campos_criticos": [],
    },
    "premio produtividade": {
        "nome_pjecalc": "PRÊMIO PRODUÇÃO",
        "caracteristica": "Comum",
        "ocorrencia": "Mensal",
        "incidencia_fgts": True,
        "incidencia_inss": True,
        "incidencia_ir": True,
        "tipo": "Principal",
        "compor_principal": True,
        "lancamento": "Expresso",
        "campos_criticos": [],
    },
    "repouso semanal remunerado comissionista": {
        "nome_pjecalc": "REPOUSO SEMANAL REMUNERADO (COMISSIONISTA)",
        "caracteristica": "Comum",
        "ocorrencia": "Mensal",
        "incidencia_fgts": True,
        "incidencia_inss": True,
        "incidencia_ir": True,
        "tipo": "Principal",
        "compor_principal": True,
        "lancamento": "Expresso",
        "campos_criticos": [],
    },
    "rsr comissionista": {
        "nome_pjecalc": "REPOUSO SEMANAL REMUNERADO (COMISSIONISTA)",
        "caracteristica": "Comum",
        "ocorrencia": "Mensal",
        "incidencia_fgts": True,
        "incidencia_inss": True,
        "incidencia_ir": True,
        "tipo": "Principal",
        "compor_principal": True,
        "lancamento": "Expresso",
        "campos_criticos": [],
    },
    "dsr comissionista": {
        "nome_pjecalc": "REPOUSO SEMANAL REMUNERADO (COMISSIONISTA)",
        "caracteristica": "Comum",
        "ocorrencia": "Mensal",
        "incidencia_fgts": True,
        "incidencia_inss": True,
        "incidencia_ir": True,
        "tipo": "Principal",
        "compor_principal": True,
        "lancamento": "Expresso",
        "campos_criticos": [],
    },
    "restituicao de despesa": {
        "nome_pjecalc": "RESTITUIÇÃO / INDENIZAÇÃO DE DESPESA",
        "caracteristica": "Comum",
        "ocorrencia": "Desligamento",
        "incidencia_fgts": False,
        "incidencia_inss": False,
        "incidencia_ir": False,
        "tipo": "Principal",
        "compor_principal": True,
        "lancamento": "Expresso",
        "campos_criticos": ["valor_informado"],
    },
    "indenizacao de despesa": {
        "nome_pjecalc": "RESTITUIÇÃO / INDENIZAÇÃO DE DESPESA",
        "caracteristica": "Comum",
        "ocorrencia": "Desligamento",
        "incidencia_fgts": False,
        "incidencia_inss": False,
        "incidencia_ir": False,
        "tipo": "Principal",
        "compor_principal": True,
        "lancamento": "Expresso",
        "campos_criticos": ["valor_informado"],
    },
    "reembolso de despesas": {
        "nome_pjecalc": "RESTITUIÇÃO / INDENIZAÇÃO DE DESPESA",
        "caracteristica": "Comum",
        "ocorrencia": "Desligamento",
        "incidencia_fgts": False,
        "incidencia_inss": False,
        "incidencia_ir": False,
        "tipo": "Principal",
        "compor_principal": True,
        "lancamento": "Expresso",
        "campos_criticos": ["valor_informado"],
    },
    "saldo de empreitada": {
        "nome_pjecalc": "SALDO DE EMPREITADA",
        "caracteristica": "Comum",
        "ocorrencia": "Desligamento",
        "incidencia_fgts": True,
        "incidencia_inss": True,
        "incidencia_ir": True,
        "tipo": "Principal",
        "compor_principal": True,
        "lancamento": "Expresso",
        "campos_criticos": [],
    },
    "valor pago nao tributavel": {
        "nome_pjecalc": "VALOR PAGO - NÃO TRIBUTÁVEL",
        "caracteristica": "Comum",
        "ocorrencia": "Desligamento",
        "incidencia_fgts": False,
        "incidencia_inss": False,
        "incidencia_ir": False,
        "tipo": "Principal",
        "compor_principal": True,
        "lancamento": "Expresso",
        "campos_criticos": ["valor_informado"],
    },
    "valor pago tributavel": {
        "nome_pjecalc": "VALOR PAGO - TRIBUTÁVEL",
        "caracteristica": "Comum",
        "ocorrencia": "Desligamento",
        "incidencia_fgts": True,
        "incidencia_inss": True,
        "incidencia_ir": True,
        "tipo": "Principal",
        "compor_principal": True,
        "lancamento": "Expresso",
        "campos_criticos": ["valor_informado"],
    },
    "13 salario integral": {
        "nome_pjecalc": "13º SALÁRIO",
        "caracteristica": "13o Salario",
        "ocorrencia": "Dezembro",
        "incidencia_fgts": True,
        "incidencia_inss": True,
        "incidencia_ir": True,
        "tipo": "Principal",
        "compor_principal": True,
        "campos_criticos": ["base_calculo"],
    },
    "decimo terceiro salario integral": {
        "nome_pjecalc": "13º SALÁRIO",
        "caracteristica": "13o Salario",
        "ocorrencia": "Dezembro",
        "incidencia_fgts": True,
        "incidencia_inss": True,
        "incidencia_ir": True,
        "tipo": "Principal",
        "compor_principal": True,
        "campos_criticos": ["base_calculo"],
    },
    "adicional acumulo de funcao": {
        "nome_pjecalc": "GRATIFICAÇÃO DE FUNÇÃO",
        "caracteristica": "Comum",
        "ocorrencia": "Mensal",
        "incidencia_fgts": True,
        "incidencia_inss": True,
        "incidencia_ir": True,
        "tipo": "Principal",
        "compor_principal": True,
        "campos_criticos": ["percentual", "periodo"],
    },
    "adicional por acumulo de funcao": {
        "nome_pjecalc": "GRATIFICAÇÃO DE FUNÇÃO",
        "caracteristica": "Comum",
        "ocorrencia": "Mensal",
        "incidencia_fgts": True,
        "incidencia_inss": True,
        "incidencia_ir": True,
        "tipo": "Principal",
        "compor_principal": True,
        "campos_criticos": ["percentual", "periodo"],
    },
    "feriado em dobro": {
        "nome_pjecalc": "FERIADO EM DOBRO",
        "caracteristica": "Comum",
        "ocorrencia": "Mensal",
        "incidencia_fgts": True,
        "incidencia_inss": True,
        "incidencia_ir": True,
        "tipo": "Principal",
        "compor_principal": True,
        "campos_criticos": ["periodo"],
    },
    "feriado trabalhado em dobro": {
        "nome_pjecalc": "FERIADO EM DOBRO",
        "caracteristica": "Comum",
        "ocorrencia": "Mensal",
        "incidencia_fgts": True,
        "incidencia_inss": True,
        "incidencia_ir": True,
        "tipo": "Principal",
        "compor_principal": True,
        "campos_criticos": ["periodo"],
    },
    "feriados trabalhados em dobro": {
        "nome_pjecalc": "FERIADO EM DOBRO",
        "caracteristica": "Comum",
        "ocorrencia": "Mensal",
        "incidencia_fgts": True,
        "incidencia_inss": True,
        "incidencia_ir": True,
        "tipo": "Principal",
        "compor_principal": True,
        "campos_criticos": ["periodo"],
    },
    # ── Verbas Expresso adicionais (screenshot PJE-Calc v2.15.1) ──
    "intervalo intrajornada": {
        "nome_pjecalc": "INTERVALO INTRAJORNADA",
        "caracteristica": "Comum",
        "ocorrencia": "Mensal",
        "incidencia_fgts": True,
        "incidencia_inss": True,
        "incidencia_ir": True,
        "tipo": "Principal",
        "compor_principal": True,
        "campos_criticos": ["periodo", "cartao_ponto"],
    },
    "intervalo interjornadas": {
        "nome_pjecalc": "INTERVALO INTERJORNADAS",
        "caracteristica": "Comum",
        "ocorrencia": "Mensal",
        "incidencia_fgts": True,
        "incidencia_inss": True,
        "incidencia_ir": True,
        "tipo": "Principal",
        "compor_principal": True,
        "campos_criticos": ["periodo", "cartao_ponto"],
    },
    "comissao": {
        "nome_pjecalc": "COMISSÃO",
        "caracteristica": "Comum",
        "ocorrencia": "Mensal",
        "incidencia_fgts": True,
        "incidencia_inss": True,
        "incidencia_ir": True,
        "tipo": "Principal",
        "compor_principal": True,
        "campos_criticos": ["periodo"],
    },
    "comissoes": {
        "nome_pjecalc": "COMISSÃO",
        "caracteristica": "Comum",
        "ocorrencia": "Mensal",
        "incidencia_fgts": True,
        "incidencia_inss": True,
        "incidencia_ir": True,
        "tipo": "Principal",
        "compor_principal": True,
        "campos_criticos": ["periodo"],
    },
    "diferenca salarial": {
        "nome_pjecalc": "DIFERENÇA SALARIAL",
        "caracteristica": "Comum",
        "ocorrencia": "Mensal",
        "incidencia_fgts": True,
        "incidencia_inss": True,
        "incidencia_ir": True,
        "tipo": "Principal",
        "compor_principal": True,
        "campos_criticos": ["periodo"],
    },
    "diferencas salariais": {
        "nome_pjecalc": "DIFERENÇA SALARIAL",
        "caracteristica": "Comum",
        "ocorrencia": "Mensal",
        "incidencia_fgts": True,
        "incidencia_inss": True,
        "incidencia_ir": True,
        "tipo": "Principal",
        "compor_principal": True,
        "campos_criticos": ["periodo"],
    },
    "gratificacao de funcao": {
        "nome_pjecalc": "GRATIFICAÇÃO DE FUNÇÃO",
        "caracteristica": "Comum",
        "ocorrencia": "Mensal",
        "incidencia_fgts": True,
        "incidencia_inss": True,
        "incidencia_ir": True,
        "tipo": "Principal",
        "compor_principal": True,
        "campos_criticos": ["percentual", "periodo"],
    },
    "participacao nos lucros": {
        "nome_pjecalc": "PARTICIPAÇÃO NOS LUCROS OU RESULTADOS - PLR",
        "caracteristica": "Comum",
        "ocorrencia": "Desligamento",
        "incidencia_fgts": False,
        "incidencia_inss": False,
        "incidencia_ir": True,
        "tipo": "Principal",
        "compor_principal": True,
        "campos_criticos": ["valor_informado"],
    },
    "plr": {
        "nome_pjecalc": "PARTICIPAÇÃO NOS LUCROS OU RESULTADOS - PLR",
        "caracteristica": "Comum",
        "ocorrencia": "Desligamento",
        "incidencia_fgts": False,
        "incidencia_inss": False,
        "incidencia_ir": True,
        "tipo": "Principal",
        "compor_principal": True,
        "campos_criticos": ["valor_informado"],
    },
    "dano estetico": {
        "nome_pjecalc": "INDENIZAÇÃO POR DANO ESTÉTICO",
        "caracteristica": "Comum",
        "ocorrencia": "Desligamento",
        "incidencia_fgts": False,
        "incidencia_inss": False,
        "incidencia_ir": False,
        "tipo": "Principal",
        "compor_principal": True,
        "pagina_pjecalc": "Multas e Indenizações",
        "campos_criticos": ["valor_informado"],
    },
    "indenizacao adicional": {
        "nome_pjecalc": "INDENIZAÇÃO ADICIONAL",
        "caracteristica": "Comum",
        "ocorrencia": "Desligamento",
        "incidencia_fgts": False,
        "incidencia_inss": False,
        "incidencia_ir": False,
        "tipo": "Principal",
        "compor_principal": True,
        "campos_criticos": ["valor_informado"],
    },
    "multa convencional": {
        "nome_pjecalc": "MULTA CONVENCIONAL",
        "caracteristica": "Comum",
        "ocorrencia": "Desligamento",
        "incidencia_fgts": False,
        "incidencia_inss": False,
        "incidencia_ir": False,
        "tipo": "Principal",
        "compor_principal": True,
        "campos_criticos": ["valor_informado"],
    },
    "salario retido": {
        "nome_pjecalc": "SALÁRIO RETIDO",
        "caracteristica": "Comum",
        "ocorrencia": "Mensal",
        "incidencia_fgts": True,
        "incidencia_inss": True,
        "incidencia_ir": True,
        "tipo": "Principal",
        "compor_principal": True,
        "campos_criticos": ["periodo"],
    },
    "salario maternidade": {
        "nome_pjecalc": "SALÁRIO MATERNIDADE",
        "caracteristica": "Comum",
        "ocorrencia": "Mensal",
        "incidencia_fgts": True,
        "incidencia_inss": True,
        "incidencia_ir": True,
        "tipo": "Principal",
        "compor_principal": True,
        "campos_criticos": ["periodo"],
    },
    "horas in itinere": {
        "nome_pjecalc": "HORAS IN ITINERE",
        "caracteristica": "Comum",
        "ocorrencia": "Mensal",
        "incidencia_fgts": True,
        "incidencia_inss": True,
        "incidencia_ir": True,
        "tipo": "Principal",
        "compor_principal": True,
        "campos_criticos": ["periodo"],
    },
    "adicional de sobreaviso": {
        "nome_pjecalc": "ADICIONAL DE SOBREAVISO",
        "caracteristica": "Comum",
        "ocorrencia": "Mensal",
        "incidencia_fgts": True,
        "incidencia_inss": True,
        "incidencia_ir": True,
        "tipo": "Principal",
        "compor_principal": True,
        "campos_criticos": ["periodo"],
    },
    "repouso semanal remunerado": {
        "nome_pjecalc": "REPOUSO SEMANAL REMUNERADO EM DOBRO",
        "caracteristica": "Comum",
        "ocorrencia": "Mensal",
        "incidencia_fgts": True,
        "incidencia_inss": True,
        "incidencia_ir": True,
        "tipo": "Principal",
        "compor_principal": True,
        "campos_criticos": ["periodo"],
    },
    "devolucao de descontos indevidos": {
        "nome_pjecalc": "DEVOLUÇÃO DE DESCONTOS INDEVIDOS",
        "caracteristica": "Comum",
        "ocorrencia": "Mensal",
        "incidencia_fgts": False,
        "incidencia_inss": False,
        "incidencia_ir": False,
        "tipo": "Principal",
        "compor_principal": True,
        "campos_criticos": ["periodo"],
    },
    "descontos indevidos": {
        "nome_pjecalc": "DEVOLUÇÃO DE DESCONTOS INDEVIDOS",
        "caracteristica": "Comum",
        "ocorrencia": "Mensal",
        "incidencia_fgts": False,
        "incidencia_inss": False,
        "incidencia_ir": False,
        "tipo": "Principal",
        "compor_principal": True,
        "campos_criticos": ["periodo"],
    },
    "tiquete alimentacao": {
        "nome_pjecalc": "TÍQUETE-ALIMENTAÇÃO",
        "caracteristica": "Comum",
        "ocorrencia": "Mensal",
        "incidencia_fgts": False,
        "incidencia_inss": False,
        "incidencia_ir": False,
        "tipo": "Principal",
        "compor_principal": True,
        "campos_criticos": ["periodo"],
    },
    "cesta basica": {
        "nome_pjecalc": "CESTA BÁSICA",
        "caracteristica": "Comum",
        "ocorrencia": "Mensal",
        "incidencia_fgts": False,
        "incidencia_inss": False,
        "incidencia_ir": False,
        "tipo": "Principal",
        "compor_principal": True,
        "campos_criticos": ["periodo"],
    },
    "adicional de produtividade": {
        "nome_pjecalc": "ADICIONAL DE PRODUTIVIDADE 30%",
        "caracteristica": "Comum",
        "ocorrencia": "Mensal",
        "incidencia_fgts": True,
        "incidencia_inss": True,
        "incidencia_ir": True,
        "tipo": "Principal",
        "compor_principal": True,
        "campos_criticos": ["percentual", "periodo"],
    },
    "adicional de risco": {
        "nome_pjecalc": "ADICIONAL DE RISCO 40%",
        "caracteristica": "Comum",
        "ocorrencia": "Mensal",
        "incidencia_fgts": True,
        "incidencia_inss": True,
        "incidencia_ir": True,
        "tipo": "Principal",
        "compor_principal": True,
        "campos_criticos": ["periodo"],
    },
    "gorjeta": {
        "nome_pjecalc": "GORJETA",
        "caracteristica": "Comum",
        "ocorrencia": "Mensal",
        "incidencia_fgts": True,
        "incidencia_inss": True,
        "incidencia_ir": True,
        "tipo": "Principal",
        "compor_principal": True,
        "campos_criticos": ["periodo"],
    },
    "ajuda de custo": {
        "nome_pjecalc": "AJUDA DE CUSTO",
        "caracteristica": "Comum",
        "ocorrencia": "Mensal",
        "incidencia_fgts": False,
        "incidencia_inss": False,
        "incidencia_ir": False,
        "tipo": "Principal",
        "compor_principal": True,
        "campos_criticos": ["periodo"],
    },
    "gratificacao por tempo de servico": {
        "nome_pjecalc": "GRATIFICAÇÃO POR TEMPO DE SERVIÇO",
        "caracteristica": "Comum",
        "ocorrencia": "Mensal",
        "incidencia_fgts": True,
        "incidencia_inss": True,
        "incidencia_ir": True,
        "tipo": "Principal",
        "compor_principal": True,
        "campos_criticos": ["periodo"],
    },
    "abono pecuniario": {
        "nome_pjecalc": "ABONO PECUNIÁRIO",
        "caracteristica": "Ferias",
        "ocorrencia": "Periodo Aquisitivo",
        "incidencia_fgts": False,
        "incidencia_inss": False,
        "incidencia_ir": True,
        "tipo": "Principal",
        "compor_principal": True,
        "campos_criticos": [],
    },
    "diarias": {
        "nome_pjecalc": "DIÁRIAS - PAGAMENTO",
        "caracteristica": "Comum",
        "ocorrencia": "Mensal",
        "incidencia_fgts": False,
        "incidencia_inss": False,
        "incidencia_ir": False,
        "tipo": "Principal",
        "compor_principal": True,
        "campos_criticos": ["periodo"],
    },
    "diarias integracao ao salario": {
        "nome_pjecalc": "DIÁRIAS - INTEGRAÇÃO AO SALÁRIO",
        "caracteristica": "Comum",
        "ocorrencia": "Mensal",
        "incidencia_fgts": True,
        "incidencia_inss": True,
        "incidencia_ir": True,
        "tipo": "Principal",
        "compor_principal": True,
        "campos_criticos": ["periodo"],
    },
    "diarias integracao salarial": {
        "nome_pjecalc": "DIÁRIAS - INTEGRAÇÃO AO SALÁRIO",
        "caracteristica": "Comum",
        "ocorrencia": "Mensal",
        "incidencia_fgts": True,
        "incidencia_inss": True,
        "incidencia_ir": True,
        "tipo": "Principal",
        "compor_principal": True,
        "campos_criticos": ["periodo"],
    },
    # ── Verbas de ACORDO (Expresso PJE-Calc v2.15.1) ──
    # Usadas quando a sentença homologa acordo judicial.
    # Cada tipo tem tratamento tributário distinto.
    "acordo mera liberalidade": {
        "nome_pjecalc": "ACORDO (MERA LIBERALIDADE)",
        "caracteristica": "Comum",
        "ocorrencia": "Desligamento",
        "incidencia_fgts": False,
        "incidencia_inss": False,
        "incidencia_ir": False,
        "tipo": "Principal",
        "compor_principal": True,
        "campos_criticos": ["valor_informado"],
    },
    "acordo multa": {
        "nome_pjecalc": "ACORDO (MULTA)",
        "caracteristica": "Comum",
        "ocorrencia": "Desligamento",
        "incidencia_fgts": False,
        "incidencia_inss": False,
        "incidencia_ir": False,
        "tipo": "Principal",
        "compor_principal": True,
        "campos_criticos": ["valor_informado"],
    },
    "acordo verbas indenizatorias": {
        "nome_pjecalc": "ACORDO (VERBAS INDENIZATÓRIAS)",
        "caracteristica": "Comum",
        "ocorrencia": "Desligamento",
        "incidencia_fgts": False,
        "incidencia_inss": False,
        "incidencia_ir": False,
        "tipo": "Principal",
        "compor_principal": True,
        "campos_criticos": ["valor_informado"],
    },
    "acordo verbas remuneratorias": {
        "nome_pjecalc": "ACORDO (VERBAS REMUNERATÓRIAS)",
        "caracteristica": "Comum",
        "ocorrencia": "Desligamento",
        "incidencia_fgts": True,
        "incidencia_inss": True,
        "incidencia_ir": True,
        "tipo": "Principal",
        "compor_principal": True,
        "campos_criticos": ["valor_informado"],
    },
}

# ── Tabela normalizada para lookup robusto ────────────────────────────────────
# _normalizar_chave() remove preposições ("de", "do", "da"), mas as chaves acima
# contêm essas preposições. Sem normalização, "saldo salario" (normalizado da
# sentença) não encontra a chave "saldo de salario". Solução: manter ambas formas.
_VERBAS_NORMALIZADAS: dict[str, dict[str, Any]] = {}
for _k, _v in VERBAS_PREDEFINIDAS.items():
    _VERBAS_NORMALIZADAS[_k] = _v  # chave original
    import unicodedata as _ud
    import re as _re_init
    _norm = _ud.normalize("NFD", _k.lower())
    _norm = "".join(c for c in _norm if _ud.category(c) != "Mn")
    _norm = _norm.replace("º", "").replace("°", "").replace(".", "")
    _norm = _re_init.sub(r"\s*\+?\s*1/3\s*", " ", _norm).strip()
    for _stop in [" da ", " de ", " do ", " das ", " dos ", " a ", " o "]:
        _norm = _norm.replace(_stop, " ")
    _norm = _re_init.sub(r"\s+", " ", _norm).strip()
    if _norm != _k:
        _VERBAS_NORMALIZADAS[_norm] = _v
del _k, _v, _norm, _ud, _re_init


# Mapeamento de reflexas típicas (Manual, Seção 3.4)
REFLEXAS_TIPICAS: dict[str, list[dict[str, Any]]] = {
    # Chaves = nome_pjecalc EXATO (como na página Expresso do PJE-Calc v2.15.1)
    "HORAS EXTRAS 50%": [
        {
            "nome": "RSR sobre Horas Extras",
            "comportamento_base": "Média pelo Valor Absoluto",
            "incidencia_fgts": True,
            "incidencia_inss": True,
            "incidencia_ir": True,
        },
        {
            "nome": "13º s/ Horas Extras",
            "comportamento_base": "Média pelo Valor Absoluto",
            "caracteristica": "13o Salario",
            "ocorrencia": "Desligamento",
            "incidencia_fgts": True,
            "incidencia_inss": True,
            "incidencia_ir": True,
        },
        {
            "nome": "Férias + 1/3 s/ Horas Extras",
            "comportamento_base": "Média pelo Valor Absoluto",
            "caracteristica": "Ferias",
            "ocorrencia": "Periodo Aquisitivo",
            "incidencia_fgts": False,
            "incidencia_inss": True,
            "incidencia_ir": True,
        },
    ],
    "ADICIONAL NOTURNO 20%": [
        {
            "nome": "RSR sobre Adicional Noturno",
            "comportamento_base": "Média pelo Valor Absoluto",
            "incidencia_fgts": True,
            "incidencia_inss": True,
            "incidencia_ir": True,
        },
        {
            "nome": "13º s/ Adicional Noturno",
            "comportamento_base": "Média pelo Valor Absoluto",
            "caracteristica": "13o Salario",
            "ocorrencia": "Desligamento",
            "incidencia_fgts": True,
            "incidencia_inss": True,
            "incidencia_ir": True,
        },
        {
            "nome": "Férias + 1/3 s/ Adicional Noturno",
            "comportamento_base": "Média pelo Valor Absoluto",
            "caracteristica": "Ferias",
            "ocorrencia": "Periodo Aquisitivo",
            "incidencia_fgts": False,
            "incidencia_inss": True,
            "incidencia_ir": True,
        },
    ],
    "ADICIONAL DE INSALUBRIDADE": [
        {
            "nome": "13º s/ Insalubridade",
            "comportamento_base": "Valor Mensal",
            "caracteristica": "13o Salario",
            "ocorrencia": "Desligamento",
            "incidencia_fgts": True,
            "incidencia_inss": True,
            "incidencia_ir": True,
        },
        {
            "nome": "Férias + 1/3 s/ Insalubridade",
            "comportamento_base": "Valor Mensal",
            "caracteristica": "Ferias",
            "ocorrencia": "Periodo Aquisitivo",
            "incidencia_fgts": False,
            "incidencia_inss": True,
            "incidencia_ir": True,
        },
    ],
    "ADICIONAL DE INSALUBRIDADE 40%": [
        {
            "nome": "13º s/ Insalubridade",
            "comportamento_base": "Valor Mensal",
            "caracteristica": "13o Salario",
            "ocorrencia": "Desligamento",
            "incidencia_fgts": True,
            "incidencia_inss": True,
            "incidencia_ir": True,
        },
        {
            "nome": "Férias + 1/3 s/ Insalubridade",
            "comportamento_base": "Valor Mensal",
            "caracteristica": "Ferias",
            "ocorrencia": "Periodo Aquisitivo",
            "incidencia_fgts": False,
            "incidencia_inss": True,
            "incidencia_ir": True,
        },
        {
            "nome": "Aviso Prévio s/ Insalubridade",
            "comportamento_base": "Valor Mensal",
            "caracteristica": "Aviso Previo",
            "ocorrencia": "Desligamento",
            "incidencia_fgts": True,
            "incidencia_inss": True,
            "incidencia_ir": True,
        },
    ],
    "ADICIONAL DE PERICULOSIDADE 30%": [
        {
            "nome": "13º s/ Periculosidade",
            "comportamento_base": "Valor Mensal",
            "caracteristica": "13o Salario",
            "ocorrencia": "Desligamento",
            "incidencia_fgts": True,
            "incidencia_inss": True,
            "incidencia_ir": True,
        },
        {
            "nome": "Férias + 1/3 s/ Periculosidade",
            "comportamento_base": "Valor Mensal",
            "caracteristica": "Ferias",
            "ocorrencia": "Periodo Aquisitivo",
            "incidencia_fgts": False,
            "incidencia_inss": True,
            "incidencia_ir": True,
        },
        {
            "nome": "Aviso Prévio s/ Periculosidade",
            "comportamento_base": "Valor Mensal",
            "caracteristica": "Aviso Previo",
            "ocorrencia": "Desligamento",
            "incidencia_fgts": True,
            "incidencia_inss": True,
            "incidencia_ir": True,
        },
    ],
    "ADICIONAL DE TRANSFERÊNCIA 25%": [
        {
            "nome": "13º s/ Transferência",
            "comportamento_base": "Valor Mensal",
            "caracteristica": "13o Salario",
            "ocorrencia": "Desligamento",
            "incidencia_fgts": True,
            "incidencia_inss": True,
            "incidencia_ir": True,
        },
        {
            "nome": "Férias + 1/3 s/ Transferência",
            "comportamento_base": "Valor Mensal",
            "caracteristica": "Ferias",
            "ocorrencia": "Periodo Aquisitivo",
            "incidencia_fgts": False,
            "incidencia_inss": True,
            "incidencia_ir": True,
        },
        {
            "nome": "Aviso Prévio s/ Transferência",
            "comportamento_base": "Valor Mensal",
            "caracteristica": "Aviso Previo",
            "ocorrencia": "Desligamento",
            "incidencia_fgts": True,
            "incidencia_inss": True,
            "incidencia_ir": True,
        },
    ],
    "Diferença Salarial": [
        {
            "nome": "13º s/ Diferença Salarial",
            "comportamento_base": "Valor Mensal",
            "caracteristica": "13o Salario",
            "ocorrencia": "Desligamento",
            "incidencia_fgts": True,
            "incidencia_inss": True,
            "incidencia_ir": True,
        },
        {
            "nome": "Férias + 1/3 s/ Diferença Salarial",
            "comportamento_base": "Valor Mensal",
            "caracteristica": "Ferias",
            "ocorrencia": "Periodo Aquisitivo",
            "incidencia_fgts": False,
            "incidencia_inss": True,
            "incidencia_ir": True,
        },
        {
            "nome": "Aviso Prévio s/ Diferença Salarial",
            "comportamento_base": "Valor Mensal",
            "caracteristica": "Aviso Previo",
            "ocorrencia": "Desligamento",
            "incidencia_fgts": True,
            "incidencia_inss": True,
            "incidencia_ir": True,
        },
    ],
    "Adicional por Acúmulo de Função": [
        {
            "nome": "Reflexo do Adicional de Acúmulo em Aviso Prévio",
            "comportamento_base": "Valor Mensal",
            "caracteristica": "Aviso Previo",
            "ocorrencia": "Desligamento",
            "incidencia_fgts": True,
            "incidencia_inss": True,
            "incidencia_ir": True,
        },
        {
            "nome": "Reflexo do Adicional de Acúmulo em 13º Salário",
            "comportamento_base": "Valor Mensal",
            "caracteristica": "13o Salario",
            "ocorrencia": "Desligamento",
            "incidencia_fgts": True,
            "incidencia_inss": True,
            "incidencia_ir": True,
        },
        {
            "nome": "Reflexo do Adicional de Acúmulo em Férias + 1/3",
            "comportamento_base": "Valor Mensal",
            "caracteristica": "Ferias",
            "ocorrencia": "Periodo Aquisitivo",
            "incidencia_fgts": False,
            "incidencia_inss": True,
            "incidencia_ir": True,
        },
    ],
    "Feriado em Dobro": [
        {
            "nome": "Reflexo dos Feriados em Aviso Prévio",
            "comportamento_base": "Média pelo Valor Absoluto",
            "caracteristica": "Aviso Previo",
            "ocorrencia": "Desligamento",
            "incidencia_fgts": True,
            "incidencia_inss": True,
            "incidencia_ir": True,
        },
        {
            "nome": "Reflexo dos Feriados em 13º Salário",
            "comportamento_base": "Média pelo Valor Absoluto",
            "caracteristica": "13o Salario",
            "ocorrencia": "Desligamento",
            "incidencia_fgts": True,
            "incidencia_inss": True,
            "incidencia_ir": True,
        },
        {
            "nome": "Reflexo dos Feriados em Férias + 1/3",
            "comportamento_base": "Média pelo Valor Absoluto",
            "caracteristica": "Ferias",
            "ocorrencia": "Periodo Aquisitivo",
            "incidencia_fgts": False,
            "incidencia_inss": True,
            "incidencia_ir": True,
        },
    ],
}


# ── Funções públicas ──────────────────────────────────────────────────────────

def classificar_verba(verba: dict[str, Any]) -> dict[str, Any]:
    """
    Mapeia uma verba extraída da sentença para a configuração PJE-Calc.
    Prioriza o Lançamento Expresso (verbas pré-definidas).
    Para verbas não reconhecidas, usa LLM para sugestão.

    Retorna o dicionário da verba enriquecido com campos PJE-Calc.
    """
    nome = verba.get("nome_sentenca", "")
    chave = _normalizar_chave(nome)

    # Detectar se o nome original contém sufixo "- Diferenças"
    _, _eh_diferenca = _remover_sufixo_diferencas(nome)

    # Busca direta (tabela normalizada cobre ambas formas)
    config_pjec = _VERBAS_NORMALIZADAS.get(chave)

    # Busca por similaridade (substrings)
    if not config_pjec:
        config_pjec = _buscar_por_similaridade(chave)

    # Se não encontrou, tentar removendo sufixo "- Diferenças"
    # Ex: "Aviso Prévio Indenizado - Diferenças" → busca "Aviso Prévio Indenizado"
    if not config_pjec and _eh_diferenca:
        nome_base, _ = _remover_sufixo_diferencas(nome)
        chave_base = _normalizar_chave(nome_base)
        config_pjec = _VERBAS_NORMALIZADAS.get(chave_base) or _buscar_por_similaridade(chave_base)

    if config_pjec:
        verba_mapeada = {**verba, **config_pjec}
        verba_mapeada["lancamento"] = "Expresso"
        verba_mapeada["mapeada"] = True
        verba_mapeada["confianca_mapeamento"] = 1.0
        # Sugerir reflexas típicas se aplicável
        reflexas = REFLEXAS_TIPICAS.get(config_pjec["nome_pjecalc"], [])
        verba_mapeada["reflexas_sugeridas"] = reflexas
        if _eh_diferenca:
            verba_mapeada["_diferenca"] = True
            verba_mapeada["_alerta"] = (
                f"Verba de diferenças \"{nome}\" tratada como verba Expresso "
                f"\"{config_pjec['nome_pjecalc']}\""
            )
    else:
        # Tentar via LLM
        verba_mapeada = _classificar_via_llm(verba)
        verba_mapeada["lancamento"] = "Manual"
        verba_mapeada["mapeada"] = False

    return verba_mapeada


def mapear_para_pjecalc(verbas: list[dict[str, Any]]) -> dict[str, Any]:
    """
    Processa todas as verbas e retorna o mapa completo:
    {
        "predefinidas": [...],   # Lançamento Expresso
        "personalizadas": [...], # Lançamento Manual
        "nao_reconhecidas": [...],
        "reflexas_sugeridas": [...],
    }
    Otimização: verbas não reconhecidas são classificadas em UMA única chamada
    ao Claude (em lote), evitando N chamadas sequenciais.
    """
    predefinidas: list[dict] = []
    pendentes_llm: list[dict] = []   # verbas que precisam de classificação LLM
    reflexas_acumuladas: list[dict] = []

    # Passagem 1: classificar via dicionário (instantâneo)
    for verba in verbas:
        nome = verba.get("nome_sentenca", "")
        chave = _normalizar_chave(nome)

        # Detectar se o nome original contém sufixo "- Diferenças"
        _, _eh_diferenca = _remover_sufixo_diferencas(nome)

        config_pjec = _VERBAS_NORMALIZADAS.get(chave) or _buscar_por_similaridade(chave)

        # Se não encontrou, tentar removendo sufixo "- Diferenças"
        if not config_pjec and _eh_diferenca:
            nome_base, _ = _remover_sufixo_diferencas(nome)
            chave_base = _normalizar_chave(nome_base)
            config_pjec = _VERBAS_NORMALIZADAS.get(chave_base) or _buscar_por_similaridade(chave_base)

        if config_pjec:
            # Verbas marcadas _apenas_fgts não devem virar verba na automação
            # (ex: Multa Art. 467 é checkbox FGTS + reflexa automática, não verba Expresso)
            if config_pjec.get("_apenas_fgts"):
                logging.getLogger(__name__).info(f"Verba '{nome}' marcada _apenas_fgts — não incluída como verba Expresso")
                continue
            resultado = {**verba, **config_pjec}
            resultado["lancamento"] = "Expresso"
            resultado["mapeada"] = True
            resultado["confianca_mapeamento"] = 1.0
            resultado["reflexas_sugeridas"] = REFLEXAS_TIPICAS.get(config_pjec["nome_pjecalc"], [])
            if _eh_diferenca:
                resultado["_diferenca"] = True
                resultado["_alerta"] = (
                    f"Verba de diferenças \"{nome}\" tratada como verba Expresso "
                    f"\"{config_pjec['nome_pjecalc']}\""
                )
            predefinidas.append(resultado)
            reflexas_acumuladas.extend(resultado["reflexas_sugeridas"])
        else:
            pendentes_llm.append(verba)

    # Passagem 2: classificar não reconhecidas em UMA chamada LLM
    personalizadas: list[dict] = []
    nao_reconhecidas: list[dict] = []

    # Nomes PJE-Calc que são verbas Expresso (nunca devem ir para Manual)
    _NOMES_EXPRESSO = {
        _normalizar_chave(cfg.get("nome_pjecalc", ""))
        for cfg in VERBAS_PREDEFINIDAS.values()
        if cfg.get("compor_principal")
    }

    if pendentes_llm:
        classificadas = _classificar_lote_via_llm(pendentes_llm)
        for resultado in classificadas:
            # Se o LLM classificou como uma verba que existe no Expresso,
            # promover para predefinidas (não criar manual para Férias, 13º, etc.)
            _nome_pjc = resultado.get("nome_pjecalc") or (resultado.get("sugestao_llm") or {}).get("nome_pjecalc", "")
            _nome_pjc_norm = _normalizar_chave(_nome_pjc) if _nome_pjc else ""
            _carac = _normalizar_chave(resultado.get("caracteristica", ""))
            _is_expresso_verba = (
                _nome_pjc_norm in _NOMES_EXPRESSO
                or _carac in ("ferias", "decimo terceiro salario", "13o salario")
                or any(k in _nome_pjc_norm for k in ("ferias", "13 salario", "decimo terceiro"))
            )
            if _is_expresso_verba and _nome_pjc:
                # Buscar config predefinida correspondente
                _cfg_match = None
                for _k, _cfg in _VERBAS_NORMALIZADAS.items():
                    if _normalizar_chave(_cfg.get("nome_pjecalc", "")) == _nome_pjc_norm:
                        _cfg_match = _cfg
                        break
                if _cfg_match:
                    resultado = {**resultado, **_cfg_match}
                    resultado["lancamento"] = "Expresso"
                    resultado["mapeada"] = True
                    resultado["confianca_mapeamento"] = 0.85  # via LLM, não dicionário direto
                    resultado["reflexas_sugeridas"] = REFLEXAS_TIPICAS.get(_cfg_match["nome_pjecalc"], [])
                    predefinidas.append(resultado)
                    reflexas_acumuladas.extend(resultado["reflexas_sugeridas"])
                    continue

            resultado["lancamento"] = "Manual"
            resultado["mapeada"] = False
            if resultado.get("sugestao_llm"):
                personalizadas.append(resultado)
            else:
                nao_reconhecidas.append(resultado)

    # Deduplicar predefinidas por nome_pjecalc (ex: duas extrações "férias proporcionais"
    # e "férias + 1/3" ambas mapeiam para "FÉRIAS + 1/3" — só precisa 1 checkbox Expresso)
    _nomes_pjecalc_vistos: set[str] = set()
    predefinidas_dedup: list[dict] = []
    for p in predefinidas:
        _npj = (p.get("nome_pjecalc") or "").upper()
        if _npj and _npj in _nomes_pjecalc_vistos:
            continue
        _nomes_pjecalc_vistos.add(_npj)
        predefinidas_dedup.append(p)

    # Deduplicar reflexas
    nomes_reflexas_vistos: set[str] = set()
    reflexas_unicas = []
    for r in reflexas_acumuladas:
        if r["nome"] not in nomes_reflexas_vistos:
            nomes_reflexas_vistos.add(r["nome"])
            reflexas_unicas.append(r)

    # Fase final: Atribuir estratégias de preenchimento a cada verba
    resultado = {
        "predefinidas": predefinidas_dedup,
        "personalizadas": personalizadas,
        "nao_reconhecidas": nao_reconhecidas,
        "reflexas_sugeridas": reflexas_unicas,
    }
    atribuir_estrategias_verbas(resultado)
    return resultado


def atribuir_estrategias_verbas(
    verbas_mapeadas: dict[str, Any],
    db_session: Any = None,
    llm_orchestrator: Any = None,
) -> None:
    """
    Atribui estrategia_preenchimento a cada verba em verbas_mapeadas (in-place).

    Pode ser chamada:
    - No momento da classificação (sem DB, usando só catálogo estático)
    - Posteriormente com DB para enriquecer com histórico de sucesso/falha

    Args:
        verbas_mapeadas: dict com chaves "predefinidas", "personalizadas", etc.
        db_session: sessão SQLAlchemy opcional (para consultar histórico)
        llm_orchestrator: orquestrador LLM opcional (para matching semântico)
    """
    try:
        from learning.verba_strategies import VerbaStrategyEngine
        engine = VerbaStrategyEngine(db=db_session, llm_orchestrator=llm_orchestrator)
    except Exception:
        # Se o módulo de estratégias não estiver disponível, pular silenciosamente
        return

    todas_verbas = (
        verbas_mapeadas.get("predefinidas", [])
        + verbas_mapeadas.get("personalizadas", [])
    )

    for verba in todas_verbas:
        # Não sobrescrever estratégia já definida (ex: editada pelo usuário)
        if verba.get("estrategia_preenchimento"):
            continue
        try:
            estrategia = engine.escolher_estrategia(verba)
            # Montar reflexas com estratégias
            reflexas_info = []
            for ref_sug in verba.get("reflexas_sugeridas", []):
                ref_nome = ref_sug.get("nome", "") if isinstance(ref_sug, dict) else str(ref_sug)
                reflexas_info.append({
                    "nome": ref_nome,
                    "estrategia": "automatica",  # geradas pelo Expresso automaticamente
                    "nome_pjecalc": ref_nome,
                })
            verba["estrategia_preenchimento"] = {
                "estrategia": estrategia.get("estrategia", "manual"),
                "nome_pjecalc": estrategia.get("expresso_nome")
                    or verba.get("nome_pjecalc")
                    or verba.get("nome_sentenca", ""),
                "expresso_base": estrategia.get("expresso_base"),
                "campos_alterar": estrategia.get("campos_alterar"),
                "confianca": estrategia.get("confianca", 0.5),
                "baseado_em": estrategia.get("baseado_em", "fallback"),
                "parametros": estrategia.get("parametros", {}),
                "incidencias": estrategia.get("incidencias", {}),
            }
            if reflexas_info:
                verba["estrategia_preenchimento"]["reflexas"] = reflexas_info
        except Exception as _e:
            import logging
            logging.getLogger(__name__).debug(
                f"Erro ao atribuir estratégia para verba '{verba.get('nome_sentenca', '?')}': {_e}"
            )


# ── Funções auxiliares ────────────────────────────────────────────────────────

def _normalizar_chave(nome: str) -> str:
    """Normaliza o nome da verba para busca no dicionário."""
    import unicodedata
    nome = unicodedata.normalize("NFD", nome.lower())
    nome = "".join(c for c in nome if unicodedata.category(c) != "Mn")
    nome = nome.replace("º", "").replace("°", "").replace(".", "")
    # Remover "+ 1/3" de férias (implícito no PJE-Calc)
    nome = _re_mod.sub(r"\s*\+?\s*1/3\s*", " ", nome).strip()
    # Remover artigos e preposições irrelevantes
    for stop in [" da ", " de ", " do ", " das ", " dos ", " a ", " o "]:
        nome = nome.replace(stop, " ")
    # Colapsar espaços múltiplos
    nome = _re_mod.sub(r"\s+", " ", nome)
    return nome.strip()


import re as _re_mod

# Padrão para detectar sufixos de "diferenças" no nome da verba
_PADRAO_DIFERENCAS = _re_mod.compile(
    r"\s*[-–—]\s*diferen[cç]as?\s*$",
    _re_mod.IGNORECASE,
)


def _remover_sufixo_diferencas(nome: str) -> tuple[str, bool]:
    """
    Remove sufixo "- Diferenças" / "- Diferença" / "- Diferencas" do nome da verba.

    Verbas como "Aviso Prévio Indenizado - Diferenças" devem ser tratadas como
    a verba Expresso base correspondente ("AVISO PRÉVIO").

    Retorna (nome_sem_sufixo, tinha_sufixo).
    """
    if _PADRAO_DIFERENCAS.search(nome):
        nome_limpo = _PADRAO_DIFERENCAS.sub("", nome).strip()
        return nome_limpo, True
    return nome, False


def _buscar_por_similaridade(chave: str) -> dict[str, Any] | None:
    """Busca por similaridade de string (SequenceMatcher) nas verbas predefinidas.

    Para prefix matches (ex: "ferias proporcionais + 1/3" ↔ "ferias proporcionais"),
    o score é proporcional ao comprimento do match, evitando empates entre
    "ferias" (0.90) e "ferias proporcionais" (0.95).
    """
    from difflib import SequenceMatcher

    melhor_match: dict[str, Any] | None = None
    melhor_score = 0.0
    melhor_len = 0  # comprimento da chave que gerou melhor_score (desempate)
    segundo_score = 0.0

    for chave_ref, config in _VERBAS_NORMALIZADAS.items():
        # Prefixo exato — score proporcional ao comprimento do match
        # "ferias proporcionais" (20 chars) vence "ferias" (6 chars) quando
        # ambas são prefixo de "ferias proporcionais + 1/3"
        if chave.startswith(chave_ref):
            # chave_ref é prefixo de chave → score = 0.90 + 0.09*(len_ref/len_chave)
            score = 0.90 + 0.09 * (len(chave_ref) / max(len(chave), 1))
        elif chave_ref.startswith(chave):
            # chave é prefixo de chave_ref
            score = 0.90 + 0.09 * (len(chave) / max(len(chave_ref), 1))
        else:
            score = SequenceMatcher(None, chave, chave_ref).ratio()

        if score > melhor_score or (score == melhor_score and len(chave_ref) > melhor_len):
            segundo_score = melhor_score
            melhor_score = score
            melhor_match = config
            melhor_len = len(chave_ref)
        elif score > segundo_score:
            segundo_score = score

    # Exigir alta similaridade E diferença clara do segundo candidato (sem ambiguidade)
    if melhor_score >= 0.75 and (melhor_score - segundo_score) >= 0.05:
        return melhor_match
    return None


def _classificar_via_llm(verba: dict[str, Any]) -> dict[str, Any]:
    """Classifica uma única verba via LLM — wrapper de _classificar_lote_via_llm."""
    resultado = _classificar_lote_via_llm([verba])
    return resultado[0] if resultado else verba


def _classificar_lote_via_llm(verbas_nao_reconhecidas: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Classifica todas as verbas não reconhecidas em UMA única chamada ao Claude.
    Evita N chamadas sequenciais (uma por verba) que causam lentidão excessiva.
    """
    if not verbas_nao_reconhecidas:
        return []

    if not ANTHROPIC_API_KEY:
        for v in verbas_nao_reconhecidas:
            v["sugestao_llm"] = None
            v["nao_reconhecida"] = True
        return verbas_nao_reconhecidas

    import json as _json, re as _re

    # Montar lista de verbas para o prompt
    itens = []
    for i, v in enumerate(verbas_nao_reconhecidas):
        itens.append(
            f'{i}. Nome: "{v.get("nome_sentenca", "")}" | '
            f'Texto: "{v.get("texto_original", "")[:200]}"'
        )
    lista_verbas = "\n".join(itens)

    prompt = f"""Você é especialista em PJE-Calc (cálculo trabalhista).
Classifique as verbas abaixo extraídas de uma sentença trabalhista.
Responda APENAS com um array JSON com {len(verbas_nao_reconhecidas)} objetos (um por verba, na mesma ordem):

{lista_verbas}

Schema de cada objeto:
{{
  "nome_pjecalc": "nome a usar no campo Nome",
  "caracteristica": "Comum | 13o Salario | Aviso Previo | Ferias",
  "ocorrencia": "Mensal | Dezembro | Periodo Aquisitivo | Desligamento",
  "incidencia_fgts": true/false,
  "incidencia_inss": true/false,
  "incidencia_ir": true/false,
  "tipo": "Principal | Reflexa",
  "compor_principal": true/false,
  "pagina_pjecalc": "Verbas | Multas e Indenizacoes",
  "confianca": 0.0-1.0,
  "justificativa": "breve explicação"
}}

Responda SOMENTE com o array JSON, sem markdown."""

    try:
        cliente = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY, timeout=60.0)
        resposta = cliente.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=1024 * len(verbas_nao_reconhecidas),
            temperature=CLAUDE_EXTRACTION_TEMPERATURE,
            messages=[{"role": "user", "content": prompt}],
        )
        conteudo = resposta.content[0].text.strip()
        conteudo = _re.sub(r"^```(?:json)?\s*", "", conteudo)
        conteudo = _re.sub(r"\s*```\s*$", "", conteudo)
        sugestoes = _json.loads(conteudo)
        if not isinstance(sugestoes, list):
            raise ValueError("Resposta não é uma lista")
        for i, v in enumerate(verbas_nao_reconhecidas):
            if i < len(sugestoes) and isinstance(sugestoes[i], dict):
                v["sugestao_llm"] = sugestoes[i]
                v.update(sugestoes[i])
            else:
                v["sugestao_llm"] = None
                v["nao_reconhecida"] = True
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"Classificação em lote falhou: {e}")
        for v in verbas_nao_reconhecidas:
            v["sugestao_llm"] = None
            v["nao_reconhecida"] = True

    return verbas_nao_reconhecidas
