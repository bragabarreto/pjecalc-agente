"""Extração IA in-app — Fase 1 (12/06/2026).

Replica o fluxo do Projeto Claude externo DENTRO do aplicativo:
o usuário cola o texto da sentença (ou sobe PDF/DOCX/TXT/MD) e anexa
documentos do processo (PDF, imagens, MD/TXT, planilhas XLSX); a extração
roda via API Anthropic com o MESMO prompt do projeto externo
(`SYSTEM_PROMPT_V2_EXTERNAL` — fonte única em modules/extraction_v2.py)
e o MESMO fluxo de 2 etapas:

    Etapa 1: resumo prévio em markdown → usuário revisa/corrige na tela
    Etapa 2: após "Confirmar", JSON v2 → normalizer → prévia v2

A partir da Etapa 2 o fluxo desemboca 100% no pipeline v2 existente
(`_save_previa` → /previa/v2/{id} → automação) — nada do v2 é alterado.

⚠ PRESERVAÇÃO (regra do CLAUDE.md): este módulo é ADITIVO. Os caminhos
existentes — colar/subir JSON do projeto externo via /processar/v2 ou
auto-detecção .json no /processar — permanecem intocados e continuam
sendo opção de entrada. Rotas novas usam o sufixo /ia para não colidir
com /previa_v3 (UI antiga da prévia v1).

Regra IA-only: qualquer falha da API Anthropic → fase "erro" com mensagem
clara. NUNCA gerar prévia por fallback regex.

Correções com DOCUMENTOS (18/09/2026): o turno de correção aceita anexos
(PDF, imagens, DOCX, MD/TXT, XLSX, texto colado) nos mesmos moldes do envio
inicial. Os anexos entram como blocos de conteúdo do PRÓPRIO turno (não da
1ª mensagem) — preserva o prefixo em cache e a IA recebe "correção + novos
documentos" como uma coisa só.

Erros em LINGUAGEM NATURAL (18/09/2026): a falha da Etapa 2 (JSON rejeitado
pela validação Pydantic/normalizer) não é mais exibida como traceback. O
sistema traduz o erro (`_explicacao_deterministica`) e pergunta à IA, na
mesma conversa, o que está errado e QUAL informação/documento falta
(`_explicar_erro_via_ia`). O texto bruto fica em `erro_tecnico` (colapsado
na tela). Erros da API (crédito, sobrecarga, rede) viram frases claras via
`_descrever_excecao`. Falha de uma correção NÃO mata mais a sessão: o resumo
anterior continua válido (`aviso` + `correcao_pendente`).
"""

from __future__ import annotations

import base64
import json
import logging
import os
import re
import threading
import time
import uuid
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

logger = logging.getLogger(__name__)

router_extracao = APIRouter()
templates = Jinja2Templates(directory=str(Path(__file__).parent.parent / "templates"))

# ─── Storage de sessões de extração (mesma cascata do webapp_v2) ──────────
_CANDIDATOS = [
    os.environ.get("EXTRACAO_IA_DIR"),
    "/app/data/calculations/extracao_ia",
    "data/calculations/extracao_ia",
    "/tmp/pjecalc_extracao_ia",
]
_STORE_DIR: Path | None = None
for _c in _CANDIDATOS:
    if not _c:
        continue
    try:
        _p = Path(_c)
        _p.mkdir(parents=True, exist_ok=True)
        _t = _p / ".write_test"
        _t.write_text("ok")
        _t.unlink()
        _STORE_DIR = _p
        break
    except Exception:
        continue
if _STORE_DIR is None:
    _STORE_DIR = Path("/tmp/pjecalc_extracao_ia")
    _STORE_DIR.mkdir(parents=True, exist_ok=True)
logger.info(f"webapp_extracao: _STORE_DIR = {_STORE_DIR}")


def _recuperar_sessoes_orfas() -> None:
    """#80-AH — recovery no startup: sessões mortas por reinício do container.

    Deploy/restart mata o worker thread da extração; a sessão fica travada em
    `*_processando` PARA SEMPRE (caso RODRIGO ROCHA 0000905-05, 02/07/2026 —
    deploy no meio da Etapa 1). Ao subir o app:
      • etapa1_processando COM resumo_md salvo → o trabalho terminou, só a fase
        não virou: promover a `resumo_pronto` (usuário continua de onde parou);
      • etapa1_processando SEM resumo → `erro` com mensagem clara (reenviar);
      • etapa2_processando → voltar a `resumo_pronto` (a conversa está salva —
        o usuário só digita "confirmar" de novo).
    Best-effort: nunca levanta.
    """
    import json as _json
    try:
        for d in _STORE_DIR.iterdir():
            f = d / "estado.json"
            if not f.exists():
                continue
            try:
                est = _json.loads(f.read_text(encoding="utf-8"))
            except Exception:
                continue
            fase = est.get("fase")
            if fase not in ("etapa1_processando", "etapa2_processando"):
                continue
            if fase == "etapa1_processando" and not (est.get("resumo_md") or "").strip():
                est["fase"] = "erro"
                est["erro"] = ("Processamento interrompido por reinício do servidor. "
                               "Reenvie a sentença em /novo/ia.")
            else:
                est["fase"] = "resumo_pronto"
                if fase == "etapa2_processando":
                    est["aviso_recuperacao"] = ("Geração do JSON interrompida por reinício "
                                                "do servidor — digite 'confirmar' novamente.")
            try:
                f.write_text(_json.dumps(est, ensure_ascii=False), encoding="utf-8")
                logger.warning(
                    "webapp_extracao #80-AH: sessão órfã %s recuperada (%s → %s)",
                    d.name, fase, est["fase"],
                )
            except Exception:
                pass
    except Exception as _e:
        logger.warning("webapp_extracao #80-AH: recovery de órfãs falhou: %s", _e)


_recuperar_sessoes_orfas()

_MAX_FILE_BYTES = 15 * 1024 * 1024
_IMG_MAX_PX = 1536
_MAX_EXTRAS = 10
_MAX_TOKENS_ETAPA1 = 16000
_MAX_TOKENS_ETAPA2 = 32000


def _sessao_dir(sessao_id: str) -> Path:
    d = _STORE_DIR / sessao_id
    (d / "files").mkdir(parents=True, exist_ok=True)
    return d


def _load_estado(sessao_id: str) -> dict | None:
    f = _STORE_DIR / sessao_id / "estado.json"
    if not f.exists():
        return None
    return json.loads(f.read_text(encoding="utf-8"))


def _save_estado(sessao_id: str, estado: dict) -> None:
    f = _STORE_DIR / sessao_id / "estado.json"
    f.write_text(json.dumps(estado, ensure_ascii=False, indent=2), encoding="utf-8")


# ─── Conversão de arquivos para blocos de conteúdo da API ─────────────────


def _xlsx_para_markdown(path: Path, max_linhas: int = 200) -> str:
    """Converte planilha em tabelas markdown (uma por aba)."""
    from openpyxl import load_workbook

    wb = load_workbook(path, read_only=True, data_only=True)
    partes: list[str] = []
    for ws in wb.worksheets:
        linhas = []
        for i, row in enumerate(ws.iter_rows(values_only=True)):
            if i >= max_linhas:
                linhas.append(f"... ({ws.max_row - max_linhas} linhas omitidas)")
                break
            cels = ["" if c is None else str(c) for c in row]
            linhas.append("| " + " | ".join(cels) + " |")
            if i == 0:
                linhas.append("|" + "---|" * len(cels))
        if linhas:
            partes.append(f"### Aba: {ws.title}\n" + "\n".join(linhas))
    wb.close()
    return "\n\n".join(partes) or "(planilha vazia)"


def _arquivo_para_bloco(meta: dict) -> list[dict]:
    """Converte um arquivo salvo em bloco(s) de conteúdo da API Anthropic.

    Tipos: pdf → document block; imagem → image block;
    docx/txt/md → texto extraído; xlsx → tabela markdown.
    """
    path = Path(meta["caminho"])
    suf = path.suffix.lower()
    contexto = meta.get("contexto") or ""
    prefixo = f"=== DOCUMENTO: {meta.get('nome', path.name)}"
    if contexto:
        prefixo += f" ({contexto})"
    prefixo += " ==="

    if meta["tipo"] == "imagem":
        data = base64.standard_b64encode(path.read_bytes()).decode()
        blocos: list[dict] = [{"type": "text", "text": prefixo}]
        blocos.append({
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": meta.get("mime_type", "image/jpeg"),
                "data": data,
            },
        })
        return blocos

    if suf == ".pdf":
        data = base64.standard_b64encode(path.read_bytes()).decode()
        return [
            {"type": "text", "text": prefixo},
            {
                "type": "document",
                "source": {
                    "type": "base64",
                    "media_type": "application/pdf",
                    "data": data,
                },
            },
        ]

    if suf in (".docx", ".doc"):
        from modules.ingestion import _ler_docx

        res = _ler_docx(path, [])
        return [{"type": "text", "text": f"{prefixo}\n{res.get('texto', '')[:50000]}"}]

    if suf in (".xlsx", ".xlsm"):
        try:
            md = _xlsx_para_markdown(path)
        except Exception as e:
            md = f"(falha ao ler planilha: {e})"
        return [{"type": "text", "text": f"{prefixo}\n{md[:50000]}"}]

    # txt / md / csv / fallback texto
    try:
        txt = path.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        txt = f"(falha ao ler arquivo: {e})"
    return [{"type": "text", "text": f"{prefixo}\n{txt[:50000]}"}]


def _texto_sentenca_para_normalizer(estado: dict) -> str | None:
    """Texto da SENTENÇA (não dos documentos extras) p/ o normalizer — #80-DR.

    O normalizer decide se a Súmula 340 foi determinada EXPRESSAMENTE pela
    sentença (divisão #80-DK). Fontes: o texto colado + o arquivo enviado como
    "sentença/decisão principal" (PDF via pdfplumber, DOCX, TXT/MD). Best-effort:
    qualquer falha devolve None e o normalizer cai no fallback (texto da verba).
    Documentos extras (CCT, contracheques) NÃO entram — poderiam citar a súmula
    sem que a sentença a determine.
    """
    partes: list[str] = []
    try:
        texto = (estado.get("texto_colado") or "").strip()
        if texto:
            partes.append(texto)
        for meta in _todos_arquivos(estado):
            if "senten" not in str(meta.get("contexto") or "").lower():
                continue
            if meta.get("tipo") == "imagem":
                continue
            path = Path(meta.get("caminho") or "")
            if not path.is_file():
                continue
            suf = path.suffix.lower()
            try:
                if suf == ".pdf":
                    from modules.ingestion import _ler_pdf
                    partes.append(str(_ler_pdf(path, []).get("texto") or ""))
                elif suf in (".docx", ".doc"):
                    from modules.ingestion import _ler_docx
                    partes.append(str(_ler_docx(path, []).get("texto") or ""))
                elif suf in (".txt", ".md", ".csv"):
                    partes.append(path.read_text(encoding="utf-8", errors="replace"))
            except Exception as e:  # noqa: BLE001
                logger.warning("texto da sentença p/ normalizer (%s): %s", path.name, e)
    except Exception as e:  # noqa: BLE001
        logger.warning("texto da sentença p/ normalizer: %s", e)
    txt = "\n\n".join(t for t in partes if t and t.strip())
    return txt if txt.strip() else None


def _todos_arquivos(estado: dict):
    """Anexos do envio inicial + anexos de cada turno de correção."""
    yield from (estado.get("arquivos") or [])
    for t in estado.get("conversa") or []:
        yield from (t.get("arquivos") or [])


def _montar_conteudo_etapa1(estado: dict) -> list[dict]:
    """Remonta os blocos da 1ª mensagem do usuário a partir do estado."""
    blocos: list[dict] = []
    texto = (estado.get("texto_colado") or "").strip()
    if texto:
        blocos.append({
            "type": "text",
            "text": f"=== SENTENÇA (texto colado) ===\n{texto}",
        })
    for meta in estado.get("arquivos", []):
        try:
            blocos.extend(_arquivo_para_bloco(meta))
        except Exception as e:
            logger.warning(f"bloco de {meta.get('nome')}: {e}")
            blocos.append({
                "type": "text",
                "text": f"(documento {meta.get('nome')} não pôde ser lido: {e})",
            })
    blocos.append({
        "type": "text",
        "text": (
            "Execute a ETAPA 1 do fluxo operacional: apresente o resumo "
            "prévio em markdown para minha validação. NÃO gere o JSON ainda."
        ),
    })
    return blocos


def _bloco_aprendizado() -> str | None:
    """Hints de aprendizado injetados na Etapa 2 (best-effort → None).

    Dois planos, mesmo canal:
    • Plano 2 — padrões de parametrização reincidentes (prévias confirmadas);
    • Plano 3 — regras aprendidas de PJCs DEFINITIVOS (diff gerado × corrigido
      manualmente pelo calculista), tipo_regra='pjc_definitivo'.
    No-op até haver padrão/regra qualificado (n≥2 ou confiança≥0,6)."""
    try:
        from database import SessionLocal
        from learning.estrategia_parametrizacao import montar_bloco_aprendizado
        db = SessionLocal()
        try:
            partes = []
            b2 = montar_bloco_aprendizado(db)
            if b2:
                partes.append(b2)
            try:
                from learning.pjc_aprendizado import montar_bloco_pjc_definitivo
                b3 = montar_bloco_pjc_definitivo(db)
                if b3:
                    partes.append(b3)
            except Exception:
                pass
            return "\n\n".join(partes) if partes else None
        finally:
            db.close()
    except Exception:
        return None


def _montar_messages(
    estado: dict, nova_msg: str | None = None, incluir_aprendizado: bool = False
) -> list[dict]:
    """Histórico completo da conversa para a API (stateless).

    Prompt caching: o último bloco da 1ª mensagem recebe cache_control —
    isso cacheia o PREFIXO inteiro (system prompt ~25k tokens + sentença +
    documentos). Etapa 1 grava o cache; correções e Etapa 2 (minutos
    depois, mesmo prefixo) leem com 90% de desconto na entrada.

    incluir_aprendizado=True (só Etapa 2): anexa os padrões aprendidos como
    bloco de texto APÓS o breakpoint de cache (não invalida o prefixo
    cacheado; é referência, a sentença e os invariantes prevalecem).
    """
    blocos = _montar_conteudo_etapa1(estado)
    if blocos:
        blocos[-1]["cache_control"] = {"type": "ephemeral"}
        if incluir_aprendizado:
            apr = _bloco_aprendizado()
            if apr:
                blocos.append({"type": "text", "text": apr})
    msgs: list[dict] = [{"role": "user", "content": blocos}]
    for turno in estado.get("conversa", []):
        arqs = turno.get("arquivos") or []
        if arqs and turno["role"] == "user":
            # correção COM documentos: anexos no próprio turno (o prefixo da
            # 1ª mensagem — e seu cache — não muda)
            conteudo: list[dict] = []
            for meta in arqs:
                try:
                    conteudo.extend(_arquivo_para_bloco(meta))
                except Exception as e:  # noqa: BLE001
                    logger.warning(f"bloco de {meta.get('nome')}: {e}")
                    conteudo.append({
                        "type": "text",
                        "text": f"(documento {meta.get('nome')} não pôde ser lido: {e})",
                    })
            conteudo.append({"type": "text", "text": turno["texto"]})
            msgs.append({"role": "user", "content": conteudo})
        else:
            msgs.append({"role": turno["role"], "content": turno["texto"]})
    if nova_msg:
        msgs.append({"role": "user", "content": nova_msg})
    return msgs


def _chamar_claude(messages: list[dict], max_tokens: int) -> str:
    import anthropic

    from config import ANTHROPIC_API_KEY, CLAUDE_MODEL
    from modules.extraction_v2 import SYSTEM_PROMPT_V2_EXTERNAL

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY, timeout=600.0)
    resp = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=max_tokens,
        # cache_control no system: o prompt (~25k tokens) é idêntico em
        # TODA chamada — a 1ª grava o cache, as demais pagam 10% na leitura
        system=[{
            "type": "text",
            "text": SYSTEM_PROMPT_V2_EXTERNAL,
            "cache_control": {"type": "ephemeral"},
        }],
        messages=messages,
        temperature=0.0,
    )
    u = getattr(resp, "usage", None)
    usage = {
        "input": getattr(u, "input_tokens", 0),
        "output": getattr(u, "output_tokens", 0),
        "cache_write": getattr(u, "cache_creation_input_tokens", 0) or 0,
        "cache_read": getattr(u, "cache_read_input_tokens", 0) or 0,
    } if u is not None else {}
    print(f"[extracao-ia] tokens: {usage}", flush=True)
    texto = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text").strip()
    return texto, usage


def _extrair_json(texto: str) -> dict:
    """Extrai o objeto JSON da resposta da Etapa 2 (tolerante a fences)."""
    t = texto.strip()
    if t.startswith("```"):
        t = re.sub(r"^```[a-zA-Z]*\n", "", t)
        t = re.sub(r"\n```\s*$", "", t)
    try:
        return json.loads(t)
    except json.JSONDecodeError:
        # fallback: maior bloco {...} da resposta
        ini, fim = t.find("{"), t.rfind("}")
        if ini >= 0 and fim > ini:
            return json.loads(t[ini : fim + 1])
        raise


# ─── Erros em linguagem natural ───────────────────────────────────────────


def _eh_erro_api(e: Exception) -> bool:
    try:
        import anthropic as _a
        return isinstance(e, _a.APIError)
    except Exception:  # noqa: BLE001
        return False


def _descrever_excecao(e: Exception) -> str:
    """Erro da API/SDK em uma frase para o revisor (o bruto vai em `erro_tecnico`)."""
    txt = str(e)
    low = txt.lower()
    try:
        import anthropic as _a
    except Exception:  # noqa: BLE001
        _a = None
    if _a is not None:
        if isinstance(e, _a.AuthenticationError):
            return "chave da API inválida ou ausente — verifique a configuração do servidor."
        if isinstance(e, _a.RateLimitError):
            return "limite de requisições da API atingido — aguarde alguns instantes e tente de novo."
        if isinstance(e, _a.InternalServerError) or "overloaded" in low or "529" in low:
            return "a API da Anthropic está sobrecarregada neste momento — tente de novo em instantes."
        if isinstance(e, (_a.APITimeoutError, _a.APIConnectionError)):
            return "falha de rede ao falar com a API — tente de novo em instantes."
        if isinstance(e, _a.BadRequestError):
            if "credit" in low or "billing" in low:
                return "créditos da API esgotados — adicione fundos no Console da Anthropic."
            if "too long" in low or "too many tokens" in low:
                return ("o volume de sentença + documentos excede o limite da IA — remova os "
                        "documentos menos relevantes ou envie só os trechos necessários.")
            return f"a API recusou a requisição: {txt[:200]}"
    if isinstance(e, (TypeError, AttributeError, ImportError)):
        return ("erro de software (incompatibilidade da biblioteca da API), não de crédito — "
                "avise o responsável técnico; repetir não resolve.")
    return f"{type(e).__name__}: {txt[:300]}"


_NOMES_SECAO = {
    "processo": "Dados do processo",
    "parametros_calculo": "Parâmetros do cálculo",
    "historico_salarial": "Histórico salarial",
    "verbas_principais": "Verba",
    "reflexos": "Reflexo",
    "cartao_de_ponto": "Cartão de ponto",
    "cartoes_de_ponto": "Cartão de ponto",
    "faltas": "Faltas",
    "ferias": "Férias",
    "fgts": "FGTS",
    "contribuicao_social": "Contribuição social",
    "imposto_de_renda": "Imposto de renda",
    "honorarios": "Honorários",
    "custas_judiciais": "Custas judiciais",
    "correcao_juros_multa": "Correção monetária e juros",
    "liquidacao": "Liquidação",
    "multas_indenizacoes": "Multas e indenizações",
}


def _nome_item(ctx, secao: str, idx: int) -> str | None:
    """Nome legível do item `secao[idx]` do payload (verba, histórico, reflexo…)."""
    try:
        item = ctx[secao][idx]
    except Exception:  # noqa: BLE001
        return None
    if not isinstance(item, dict):
        return None
    for k in ("nome_pjecalc", "nome_sentenca", "expresso_alvo", "nome", "alvo", "tipo"):
        v = item.get(k)
        if v:
            return str(v)
    return None


def _traduzir_erro_validacao(e: Exception, payload) -> str:
    """ValidationError do Pydantic → lista markdown nomeando verba/seção pelo
    NOME (não pelo índice/campo técnico). Vazio se `e` não for ValidationError."""
    fn = getattr(e, "errors", None)
    if not callable(fn):
        return ""
    try:
        lista = fn()
    except Exception:  # noqa: BLE001
        return ""
    linhas: list[str] = []
    for err in list(lista)[:30]:
        loc = list(err.get("loc") or ())
        partes: list[str] = []
        ctx = payload if isinstance(payload, dict) else None
        i = 0
        while i < len(loc):
            p = loc[i]
            if isinstance(p, int):
                partes.append(f"item {p + 1}")
                i += 1
                continue
            rotulo = _NOMES_SECAO.get(p, str(p).replace("_", " "))
            if i + 1 < len(loc) and isinstance(loc[i + 1], int):
                nome = _nome_item(ctx, p, loc[i + 1])
                partes.append(f"{rotulo} «{nome}»" if nome else f"{rotulo} nº {loc[i + 1] + 1}")
                try:
                    ctx = ctx[p][loc[i + 1]]
                except Exception:  # noqa: BLE001
                    ctx = None
                i += 2
                continue
            partes.append(rotulo)
            ctx = ctx.get(p) if isinstance(ctx, dict) else None
            i += 1
        msg = str(err.get("msg") or "")
        if msg.startswith("Value error, "):
            msg = msg[len("Value error, "):]
        tipo = str(err.get("type") or "")
        if tipo == "missing":
            msg = "informação obrigatória ausente"
        elif tipo in ("literal_error", "enum"):
            msg = f"valor não aceito «{err.get('input')}» — {msg}"
        linhas.append(f"- **{' → '.join(partes) or 'documento'}**: {msg}")
    return "\n".join(linhas)


def _explicacao_deterministica(e: Exception, payload) -> str:
    """Explicação SEM IA (fallback e insumo do pedido à IA)."""
    if isinstance(e, json.JSONDecodeError):
        return ("A resposta da IA não veio como JSON válido (provavelmente truncada ou "
                "com texto fora do JSON). Clique em **Confirmar** novamente; se persistir, "
                "reduza o volume de documentos anexados.")
    trad = _traduzir_erro_validacao(e, payload)
    if trad:
        return ("O JSON gerado foi rejeitado pela validação do sistema nos pontos "
                "abaixo:\n\n" + trad)
    return f"Erro interno ao montar a prévia: {_descrever_excecao(e)}"


_PROMPT_EXPLICAR_ERRO = """⚠️ MENSAGEM AUTOMÁTICA DO SISTEMA (não é do revisor humano).

O JSON que você emitiu na Etapa 2 foi REJEITADO pela validação do sistema. Erro:

```
{erro}
```

Explique o problema em linguagem natural, em português, para um revisor humano
(juiz/calculista) que NÃO lê código nem JSON. NÃO emita JSON agora. NÃO cite
nomes de campos técnicos — nomeie a verba/seção como aparece na sentença.
Estruture assim:

### O que deu errado
Uma frase por problema.

### O que preciso de você
Lista objetiva do que falta — a informação exata (ex.: "o valor do salário em
março/2024", "a data exata da dispensa") ou o documento a anexar (ex.:
"contracheques de 2023", "TRCT"). Se NÃO faltar nada e você puder corrigir
sozinho, escreva exatamente: **Nenhuma informação adicional é necessária —
posso corrigir sozinho.** e diga o que vai mudar.

### Próximo passo
Uma frase: enviar as informações/documentos pelo campo de correções (é
possível anexar arquivos), ou clicar em "Confirmar" novamente."""


def _explicar_erro_via_ia(estado: dict, erro: str) -> str | None:
    """Pergunta à IA, na MESMA conversa (prefixo em cache), o que está errado e
    qual informação/documento falta. Os dois turnos ficam marcados `auto=True`
    (não aparecem como "correção enviada"), mas permanecem no histórico: na
    próxima correção/confirmação a IA sabe o que foi rejeitado. Best-effort."""
    pergunta = _PROMPT_EXPLICAR_ERRO.replace("{erro}", erro[:6000])
    conv = estado.setdefault("conversa", [])
    conv.append({"role": "user", "texto": pergunta, "auto": True})
    try:
        resp, usage = _chamar_claude(_montar_messages(estado), _MAX_TOKENS_ETAPA1)
        estado.setdefault("usage", []).append({"etapa": "explicacao_erro", **usage})
        conv.append({"role": "assistant", "texto": resp, "auto": True})
        return resp.strip() or None
    except Exception as e:  # noqa: BLE001
        logger.warning("explicação do erro via IA falhou: %s", e)
        if conv and conv[-1].get("auto") and conv[-1].get("role") == "user":
            conv.pop()  # não deixar turno de usuário órfão no histórico
        return None


# ─── Workers em background (thread própria — chamadas longas à API) ───────


def _worker_etapa1(sessao_id: str) -> None:
    estado = _load_estado(sessao_id) or {}
    try:
        resumo, usage = _chamar_claude(_montar_messages(estado), _MAX_TOKENS_ETAPA1)
        estado.setdefault("usage", []).append({"etapa": "resumo", **usage})
        estado["conversa"] = estado.get("conversa", [])
        estado["conversa"].append({"role": "assistant", "texto": resumo})
        estado["resumo_md"] = resumo
        estado["fase"] = "resumo_pronto"
    except Exception as e:
        logger.exception(f"[{sessao_id}] etapa 1 falhou")
        estado["fase"] = "erro"
        estado["erro"] = f"Falha na extração via IA (Etapa 1): {_descrever_excecao(e)}"
        estado["erro_tecnico"] = f"{type(e).__name__}: {e}"[:6000]
    _save_estado(sessao_id, estado)


def _worker_correcao(sessao_id: str, turno: dict) -> None:
    """`turno` = {"role": "user", "texto": ..., "arquivos": [meta...]?,
    "texto_original": ...} montado em `corrigir_ia`."""
    estado = _load_estado(sessao_id) or {}
    try:
        estado.setdefault("conversa", []).append(turno)
        _save_estado(sessao_id, estado)
        resumo, usage = _chamar_claude(_montar_messages(estado), _MAX_TOKENS_ETAPA1)
        estado.setdefault("usage", []).append({"etapa": "correcao", **usage})
        estado["conversa"].append({"role": "assistant", "texto": resumo})
        estado["resumo_md"] = resumo
        estado["fase"] = "resumo_pronto"
        estado.pop("correcao_pendente", None)
    except Exception as e:
        logger.exception(f"[{sessao_id}] correção falhou")
        humano = _descrever_excecao(e)
        estado["erro_tecnico"] = f"{type(e).__name__}: {e}"[:6000]
        conv = estado.get("conversa") or []
        if conv and conv[-1] is turno:
            conv.pop()  # turno sem resposta não fica no histórico
        if (estado.get("resumo_md") or "").strip():
            # o resumo anterior continua válido — NÃO matar a sessão. O texto
            # e os anexos da tentativa ficam guardados p/ reenvio automático.
            estado["fase"] = "resumo_pronto"
            estado["correcao_pendente"] = turno
            estado["aviso"] = (
                f"A correção NÃO foi aplicada: {humano} O resumo abaixo é o anterior. "
                "Seu texto foi mantido no campo de correções"
                + (f" e os {len(turno.get('arquivos') or [])} documento(s) anexado(s) "
                   "serão reenviados automaticamente" if turno.get("arquivos") else "")
                + " — clique em Refazer novamente."
            )
        else:
            estado["fase"] = "erro"
            estado["erro"] = f"Falha ao aplicar correções via IA: {humano}"
    _save_estado(sessao_id, estado)


def _worker_etapa2(sessao_id: str) -> None:
    estado = _load_estado(sessao_id) or {}
    payload = None
    try:
        estado.setdefault("conversa", []).append({"role": "user", "texto": "confirmar"})
        _save_estado(sessao_id, estado)
        bruto, usage = _chamar_claude(
            _montar_messages(estado, incluir_aprendizado=True), _MAX_TOKENS_ETAPA2
        )
        estado.setdefault("usage", []).append({"etapa": "json", **usage})
        estado["conversa"].append({"role": "assistant", "texto": bruto})
        try:
            payload = _extrair_json(bruto)
        except (json.JSONDecodeError, ValueError):
            # retry único: resposta veio com texto extra/JSON truncado —
            # pedir reemissão estrita (barata: prefixo inteiro vem do cache)
            estado["conversa"].append({
                "role": "user",
                "texto": (
                    "A resposta anterior não era JSON válido. Reemita AGORA "
                    "o JSON completo do schema v2, SOMENTE o JSON, sem "
                    "markdown e sem texto antes ou depois."
                ),
            })
            _save_estado(sessao_id, estado)
            bruto, usage = _chamar_claude(
                _montar_messages(estado, incluir_aprendizado=True),
                _MAX_TOKENS_ETAPA2,
            )
            estado.setdefault("usage", []).append({"etapa": "json_retry", **usage})
            estado["conversa"].append({"role": "assistant", "texto": bruto})
            payload = _extrair_json(bruto)

        # mesmo pipeline do /processar/v2: normalizer → Pydantic → store v2
        from modules.json_normalizer import normalize_v2_json
        from modules.webapp_v2 import PreviaCalculoV2, _save_previa

        # #80-DR: a sentença é a fonte da determinação expressa da Súmula 340
        payload = normalize_v2_json(
            payload, sentenca_texto=_texto_sentenca_para_normalizer(estado)
        )
        previa = PreviaCalculoV2.model_validate(payload)
        _previa_dump = previa.model_dump()
        _save_previa(sessao_id, _previa_dump)
        # #80-AI: prévia entra na lista principal de processos DESDE a geração
        # (requisito: disponível p/ automação posterior sem depender de URL)
        try:
            from modules.webapp_v2 import registrar_calculo_db
            registrar_calculo_db(sessao_id, _previa_dump, status="previa_gerada")
        except Exception as _e_reg:
            logger.warning("registrar_calculo_db pós-Etapa2: %s", _e_reg)
        # Aprendizado FATIA 3: snapshot das assinaturas EXTRAÍDAS (antes da
        # edição do usuário) — base do ciclo de confiança na captura.
        try:
            from modules.webapp_v2 import _save_snapshot_extracao
            _save_snapshot_extracao(sessao_id, _previa_dump)
        except Exception:
            pass

        estado["fase"] = "previa_pronta"
        estado["url_previa"] = f"/previa/v2/{sessao_id}"
    except Exception as e:
        logger.exception(f"[{sessao_id}] etapa 2 falhou")
        # o resumo continua válido: o usuário pode corrigir (com documentos)
        # e confirmar de novo
        estado["fase"] = "erro_etapa2"
        estado["erro_tecnico"] = f"{type(e).__name__}: {e}"[:6000]
        if _eh_erro_api(e):
            estado["erro"] = f"Falha na geração do JSON (Etapa 2): {_descrever_excecao(e)}"
            estado["erro_explicacao"] = None
        else:
            estado["erro"] = (
                "O JSON gerado pela IA foi rejeitado pela validação do sistema. "
                "Veja abaixo, em linguagem natural, o que está errado ou faltando."
            )
            det = _explicacao_deterministica(e, payload)
            estado["erro_explicacao"] = (
                _explicar_erro_via_ia(estado, f"{det}\n\n{estado['erro_tecnico'][:4000]}")
                or det
            )
    _save_estado(sessao_id, estado)


def _disparar(worker, *args) -> None:
    threading.Thread(target=worker, args=args, daemon=True).start()


def _limpar_sessoes_antigas(ttl_dias: int = 7) -> None:
    """Remove sessões de extração com mais de `ttl_dias` (os anexos podem
    chegar a 150MB por sessão — sem TTL o volume enche). Best-effort."""
    import shutil

    limite = time.time() - ttl_dias * 86400
    try:
        for d in _STORE_DIR.iterdir():
            if d.is_dir() and d.stat().st_mtime < limite:
                shutil.rmtree(d, ignore_errors=True)
                logger.info(f"extracao-ia: sessão antiga removida: {d.name}")
    except Exception as e:
        logger.warning(f"extracao-ia: limpeza falhou: {e}")


# ─── Rotas ────────────────────────────────────────────────────────────────


@router_extracao.get("/novo/ia", response_class=HTMLResponse)
async def pagina_novo_ia(request: Request):
    """Formulário: colar sentença ou subir arquivo + documentos extras."""
    return templates.TemplateResponse(request, "novo_calculo_ia.html", {})


async def _salvar_upload(up, sdir: Path, idx: int, contexto: str, eh_imagem: bool) -> dict | None:
    """Grava um upload em `<sessão>/files/` e devolve o meta (None se vazio/grande).
    Imagens são redimensionadas (≤1536px) e convertidas p/ JPEG."""
    dados = await up.read()
    if not dados or len(dados) > _MAX_FILE_BYTES:
        return None
    nome = Path(up.filename).name
    suf = Path(nome).suffix.lower()
    meta: dict = {"nome": nome, "contexto": contexto}
    if eh_imagem or suf in (".jpg", ".jpeg", ".png", ".webp", ".gif"):
        import io

        from PIL import Image as _PIL

        try:
            img = _PIL.open(io.BytesIO(dados))
            img.thumbnail((_IMG_MAX_PX, _IMG_MAX_PX), _PIL.Resampling.LANCZOS)
            if img.mode == "RGBA":
                img = img.convert("RGB")
            buf = io.BytesIO()
            fmt = "JPEG" if img.mode in ("RGB", "L") else "PNG"
            img.save(buf, format=fmt, quality=85)
            dados = buf.getvalue()
            meta["mime_type"] = "image/jpeg" if fmt == "JPEG" else "image/png"
        except Exception:
            meta["mime_type"] = getattr(up, "content_type", "image/jpeg")
        meta["tipo"] = "imagem"
        path = sdir / "files" / f"{idx}_{Path(nome).stem}.jpg"
    else:
        meta["tipo"] = "arquivo"
        path = sdir / "files" / f"{idx}_{nome}"
    path.write_bytes(dados)
    meta["caminho"] = str(path)
    return meta


async def _coletar_extras(form, sdir: Path, idx_base: int) -> tuple[list[dict], str]:
    """Documentos extras do form (padrão doc_arquivo_N / doc_imagem_N /
    doc_texto_N / doc_contexto_N — o mesmo do envio inicial e da correção).
    Devolve (metas dos arquivos salvos, texto dos documentos colados)."""
    arquivos: list[dict] = []
    texto_extra = ""
    for i in range(_MAX_EXTRAS):
        ctx = str(form.get(f"doc_contexto_{i}", "")).strip()
        arq = form.get(f"doc_arquivo_{i}")
        img = form.get(f"doc_imagem_{i}")
        txt = form.get(f"doc_texto_{i}")
        meta = None
        if arq is not None and hasattr(arq, "filename") and arq.filename:
            meta = await _salvar_upload(arq, sdir, idx_base + i, ctx, eh_imagem=False)
        elif img is not None and hasattr(img, "filename") and img.filename:
            meta = await _salvar_upload(img, sdir, idx_base + i, ctx, eh_imagem=True)
        elif txt and str(txt).strip():
            texto_extra += (
                f"\n\n=== DOCUMENTO COLADO{f' ({ctx})' if ctx else ''} ===\n"
                + str(txt).strip()[:30000]
            )
        if meta:
            arquivos.append(meta)
    return arquivos, texto_extra


@router_extracao.post("/processar/ia")
async def processar_ia(request: Request):
    """Recebe sentença (texto colado e/ou arquivo) + extras; dispara Etapa 1."""
    form = await request.form()
    sessao_id = str(uuid.uuid4())
    sdir = _sessao_dir(sessao_id)
    _disparar(_limpar_sessoes_antigas)

    texto_colado = str(form.get("texto_sentenca", "")).strip()
    arquivos: list[dict] = []

    # sentença em arquivo (opcional — texto colado também vale)
    sent = form.get("arquivo_sentenca")
    if sent is not None and hasattr(sent, "filename") and sent.filename:
        meta = await _salvar_upload(sent, sdir, 0, "sentença/decisão principal", eh_imagem=False)
        if meta:
            arquivos.append(meta)

    extras, texto_extra = await _coletar_extras(form, sdir, 1)
    arquivos.extend(extras)
    texto_colado += texto_extra

    if not texto_colado and not arquivos:
        return JSONResponse(
            status_code=400,
            content={"erro": "Cole o texto da sentença ou anexe ao menos um arquivo."},
        )

    estado = {
        "fase": "etapa1_processando",
        "criado_em": time.strftime("%Y-%m-%d %H:%M:%S"),
        "texto_colado": texto_colado,
        "arquivos": arquivos,
        "conversa": [],
    }
    _save_estado(sessao_id, estado)
    _disparar(_worker_etapa1, sessao_id)

    return JSONResponse({
        "sessao_id": sessao_id,
        "url_resumo": f"/resumo/ia/{sessao_id}",
    })


@router_extracao.get("/resumo/ia/{sessao_id}", response_class=HTMLResponse)
async def pagina_resumo_ia(sessao_id: str, request: Request):
    """Página do resumo de validação (Etapa 1) com polling."""
    estado = _load_estado(sessao_id)
    if estado is None:
        return HTMLResponse("Sessão de extração não encontrada.", status_code=404)
    return templates.TemplateResponse(
        request, "resumo_ia.html", {"sessao_id": sessao_id}
    )


@router_extracao.get("/api/ia/{sessao_id}/estado")
async def estado_ia(sessao_id: str):
    estado = _load_estado(sessao_id)
    if estado is None:
        return JSONResponse({"fase": "nao_encontrada"}, status_code=404)
    # histórico de correções já enviadas (para exibir na tela) — turnos
    # `auto` (pedido de explicação de erro) e "confirmar" não contam
    correcoes: list[str] = []
    for t in estado.get("conversa", []):
        if t.get("role") != "user" or t.get("auto") or t.get("texto") == "confirmar":
            continue
        s = t.get("texto_original") or t.get("texto") or ""
        n = len(t.get("arquivos") or [])
        if n:
            s = f"📎 {n} documento(s) — {s}"
        correcoes.append(s)
    pend = estado.get("correcao_pendente") or {}
    return JSONResponse({
        "fase": estado.get("fase"),
        "resumo_md": estado.get("resumo_md"),
        "erro": estado.get("erro"),
        "erro_tecnico": estado.get("erro_tecnico"),
        "erro_explicacao": estado.get("erro_explicacao"),
        "aviso": estado.get("aviso") or estado.get("aviso_recuperacao"),
        "correcao_pendente": pend.get("texto_original") or pend.get("texto"),
        "url_previa": estado.get("url_previa"),
        "n_arquivos": sum(1 for _ in _todos_arquivos(estado)),
        "usage": estado.get("usage", []),
        "correcoes": correcoes,
    })


@router_extracao.post("/api/ia/{sessao_id}/corrigir")
async def corrigir_ia(sessao_id: str, request: Request):
    """Correção do resumo: texto E/OU documentos novos.

    Aceita JSON `{"correcoes": "..."}` (forma original) ou multipart com
    `correcoes` + `doc_arquivo_N`/`doc_imagem_N`/`doc_texto_N`/`doc_contexto_N`
    (mesmo padrão do envio inicial). Os anexos viram blocos do PRÓPRIO turno.
    """
    estado = _load_estado(sessao_id)
    if estado is None:
        return JSONResponse({"erro": "sessão não encontrada"}, status_code=404)
    if estado.get("fase") not in ("resumo_pronto", "erro_etapa2"):
        return JSONResponse({"erro": f"fase atual: {estado.get('fase')}"}, status_code=409)

    arquivos: list[dict] = []
    if "multipart/form-data" in (request.headers.get("content-type") or ""):
        form = await request.form()
        correcoes = str(form.get("correcoes", "")).strip()
        sdir = _sessao_dir(sessao_id)
        idx_base = 1 + sum(1 for _ in (sdir / "files").iterdir())
        arquivos, texto_extra = await _coletar_extras(form, sdir, idx_base)
        correcoes += texto_extra
    else:
        payload = await request.json()
        correcoes = str((payload or {}).get("correcoes", "")).strip()

    # anexos de uma tentativa anterior que falhou (API fora do ar etc.)
    pend = estado.pop("correcao_pendente", None) or {}
    arquivos = list(pend.get("arquivos") or []) + arquivos

    if not correcoes and not arquivos:
        return JSONResponse(
            {"erro": "descreva as correções ou anexe ao menos um documento"},
            status_code=400,
        )
    texto = correcoes or "Seguem documentos adicionais do processo."
    if arquivos:
        texto += (
            f"\n\n(Anexei {len(arquivos)} documento(s) adicional(is) nesta mensagem. "
            "Refaça a ETAPA 1 integrando as informações deles e as correções acima. "
            "NÃO gere o JSON ainda.)"
        )
    turno: dict = {"role": "user", "texto": texto, "texto_original": correcoes}
    if arquivos:
        turno["arquivos"] = arquivos

    estado["fase"] = "etapa1_processando"
    for k in ("erro", "erro_tecnico", "erro_explicacao", "aviso", "aviso_recuperacao"):
        estado.pop(k, None)
    _save_estado(sessao_id, estado)
    _disparar(_worker_correcao, sessao_id, turno)
    return JSONResponse({"status": "processando", "n_arquivos": len(arquivos)})


@router_extracao.post("/api/ia/{sessao_id}/confirmar")
async def confirmar_ia(sessao_id: str):
    estado = _load_estado(sessao_id)
    if estado is None:
        return JSONResponse({"erro": "sessão não encontrada"}, status_code=404)
    if estado.get("fase") not in ("resumo_pronto", "erro_etapa2"):
        return JSONResponse({"erro": f"fase atual: {estado.get('fase')}"}, status_code=409)
    estado["fase"] = "etapa2_processando"
    for k in ("erro", "erro_tecnico", "erro_explicacao", "aviso", "aviso_recuperacao"):
        estado.pop(k, None)
    _save_estado(sessao_id, estado)
    _disparar(_worker_etapa2, sessao_id)
    return JSONResponse({"status": "processando"})
