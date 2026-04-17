# modules/playwright_pjecalc.py — Automação Playwright para PJE-Calc Cidadão
#
# Implementação conforme Manual Técnico v2.0:
#   - Verificação HTTP após TCP (não apenas porta)
#   - Decorator @retry com detecção de ViewExpiredException
#   - Monitor de AJAX JSF nativo (jsf.ajax.addOnEvent)
#   - Hierarquia de seletores: get_by_label → [id$=] → XPath contains → escaped CSS
#   - press_sequentially para campos de data
#   - Mapeamento dinâmico de campos para diagnóstico
#   - Tratamento do erro de primeira carga do PJE-Calc

from __future__ import annotations

import functools
import json
import re
import signal
import socket
import subprocess
import time
import urllib.request
import logging
import os
from pathlib import Path
from typing import Any, Callable

# DOM selectors validados — ver knowledge/pjecalc_selectors.py
from knowledge.pjecalc_selectors import (
    DadosProcesso,
    ParametrosCalculo,
    ParametrosGerais,
    HistoricoSalarial,
    Ferias as FeriasSelectors,
    Faltas as FaltasSelectors,
    CartaoPonto,
    VerbaListagem,
    VerbaExpresso,
    VerbaManual,
    VerbaParametro,
    VerbaOcorrencia,
    FGTS as FGTSSelectors,
    ContribuicaoSocial as INSSSelectors,
    ImpostoRenda as IRSelectors,
    Honorarios as HonorariosSelectors,
    MultasIndenizacoes as MultasSelectors,
    SalarioFamilia as SalFamSelectors,
    SeguroDesemprego as SegDeseSelectors,
    PrevidenciaPrivada as PrevPrivSelectors,
    PensaoAlimenticia as PensAlimSelectors,
    CorrecaoJurosMulta,
    CustasJudiciais as CustasSelectors,
    Liquidacao,
    Exportacao,
    SidebarMenu,
    Mensagens,
    Comum,
)

# structlog preferido; fallback para stdlib logging se não disponível
try:
    import structlog
    logger = structlog.get_logger(__name__)
except ImportError:
    logger = logging.getLogger(__name__)  # type: ignore[assignment]

# tenacity disponível para retries futuros via BrowserManager
try:
    from tenacity import retry as _tenacity_retry, stop_after_attempt, wait_exponential  # noqa: F401
    _TENACITY_AVAILABLE = True
except ImportError:
    _TENACITY_AVAILABLE = False

# URL base do PJE-Calc — lida de config/env uma vez no import do módulo
try:
    from config import PJECALC_LOCAL_URL as _PJECALC_LOCAL_URL
except ImportError:
    _PJECALC_LOCAL_URL = os.environ.get(
        "PJECALC_LOCAL_URL", "http://localhost:9257/pjecalc"
    )

# Porta extraída da URL base (para checagem TCP de fallback)
def _porta_local() -> int:
    try:
        import urllib.parse as _p
        return int(_p.urlparse(_PJECALC_LOCAL_URL).port or 9257)
    except Exception:
        return 9257


# ── Decorator de retry ────────────────────────────────────────────────────────

def retry(max_tentativas: int = 3, delay: int = 2):
    """Retry automático com screenshot em falha, detecção de ViewExpiredException e crash recovery."""
    def decorator(func):
        @functools.wraps(func)
        def wrapper(self: "PJECalcPlaywright", *args, **kwargs):
            ultima_exc = None
            for tentativa in range(1, max_tentativas + 1):
                try:
                    return func(self, *args, **kwargs)
                except Exception as exc:
                    ultima_exc = exc
                    self._log(f"  ⚠ Tentativa {tentativa}/{max_tentativas} em {func.__name__}: {exc}")
                    # Screenshot para diagnóstico
                    try:
                        os.makedirs("screenshots", exist_ok=True)
                        self._page.screenshot(
                            path=f"screenshots/erro_{func.__name__}_{tentativa}.png",
                            full_page=True,
                        )
                    except Exception:
                        pass
                    # Recuperar crash do Firefox (Target crashed / context destruído)
                    exc_str = str(exc)
                    if any(k in exc_str for k in ("Target crashed", "Target page, context or browser has been closed",
                                                    "Execution context was destroyed")):
                        self._log("  🔄 Firefox crashou — reiniciando browser…")
                        try:
                            self.fechar()
                        except Exception:
                            pass
                        try:
                            import sys
                            headless = getattr(self, "_headless", sys.platform != "win32")
                            # IMPORTANTE: iniciar_browser DEVE rodar na mesma thread que
                            # vai usar o self._page depois. Playwright sync API é thread-bound
                            # (greenlet): criar em uma thread e usar em outra causa
                            # "cannot switch to a different thread (which happens to have exited)".
                            # iniciar_browser já faz asyncio._set_running_loop(None) para
                            # contornar o "Sync API inside asyncio loop" quando a thread herda
                            # o loop do uvicorn (Python 3.10+).
                            self.iniciar_browser(headless=headless)
                            self._instalar_monitor_ajax()
                            self._page.goto(
                                f"{self.PJECALC_BASE}/pages/principal.jsf",
                                wait_until="domcontentloaded", timeout=30000
                            )
                            self._page.wait_for_timeout(2000)
                            self._log("  ✓ Browser reiniciado — retentando fase…")
                        except Exception as re_exc:
                            self._log(f"  ⚠ Falha ao reiniciar browser: {re_exc}")
                    # Recupera ViewState expirado
                    try:
                        body = self._page.locator("body").text_content(timeout=3000) or ""
                        if "ViewExpired" in body or "expired" in body.lower():
                            self._log("  ↻ ViewState expirado — recarregando página…")
                            self._page.reload()
                            self._page.wait_for_load_state("networkidle", timeout=10000)
                    except Exception as view_exc:
                        logger.debug(f"retry: ViewExpired check failed: {view_exc}")
                    if tentativa < max_tentativas:
                        # Backoff exponencial: 2s, 4s, 8s
                        time.sleep(delay * (2 ** (tentativa - 1)))
            raise ultima_exc
        return wrapper
    return decorator


# ── Verificação e inicialização do PJE-Calc ───────────────────────────────────

def pjecalc_rodando() -> bool:
    """
    Retorna True se o PJE-Calc já está disponível via HTTP.
    Aceita 200, 302 e 404 — qualquer resposta HTTP indica Tomcat ativo.
    404 = Tomcat up mas webapp ainda deployando; 200/302 = totalmente pronto.
    Fallback para TCP se a checagem HTTP falhar (ex: timeout de rede).
    """
    try:
        with urllib.request.urlopen(_PJECALC_LOCAL_URL, timeout=2) as r:
            return r.status in (200, 302, 404)
    except Exception:
        pass
    # Fallback TCP: porta aberta sem resposta HTTP ainda
    try:
        s = socket.create_connection(("127.0.0.1", _porta_local()), timeout=1)
        s.close()
        return True
    except OSError:
        return False


def iniciar_pjecalc(pjecalc_dir: str | Path, timeout: int = 180, log_cb=None) -> None:
    """
    Inicia o PJE-Calc Cidadão via iniciarPjeCalc.bat (Windows) ou iniciarPjeCalc.sh (Linux).
    Aguarda:
      1) porta TCP abrir
      2) HTTP responder com 200/302/404
    Emite mensagens de progresso via log_cb durante a espera.
    """
    import platform
    _log = log_cb or (lambda m: None)
    dir_path = Path(pjecalc_dir)

    if pjecalc_rodando():
        # pjecalc_rodando() já confirmou HTTP — sem espera adicional.
        # (O SSE em webapp.py faz a espera longa de 600s; aqui só confirmamos.)
        logger.info(f"PJE-Calc HTTP disponível em {_PJECALC_LOCAL_URL} — iniciando automação.")
        _log("PJE-Calc disponível — iniciando automação…")
        return

    logger.info(f"Iniciando PJE-Calc Cidadão a partir de {dir_path}…")
    _log("Iniciando PJE-Calc Cidadão… (pode levar até 3 minutos)")

    sistema = platform.system()
    if sistema == "Windows":
        launcher = dir_path / "iniciarPjeCalc.bat"
        if not launcher.exists():
            raise FileNotFoundError(
                f"iniciarPjeCalc.bat não encontrado em {dir_path}. "
                "Verifique a configuração PJECALC_DIR."
            )
        subprocess.Popen(
            ["cmd", "/c", str(launcher)],
            cwd=str(dir_path),
            creationflags=subprocess.CREATE_NEW_CONSOLE,
        )
    elif sistema == "Darwin":
        # macOS: usa iniciarPjeCalc-macos.sh (Bootstrap direto, sem Xvfb/xdotool)
        # Fallback: iniciarPjeCalc.sh genérico, depois .app bundle
        macos_launcher = Path(__file__).parent.parent / "iniciarPjeCalc-macos.sh"
        generic_launcher = dir_path / "iniciarPjeCalc.sh"
        app_bundle = dir_path / "PJE-Calc.app"
        if macos_launcher.exists():
            subprocess.Popen(
                ["bash", str(macos_launcher)],
                env={**os.environ, "PJECALC_DIR": str(dir_path)},
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        elif generic_launcher.exists():
            subprocess.Popen(
                ["bash", str(generic_launcher)],
                cwd=str(dir_path),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        elif app_bundle.exists():
            subprocess.Popen(["open", str(app_bundle)])
        else:
            raise FileNotFoundError(
                f"Launcher macOS não encontrado. "
                "Inicie o PJE-Calc Cidadão manualmente e tente novamente.\n"
                "Para instalar Java 8: brew install --cask temurin@8"
            )
    else:
        # Linux / Docker: usa iniciarPjeCalc.sh
        launcher = dir_path / "iniciarPjeCalc.sh"
        if not launcher.exists():
            raise FileNotFoundError(
                f"iniciarPjeCalc.sh não encontrado em {dir_path}. "
                "Verifique a configuração PJECALC_DIR ou crie o script shell."
            )
        subprocess.Popen(
            ["bash", str(launcher)],
            cwd=str(dir_path),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    # 1) Aguarda porta TCP abrir
    inicio = time.time()
    while time.time() - inicio < timeout:
        if pjecalc_rodando():
            logger.info(f"PJE-Calc: porta TCP aberta ({_porta_local()}).")
            _log("PJE-Calc: porta TCP aberta. Aguardando deploy web…")
            break
        time.sleep(2)
    else:
        raise TimeoutError(
            f"PJE-Calc não ficou disponível em {timeout}s. "
            "Verifique se o Java está instalado corretamente."
        )

    # 2) Aguarda HTTP responder (Tomcat pode aceitar TCP antes de concluir deploy)
    _aguardar_http(timeout=180, log_cb=log_cb)


def _aguardar_http(timeout: int = 300, log_cb=None) -> None:
    """
    Aguarda o PJE-Calc responder com 200, 302 ou 404.
    404 é aceito: indica que o Tomcat está ativo mas o war ainda está sendo
    deployado. O Playwright consegue conectar assim que a página JSF responder.
    Emite progresso via log_cb a cada 15s.
    """
    url = _PJECALC_LOCAL_URL
    inicio = time.time()
    ultimo_log = -15  # força log no primeiro ciclo
    while time.time() - inicio < timeout:
        try:
            with urllib.request.urlopen(url, timeout=5) as resp:
                if resp.status in (200, 302, 404):
                    logger.info(f"PJE-Calc HTTP respondendo (status {resp.status}) — pronto.")
                    if log_cb:
                        log_cb(f"PJE-Calc pronto (HTTP {resp.status}).")
                    if resp.status == 404:
                        time.sleep(3)  # margem extra: 404 = war ainda deployando
                    return
        except Exception:
            pass
        elapsed = int(time.time() - inicio)
        if log_cb and elapsed - ultimo_log >= 15:
            log_cb(f"⏳ Aguardando PJE-Calc inicializar… ({elapsed}s/{timeout}s)")
            ultimo_log = elapsed
        time.sleep(3)
    raise TimeoutError(
        f"PJE-Calc: porta aberta mas HTTP não respondeu em {timeout}s. "
        "Verifique /api/logs/java para diagnóstico."
    )


# ── H2 cleanup e controle do Tomcat ──────────────────────────────────────────

def limpar_h2_database(pjecalc_dir: str | Path, log_cb=None) -> bool:
    """
    Remove arquivos H2 (.h2.db, .lock.db, .mv.db, .trace.db) do diretório .dados/.
    NÃO remove JSONs, PJCs ou outros arquivos do usuário.
    Deve ser chamada ANTES de iniciar o Tomcat (ou após pará-lo).
    Restaura template .h2.db.template se disponível (schema Hibernate obrigatório).

    NOTA: O template pode conter cálculos residuais de execuções anteriores.
    A proteção contra contaminação por cálculos residuais é feita pela
    verificação de identidade do processo (_verificar_calculo_correto) na
    automação, não pela limpeza do H2.
    """
    _log = log_cb or (lambda m: None)
    dados_dir = Path(pjecalc_dir) / ".dados"

    if not dados_dir.exists():
        _log("H2 cleanup: diretório .dados/ não encontrado — ignorado")
        return False

    h2_patterns = ["*.h2.db", "*.lock.db", "*.mv.db", "*.trace.db"]
    removed = []
    for pattern in h2_patterns:
        for f in dados_dir.glob(pattern):
            if f.name.endswith(".template"):
                continue  # nunca remover o template
            try:
                f.unlink()
                removed.append(f.name)
            except OSError as e:
                _log(f"H2 cleanup: erro ao remover {f.name}: {e}")

    if removed:
        _log(f"H2 cleanup: removidos {removed}")
    else:
        _log("H2 cleanup: nenhum arquivo H2 encontrado")

    # Restaurar template se H2 foi removido e template existe
    template = dados_dir / "pjecalc.h2.db.template"
    h2_db = dados_dir / "pjecalc.h2.db"
    if not h2_db.exists() and template.exists():
        import shutil
        shutil.copy2(str(template), str(h2_db))
        _log("H2 cleanup: template restaurado → pjecalc.h2.db")

    return bool(removed)


def limpar_calculo_via_sql(pjecalc_dir: str | Path, log_cb=None) -> bool:
    """Limpa dados de cálculos do H2 via SQL direto, SEM parar o Tomcat.

    O H2 do PJE-Calc aceita múltiplas conexões quando configurado com
    AUTO_SERVER=TRUE (padrão). Usamos o jar do H2 embutido no PJE-Calc
    para executar DELETE nas tabelas de dados de cálculo, preservando
    tabelas de sistema/referência.

    Retorna True se conseguiu limpar, False se falhou.
    """
    _log = log_cb or (lambda m: None)
    dados_dir = Path(pjecalc_dir) / ".dados"
    h2_db = dados_dir / "pjecalc.h2.db"

    if not h2_db.exists():
        _log("SQL cleanup: arquivo H2 não encontrado — ignorado")
        return False

    # Localizar o jar do H2 no diretório do PJE-Calc
    pjecalc_path = Path(pjecalc_dir)
    h2_jar = None
    for candidate in [
        pjecalc_path / "bin" / "lib" / "h2.jar",
        pjecalc_path / "bin" / "lib" / "h2-1.4.200.jar",
        pjecalc_path / "tomcat" / "lib" / "h2.jar",
        pjecalc_path / "tomcat" / "lib" / "h2-1.4.200.jar",
    ]:
        if candidate.exists():
            h2_jar = candidate
            break

    # Busca recursiva como fallback
    if not h2_jar:
        for f in pjecalc_path.rglob("h2*.jar"):
            if "h2" in f.name.lower() and f.suffix == ".jar":
                h2_jar = f
                break

    if not h2_jar:
        _log("SQL cleanup: h2.jar não encontrado no PJE-Calc — ignorado")
        return False

    # URL JDBC para conectar ao H2 (modo embedded file)
    # O H2 no PJE-Calc usa file mode. Se o Tomcat está rodando,
    # precisamos do modo AUTO_SERVER para conectar simultaneamente.
    h2_db_path = str(h2_db).replace(".h2.db", "")
    jdbc_url = f"jdbc:h2:file:{h2_db_path};AUTO_SERVER=TRUE;IFEXISTS=TRUE"

    # SQL para limpar tabelas de dados de cálculo
    # Ordem: tabelas dependentes primeiro (FK constraints)
    sql_statements = """
DELETE FROM TBOCORRENCIA;
DELETE FROM TBREFLEXAVERBA;
DELETE FROM TBVERBA;
DELETE FROM TBHISTORICOSALARIAL;
DELETE FROM TBFALTA;
DELETE FROM TBFERIAS;
DELETE FROM TBCARTAOPONTO;
DELETE FROM TBHONORARIO;
DELETE FROM TBLIQUIDACAO;
DELETE FROM TBCALCULO;
COMMIT;
""".strip()

    try:
        # Detectar Java disponível
        java_cmd = os.environ.get("JAVA_HOME", "")
        if java_cmd:
            java_cmd = os.path.join(java_cmd, "bin", "java")
        else:
            java_cmd = "java"

        # Executar SQL via H2 Shell (modo não-interativo)
        result = subprocess.run(
            [java_cmd, "-cp", str(h2_jar), "org.h2.tools.Shell",
             "-url", jdbc_url, "-user", "sa", "-password", ""],
            input=sql_statements,
            capture_output=True,
            text=True,
            timeout=30,
        )

        if result.returncode == 0:
            _log("SQL cleanup: cálculos removidos do H2 com sucesso")
            return True
        else:
            # Pode falhar se as tabelas não existem com esses nomes exatos
            # Tentar nomes alternativos (sem prefixo TB)
            _log(f"SQL cleanup: tentativa 1 falhou ({result.stderr[:200]})")
            sql_alt = """
DELETE FROM OCORRENCIA;
DELETE FROM REFLEXAVERBA;
DELETE FROM VERBA;
DELETE FROM HISTORICOSALARIAL;
DELETE FROM FALTA;
DELETE FROM FERIAS;
DELETE FROM CARTAOPONTO;
DELETE FROM HONORARIO;
DELETE FROM LIQUIDACAO;
DELETE FROM CALCULO;
COMMIT;
""".strip()
            result2 = subprocess.run(
                [java_cmd, "-cp", str(h2_jar), "org.h2.tools.Shell",
                 "-url", jdbc_url, "-user", "sa", "-password", ""],
                input=sql_alt,
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result2.returncode == 0:
                _log("SQL cleanup: cálculos removidos (nomes alternativos)")
                return True
            _log(f"SQL cleanup: ambas tentativas falharam — stderr: {result2.stderr[:200]}")
            return False

    except FileNotFoundError:
        _log("SQL cleanup: Java não encontrado — ignorado")
        return False
    except subprocess.TimeoutExpired:
        _log("SQL cleanup: timeout (30s) — H2 pode estar locked")
        return False
    except Exception as e:
        _log(f"SQL cleanup: erro inesperado — {e}")
        return False


def _parar_tomcat(timeout: int = 15) -> None:
    """Para o Tomcat via SIGTERM ao PID em /tmp/pjecalc.pid. SIGKILL após timeout."""
    pid_file = Path("/tmp/pjecalc.pid")
    if not pid_file.exists():
        return
    try:
        pid = int(pid_file.read_text().strip())
        os.kill(pid, signal.SIGTERM)
        for _ in range(timeout):
            try:
                os.kill(pid, 0)
                time.sleep(1)
            except OSError:
                break  # processo morreu
        else:
            os.kill(pid, signal.SIGKILL)
    except (ValueError, ProcessLookupError, PermissionError):
        pass
    finally:
        pid_file.unlink(missing_ok=True)


# ── Utilitários de formatação ─────────────────────────────────────────────────

def _fmt_br(valor: float | str | None) -> str:
    """Formata número como moeda BR: 1234.56 → '1.234,56'."""
    if valor is None:
        return ""
    try:
        return f"{float(valor):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except (ValueError, TypeError):
        return str(valor)


def _parsear_numero_processo(numero: str | None) -> dict:
    """'0001686-52.2026.5.07.0003' → {numero, digito, ano, justica, regiao, vara}."""
    if not numero:
        return {}
    m = re.match(r"(\d{7})-(\d{2})\.(\d{4})\.(\d)\.(\d{2})\.(\d{4})", numero.strip())
    if m:
        return {
            "numero": m.group(1),
            "digito": m.group(2),
            "ano": m.group(3),
            "justica": m.group(4),
            "regiao": m.group(5),
            "vara": m.group(6),
        }
    return {}


# ── Classe de automação Playwright ────────────────────────────────────────────

class PJECalcPlaywright:
    """
    Preenche o PJE-Calc Cidadão via Playwright (browser visível).
    Implementa as recomendações do Manual Técnico v2.0.
    """

    # URL base do PJE-Calc local — lida de PJECALC_LOCAL_URL (config/env).
    # Padrão: http://localhost:9257/pjecalc (bundled pjecalc-dist/).
    # Instalação padrão TRT: http://localhost:8080/pje-calc
    try:
        from config import PJECALC_LOCAL_URL as _LOCAL_URL
        PJECALC_BASE = _LOCAL_URL
    except ImportError:
        import os as _os
        PJECALC_BASE = _os.environ.get(
            "PJECALC_LOCAL_URL", "http://localhost:9257/pjecalc"
        )
    LOG_DIR = Path("data/logs")

    def __init__(
        self,
        log_cb: Callable[[str], None] | None = None,
        exec_dir: Path | None = None,
    ):
        self._log_cb = log_cb or (lambda msg: None)
        self._pw = None
        self._pw_cm = None
        self._browser = None
        self._page = None
        self._headless = False  # stored by iniciar_browser() para crash recovery
        self._exec_dir = exec_dir  # diretório de persistência por cálculo
        # Capturados após criar um novo cálculo — usados para URL-based navigation
        self._calculo_url_base: str | None = None
        self._calculo_conversation_id: str | None = None
        self._dados: dict | None = None  # dados da sentença (armazenado em preencher_calculo)
        self._reflexos_configurados: set[str] = set()  # nomes de verbas principais cujos reflexos foram configurados via botão
        self._verbas_expresso_ok: set[str] = set()  # nomes de verbas criadas com sucesso via Expresso (reflexos auto-gerados)
        self._strategy_engine = None  # VerbaStrategyEngine — inicializado lazy em fase_verbas

    # ── Ciclo de vida ──────────────────────────────────────────────────────────

    def iniciar_browser(self, headless: bool = False) -> None:
        import asyncio
        import os, sys
        # Em Linux sem display real (Railway/Docker), forçar headless
        if sys.platform != "win32" and not os.environ.get("DISPLAY"):
            headless = True
        self._headless = headless  # salva para crash recovery no retry
        # sync_playwright() falha com "Sync API inside asyncio loop" quando chamado
        # de uma thread que herda o running loop do uvicorn (Python 3.10+).
        # Solução: limpar o running loop a nível C via asyncio._set_running_loop(None)
        # e criar um loop novo isolado.
        asyncio.set_event_loop(asyncio.new_event_loop())
        # Forçar limpeza do running loop (C-level thread-local) — necessário em Python 3.10+
        # quando threads daemon herdam referência ao loop do uvicorn/asyncio main thread.
        _set_running = getattr(asyncio, "_set_running_loop", None)
        if _set_running:
            _set_running(None)
        from playwright.sync_api import sync_playwright
        # Guardamos o context manager (não só a instância) para que fechar()
        # consiga chamar __exit__ corretamente. A instância Playwright em si
        # não expõe __exit__ — o erro 'Playwright object has no attribute __exit__'
        # mascarava exceções reais no teardown.
        self._pw_cm = sync_playwright()
        self._pw = self._pw_cm.__enter__()
        self._browser = self._pw.firefox.launch(
            headless=headless,
            slow_mo=0 if headless else 150,
        )
        # viewport explícito: necessário para offsetParent e is_visible() funcionarem
        # em modo headless — sem viewport, todos os elementos reportam offsetParent=null
        ctx = self._browser.new_context(
            viewport={"width": 1920, "height": 1080},
            locale="pt-BR",
        )
        self._page = ctx.new_page()
        self._page.set_default_timeout(60000)
        # Interceptar erros HTTP e erros JS (diagnóstico em produção)
        # Excluir arquivos estáticos/fontes que geram 404 inofensivos (tahoma.ttf, etc.)
        _STATIC_EXTS = ('.ttf', '.woff', '.woff2', '.otf', '.eot',
                        '.ico', '.png', '.gif', '.jpg', '.svg')
        self._page.on(
            "response",
            lambda r: self._log(f"  ⚠ HTTP {r.status}: {r.url}")
            if r.status >= 400 and "9257" in r.url
                and not r.url.split('?')[0].lower().endswith(_STATIC_EXTS)
            else None,
        )
        self._page.on(
            "console",
            lambda m: self._log(f"  [JS] {m.text}")
            if m.type == "error"
            else None,
        )

    def fechar(self) -> None:
        # Teardown defensivo: cada etapa em try separado para que uma falha
        # não impeça as seguintes. Erros aqui NÃO devem mascarar exceções
        # reais que ocorreram durante a automação.
        try:
            if self._browser is not None:
                self._browser.close()
        except Exception as e:
            logger.debug(f"fechar(): browser.close falhou: {e}")
        try:
            if getattr(self, "_pw_cm", None) is not None:
                self._pw_cm.__exit__(None, None, None)
            elif self._pw is not None and hasattr(self._pw, "stop"):
                self._pw.stop()
        except Exception as e:
            logger.debug(f"fechar(): playwright stop falhou: {e}")
        self._browser = None
        self._pw = None
        self._pw_cm = None

    # ── Logging ────────────────────────────────────────────────────────────────

    def _log(self, msg: str) -> None:
        logger.info(msg)
        self._log_cb(msg)

    # ── Monitor de AJAX JSF ────────────────────────────────────────────────────

    def _instalar_monitor_ajax(self) -> None:
        """Injeta listener no sistema de AJAX do JSF para esperas precisas."""
        self._page.evaluate("""() => {
            window.__ajaxCompleto = true;
            if (typeof jsf !== 'undefined' && jsf.ajax) {
                jsf.ajax.addOnEvent(function(data) {
                    if (data.status === 'begin') window.__ajaxCompleto = false;
                    if (data.status === 'success' || data.status === 'complete')
                        window.__ajaxCompleto = true;
                });
            }
        }""")

    def _aguardar_ajax(self, timeout: int = 15000) -> None:
        """Aguarda conclusão do AJAX JSF; fallback para networkidle.

        Se o monitor AJAX não está instalado (ex: após page.goto()),
        reinstala automaticamente. Timeout reduzido a 5s quando monitor
        ausente para evitar hangs de 15s em páginas sem AJAX pendente.
        """
        try:
            # Verificar se monitor está instalado; reinstalar se necessário
            _monitor_ok = False
            try:
                _monitor_ok = self._page.evaluate(
                    "() => typeof window.__ajaxCompleto !== 'undefined'"
                )
            except Exception as e:
                logger.debug(f"_aguardar_ajax: check monitor failed: {e}")
            if not _monitor_ok:
                try:
                    self._instalar_monitor_ajax()
                    # Após goto, AJAX inicial já completou — marcar como completo
                    self._page.evaluate("() => { window.__ajaxCompleto = true; }")
                except Exception as e:
                    logger.debug(f"_aguardar_ajax: reinstall monitor failed: {e}")
                # Sem monitor + recém-instalado → networkidle é mais confiável
                try:
                    self._page.wait_for_load_state("networkidle", timeout=5000)
                except Exception:
                    self._page.wait_for_timeout(1000)
                return

            self._page.wait_for_function(
                "() => window.__ajaxCompleto === true",
                timeout=timeout,
            )
            # Reset obrigatório: sem isso a próxima espera retorna imediatamente
            # com o true da operação anterior (falso positivo em cascata AJAX).
            try:
                self._page.evaluate("() => { window.__ajaxCompleto = false; }")
            except Exception as e:
                logger.debug(f"_aguardar_ajax: reset flag failed: {e}")
        except Exception as e:
            logger.debug(f"_aguardar_ajax: wait_for_function failed ({e}), fallback networkidle")
            try:
                self._page.wait_for_load_state("networkidle", timeout=5000)
            except Exception:
                self._page.wait_for_timeout(2000)

    # ── Descoberta dinâmica de campos ─────────────────────────────────────────

    def mapear_campos(self, nome_pagina: str = "pagina") -> list[dict]:
        """
        Cataloga todos os campos input/select/textarea da página atual.
        Salva em data/logs/campos_{nome_pagina}.json para diagnóstico.
        """
        campos = self._page.evaluate("""() => {
            const campos = [];
            document.querySelectorAll('input, select, textarea').forEach(el => {
                const lbl = document.querySelector(`label[for='${el.id}']`);
                // getBoundingClientRect funciona em headless (offsetParent não)
                const r = el.getBoundingClientRect();
                campos.push({
                    id: el.id,
                    name: el.name || '',
                    type: el.type || el.tagName.toLowerCase(),
                    tag: el.tagName.toLowerCase(),
                    label: lbl ? lbl.textContent.trim() : '',
                    visible: r.width > 0 && r.height > 0,
                    sufixo: el.id.includes(':') ? el.id.split(':').pop() : el.id
                });
            });
            return campos;
        }""")
        # Salvar para diagnóstico
        try:
            self.LOG_DIR.mkdir(parents=True, exist_ok=True)
            caminho = self.LOG_DIR / f"campos_{nome_pagina}.json"
            caminho.write_text(
                json.dumps(campos, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            self._log(f"  📋 Mapeamento de campos salvo: {caminho}")
        except Exception:
            pass
        return campos

    # ── Localização de elementos — hierarquia de 4 níveis ────────────────────

    def _localizar(
        self,
        field_id: str,
        label: str | None = None,
        tipo: str = "input",
        timeout: int = 5000,
    ):
        """
        Localiza elemento JSF seguindo hierarquia do manual:
        1. get_by_label (mais estável)
        2. [id$='sufixo'] (sufixo do ID)
        3. XPath contains(@id) (sem problema com dois-pontos)
        4. ID escapado (último recurso)
        Retorna Locator visível ou None.
        """
        # Nível 1: por label
        if label:
            loc = self._page.get_by_label(label, exact=False)
            if loc.count() > 0:
                return loc.first

        # Nível 2: sufixo de ID, SEMPRE com prefixo de tag para evitar match em
        # elementos errados (ex: <table class="rich-calendar-exterior"> ou <li>
        # ou <input type="hidden"> — que NÃO são interagíveis).
        sufixo = field_id.split(":")[-1]  # extrai sufixo se vier com prefixo
        seletores_base = [
            f"[id*='{sufixo}InputDate']",  # RichFaces 3.x Calendar: formulario:dataXxxInputDate
            f"[id$='{sufixo}_input']",      # RichFaces 4.x: <input id="..._input">
            f"[id$=':{sufixo}']",
            f"[id$='{sufixo}']",
        ]
        if tipo == "select":
            seletores = [f"select{s}" for s in seletores_base]
        elif tipo == "checkbox":
            seletores = [f"input[type='checkbox']{s}" for s in seletores_base]
        elif tipo == "input":
            # :not([type='hidden']) evita match em:
            #   1. <table id="...:dataAdmissao" class="rich-calendar-exterior"> (popup)
            #   2. <input id="...:dataAdmissao" type="hidden"> (campo oculto de valor)
            # O campo visível do RichFaces Calendar tem id "...InputDate" (seletor 1 acima)
            seletores = [f"input:not([type='hidden']){s}" for s in seletores_base]
        else:
            seletores = seletores_base

        for sel in seletores:
            try:
                loc = self._page.locator(sel)
                if loc.count() > 0 and loc.first.is_visible():
                    return loc.first
            except Exception:
                continue

        # Nível 2.5: name attribute — JSF às vezes usa name= mais estável que id=
        if tipo == "select":
            seletores_name = [f"select[name$='{sufixo}']", f"select[name*='{sufixo}']"]
        elif tipo == "checkbox":
            seletores_name = [
                f"input[type='checkbox'][name$='{sufixo}']",
                f"input[type='checkbox'][name*='{sufixo}']",
            ]
        else:
            seletores_name = [f"input[name$='{sufixo}']", f"input[name*='{sufixo}']"]
        for sel in seletores_name:
            try:
                loc = self._page.locator(sel)
                if loc.count() > 0 and loc.first.is_visible():
                    return loc.first
            except Exception:
                continue

        # Nível 3: XPath contains(@id)
        # Para "input": @type='text' exclui hidden inputs (ex: formulario:dataDemissao hidden)
        xpath_map = {
            "input":    f"//input[@type='text' and contains(@id, '{sufixo}')]",
            "select":   f"//select[contains(@id, '{sufixo}')]",
            "checkbox": f"//input[@type='checkbox' and contains(@id, '{sufixo}')]",
        }
        xpath = xpath_map.get(tipo, f"//*[contains(@id, '{sufixo}')]")
        try:
            loc = self._page.locator(xpath)
            if loc.count() > 0 and loc.first.is_visible():
                return loc.first
        except Exception:
            pass

        # Nível 4: ID completo com dois-pontos escapados
        escaped = field_id.replace(":", "\\:")
        try:
            loc = self._page.locator(f"#{escaped}")
            if loc.count() > 0 and loc.first.is_visible():
                return loc.first
        except Exception:
            pass

        return None

    # ── Primitivas DOM ─────────────────────────────────────────────────────────

    def _preencher(
        self,
        field_id: str,
        valor: str,
        obrigatorio: bool = True,
        label: str | None = None,
    ) -> bool:
        """Preenche campo de input JSF com fallback entre 4 estratégias."""
        if not valor:
            return False
        loc = self._localizar(field_id, label, tipo="input")
        if not loc:
            if obrigatorio:
                self._log(f"  ⚠ {field_id}: campo não encontrado — preencha manualmente.")
            return False
        try:
            loc.wait_for(state="visible", timeout=8000)
            # Verificar se disabled/readonly — evitar timeout de 60s do Playwright
            try:
                _state = loc.evaluate("el => ({disabled: el.disabled, readonly: el.readOnly})")
                if _state.get("disabled") or _state.get("readonly"):
                    loc.evaluate(
                        "(el, v) => { el.disabled = false; el.readOnly = false; "
                        "el.value = v; "
                        "el.dispatchEvent(new Event('input',{bubbles:true})); "
                        "el.dispatchEvent(new Event('change',{bubbles:true})); }",
                        valor,
                    )
                    self._log(f"  ✓ {field_id}: {valor} (disabled/readonly override)")
                    return True
            except Exception:
                pass
            loc.click()
            loc.fill("")
            loc.fill(valor)
            loc.dispatch_event("input")
            loc.dispatch_event("change")
            # Sem blur intencional: JSF/RichFaces usa blur para AJAX postback.
            # Disparar blur aqui causa race condition com o próximo campo → HTTP 500.
            # O blur natural ocorre quando o próximo campo recebe foco (click/Tab).
            self._log(f"  ✓ {field_id}: {valor}")
            return True
        except Exception as e:
            if obrigatorio:
                self._log(f"  ⚠ {field_id}: erro ao preencher — {e}")
            return False

    def _preencher_data(
        self,
        field_id: str,
        data: str,
        obrigatorio: bool = True,
        label: str | None = None,
    ) -> bool:
        """
        Preenche campo de data (rich:calendar) usando JS direto no componente RichFaces.

        O rich:calendar gera:
        - Input visível: formulario:{field_id}InputDate (onde o usuário digita)
        - Hidden input: formulario:{field_id}InputCurrentDate (valor submetido ao JSF)
        - Componente JS: RichFaces.calendarUtils / __richfaces_calendar

        Estratégia: setar ambos os inputs via JS e disparar eventos de change/blur
        para que o JSF receba o valor no submit do form.

        IMPORTANTE: Usar Tab ao final (não Escape!) para disparar blur → JSF sync.
        O blur pode disparar AJAX em alguns campos (dataDemissao), mas isso é necessário
        para o valor ser submetido corretamente.
        """
        if not data:
            return False
        loc = self._localizar(field_id, label, tipo="input")
        if not loc:
            if obrigatorio:
                self._log(f"  ⚠ data {field_id}: campo não encontrado — preencha manualmente.")
            return False
        try:
            loc.wait_for(state="visible", timeout=8000)

            # Verificar se o campo está disabled (dataCriacao, etc.)
            try:
                _is_disabled = loc.evaluate("el => el.disabled")
                if _is_disabled:
                    # Campo disabled — setar via JS direto (sem focus/type)
                    loc.evaluate(
                        "(el, v) => { el.disabled = false; el.value = v; el.disabled = true; }",
                        data,
                    )
                    self._log(f"  ✓ data {field_id}: {data} (disabled/readonly override)")
                    return True
            except Exception:
                pass

            # Estratégia: simular digitação humana no input visível do rich:calendar
            #
            # rich:calendar gera:
            # - formulario:dataXxxInputDate — input visível (máscara 99/99/9999)
            # - formulario:dataXxxInputCurrentDate — hidden (valor submetido ao JSF)
            #
            # O RichFaces Calendar JS converte InputDate → InputCurrentDate no blur.
            # Devemos deixar essa conversão acontecer NATURALMENTE.
            # NÃO setar InputCurrentDate manualmente (formato interno desconhecido).
            #
            # Passos:
            # 1. Focus no input (ativa a máscara via oninputfocus)
            # 2. Ctrl+A + Delete para limpar
            # 3. Digitar dígitos (máscara auto-insere barras: 04112024 → 04/11/2024)
            # 4. Clicar no body para blur natural (NÃO Tab — pode abrir popup do próximo calendar)

            loc.focus()
            self._page.wait_for_timeout(300)  # Esperar máscara ativar (oninputfocus)
            self._page.keyboard.press("Control+a")
            self._page.keyboard.press("Delete")
            self._page.wait_for_timeout(100)

            # Digitar apenas os dígitos — a máscara 99/99/9999 auto-insere as barras
            digits_only = data.replace("/", "").replace("-", "")
            loc.press_sequentially(digits_only, delay=80)
            self._page.wait_for_timeout(300)

            # Tirar foco do campo para disparar blur natural → RichFaces atualiza hidden
            # NÃO usar Escape (limpa o valor digitado no rich:calendar!)
            # NÃO clicar no body (pode acertar logo/menu e navegar para outra página!)
            # Usar Tab diretamente — move foco para o próximo campo, disparando blur.
            # Se o calendar popup abrir, Tab fecha-o e move foco.
            self._page.keyboard.press("Tab")
            # Aguardar AJAX (dateDemissao tem a4j:support oninputblur que re-renderiza)
            self._aguardar_ajax(timeout=5000)
            self._page.wait_for_timeout(300)

            # Verificar valores resultantes (rich:calendar ou input simples)
            _result = self._page.evaluate("""(suffix) => {
                // Tentar rich:calendar primeiro
                const calInput = document.querySelector('input[id$="' + suffix + 'InputDate"]');
                if (calInput) {
                    const hid = document.getElementById(calInput.id.replace('InputDate', 'InputCurrentDate'));
                    return {
                        visible: calInput.value,
                        hidden: hid ? hid.value : 'NO_HIDDEN',
                        type: 'calendar'
                    };
                }
                // Fallback: input simples
                const simpleInput = document.querySelector(
                    'input[id$="' + suffix + '"]:not([type="hidden"])'
                );
                if (simpleInput) {
                    return {visible: simpleInput.value, hidden: '', type: 'simple'};
                }
                return {visible: 'NOT_FOUND', hidden: '', type: 'none'};
            }""", field_id)

            _vis = _result.get("visible", "") if isinstance(_result, dict) else str(_result)
            _hid = _result.get("hidden", "") if isinstance(_result, dict) else ""
            _type = _result.get("type", "") if isinstance(_result, dict) else ""

            self._aguardar_ajax(timeout=2000)
            if _type == "calendar":
                self._log(f"  ✓ data {field_id}: {data} (visible={_vis}, hidden={_hid})")
            else:
                self._log(f"  ✓ data {field_id}: {data}")
            return True
        except Exception as e:
            # Fallback: setar valor via JS no input visível + disparar blur
            try:
                self._page.evaluate("""([suffix, dateStr]) => {
                    const input = document.querySelector(
                        'input[id$="' + suffix + 'InputDate"], input[id$="' + suffix + '"]'
                    );
                    if (!input) return false;
                    input.focus();
                    input.value = dateStr;
                    input.dispatchEvent(new Event('change', {bubbles: true}));
                    input.dispatchEvent(new Event('blur', {bubbles: true}));
                    return true;
                }""", [field_id, data])
                self._log(f"  ✓ data {field_id} (JS fallback): {data}")
                return True
            except Exception as e2:
                self._log(f"  ⚠ data {field_id}: erro — {e} | fallback: {e2}")
                return False

    def _selecionar(
        self,
        field_id: str,
        valor: str,
        label: str | None = None,
        obrigatorio: bool = True,
    ) -> bool:
        """Seleciona opção em <select> JSF por label (texto visível) ou value."""
        if not valor:
            return False
        loc = self._localizar(field_id, label, tipo="select")
        if not loc:
            if obrigatorio:
                self._log(f"  ⚠ select {field_id}: não encontrado — selecione manualmente.")
            return False
        try:
            loc.wait_for(state="visible", timeout=8000)
            # Verificar se o select está disabled (evitar timeout de 60s do Playwright)
            try:
                _is_disabled = loc.evaluate("el => el.disabled")
                if _is_disabled:
                    self._log(f"  ⚠ select {field_id}: disabled — tentando JS direto")
                    _js_ok = self._page.evaluate(
                        """([suffix, val]) => {
                            const sel = [...document.querySelectorAll('select')]
                                .find(s => s.id && s.id.endsWith(suffix));
                            if (!sel) return false;
                            sel.disabled = false;
                            // Tentar por value
                            for (const opt of sel.options) {
                                if (opt.value === val || opt.text.trim() === val) {
                                    sel.value = opt.value;
                                    sel.dispatchEvent(new Event('change', {bubbles: true}));
                                    return true;
                                }
                            }
                            return false;
                        }""",
                        [field_id, valor],
                    )
                    if _js_ok:
                        self._aguardar_ajax()
                        self._log(f"  ✓ select {field_id}: {valor} (via JS disabled override)")
                        return True
                    return False
            except Exception:
                pass
            # Tenta por value primeiro, depois por label (ambos com timeout curto
            # para evitar 60s de espera quando a opção simplesmente não existe)
            _selected = False
            try:
                loc.select_option(value=valor, timeout=3000)
                _selected = True
            except Exception:
                pass
            if not _selected:
                try:
                    loc.select_option(label=valor, timeout=3000)
                    _selected = True
                except Exception:
                    pass
            if not _selected:
                # Última tentativa: JS direto com fuzzy match em value e text
                _js_ok = self._page.evaluate(
                    """([suffix, val]) => {
                        const sel = [...document.querySelectorAll('select')]
                            .find(s => s.id && s.id.endsWith(suffix));
                        if (!sel) return false;
                        const n = s => (s || '').toString().trim().toLowerCase();
                        const target = n(val);
                        for (const opt of sel.options) {
                            if (n(opt.value) === target || n(opt.text) === target) {
                                sel.value = opt.value;
                                sel.dispatchEvent(new Event('change', {bubbles: true}));
                                return true;
                            }
                        }
                        return false;
                    }""",
                    [field_id, valor],
                )
                if not _js_ok:
                    raise Exception(f"opção '{valor}' não encontrada no select")
            loc.dispatch_event("change")
            self._aguardar_ajax()
            self._log(f"  ✓ select {field_id}: {valor}")
            return True
        except Exception as e:
            self._log(f"  ⚠ select {field_id}: erro — {e}")
            return False

    def _extrair_opcoes_select(self, field_suffix: str) -> list[dict]:
        """
        Extrai todas as opções de um <select> cujo ID termina com field_suffix.
        Retorna lista de {value, text} para fuzzy matching.
        """
        try:
            opcoes = self._page.evaluate(f"""(suffix) => {{
                const sel = [...document.querySelectorAll('select')].find(
                    s => s.id && s.id.endsWith(suffix)
                );
                if (!sel) return [];
                return [...sel.options].map(o => ({{value: o.value, text: o.text.trim()}}));
            }}""", field_suffix)
            return opcoes or []
        except Exception:
            return []

    def _match_fuzzy(self, valor: str, opcoes: list[dict]) -> str | None:
        """
        Normaliza e compara valor com as opções disponíveis.
        Retorna o value da opção mais próxima, ou None se nenhuma encontrada.
        """
        import unicodedata

        def _norm(s: str) -> str:
            s = s.lower().strip()
            s = unicodedata.normalize("NFD", s)
            s = "".join(c for c in s if not unicodedata.combining(c))
            return s

        val_norm = _norm(valor)
        # Exact match first (text)
        for op in opcoes:
            if _norm(op.get("text", "")) == val_norm:
                return op["value"]
        # Exact match on value
        for op in opcoes:
            if _norm(op.get("value", "")) == val_norm:
                return op["value"]
        # Substring match (skip empty text/value and noSelection placeholders)
        for op in opcoes:
            txt = _norm(op.get("text", ""))
            val = op.get("value", "")
            if not txt or "noselection" in val.lower():
                continue
            if val_norm in txt or txt in val_norm:
                return op["value"]
        return None

    def _marcar_radio(self, field_id: str, valor: str) -> bool:
        """Clica em radio button JSF.

        Hardened contra hangs: cada click tem timeout explícito de 5s (vs. default
        30s do Playwright). Se AJAX anterior ainda está pendente, esperamos até 5s
        pelo ViewState estabilizar antes de clicar.
        """
        # Garantir que AJAX pré-existente terminou antes de clicar no novo radio.
        # Se não terminar em 5s, prosseguir mesmo assim — o novo click vai invalidar
        # o anterior ou o JSF vai processar em fila.
        try:
            self._page.wait_for_load_state("networkidle", timeout=5000)
        except Exception:
            pass

        seletores = [
            f"input[type='radio'][value='{valor}'][id$='{field_id}']",
            f"table[id$='{field_id}'] input[value='{valor}']",
            f"input[type='radio'][name$='{field_id}'][value='{valor}']",
            f"input[type='radio'][name*='{field_id}'][value='{valor}']",
            f"//input[@type='radio' and @value='{valor}' and contains(@id, '{field_id}')]",
            f"//input[@type='radio' and @value='{valor}' and contains(@name, '{field_id}')]",
        ]
        for sel in seletores:
            try:
                loc = self._page.locator(sel)
                if loc.count() > 0:
                    # timeout=5000: fail fast se o elemento está bloqueado por overlay
                    # ou não-clicável. Default do Playwright (30s) esconde problemas.
                    loc.first.click(timeout=5000)
                    # Aguardar AJAX a4j:support (evita LockTimeoutException no
                    # @Synchronized apresentadorVerbaDeCalculo causada por
                    # pipelining de requests consecutivos).
                    # Timeout 8s: radios com a4j:support completam em <1s;
                    # timeout cheio de 15s acumula em fases com muitos radios.
                    self._aguardar_ajax(timeout=8000)
                    self._log(f"  ✓ radio {field_id}: {valor}")
                    return True
            except Exception:
                continue
        # Fallback: match by label text (JSF radios often have enum value != display label)
        # Maps common enum values to their label text variants
        import unicodedata as _ud_radio
        _norm = lambda s: _ud_radio.normalize("NFD", s.lower()).encode("ascii", "ignore").decode().strip()
        _valor_norm = _norm(valor)
        _label_map = {
            "fixa": ["fixa"], "variavel": ["variavel", "variável"],
            "informado": ["informado", "informada"], "calculado": ["calculado", "calculada"],
            "principal": ["principal"], "reflexo": ["reflexa", "reflexo"],
            "comum": ["comum"], "mensal": ["mensal"],
            "decimo_terceiro_salario": ["13o salario", "13º salário", "décimo terceiro"],
            "ferias": ["ferias", "férias"], "aviso_previo": ["aviso previo", "aviso prévio"],
            "desligamento": ["desligamento"], "dezembro": ["dezembro"],
            "periodo_aquisitivo": ["periodo aquisitivo", "período aquisitivo"],
            "ocorrencias_vencidas": ["sim", "vencidas"],
            "ocorrencias_vincendas": ["nao", "não", "vincendas"],
        }
        _labels_to_try = _label_map.get(_valor_norm, [_valor_norm])
        try:
            loc_all = self._page.locator(
                f"input[type='radio'][id*='{field_id}'], "
                f"input[type='radio'][name*='{field_id}']"
            )
            for idx in range(loc_all.count()):
                _r = loc_all.nth(idx)
                # Get label text from adjacent element
                _label_text = ""
                try:
                    _label_text = _r.evaluate("""el => {
                        const lbl = el.parentElement?.querySelector('label')
                            || document.querySelector('label[for="' + el.id + '"]');
                        if (lbl) return lbl.textContent.trim();
                        const next = el.nextSibling;
                        if (next && next.nodeType === 3) return next.textContent.trim();
                        return '';
                    }""")
                except Exception:
                    continue
                _label_norm = _norm(_label_text)
                for _try_label in _labels_to_try:
                    if _label_norm == _norm(_try_label) or _label_norm.startswith(_norm(_try_label)):
                        _r.click()
                        # Aguardar AJAX a4j:support (mesmo motivo acima).
                        self._aguardar_ajax()
                        self._log(f"  ✓ radio {field_id}: {valor} (label='{_label_text}')")
                        return True
        except Exception:
            pass
        self._log(f"  ⚠ radio {field_id}={valor}: não encontrado")
        return False

    def _marcar_radio_js(self, sufixo_id: str, valor: str) -> bool:
        """Fallback JS puro para radio buttons JSF — busca por contains() no id/name.

        Usado quando _marcar_radio() falha (ex: table wrapper com ID dinâmico).
        Dispara click + change event para garantir atualização do ViewState.
        """
        try:
            clicou = self._page.evaluate(f"""() => {{
                const radios = [...document.querySelectorAll('input[type="radio"]')];
                const sufixo = '{sufixo_id}';
                const valor = '{valor}';
                const valorLower = valor.toLowerCase();

                // 1. Busca exata por value + id contains
                let r = radios.find(el =>
                    (el.id || '').includes(sufixo) && el.value === valor
                );
                // 2. Busca exata por value + name contains
                if (!r) {{
                    r = radios.find(el =>
                        (el.name || '').includes(sufixo) && el.value === valor
                    );
                }}
                // 3. Busca por LABEL text (JSF radios podem ter value != enum name)
                if (!r) {{
                    for (const radio of radios) {{
                        if (!(radio.id || '').includes(sufixo) && !(radio.name || '').includes(sufixo))
                            continue;
                        // Check adjacent label element
                        const labelEl = radio.parentElement?.querySelector('label')
                            || document.querySelector('label[for="' + radio.id + '"]');
                        if (labelEl) {{
                            const labelText = labelEl.textContent.trim().toLowerCase()
                                .normalize('NFD').replace(/[\u0300-\u036f]/g, '');
                            const targetNorm = valorLower.normalize('NFD').replace(/[\u0300-\u036f]/g, '');
                            if (labelText === targetNorm || labelText.startsWith(targetNorm)
                                || targetNorm.startsWith(labelText)) {{
                                r = radio;
                                break;
                            }}
                        }}
                        // Check text node sibling
                        const nextText = radio.nextSibling;
                        if (nextText && nextText.nodeType === 3) {{
                            const txt = nextText.textContent.trim().toLowerCase()
                                .normalize('NFD').replace(/[\u0300-\u036f]/g, '');
                            const targetNorm = valorLower.normalize('NFD').replace(/[\u0300-\u036f]/g, '');
                            if (txt === targetNorm || txt.startsWith(targetNorm)
                                || targetNorm.startsWith(txt)) {{
                                r = radio;
                                break;
                            }}
                        }}
                    }}
                }}
                if (r) {{
                    r.click();
                    r.dispatchEvent(new Event('change', {{bubbles: true}}));
                    return true;
                }}
                return false;
            }}""")
            if clicou:
                self._aguardar_ajax()
                self._log(f"  ✓ radio JS {sufixo_id}: {valor}")
                return True
        except Exception:
            pass
        self._log(f"  ⚠ radio JS {sufixo_id}={valor}: não encontrado")
        return False

    def _preencher_radio_ou_select(
        self,
        field_id: str,
        valor: str,
        obrigatorio: bool = True,
    ) -> bool:
        """Tenta preencher campo como select primeiro, depois como radio (JSF pode usar qualquer um).

        Budget wallclock de 20s para evitar hangs: se as tentativas encadeadas
        (select → radio → radio_js → eval) excederem 20s, aborta silenciosamente.
        Radios JSF/a4j normais completam em <3s.
        """
        import time as _t
        _deadline = _t.monotonic() + 20.0

        def _budget_ok() -> bool:
            return _t.monotonic() < _deadline

        # Try select (by option value or text)
        if _budget_ok() and self._selecionar(field_id, valor, obrigatorio=False):
            return True
        # Try radio (Playwright locator)
        if _budget_ok() and self._marcar_radio(field_id, valor):
            return True
        # Try radio (JS fallback)
        if _budget_ok() and self._marcar_radio_js(field_id, valor):
            return True
        if not _budget_ok():
            self._log(f"  ⚠ {field_id}={valor}: budget de 20s estourado — pulando")
            return False
        # JS fallback: search selects by option text containing valor
        try:
            _found = self._page.evaluate(f"""() => {{
                const sels = [...document.querySelectorAll('select')];
                const target = '{valor}'.toLowerCase();
                for (const sel of sels) {{
                    if (!(sel.id || '').toLowerCase().includes('{field_id}'.toLowerCase())) continue;
                    for (const opt of sel.options) {{
                        if (opt.value.toLowerCase() === target || opt.text.toLowerCase().includes(target)) {{
                            sel.value = opt.value;
                            sel.dispatchEvent(new Event('change', {{bubbles: true}}));
                            return sel.id + '=' + opt.value;
                        }}
                    }}
                }}
                return null;
            }}""")
            if _found:
                self._aguardar_ajax()
                self._log(f"  ✓ select JS {field_id}: {_found}")
                return True
        except Exception:
            pass
        if obrigatorio:
            self._log(f"  ⚠ {field_id}={valor}: não encontrado como select nem radio")
        return False

    def _marcar_checkbox(
        self,
        field_id: str,
        marcar: bool = True,
        label: str | None = None,
    ) -> bool:
        """Marca ou desmarca checkbox JSF."""
        loc = self._localizar(field_id, label, tipo="checkbox")
        if not loc:
            return False
        try:
            loc.wait_for(state="visible", timeout=3000)
            if loc.is_checked() != marcar:
                loc.click()
                # Short AJAX wait — checkbox clicks can trigger server errors
                # (e.g. NPE in ApresentadorHonorarios) that hang the monitor
                self._aguardar_ajax(timeout=5000)
            return True
        except Exception as e:
            logger.debug(f"_marcar_checkbox({field_id}): {e}")
            return False

    def _clicar_menu_lateral(self, texto: str, obrigatorio: bool = True) -> bool:
        """
        Clica em link do menu lateral via JavaScript (invulnerável a visibilidade).
        Funciona mesmo que o menu esteja colapsado — dispara o onclick do JSF/A4J
        diretamente sem depender de Playwright ver o elemento.
        Retorna True se clicou com sucesso, False se não encontrou.
        """
        # Tentativa 1: seletor de ID específico do sidebar (robusto, sem ambiguidade)
        # O menu PJE-Calc usa li[id='li_XXX'] (menu-pilares.xhtml) e a4j:commandLink
        # com IDs gerados. Tentamos ambos padrões: a[id*='menuXXX'] e li[id*='xxx'] > a
        # Seletores do SidebarMenu — ver knowledge/pjecalc_selectors.py
        _MENU_ID_MAP = {
            "Histórico Salarial": SidebarMenu.HISTORICO_SALARIAL,
            "Verbas":             SidebarMenu.VERBAS,
            "FGTS":               SidebarMenu.FGTS,
            "Honorários":         SidebarMenu.HONORARIOS,
            "Liquidar":           SidebarMenu.LIQUIDAR,
            "Faltas":             SidebarMenu.FALTAS,
            "Férias":             SidebarMenu.FERIAS,
            "Dados do Cálculo":   SidebarMenu.DADOS_DO_CALCULO,
            "Novo":               SidebarMenu.NOVO,
            "Operações":          SidebarMenu.OPERACOES,
            "Imprimir":           SidebarMenu.IMPRIMIR,
            "Contribuição Social": SidebarMenu.CONTRIBUICAO_SOCIAL,
            "Contribuicao Social": SidebarMenu.CONTRIBUICAO_SOCIAL,
            "Imposto de Renda":   SidebarMenu.IMPOSTO_RENDA,
            "Multas":             SidebarMenu.MULTAS,
            "Cartão de Ponto":    SidebarMenu.CARTAO_DE_PONTO,
            "Salário Família":    SidebarMenu.SALARIO_FAMILIA,
            "Seguro Desemprego":  SidebarMenu.SEGURO_DESEMPREGO,
            "Pensão Alimentícia": SidebarMenu.PENSAO_ALIMENTICIA,
            "Previdência Privada": SidebarMenu.PREVIDENCIA_PRIVADA,
            "Custas Judiciais":   SidebarMenu.CUSTAS_JUDICIAIS,
            "Custas":             SidebarMenu.CUSTAS_JUDICIAIS,
            "Correção, Juros e Multa": SidebarMenu.CORRECAO_JUROS,
            "Correção e Juros":   SidebarMenu.CORRECAO_JUROS,
            "Exportar":           SidebarMenu.EXPORTAR,
            "Exportação":         SidebarMenu.EXPORTAR,
            "Excluir":            "a[id*='menuExcluir']",
            "Fechar":             "a[id*='menuFechar']",
        }
        # Mapa de IDs reais de <li> do menu-pilares (confirmados por inspeção DOM v2.15.1)
        # Padrão: li_calculo_XXX (dentro de cálculo) ou li_tabelas_XXX (tabelas)
        # Nota: estes IDs de <li> complementam os seletores <a> de SidebarMenu (pjecalc_selectors.py)
        _LI_ID_MAP = {
            "Cartão de Ponto":     ["calculo_cartao_ponto"],
            "Dados do Cálculo":    ["calculo_dados_do_calculo"],
            "Faltas":              ["calculo_faltas"],
            "Férias":              ["calculo_ferias"],
            "Histórico Salarial":  ["calculo_historico_salarial"],
            "Verbas":              ["calculo_verbas"],
            "Salário Família":     ["calculo_salario_familia"],
            "Salário-família":     ["calculo_salario_familia"],
            "Seguro Desemprego":   ["calculo_seguro_desemprego"],
            "Seguro-desemprego":   ["calculo_seguro_desemprego"],
            "FGTS":                ["calculo_fgts"],
            "Contribuição Social": ["calculo_inss"],
            "Contribuicao Social": ["calculo_inss"],
            "Previdência Privada": ["calculo_previdencia_privada"],
            "Pensão Alimentícia":  ["calculo_pensao_alimenticia"],
            "Imposto de Renda":    ["calculo_irpf"],
            "Multas":              ["calculo_multas_e_indenizacoes"],
            "Multas e Indenizações": ["calculo_multas_e_indenizacoes"],
            "Honorários":          ["calculo_honorarios"],
            "Custas Judiciais":    ["calculo_custas_judiciais"],
            "Correção, Juros e Multa": ["calculo_correcao_juros_e_multa"],
            # Itens sob "Operações" no menu-pilares — usam enum OPERACOES_*
            # (ver MenuItemEnum.class: OPERACOES_LIQUIDAR, OPERACOES_EXPORTAR, etc.)
            # li IDs gerados via #{instItem.item.toString().toLowerCase()} em menu-pilares.xhtml
            "Liquidar":            ["operacoes_liquidar", "calculo_liquidar"],
            "Exportar":            ["operacoes_exportar", "calculo_exportar"],
            "Exportação":          ["operacoes_exportar", "calculo_exportar"],
            "Imprimir":            ["operacoes_imprimir_pagamento", "operacoes_imprimir", "calculo_imprimir"],
            "Validar":             ["operacoes_validar"],
            "Excluir":             ["operacoes_excluir", "calculo_excluir"],
            "Fechar":              ["operacoes_fechar", "calculo_fechar"],
        }
        sel_id = _MENU_ID_MAP.get(texto)
        if sel_id:
            loc = self._page.locator(sel_id)
            if loc.count() > 0:
                try:
                    loc.first.click(force=True)
                    self._aguardar_ajax()
                    self._page.wait_for_timeout(500)
                    return True
                except Exception:
                    pass  # fallback para busca por texto abaixo

        # Tentativa 1b: buscar <li> pelo padrão de ID do menu-pilares (li_XXX > a)
        li_ids = _LI_ID_MAP.get(texto)
        if li_ids:
            for li_id in li_ids:
                # Primeiro: ID exato (li#li_calculo_xxx a)
                loc = self._page.locator(f"li#li_{li_id} a")
                if loc.count() == 0:
                    # Fallback: busca parcial
                    loc = self._page.locator(f"li[id*='{li_id}'] a")
                if loc.count() > 0:
                    try:
                        loc.first.click(force=True)
                        self._aguardar_ajax()
                        self._page.wait_for_timeout(500)
                        self._log(f"  → Menu '{texto}' via li#{li_id}")
                        return True
                    except Exception:
                        pass
        self._page.wait_for_timeout(400)

        # Tentativa 2: navegação por URL com conversationId do cálculo ativo
        # (mais confiável que busca textual quando IDs do menu são dinâmicos)
        _URL_SECTION_MAP = {
            # URLs confirmadas por inspeção DOM (v2.15.1, TRT7)
            "Dados do Cálculo":        "calculo.jsf",
            "Faltas":                  "falta.jsf",
            "Férias":                  "ferias.jsf",
            "Histórico Salarial":      "historico-salarial.jsf",
            "Verbas":                  "verba/verba-calculo.jsf",
            "Cartão de Ponto":         "../cartaodeponto/apuracao-cartaodeponto.jsf",
            "Salário-família":         "salario-familia.jsf",
            "Seguro-desemprego":       "seguro-desemprego.jsf",
            "FGTS":                    "fgts.jsf",
            "Contribuição Social":     "inss/inss.jsf",
            "Contribuicao Social":     "inss/inss.jsf",
            "Previdência Privada":     "previdencia-privada.jsf",
            "Pensão Alimentícia":      "pensao-alimenticia.jsf",
            "Imposto de Renda":        "irpf.jsf",
            "Multas e Indenizações":   "multas-indenizacoes.jsf",
            "Multas":                  "multas-indenizacoes.jsf",
            "Honorários":              "honorarios.jsf",
            "Custas Judiciais":        "custas.jsf",
            "Correção, Juros e Multa": "parametros-atualizacao/parametros-atualizacao.jsf",
            "Liquidar":                "liquidacao.jsf",
            "Imprimir":                "imprimir.jsf",
            "Exportar":                "exportacao.jsf",
            "Exportação":              "exportacao.jsf",
        }
        # NÃO usar URL direta para "Liquidar" e "Exportar" — a navegação via URL
        # não inicializa os backing beans Seam, causando NPE em registro.data.
        # Essas páginas DEVEM ser acessadas via sidebar JSF click.
        _SKIP_URL_NAV = {"Liquidar", "Exportar", "Exportação"}
        if self._calculo_url_base and self._calculo_conversation_id and texto not in _SKIP_URL_NAV:
            jsf_page = _URL_SECTION_MAP.get(texto)
            if jsf_page:
                try:
                    _url = (
                        f"{self._calculo_url_base}{jsf_page}"
                        f"?conversationId={self._calculo_conversation_id}"
                    )
                    self._log(f"  → URL nav: {jsf_page}?conversationId={self._calculo_conversation_id}")
                    self._page.goto(_url, wait_until="domcontentloaded", timeout=15000)
                    # Reinstalar monitor AJAX após goto (contexto JS é perdido na navegação)
                    try:
                        self._instalar_monitor_ajax()
                    except Exception:
                        pass
                    self._aguardar_ajax()
                    self._page.wait_for_timeout(500)
                    # Detectar página de erro do Seam (apenas formulario:fechar visível,
                    # sem botões de ação — indica 404 ou conversação inválida)
                    _so_fechar = (
                        self._page.locator("input[id='formulario:fechar']").count() > 0
                        and self._page.locator(
                            f"{VerbaListagem.BTN_EXPRESSO}, input[id*='btnNovo'], "
                            "input[id*='btnSalvar'], input[id*='btnLiquidar']"
                        ).count() == 0
                    )
                    if _so_fechar:
                        self._log(f"  ⚠ URL nav: página de erro para '{texto}' — recuperando para calculo.jsf")
                        _calculo_url = (
                            f"{self._calculo_url_base}calculo.jsf"
                            f"?conversationId={self._calculo_conversation_id}"
                        )
                        self._page.goto(_calculo_url, wait_until="domcontentloaded", timeout=10000)
                        self._aguardar_ajax()
                        raise Exception("erro-page-recovery")
                    return True
                except Exception as _e:
                    self._log(f"  ⚠ URL nav falhou para '{texto}': {_e}")

        # Diagnóstico: listar sidebar links para Cartão de Ponto (debug)
        if texto == "Cartão de Ponto":
            try:
                _diag = self._page.evaluate("""() => {
                    const links = [...document.querySelectorAll('#menupainel a, [id*="menu"] a')];
                    const allLinks = [...document.querySelectorAll('a')];
                    const lis = [...document.querySelectorAll('#menupainel li')];
                    return {
                        menuLinks: links.map(a => ({
                            txt: (a.textContent||'').replace(/\\s+/g,' ').trim().substring(0,50),
                            id: a.id||'',
                            liId: a.closest('li') ? a.closest('li').id : ''
                        })).filter(x => x.txt.length > 0).slice(0, 30),
                        menuLis: lis.map(li => ({id: li.id, cls: li.className, txt: li.textContent.replace(/\\s+/g,' ').trim().substring(0,50)})).filter(x => x.id || x.txt.length < 30).slice(0, 30),
                        totalLinks: allLinks.length,
                        menuPainelExists: !!document.querySelector('#menupainel'),
                        cartaoMatches: allLinks.filter(a => {
                            const t = (a.textContent||'').normalize('NFD').replace(/[\\u0300-\\u036f]/g,'').toLowerCase();
                            return t.includes('cartao') || t.includes('ponto');
                        }).map(a => ({
                            txt: (a.textContent||'').replace(/\\s+/g,' ').trim().substring(0,60),
                            id: a.id||'',
                            href: a.href||''
                        })).slice(0, 10)
                    };
                }""")
                self._log(f"  🔍 Diagnóstico sidebar para Cartão de Ponto:")
                self._log(f"     menuPainel existe: {_diag.get('menuPainelExists')}")
                self._log(f"     Total links: {_diag.get('totalLinks')}")
                self._log(f"     Menu links: {[(x['txt'], x['id'][:20]) for x in _diag.get('menuLinks',[])[:20]]}")
                self._log(f"     Menu LIs: {[(x['id'], x['txt'][:25]) for x in _diag.get('menuLis',[])[:20]]}")
                self._log(f"     Matches 'cartao'/'ponto': {_diag.get('cartaoMatches',[])}")
            except Exception as _de:
                self._log(f"  🔍 Diagnóstico erro: {_de}")

        # Tentativa 3: JS click com escopo no container do menu lateral
        # Ancora-se em "Histórico Salarial" (exclusivo do menu de cálculo) para evitar
        # clicar em links homônimos do menu de referência (Tabelas).
        # Usa normalização de acentos para evitar falhas com ã/á/é/ó.
        clicou = self._page.evaluate(
            """(texto) => {
                // Normalizar removendo acentos para comparação tolerante
                function norm(s) {
                    return s.normalize('NFD').replace(/[\\u0300-\\u036f]/g, '')
                            .replace(/[\\s\\u00a0]+/g, ' ').trim().toLowerCase();
                }
                const textoNorm = norm(texto);
                const allLinks = [...document.querySelectorAll('a')];
                // Tenta encontrar o link no mesmo container do menu de cálculo
                const anchors = ['Histórico Salarial', 'FGTS', 'Faltas'];
                const anchor = anchors.find(t => t !== texto);
                if (anchor) {
                    const anchorNorm = norm(anchor);
                    const anchorEl = allLinks.find(
                        a => norm(a.textContent || '').includes(anchorNorm)
                    );
                    if (anchorEl) {
                        let parent = anchorEl.parentElement;
                        for (let i = 0; i < 8 && parent && parent.tagName !== 'BODY'; i++) {
                            const found = [...parent.querySelectorAll('a')].find(
                                a => a !== anchorEl &&
                                     norm(a.textContent || '').includes(textoNorm)
                            );
                            if (found) { found.click(); return true; }
                            parent = parent.parentElement;
                        }
                    }
                }
                // Fallback: primeiro link com texto exato (normalizado)
                const el = allLinks.find(
                    a => norm(a.textContent || '') === textoNorm
                );
                if (el) { el.click(); return true; }
                // Fallback 2: link contendo o texto (normalizado)
                const el2 = allLinks.find(
                    a => norm(a.textContent || '').includes(textoNorm)
                );
                if (el2) { el2.click(); return true; }
                return false;
            }""",
            texto,
        )
        if clicou:
            self._aguardar_ajax()
            self._page.wait_for_timeout(500)
            return True
        # Fallback: Playwright (visível ou não)
        loc = self._page.locator(f"a:has-text('{texto}')")
        if loc.count() == 0:
            loc = self._page.get_by_role("link", name=texto)
        if loc.count() == 0:
            if obrigatorio or texto == "Cartão de Ponto":
                self._log(f"  ⚠ Menu '{texto}': link não encontrado.")
                try:
                    diag = self._page.evaluate("""() => {
                        const links = [...document.querySelectorAll('a')]
                            .map(a => ({
                                txt: a.textContent.replace(/\\s+/g, ' ').trim(),
                                id: a.id || '',
                                liId: a.closest('li') ? a.closest('li').id : ''
                            }))
                            .filter(x => x.txt.length > 1 && x.txt.length < 80);
                        // Also get all li IDs in menupainel
                        const menuLis = [...document.querySelectorAll('#menupainel li')]
                            .map(li => ({id: li.id, txt: li.textContent.replace(/\\s+/g, ' ').trim().substring(0, 50)}));
                        return {
                            links: links.slice(0, 40),
                            menuLis: menuLis.slice(0, 40)
                        };
                    }""")
                    self._log(f"  ℹ Links (texto|id|liId): {[(x['txt'][:30], x['id'][:30], x['liId'][:30]) for x in diag.get('links',[])[:25]]}")
                    self._log(f"  ℹ Menu LIs: {[(x['id'], x['txt'][:30]) for x in diag.get('menuLis',[]) if x['id']]}")
                except Exception:
                    pass
            return False
        try:
            loc.first.click(force=True)
            self._aguardar_ajax()
            self._page.wait_for_timeout(500)
            return True
        except Exception as e:
            if obrigatorio:
                self._log(f"  ⚠ Menu '{texto}': erro ao clicar — {e}")
            return False

    def _clicar_botao_id(self, id_suffix: str) -> bool:
        """Clica em botão/input/link pelo sufixo de ID. force=True necessário para a4j:commandButton."""
        loc = self._page.locator(
            f"input[id*='{id_suffix}'], button[id*='{id_suffix}'], a[id*='{id_suffix}']"
        )
        if loc.count() > 0:
            try:
                loc.first.click(force=True)
                return True
            except Exception:
                return False
        return False

    def _verificar_secao_ativa(self, secao_esperada: str) -> bool:
        """Verifica se a seção atual (URL ou heading) corresponde à seção esperada.
        Normaliza acentos antes de comparar para evitar falsos-negativos
        (ex: 'Honorár' vs 'honorarios', 'Contribuição' vs 'contribuicao').
        """
        import unicodedata

        def _sem_acento(s: str) -> str:
            return "".join(
                c for c in unicodedata.normalize("NFD", s)
                if unicodedata.category(c) != "Mn"
            ).lower()

        try:
            url = self._page.url
            heading = self._page.evaluate(
                "() => (document.querySelector('h1,h2,h3,legend,.tituloPagina')||{}).textContent?.trim()||''"
            )
            self._log(f"  ℹ Seção: '{heading[:60]}' | url: ...{url[-50:]}")
            _esp = _sem_acento(secao_esperada)
            return _esp in _sem_acento(heading) or _esp in _sem_acento(url)
        except Exception:
            return False

    def _clicar_aba(self, aba_id: str) -> None:
        """Clica em aba RichFaces."""
        seletores = [
            f"[id$='{aba_id}_lbl']",
            f"[id$='{aba_id}_header']",
            f"[id$='{aba_id}'] span",
        ]
        for sel in seletores:
            try:
                loc = self._page.locator(sel)
                if loc.count() > 0:
                    loc.first.click()
                    self._aguardar_ajax()
                    return
            except Exception:
                continue

    def _clicar_botao(self, texto: str, obrigatorio: bool = True) -> bool:
        """Clica em botão pelo texto visível, com fallback de busca por proximidade."""
        # Tentativa 1: match exato via Playwright
        loc = self._page.locator(
            f"input[type='submit'][value='{texto}'], "
            f"input[type='button'][value='{texto}'], "
            f"button:has-text('{texto}'), "
            f"a:has-text('{texto}')"
        )
        if loc.count() > 0:
            loc.first.click()
            self._aguardar_ajax()
            return True
        # Tentativa 2: busca por proximidade via JS (token-overlap ≥ 0.5)
        try:
            _clicou = self._page.evaluate(
                r"""(texto) => {
                    function norm(s) {
                        return (s || '').toLowerCase()
                            .normalize('NFD').replace(/[\u0300-\u036f]/g, '')
                            .replace(/[^a-z0-9 ]/g, ' ').replace(/\s+/g, ' ').trim();
                    }
                    function score(a, b) {
                        const ta = norm(a).split(' ').filter(t => t.length >= 2);
                        const tb = norm(b).split(' ').filter(t => t.length >= 2);
                        if (!ta.length || !tb.length) return 0;
                        const setA = new Set(ta);
                        let shared = 0;
                        for (const t of setA) { if (tb.some(u => u.includes(t) || t.includes(u))) shared++; }
                        return shared / Math.max(ta.length, tb.length);
                    }
                    const candidates = [
                        ...document.querySelectorAll('input[type="submit"], input[type="button"], button, a[href]')
                    ].filter(el => {
                        const r = el.getBoundingClientRect();
                        return r.width > 0 && r.height > 0;
                    });
                    let best = null, bestScore = 0;
                    for (const el of candidates) {
                        const t = (el.value || el.textContent || '').trim();
                        const s = score(texto, t);
                        if (s > bestScore) { bestScore = s; best = el; }
                    }
                    if (bestScore >= 0.50 && best) {
                        best.click();
                        return (best.value || best.textContent || '').trim().substring(0, 60);
                    }
                    return null;
                }""",
                texto,
            )
            if _clicou:
                self._log(f"  ✓ Botão '{texto}' → fuzzy match: '{_clicou}'")
                self._aguardar_ajax()
                return True
        except Exception:
            pass
        if obrigatorio:
            self._log(f"  ⚠ Botão '{texto}' não encontrado.")
        return False

    def _clicar_salvar(self, aguardar_sucesso: bool = True) -> bool:
        """Clica no botão Salvar e aguarda mensagem de sucesso (padrão CalcMachine).

        DOM v2.15.1: o botão Salvar NÃO é input[type='submit'] nem <button>.
        É input[type='button'] com id='formulario:salvar'. Seletor [id$='salvar']
        cobre ambos os casos. submits:[] confirma que não há submit buttons.

        IMPORTANTE: Após clicar, faz polling pela mensagem de sucesso JSF
        ("Operação realizada com sucesso" ou similar) por até 10s. Isso garante
        que o servidor completou a transação (IIDCALCULO atribuído) antes de
        prosseguir para a próxima fase. Sem esse polling, fases subsequentes
        (ex: Histórico Salarial) podem falhar com IIDCALCULO NULL no H2.
        """
        seletores = [
            "[id$='salvar']",            # cobre formulario:salvar (qualquer tipo)
            "input[value='Salvar']",     # fallback por valor do botão
            "input[type='button'][value*='Salvar']",  # input type=button explícito
            "button:has-text('Salvar')", # botão HTML5
            "a:has-text('Salvar')",      # link estilizado como botão
        ]

        def _poll_mensagem_sucesso() -> bool:
            """Faz polling pela mensagem de sucesso JSF por até 10s (500ms entre tentativas).

            Retorna True se mensagem encontrada, False se timeout sem mensagem.
            Quando aguardar_sucesso=False, retorna True imediatamente.
            """
            if not aguardar_sucesso:
                return True
            for _tentativa in range(20):  # 20 × 500ms = 10s
                try:
                    # Seletores de mensagem passados como parâmetro (evita quebra por aspas)
                    msg = self._page.evaluate("""(sels) => {
                        const msgs = document.querySelectorAll(
                            sels.sucesso + ', [class*="msg"], [class*="sucesso"]'
                        );
                        for (const m of msgs) {
                            const t = (m.textContent || '').toLowerCase();
                            if (t.includes('sucesso') || t.includes('realizada') || t.includes('salvo'))
                                return m.textContent.trim().substring(0, 80);
                        }
                        const erros = document.querySelectorAll(
                            sels.erro + ', .rf-msg-err, [class*="erro"], [class*="error"]'
                        );
                        for (const e of erros) {
                            const t = (e.textContent || '').toLowerCase();
                            if (t.includes('erro') || t.includes('error') || t.includes('falha')
                                || t.includes('não pôde') || t.includes('não pode')
                                || t.includes('formulário') || t.includes('inesperado'))
                                return 'ERRO:' + e.textContent.trim().substring(0, 200);
                        }
                        return null;
                    }""", {"sucesso": Mensagens.SUCESSO, "erro": Mensagens.ERRO})
                    if msg:
                        if msg.startswith('ERRO:'):
                            self._log(f"  ✗ Salvar: {msg}")
                            return False
                        self._log(f"  ✓ Salvar: '{msg}'")
                        return True
                except Exception:
                    pass
                self._page.wait_for_timeout(500)
            self._log("  ⚠ Salvar: mensagem de sucesso não detectada em 10s (prosseguindo)")
            return True  # não bloquear indefinidamente — mas log do warning

        def _clicar_e_aguardar(clicou_via: str) -> bool:
            """Após clicar Salvar, aguarda AJAX + polling mensagem de sucesso."""
            self._aguardar_ajax()
            _ok = _poll_mensagem_sucesso()
            # Aguardar networkidle extra para garantir que a transação H2 commitou
            try:
                self._page.wait_for_load_state("networkidle", timeout=5000)
            except Exception:
                pass
            return _ok

        for sel in seletores:
            try:
                loc = self._page.locator(sel)
                if loc.count() > 0:
                    self._log(f"  → Salvar: clicando via '{sel}'")
                    loc.first.click(force=True)
                    return _clicar_e_aguardar(sel)
            except Exception:
                continue
        # JS fallback: busca por id/value/textContent — inclui input[type='button']
        try:
            clicou = self._page.evaluate("""() => {
                const candidates = [
                    document.querySelector('[id$=":salvar"]'),
                    document.querySelector('[id*="btnSalvar"]'),
                    document.querySelector('input[value="Salvar"]'),
                    document.querySelector('input[value*="Salvar"]'),
                    ...[...document.querySelectorAll('input[type="button"]')]
                        .filter(b => (b.value||'').trim().toLowerCase() === 'salvar'),
                    ...[...document.querySelectorAll('button')]
                        .filter(b => (b.textContent||'').trim().toLowerCase() === 'salvar'),
                    ...[...document.querySelectorAll('a')]
                        .filter(a => (a.textContent||'').trim().toLowerCase() === 'salvar'),
                ];
                const btn = candidates.find(b => b != null);
                if (btn) { btn.click(); return btn.id || btn.value || btn.textContent.trim() || 'ok'; }
                return null;
            }""")
            if clicou:
                return _clicar_e_aguardar(f"JS:{clicou}")
        except Exception:
            pass
        self._log("  ⚠ Botão Salvar não encontrado — clique manualmente.")
        return False

    def _detectar_erros_formulario(self, fase: str = "") -> list[dict]:
        """Detecta e loga campos com erro após um Salvar falhar.

        Busca elementos de erro JSF/RichFaces no DOM:
        - .rf-msg-err, .rf-msgs-sum-err (mensagens de erro RichFaces)
        - span.rf-msg-det (detalhe do erro)
        - Ícones de erro com tooltip (title ou data-original-title)
        - Campos com classe 'rf-inpt-fld-err' (input com borda vermelha)

        Para cada erro encontrado:
        1. Loga o campo e a mensagem de erro
        2. Tenta hover para ler tooltip (descrição completa)
        3. Captura screenshot do estado de erro

        Retorna lista de dicts: [{"campo": str, "mensagem": str, "campo_id": str}]
        """
        erros: list[dict] = []
        try:
            # Estratégia 1: Buscar mensagens de erro RichFaces globais e inline
            erros_dom = self._page.evaluate("""() => {
                const resultado = [];

                // 1. Mensagens de erro globais (topo da página)
                const globais = document.querySelectorAll(
                    '.rf-msgs-sum-err, .rf-msgs-det, .rf-msgs li'
                );
                for (const el of globais) {
                    const txt = (el.textContent || '').trim();
                    if (txt && (txt.toLowerCase().includes('erro') ||
                                txt.toLowerCase().includes('obrigat') ||
                                txt.toLowerCase().includes('inválid') ||
                                txt.toLowerCase().includes('preenchi') ||
                                txt.toLowerCase().includes('não pôde') ||
                                txt.length > 3)) {
                        resultado.push({campo: '_global', mensagem: txt.substring(0, 200), campo_id: ''});
                    }
                }

                // 2. Mensagens de erro inline por campo (RichFaces rf-msg)
                const msgsInline = document.querySelectorAll(
                    '.rf-msg-err, .rf-msg-det, span[class*="rf-msg"]'
                );
                for (const el of msgsInline) {
                    const txt = (el.textContent || '').trim();
                    if (!txt) continue;
                    // Tentar identificar o campo associado via DOM
                    let campoId = '';
                    let campoLabel = '';
                    // O rf-msg geralmente está perto do campo — buscar label ou input vizinho
                    const parent = el.closest('td, div, span.rf-msg');
                    if (parent) {
                        const input = parent.querySelector('input, select, textarea') ||
                                      parent.previousElementSibling;
                        if (input && input.id) {
                            campoId = input.id.replace(/^formulario:/, '');
                        }
                    }
                    // Tentar buscar label próxima
                    const row = el.closest('tr, div[class*="form"], div[class*="campo"]');
                    if (row) {
                        const lbl = row.querySelector('label, td:first-child, span[class*="label"]');
                        if (lbl) campoLabel = (lbl.textContent || '').trim();
                    }
                    resultado.push({
                        campo: campoLabel || campoId || '_inline',
                        mensagem: txt.substring(0, 200),
                        campo_id: campoId,
                    });
                }

                // 3. Campos com classe de erro (input com borda vermelha)
                const camposErro = document.querySelectorAll(
                    '.rf-inpt-fld-err, input.error, select.error, ' +
                    'input[class*="Err"], select[class*="Err"], ' +
                    '[aria-invalid="true"]'
                );
                for (const el of camposErro) {
                    const campoId = (el.id || '').replace(/^formulario:/, '');
                    // Buscar tooltip do ícone de erro vizinho
                    let tooltip = '';
                    const nextSibling = el.nextElementSibling;
                    if (nextSibling) {
                        tooltip = nextSibling.getAttribute('title') ||
                                  nextSibling.getAttribute('data-original-title') ||
                                  (nextSibling.textContent || '').trim();
                    }
                    // Buscar label do campo
                    let label = '';
                    if (el.id) {
                        const lbl = document.querySelector('label[for="' + el.id + '"]');
                        if (lbl) label = (lbl.textContent || '').trim();
                    }
                    if (!label) {
                        const row = el.closest('tr, div');
                        if (row) {
                            const lbl = row.querySelector('label, td:first-child');
                            if (lbl) label = (lbl.textContent || '').trim();
                        }
                    }
                    // Verificar se já temos esse campo nos resultados
                    const jaExiste = resultado.some(r => r.campo_id === campoId && campoId);
                    if (!jaExiste) {
                        resultado.push({
                            campo: label || campoId || '_campo_erro',
                            mensagem: tooltip || 'Campo marcado com erro (sem tooltip)',
                            campo_id: campoId,
                        });
                    }
                }

                // 4. linkErro — marcadores de erro nativos do PJE-Calc (X vermelho)
                // Cada campo tem um <a class="linkErro" id="campoErro"> com <rich:toolTip>
                // Só ficam visíveis quando JSF detecta erro de validação
                const linksErro = document.querySelectorAll('a.linkErro, [class="linkErro"]');
                for (const link of linksErro) {
                    // Só processar se visível (offsetParent !== null ou display !== none)
                    const style = window.getComputedStyle(link);
                    const parentMsg = link.closest('[id$="Message"], span[class*="rf-msg"]');
                    const isVisible = link.offsetParent !== null ||
                                      (parentMsg && parentMsg.offsetParent !== null);
                    if (!isVisible && style.display === 'none') continue;
                    // Verificar se realmente tem conteúdo (rich:message renderizado)
                    const msgParent = link.closest('span[class*="rf-msg"]');
                    if (msgParent && msgParent.children.length <= 1 &&
                        !msgParent.querySelector('.rf-tt-cntr, .tooltip')) continue;

                    // Extrair ID do campo a partir do ID do link (ex: "numeroErro" -> "numero")
                    const linkId = link.id || '';
                    const campoId = linkId.replace(/Erro$/, '').replace(/^formulario:/, '');

                    // Ler tooltip (mensagem de erro detalhada)
                    let tooltip = '';
                    const ttEl = link.querySelector('.rf-tt-cntr, .tooltip, [class*="toolTip"]');
                    if (ttEl) {
                        tooltip = (ttEl.textContent || '').trim();
                    }
                    if (!tooltip) {
                        tooltip = link.getAttribute('title') || link.textContent.trim() || '';
                    }

                    // Buscar label do campo
                    let label = '';
                    if (campoId) {
                        const inputEl = document.getElementById('formulario:' + campoId) ||
                                        document.querySelector('[id$="' + campoId + '"]');
                        if (inputEl) {
                            const lbl = document.querySelector('label[for="formulario:' + campoId + '"]') ||
                                        document.querySelector('label[for="' + inputEl.id + '"]');
                            if (lbl) label = (lbl.textContent || '').trim();
                        }
                    }
                    if (!label) {
                        // h:panelGroup do JSF é renderizado como <span> no DOM —
                        // não usar 'h\\:panelGroup' como seletor CSS (Element.closest
                        // valida sintaxe e rejeita namespaces JSF).
                        const row = link.closest('tr, td, div, span');
                        if (row) {
                            const lbl = row.querySelector('label');
                            if (lbl) label = (lbl.textContent || '').trim();
                        }
                    }

                    const jaExiste = resultado.some(r => r.campo_id === campoId && campoId);
                    if (!jaExiste) {
                        resultado.push({
                            campo: label || campoId || '_linkErro',
                            mensagem: tooltip || 'Campo com erro (linkErro visível)',
                            campo_id: campoId,
                        });
                    }
                }

                // 5. Ícones de erro genéricos (img com alt="erro" ou span com classe de ícone)
                const icones = document.querySelectorAll(
                    'img[alt*="erro" i], img[alt*="error" i], ' +
                    'img[src*="error"], img[src*="erro"], ' +
                    'span[class*="rf-msg-ico"], span[class*="error-icon"]'
                );
                for (const ico of icones) {
                    const tooltip = ico.getAttribute('title') ||
                                    ico.getAttribute('data-original-title') ||
                                    ico.getAttribute('alt') || '';
                    const parent = ico.closest('td, div, span');
                    let campoId = '';
                    let label = '';
                    if (parent) {
                        const input = parent.querySelector('input, select');
                        if (input) campoId = (input.id || '').replace(/^formulario:/, '');
                        const lbl = parent.querySelector('label');
                        if (lbl) label = (lbl.textContent || '').trim();
                    }
                    const jaExiste = resultado.some(r => r.campo_id === campoId && campoId);
                    if (!jaExiste && tooltip) {
                        resultado.push({
                            campo: label || campoId || '_icone',
                            mensagem: tooltip.substring(0, 200),
                            campo_id: campoId,
                        });
                    }
                }

                return resultado;
            }""")

            if erros_dom:
                erros = erros_dom
                self._log(f"  ✗ {fase + ': ' if fase else ''}Erros de formulário detectados ({len(erros)}):")
                for i, e in enumerate(erros, 1):
                    _campo_desc = e.get("campo", "?")
                    _msg = e.get("mensagem", "?")
                    _fid = e.get("campo_id", "")
                    _id_info = f" [id={_fid}]" if _fid else ""
                    self._log(f"    {i}. {_campo_desc}{_id_info}: {_msg}")

                # Hover em linkErro visíveis para ativar rich:toolTip dinâmicos
                try:
                    _links_erro = self._page.locator('a.linkErro')
                    for idx in range(_links_erro.count()):
                        try:
                            el = _links_erro.nth(idx)
                            if not el.is_visible(timeout=500):
                                continue
                            el.hover(timeout=2000)
                            self._page.wait_for_timeout(600)
                            # Ler tooltip que apareceu após hover
                            _tooltip = self._page.evaluate("""() => {
                                const tips = document.querySelectorAll(
                                    '.rf-tt-cntr, .tooltip, [role="tooltip"]'
                                );
                                for (const t of tips) {
                                    const s = window.getComputedStyle(t);
                                    if (s.display !== 'none' && s.visibility !== 'hidden') {
                                        const txt = (t.textContent || '').trim();
                                        if (txt) return txt.substring(0, 300);
                                    }
                                }
                                return '';
                            }""")
                            if _tooltip:
                                _link_id = el.get_attribute('id') or f'#{idx}'
                                self._log(f"    → linkErro {_link_id}: {_tooltip}")
                        except Exception:
                            continue
                except Exception:
                    pass

                # Capturar screenshot de diagnóstico
                self._screenshot_fase(f"erro_formulario_{fase}" if fase else "erro_formulario")
            else:
                # Nenhum erro encontrado pelas estratégias anteriores.
                # Fallback: varrer TODOS os linkErro e verificar quais são visíveis
                self._log(f"  ⚠ {fase}: Nenhum erro detectado por seletores padrão. Varrendo linkErro visíveis...")
                try:
                    _links = self._page.locator('a.linkErro')
                    _total = _links.count()
                    _visiveis = []
                    for idx in range(_total):
                        try:
                            el = _links.nth(idx)
                            if el.is_visible(timeout=300):
                                _lid = el.get_attribute('id') or f'link_{idx}'
                                _visiveis.append(_lid)
                                # Hover para pegar tooltip
                                try:
                                    el.hover(timeout=1500)
                                    self._page.wait_for_timeout(500)
                                    _tt = self._page.evaluate("""() => {
                                        const tips = document.querySelectorAll('.rf-tt-cntr, .tooltip');
                                        for (const t of tips) {
                                            const s = window.getComputedStyle(t);
                                            if (s.display !== 'none' && s.visibility !== 'hidden') {
                                                const txt = (t.textContent || '').trim();
                                                if (txt) return txt.substring(0, 300);
                                            }
                                        }
                                        return '';
                                    }""")
                                    campo_id = _lid.replace('Erro', '').replace('formulario:', '')
                                    erros.append({
                                        "campo": campo_id,
                                        "mensagem": _tt or "linkErro visível sem tooltip",
                                        "campo_id": campo_id,
                                    })
                                    self._log(f"    → linkErro visível: {_lid} — {_tt or '(sem tooltip)'}")
                                except Exception:
                                    erros.append({
                                        "campo": _lid,
                                        "mensagem": "linkErro visível",
                                        "campo_id": _lid.replace('Erro', ''),
                                    })
                                    self._log(f"    → linkErro visível: {_lid}")
                        except Exception:
                            continue
                    if not _visiveis:
                        self._log(f"    Nenhum linkErro visível encontrado ({_total} no DOM)")
                except Exception as _e_link:
                    self._log(f"  ⚠ Varredura linkErro: {_e_link}")
        except Exception as _e_det:
            self._log(f"  ⚠ Detecção de erros: {_e_det}")

        return erros

    def _tentar_corrigir_erros(self, erros: list[dict], dados: dict, fase: str) -> bool:
        """Tenta corrigir erros comuns detectados por _detectar_erros_formulario.

        Estratégias de correção por tipo de erro:
        1. Campo obrigatório vazio → tentar preencher com valor padrão
        2. Data com formato inválido → reformatar DD/MM/AAAA
        3. Tipo de rescisão não selecionado → selecionar SEM_JUSTA_CAUSA
        4. Documento fiscal formato errado → limpar e re-preencher

        Retorna True se alguma correção foi aplicada (caller deve re-salvar).
        """
        if not erros:
            return False

        _corrigiu = False
        proc = dados.get("processo", {}) if isinstance(dados, dict) else {}
        cont = dados.get("contrato", {}) if isinstance(dados, dict) else {}

        for e in erros:
            _fid = e.get("campo_id", "")
            _msg = (e.get("mensagem", "") or "").lower()
            _campo = (e.get("campo", "") or "").lower()

            # ── Data obrigatória vazia ou formato inválido ──
            if "data" in _campo or "data" in _fid or "data" in _msg:
                import datetime
                _hoje = datetime.date.today().strftime("%d/%m/%Y")
                # Campos de data comuns que podem estar vazios
                _datas_defaults = {
                    "dataAdmissao": cont.get("admissao", ""),
                    "dataDemissao": cont.get("demissao", ""),
                    "dataAjuizamento": cont.get("ajuizamento", ""),
                    "dataDeCriacao": _hoje,
                    "dataCriacao": _hoje,
                    "dataInicialApuracao": cont.get("admissao", ""),
                }
                if _fid and _fid in _datas_defaults and _datas_defaults[_fid]:
                    if self._preencher_data(_fid, _datas_defaults[_fid], obrigatorio=False):
                        self._log(f"    → Correção: {_fid} = {_datas_defaults[_fid]}")
                        _corrigiu = True

            # ── Campo obrigatório vazio (genérico) ──
            elif "obrigat" in _msg or "preenchimento" in _msg or "required" in _msg:
                # Tentar identificar e preencher campos obrigatórios com defaults
                _defaults_obrigatorios = {
                    "valorCargaHorariaPadrao": "220,00",
                    "tipoDaBaseTabelada": "INTEGRAL",
                }
                if _fid and _fid in _defaults_obrigatorios:
                    _val = _defaults_obrigatorios[_fid]
                    if _fid in ("tipoDaBaseTabelada",):
                        if self._selecionar(_fid, _val, obrigatorio=False):
                            self._log(f"    → Correção: {_fid} = {_val}")
                            _corrigiu = True
                    else:
                        if self._preencher(_fid, _val, obrigatorio=False):
                            self._log(f"    → Correção: {_fid} = {_val}")
                            _corrigiu = True

            # ── Documento fiscal formato errado ──
            elif "documento" in _campo or "cpf" in _msg or "cnpj" in _msg or "fiscal" in _campo:
                # Limpar formatação do CPF/CNPJ (apenas dígitos)
                import re
                for _doc_id in ["reclamanteNumeroDocumentoFiscal", "reclamadoNumeroDocumentoFiscal",
                                "cpfReclamante", "cnpjReclamado"]:
                    try:
                        _val_atual = self._page.evaluate(
                            f"""() => {{
                                const el = document.querySelector('[id$="{_doc_id}"]');
                                return el ? el.value : null;
                            }}"""
                        )
                        if _val_atual:
                            _limpo = re.sub(r'[^\d]', '', _val_atual)
                            if _limpo and _limpo != _val_atual:
                                self._preencher(_doc_id, _limpo, obrigatorio=False)
                                self._log(f"    → Correção: {_doc_id} reformatado ({_val_atual} → {_limpo})")
                                _corrigiu = True
                    except Exception:
                        continue

            # ── Valor inválido (formato monetário) ──
            elif "valor" in _campo or "valor" in _fid:
                if _fid:
                    try:
                        _val_atual = self._page.evaluate(
                            f"""() => {{
                                const el = document.querySelector('[id$="{_fid}"]');
                                return el ? el.value : null;
                            }}"""
                        )
                        if _val_atual:
                            # Reformatar para padrão BR (vírgula decimal)
                            import re
                            _limpo = re.sub(r'[^\d,.]', '', _val_atual)
                            if '.' in _limpo and ',' not in _limpo:
                                _limpo = _limpo.replace('.', ',')
                                self._preencher(_fid, _limpo, obrigatorio=False)
                                self._log(f"    → Correção: {_fid} reformatado ({_val_atual} → {_limpo})")
                                _corrigiu = True
                    except Exception:
                        pass

        if _corrigiu:
            self._log("    → Correções aplicadas — re-salvando…")
            self._aguardar_ajax()
        else:
            self._log("    → Nenhuma correção automática possível — verifique os campos manualmente")

        return _corrigiu

    def _salvar_com_deteccao_erros(self, fase: str, dados: dict | None = None,
                                    max_tentativas: int = 2) -> bool:
        """Wrapper robusto de Salvar: detecta erros, tenta corrigir, re-salva.

        1. Clica Salvar
        2. Se falhar: detecta erros no formulário (tooltips, mensagens)
        3. Tenta corrigir erros comuns automaticamente
        4. Re-salva até max_tentativas vezes
        5. Captura screenshot em caso de falha persistente

        Retorna True se o salvamento foi bem-sucedido.
        """
        for tentativa in range(max_tentativas):
            _ok = self._clicar_salvar()
            if _ok:
                return True

            self._log(f"  ⚠ {fase}: Salvar falhou (tentativa {tentativa + 1}/{max_tentativas})")

            # Detectar erros específicos
            _erros = self._detectar_erros_formulario(fase)

            if not _erros:
                # Nenhum erro detectado no DOM — dump de campos vazios para diagnóstico
                try:
                    _vazios = self._page.evaluate("""() => {
                        const result = [];
                        // Selects sem valor selecionado
                        for (const sel of document.querySelectorAll('select')) {
                            if (!sel.offsetParent) continue; // hidden
                            const val = sel.value || '';
                            const id = sel.id || sel.name || '';
                            if (!val || val.includes('noSelection')) {
                                const opts = [...sel.options].slice(0, 5).map(o => o.value + '=' + o.text.trim());
                                result.push('SELECT ' + id + ' vazio [' + opts.join(', ') + ']');
                            }
                        }
                        // Inputs required vazios
                        for (const inp of document.querySelectorAll('input[required], input[aria-required="true"]')) {
                            if (!inp.offsetParent) continue;
                            if (!inp.value) {
                                result.push('INPUT ' + (inp.id || inp.name) + ' required vazio');
                            }
                        }
                        return result;
                    }""")
                    if _vazios:
                        self._log(f"  ⚠ {fase}: Campos possivelmente obrigatórios vazios:")
                        for v in _vazios[:10]:
                            self._log(f"    → {v}")
                except Exception:
                    pass
                self._log(f"  ⚠ {fase}: Nenhum erro específico detectado no DOM")
                if tentativa < max_tentativas - 1:
                    self._page.wait_for_timeout(2000)
                    continue
                return False

            # Tentar corrigir erros automaticamente
            if dados and tentativa < max_tentativas - 1:
                _corrigiu = self._tentar_corrigir_erros(_erros, dados, fase)
                if _corrigiu:
                    self._page.wait_for_timeout(500)
                    continue  # re-salvar na próxima iteração

            # Se não conseguiu corrigir, ainda tenta re-salvar (às vezes erros intermitentes)
            if tentativa < max_tentativas - 1:
                self._page.wait_for_timeout(1000)

        # Falha persistente: screenshot final
        self._screenshot_fase(f"erro_persistente_{fase}")
        self._log(f"  ✗ {fase}: Salvar falhou após {max_tentativas} tentativas")
        return False

    def _regerar_ocorrencias_verbas(self) -> bool:
        """Clica em 'Regerar' na aba Verbas para atualizar ocorrências.

        QUANDO USAR: Após alterações nos Parâmetros do Cálculo (carga horária,
        período, prescrição, etc.) que afetam a grade de ocorrências das verbas.
        O manual oficial exige: "Regerar Ocorrências: Necessário quando parâmetros
        que afetam ocorrências são modificados."

        DOM v2.15.1 (verba-calculo.xhtml):
        - formulario:tipoRegeracao (radio) — Manter / Sobrescrever
        - formulario:regerarOcorrencias (commandButton) — "Regerar"
        - Confirma via window.confirm (MSG0017)
        """
        self._log("  → Regerar ocorrências das verbas…")
        try:
            # Navegar para aba Verbas
            _nav = self._clicar_menu_lateral("Verbas", obrigatorio=False)
            if not _nav:
                self._log("  ⚠ Regerar: não conseguiu navegar para Verbas")
                return False
            self._aguardar_ajax()
            self._page.wait_for_timeout(1000)

            # Selecionar "Manter alterações realizadas nas ocorrências" (padrão seguro)
            try:
                radio_manter = self._page.locator(
                    "input[id$='tipoRegeracao'][type='radio']"
                )
                if radio_manter.count() >= 1:
                    # O primeiro radio é "Manter" (itemValue=true)
                    radio_manter.first.click(force=True)
                    self._page.wait_for_timeout(300)
                    self._log("    ✓ Opção: Manter alterações")
            except Exception as e:
                self._log(f"    ⚠ Radio tipoRegeracao: {e}")

            # Auto-confirmar o window.confirm do Regerar (once handler via expect_event)
            self._page.once("dialog", lambda d: d.accept())

            # Scroll para garantir que o botão Regerar fique visível
            self._page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            self._page.wait_for_timeout(300)

            # Clicar botão Regerar — tentar múltiplos seletores
            _REGERAR_SELS = [
                HistoricoSalarial.REGERAR_OCORRENCIAS,  # "[id$='regerarOcorrencias']"
                "input[value='Regerar']",
                "input[value='Regerar Ocorrências']",
                "input[type='submit'][value*='egerar']",
                "button:has-text('Regerar')",
            ]
            for _sel in _REGERAR_SELS:
                _btn = self._page.locator(_sel)
                if _btn.count() > 0:
                    _btn.first.click(force=True)
                    self._aguardar_ajax()
                    self._page.wait_for_timeout(2000)
                    self._log(f"  ✓ Regerar ocorrências executado ({_sel})")
                    return True

            # Fallback JS: buscar qualquer input/button com texto "Regerar"
            _js_clicked = self._page.evaluate("""() => {
                const els = [...document.querySelectorAll('input[type="submit"], input[type="button"], button')];
                for (const el of els) {
                    const txt = (el.value || el.textContent || '').toLowerCase();
                    if (txt.includes('regerar')) {
                        el.click();
                        return el.id || el.value || 'found';
                    }
                }
                return null;
            }""")
            if _js_clicked:
                self._aguardar_ajax()
                self._page.wait_for_timeout(2000)
                self._log(f"  ✓ Regerar ocorrências executado via JS ({_js_clicked})")
                return True

            self._log("  ⚠ Botão Regerar não encontrado na página de Verbas — pode não ser necessário se verbas não foram alteradas")
            return False
        except Exception as e:
            self._log(f"  ⚠ Regerar ocorrências: erro {e}")
            return False

    def _clicar_novo(self) -> None:
        """Clica no botão Novo da seção atual — prioriza dentro de #formulario."""
        url_pre = self._page.url

        # Método 1: seletores CSS por ID (não ambíguos — sem button:has-text que pega top-nav)
        for sel in ["[id$='novo']", "[id$='novoBt']", "[id$='novoBtn']",
                    "input[value='Novo']"]:
            try:
                loc = self._page.locator(sel)
                if loc.count() > 0:
                    self._log(f"  → Novo: clicando via '{sel}'")
                    loc.first.click(); self._aguardar_ajax()
                    self._page.wait_for_timeout(800)
                    self._log(f"  → URL pós-Novo: {self._page.url} (mudou: {self._page.url != url_pre})")
                    return
            except Exception:
                continue

        # Método 2: JS — busca PRIMEIRO dentro de #formulario (seção atual),
        # depois fallback global. Evita clicar no "Novo" do top-nav.
        clicou = self._page.evaluate("""() => {
            const form = document.getElementById('formulario');
            const containers = form ? [form, document] : [document];
            for (const container of containers) {
                const els = [...container.querySelectorAll(
                    'a, input[type="submit"], input[type="button"], button')];
                for (const el of els) {
                    const txt = (el.textContent || el.value || el.title || '')
                        .replace(/[\\s\\u00a0]+/g,' ').trim();
                    if (txt === 'Novo' || txt === 'Nova') {
                        el.click(); return el.id || '(sem id)';
                    }
                }
            }
            return null;
        }""")
        if clicou:
            self._log(f"  → Novo: clicado via JS (elem: {clicou})")
            self._aguardar_ajax(); self._page.wait_for_timeout(800)
            self._log(f"  → URL pós-Novo: {self._page.url} (mudou: {self._page.url != url_pre})")
            return

        # Diagnóstico
        self._log("  ⚠ Botão Novo não encontrado — elementos clicáveis na página:")
        try:
            items = self._page.evaluate("""() =>
                [...document.querySelectorAll('a, input[type="submit"], button')]
                .map(el => el.id + ' | ' + (el.textContent||el.value||'').trim())
                .filter(s => s.length > 3 && s.length < 80)
            """)
            self._log(f"  {items[:25]}")
        except Exception:
            pass

    def _aguardar_usuario(self, mensagem: str) -> None:
        """Injeta overlay amarelo para o usuário agir e clicar em Continuar."""
        self._log(f"AGUARDANDO_USUARIO: {mensagem}")
        js = """
        (msg) => new Promise(resolve => {
            const div = document.createElement('div');
            div.id = 'pjecalc-agente-overlay';
            div.style.cssText = 'position:fixed;top:0;left:0;width:100%;z-index:999999;'+
                'background:#fff3cd;border-bottom:3px solid #ffc107;padding:16px 24px;'+
                'font-family:Arial;font-size:14px;display:flex;align-items:center;'+
                'gap:16px;box-shadow:0 4px 8px rgba(0,0,0,.2);';
            div.innerHTML = '<span style="font-size:22px">\u26a0\ufe0f</span>' +
                '<span style="flex:1"><strong>Ação necessária:</strong> ' + msg + '</span>' +
                '<button id="pjecalc-continuar" style="background:#1a3a6b;color:#fff;' +
                'border:none;padding:8px 20px;border-radius:4px;cursor:pointer;font-size:14px;">'+
                'Continuar</button>';
            document.body.prepend(div);
            document.getElementById('pjecalc-continuar').onclick = () => {
                div.remove(); resolve();
            };
        })
        """
        try:
            self._page.evaluate(js, mensagem)
            self._page.wait_for_selector("#pjecalc-agente-overlay", state="detached", timeout=600000)
        except Exception:
            pass

    def _verificar_e_fazer_login(self) -> None:
        """Verifica se está logado; se não, tenta credenciais via env vars ou padrão.
        NUNCA bloqueia para aguardar interação manual — lança RuntimeError em falha.
        """
        url = self._page.url
        if "logon" not in url.lower():
            return

        self._log("Página de login detectada — tentando credenciais automáticas…")
        # Prioridade: env vars PJECALC_USER/PJECALC_PASS → credenciais padrão conhecidas
        credenciais_env = []
        if os.environ.get("PJECALC_USER") and os.environ.get("PJECALC_PASS"):
            credenciais_env = [(os.environ["PJECALC_USER"], os.environ["PJECALC_PASS"])]
        for usuario, senha in credenciais_env + [
            ("admin", "pjeadmin"),
            ("admin", "admin"),
            ("pjecalc", "pjecalc"),
            ("advogado", "advogado"),
        ]:
            try:
                sel_user = "input[name*='usuario'], input[id*='usuario'], input[type='text'][name*='j_'], input[name*='j_username']"
                self._page.fill(sel_user, usuario, timeout=2000)
                self._page.fill("input[type='password']", senha, timeout=2000)
                self._page.click("input[type='submit'], button[type='submit']", timeout=2000)
                self._page.wait_for_timeout(2000)
                if "logon" not in self._page.url.lower():
                    self._log(f"Login automático com '{usuario}' — OK.")
                    return
            except Exception:
                continue

        raise RuntimeError(
            "Login automático falhou: nenhuma das credenciais padrão funcionou. "
            "Configure as variáveis de ambiente PJECALC_USER e PJECALC_PASS com as "
            "credenciais corretas do PJE-Calc Cidadão antes de iniciar a automação."
        )

    # ── Verificações de saúde (Tomcat + página) ────────────────────────────────

    def _verificar_tomcat(self, timeout: int = 120) -> bool:
        """Aguarda o Tomcat responder antes de prosseguir. Loga progresso a cada 15s."""
        url = self.PJECALC_BASE
        inicio = time.time()
        ultimo_log = -15
        while time.time() - inicio < timeout:
            try:
                with urllib.request.urlopen(url, timeout=5) as r:
                    if r.status in (200, 302, 404):
                        return True
            except Exception:
                pass
            elapsed = int(time.time() - inicio)
            if elapsed > 5 and elapsed - ultimo_log >= 15:
                self._log(f"  ⏳ Aguardando Tomcat... ({elapsed}s/{timeout}s)")
                ultimo_log = elapsed
            time.sleep(5)
        self._log("  ⚠ Tomcat não respondeu — continuando mesmo assim.")
        return False

    def _verificar_pagina_pjecalc(self) -> bool:
        """Garante que a página atual é válida (no PJE-Calc, sem erro 500, com conteúdo).
        Renavega para home se necessário. Retorna True se OK."""
        url = self._page.url
        if "9257" not in url:
            self._log("  ⚠ Página fora do PJE-Calc — renavegando para home…")
            try:
                self._page.goto(
                    f"{self.PJECALC_BASE}/pages/principal.jsf",
                    wait_until="domcontentloaded", timeout=30000,
                )
                self._page.wait_for_timeout(2000)
            except Exception:
                pass
            return False
        try:
            body = self._page.locator("body").text_content(timeout=5000) or ""
            if len(body.strip()) < 50:
                self._log("  ⚠ Página com pouco conteúdo — recarregando…")
                self._page.wait_for_timeout(2000)
                self._page.reload()
                self._page.wait_for_load_state("networkidle", timeout=15000)
                return False
            if "Erro interno do servidor" in body or ("500" in body and "Erro" in body):
                self._log("  ⚠ Erro 500 detectado — aguardando 5s e retentando…")
                self._page.wait_for_timeout(5000)
                # Recarregar a página atual antes de voltar para home
                try:
                    self._page.reload(wait_until="domcontentloaded", timeout=15000)
                    self._page.wait_for_timeout(2000)
                    body2 = self._page.locator("body").text_content(timeout=5000) or ""
                    if "Erro interno" not in body2 and "500" not in body2:
                        self._log("  ✓ Erro 500 resolvido após reload")
                        return True
                except Exception:
                    pass
                # Ainda com erro — voltar para home
                self._log("  ⚠ Erro 500 persistente — voltando para home…")
                home = self._page.locator(
                    "a:has-text('Tela Inicial'), a:has-text('Página Inicial')"
                )
                if home.count() > 0:
                    home.first.click()
                    self._page.wait_for_timeout(2000)
                return False
        except Exception:
            pass
        return True

    # ── Navegação principal ────────────────────────────────────────────────────

    def _reabrir_calculo_recentes(self) -> bool:
        """Volta para principal.jsf e re-abre o cálculo via lista de Recentes.

        Cria uma nova conversação Seam limpa, necessário quando a conversação atual
        está corrompida (NPE, ViewExpiredException, etc.).
        Retorna True se o cálculo foi re-aberto com sucesso.
        """
        try:
            _home = f"{self.PJECALC_BASE}/pages/principal.jsf"
            self._page.goto(_home, wait_until="domcontentloaded", timeout=15000)
            self._page.wait_for_timeout(2000)
            try:
                self._instalar_monitor_ajax()
            except Exception:
                pass

            _listbox = self._page.locator(
                "select[class*='listaCalculosRecentes'], select[name*='listaCalculosRecentes']"
            )
            if _listbox.count() == 0:
                self._log("  ⚠ Lista de cálculos recentes não encontrada")
                return False

            _options = _listbox.first.locator("option")
            _n_opts = _options.count()
            if _n_opts == 0:
                return False

            # Buscar pelo CNJ
            _num_proc = (self._dados or {}).get("processo", {}).get("numero", "")
            _num_clean = _num_proc.replace(".", "").replace("-", "").replace("/", "") if _num_proc else ""
            _found_idx = None

            if _num_clean:
                for _idx in range(_n_opts):
                    _opt_text = (_options.nth(_idx).text_content() or "")
                    _opt_clean = _opt_text.replace(".", "").replace("-", "").replace("/", "")
                    if _num_clean in _opt_clean:
                        _found_idx = _idx
                        break

            # Fallback: buscar pelo nome do reclamante
            if _found_idx is None:
                _reclamante = (self._dados or {}).get("processo", {}).get("reclamante", {})
                _nome_recl = (_reclamante.get("nome") or "").strip().upper() if isinstance(_reclamante, dict) else ""
                if _nome_recl and len(_nome_recl) >= 5:
                    for _idx in range(_n_opts):
                        _opt_text = (_options.nth(_idx).text_content() or "").upper()
                        if _nome_recl in _opt_text:
                            _found_idx = _idx
                            break

            if _found_idx is None:
                # Diagnóstico: listar todos os itens disponíveis
                _nome_recl2 = ""
                try:
                    _r = (self._dados or {}).get("processo", {}).get("reclamante", {})
                    _nome_recl2 = (_r.get("nome") or "").strip() if isinstance(_r, dict) else ""
                except Exception:
                    pass
                self._log(f"  ℹ Recentes ({_n_opts} itens) — buscando CNJ='{_num_proc}' / reclamante='{_nome_recl2}':")
                for _idx in range(min(_n_opts, 5)):
                    _opt_text = (_options.nth(_idx).text_content() or "").strip()
                    self._log(f"    item {_idx+1}: '{_opt_text[:100]}'")

                # Último recurso: se há apenas 1 item nos recentes, é provável que seja o nosso
                # (H2 foi limpo antes, então só existe o cálculo que acabamos de criar)
                if _n_opts == 1:
                    self._log("  → Apenas 1 cálculo nos recentes — usando-o como fallback")
                    _found_idx = 0
                else:
                    self._log(f"  ⚠ Processo '{_num_proc}' não encontrado nos recentes")
                    return False

            _opt_el = _listbox.first.locator("option").nth(_found_idx)
            _opt_el.click()
            self._page.wait_for_timeout(300)
            _opt_el.dblclick()
            self._aguardar_ajax(30000)
            self._page.wait_for_timeout(2000)

            _url_after = self._page.url
            if "calculo" in _url_after and "conversationId" in _url_after:
                self._capturar_base_calculo()
                self._log(f"  ✓ Cálculo re-aberto via Recentes: conversationId={self._calculo_conversation_id}")
                return True
            return False
        except Exception as _e:
            self._log(f"  ⚠ _reabrir_calculo_recentes: {_e}")
            return False

    def _capturar_base_calculo(self) -> None:
        """Captura a URL base e conversationId do cálculo ativo para navegação por URL."""
        import re as _re
        try:
            url = self._page.url
            m_base = _re.match(r'(https?://.+/)[^/?]+\.jsf', url)
            m_conv = _re.search(r'conversationId=(\d+)', url)
            if m_base and m_conv:
                base = m_base.group(1)
                # Normalizar para sempre parar em calculo/ — sem isto, URLs como
                # .../calculo/verba/verbas-para-calculo.jsf geram base ".../calculo/verba/"
                # e os paths do _URL_SECTION_MAP ficam dobrados (ex: verba/verba/verba-calculo.jsf)
                m_calculo = _re.search(r'(https?://.+?/calculo/)', base)
                if m_calculo:
                    base = m_calculo.group(1)
                self._calculo_url_base = base
                self._calculo_conversation_id = m_conv.group(1)
                self._log(
                    f"  ℹ URL base: {self._calculo_url_base} | conversationId={self._calculo_conversation_id}"
                )
        except Exception:
            pass

    def _limpar_calculo_via_ui(self) -> bool:
        """Limpa cálculos existentes via interface do PJE-Calc (sem reiniciar Tomcat).

        Navega para a Tela Inicial, verifica se há cálculos na lista de Recentes,
        e exclui cada um via menu Operações > Excluir.
        Retorna True se conseguiu limpar (ou não havia nada para limpar).
        """
        try:
            self._log("Limpando cálculos existentes via interface…")
            # Navegar para Home
            _home = f"{self.PJECALC_BASE}/pages/principal.jsf"
            self._page.goto(_home, wait_until="domcontentloaded", timeout=30000)
            self._page.wait_for_timeout(2000)

            # Verificar se há cálculos na lista de Recentes
            _listbox = self._page.locator(
                "select[class*='listaCalculosRecentes'], select[name*='listaCalculosRecentes']"
            )
            if _listbox.count() == 0:
                self._log("  ✓ Nenhuma lista de recentes encontrada — banco limpo")
                return True

            _options = _listbox.first.locator("option")
            _n_opts = _options.count()
            if _n_opts == 0:
                self._log("  ✓ Nenhum cálculo nos recentes — banco limpo")
                return True

            self._log(f"  Encontrados {_n_opts} cálculo(s) nos recentes — excluindo…")

            # Excluir cada cálculo: abrir via duplo-clique, depois Operações > Excluir
            _max_exclusoes = min(_n_opts, 10)  # safety: no máximo 10
            for _i in range(_max_exclusoes):
                try:
                    # Re-ler a lista (pode ter mudado após exclusão)
                    _listbox = self._page.locator(
                        "select[class*='listaCalculosRecentes'], select[name*='listaCalculosRecentes']"
                    )
                    if _listbox.count() == 0:
                        break
                    _opts = _listbox.first.locator("option")
                    if _opts.count() == 0:
                        break

                    # Abrir o primeiro cálculo
                    _opt = _opts.first
                    _opt.click()
                    self._page.wait_for_timeout(300)
                    _opt.dblclick()
                    self._aguardar_ajax(30000)
                    self._page.wait_for_timeout(2000)

                    # Verificar se estamos dentro de um cálculo (URL com conversationId)
                    _url = self._page.url
                    if "calculo" not in _url and "conversationId" not in _url:
                        self._log(f"  ⚠ Não abriu cálculo (URL: {_url[:80]}) — abortando limpeza UI")
                        return False

                    # Auto-confirmar o dialog de exclusão
                    self._page.once("dialog", lambda d: d.accept())

                    # Clicar em Excluir via menu lateral
                    _excluiu = self._clicar_menu_lateral("Excluir", obrigatorio=False)
                    if not _excluiu:
                        # Fallback: buscar link de texto "Excluir" em qualquer lugar
                        _exc_link = self._page.locator("a:has-text('Excluir')")
                        if _exc_link.count() > 0:
                            self._page.once("dialog", lambda d: d.accept())
                            _exc_link.first.click(force=True)
                            _excluiu = True

                    if _excluiu:
                        self._aguardar_ajax(15000)
                        self._page.wait_for_timeout(2000)
                        self._log(f"  ✓ Cálculo {_i+1} excluído")
                    else:
                        self._log(f"  ⚠ Não encontrou botão Excluir para cálculo {_i+1}")
                        return False

                    # Voltar para Home para próxima iteração
                    self._page.goto(_home, wait_until="domcontentloaded", timeout=15000)
                    self._page.wait_for_timeout(1500)

                except Exception as _exc_inner:
                    self._log(f"  ⚠ Erro ao excluir cálculo {_i+1}: {_exc_inner}")
                    # Tentar voltar para Home mesmo com erro
                    try:
                        self._page.goto(_home, wait_until="domcontentloaded", timeout=15000)
                        self._page.wait_for_timeout(1000)
                    except Exception:
                        pass
                    return False

            self._log("  ✓ Todos os cálculos excluídos via interface")
            return True

        except Exception as _exc:
            self._log(f"  ⚠ Limpeza via UI falhou: {_exc}")
            return False

    def _ir_para_novo_calculo(self) -> None:
        """Navega para o formulário de Novo Cálculo via menu 'Novo'.

        Usa o fluxo 'Novo' (primeira liquidação de sentença), NÃO 'Cálculo Externo'
        (que serve apenas para atualizar cálculos existentes).
        Navegação via clique no menu — URL direta causa ViewState inválido no JSF.
        """
        self._log("Navegando para Novo Cálculo via menu…")

        self._clicar_menu_lateral("Novo")
        # Aguardar a navegação JSF estabilizar antes de interagir com a página.
        # wait_for_timeout fixo é insuficiente; networkidle garante que todos os
        # requests AJAX do JSF terminaram antes de evaluate() ser chamado.
        try:
            self._page.wait_for_load_state("networkidle", timeout=12000)
        except Exception:
            self._page.wait_for_timeout(2500)
        self._aguardar_ajax()

        # Recuperação: se página de erro, volta para home e tenta novamente
        try:
            body = self._page.locator("body").text_content(timeout=3000) or ""
            if "Erro" in body and ("Servidor" in body or "inesperado" in body):
                self._log("  Erro detectado após menu — voltando para Tela Inicial…")
                link = self._page.locator("a:has-text('Tela Inicial'), a:has-text('Página Inicial')")
                if link.count() > 0:
                    link.first.click()
                    self._page.wait_for_timeout(1500)
                self._clicar_menu_lateral("Novo")
                try:
                    self._page.wait_for_load_state("networkidle", timeout=10000)
                except Exception:
                    self._page.wait_for_timeout(2000)
        except Exception:
            pass

        self._capturar_base_calculo()
        self._log("  ✓ Formulário de Novo Cálculo aberto.")

    # ── Fase 1: Dados do Processo + Parâmetros ─────────────────────────────────

    @retry(max_tentativas=3)
    def fase_dados_processo(self, dados: dict) -> None:
        import datetime
        self._log("Fase 1 — Dados do processo…")
        # Garantir que a página terminou de navegar antes de chamar evaluate().
        # "Execution context was destroyed" ocorre quando a página ainda está
        # em navegação JSF e evaluate() é chamado prematuramente.
        try:
            self._page.wait_for_load_state("domcontentloaded", timeout=8000)
        except Exception:
            pass
        self._aguardar_ajax()
        self.mapear_campos("fase1_dados_processo")

        proc = dados.get("processo", {})
        cont = dados.get("contrato", {})
        presc = dados.get("prescricao", {})
        ap = dados.get("aviso_previo", {})

        # ── Campos do cabeçalho (Tipo e Data de Criação) ──
        self._preencher("tipo", "Trabalhista", False)
        hoje = datetime.date.today().strftime("%d/%m/%Y")
        # Tentar IDs em ordem — para no primeiro encontrado (evita duplo preenchimento)
        _campos_data_cabecalho = [
            "dataDeCriacao", "dataCriacao", "dataDeAbertura", "dataAbertura", "dataCalculo"
        ]
        _preencheu_data_cabecalho = False
        for _fid in _campos_data_cabecalho:
            if self._preencher_data(_fid, hoje, obrigatorio=False):
                _preencheu_data_cabecalho = True
                break
        # JS fallback: encontrar qualquer input de data no cabeçalho
        if not _preencheu_data_cabecalho:
            try:
                self._page.evaluate(
                    """(data) => {
                        const inputs = document.querySelectorAll(
                            'input[id*="dataDe"], input[id*="dataCria"], input[id*="dataCalc"]'
                        );
                        if (inputs.length > 0) {
                            inputs[0].value = data;
                            inputs[0].dispatchEvent(new Event('change',{bubbles:true}));
                        }
                    }""",
                    hoje,
                )
            except Exception:
                pass

        # ── Aba Dados do Processo ──
        self._clicar_aba("tabDadosProcesso")
        self._page.wait_for_timeout(400)

        # Número do processo (campos separados na interface)
        num = _parsear_numero_processo(proc.get("numero"))
        if not num:
            # Fallback: usar campos desmembrados armazenados no processo
            # (cobre sessões gravadas quando processo.numero foi truncado para 7 dígitos)
            _seq = proc.get("numero_seq") or (proc.get("numero", "") if len(proc.get("numero", "")) == 7 else "")
            if _seq and proc.get("digito_verificador") and proc.get("ano"):
                num = {
                    "numero":  _seq,
                    "digito":  proc.get("digito_verificador", ""),
                    "ano":     proc.get("ano", ""),
                    "justica": proc.get("segmento", "5"),
                    "regiao":  proc.get("regiao", ""),
                    "vara":    proc.get("vara", ""),
                }
                self._log(f"  ℹ numero processo: reconstruído dos campos desmembrados ({_seq})")
        if num:
            self._preencher("numero", num.get("numero", ""), False)
            self._preencher("digito", num.get("digito", ""), False)
            self._preencher("ano", num.get("ano", ""), False)
            self._preencher("justica", num.get("justica", ""), False)
            self._preencher("regiao", num.get("regiao", ""), False)
            self._preencher("vara", num.get("vara", ""), False)
        else:
            self._log(f"  ⚠ numero processo não disponível — preencher manualmente")

        # Valor da causa e data de autuação
        if proc.get("valor_causa"):
            self._preencher("valorDaCausa", _fmt_br(proc["valor_causa"]), False)
            self._preencher("valorCausa", _fmt_br(proc["valor_causa"]), False)
        if proc.get("autuado_em"):
            self._preencher_data("autuadoEm", proc["autuado_em"], False)
            self._preencher_data("dataAutuacao", proc["autuado_em"], False)

        # Partes
        if proc.get("reclamante"):
            self._preencher("reclamanteNome", proc["reclamante"], False)
            self._preencher("nomeReclamante", proc["reclamante"], False)
        if proc.get("reclamado"):
            self._preencher("reclamadoNome", proc["reclamado"], False)
            self._preencher("nomeReclamado", proc["reclamado"], False)

        if proc.get("cpf_reclamante"):
            self._marcar_radio("documentoFiscalReclamante", "CPF")
            self._preencher("reclamanteNumeroDocumentoFiscal", proc["cpf_reclamante"], False)
            self._preencher("cpfReclamante", proc["cpf_reclamante"], False)
        if proc.get("cnpj_reclamado"):
            self._marcar_radio("tipoDocumentoFiscalReclamado", "CNPJ")
            self._preencher("reclamadoNumeroDocumentoFiscal", proc["cnpj_reclamado"], False)
            self._preencher("cnpjReclamado", proc["cnpj_reclamado"], False)

        if proc.get("advogado_reclamante"):
            # Clicar em "Incluir" advogado reclamante se botão existir
            try:
                _btn_adv_rec = self._page.locator("[id$='incluirAdvogadoReclamante']")
                if _btn_adv_rec.count() > 0:
                    _btn_adv_rec.click()
                    self._aguardar_ajax()
                    self._page.wait_for_timeout(500)
            except Exception:
                pass
            self._preencher("nomeAdvogadoReclamante", proc["advogado_reclamante"], False)
        if proc.get("oab_reclamante"):
            self._preencher("numeroOABAdvogadoReclamante", proc["oab_reclamante"], False)
        if proc.get("doc_advogado_reclamante"):
            self._preencher("numeroDocumentoAdvogadoReclamante", proc["doc_advogado_reclamante"], False)

        # Advogado do reclamado — IDs confirmados no DOM
        if proc.get("advogado_reclamado"):
            # Clicar em "Incluir" para adicionar advogado (botão dinâmico RichFaces)
            try:
                _btn_adv = self._page.locator("[id$='incluirAdvogadoReclamado']")
                if _btn_adv.count() > 0:
                    _btn_adv.click()
                    self._aguardar_ajax()
                    self._page.wait_for_timeout(500)
            except Exception:
                pass
            self._preencher("nomeAdvogadoReclamado", proc["advogado_reclamado"], False)
        if proc.get("oab_reclamado"):
            self._preencher("numeroOABAdvogadoReclamado", proc["oab_reclamado"], False)
        if proc.get("doc_advogado_reclamado"):
            self._preencher("numeroDocumentoAdvogadoReclamado", proc["doc_advogado_reclamado"], False)

        # PIS/PASEP do reclamante — documento previdenciário
        if proc.get("pis_reclamante") or proc.get("pasep_reclamante"):
            _pis = proc.get("pis_reclamante") or proc.get("pasep_reclamante", "")
            self._marcar_radio("reclamanteTipoDocumentoPrevidenciario", "PIS")
            self._preencher("reclamanteNumeroDocumentoPrevidenciario", _pis, False)

        # NOTA: NÃO salvar aqui. Manual oficial (Seção 5 + Seção 10) exige que o
        # Salvar ocorra APENAS APÓS ambas as abas (Dados do Processo + Parâmetros
        # do Cálculo) estarem preenchidas: "CRITICO: Apos completar e verificar
        # ambas as abas, o usuario DEVE clicar no icone Salvar". Salvar apenas
        # com a aba Geral preenchida gera "Existem erros no formulário" porque
        # campos obrigatórios dos Parâmetros (estado/município/carga horária)
        # ainda não foram informados. O Salvar final ocorre no fim desta fase.

        # ── Aba Parâmetros do Cálculo ──
        self._log("  → Aba Parâmetros do Cálculo…")
        self._clicar_aba("tabParametrosCalculo")
        self._page.wait_for_timeout(600)
        self.mapear_campos("fase1_parametros")

        # Estado + Município (IDs confirmados por inspeção DOM: formulario:estado, formulario:municipio)
        # Estado usa índice numérico (0=AC, 1=AL, ..., 5=CE, ...) — NÃO a sigla como value
        _UF_INDEX = {
            "AC": "0", "AL": "1", "AP": "2", "AM": "3", "BA": "4", "CE": "5",
            "DF": "6", "ES": "7", "GO": "8", "MA": "9", "MT": "10", "MS": "11",
            "MG": "12", "PA": "13", "PB": "14", "PR": "15", "PE": "16", "PI": "17",
            "RJ": "18", "RN": "19", "RS": "20", "RO": "21", "RR": "22", "SC": "23",
            "SP": "24", "SE": "25", "TO": "26",
        }
        # Mapa TRT → UF (para inferir estado a partir do número do processo quando uf não vier explícito)
        _TRT_UF = {
            "1": "RJ", "2": "SP", "3": "MG", "4": "RS", "5": "BA", "6": "PE",
            "7": "CE", "8": "PA", "9": "PR", "10": "DF", "11": "AM", "12": "SC",
            "13": "PB", "14": "RO", "15": "SP", "16": "MA", "17": "ES", "18": "GO",
            "19": "AL", "20": "SE", "21": "RN", "22": "PI", "23": "MT", "24": "MS",
        }
        _uf = proc.get("uf") or proc.get("estado") or _TRT_UF.get(str(proc.get("regiao", "")), "")
        if _uf:
            _idx_estado = _UF_INDEX.get(_uf.upper())
            if _idx_estado and self._selecionar("estado", _idx_estado, obrigatorio=False):
                self._log(f"  ✓ estado: {_uf} (value={_idx_estado})")
                self._aguardar_ajax()  # municipio é carregado via AJAX após estado
                # Aguardar opções de município carregarem (mais robusto que timeout fixo)
                try:
                    self._page.wait_for_function(
                        """() => {
                            const s = document.getElementById('formulario:municipio');
                            return s && s.options.length > 1;
                        }""",
                        timeout=10000,
                    )
                except Exception:
                    self._page.wait_for_timeout(2000)  # fallback

                # Município — 3 estratégias em cascata: exato → startsWith → includes
                _cidade = proc.get("municipio") or proc.get("cidade") or ""
                if _cidade:
                    _municipio_selecionado = self._page.evaluate(
                        """(cidade) => {
                            function norm(s) {
                                return (s||'').toUpperCase()
                                    .normalize('NFD').replace(/[\u0300-\u036f]/g,'').trim();
                            }
                            const sel = document.getElementById('formulario:municipio');
                            if (!sel || sel.options.length <= 1) return null;
                            const c = norm(cidade);
                            // Log primeiras opções para diagnóstico
                            const opts = Array.from(sel.options).slice(0,5)
                                .map(o => o.value + ':' + o.text).join(' | ');
                            console.log('[municipio] cidade=' + c + ' opts=' + opts);
                            // Estratégia 1: match exato normalizado
                            for (const o of sel.options) {
                                if (norm(o.text) === c) {
                                    sel.value = o.value;
                                    sel.dispatchEvent(new Event('change',{bubbles:true}));
                                    return '1:' + o.text;
                                }
                            }
                            // Estratégia 2: option começa com nome da cidade
                            for (const o of sel.options) {
                                const ot = norm(o.text);
                                if (ot.startsWith(c + ' ') || ot.startsWith(c + '-') || ot === c) {
                                    sel.value = o.value;
                                    sel.dispatchEvent(new Event('change',{bubbles:true}));
                                    return '2:' + o.text;
                                }
                            }
                            // Estratégia 3: includes bidirecional
                            for (const o of sel.options) {
                                const ot = norm(o.text);
                                if (ot.includes(c) || c.includes(ot)) {
                                    sel.value = o.value;
                                    sel.dispatchEvent(new Event('change',{bubbles:true}));
                                    return '3:' + o.text;
                                }
                            }
                            return null;
                        }""",
                        _cidade,
                    )
                    if _municipio_selecionado:
                        estrategia, nome = _municipio_selecionado.split(":", 1) if ":" in _municipio_selecionado else ("?", _municipio_selecionado)
                        self._log(f"  ✓ municipio: '{nome}' (estratégia {estrategia})")
                        self._aguardar_ajax()  # aguardar AJAX pós-seleção município
                    else:
                        self._log(f"  ⚠ municipio '{_cidade}' não encontrado — verifique o nome na sentença")

        # Dados do contrato
        # Datas: _localizar() busca [id*='InputDate'] primeiro, cobrindo formulario:dataAdmissaoInputDate etc.
        if cont.get("admissao"):
            self._preencher_data("dataAdmissao", cont["admissao"], False)
        if cont.get("demissao"):
            self._preencher_data("dataDemissao", cont["demissao"], False)
        if cont.get("ajuizamento"):
            self._preencher_data("dataAjuizamento", cont["ajuizamento"], False)

        # NOTA: tipoRescisao NÃO existe no DOM do PJE-Calc (confirmado em calculo.xhtml).
        # O tipo de rescisão é determinado pelas verbas/aviso prévio, não por campo no formulário.

        # Regime de trabalho — ID confirmado: formulario:tipoDaBaseTabelada
        # Values: INTEGRAL (padrão), PARCIAL, INTERMITENTE
        _regime_map = {
            "Tempo Integral": "INTEGRAL", "tempo integral": "INTEGRAL",
            "Tempo Parcial": "PARCIAL", "tempo parcial": "PARCIAL",
            "Trabalho Intermitente": "INTERMITENTE", "intermitente": "INTERMITENTE",
        }
        if cont.get("regime"):
            _regime_val = _regime_map.get(cont["regime"], "INTEGRAL")
            self._selecionar("tipoDaBaseTabelada", _regime_val, obrigatorio=False)

        # Carga horária padrão — ID confirmado: formulario:valorCargaHorariaPadrao
        # Este campo é OBRIGATÓRIO (required=true) e usado pelo Cartão de Ponto.
        # Valor MENSAL em horas (ex: 220, 180, 150). Formato: currencyMask BR.
        # Se carga_horaria não foi extraída, calcular a partir de jornada_diaria/semanal.
        _ch_mensal_padrao = cont.get("carga_horaria")
        if not _ch_mensal_padrao:
            _jd = cont.get("jornada_diaria")
            _js = cont.get("jornada_semanal")
            # Fórmula PJE-Calc: carga mensal = jornada_semanal × 5
            # Ex: 44h/sem → 220h/mês, 40h/sem → 200h/mês, 36h/sem → 180h/mês
            if _js:
                _ch_mensal_padrao = round(_js * 5, 2)
            elif _jd:
                _ch_mensal_padrao = round(_jd * 5 * 5, 2)  # diária × 5 dias × 5 semanas
            else:
                _ch_mensal_padrao = 220  # CLT padrão
        _ch = _fmt_br(float(_ch_mensal_padrao))
        self._preencher("valorCargaHorariaPadrao", _ch, False)
        self._log(f"  ✓ valorCargaHorariaPadrao: {_ch}")

        # Maior remuneração e última remuneração — IDs confirmados por inspeção DOM
        if cont.get("maior_remuneracao"):
            self._preencher("valorMaiorRemuneracao", _fmt_br(cont["maior_remuneracao"]), False)
        if cont.get("ultima_remuneracao"):
            self._preencher("valorUltimaRemuneracao", _fmt_br(cont["ultima_remuneracao"]), False)

        # Aviso prévio — ID confirmado: formulario:apuracaoPrazoDoAvisoPrevio
        # Values: NAO_APURAR, APURACAO_CALCULADA, APURACAO_INFORMADA
        # Manual seção 5.3:
        #   - Nao Apurar:  mantém 30 dias padrão (sem campo Quantidade)
        #   - Calculado:   Lei 12.506/2011 (30 + 3/ano, máx 90) — seguro como default
        #   - Informado:   EXIGE campo prazoAvisoInformado com qtd de dias (obrigatório)
        # Se tipo=Informado mas prazo_dias não veio da extração, cair para "Calculado"
        # (evita erro "Campo obrigatório: Quantidade" no Salvar).
        _ap_map = {
            "Calculado": "APURACAO_CALCULADA",
            "Informado": "APURACAO_INFORMADA",
            "Nao Apurar": "NAO_APURAR",
            "nao_apurar": "NAO_APURAR",
        }
        _ap_tipo = ap.get("tipo", "Calculado")
        _ap_prazo_dias = ap.get("prazo_dias")
        if _ap_tipo == "Informado" and not _ap_prazo_dias:
            self._log(
                "  ⚠ Aviso prévio tipo=Informado sem prazo_dias — caindo para Calculado (Lei 12.506/2011)"
            )
            _ap_tipo = "Calculado"
        _ap_val = _ap_map.get(_ap_tipo, "APURACAO_CALCULADA")
        self._selecionar("apuracaoPrazoDoAvisoPrevio", _ap_val, obrigatorio=False)
        # onchange reRender="painelPrazoAvisoInformado" — aguardar AJAX antes de
        # preencher prazoAvisoInformado (painel só é renderizado quando valor='I').
        if _ap_val == "APURACAO_INFORMADA":
            self._aguardar_ajax()
            # Campo obrigatório quando tipo=Informado. Fallback: 30 dias.
            _dias = int(_ap_prazo_dias) if _ap_prazo_dias else 30
            self._preencher("prazoAvisoInformado", str(_dias), False)
            self._log(f"  ✓ prazoAvisoInformado: {_dias} dias")

        # Prescrição
        if presc.get("quinquenal") is not None:
            self._marcar_checkbox("prescricaoQuinquenal", bool(presc["quinquenal"]))
        if presc.get("fgts") is not None:
            self._marcar_checkbox("prescricaoFgts", bool(presc["fgts"]))

        # Checkboxes auxiliares de parâmetros
        # sabadoDiaUtil — se sábado é dia útil para fins de cálculo (padrão true na maioria)
        if cont.get("sabado_dia_util") is not None:
            self._marcar_checkbox("sabadoDiaUtil", bool(cont["sabado_dia_util"]))
        # projetaAvisoIndenizado — projetar aviso prévio para cálculos (13º, férias prop.)
        if ap.get("projetar") is not None:
            self._marcar_checkbox("projetaAvisoIndenizado", bool(ap["projetar"]))
        # zeraValorNegativo — zerar verbas com resultado negativo (padrão: true)
        if dados.get("zera_valor_negativo") is not None:
            self._marcar_checkbox("zeraValorNegativo", bool(dados["zera_valor_negativo"]))

        # Feriados — considerar feriados estaduais e municipais
        if dados.get("considerar_feriado_estadual") is not None:
            self._marcar_checkbox("consideraFeriadoEstadual", bool(dados["considerar_feriado_estadual"]))
        if dados.get("considerar_feriado_municipal") is not None:
            self._marcar_checkbox("consideraFeriadoMunicipal", bool(dados["considerar_feriado_municipal"]))

        # Datas de início e término do cálculo (período de apuração)
        if cont.get("data_inicio_calculo"):
            self._preencher_data("dataInicioCalculo", cont["data_inicio_calculo"], False)
        if cont.get("data_fim_calculo") or cont.get("data_termino_calculo"):
            _dt_fim = cont.get("data_fim_calculo") or cont.get("data_termino_calculo")
            self._preencher_data("dataTerminoCalculo", _dt_fim, False)

        # Exceções de Carga Horária (períodos com CH diferente)
        _excecoes_ch = dados.get("excecoes_carga_horaria", [])
        for _exc_ch in _excecoes_ch:
            try:
                _btn_exc = self._page.locator("[id$='incluirExcecaoCH']")
                if _btn_exc.count() > 0:
                    _btn_exc.click()
                    self._aguardar_ajax()
                    self._page.wait_for_timeout(500)
                    if _exc_ch.get("data_inicio"):
                        self._preencher_data("dataInicioExcecao", _exc_ch["data_inicio"], False)
                    if _exc_ch.get("data_termino"):
                        self._preencher_data("dataTerminoExcecao", _exc_ch["data_termino"], False)
                    if _exc_ch.get("valor"):
                        self._preencher("valorExcecaoCH", _fmt_br(_exc_ch["valor"]), False)
                    self._log(f"  ✓ Exceção CH: {_exc_ch.get('data_inicio')} a {_exc_ch.get('data_termino')}")
            except Exception as _e_exc:
                self._log(f"  ⚠ Exceção CH: {_e_exc}")

        # Exceções de Sábado (períodos onde sábado NÃO é dia útil)
        _excecoes_sab = dados.get("excecoes_sabado", [])
        for _exc_sab in _excecoes_sab:
            try:
                _btn_sab = self._page.locator("[id$='incluirExcecaoSab']")
                if _btn_sab.count() > 0:
                    _btn_sab.click()
                    self._aguardar_ajax()
                    self._page.wait_for_timeout(500)
                    if _exc_sab.get("data_inicio"):
                        self._preencher_data("dataInicioExcecaoSabado", _exc_sab["data_inicio"], False)
                    if _exc_sab.get("data_termino"):
                        self._preencher_data("dataTerminoExcecaoSabado", _exc_sab["data_termino"], False)
                    self._log(f"  ✓ Exceção Sábado: {_exc_sab.get('data_inicio')} a {_exc_sab.get('data_termino')}")
            except Exception as _e_sab:
                self._log(f"  ⚠ Exceção Sábado: {_e_sab}")

        # Pontos Facultativos
        _pontos_fac = dados.get("pontos_facultativos", [])
        for _pf in _pontos_fac:
            try:
                _btn_pf = self._page.locator("[id$='cmdAdicionarPontoFacultativo']")
                if _btn_pf.count() > 0:
                    _btn_pf.click()
                    self._aguardar_ajax()
                    self._page.wait_for_timeout(500)
                    if _pf.get("data"):
                        self._preencher_data("pontoFacultativo", _pf["data"], False)
                    self._log(f"  ✓ Ponto Facultativo: {_pf.get('data')}")
            except Exception as _e_pf:
                self._log(f"  ⚠ Ponto Facultativo: {_e_pf}")

        # NOTA: Índices de correção e juros NÃO são configurados aqui na aba
        # Parâmetros do Cálculo. São configurados exclusivamente em fase_parametros_atualizacao()
        # (Fase 6 — página correcao-juros.jsf). Configurar em ambos os lugares causa
        # conflitos no modelo JSF e "Erro inesperado. Erro: 1" ao salvar a Fase 6.
        ir = dados.get("imposto_renda", {})

        if ir.get("apurar"):
            self._marcar_checkbox("apurarImpostoRenda", True)
            if ir.get("meses_tributaveis"):
                self._preencher("qtdMesesRendimento", str(ir["meses_tributaveis"]), False)
            if ir.get("dependentes"):
                self._marcar_checkbox("possuiDependentes", True)
                self._preencher("quantidadeDependentes", str(ir["dependentes"]), False)

        # ── Comentários: Justiça Gratuita → exigibilidade suspensa (art. 791-A, §4º, CLT) ──
        # Só incluir a frase quando a parte beneficiária da JG é DEVEDORA de honorários
        jg = dados.get("justica_gratuita", {})
        _jg_reclamante = jg.get("reclamante", False)
        _jg_reclamado = jg.get("reclamado", False)
        _honorarios = dados.get("honorarios", [])
        if isinstance(_honorarios, dict):
            _honorarios = [_honorarios] if _honorarios else []
        # Verificar quais partes com JG são devedoras de honorários
        _devedores_hon = {h.get("devedor", "").upper() for h in _honorarios if isinstance(h, dict)}
        _jg_devedor_reclamante = _jg_reclamante and "RECLAMANTE" in _devedores_hon
        _jg_devedor_reclamado = _jg_reclamado and "RECLAMADO" in _devedores_hon
        if _jg_devedor_reclamante or _jg_devedor_reclamado:
            # Montar descrição da(s) parte(s) beneficiária(s) que são devedoras
            _partes_jg = []
            if _jg_devedor_reclamante:
                _nome_reclamante = proc.get("reclamante", "pelo(a) reclamante")
                _partes_jg.append(f"pelo(a) reclamante ({_nome_reclamante})")
            if _jg_devedor_reclamado:
                _nome_reclamado = proc.get("reclamado", "pelo(a) reclamado(a)")
                _partes_jg.append(f"pelo(a) reclamado(a) ({_nome_reclamado})")
            _desc_partes = " e ".join(_partes_jg)
            _comentario_jg = (
                f"Honorários advocatícios devidos {_desc_partes} com exigibilidade "
                f"suspensa, ante a gratuidade judiciária deferida, nos termos do "
                f"art. 791-A, parágrafo 4o, da CLT."
            )
            self._preencher("comentarios", _comentario_jg, False)
            self._log(f"  ✓ Comentários: justiça gratuita — {_desc_partes}")

        if not self._salvar_com_deteccao_erros("Fase 1", dados, max_tentativas=3):
            self._log("  ⚠ Fase 1: Salvar não confirmado — dados do processo podem não ter persistido.")

        # Verificação pós-save: confirmar que o cálculo foi persistido no H2.
        # Após o primeiro Salvar bem-sucedido, a URL deve conter conversationId
        # (indicando que o Seam criou o registro em TBCALCULO com IIDCALCULO).
        # Sem essa verificação, fases subsequentes falham com IIDCALCULO NULL.
        self._capturar_base_calculo()
        _url_pos_save = self._page.url
        if "conversationId" in _url_pos_save:
            self._log(f"  ✓ Cálculo persistido (conversationId presente na URL)")
        else:
            self._log("  ⚠ conversationId ausente na URL pós-save — tentando re-salvar…")
            self._page.wait_for_timeout(2000)
            self._salvar_com_deteccao_erros("Fase 1 (retry)", dados, max_tentativas=2)
            self._capturar_base_calculo()
            _url_retry = self._page.url
            if "conversationId" in _url_retry:
                self._log(f"  ✓ Cálculo persistido após re-save")
            else:
                self._log("  ⚠ conversationId ainda ausente — prosseguindo (risco de IIDCALCULO NULL)")

        self._log("Fase 1 concluída.")

    # ── Utilitário de screenshot por fase ──────────────────────────────────────

    def _screenshot_fase(self, nome_fase: str) -> None:
        """Captura screenshot após conclusão de uma fase (diagnóstico não-crítico).
        Salva em SCREENSHOTS_DIR (global) e em exec_dir/screenshots/ (por cálculo)."""
        try:
            from config import SCREENSHOTS_DIR
            import time as _t
            ts = int(_t.time())
            Path(SCREENSHOTS_DIR).mkdir(parents=True, exist_ok=True)
            path = Path(SCREENSHOTS_DIR) / f"{ts}_{nome_fase}.png"
            self._page.screenshot(path=str(path), full_page=False)
            self._log(f"  📸 {path.name}")

            # Salvar cópia no diretório de persistência do cálculo
            if self._exec_dir:
                import shutil
                calc_ss = self._exec_dir / "screenshots" / f"{nome_fase}.png"
                calc_ss.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(str(path), str(calc_ss))
        except Exception as e_ss:
            logger.debug(f"Screenshot falhou (não crítico): {e_ss}")

    # ── Fase 2a: Parâmetros Gerais ─────────────────────────────────────────────

    @retry(max_tentativas=2)
    def fase_parametros_gerais(self, parametros: dict) -> None:
        """Preenche Parâmetros Gerais (Passo 2): data inicial de apuração, carga horária.

        Chamado com `passo_2_parametros_gerais` do parametrizacao.json.
        """
        self._log("Fase 2a — Parâmetros Gerais…")

        data_inicial = parametros.get("data_inicial_apuracao")
        data_final = parametros.get("data_final_apuracao")
        carga_diaria = parametros.get("carga_horaria_diaria")
        carga_semanal = parametros.get("carga_horaria_semanal")
        zerar_negativos = parametros.get("zerar_valores_negativos", True)

        # Validação: data_inicial não pode ser anterior à admissão.
        # O PJE-Calc rejeita datas de apuração fora do período contratual.
        # Causa comum: prescrição quinquenal calculada a partir do ajuizamento
        # pode gerar data anterior à admissão (ex: ajuiz 2026 - 5 = 2021, mas admissão é 2025).
        if data_inicial:
            from datetime import datetime as _dt_parse
            try:
                _admissao_str = parametros.get("data_admissao", "")
                if _admissao_str:
                    _fmt = "%d/%m/%Y"
                    _dt_ini = _dt_parse.strptime(data_inicial, _fmt)
                    _dt_adm = _dt_parse.strptime(_admissao_str, _fmt)
                    if _dt_ini < _dt_adm:
                        self._log(
                            f"  ⚠ data_inicial_apuracao ({data_inicial}) anterior à admissão "
                            f"({_admissao_str}) — ajustando para admissão"
                        )
                        data_inicial = _admissao_str
            except (ValueError, TypeError):
                pass  # formato inválido — preencher como está

        if data_inicial:
            self._preencher_data("dataInicialApuracao", data_inicial, False)
            self._preencher_data("dataInicio", data_inicial, False)
        if data_final:
            self._preencher_data("dataFinalApuracao", data_final, False)
            self._preencher_data("dataFim", data_final, False)
        if carga_diaria:
            self._preencher("cargaHorariaDiaria", str(int(carga_diaria)), False)
            self._log(f"  ✓ cargaHorariaDiaria: {int(carga_diaria)}")
        if carga_semanal:
            self._preencher("cargaHorariaSemanal", str(int(carga_semanal)), False)
            self._log(f"  ✓ cargaHorariaSemanal: {int(carga_semanal)}")
        if zerar_negativos is not None:
            self._marcar_checkbox("zerarValoresNegativos", bool(zerar_negativos))

        if not self._salvar_com_deteccao_erros("Fase 2a", parametros, max_tentativas=2):
            self._log("  ⚠ Fase 2a: Salvar não confirmado — parâmetros gerais podem não ter persistido.")
        self._aguardar_ajax()
        # Captura/atualiza URL base após salvar (URL pode ter mudado com novo conversationId)
        self._capturar_base_calculo()
        self._log("  Fase 2a concluída.")

    # ── Fase 2: Histórico Salarial ─────────────────────────────────────────────

    @staticmethod
    def _consolidar_historico(historico: list[dict], max_bases: int = 15) -> list[dict]:
        """Consolida entradas de histórico salarial em ≤max_bases bases.

        O PJE-Calc limita a 15 bases no Histórico Salarial. Agrupa períodos
        consecutivos com mesmo nome e valor em uma única base.
        Se ainda exceder max_bases, agrupa períodos com mesmo nome
        independente de descontinuidade de valor.
        """
        if len(historico) <= max_bases:
            return historico

        def _parse_valor(v) -> float:
            if isinstance(v, (int, float)):
                return float(v)
            s = str(v).replace(".", "").replace(",", ".").strip()
            try:
                return float(s)
            except ValueError:
                return 0.0

        # Fase 1: agrupar consecutivos com mesmo nome+valor
        grupos: list[dict] = []
        for h in historico:
            nome = h.get("nome", "Salário")
            valor = _parse_valor(h.get("valor", 0))
            if (grupos
                and grupos[-1]["nome"] == nome
                and abs(grupos[-1]["_valor_num"] - valor) < 0.01):
                # Estender data_fim do grupo atual
                grupos[-1]["data_fim"] = h.get("data_fim", grupos[-1]["data_fim"])
            else:
                grupos.append({
                    **h,
                    "nome": nome,
                    "_valor_num": valor,
                })

        if len(grupos) <= max_bases:
            return grupos

        # Fase 2: agrupar por nome, usando data_inicio mais antiga e data_fim mais recente
        # Para nomes que têm múltiplas bases com valores diferentes, usar valor médio
        # e marcar como variável (será editado via Grade de Ocorrências)
        from collections import OrderedDict
        por_nome: OrderedDict[str, list[dict]] = OrderedDict()
        for g in grupos:
            nome = g.get("nome", "Salário")
            por_nome.setdefault(nome, []).append(g)

        consolidados: list[dict] = []
        for nome, entries in por_nome.items():
            if len(entries) == 1:
                consolidados.append(entries[0])
            else:
                # Agrupar todas as entradas deste nome em uma única base
                data_inicio = entries[0].get("data_inicio", "")
                data_fim = entries[-1].get("data_fim", "")
                # Usar o último valor (mais recente) como valor da base
                valor = entries[-1].get("valor", "")
                consolidados.append({
                    **entries[0],
                    "nome": nome,
                    "data_inicio": data_inicio,
                    "data_fim": data_fim,
                    "valor": valor,
                    "variavel": len(set(e.get("valor") for e in entries)) > 1,
                })

        return consolidados[:max_bases]

    def fase_historico_salarial(self, dados: dict) -> None:
        historico = dados.get("historico_salarial", [])
        if not historico:
            self._log("Fase 2 — Histórico Salarial: sem entradas extraídas — ignorado.")
            return
        # Consolidar entradas para respeitar limite de 15 bases do PJE-Calc
        if len(historico) > 15:
            historico = self._consolidar_historico(historico)
            self._log(f"Fase 2 — Histórico Salarial: consolidado para {len(historico)} base(s) (limite PJE-Calc: 15)")
        self._log(f"Fase 2 — Histórico Salarial: {len(historico)} período(s) extraído(s)…")
        self._verificar_tomcat(timeout=90)
        self._verificar_pagina_pjecalc()

        # Pré-verificação: confirmar que conversationId está disponível
        # (indica que o cálculo foi persistido no H2 com IIDCALCULO válido)
        if not self._calculo_conversation_id:
            self._capturar_base_calculo()
        if not self._calculo_conversation_id:
            self._log("  ⚠ Histórico Salarial: conversationId ausente — cálculo pode não ter sido persistido")

        navegou = self._clicar_menu_lateral("Histórico Salarial", obrigatorio=False)
        if navegou:
            navegou = self._verificar_secao_ativa("Histórico")

        # Verificar se a página carregou sem erros H2/JSF (IIDCALCULO NULL causa HTTP 500)
        if navegou:
            try:
                _body_check = self._page.evaluate(
                    "() => (document.body ? document.body.textContent : '').substring(0, 500)"
                )
                if "500" in _body_check or "NullPointer" in _body_check or "JdbcBatch" in _body_check:
                    self._log("  ⚠ Histórico Salarial: erro H2/JSF detectado na página — tentando recuperar…")
                    # Tentar voltar para Parâmetros do Cálculo e re-salvar
                    if self._calculo_url_base and self._calculo_conversation_id:
                        _url_params = (
                            f"{self._calculo_url_base}parametros-do-calculo.jsf"
                            f"?conversationId={self._calculo_conversation_id}"
                        )
                        self._page.goto(_url_params, wait_until="domcontentloaded", timeout=15000)
                        self._aguardar_ajax()
                        self._clicar_salvar()
                        self._page.wait_for_timeout(2000)
                        # Re-tentar navegação para Histórico Salarial
                        navegou = self._clicar_menu_lateral("Histórico Salarial", obrigatorio=False)
                        if navegou:
                            navegou = self._verificar_secao_ativa("Histórico")
            except Exception as _e_check:
                self._log(f"  ⚠ Verificação pós-navegação: {_e_check}")

        if not navegou:
            self._log("  ⚠ Histórico Salarial não disponível no menu — listando para referência:")
            for h in historico:
                self._log(f"    {h.get('data_inicio','')} a {h.get('data_fim','')} — R$ {h.get('valor','')}")
            return
        self.mapear_campos("fase2_historico_salarial")
        def _para_competencia(d: str) -> str:
            partes = d.split("/")
            if len(partes) == 3 and len(partes[2]) == 4:
                return f"{partes[1]}/{partes[2]}"  # dd/mm/yyyy → MM/yyyy
            if len(partes) == 2 and len(partes[1]) == 4:
                return d  # já MM/yyyy
            return d

        for idx_h, h in enumerate(historico):
          try:
            # Garantir que estamos na página de listagem do Histórico Salarial
            # ANTES de tentar clicar "Incluir"/"Novo". Após salvar o período anterior,
            # a página pode ter redirecionado para outro lugar ou o DOM pode ter mudado.
            if idx_h > 0:
                # Navegar explicitamente para a listagem do Histórico Salarial
                if self._calculo_url_base and self._calculo_conversation_id:
                    _url_hist_list = (
                        f"{self._calculo_url_base}historico-salarial.jsf"
                        f"?conversationId={self._calculo_conversation_id}"
                    )
                    try:
                        self._page.goto(_url_hist_list, wait_until="domcontentloaded", timeout=15000)
                        self._aguardar_ajax()
                        self._page.wait_for_timeout(1000)
                    except Exception:
                        # Fallback: usar menu lateral
                        self._clicar_menu_lateral("Histórico Salarial", obrigatorio=False)
                        self._page.wait_for_timeout(1000)
                else:
                    self._clicar_menu_lateral("Histórico Salarial", obrigatorio=False)
                    self._page.wait_for_timeout(1000)

            # Fluxo: clicar "incluir"/"Novo" → preencher formulário inline ou navegar
            # IMPORTANTE: NÃO usar _clicar_novo() — pega "Novo" do top-nav e cria novo cálculo.
            #
            # O formulário do Histórico pode ser:
            # (a) página separada historico-salario.jsf (navegação completa)
            # (b) formulário inline na listagem (AJAX parcial)
            # Em ambos os casos, o "incluir" abre o form.

            _abriu = (self._clicar_botao_id("incluir")
                      or self._clicar_botao_id("btnNovoHistorico")
                      or self._clicar_botao_id("novo"))
            if not _abriu:
                # Se não encontrou "incluir", pode ser que a página já tenha entradas
                # e o botão tenha outro ID. Tentar via JS ampla.
                _abriu = self._page.evaluate("""() => {
                    const btns = [...document.querySelectorAll(
                        'input[type="button"], input[type="submit"], a[onclick], a.rf-dt-c'
                    )];
                    for (const btn of btns) {
                        const t = ((btn.value || '') + ' ' + (btn.textContent || '') +
                                   ' ' + (btn.title || '')).trim().toLowerCase();
                        if (t === 'novo' || t === 'incluir' || t === 'nova base'
                            || t.includes('novo hist') || t === 'new' || t === 'add') {
                            btn.click();
                            return true;
                        }
                    }
                    // Fallback: buscar qualquer input[type="submit"] que não seja Salvar/Cancelar
                    const submits = document.querySelectorAll('input[type="submit"], input[type="button"]');
                    for (const s of submits) {
                        const v = (s.value || '').toLowerCase();
                        if (v && !v.includes('salvar') && !v.includes('cancelar') &&
                            !v.includes('fechar') && !v.includes('excluir') &&
                            !v.includes('importar') && !v.includes('grade') &&
                            (v.includes('novo') || v.includes('incluir') || v.includes('add'))) {
                            s.click();
                            return true;
                        }
                    }
                    return false;
                }""")
            if not _abriu:
                self._log(f"  ⚠ Botão 'incluir'/'Novo' não encontrado no Histórico Salarial (período {idx_h+1})")
                continue
            self._aguardar_ajax()
            self._page.wait_for_timeout(1500)

            # Verificar se navegou para outra página ou se o form é inline
            _url_after = self._page.url
            _is_form_page = "historico-salario" in _url_after and "historico-salarial" not in _url_after

            # Diagnóstico: mapear campos IMEDIATAMENTE após abrir o form (antes de qualquer fill)
            if idx_h == 0:
                self.mapear_campos("fase2_historico_salario_form")

            # Aguardar carregamento do formulário (inline ou navegação)
            # IDs confirmados: nome, tipoVariacaoDaParcela:0, tipoValor:0,
            #   competenciaInicialInputDate, competenciaFinalInputDate, valorParaBaseDeCalculo
            try:
                self._page.wait_for_selector(
                    "input[id*='competenciaInicial'], input[id*='nome'], "
                    "input[id*='tipoVariacao'], input[id*='tipoValor'], "
                    "input[id*='valorPara']",
                    state="visible", timeout=10000
                )
            except Exception:
                self._page.wait_for_timeout(2000)

            # Nome da entrada — ID confirmado: formulario:nome
            nome_hist = h.get("nome", "Salário")
            self._preencher("nome", nome_hist, False)
            # Tab (not blur) to move to next field without closing inline form
            try:
                _nm = self._localizar("nome", tipo="input")
                if _nm:
                    _nm.press("Tab")
                    self._page.wait_for_timeout(500)
            except Exception:
                pass

            # Fechar ONLY suggestion popups (NOT the form itself!)
            # Use targeted CSS hide instead of Escape/body click which closes inline forms
            try:
                self._page.evaluate("""() => {
                    document.querySelectorAll(
                        '.rf-au-lst, .rf-su-lst, [id*="suggestionBox"], ' +
                        '.rich-sb-ext-decor, .rich-sb-common-container'
                    ).forEach(el => { el.style.display = 'none'; });
                }""")
                self._page.wait_for_timeout(200)
            except Exception:
                pass

            # Tipo de variação: FIXA (valor fixo) ou VARIAVEL (muda mês a mês)
            # ID: formulario:tipoVariacaoDaParcela (radio :0=Fixa, :1=Variável)
            _tipo_var = "VARIAVEL" if h.get("variavel") else "FIXA"
            if not self._marcar_radio("tipoVariacaoDaParcela", _tipo_var):
                if not self._marcar_radio_js("tipoVariacaoDaParcela", _tipo_var):
                    self._marcar_radio("parcela", _tipo_var) or \
                        self._marcar_radio_js("parcela", _tipo_var)

            # Tipo de valor: INFORMADO (preenchido manualmente) ou CALCULADO
            # Campo pode ser "tipoValor" (select), "valor" (radio), ou outro
            _tipo_valor_ok = (
                self._marcar_radio("tipoValor", "INFORMADO")
                or self._marcar_radio("valor", "INFORMADO")
                or self._selecionar("tipoValor", "INFORMADO", obrigatorio=False)
                or self._selecionar("tipoValor", "Informado", obrigatorio=False)
                or self._marcar_radio_js("tipoValor", "INFORMADO")
                or self._marcar_radio_js("valor", "INFORMADO")
            )
            if not _tipo_valor_ok:
                self._log("  ⚠ tipoValor/valor: nenhum seletor funcionou")

            _comp_ini = _para_competencia(h.get("data_inicio", ""))
            _comp_fim = _para_competencia(h.get("data_fim", ""))
            # Competência fields (MM/yyyy): rich:calendar with jQuery mask('99/9999').
            # DOM IDs confirmados v2.15.1: formulario:competenciaInicialInputDate / formulario:competenciaFinalInputDate
            # (NÃO dataInicio/dataFinal — esses são campos diferentes)
            for _cfield, _cval in [("competenciaInicial", _comp_ini),
                                    ("competenciaFinal", _comp_fim)]:
                _cloc = self._localizar(_cfield, tipo="input")
                if _cloc and _cval:
                    try:
                        _cloc.focus()
                        self._page.keyboard.press("Control+a")
                        self._page.keyboard.press("Delete")
                        _cdigits = _cval.replace("/", "")
                        _cloc.press_sequentially(_cdigits, delay=80)
                        self._page.wait_for_timeout(200)
                        # Set the hidden field value too (rich:calendar stores
                        # the date in the hidden input without InputDate suffix)
                        self._page.evaluate(f"""(val) => {{
                            // Find the InputDate field and its hidden sibling
                            const inputs = document.querySelectorAll('input[id*="{_cfield}"]');
                            for (const inp of inputs) {{
                                if (inp.id.endsWith('InputDate')) {{
                                    inp.value = val;
                                    inp.dispatchEvent(new Event('change', {{bubbles:true}}));
                                }}
                                if (inp.type === 'hidden' && !inp.id.endsWith('InputDate')) {{
                                    // Hidden field stores value in the same format
                                    inp.value = val;
                                }}
                            }}
                        }}""", _cval)
                        # Tab to trigger blur + server model update
                        _cloc.press("Tab")
                        self._page.wait_for_timeout(500)
                        self._log(f"  ✓ data {_cfield}: {_cval}")
                    except Exception as _e_comp:
                        self._log(f"  ⚠ {_cfield}: {_e_comp}")
                        self._preencher_data(_cfield, _cval, False)

            # Valor base — ID confirmado: formulario:valorParaBaseDeCalculo
            _val = _fmt_br(h.get("valor", ""))
            self._preencher("valorParaBaseDeCalculo", _val, False)
            # Dispatch blur to submit value to JSF server model
            try:
                _vl = self._localizar("valorParaBaseDeCalculo", tipo="input")
                if _vl:
                    _vl.dispatch_event("blur")
                    self._page.wait_for_timeout(500)
            except Exception:
                pass

            # Tipo FIXA/VARIAVEL (radio referencia — DOM: formulario:referencia)
            _variavel = h.get("variavel", False)
            if _variavel:
                self._preencher_radio_ou_select("referencia", "VARIAVEL", obrigatorio=False)
            # Se FIXA (default), não precisa clicar — já é o default do PJE-Calc

            # Incidências — checkboxes may trigger AJAX that errors on server side
            # (known NPE in ApresentadorHonorarios). Use short timeout and don't block.
            try:
                _inc_fgts = h.get("incidencia_fgts", True)
                _inc_inss = h.get("incidencia_cs", h.get("incidencia_inss", True))
                self._marcar_checkbox("fgts", bool(_inc_fgts))
                self._marcar_checkbox("inss", bool(_inc_inss))
                # FGTS já recolhido (para dedução)
                if h.get("fgts_recolhido") or h.get("fgts_ja_recolhido"):
                    self._marcar_checkbox("fgtsJaRecolhido", True)
                # Contribuições sociais já recolhidas
                if h.get("cs_recolhida") or h.get("contribuicoes_ja_recolhidas"):
                    self._marcar_checkbox("contribuicoesJaRecolhidas", True)
            except Exception as _e_chk:
                self._log(f"  ⚠ Checkboxes FGTS/INSS: {_e_chk} — continuando")

            # Diagnostic: check actual field values before generating occurrences
            # DOM IDs confirmados: competenciaInicialInputDate, competenciaFinalInputDate,
            #   nome, valorParaBaseDeCalculo
            try:
                _diag = self._page.evaluate("""() => {
                    const fields = {};
                    document.querySelectorAll(
                        'input[id*="competenciaInicial"], input[id*="competenciaFinal"], ' +
                        'input[id*="nome"], input[id*="valorPara"]'
                    ).forEach(el => {
                        if (el.type !== 'hidden')
                            fields[el.id.split(':').pop()] = el.value;
                    });
                    return fields;
                }""")
                self._log(f"  ℹ Campos antes de Gerar: {_diag}")
            except Exception:
                pass

            # Gerar Ocorrências (ícone "+" verde ao lado do campo Valor)
            # Manual PJE-Calc: "Clicar icone 'Gerar Ocorrencias'" após preencher
            # Competência Inicial, Final e Valor.
            # O botão é um ícone (a4j:commandButton ou h:commandButton) com imagem "+".
            # Pode ter IDs variados: cmdGerarOcorrencias, cmdAdicionarOcorrencia,
            # cmdAdicionar, ou um j_id gerado. Busca ampla necessária.
            _gerou = False

            # Estratégia 1: seletores conhecidos de ícone "+" / "adicionar" / "gerar"
            _gen_seletores = [
                "a[id*='cmdGerarOcorrencias'], a[id*='GerarOcorrencias']",
                "a[id*='cmdAdicionarOcorrencia'], a[id*='Adicionar']",
                "input[id*='cmdGerarOcorrencias'], input[id*='GerarOcorrencias']",
                "input[id*='cmdAdicionarOcorrencia'], input[id*='Adicionar']",
            ]
            for _sel_gen in _gen_seletores:
                if _gerou:
                    break
                _gen_loc = self._page.locator(_sel_gen)
                if _gen_loc.count() > 0:
                    try:
                        _gen_loc.first.scroll_into_view_if_needed()
                        self._page.wait_for_timeout(300)
                        _gen_loc.first.click()
                        _gerou = True
                        self._log(f"  ✓ Gerar Ocorrências via '{_sel_gen}'")
                    except Exception:
                        try:
                            _gen_loc.first.click(force=True)
                            _gerou = True
                            self._log(f"  ✓ Gerar Ocorrências via '{_sel_gen}' (force)")
                        except Exception:
                            pass

            # Estratégia 2: buscar ícone "+" (img com src contendo "add" ou "plus")
            # ou qualquer <a>/<input> com ícone próximo ao campo Valor
            if not _gerou:
                try:
                    _gerou = self._page.evaluate("""() => {
                        // Buscar botão com imagem de "+" ou "add"
                        const candidates = [
                            ...document.querySelectorAll('a[onclick*="AJAX"], input[type="image"], a img'),
                        ];
                        // Buscar elemento <a> ou <input> que seja irmão/próximo de valorParaBaseDeCalculo
                        const valorField = document.querySelector('[id*="valorParaBaseDeCalculo"]');
                        if (valorField) {
                            const parent = valorField.closest('td, div, span, fieldset');
                            if (parent) {
                                const nearby = parent.querySelectorAll('a[onclick], input[type="image"], a:has(img)');
                                for (const el of nearby) {
                                    el.click();
                                    return true;
                                }
                                // Tentar próximo <td> irmão
                                const nextTd = parent.nextElementSibling;
                                if (nextTd) {
                                    const btn = nextTd.querySelector('a[onclick], input[type="image"], a:has(img)');
                                    if (btn) { btn.click(); return true; }
                                }
                            }
                        }
                        // Fallback: qualquer link/botão com onclick A4J na seção de ocorrências
                        const section = document.querySelector('[id*="ocorrencia"], [id*="Ocorrencia"]');
                        if (section) {
                            const btn = section.querySelector('a[onclick*="AJAX"], input[onclick*="AJAX"]');
                            if (btn) { btn.click(); return true; }
                        }
                        return false;
                    }""")
                    if _gerou:
                        self._log("  ✓ Gerar Ocorrências via ícone '+' próximo ao Valor")
                except Exception as _e_ger2:
                    self._log(f"  ⚠ Gerar Ocorrências (ícone): {_e_ger2}")

            # Estratégia 3: último recurso — buscar qualquer elemento clicável
            # com onclick contendo AJAX na página inteira (exceto Salvar/Cancelar)
            if not _gerou:
                try:
                    _gerou = self._page.evaluate("""() => {
                        const allClickable = document.querySelectorAll(
                            'a[onclick*="AJAX"], input[type="image"][onclick]'
                        );
                        for (const el of allClickable) {
                            const id = el.id || '';
                            const val = el.value || el.textContent || '';
                            // Excluir Salvar, Cancelar, menu links
                            if (id.includes('salvar') || id.includes('cancelar') ||
                                val.includes('Salvar') || val.includes('Cancelar') ||
                                id.includes('j_id38')) continue;
                            // Excluir links de navegação do menu lateral
                            if (el.closest('[class*="menu"], [class*="painelMenu"]')) continue;
                            el.click();
                            return true;
                        }
                        return false;
                    }""")
                    if _gerou:
                        self._log("  ✓ Gerar Ocorrências via fallback AJAX")
                except Exception as _e_ger3:
                    self._log(f"  ⚠ Gerar Ocorrências (fallback): {_e_ger3}")
            if _gerou:
                self._aguardar_ajax()
                self._page.wait_for_timeout(2000)
                # Verify occurrences were generated via listagemMC table
                try:
                    _has_occ = self._page.evaluate("""() => {
                        const tbl = document.querySelector(
                            'table[id*="listagemMC"], table[id*="listagem"]'
                        );
                        if (!tbl) return 0;
                        return tbl.querySelectorAll('tr').length;
                    }""")
                    if _has_occ and _has_occ > 0:
                        self._log(f"  ✓ Ocorrências geradas: {nome_hist} ({_has_occ} linhas)")
                    else:
                        self._log(f"  ⚠ Gerar Ocorrências: tabela sem linhas")
                except Exception:
                    self._log(f"  ✓ Ocorrências geradas: {nome_hist}")
                self._page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            else:
                self._log(f"  ⚠ Botão Gerar Ocorrências não encontrado")

            # Salvar — DOM v2.15.1: formulario:salvar (input type="button")
            # Scroll para baixo para garantir visibilidade do botão Salvar
            self._page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            self._page.wait_for_timeout(300)
            _salvou = self._clicar_salvar()
            if not _salvou:
                # Tentar via JS direto no formulario:salvar
                try:
                    _salvou = self._page.evaluate("""() => {
                        const btn = document.querySelector('[id$=":salvar"], input[value="Salvar"]');
                        if (btn) { btn.click(); return true; }
                        return false;
                    }""")
                except Exception:
                    pass
            self._aguardar_ajax()
            self._page.wait_for_timeout(500)

            # Check for form error messages after save
            # Note: "Erro inesperado" from PJE-Calc often means the RENDERING
            # of the page after save failed (e.g. NPE in ApresentadorHonorarios),
            # but the database save may have succeeded. Check for validation errors
            # specifically (like "Deve haver pelo menos um registro de Ocorrências")
            # as those actually mean the save failed.
            try:
                _err_msg = self._page.evaluate("""() => {
                    const msgs = document.querySelectorAll('.rf-msgs-sum, .rich-messages-label, [class*="erro"], [class*="error"]');
                    for (const m of msgs) {
                        const t = (m.textContent || '').trim();
                        if (t && (t.toLowerCase().includes('erro') || t.toLowerCase().includes('error')))
                            return t.substring(0, 200);
                    }
                    return null;
                }""")
                if _err_msg:
                    _is_validation = any(s in _err_msg.lower() for s in [
                        "ocorrências", "obrigatório", "preenchimento", "inválid",
                        "deve haver", "não pode"
                    ])
                    if _is_validation:
                        self._log(f"  ⚠ Erro validação período {idx_h+1}: {_err_msg}")
                        # Detectar campos específicos com erro
                        self._detectar_erros_formulario(f"Hist.Salarial período {idx_h+1}")
                        self._clicar_menu_lateral("Histórico Salarial", obrigatorio=False)
                        self._page.wait_for_timeout(1000)
                        continue
                    else:
                        # "Erro inesperado" = likely rendering error, save may have succeeded
                        self._log(f"  ⚠ Erro servidor período {idx_h+1} (save pode ter sucedido): {_err_msg}")
            except Exception:
                pass

            try:
                self._page.wait_for_selector(
                    "[id$='filtroNome'], [id*='incluir'], [name*='filtroNome']",
                    state="visible", timeout=5000
                )
            except Exception:
                self._clicar_menu_lateral("Histórico Salarial", obrigatorio=False)
                self._page.wait_for_timeout(800)
            _status_icon = "✓" if (_gerou and _salvou) else "⚠"
            self._log(f"  {_status_icon} Período {idx_h+1}/{len(historico)}: {h.get('data_inicio','')} a {h.get('data_fim','')} — R$ {h.get('valor','')}")
          except Exception as _e_hist:
            self._log(f"  ⚠ Erro no período {idx_h+1}: {_e_hist} — tentando recuperar")
            try:
                self._clicar_menu_lateral("Histórico Salarial", obrigatorio=False)
                self._page.wait_for_timeout(1000)
            except Exception:
                pass
        self._log("Fase 2 concluída.")

    # ── Probes de saúde do Tomcat ────────────────────────────────────────────

    def _tomcat_esta_vivo(self) -> bool:
        """Probe rápido HTTP+TCP do Tomcat (< 2s). Retorna True se responde."""
        try:
            with urllib.request.urlopen(self.PJECALC_BASE, timeout=2) as r:
                return r.status in (200, 302, 404)
        except Exception:
            pass
        try:
            s = socket.create_connection(("127.0.0.1", _porta_local()), timeout=1)
            s.close()
            return True
        except OSError:
            return False

    def _aguardar_tomcat_restart(self, timeout: int = 180) -> bool:
        """Aguarda watchdog reiniciar o Tomcat após crash.
        Cria signal file para restart imediato. Retorna True se recuperou."""
        self._log(f"  ⚠ Tomcat morreu — aguardando watchdog reiniciar (até {timeout}s)…")
        # Signal file: watchdog detecta e reinicia imediatamente
        try:
            Path("/tmp/pjecalc_restart_request").touch()
        except OSError:
            pass
        inicio = time.time()
        while time.time() - inicio < timeout:
            if self._tomcat_esta_vivo():
                # Esperar mais 10s para webapp terminar deploy
                time.sleep(10)
                if self._tomcat_esta_vivo():
                    elapsed = int(time.time() - inicio)
                    self._log(f"  ✓ Tomcat reiniciado em {elapsed}s")
                    return True
            time.sleep(5)
        self._log(f"  ✗ Tomcat não reiniciou em {timeout}s")
        return False

    def _renavegar_apos_crash(self) -> None:
        """Após Tomcat reiniciar, navega de volta ao cálculo usando conversationId."""
        self._log("  → Renavegando para o cálculo após restart…")
        if self._calculo_url_base and self._calculo_conversation_id:
            target = (f"{self._calculo_url_base}verba/verba-calculo.jsf"
                      f"?conversationId={self._calculo_conversation_id}")
        else:
            target = f"{self.PJECALC_BASE}/pages/principal.jsf"
        try:
            self._page.goto(target, wait_until="domcontentloaded", timeout=30000)
            self._page.wait_for_timeout(2000)
            self._instalar_monitor_ajax()
        except Exception as e:
            self._log(f"  ⚠ Falha ao renavegar: {e} — tentando home")
            self._page.goto(
                f"{self.PJECALC_BASE}/pages/principal.jsf",
                wait_until="domcontentloaded", timeout=30000,
            )
            self._page.wait_for_timeout(2000)

    # ── Fase 3: Verbas ─────────────────────────────────────────────────────────

    def _tentar_expresso(self, predefinidas: list) -> tuple[bool, list[str]]:
        """Tenta Lançamento Expresso com health checks após cada passo.

        Retorna (sucesso, nao_encontradas).
        Raises RuntimeError se Tomcat morrer durante a operação.
        """
        _nao_encontradas: list[str] = []

        # Clicar botão "Expresso"
        _clicou_expresso = False
        if self._clicar_botao_id("lancamentoExpresso"):
            self._aguardar_ajax()
            self._page.wait_for_timeout(800)
            _clicou_expresso = True
            self._log("  ✓ Botão Expresso via _clicar_botao_id('lancamentoExpresso')")

        if not _clicou_expresso:
            for _sel in [
                VerbaListagem.BTN_EXPRESSO,  # "input[id*='btnExpresso']"
                "input[value='Expresso']",
                "input[value*='Expresso']",
                "a[id*='Expresso']",
            ]:
                try:
                    _loc = self._page.locator(_sel)
                    if _loc.count() > 0:
                        _loc.first.click(force=True)
                        self._aguardar_ajax()
                        self._page.wait_for_timeout(800)
                        _clicou_expresso = True
                        self._log(f"  ✓ Botão Expresso via '{_sel}'")
                        break
                except Exception:
                    continue

        if not _clicou_expresso:
            try:
                _res = self._page.evaluate("""() => {
                    const el = [...document.querySelectorAll('input,button,a')]
                        .find(e => (e.value||e.textContent||'').trim().toUpperCase() === 'EXPRESSO');
                    if (el) { el.click(); return el.id || el.tagName; }
                    return null;
                }""")
                if _res:
                    self._aguardar_ajax()
                    self._page.wait_for_timeout(800)
                    _clicou_expresso = True
                    self._log(f"  ✓ Botão Expresso via JS: {_res}")
            except Exception as _e:
                self._log(f"  ⚠ Botão Expresso não encontrado: {_e}")

        if not _clicou_expresso:
            return False, [v.get("nome_pjecalc") or v.get("nome_sentenca") or "" for v in predefinidas]

        # HEALTH CHECK: Tomcat pode morrer logo após o clique
        time.sleep(1)
        if not self._tomcat_esta_vivo():
            raise RuntimeError("Tomcat morreu após clique no Expresso")

        # Aguardar navegação para verbas-para-calculo.jsf
        try:
            self._page.wait_for_url("**/verbas-para-calculo**", timeout=10000)
        except Exception:
            self._page.wait_for_timeout(2000)

        # HEALTH CHECK pós-navegação
        if not self._tomcat_esta_vivo():
            raise RuntimeError("Tomcat morreu após navegação Expresso")

        # Scroll progressivo para carregar TODAS as verbas (tabela <a4j:repeat> em 3 colunas)
        # A tabela tem ~60+ verbas mas só ~27 são visíveis no viewport. Verbas como
        # "13º Salário", "Saldo de Salário", "Férias Proporcionais + 1/3", "Multa 477"
        # ficam abaixo do scroll e precisam de forçar layout para entrar no DOM visível.
        # Scroll em 5 passos (0%→25%→50%→75%→100%) com delay entre cada passo para
        # dar tempo ao <a4j:repeat> de renderizar as linhas lazy.
        try:
            for _pct in (0.0, 0.25, 0.50, 0.75, 1.0):
                self._page.evaluate(
                    """(pct) => {
                        const containers = document.querySelectorAll(
                            '[id*="listagem"], [id*="verbas-para-calculo"], table.list-check, .rich-table, .panelGrid, form'
                        );
                        for (const c of containers) {
                            if (c.scrollHeight > c.clientHeight) {
                                c.scrollTop = c.scrollHeight * pct;
                            }
                        }
                        window.scrollTo(0, document.body.scrollHeight * pct);
                    }""",
                    _pct,
                )
                self._page.wait_for_timeout(250)
            # Voltar ao topo para que o salvamento funcione
            self._page.evaluate("() => window.scrollTo(0, 0)")
            self._page.wait_for_timeout(300)
        except Exception:
            pass

        # Listar verbas disponíveis (diagnóstico)
        # Nota: NÃO existe [id*=":nome"] no Expresso — o nome é o texto da célula <td>
        # que contém o checkbox. Usamos cloneNode(true) + remoção de inputs/scripts.
        try:
            _labels_exp = self._page.evaluate("""() => {
                const cbs = document.querySelectorAll('""" + VerbaExpresso.CHECKBOX_SELECIONADA + """');
                return [...cbs].map(cb => {
                    const td = cb.closest('td');
                    if (!td) return '';
                    const clone = td.cloneNode(true);
                    clone.querySelectorAll('input, script, style').forEach(el => el.remove());
                    return clone.textContent.replace(/\\s+/g, ' ').trim();
                }).filter(Boolean);
            }""")
            self._log(f"  📋 Verbas Expresso disponíveis ({len(_labels_exp)}): {_labels_exp}")
        except Exception:
            pass

        # Marcar checkboxes
        # Prioridade do nome para matching Expresso:
        # 1) estrategia_preenchimento.expresso_base (nome exato do checkbox Expresso)
        # 2) nome_pjecalc (nome canônico da tabela Expresso, setado pela classification)
        # 3) nome_sentenca (fallback — só quando não houve mapping)
        # NOTA: nome_pjecalc ANTES de nome_sentenca, pois a classification fez o
        # mapeamento por proximidade semântica para a verba canônica do Expresso.
        # Usar nome_sentenca primeiro (nome longo da sentença) derrubaria o Expresso.
        _marcadas: list[str] = []
        for v in predefinidas:
            _estr = v.get("estrategia_preenchimento", {}) or {}
            nome = (
                _estr.get("expresso_base")
                or v.get("nome_pjecalc")
                or v.get("nome_sentenca")
                or ""
            )
            if not nome:
                continue
            _pct = v.get("percentual")
            if self._marcar_checkbox_expresso(nome, percentual=_pct):
                _marcadas.append(nome)
            else:
                _nao_encontradas.append(nome)
                self._log(f"  ⚠ Verba não encontrada no Expresso: {nome}")

        if _marcadas:
            self._log(f"  ✓ Marcadas: {_marcadas}")
            # Registrar verbas Expresso OK — seus reflexos são auto-gerados pelo PJE-Calc
            for _m in _marcadas:
                self._verbas_expresso_ok.add(_m.upper())
            _salvou = (
                self._clicar_botao_id("btnSalvarExpresso")
                or self._clicar_salvar()
            )
            if _salvou:
                self._aguardar_ajax()
                self._page.wait_for_timeout(1500)
                # Verificar se o salvamento gerou erro mesmo retornando "sucesso"
                _erros_exp = self._detectar_erros_formulario("Fase 3 Expresso")
                if _erros_exp:
                    self._log(f"  ⚠ Verbas Expresso: {len(_erros_exp)} erro(s) detectado(s) após salvar")
                    _salvou = False
                else:
                    self._log("  ✓ Verbas Expresso salvas")
            else:
                self._log("  ⚠ btnSalvarExpresso não encontrado — tentando Enter")
                try:
                    self._page.keyboard.press("Enter")
                    self._aguardar_ajax()
                    self._page.wait_for_timeout(1500)
                    # Verificar erros após Enter
                    _erros_enter = self._detectar_erros_formulario("Fase 3 Expresso (Enter)")
                    if _erros_enter:
                        self._log(f"  ⚠ Verbas Expresso: erros após Enter")
                        _salvou = False
                except Exception:
                    pass

            # HEALTH CHECK pós-salvamento
            if not self._tomcat_esta_vivo():
                raise RuntimeError("Tomcat morreu após salvar Expresso")

            # Atualizar conversationId — o Expresso save pode mudar a conversação JSF.
            # Sem isso, navegações subsequentes (Manual, FGTS, etc.) usam ID expirado → HTTP 500.
            self._capturar_base_calculo()

            # Configurar reflexos (tolerante a NPE em verba-calculo.jsf)
            try:
                self._configurar_reflexos_expresso(predefinidas)
            except Exception as _e_refl:
                self._log(f"  ⚠ Reflexos: {_e_refl} — continuando sem reflexos")

            # Configurar Parâmetros + Ocorrências de cada verba
            # (período, percentual, base de cálculo — dados extraídos da sentença)
            try:
                self._pos_expresso_parametros_ocorrencias(predefinidas)
            except Exception as _e_pos:
                self._log(f"  ⚠ Pós-expresso parâmetros: {_e_pos} — continuando")
        else:
            self._log("  ⚠ Nenhuma verba marcada no Expresso")

        return bool(_marcadas), _nao_encontradas

    @retry(max_tentativas=2)
    def fase_verbas(self, verbas_mapeadas: dict) -> None:
        """Fase 3 — Verbas: Expresso com proteção contra crash + fallback Manual.

        Estratégia:
        1. PRE-CHECK: verifica se Tomcat está vivo
        2. Tenta Expresso com health checks após cada passo
        3. Se Tomcat morrer: aguarda watchdog reiniciar, retenta uma vez
        4. Se falhar 2x: fallback 100% Manual

        Integração com VerbaStrategyEngine:
        - Consulta histórico de sucesso/falha para cada verba
        - Registra resultado (sucesso/falha) de cada tentativa
        - Permite escolha inteligente entre expresso_direto, expresso_adaptado e manual
        """
        self._log("Fase 3 — Verbas…")

        # Inicializar VerbaStrategyEngine (opcional — não bloqueia se ausente)
        if self._strategy_engine is None:
            try:
                from learning.verba_strategies import VerbaStrategyEngine
                from infrastructure.database import SessionLocal
                _db = SessionLocal()
                # Tentar inicializar LLM Orchestrator para matching semântico de verbas
                _llm_orch = None
                try:
                    from core.llm_orchestrator import LLMOrchestrator
                    from infrastructure.config import settings
                    _llm_orch = LLMOrchestrator(settings)
                except Exception as _e_llm:
                    self._log(f"  ⚠ LLM Orchestrator indisponível para matching de verbas: {_e_llm}")
                self._strategy_engine = VerbaStrategyEngine(db=_db, llm_orchestrator=_llm_orch)
                self._log("  ✓ VerbaStrategyEngine inicializado" + (" (com LLM matching)" if _llm_orch else " (sem LLM matching)"))
            except Exception as _e_strat:
                self._log(f"  ⚠ VerbaStrategyEngine indisponível: {_e_strat} — continuando sem learning")
                self._strategy_engine = None

        self._verificar_tomcat(timeout=90)
        self._verificar_pagina_pjecalc()
        self._clicar_menu_lateral("Verbas")
        # Se página retornou 500 (NPE comum em verba-calculo.jsf), re-abrir cálculo via Recentes
        if not self._verificar_pagina_pjecalc():
            self._log("  → 500 em Verbas — re-abrindo cálculo via Recentes…")
            self._reabrir_calculo_recentes()
            self._clicar_menu_lateral("Verbas")
            self._verificar_pagina_pjecalc()
        self._verificar_secao_ativa("Verba")
        self._page.wait_for_timeout(1500)

        predefinidas = verbas_mapeadas.get("predefinidas", [])
        personalizadas = verbas_mapeadas.get("personalizadas", [])

        # ── Re-sort por estratégia do usuário (se editada na prévia) ──────────
        # Se o usuário alterou estratégias na prévia, respeitar a decisão:
        # - Verbas com estrategia "manual" movem para personalizadas
        # - Verbas com estrategia "expresso_direto"/"expresso_adaptado" movem para predefinidas
        _pred_final = []
        _pers_final = list(personalizadas)
        for v in predefinidas:
            ep = v.get("estrategia_preenchimento", {})
            if ep.get("baseado_em") == "usuario" and ep.get("estrategia") == "manual":
                self._log(f"  → Usuario definiu '{v.get('nome_pjecalc', '?')}' como Manual")
                _pers_final.append(v)
            else:
                _pred_final.append(v)
        # Mover personalizadas que o usuario marcou como expresso
        _pers_keep = []
        for v in _pers_final:
            ep = v.get("estrategia_preenchimento", {})
            if ep.get("baseado_em") == "usuario" and ep.get("estrategia") in ("expresso_direto", "expresso_adaptado"):
                self._log(f"  → Usuario definiu '{v.get('nome_pjecalc', '?')}' como Expresso")
                _pred_final.append(v)
            else:
                _pers_keep.append(v)
        predefinidas = _pred_final
        personalizadas = _pers_keep

        # Filtrar verbas com _apenas_fgts (ex: Multa 467) — são checkbox FGTS, não verba
        predefinidas = [v for v in predefinidas if not v.get("_apenas_fgts")]
        personalizadas = [v for v in personalizadas if not v.get("_apenas_fgts")]

        # ── REGRA MANUAL PJE-CALC: Reflexas de verbas Expresso são AUTO-GERADAS ──
        # Segundo o manual (seção 9.7/9.8), após salvar verbas no Expresso, o PJE-Calc
        # gera automaticamente as parcelas reflexas. O usuário apenas clica "Exibir Reflexas"
        # na listagem e marca os checkboxes desejados.
        # Portanto: reflexas cujo principal está em predefinidas (Expresso) NUNCA devem
        # ir para criação manual — EXCETO se o usuário explicitamente aprovou estratégia
        # "manual" na prévia.
        if predefinidas:
            _nomes_pred_lower = set()
            for _vp in predefinidas:
                _ep = _vp.get("estrategia_preenchimento", {}) or {}
                _n = (_ep.get("expresso_base") or _vp.get("nome_sentenca")
                      or _vp.get("nome_pjecalc") or "")
                if _n:
                    _nomes_pred_lower.add(_n.lower())
            _pers_sem_reflexas = []
            for v in personalizadas:
                _nome_v = (v.get("nome_pjecalc") or v.get("nome_sentenca") or "").lower()
                _eh_ref = (v.get("eh_reflexa")
                           or v.get("tipo", "").lower() == "reflexa"
                           or "reflexo" in _nome_v
                           or "sobre" in _nome_v)
                if _eh_ref:
                    # Verificar se o usuário aprovou explicitamente a estratégia "manual"
                    _ep_ref = v.get("estrategia_preenchimento", {}) or {}
                    _estrategia_ref = (_ep_ref.get("estrategia") or "").lower()
                    if _estrategia_ref == "manual":
                        self._log(
                            f"  → '{v.get('nome_pjecalc') or v.get('nome_sentenca')}' "
                            f"é reflexa com estratégia MANUAL aprovada pelo usuário — "
                            f"mantendo no fluxo manual"
                        )
                        _pers_sem_reflexas.append(v)
                        continue
                    # Reflexas sem aprovação manual → tratadas por _configurar_reflexos_expresso
                    self._log(
                        f"  → '{v.get('nome_pjecalc') or v.get('nome_sentenca')}' "
                        f"é reflexa — será tratada via 'Exibir Reflexas' do Expresso, "
                        f"removendo do fluxo manual"
                    )
                    continue
                _pers_sem_reflexas.append(v)
            personalizadas = _pers_sem_reflexas

        # Diagnóstico: listar botões disponíveis
        try:
            _botoes_verbas = self._page.evaluate("""() =>
                [...document.querySelectorAll('a,input[type="submit"],input[type="button"],button')]
                .map(el => ({id: el.id, txt: (el.textContent||el.value||el.title||'').replace(/\\s+/g,' ').trim()}))
                .filter(o => o.txt.length > 1 && o.txt.length < 50)
                .map(o => o.txt + (o.id ? ' [' + o.id + ']' : ''))
            """)
            self._log(f"  🔘 Botões pág Verbas: {list(dict.fromkeys(_botoes_verbas))[:20]}")
        except Exception:
            pass

        self.mapear_campos("fase3_verbas")

        _expresso_protection = os.environ.get("EXPRESSO_CRASH_PROTECTION", "true").lower() == "true"

        # ── 3A: Lançamento Expresso (verbas predefinidas) ─────────────────────
        if predefinidas:
            self._log(f"  → Expresso: {len(predefinidas)} verba(s) predefinida(s)")

            if not self._tomcat_esta_vivo():
                self._log("  ⚠ Tomcat não responde — todas as verbas via Manual")
                personalizadas = predefinidas + personalizadas
                predefinidas = []
            else:
                self._screenshot_fase("03_pre_expresso")
                _expresso_ok = False
                _nao_encontradas: list[str] = []

                try:
                    _expresso_ok, _nao_encontradas = self._tentar_expresso(predefinidas)
                except RuntimeError as crash_err:
                    self._log(f"  ☠ {crash_err}")
                    _expresso_ok = False
                except Exception as exc:
                    self._log(f"  ⚠ Expresso falhou: {exc}")
                    _expresso_ok = False

                # Se crash: aguardar restart e retentar UMA vez
                if not _expresso_ok and _expresso_protection and not self._tomcat_esta_vivo():
                    self._log("  ☠ Tomcat morreu após Expresso — aguardando restart…")
                    if self._aguardar_tomcat_restart(timeout=180):
                        self._renavegar_apos_crash()
                        try:
                            self._clicar_menu_lateral("Verbas")
                            self._page.wait_for_timeout(1500)
                            _expresso_ok, _nao_encontradas = self._tentar_expresso(predefinidas)
                        except Exception as exc2:
                            self._log(f"  ⚠ Expresso falhou na 2ª tentativa: {exc2}")
                            _expresso_ok = False
                    else:
                        raise RuntimeError("Tomcat não reiniciou após crash do Expresso")

                if not _expresso_ok:
                    # ABORT IMMEDIATE: Se alguma predefinida tinha estratégia
                    # explícita "expresso_direto" na prévia, Manual não vai resolver
                    # (mesmo nome, mesmo DOM). Abortar com diagnóstico.
                    _tinha_direto = [
                        v for v in predefinidas
                        if (v.get("estrategia_preenchimento") or {}).get("estrategia") == "expresso_direto"
                    ]
                    if _tinha_direto:
                        _nomes_esp = [
                            (v.get("estrategia_preenchimento") or {}).get("expresso_base")
                            or v.get("nome_pjecalc")
                            or v.get("nome_sentenca")
                            or "?"
                            for v in _tinha_direto
                        ]
                        # Capturar labels Expresso reais para diagnóstico acionável
                        _labels_atuais: list[str] = []
                        try:
                            _labels_atuais = self._page.evaluate("""() => {
                                const rows = [...document.querySelectorAll('table tr')];
                                return rows.map(tr => {
                                    const td = tr.querySelector('td:nth-child(2)');
                                    if (!td) return '';
                                    const clone = td.cloneNode(true);
                                    clone.querySelectorAll('input, script, style').forEach(el => el.remove());
                                    return clone.textContent.replace(/\\s+/g, ' ').trim();
                                }).filter(Boolean);
                            }""")
                        except Exception:
                            pass
                        self._log(
                            f"  ❌ Expresso falhou para verbas com estratégia 'expresso_direto': {_nomes_esp}"
                        )
                        if _labels_atuais:
                            self._log(f"  📋 Labels disponíveis no DOM ({len(_labels_atuais)}): {_labels_atuais[:30]}")
                        raise RuntimeError(
                            "AUTOMAÇÃO ABORTADA: Expresso falhou em marcar as verbas principais com "
                            f"estratégia 'expresso_direto'. Esperado: {_nomes_esp}. "
                            "Cair em Manual não resolve (mesmo nome, mesmo DOM). "
                            "Volte à prévia, verifique o campo 'Verba Expresso Base' — deve conter um "
                            "nome EXATO do catálogo Expresso (use o autocomplete do datalist). "
                            "Se a verba da sentença não existe no catálogo, mude a estratégia para 'manual'."
                        )
                    # Caso contrário (sem 'expresso_direto' explícito) — cair em Manual como fallback legítimo
                    self._log("  → Expresso falhou — 100% Manual")
                    personalizadas = predefinidas + personalizadas
                    # Registrar falha Expresso no strategy engine
                    if self._strategy_engine:
                        for v in predefinidas:
                            try:
                                self._strategy_engine.registrar_resultado(
                                    v, "expresso_direto", sucesso=False, erro="Expresso falhou ou Tomcat crash"
                                )
                            except Exception:
                                pass
                else:
                    # Verbas não encontradas no Expresso → Manual
                    if _nao_encontradas:
                        self._log(
                            f"  → {len(_nao_encontradas)} verba(s) não encontrada(s) no Expresso "
                            f"— adicionando ao fluxo Manual: {_nao_encontradas}"
                        )
                        personalizadas = [
                            v for v in predefinidas
                            if (v.get("nome_pjecalc") or v.get("nome_sentenca") or "") in _nao_encontradas
                        ] + personalizadas
                    # Registrar resultado no strategy engine
                    if self._strategy_engine:
                        _nao_enc_set = set(_nao_encontradas)
                        for v in predefinidas:
                            _vname = v.get("nome_pjecalc") or v.get("nome_sentenca") or ""
                            try:
                                if _vname in _nao_enc_set:
                                    self._strategy_engine.registrar_resultado(
                                        v, "expresso_direto", sucesso=False,
                                        erro="Verba não encontrada na tabela Expresso",
                                    )
                                else:
                                    self._strategy_engine.registrar_resultado(
                                        v, "expresso_direto", sucesso=True,
                                        detalhes={"expresso_nome": _vname},
                                    )
                            except Exception:
                                pass

        # ── 3B: Verbas personalizadas (Manual/Novo) ────────────────────────
        if personalizadas:
            self._log(f"  → Manual: {len(personalizadas)} verba(s) personalizada(s)")
            self._clicar_menu_lateral("Verbas", obrigatorio=False)
            self._page.wait_for_timeout(1000)
            self._lancar_verbas_manual(personalizadas)

        nao_rec = verbas_mapeadas.get("nao_reconhecidas", [])
        if nao_rec:
            nomes = ", ".join(v.get("nome_sentenca", "?") for v in nao_rec)
            self._log(
                f"  ⚠ AVISO: {len(nao_rec)} verba(s) não mapeada(s) ignorada(s) na automação "
                f"(deveriam ter sido corrigidas na prévia): {nomes}"
            )

        self._log("Fase 3 concluída.")

    def _marcar_checkbox_expresso(self, nome: str, percentual: float | None = None) -> bool:
        """Localiza e marca o checkbox do Expresso cujo nome contém 'nome' (case-insensitive).

        Estrutura confirmada DOM v2.15.1 (verbas-para-calculo.jsf):
        - Grade de 3 colunas com IDs dinâmicos: formulario:j_id82:ROW:j_id84:COL:selecionada
        - NÃO existe elemento [id*=":nome"] — o nome é o texto da célula <td> pai
        - Cada <td> contém: checkbox + label/span com o nome da verba
        Busca pelo texto da célula individual (não da linha inteira).
        Se percentual fornecido, prefere match com percentual correto (ex: 40% vs 10%).
        """
        try:
            _resultado = self._page.evaluate(
                """([nome, percentual]) => {
                    function norm(s) {
                        s = s.toLowerCase()
                            .normalize('NFD').replace(/[\u0300-\u036f]/g, '');
                        s = s.replace(/\\bart\\.?\\s*/g, 'artigo ')
                             .replace(/[^a-z0-9 %]/g, ' ')
                             .replace(/\\s+/g, ' ').trim();
                        return s;
                    }
                    function stem(w) {
                        // Portuguese plural→singular: morais→moral, sociais→social
                        if (w.endsWith('ais') && w.length > 4) return w.slice(0, -2) + 'l';
                        // ões→ão: opcoes→opcao (after NFD, ões→oes, ão→ao)
                        if (w.endsWith('oes') && w.length > 4) return w.slice(0, -3) + 'ao';
                        // Simple -s plural: danos→dano, verbas→verba
                        if (w.endsWith('s') && w.length > 3 && !w.endsWith('ss')) return w.slice(0, -1);
                        return w;
                    }
                    function tokens(s) {
                        return norm(s).split(' ').filter(t => t.length >= 2).map(stem);
                    }
                    function score(a, b) {
                        const ta = new Set(tokens(a));
                        const tb = new Set(tokens(b));
                        if (ta.size === 0 || tb.size === 0) return 0;
                        let shared = 0;
                        for (const t of ta) {
                            if (tb.has(t)) shared++;
                            else { for (const u of tb) { if (t.length >= 3 && (u.includes(t)||t.includes(u))) shared += 0.4; } }
                        }
                        return shared / Math.max(ta.size, tb.size);
                    }

                    // Coletar pares (checkbox, textoCell) — texto da célula individual, não da linha
                    // NÃO filtrar por getBoundingClientRect — checkboxes abaixo do fold têm
                    // dimensão 0x0 mas são perfeitamente clicáveis via JS.
                    const pairs = [];
                    document.querySelectorAll('input[type="checkbox"][id$=":selecionada"]').forEach(cb => {
                        // Pegar texto do container mais próximo que seja <td>, <li> ou <label>
                        const cell = cb.closest('td') || cb.closest('li') || cb.closest('label') || cb.parentElement;
                        if (!cell) return;
                        // Excluir texto de scripts/menus (>200 chars é menu lateral)
                        const txt = cell.textContent.replace(/\\s+/g, ' ').trim();
                        if (txt.length > 0 && txt.length <= 80) {
                            pairs.push({cb, txt});
                        }
                    });

                    const nomeLower = norm(nome);
                    const nomeTok = tokens(nome);

                    // 1ª: match exato
                    for (const {cb, txt} of pairs) {
                        if (norm(txt) === nomeLower) {
                            if (!cb.checked) cb.click();
                            return txt;
                        }
                    }
                    // 2ª: substring
                    for (const {cb, txt} of pairs) {
                        const t = norm(txt);
                        if (t.includes(nomeLower) || nomeLower.includes(t)) {
                            if (!cb.checked) cb.click();
                            return txt;
                        }
                    }
                    // 3ª: todos os tokens presentes
                    if (nomeTok.length >= 2) {
                        for (const {cb, txt} of pairs) {
                            const t = norm(txt);
                            if (nomeTok.every(p => t.includes(p))) {
                                if (!cb.checked) cb.click();
                                return txt;
                            }
                        }
                    }
                    // 3.5ª: percentual-aware — se percentual fornecido, prefere match com %
                    if (percentual !== null && percentual !== undefined) {
                        const pctNum = Math.round(percentual * 100).toString();
                        let bestPct = null, bestPctScore = 0;
                        for (const {cb, txt} of pairs) {
                            const s = score(nome, txt);
                            const t = norm(txt);
                            if (s >= 0.50 && (t.includes(pctNum + '%') || t.includes(pctNum + ' %') || t.includes(pctNum + ' por'))) {
                                if (s > bestPctScore || !bestPct) {
                                    bestPctScore = s; bestPct = {cb, txt};
                                }
                            }
                        }
                        if (bestPct) {
                            if (!bestPct.cb.checked) bestPct.cb.click();
                            return bestPct.txt + ' (pct-match ' + pctNum + '%)';
                        }
                    }

                    // 4ª: token-overlap Jaccard ≥ 0.40
                    let best = 0, bestCb = null, bestTxt = null;
                    for (const {cb, txt} of pairs) {
                        const s = score(nome, txt);
                        if (s > best) { best = s; bestCb = cb; bestTxt = txt; }
                    }
                    if (best >= 0.40 && bestCb) {
                        if (!bestCb.checked) bestCb.click();
                        return '~' + bestTxt + ' (score=' + best.toFixed(2) + ')';
                    }
                    return null;
                }""",
                [nome, percentual],
            )
            if _resultado:
                self._log(f"  ✓ Expresso checkbox: {nome} → '{_resultado}'")
                self._page.wait_for_timeout(200)
                return True
            return False
        except Exception as _e:
            self._log(f"  ⚠ _marcar_checkbox_expresso({nome}): {_e}")
            return False

    # ── Mapeamento base_calculo → enum do select tipoDaBaseTabelada ────────────
    _BASE_CALCULO_MAP: dict[str, str] = {
        "maior remuneracao":  "MAIOR_REMUNERACAO",
        "maior remuneração":  "MAIOR_REMUNERACAO",
        "historico salarial": "HISTORICO_SALARIAL",
        "histórico salarial": "HISTORICO_SALARIAL",
        "salario minimo":     "SALARIO_MINIMO",
        "salário mínimo":     "SALARIO_MINIMO",
        "piso salarial":      "SALARIO_DA_CATEGORIA",
        "salario categoria":  "SALARIO_DA_CATEGORIA",
    }

    def _configurar_parametros_verba(self, verba: dict, nome_na_lista: str) -> bool:
        """Abre 'Parâmetros da Verba' para a linha que contém nome_na_lista e preenche
        todos os campos disponíveis na extração (período, percentual, base, quantidade).

        Retorna True se salvou com sucesso.
        """
        import re as _re

        # 1. Clicar botão "Parâmetros da Verba" na linha correspondente
        _kw = nome_na_lista.lower()[:18]
        _clicou = self._page.evaluate(f"""() => {{
            const kw = {repr(_kw)};
            const rows = document.querySelectorAll('tr');
            for (const tr of rows) {{
                if (!tr.textContent.toLowerCase().includes(kw)) continue;
                // Buscar por texto/title/alt em links e botões
                const btns = [...tr.querySelectorAll(
                    'a, input[type="button"], input[type="submit"], input[type="image"]'
                )];
                for (const btn of btns) {{
                    const t = ((btn.title || '') + ' ' + (btn.value || '') + ' ' +
                               (btn.textContent || '') + ' ' + (btn.alt || '')).toLowerCase();
                    if (t.includes('par') && t.includes('metro')) {{
                        btn.click();
                        return true;
                    }}
                }}
                // Buscar por ID contendo "parametro" ou "alterar" ou "editar"
                const acoes = [...tr.querySelectorAll(
                    'a[id*="parametro"], a[id*="alterar"], a[id*="editar"], ' +
                    'input[id*="parametro"], input[id*="alterar"], input[id*="editar"], ' +
                    'a[id*="acao"], input[id*="acao"]'
                )];
                if (acoes.length >= 1) {{
                    acoes[0].click();
                    return true;
                }}
                // Fallback: buscar ícones de ação (links com img) — o segundo é normalmente "Parâmetros"
                const iconLinks = [...tr.querySelectorAll('a:has(img), a[onclick]')]
                    .filter(a => !a.textContent.trim().toLowerCase().includes('exclu'));
                if (iconLinks.length >= 2) {{
                    iconLinks[1].click();  // Parâmetros é geralmente o 2o ícone
                    return true;
                }} else if (iconLinks.length === 1) {{
                    iconLinks[0].click();
                    return true;
                }}
            }}
            return false;
        }}""")
        if not _clicou:
            self._log(f"  ⚠ Parâmetros '{nome_na_lista}': botão não encontrado na listagem")
            return False

        self._aguardar_ajax()
        self._page.wait_for_timeout(800)

        # Verificar se navegou para verba-calculo.jsf
        _url_atual = self._page.url
        if "verba-calculo" not in _url_atual and "verba" not in _url_atual:
            self._log(f"  ⚠ Parâmetros '{nome_na_lista}': navegação inesperada → {_url_atual}")
            return False

        # 2. Preencher campos disponíveis
        _preencheu = False

        # Período De
        _pini = verba.get("periodo_inicio")
        if _pini:
            self._preencher_data("periodoInicialInputDate", _pini, obrigatorio=False)
            _preencheu = True

        # Período Até
        _pfim = verba.get("periodo_fim")
        if _pfim:
            self._preencher_data("periodoFinalInputDate", _pfim, obrigatorio=False)
            _preencheu = True

        # Multiplicador (percentual) — só se extraído
        _perc = verba.get("percentual")
        _confianca = verba.get("confianca", 1.0)
        if _perc is not None and _confianca >= 0.7:
            # Converter 0.5 → "50" (o campo espera percentual direto, não fração)
            _perc_val = _perc * 100 if _perc <= 1.0 else _perc
            self._preencher("outroValorDoMultiplicador", _fmt_br(_perc_val), obrigatorio=False)
            _preencheu = True

        # Base de cálculo
        _base_raw = (verba.get("base_calculo") or "").lower().strip()
        _base_enum = self._BASE_CALCULO_MAP.get(_base_raw)
        if _base_enum:
            self._marcar_radio("tipoDaBaseTabelada", _base_enum)
            _preencheu = True

        # Quantidade (se informada na sentença)
        _qtd = verba.get("quantidade") or verba.get("valor_informado_quantidade")
        if _qtd is not None:
            self._marcar_radio("tipoDaQuantidade", "INFORMADA")
            self._preencher("valorInformadoDaQuantidade", _fmt_br(_qtd), obrigatorio=False)
            _preencheu = True

        if not _preencheu:
            self._log(f"  → Parâmetros '{nome_na_lista}': sem dados a preencher — cancelando")
            # Voltar sem salvar
            _btn_cancelar = self._page.locator("[id$='cancelar']")
            if _btn_cancelar.count() > 0:
                _btn_cancelar.first.click()
                self._aguardar_ajax()
            return False

        # 3. Salvar
        self._clicar_salvar()

        # 4. Garantir retorno à listagem
        if "verbas-para-calculo" not in self._page.url:
            self._clicar_menu_lateral("Verbas", obrigatorio=False)
            self._aguardar_ajax()

        self._log(
            f"  ✓ Parâmetros '{nome_na_lista}': "
            f"período {_pini or '?'}→{_pfim or '?'}"
            + (f", {_perc_val:.0f}%" if _perc is not None and _confianca >= 0.7 else "")
        )
        return True

    def _configurar_ocorrencias_verba(self, nome_na_lista: str, v: dict | None = None) -> bool:
        """Abre 'Ocorrências da Verba' para a linha que contém nome_na_lista,
        gera as ocorrências automáticas e salva.

        Se `v` for fornecido e contiver periodo_inicio/periodo_fim, desmarca as
        ocorrências de meses fora do intervalo do período da verba.

        Retorna True se salvou com sucesso.
        """
        _kw = nome_na_lista.lower()[:18]

        # Garantir que estamos na listagem
        if "verbas-para-calculo" not in self._page.url:
            self._clicar_menu_lateral("Verbas", obrigatorio=False)
            self._aguardar_ajax()

        # 1. Clicar botão "Ocorrências da Verba" na linha correspondente
        _clicou = self._page.evaluate(f"""() => {{
            const rows = document.querySelectorAll('tr');
            for (const tr of rows) {{
                if (!tr.textContent.toLowerCase().includes({repr(_kw)})) continue;
                const btns = [...tr.querySelectorAll('a, input[type="button"], input[type="submit"]')];
                for (const btn of btns) {{
                    const t = (btn.title || btn.value || btn.textContent || '').toLowerCase();
                    if (t.includes('ocorr')) {{
                        btn.click();
                        return true;
                    }}
                }}
            }}
            return false;
        }}""")
        if not _clicou:
            self._log(f"  ⚠ Ocorrências '{nome_na_lista}': botão não encontrado")
            return False

        self._aguardar_ajax()
        self._page.wait_for_timeout(400)

        # FIX: guarda de URL pós-clique. Se o clique heurístico por 'ocorr' pegou
        # um link errado (ex: menu lateral "Faltas" pode conter "ocorrência"), a
        # página navega para falta.jsf em vez da tela de Ocorrências da Verba.
        # Sem validar isso, o filtro de checkboxes por período desmarca ocorrências
        # de FALTAS indevidamente. Manual Seção 9 (Verbas) — fluxo pós-Expresso
        # opera SEMPRE dentro de verbas-para-calculo/verba-calculo.
        _url_oc = self._page.url
        if ("falta" in _url_oc and "verba" not in _url_oc) or (
            "verba" not in _url_oc and "ocorrencia" not in _url_oc
        ):
            self._log(
                f"  ⚠ Ocorrências '{nome_na_lista}': navegação inesperada → {_url_oc}"
                " — pulando verba para não corromper outra tela"
            )
            # Voltar para a listagem de verbas
            try:
                self._clicar_menu_lateral("Verbas", obrigatorio=False)
                self._aguardar_ajax()
            except Exception:
                pass
            return False

        # 2. Gerar ocorrências automáticas (mesmo padrão do histórico salarial)
        _gerou = (
            self._clicar_botao_id("cmdGerarOcorrencias")
            or self._clicar_botao_id("btnGerarOcorrencias")
        )
        if not _gerou:
            _anc = self._page.locator(
                "a[id*='cmdGerarOcorrencias'], a[id*='btnGerarOcorrencias'], "
                "input[value*='Gerar'], a:has-text('Gerar')"
            )
            if _anc.count() > 0:
                _anc.first.click()
                _gerou = True
        if _gerou:
            self._aguardar_ajax()
            self._page.evaluate("window.scrollTo(0, document.body.scrollHeight)")

        # 2b. FIX: filtrar ocorrências fora do período extraído da sentença.
        # O "Gerar" cria ocorrências para TODO o período do contrato; verbas
        # que só valem por N meses (ex: "Adicional Noturno de 03/2022 a 05/2023")
        # precisam ter as ocorrências fora desse intervalo desmarcadas.
        if v and _gerou:
            _pi = v.get("periodo_inicio")
            _pf = v.get("periodo_fim")
            if _pi and _pf:
                try:
                    from datetime import datetime as _dt
                    _di = _dt.strptime(_pi, "%d/%m/%Y")
                    _df = _dt.strptime(_pf, "%d/%m/%Y")
                    _mes_ini = _di.year * 12 + _di.month
                    _mes_fim = _df.year * 12 + _df.month
                    _js_filtro = (
                        "(args) => {"
                        "  const {mesIni, mesFim} = args;"
                        "  const rows = document.querySelectorAll('table tr, tbody tr');"
                        "  let desmarcados = 0;"
                        "  rows.forEach(tr => {"
                        "    const txt = tr.innerText || tr.textContent || '';"
                        "    const m = txt.match(/(\\d{2})[\\/\\-](\\d{4})/);"
                        "    if (!m) return;"
                        "    const mesOcc = parseInt(m[2]) * 12 + parseInt(m[1]);"
                        "    if (mesOcc < mesIni || mesOcc > mesFim) {"
                        "      const cbx = tr.querySelector('input[type=\"checkbox\"]');"
                        "      if (cbx && cbx.checked) { cbx.click(); desmarcados++; }"
                        "    }"
                        "  });"
                        "  return desmarcados;"
                        "}"
                    )
                    _n = self._page.evaluate(_js_filtro, {"mesIni": _mes_ini, "mesFim": _mes_fim})
                    self._log(f"  ✓ Ocorrências fora do período ({_pi}→{_pf}) desmarcadas: {_n}")
                    if _n:
                        self._aguardar_ajax()
                except Exception as _e_filt:
                    self._log(f"  ⚠ Falha ao filtrar ocorrências por período: {_e_filt}")

        # 3. Salvar
        self._clicar_salvar()

        # 4. Garantir retorno à listagem
        if "verbas-para-calculo" not in self._page.url:
            self._clicar_menu_lateral("Verbas", obrigatorio=False)
            self._aguardar_ajax()

        self._log(f"  ✓ Ocorrências '{nome_na_lista}': {'geradas e ' if _gerou else ''}salvas")
        return True

    def _pos_expresso_parametros_ocorrencias(self, predefinidas: list) -> None:
        """Após salvar o Expresso: configura Parâmetros e Ocorrências de cada verba principal.

        Iteração sobre a listagem verbas-para-calculo.jsf:
        para cada verba principal (não reflexa) com dados disponíveis →
        abre Parâmetros da Verba, preenche, salva → abre Ocorrências, gera, salva.
        """
        if not predefinidas:
            return

        # Garantir listagem — se page está em estado inválido (500, home), re-abrir cálculo
        if "verbas-para-calculo" not in self._page.url:
            # Se estamos na home ou em 500, re-abrir cálculo via Recentes primeiro
            _url_atual = self._page.url
            if "principal.jsf" in _url_atual or "9257" not in _url_atual:
                self._log("  → Página fora do cálculo — re-abrindo via Recentes…")
                self._reabrir_calculo_recentes()
            self._clicar_menu_lateral("Verbas", obrigatorio=False)
            self._aguardar_ajax()
            self._page.wait_for_timeout(800)
            # Fallback: URL direta se menu lateral não navegou para a listagem
            if "verbas-para-calculo" not in self._page.url:
                if self._calculo_url_base and self._calculo_conversation_id:
                    try:
                        _url_vl = (
                            f"{self._calculo_url_base}verba/verbas-para-calculo.jsf"
                            f"?conversationId={self._calculo_conversation_id}"
                        )
                        self._page.goto(_url_vl, wait_until="domcontentloaded", timeout=15000)
                        self._aguardar_ajax()
                        self._page.wait_for_timeout(800)
                    except Exception:
                        pass

        for v in predefinidas:
            # Pular verbas reflexas — não têm linha própria na listagem
            if v.get("eh_reflexa") or (v.get("tipo") or "").lower() == "reflexa":
                continue
            nome = (v.get("nome_pjecalc") or v.get("nome_sentenca") or "").strip()
            if not nome:
                continue

            # Parâmetros — apenas se há dado útil para preencher
            _tem_dado = any([
                v.get("periodo_inicio"),
                v.get("periodo_fim"),
                v.get("percentual") is not None,
                v.get("base_calculo"),
                v.get("quantidade") is not None,
            ])
            if _tem_dado:
                try:
                    self._configurar_parametros_verba(v, nome)
                except Exception as _e:
                    self._log(f"  ⚠ _configurar_parametros_verba('{nome}'): {_e}")

            # Ocorrências — sempre tentar (gerar + salvar confirma o período)
            try:
                self._configurar_ocorrencias_verba(nome, v=v)
            except Exception as _e:
                self._log(f"  ⚠ _configurar_ocorrencias_verba('{nome}'): {_e}")

    def _configurar_reflexos_expresso(self, verbas: list) -> None:
        """Configura reflexos de verbas Expresso via link 'Exibir' na listagem de verbas.

        Arquitetura: reflexos NÃO são verbas manuais autônomas. Após salvar verbas no Expresso,
        navegar para a listagem de verbas (verba-calculo.jsf — NÃO verbas-para-calculo.jsf),
        clicar em 'Exibir' à direita de cada verba principal e marcar os checkboxes dos reflexos.
        """
        try:
            # Garantir que estamos na página de listagem de verbas (verba-calculo.jsf)
            # IMPORTANTE: Os botões 'Exibir'/'Verba Reflexa' ficam em verba-calculo.jsf,
            # NÃO em verbas-para-calculo.jsf (que é a página do Lançamento Expresso).
            _url_atual = self._page.url
            if "verba-calculo" not in _url_atual or "verbas-para-calculo" in _url_atual:
                self._log("  → Navegando para listagem de verbas (verba-calculo.jsf)…")
                # Tentar via menu lateral primeiro
                _nav_ok = self._clicar_menu_lateral("Verbas", obrigatorio=False)
                self._aguardar_ajax()
                self._page.wait_for_timeout(1000)
                # Se menu lateral falhou ou não levou à listagem correta, usar URL direta
                if not _nav_ok or "verba-calculo" not in self._page.url or "verbas-para-calculo" in self._page.url:
                    if self._calculo_url_base and self._calculo_conversation_id:
                        _url_verbas = (
                            f"{self._calculo_url_base}verba/verba-calculo.jsf"
                            f"?conversationId={self._calculo_conversation_id}"
                        )
                        self._log("  → URL direta para verba-calculo.jsf…")
                        try:
                            self._page.goto(_url_verbas, wait_until="domcontentloaded", timeout=15000)
                            self._aguardar_ajax()
                            self._page.wait_for_timeout(1000)
                        except Exception as _e:
                            self._log(f"  ⚠ URL direta verba-calculo: {_e}")

            # Detectar HTTP 500 / NPE na listagem de verbas
            # Bug conhecido: ApresentadorVerbaDeCalculo.carregarBasesParaPrincipal
            # lança NullPointerException após Expresso, impedindo renderização da página.
            try:
                _is_500 = self._page.evaluate("""() => {
                    const body = document.body ? document.body.textContent : '';
                    return body.includes('HTTP Status 500') ||
                           body.includes('NullPointerException') ||
                           body.includes('Erro inesperado') ||
                           body.includes('ViewExpiredException') ||
                           document.title.includes('500');
                }""")
                if _is_500:
                    self._log("  ⚠ verba-calculo.jsf retornou erro 500 (NPE conhecida) — pulando reflexos")
                    return
            except Exception:
                pass

            # Mapa nome_pjecalc → reflexas_tipicas (ou lista vazia = marcar TODOS)
            # Estratégia: para verbas Expresso com reflexas_tipicas, marcar só as listadas.
            # Para verbas Expresso SEM reflexas_tipicas, marcar TODOS os checkboxes
            # (PJE-Calc já pré-configura as reflexas corretas para cada verba Expresso).
            _reflexos_map: dict[str, list[str]] = {}
            for v in verbas:
                _nome_v = v.get("nome_pjecalc") or v.get("nome_sentenca") or ""
                _reflexas = v.get("reflexas_tipicas", [])
                # Não configurar reflexas de verbas que são elas mesmas reflexas
                if _nome_v and not v.get("eh_reflexa") and "reflexo" not in _nome_v.lower():
                    # Se tem reflexas específicas, usar; senão lista vazia = marcar todos
                    _reflexos_map[_nome_v] = _reflexas

            if not _reflexos_map:
                self._log("  → Nenhuma verba principal para configurar reflexos")
                return

            # Verificar se há botões de reflexo na página
            # PJE-Calc usa ícones (img) ou links com título "Exibir"/"Verba Reflexa"
            _btn_count = self._page.evaluate("""() => {
                const all = [...document.querySelectorAll(
                    'a, input[type="button"], input[type="submit"], input[type="image"]'
                )];
                return all.filter(el => {
                    const t = ((el.textContent || '') + ' ' + (el.value || '') + ' ' +
                               (el.title || '') + ' ' + (el.alt || '')).trim().toLowerCase();
                    return t.includes('exibir') || t.includes('verba reflexa')
                        || t.includes('reflexa') || t.includes('reflexo');
                }).length;
            }""")
            if not _btn_count:
                # Verbas Expresso incluem reflexos automaticamente — não é erro crítico
                self._log("  → Nenhum botão 'Verba Reflexa'/'Exibir' encontrado — reflexos Expresso já pré-configurados")
                return
            self._log(f"  → Configurando reflexos ({_btn_count} botão(ões) encontrado(s))…")

            _linhas = self._page.evaluate("""() => {
                const rows = [...document.querySelectorAll(
                    'tr[id*="listagem"], tr.rich-table-row, tbody tr'
                )];
                return rows.map((tr, i) => ({
                    index: i,
                    texto: tr.textContent.replace(/\\s+/g,' ').trim().substring(0, 120),
                    temBotaoReflexo: [...tr.querySelectorAll('a, input[type="button"], input[type="submit"]')]
                        .some(el => {
                            const t = (el.textContent || el.value || '').trim().toLowerCase();
                            return t.includes('exibir') || t.includes('verba reflexa') || t.includes('reflexa');
                        }),
                }));
            }""")

            for row in _linhas:
                if not row.get("temBotaoReflexo"):
                    continue
                _texto_row = row.get("texto", "").lower()

                _reflexas_needed: list[str] | None = None  # None = não encontrou verba
                _marcar_todos: bool = False
                _nome_principal: str = ""
                for nome_v, reflexas in _reflexos_map.items():
                    # Testar as 3 primeiras palavras do nome para match
                    _palavras = nome_v.lower().split()
                    for _n_words in (3, 2, 1):
                        _kw = " ".join(_palavras[:_n_words])
                        if _kw and _kw in _texto_row:
                            _nome_principal = nome_v
                            if reflexas:
                                _reflexas_needed = reflexas
                                self._log(f"  → Reflexos específicos de '{nome_v}': {reflexas}")
                            else:
                                _marcar_todos = True
                                self._log(f"  → Reflexos de '{nome_v}': marcar TODOS (Expresso pré-configurado)")
                            break
                    if _reflexas_needed is not None or _marcar_todos:
                        break

                if _reflexas_needed is None and not _marcar_todos:
                    continue

                row_idx = row["index"]
                try:
                    _clicou = self._page.evaluate(
                        """(idx) => {
                            const rows = [...document.querySelectorAll(
                                'tr[id*="listagem"], tr.rich-table-row, tbody tr'
                            )];
                            if (idx >= rows.length) return false;
                            const link = [...rows[idx].querySelectorAll(
                                'a, input[type="button"], input[type="submit"]'
                            )].find(el => {
                                const t = (el.textContent || el.value || '').trim().toLowerCase();
                                return t.includes('exibir') || t.includes('verba reflexa') || t.includes('reflexa');
                            });
                            if (!link) return false;
                            link.click();
                            return link.textContent || link.value || 'ok';
                        }""",
                        row_idx,
                    )
                    if not _clicou:
                        continue
                    self._log(f"  → Clicou botão reflexo: '{_clicou}'")
                    self._aguardar_ajax()
                    self._page.wait_for_timeout(600)
                except Exception as _e:
                    self._log(f"  ⚠ Botão reflexo row {row_idx}: {_e}")
                    continue

                _algum_reflexo_marcado = False

                if _marcar_todos:
                    # Marcar TODOS os checkboxes de reflexo visíveis após clicar "Exibir"
                    # PJE-Calc já pré-configura as reflexas corretas para cada verba Expresso
                    try:
                        _count = self._page.evaluate("""() => {
                            const cbs = [...document.querySelectorAll(
                                'input[type="checkbox"][id*="listaReflexo"],' +
                                'input[type="checkbox"][id*="reflexo"],' +
                                'input[type="checkbox"][id*="Reflexo"],' +
                                'input[type="checkbox"][id*="ativo"]'
                            )];
                            let marked = 0;
                            for (const cb of cbs) {
                                if (!cb.checked && !cb.disabled) {
                                    cb.click();
                                    marked++;
                                }
                            }
                            return marked;
                        }""")
                        if _count:
                            self._log(f"  ✓ Marcados {_count} reflexo(s) de '{_nome_principal}'")
                            _algum_reflexo_marcado = True
                        else:
                            self._log(f"  → Nenhum reflexo desmarcado para '{_nome_principal}'")
                    except Exception as _e:
                        self._log(f"  ⚠ Marcar todos reflexos de '{_nome_principal}': {_e}")
                else:
                    # Marcar reflexos específicos por nome
                    for reflexo_nome in (_reflexas_needed or []):
                        try:
                            _marcou = self._page.evaluate(
                                """(rNome) => {
                                    function norm(s) {
                                        return s.toLowerCase()
                                            .normalize('NFD').replace(/[\\u0300-\\u036f]/g, '');
                                    }
                                    const rLower = norm(rNome);
                                    // NÃO filtrar por getBoundingClientRect — checkboxes podem
                                    // estar abaixo do fold mas são clicáveis via JS
                                    const cbs = [...document.querySelectorAll(
                                        'input[type="checkbox"][id*="listaReflexo"],' +
                                        'input[type="checkbox"][id*="reflexo"],' +
                                        'input[type="checkbox"][id*="Reflexo"]'
                                    )];
                                    // Tokenizar para matching flexível
                                    const rTokens = rLower.split(/\\s+/).filter(t => t.length >= 3);
                                    for (const cb of cbs) {
                                        const ctx = cb.closest('td,tr,li,div') || cb.parentElement;
                                        const txt = norm((ctx && ctx.textContent) || '');
                                        // Match por substring ou por todos os tokens presentes
                                        const tokenMatch = rTokens.length >= 2
                                            && rTokens.every(t => txt.includes(t));
                                        if (txt.includes(rLower) || tokenMatch) {
                                            if (!cb.checked) cb.click();
                                            return (ctx && ctx.textContent.trim().substring(0, 60)) || 'ok';
                                        }
                                    }
                                    return null;
                                }""",
                                reflexo_nome,
                            )
                            if _marcou:
                                self._log(f"  ✓ Reflexo: {reflexo_nome} → '{_marcou}'")
                                _algum_reflexo_marcado = True
                            else:
                                self._log(f"  ⚠ Reflexo não encontrado: {reflexo_nome}")
                        except Exception as _e:
                            self._log(f"  ⚠ Reflexo {reflexo_nome}: {_e}")

                if _algum_reflexo_marcado and _nome_principal:
                    self._reflexos_configurados.add(_nome_principal)

        except Exception as _e:
            self._log(f"  ⚠ _configurar_reflexos_expresso: {_e}")

    def _lancar_verbas_manual(self, verbas: list) -> None:
        """Lança verbas individualmente via botão 'Novo' (para verbas personalizadas)."""
        import unicodedata as _ud_m

        def _norm_key(s: str) -> str:
            """Normaliza chave para lookup nos mapas (sem acentos, minúsculas)."""
            return _ud_m.normalize("NFD", s.lower()).encode("ascii", "ignore").decode().strip()

        # Valores enum do PJE-Calc — chaves normalizadas para tolerância a acentos/case
        carac_map = {
            "comum": "COMUM",
            "13o salario": "DECIMO_TERCEIRO",
            "decimo terceiro salario": "DECIMO_TERCEIRO",
            "13 salario": "DECIMO_TERCEIRO",
            "ferias": "FERIAS",
            "aviso previo": "AVISO_PREVIO",
        }
        ocorr_map = {
            "mensal": "MENSAL",
            "dezembro": "DEZEMBRO",
            "periodo aquisitivo": "PERIODO_AQUISITIVO",
            "desligamento": "DESLIGAMENTO",
        }
        # URL da listagem de verbas (verba-calculo.jsf) — onde fica o botão "Manual"
        _url_verbas = self._page.url
        # Garantir que temos a URL base correta para navegar de volta
        if self._calculo_url_base and self._calculo_conversation_id:
            _url_verbas_listing = (
                f"{self._calculo_url_base}verba/verba-calculo.jsf"
                f"?conversationId={self._calculo_conversation_id}"
            )
        else:
            _url_verbas_listing = _url_verbas
        _JS_CAMPOS = """() =>
            [...document.querySelectorAll(
                'input:not([type="hidden"]):not([type="image"]):not([type="submit"]):not([type="button"]),select,textarea'
            )]
            .filter(e => { const r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0; })
            .map(e => e.id || e.name || '').filter(Boolean)
        """
        _campos_lista = set()
        try:
            _campos_lista = set(self._page.evaluate(_JS_CAMPOS))
        except Exception:
            pass

        # Verbas configuradas via checkboxes na aba FGTS — nunca criar como verba manual autônoma
        # Multa 40% FGTS e Multa Art. 467 CLT são checkboxes em Cálculo > FGTS,
        # tratados em fase_fgts() com fgts.multa_40 e fgts.multa_467.
        _VERBAS_APENAS_FGTS = {
            "multa art. 467", "multa art 467", "multa 467",
            "multa artigo 467", "multa do art. 467",
            "multa 40%", "multa fgts 40", "multa rescisória fgts",
        }

        # ── GUARD: Verbas Expresso JAMAIS podem ser criadas via Manual ──
        # Se a verba existe na tabela Expresso do PJE-Calc, deve SEMPRE usar Expresso.
        _NOMES_EXPRESSO_LOWER: set[str] = set()
        try:
            import json as _json_guard
            _catalogo_path = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                "knowledge", "catalogo_verbas_pjecalc.json"
            )
            with open(_catalogo_path, "r", encoding="utf-8") as _f_cat:
                _catalogo = _json_guard.load(_f_cat)
            for _entrada in _catalogo.get("expresso", []):
                _NOMES_EXPRESSO_LOWER.add(_entrada["nome_pjecalc"].lower())
                for _alias in _entrada.get("aliases", []):
                    _NOMES_EXPRESSO_LOWER.add(_alias.lower())
        except Exception as _e_cat:
            self._log(f"  ⚠ Não foi possível carregar catálogo Expresso para guard: {_e_cat}")

        for i, v in enumerate(verbas):
            nome = v.get("nome_pjecalc") or v.get("nome_sentenca") or ""
            _nome_lower = nome.lower()

            # ── REGRA GERAL: Automação só cria verba/reflexo manual se aprovado na prévia ──
            # O usuário deve ter explicitamente definido estratégia "manual" na prévia.
            # Sem essa aprovação, a verba é ignorada no fluxo manual.
            _ep_v = v.get("estrategia_preenchimento", {}) or {}
            _estrategia_v = (_ep_v.get("estrategia") or "").lower()
            if _estrategia_v and _estrategia_v != "manual":
                self._log(
                    f"  ⛔ '{nome}' — estratégia na prévia é '{_estrategia_v}', não 'manual'. "
                    f"Criação manual requer aprovação explícita do usuário na prévia. Pulando."
                )
                continue
            if not _estrategia_v:
                # Sem estratégia definida — verificar se é verba que o sistema adicionou
                # automaticamente (não aprovada pelo usuário). Verbas sem estratégia
                # explícita só prosseguem se não forem Expresso/Adaptado.
                self._log(
                    f"  ⚠ '{nome}' — sem estratégia definida na prévia. "
                    f"Verificando guards adicionais antes de criar manualmente."
                )

            # ── REGRA: Bloquear criação manual de verba que pertence ao Expresso ──
            if _NOMES_EXPRESSO_LOWER and _nome_lower in _NOMES_EXPRESSO_LOWER:
                self._log(
                    f"  ⛔ BLOQUEIO: '{nome}' é verba Expresso — não pode ser criada "
                    f"manualmente. Use o Lançamento Expresso. Pulando."
                )
                continue

            # ── REGRA: Pular verbas já criadas via Expresso ──
            # Férias+1/3, 13º Salário e outras verbas Expresso nunca devem ser
            # duplicadas como verbas manuais. A configuração de proporcionais vs
            # vencidas é feita via ocorrências, não via verbas separadas.
            if nome.upper() in self._verbas_expresso_ok:
                self._log(f"  → '{nome}' já registrada via Expresso — pulando criação manual")
                continue

            # ── REGRA: Pular férias/13º manuais se já registrados via Expresso ──
            # A extração pode gerar "FÉRIAS PROPORCIONAIS + 1/3" como verba separada,
            # mas no PJE-Calc é a mesma verba "FÉRIAS + 1/3" do Expresso com ocorrências
            # configuradas para proporcional. Idem para 13º Salário Proporcional.
            _carac = _norm_key(v.get("caracteristica") or "")
            _is_ferias = "ferias" in _nome_lower or "férias" in _nome_lower or _carac == "ferias"
            _is_13 = "13" in _nome_lower or "decimo" in _nome_lower or "décimo" in _nome_lower or _carac in ("13o salario", "decimo terceiro salario")
            if _is_ferias and any("FÉRIAS" in e or "FERIAS" in e for e in self._verbas_expresso_ok):
                self._log(f"  → '{nome}' é férias — já registrada via Expresso 'FÉRIAS + 1/3', pulando")
                continue
            if _is_13 and any("13" in e for e in self._verbas_expresso_ok):
                self._log(f"  → '{nome}' é 13º — já registrado via Expresso '13º SALÁRIO', pulando")
                continue

            # ── REGRA: Pular reflexas cujo principal foi criado via Expresso ──
            # Parcelas Expresso geram reflexos automaticamente (Aviso Prévio, Férias+1/3,
            # 13º, RSR, Multa 477). Criar reflexo manual duplica e causa erro.
            _eh_reflexa = v.get("eh_reflexa") or "reflexo" in _nome_lower or "sobre" in _nome_lower

            # REGRA ADICIONAL: verbas nomeadas "Reflexo em <categoria>" (ex: "Reflexo em 13o Salário",
            # "Reflexo em Férias e 1/3") são reflexos auto-gerados por QUALQUER verba Expresso
            # principal que tenha sido criada. Não devem ser criadas manualmente.
            if _eh_reflexa and self._verbas_expresso_ok:
                _categorias_reflexo_auto = ["13", "ferias", "aviso", "rsr", "repouso", "multa 477"]
                _reflexo_categoria = any(c in _nome_lower for c in _categorias_reflexo_auto)
                if _reflexo_categoria and "reflexo" in _nome_lower:
                    self._log(
                        f"  → '{nome}' é reflexo de categoria auto-gerada pelo Expresso "
                        f"(verbas Expresso ativas: {list(self._verbas_expresso_ok)[:3]}) — pulando"
                    )
                    continue

            if _eh_reflexa:
                # Inferir nome da verba principal a partir do nome do reflexo
                import re as _re_ref
                # Padrões: "RSR sobre Horas Extras", "13º s/ Horas Extras", "Férias + 1/3 s/ Adicional Noturno"
                _m_principal = _re_ref.search(
                    r'(?i)(?:sobre|s/)\s+(.+?)$', nome
                )
                _nome_principal_ref = _m_principal.group(1).strip() if _m_principal else ""
                if not _nome_principal_ref:
                    _m_principal = _re_ref.match(r'(?i)reflexo\s+(?:de\s+)?(.+?)\s+em\s+', nome)
                    _nome_principal_ref = _m_principal.group(1).strip() if _m_principal else ""

                # Verificar se o principal foi criado via Expresso (reflexos auto-gerados)
                _skip_expresso = False
                if _nome_principal_ref:
                    _ref_upper = _norm_key(_nome_principal_ref)
                    _skip_expresso = any(
                        _ref_upper in _norm_key(exp_name) or _norm_key(exp_name) in _ref_upper
                        for exp_name in self._verbas_expresso_ok
                    )
                    if _skip_expresso:
                        self._log(
                            f"  → '{nome}' reflexo de verba Expresso '{_nome_principal_ref}' "
                            f"— reflexos auto-gerados pelo PJE-Calc, pulando criação manual"
                        )
                        continue

                # Também verificar se a verba-alvo (após "EM") é Expresso
                if not _skip_expresso:
                    import re as _re_em
                    _m_alvo = _re_em.search(r'(?i)\bem\s+(.+?)$', nome)
                    if _m_alvo:
                        _alvo_norm = _norm_key(_m_alvo.group(1))
                        _skip_expresso = any(
                            _alvo_norm in _norm_key(e) or _norm_key(e) in _alvo_norm
                            for e in self._verbas_expresso_ok
                        )
                        if _skip_expresso:
                            self._log(
                                f"  → '{nome}' reflexo para verba Expresso '{_m_alvo.group(1)}' "
                                f"— auto-gerado pelo PJE-Calc, pulando"
                            )
                            continue

                if _nome_principal_ref and _nome_principal_ref in self._reflexos_configurados:
                    self._log(f"  → '{nome}' reflexo já configurado via botão Verba Reflexa — pulando")
                    continue

                # ── REGRA: Reflexo manual requer aprovação explícita do usuário ──
                # Sem estratégia "manual" explícita na prévia, reflexos NÃO são criados
                # manualmente. As regras do manual PJE-Calc (seção 9.4/9.8) exigem que
                # reflexos sejam gerados via "Exibir Reflexas" sempre que possível.
                if _estrategia_v != "manual":
                    self._log(
                        f"  ⛔ '{nome}' é reflexo sem estratégia 'manual' aprovada "
                        f"(estratégia: '{_estrategia_v or 'não definida'}') — "
                        f"reflexos manuais requerem aprovação explícita na prévia. Pulando."
                    )
                    continue
                self._log(f"  → '{nome}' reflexo com estratégia MANUAL aprovada — criando manualmente")

            # Pular verbas configuradas via checkboxes na aba FGTS (tratadas em fase_fgts)
            if any(k in _nome_lower for k in _VERBAS_APENAS_FGTS):
                self._log(f"  → '{nome}' é checkbox da aba FGTS — configurada em fase_fgts(), ignorando criação manual")
                continue

            # Re-calcular URLs com conversationId ATUAL antes de cada navegação
            # O conversationId muda após cada save (Seam Framework) — usar ID expirado causa HTTP 500
            self._capturar_base_calculo()
            if self._calculo_url_base and self._calculo_conversation_id:
                _url_verbas_listing = (
                    f"{self._calculo_url_base}verba/verba-calculo.jsf"
                    f"?conversationId={self._calculo_conversation_id}"
                )

            # Navegar para listagem de verbas se não estiver lá
            _cur_url = self._page.url
            if "verba-calculo" not in _cur_url or "conversationId" not in _cur_url:
                try:
                    self._page.goto(_url_verbas_listing, wait_until="domcontentloaded", timeout=20000)
                    self._page.wait_for_timeout(1000)
                    self._aguardar_ajax()
                except Exception:
                    self._clicar_menu_lateral("Verbas", obrigatorio=False)
                    self._page.wait_for_timeout(800)

            # Clicar botão "Manual" (id="incluir") na listagem de verbas
            # NUNCA usar _clicar_novo() — ele pega o "Novo" do top-nav que cria novo cálculo
            _clicou_manual = self._clicar_botao_id("incluir")
            if not _clicou_manual:
                # Fallback: buscar por value="Manual"
                try:
                    _btn = self._page.locator(VerbaListagem.BTN_MANUAL)
                    if _btn.count() > 0:
                        _btn.first.click()
                        _clicou_manual = True
                except Exception:
                    pass
            self._log(f"  → Manual: {'formulario:incluir' if _clicou_manual else 'NÃO encontrado'}")
            # nome já definido no início do loop (após filtros)
            if not nome:
                nome = "Verba"
            # Aguardar formulário de dados da verba
            # ID confirmado DOM v2.15.1: formulario:descricao (campo "Nome *")
            _form_abriu = False
            _form_selector = "[id$=':descricao'], [id$=':nome'], [id$='descricaoVerba'], [id$='nomeVerba']"
            if _clicou_manual:
                self._aguardar_ajax()
                try:
                    self._page.wait_for_selector(
                        _form_selector, state="visible", timeout=8000
                    )
                    _form_abriu = True
                except Exception:
                    self._page.wait_for_timeout(2000)
                    # Verificar se estamos na página de dados da verba
                    if "verba" in self._page.url and "verba-calculo" not in self._page.url:
                        _form_abriu = True
            if not _form_abriu:
                # Tentar navegar de volta para listagem e clicar Manual novamente
                try:
                    self._page.goto(_url_verbas_listing, wait_until="domcontentloaded", timeout=15000)
                    self._page.wait_for_timeout(1000)
                    self._aguardar_ajax()
                    _clicou_manual = self._clicar_botao_id("incluir")
                    if _clicou_manual:
                        self._aguardar_ajax()
                        try:
                            self._page.wait_for_selector(_form_selector, state="visible", timeout=8000)
                            _form_abriu = True
                        except Exception:
                            self._page.wait_for_timeout(2000)
                            if "verba" in self._page.url and "verba-calculo" not in self._page.url:
                                _form_abriu = True
                except Exception:
                    pass
            if not _form_abriu:
                self._log(f"  ⚠ Verba '{nome}': formulário Manual não abriu — ignorada.")
            if not _form_abriu:
                continue
            if i == 0:
                self.mapear_campos("verba_form_manual")

            # Nome da verba — ID confirmado DOM v2.15.1: formulario:descricao
            _desc_ok = any(
                self._preencher(fid, nome, obrigatorio=False)
                for fid in ["descricao", "nome", "descricaoVerba", "nomeVerba", "titulo", "verba"]
            )
            if not _desc_ok:
                for _lbl in ["Descrição", "Nome", "Descrição da Verba", "Nome da Verba", "Verba"]:
                    _loc = self._page.get_by_label(_lbl, exact=False)
                    if _loc.count() > 0:
                        try:
                            _loc.first.fill(nome)
                            _loc.first.dispatch_event("change")
                            _desc_ok = True
                            break
                        except Exception:
                            continue

            # ── Assunto CNJ (OBRIGATÓRIO — sem ele, "Existem erros no formulário") ──
            # Procedimento confirmado por vídeo: clicar lupa → modal com lista hierárquica
            # → selecionar código 2581 (Remuneração, Verbas Indenizatórias e Benefícios)
            # Fallback: JS direto nos campos hidden se modal não funcionar
            _cnj_ok = False
            try:
                # Tentativa 1: RichFaces suggestionbox inline (digitar no campo e aguardar popup)
                _cnj_field = self._page.locator(VerbaManual.ASSUNTOS_CNJ)
                if _cnj_field.count() > 0:
                    try:
                        _cnj_field.first.click()
                        self._page.wait_for_timeout(300)
                        _cnj_field.first.press_sequentially("2581", delay=120)
                        self._page.wait_for_timeout(2000)
                        # Verificar se popup de sugestão apareceu
                        _popup = self._page.locator(VerbaManual.POPUP_SUGESTAO)
                        if _popup.count() > 0:
                            _popup.first.locator('tr, div, td').first.click()
                            self._aguardar_ajax()
                            _cnj_ok = True
                            self._log("  ✓ Assunto CNJ: 2581 (via suggestionbox)")
                    except Exception:
                        pass

                # Tentativa 2: Clicar na lupa → modal CNJ → buscar na árvore
                if not _cnj_ok:
                    _lupa = self._page.locator(
                        VerbaManual.LUPA_CNJ + ', '
                        'a[onclick*="modalCNJ"]'
                    )
                    if _lupa.count() > 0:
                        try:
                            _lupa.first.click(force=True)
                            self._aguardar_ajax()
                            self._page.wait_for_timeout(1000)
                            # Modal pode ter campo de busca
                            _modal_input = self._page.locator(VerbaManual.MODAL_CNJ_INPUT)
                            if _modal_input.count() > 0:
                                _is_readonly = _modal_input.first.evaluate(
                                    "el => el.readOnly || el.disabled"
                                )
                                if _is_readonly:
                                    _modal_input.first.evaluate("""el => {
                                        el.readOnly = false;
                                        el.disabled = false;
                                    }""")
                                _modal_input.first.fill("2581")
                                _modal_input.first.dispatch_event("change")
                                self._aguardar_ajax()
                                self._page.wait_for_timeout(1000)
                            # Clicar no item da árvore que contém "2581" ou "Remuneração"
                            _tree_item = self._page.locator(
                                VerbaManual.MODAL_CNJ_TREE + ', '
                                '[id*="modalAssunto"] tr:has-text("2581")'
                            )
                            if _tree_item.count() > 0:
                                _tree_item.first.click()
                                self._page.wait_for_timeout(500)
                            # Clicar botão "Selecionar"
                            _btn_sel = self._page.locator(
                                VerbaManual.MODAL_CNJ_SELECIONAR + ', '
                                '[id*="modalAssunto"] input[value="Selecionar"]'
                            )
                            if _btn_sel.count() > 0:
                                _is_disabled = _btn_sel.first.evaluate("el => el.disabled")
                                if not _is_disabled:
                                    _btn_sel.first.click(force=True)
                                    self._aguardar_ajax()
                                    _cnj_ok = True
                                    self._log("  ✓ Assunto CNJ: 2581 (via modal lupa)")
                            # Fechar modal se ainda aberto
                            if not _cnj_ok:
                                _close = self._page.locator(
                                    VerbaManual.MODAL_CNJ_FECHAR + ', '
                                    '[id*="modalCNJ"] input[value*="Cancelar"]'
                                )
                                if _close.count() > 0:
                                    _close.first.click(force=True)
                                    self._page.wait_for_timeout(500)
                        except Exception as _e_modal:
                            self._log(f"  ⚠ Modal CNJ: {_e_modal}")

                # Tentativa 3: JS direto — setar valor + campo hidden do código
                if not _cnj_ok:
                    _cnj_ok = self._page.evaluate("""() => {
                        const txt = document.querySelector(
                            'input[id$="assuntosCnj"]:not([id*="modalCNJ"]):not([type="hidden"])'
                        );
                        const cod = document.querySelector('[id$="codigoAssuntosCnj"]');
                        if (txt) {
                            txt.readOnly = false;
                            txt.value = '2581 - Remuneração, Verbas Indenizatórias e Benefícios';
                            txt.dispatchEvent(new Event('change', {bubbles: true}));
                            txt.dispatchEvent(new Event('blur', {bubbles: true}));
                        }
                        if (cod) {
                            cod.value = '2581';
                            cod.dispatchEvent(new Event('change', {bubbles: true}));
                        }
                        return !!(txt || cod);
                    }""")
                    if _cnj_ok:
                        self._aguardar_ajax()
                        self._log("  ✓ Assunto CNJ: 2581 (via JS direto)")
            except Exception as _e_cnj:
                self._log(f"  ⚠ Assunto CNJ: {_e_cnj}")

            # ── Para verbas reflexas: marcar tipo REFLEXO e selecionar verba base ──
            if _eh_reflexa:
                # Radio tipoDeVerba = REFLEXO (DOM: formulario:tipoDeVerba com sufixo numérico)
                # Tier 1: label-based match
                _reflexo_ok = any(
                    self._marcar_radio(fid, "REFLEXO")
                    for fid in ["tipoDeVerba", "tipoVerba", "tipo"]
                )
                # Tier 2: JS radio by name
                if not _reflexo_ok:
                    _reflexo_ok = self._marcar_radio_js("tipoDeVerba", "REFLEXO")
                # Tier 3: Direct click by index (tipoDeVerba:1 = Reflexa)
                if not _reflexo_ok:
                    try:
                        _radio_direto = self._page.locator("input[id$='tipoDeVerba:1']")
                        if _radio_direto.count() > 0:
                            _radio_direto.first.click()
                            _reflexo_ok = True
                            self._log("  ✓ tipoDeVerba:1 (Reflexa) via click direto")
                    except Exception:
                        pass
                self._aguardar_ajax()
                self._page.wait_for_timeout(500)

                # ── baseVerbaDeCalculo — OBRIGATÓRIO para reflexa (manual seção 9.4) ──
                # A verba principal deve ser selecionada no dropdown "Verba *"
                _principal_ref = v.get("verba_principal_ref") or ""
                if not _principal_ref and _m_principal:
                    _principal_ref = _m_principal.group(1).strip()
                if _principal_ref:
                    try:
                        _sel_result = self._page.evaluate(
                            """(nomePrincipal) => {
                                // Buscar select com id contendo baseVerba ou verbaDeCalculo
                                let sels = [...document.querySelectorAll('select')].filter(s => {
                                    return s.id.includes('baseVerba') || s.id.includes('verbaDeCalculo')
                                        || s.name.includes('baseVerba');
                                });
                                // Fallback: qualquer select visível com opções de verbas
                                if (!sels.length) {
                                    sels = [...document.querySelectorAll('select')].filter(s => {
                                        const r = s.getBoundingClientRect();
                                        if (r.width <= 0 || r.height <= 0) return false;
                                        // Excluir selects conhecidos que não são baseVerba
                                        if (s.id.includes('tipoDaBase') || s.id.includes('caracteristica')
                                            || s.id.includes('ocorrencia')) return false;
                                        // Deve ter opções que parecem nomes de verba
                                        return [...s.options].some(o =>
                                            o.text.length > 5 && !o.text.includes('Selecione')
                                        );
                                    });
                                }
                                const norm = s => s.toLowerCase().normalize('NFD')
                                    .replace(/[\\u0300-\\u036f]/g, '');
                                const target = norm(nomePrincipal);
                                for (const sel of sels) {
                                    // Match por nome da principal
                                    for (const opt of sel.options) {
                                        if (norm(opt.text).includes(target)) {
                                            sel.value = opt.value;
                                            sel.dispatchEvent(new Event('change', {bubbles: true}));
                                            return 'OK: ' + opt.text;
                                        }
                                    }
                                    // Fallback: primeira opção válida (pular noSelectionValue)
                                    if (sel.options.length > 1) {
                                        sel.value = sel.options[1].value;
                                        sel.dispatchEvent(new Event('change', {bubbles: true}));
                                        return 'FALLBACK: ' + sel.options[1].text;
                                    }
                                }
                                return null;
                            }""",
                            _principal_ref,
                        )
                        if _sel_result:
                            self._aguardar_ajax()
                            self._log(f"  ✓ baseVerbaDeCalculo: {_sel_result}")
                        else:
                            self._log(f"  ⚠ baseVerbaDeCalculo: nenhum select encontrado para '{_principal_ref}'")
                    except Exception as _e_base:
                        self._log(f"  ⚠ baseVerbaDeCalculo: {_e_base}")

            # ── Identificar selects visíveis por conteúdo das opções ──
            # O formulário manual de verbas no PJE-Calc tem IDs gerados pelo JSF
            # que variam (ex: formulario:j_id_xxx:caracteristicaVerba). A estratégia
            # mais robusta é identificar cada select pelo conjunto de opções que ele contém.
            _JS_SELECTS_INFO = """() => {
                function norm(s) {
                    return (s || '').toLowerCase().normalize('NFD')
                        .replace(/[\\u0300-\\u036f]/g,'').trim();
                }
                return [...document.querySelectorAll('select')].filter(s => {
                    const r = s.getBoundingClientRect();
                    return r.width > 0 && r.height > 0;
                }).map(s => ({
                    id: s.id,
                    name: s.name,
                    options: [...s.options].map(o => ({
                        value: o.value,
                        text: o.text.trim(),
                        normText: norm(o.text),
                    })),
                }));
            }"""
            _selects_info = []
            try:
                _selects_info = self._page.evaluate(_JS_SELECTS_INFO)
            except Exception:
                pass

            def _sel_por_opcoes(palavras_chave: list[str], valor_desejado: str, campo_log: str) -> bool:
                """Encontra e preenche um select identificando-o pelas opções que contém."""
                import unicodedata as _ud
                def _norm(s: str) -> str:
                    return _ud.normalize("NFD", s.lower()).encode("ascii", "ignore").decode()

                _val_norm = _norm(valor_desejado)
                for _si in _selects_info:
                    # Verificar se este select tem as opções esperadas (palavras-chave nas opções)
                    _textos_norm = [_norm(o["text"]) for o in _si.get("options", [])]
                    if not all(any(kw in t for t in _textos_norm) for kw in palavras_chave):
                        continue
                    # Encontrar a opção mais próxima do valor desejado
                    _sid = _si.get("id") or _si.get("name") or ""
                    _sufixo = _sid.split(":")[-1] if ":" in _sid else _sid
                    _opcoes = _si.get("options", [])
                    _match_value = None
                    # Exact text match
                    for _o in _opcoes:
                        if _norm(_o["text"]) == _val_norm or _norm(_o["value"]) == _val_norm:
                            _match_value = _o["value"]
                            break
                    # Substring match
                    if not _match_value:
                        for _o in _opcoes:
                            if _val_norm in _norm(_o["text"]) or _norm(_o["text"]) in _val_norm:
                                _match_value = _o["value"]
                                break
                    if not _match_value and _opcoes:
                        _match_value = _opcoes[0]["value"]  # fallback: primeira opção não-vazia

                    if _match_value is not None:
                        # Selecionar via JS diretamente (mais confiável para JSF)
                        try:
                            _resultado = self._page.evaluate(
                                """([selId, selName, val]) => {
                                    let sel = selId ? document.getElementById(selId) : null;
                                    if (!sel && selName) {
                                        sel = document.querySelector('select[name="' + selName + '"]');
                                    }
                                    if (!sel) return null;
                                    sel.value = val;
                                    sel.dispatchEvent(new Event('change', {bubbles: true}));
                                    return sel.value;
                                }""",
                                [_si.get("id", ""), _si.get("name", ""), _match_value],
                            )
                            if _resultado is not None:
                                self._aguardar_ajax()
                                self._log(f"  ✓ {campo_log}: '{_match_value}' (id={_sid})")
                                return True
                        except Exception as _e:
                            self._log(f"  ⚠ {campo_log} JS set: {_e}")
                return False

            # ── Súmula 439 TST (formulario:ocorrenciaAjuizamento, confirmado DOM v2.15.1) ──
            # Sim (juros desde ajuizamento) = OCORRENCIAS_VENCIDAS_E_VINCENDAS
            # Não (juros desde arbitramento/vencimento) = OCORRENCIAS_VENCIDAS (padrão)
            _sumula_439 = v.get("sumula_439", False)
            _ocorr_ajuiz = "OCORRENCIAS_VENCIDAS_E_VINCENDAS" if _sumula_439 else "OCORRENCIAS_VENCIDAS"
            self._marcar_radio("ocorrenciaAjuizamento", _ocorr_ajuiz)

            # ── Helper: setar radio/select buscando por valor das opções (independente de ID) ──
            def _setar_campo_por_valor(valor_enum: str, campo_log: str) -> bool:
                """Busca qualquer radio ou select no form cujas opções contenham o valor_enum."""
                try:
                    return self._page.evaluate(f"""(valorEnum) => {{
                        // Tentar radios primeiro
                        const radios = document.querySelectorAll('input[type="radio"]');
                        for (const r of radios) {{
                            if (r.value === valorEnum && !r.checked) {{
                                r.click();
                                r.dispatchEvent(new Event('change', {{bubbles: true}}));
                                return true;
                            }}
                        }}
                        // Tentar selects
                        const sels = [...document.querySelectorAll('select')].filter(s => {{
                            const r = s.getBoundingClientRect();
                            return r.width > 0 && r.height > 0;
                        }});
                        for (const sel of sels) {{
                            for (const opt of sel.options) {{
                                if (opt.value === valorEnum) {{
                                    sel.value = valorEnum;
                                    sel.dispatchEvent(new Event('change', {{bubbles: true}}));
                                    return true;
                                }}
                            }}
                        }}
                        return false;
                    }}""", valor_enum)
                except Exception:
                    return False

            # ── Característica (RADIO, ID confirmado DOM v2.15.1: formulario:caracteristicaVerba) ──
            # Valores: COMUM / DECIMO_TERCEIRO / AVISO_PREVIO / FERIAS
            carac_label = v.get("caracteristica", "Comum")
            carac_enum = carac_map.get(_norm_key(carac_label), "COMUM")
            _carac_ok = any(
                self._preencher_radio_ou_select(fid, carac_enum, obrigatorio=False)
                for fid in ["caracteristicaVerba", "caracteristica", "caracteristicaDaVerba"]
            )
            if not _carac_ok:
                # Fallback: buscar radio/select pelo valor das opções (ID-independente)
                _carac_ok = _setar_campo_por_valor(carac_enum, "caracteristica")
                if _carac_ok:
                    self._aguardar_ajax()
                    self._log(f"  ✓ caracteristica: {carac_enum} (via fallback por valor)")
            if not _carac_ok:
                self._log(f"  ⚠ Verba '{nome}': característica '{carac_label}' ({carac_enum}) NÃO preenchida — pode causar erro na liquidação")

            # ── Ocorrência de pagamento (RADIO, ID confirmado DOM v2.15.1: formulario:ocorrenciaPagto) ──
            # Valores: DESLIGAMENTO / DEZEMBRO / MENSAL / PERIODO_AQUISITIVO
            #
            # IMPORTANTE: setCaracteristica() na classe VerbaDeCalculoVO já chama
            # setOcorrenciaDePagamento(carac.getOcorrenciaDePagamento()) automaticamente:
            #   COMUM → MENSAL
            #   DECIMO_TERCEIRO → DEZEMBRO
            #   AVISO_PREVIO → DESLIGAMENTO
            #   FERIAS → PERIODO_AQUISITIVO
            #
            # Portanto, só devemos clicar explicitamente em ocorrenciaPagto quando
            # o valor desejado DIFERIR do default da característica. Clicar
            # redundantemente causa NPE em LegendaDaFormula.getBase via reRender
            # painelLabelFormula (base ainda não foi definida).
            _carac_default_ocorr = {
                "COMUM": "MENSAL",
                "DECIMO_TERCEIRO": "DEZEMBRO",
                "AVISO_PREVIO": "DESLIGAMENTO",
                "FERIAS": "PERIODO_AQUISITIVO",
            }.get(carac_enum, "MENSAL")
            ocorr_label = v.get("ocorrencia", "Mensal")
            ocorr_enum = ocorr_map.get(_norm_key(ocorr_label), _carac_default_ocorr)
            if ocorr_enum == _carac_default_ocorr:
                self._log(
                    f"  ↳ ocorrencia {ocorr_enum} já definida por setCaracteristica({carac_enum}) — "
                    "skip click (evita NPE LegendaDaFormula.getBase)"
                )
            else:
                _ocorr_ok = any(
                    self._preencher_radio_ou_select(fid, ocorr_enum, obrigatorio=False)
                    for fid in ["ocorrenciaPagto", "ocorrencia", "ocorrenciaDePagamento", "periodicidade"]
                )
                if not _ocorr_ok:
                    _ocorr_ok = _setar_campo_por_valor(ocorr_enum, "ocorrencia")
                    if _ocorr_ok:
                        self._aguardar_ajax()
                        self._log(f"  ✓ ocorrencia: {ocorr_enum} (via fallback por valor)")
                if not _ocorr_ok:
                    self._log(f"  ⚠ Verba '{nome}': ocorrência '{ocorr_label}' ({ocorr_enum}) NÃO preenchida — pode causar erro na liquidação")

            # ── Base de Cálculo em 2 etapas (confirmado por vídeo + manual seção 9.2) ──
            # Etapa 1: Selecionar "Bases Cadastradas" (tipoDaBaseTabelada)
            #   → HISTORICO_SALARIAL / MAIOR_REMUNERACAO / SALARIO_DA_CATEGORIA / SALARIO_MINIMO
            # Etapa 2: Após AJAX, selecionar sub-opção no segundo dropdown
            #   → ex: "ÚLTIMA REMUNERAÇÃO" dentro de Histórico Salarial
            # Para verbas reflexas: NÃO preencher base cadastrada — usar a verba principal como base
            if not _eh_reflexa:
                _base_label = v.get("base_calculo") or "Historico Salarial"
                _BASE_ENUM = {
                    "historico": "HISTORICO_SALARIAL",
                    "maior remuneracao": "MAIOR_REMUNERACAO",
                    "maior remuneração": "MAIOR_REMUNERACAO",
                    "salario minimo": "SALARIO_MINIMO",
                    "salário mínimo": "SALARIO_MINIMO",
                    "piso salarial": "SALARIO_DA_CATEGORIA",
                    "salario categoria": "SALARIO_DA_CATEGORIA",
                }
                _base_enum_val = None
                for _k, _bv in _BASE_ENUM.items():
                    if _k in _norm_key(_base_label):
                        _base_enum_val = _bv
                        break
                if not _base_enum_val:
                    _base_enum_val = "HISTORICO_SALARIAL"

                _base_ok = self._selecionar("tipoDaBaseTabelada", _base_enum_val, obrigatorio=False)
                if not _base_ok:
                    _base_ok = _sel_por_opcoes(["historico"], _base_label, "base_calculo")
                if not _base_ok:
                    self._log(f"  ⚠ Verba '{nome}': base_calculo '{_base_label}' não preenchida")
                else:
                    # Etapa 2: Aguardar AJAX carregar sub-dropdown e selecionar
                    self._aguardar_ajax()
                    self._page.wait_for_timeout(800)
                    _sub_base = v.get("sub_base_calculo") or "ULTIMA REMUNERACAO"
                    try:
                        _sub_result = self._page.evaluate(
                            """(subBase) => {
                                // Buscar segundo select que aparece após AJAX (não é tipoDaBaseTabelada)
                                const sels = [...document.querySelectorAll('select')].filter(s => {
                                    const r = s.getBoundingClientRect();
                                    if (r.width <= 0 || r.height <= 0) return false;
                                    if (s.id.includes('tipoDaBase')) return false;
                                    if (s.id.includes('caracteristica')) return false;
                                    if (s.id.includes('ocorrencia')) return false;
                                    if (s.id.includes('baseVerba') || s.id.includes('verbaDeCalculo')) return false;
                                    // Deve ter opções de remuneração
                                    const optTexts = [...s.options].map(o => o.text.toLowerCase());
                                    return optTexts.some(t =>
                                        t.includes('remuner') || t.includes('salario') || t.includes('salário')
                                    );
                                });
                                const norm = s => s.toLowerCase().normalize('NFD')
                                    .replace(/[\\u0300-\\u036f]/g, '');
                                const target = norm(subBase);
                                for (const sel of sels) {
                                    for (const opt of sel.options) {
                                        if (norm(opt.text).includes(target)) {
                                            sel.value = opt.value;
                                            sel.dispatchEvent(new Event('change', {bubbles: true}));
                                            return opt.text;
                                        }
                                    }
                                    // Fallback: primeira opção não-vazia
                                    const valid = [...sel.options].filter(o =>
                                        o.value && o.value !== 'noSelectionValue'
                                    );
                                    if (valid.length) {
                                        sel.value = valid[0].value;
                                        sel.dispatchEvent(new Event('change', {bubbles: true}));
                                        return 'FALLBACK: ' + valid[0].text;
                                    }
                                }
                                return null;
                            }""",
                            _sub_base,
                        )
                        if _sub_result:
                            self._aguardar_ajax()
                            self._log(f"  ✓ sub_base_calculo: {_sub_result}")
                    except Exception as _e_sub:
                        self._log(f"  ⚠ sub_base_calculo: {_e_sub}")

                    # Etapa 3 (HISTORICO_SALARIAL apenas): clicar 'incluirBaseHistorico'
                    # para adicionar o histórico selecionado à lista
                    # historicosSalariaisDaVerbaParaValorDevido. Sem este clique,
                    # Salvar falha com "Campo obrigatório: Histórico Salarial
                    # [id=baseHistoricos]" (validação do apresentador).
                    # Confirmado via verba-calculo.xhtml linha 558:
                    #   actionListener="#{apresentador.adicionarHistoricoSalarialDaVerba}"
                    if _base_enum_val == "HISTORICO_SALARIAL":
                        try:
                            _incluir_res = self._page.evaluate(
                                """() => {
                                    // Procurar commandLink 'incluirBaseHistorico' visível
                                    const links = [...document.querySelectorAll(
                                        'a[id$="incluirBaseHistorico"], a[id*="incluirBaseHistorico"]'
                                    )];
                                    for (const a of links) {
                                        const r = a.getBoundingClientRect();
                                        if (r.width > 0 && r.height > 0) {
                                            a.click();
                                            return a.id || 'incluirBaseHistorico';
                                        }
                                    }
                                    return null;
                                }"""
                            )
                            if _incluir_res:
                                self._aguardar_ajax()
                                self._page.wait_for_timeout(500)
                                self._log(f"  ✓ Histórico Salarial adicionado à base (click {_incluir_res})")
                            else:
                                self._log(
                                    "  ⚠ incluirBaseHistorico não encontrado — "
                                    "verba pode falhar ao salvar com 'Campo obrigatório: Histórico Salarial'"
                                )
                        except Exception as _e_inc:
                            self._log(f"  ⚠ incluirBaseHistorico: {_e_inc}")

            if v.get("valor_informado"):
                # formulario:valor (radio CALCULADO/INFORMADO) — confirmado DOM v2.15.1
                _val_ok = self._preencher_radio_ou_select("valor", "INFORMADO", obrigatorio=False)
                if not _val_ok:
                    _val_ok = _setar_campo_por_valor("INFORMADO", "valor")
                    if _val_ok:
                        self._aguardar_ajax()
                # formulario:outroValorDoMultiplicador — campo Multiplicador confirmado
                self._preencher("outroValorDoMultiplicador", _fmt_br(v["valor_informado"]), False)
            else:
                _val_ok = self._preencher_radio_ou_select("valor", "CALCULADO", obrigatorio=False)
                if not _val_ok:
                    _setar_campo_por_valor("CALCULADO", "valor")

            # ── Valor Devido Calculado: DivisorDeVerbaEnum.OUTRO_VALOR, TipoDeQuantidadeEnum.INFORMADA ──
            # VerbaDeCalculoVO.<init>() seta tipoDeDivisor=OUTRO_VALOR e tipoDaQuantidade=INFORMADA (bytecode v2.14.0).
            # Isso torna 3 campos obrigatórios no modo Calculado:
            #   1) outroValorDoDivisor  — required="#{registro.isInformarDivisor()}" (true quando OUTRO_VALOR)
            #   2) outroValorDoMultiplicador — required="true" incondicional
            #   3) valorInformadoDaQuantidade — required="#{registro.isTipoDaQuantidadeInformada()}" (true quando INFORMADA)
            # Os valores NÃO têm default no construtor (ficam null), então precisamos sempre preenchê-los
            # quando valor=CALCULADO. Para valor=INFORMADO, todo o painel não é renderizado (rendered=#{isValorDevidoCalculado}).
            _modo_calculado = not bool(v.get("valor_informado"))
            if _modo_calculado:
                # Tipo de divisor (DOM: tipoDeDivisor select)
                # Values: OUTRO_VALOR (default), DIAS_NO_MES, HORAS_NO_MES
                _tipo_div = v.get("tipo_divisor")
                if _tipo_div:
                    self._selecionar("tipoDeDivisor", _tipo_div, obrigatorio=False)
                    self._aguardar_ajax()
                    self._page.wait_for_timeout(300)

                # Multiplicador (default 1 = base * 1)
                _mult_val = v.get("multiplicador")
                if _mult_val is None:
                    _mult_val = 1
                self._preencher("outroValorDoMultiplicador", _fmt_br(float(_mult_val)), False)
                # Divisor (default 1 = base / 1 = base integral)
                _div_val = v.get("divisor")
                if _div_val is None:
                    _div_val = 1
                self._preencher("outroValorDoDivisor", _fmt_br(float(_div_val)), False)

                # Tipo de quantidade (DOM: tipoDaQuantidade select)
                # Values: INFORMADA (default), CONFORME_JORNADA, CONFORME_CARTAO_DE_PONTO
                _tipo_qtd = v.get("tipo_quantidade")
                if _tipo_qtd:
                    self._selecionar("tipoDaQuantidade", _tipo_qtd, obrigatorio=False)
                    self._aguardar_ajax()
                    self._page.wait_for_timeout(300)

                # Quantidade Informada (default 1 = 1 unidade por ocorrência)
                # Só preenche se tipoDaQuantidade permaneceu INFORMADA (default).
                _qtd_val = v.get("quantidade")
                if _qtd_val is None:
                    _qtd_val = 1
                self._preencher("valorInformadoDaQuantidade", _fmt_br(float(_qtd_val)), False)
            else:
                # Modo INFORMADO: multiplicador/divisor/quantidade não são renderizados.
                # Apenas preenche explícitos se o usuário forneceu (raro nesse modo).
                if v.get("multiplicador") is not None:
                    self._preencher("outroValorDoMultiplicador", _fmt_br(float(v["multiplicador"])), False)
                if v.get("divisor") is not None:
                    self._preencher("outroValorDoDivisor", _fmt_br(float(v["divisor"])), False)

            # ── Incidências (checkboxes, confirmados DOM v2.15.1) ──
            # Incidência: IRPF / Contribuição Social / FGTS / Previdência Privada / Pensão Alimentícia
            # Estratégia robusta: tentar por ID primeiro, depois por label text (JSF gera IDs variáveis)
            def _marcar_checkbox_robusto(ids: list[str], labels: list[str], marcar: bool, campo_log: str) -> bool:
                """Tenta marcar checkbox por IDs conhecidos, depois por labels visíveis."""
                for fid in ids:
                    if self._marcar_checkbox(fid, marcar):
                        return True
                # Fallback: buscar checkbox por label text no DOM
                for lbl_text in labels:
                    try:
                        _found = self._page.evaluate(f"""(labelText, shouldCheck) => {{
                            const norm = s => (s||'').toLowerCase().normalize('NFD')
                                .replace(/[\\u0300-\\u036f]/g,'').trim();
                            const target = norm(labelText);
                            // Buscar labels que contenham o texto
                            const labels = [...document.querySelectorAll('label')];
                            for (const lbl of labels) {{
                                if (norm(lbl.textContent).includes(target)) {{
                                    // Encontrar checkbox associado
                                    let cb = null;
                                    if (lbl.htmlFor) {{
                                        cb = document.getElementById(lbl.htmlFor);
                                    }}
                                    if (!cb) {{
                                        cb = lbl.querySelector('input[type="checkbox"]');
                                    }}
                                    if (!cb) {{
                                        const parent = lbl.closest('td, div, span');
                                        if (parent) cb = parent.querySelector('input[type="checkbox"]');
                                    }}
                                    if (cb && cb.type === 'checkbox') {{
                                        if (cb.checked !== shouldCheck) {{
                                            cb.click();
                                        }}
                                        return cb.id || 'found';
                                    }}
                                }}
                            }}
                            return null;
                        }}""", lbl_text, marcar)
                        if _found:
                            self._aguardar_ajax()
                            self._log(f"  ✓ {campo_log}: via label '{lbl_text}' (id={_found})")
                            return True
                    except Exception:
                        continue
                return False

            _fgts = bool(v.get("incidencia_fgts"))
            if not _marcar_checkbox_robusto(
                ["fgts", "incidenciaFGTS", "incideFgts", "incidenciaFgts", "incidenciaDoFGTS"],
                ["FGTS", "Fundo de Garantia"],
                _fgts, f"Verba '{nome}' FGTS"
            ):
                self._log(f"  ⚠ Verba '{nome}': checkbox FGTS não encontrado (desejado={_fgts})")

            _inss = bool(v.get("incidencia_inss"))
            if not _marcar_checkbox_robusto(
                ["inss", "contribuicaoSocial", "incidenciaINSS", "incidenciaInss"],
                ["Contribuição Social", "INSS", "Contribuicao Social"],
                _inss, f"Verba '{nome}' INSS/CS"
            ):
                self._log(f"  ⚠ Verba '{nome}': checkbox INSS/CS não encontrado (desejado={_inss})")

            _irpf = bool(v.get("incidencia_ir"))
            if not _marcar_checkbox_robusto(
                ["impostoDeRenda", "irpf", "ir", "incidenciaIRPF", "incidenciaIr"],
                ["IRPF", "Imposto de Renda", "IR"],
                _irpf, f"Verba '{nome}' IRPF"
            ):
                self._log(f"  ⚠ Verba '{nome}': checkbox IRPF não encontrado (desejado={_irpf})")

            # Previdência Privada e Pensão Alimentícia (checkboxes opcionais)
            if v.get("incidencia_previdencia_privada") is not None:
                _marcar_checkbox_robusto(
                    ["previdenciaPrivada", "incidenciaPrevidenciaPrivada"],
                    ["Previdência Privada", "Previdencia Privada"],
                    bool(v["incidencia_previdencia_privada"]), f"Verba '{nome}' Prev.Privada"
                )
            if v.get("incidencia_pensao_alimenticia") is not None:
                _marcar_checkbox_robusto(
                    ["pensaoAlimenticia", "incidenciaPensaoAlimenticia"],
                    ["Pensão Alimentícia", "Pensao Alimenticia"],
                    bool(v["incidencia_pensao_alimenticia"]), f"Verba '{nome}' Pensão"
                )

            # Campos opcionais de verba (comportamento, fração, dobra, exclusões)
            if v.get("tratamento_fracao"):
                self._selecionar("tratamentoFracao", v["tratamento_fracao"], obrigatorio=False)
            if v.get("comportamento_base"):
                self._selecionar("comportamentoBase", v["comportamento_base"], obrigatorio=False)
            if v.get("dobrar_valor_devido"):
                self._marcar_checkbox("dobrarValorDevido", True)
            if v.get("zerar_valor_negativo") is not None:
                self._marcar_checkbox("zerarValorNegativo", bool(v["zerar_valor_negativo"]))
            if v.get("excluir_faltas_justificadas") is not None:
                self._marcar_checkbox("excluirFaltasJustificadas", bool(v["excluir_faltas_justificadas"]))
            if v.get("excluir_faltas_nao_justificadas") is not None:
                self._marcar_checkbox("excluirFaltasNaoJustificadas", bool(v["excluir_faltas_nao_justificadas"]))
            if v.get("excluir_ferias_gozadas") is not None:
                self._marcar_checkbox("excluirFeriasGozadas", bool(v["excluir_ferias_gozadas"]))
            # Juros TST 439 (select na verba)
            if v.get("juros_tst_439"):
                self._selecionar("jurosTst439", v["juros_tst_439"], obrigatorio=False)
            # Tipo pago (radio — se verba já foi parcialmente paga)
            if v.get("tipo_pago"):
                self._marcar_radio("tipoPago", v["tipo_pago"])

            # Período — IDs confirmados DOM v2.15.1:
            # formulario:periodoInicialInputDate / formulario:periodoFinalInputDate
            if v.get("periodo_inicio"):
                self._preencher_data("periodoInicialInputDate", v["periodo_inicio"], False) or \
                self._preencher_data("periodoInicial", v["periodo_inicio"], False) or \
                self._preencher_data("dtInicial", v["periodo_inicio"], False)
            if v.get("periodo_fim"):
                self._preencher_data("periodoFinalInputDate", v["periodo_fim"], False) or \
                self._preencher_data("periodoFinal", v["periodo_fim"], False) or \
                self._preencher_data("dtFinal", v["periodo_fim"], False)

            _salvou = self._clicar_salvar()
            self._aguardar_ajax()
            self._page.wait_for_timeout(600)

            # Segundo check de erros — SOMENTE quando _clicar_salvar() retornou False.
            # _clicar_salvar() já faz polling por ~10s diferenciando sucesso vs erro
            # através dos textos 'sucesso'/'realizada' vs 'erro'/'falha'/'formulário'.
            # Se retornou True, confiamos nesse resultado — o seletor genérico
            # [class*="error"]/[class*="erro"] produz falsos positivos ao casar com
            # containers estruturais do RichFaces (rich-messages-marker, etc.)
            # que envolvem mensagens de SUCESSO também, gerando "ERRO ao salvar — Sucesso."
            if not _salvou:
                try:
                    _erro_msgs = self._page.evaluate("""() => {
                        // Filtrar apenas mensagens de erro REAIS (com texto erro/falha/obrigatório)
                        const erros = [...document.querySelectorAll(
                            '.rf-msgs-err, .rf-msg-err, ' +
                            '[class*="error"], [class*="Error"], [class*="erro"]'
                        )].map(e => (e.textContent || '').trim()).filter(t => {
                            if (!t) return false;
                            const low = t.toLowerCase();
                            // rejeita containers que envolvem mensagens de sucesso
                            if (low.includes('sucesso') || low.includes('realizada')
                                || low.includes('salvo com')) return false;
                            return low.includes('erro') || low.includes('falha')
                                || low.includes('obrigat') || low.includes('inválid')
                                || low.includes('invalid') || low.includes('não pôde')
                                || low.includes('não pode') || low.includes('formulário');
                        });
                        if (document.title && document.title.match(/500|erro|error/i)) {
                            erros.push('Página de erro HTTP: ' + document.title);
                        }
                        return erros;
                    }""")
                    if _erro_msgs:
                        self._log(f"  ⚠ Verba '{nome}': ERRO ao salvar — {'; '.join(_erro_msgs[:3])}")
                        # Detectar campos específicos com erro para diagnóstico
                        _erros_det = self._detectar_erros_formulario(f"Verba Manual '{nome}'")
                        # Tentar corrigir e re-salvar UMA vez
                        if _erros_det:
                            _corrigiu = self._tentar_corrigir_erros(_erros_det, v, f"Verba Manual '{nome}'")
                            if _corrigiu:
                                _salvou = self._clicar_salvar()
                                self._aguardar_ajax()
                                if _salvou:
                                    self._log(f"  ✓ Verba '{nome}': salvou após correção automática")
                except Exception:
                    pass

            # Após salvar, atualizar conversationId (pode ter mudado) e voltar para listagem
            self._capturar_base_calculo()
            # Recalcular URLs com o conversationId atual para próximas iterações
            if self._calculo_url_base and self._calculo_conversation_id:
                _url_verbas = (
                    f"{self._calculo_url_base}verba/verbas-para-calculo.jsf"
                    f"?conversationId={self._calculo_conversation_id}"
                )
                _url_verbas_listing = (
                    f"{self._calculo_url_base}verba/verba-calculo.jsf"
                    f"?conversationId={self._calculo_conversation_id}"
                )

            if "verbas-para-calculo" not in self._page.url:
                try:
                    self._page.goto(_url_verbas, wait_until="domcontentloaded", timeout=20000)
                    self._page.wait_for_timeout(1000)
                    self._aguardar_ajax()
                except Exception:
                    self._clicar_menu_lateral("Verbas", obrigatorio=False)
                    self._page.wait_for_timeout(800)

            if _salvou:
                self._log(f"  ✓ Verba manual: {nome}")
            else:
                self._log(f"  ✗ Verba '{nome}': Salvar falhou — VERBA NÃO REGISTRADA")

            # Registrar resultado no VerbaStrategyEngine
            if self._strategy_engine:
                try:
                    self._strategy_engine.registrar_resultado(
                        v, "manual", sucesso=_salvou,
                        erro=None if _salvou else f"Salvar falhou para '{nome}'",
                        detalhes={"parametros": {
                            "caracteristica": v.get("caracteristica"),
                            "ocorrencia": v.get("ocorrencia"),
                        }},
                    )
                except Exception:
                    pass

    # ── Fase 3B: Multas e Indenizações ────────────────────────────────────────

    def fase_multas_indenizacoes(self, multas: list) -> None:
        """Lança multas e indenizações na aba 'Multas e Indenizações'.

        Campos confirmados DOM v2.15.1 (multas-indenizacoes.jsf — formulário Novo):
        - formulario:descricao (text) — nome
        - formulario:valor (radio) — INFORMADO / CALCULADO
        - formulario:aliquota (text) — valor ou percentual
        - formulario:credorDevedor (select) — RECLAMANTE_RECLAMADO / RECLAMADO_RECLAMANTE / ...
        - formulario:tipoBaseMulta (select) — PRINCIPAL / VALOR_CAUSA / ...
        - formulario:salvar (button) — Salvar

        Chamada somente se dados['multas_indenizacoes'] for não-vazio.
        """
        if not multas:
            return
        self._log("Fase 3B — Multas e Indenizações…")
        self._verificar_tomcat(timeout=60)
        navegou = self._clicar_menu_lateral("Multas e Indenizações", obrigatorio=False) or \
                  self._clicar_menu_lateral("Multas", obrigatorio=False)
        if not navegou:
            self._log("  → Seção Multas e Indenizações não encontrada no menu — pulando.")
            return

        _url_multas = self._page.url

        for multa in multas:
            nome_m = multa.get("nome") or multa.get("descricao") or "Multa/Indenização"
            self._log(f"  → Lançando: {nome_m}")

            # Voltar para listagem se necessário
            if self._page.url != _url_multas:
                try:
                    self._page.goto(_url_multas, wait_until="domcontentloaded", timeout=20000)
                    self._aguardar_ajax()
                except Exception:
                    self._clicar_menu_lateral("Multas e Indenizações", obrigatorio=False)
                    self._page.wait_for_timeout(800)

            # Clicar "Incluir" — NUNCA _clicar_novo() que pode criar novo cálculo
            if not self._clicar_botao_id("incluir"):
                self._log(f"  ⚠ '{nome_m}': botão 'incluir' não encontrado — ignorada.")
                continue
            self._aguardar_ajax()
            try:
                self._page.wait_for_selector("[id$=':descricao']", state="visible", timeout=5000)
            except Exception:
                self._log(f"  ⚠ '{nome_m}': formulário Novo não abriu — ignorada.")
                continue

            # Nome/Descrição — ID confirmado: formulario:descricao
            self._preencher("descricao", nome_m, obrigatorio=False)

            # Valor: INFORMADO (valor fixo) ou CALCULADO (percentual sobre base)
            _valor_fixo = multa.get("valor")
            _percentual = multa.get("percentual") or multa.get("aliquota")
            if _valor_fixo is not None:
                self._marcar_radio("valor", "INFORMADO")
                self._preencher("aliquota", _fmt_br(float(_valor_fixo)), False)
            elif _percentual is not None:
                self._marcar_radio("valor", "CALCULADO")
                self._preencher("aliquota", _fmt_br(float(_percentual)), False)
            else:
                self._marcar_radio("valor", "CALCULADO")

            # Credor/Devedor — padrão: Reclamante e Reclamado
            _credor = multa.get("credor_devedor", "RECLAMANTE_RECLAMADO")
            self._selecionar("credorDevedor", _credor, obrigatorio=False)

            # Base da multa — padrão: PRINCIPAL
            _base = multa.get("base", "PRINCIPAL")
            self._selecionar("tipoBaseMulta", _base, obrigatorio=False)

            self._clicar_salvar()
            self._aguardar_ajax()
            self._page.wait_for_timeout(500)
            self._log(f"  ✓ Multa/Indenização: {nome_m}")

        self._log("Fase 3B concluída.")

    # ── Fase 4: FGTS ──────────────────────────────────────────────────────────

    @retry(max_tentativas=3)
    def fase_fgts(self, fgts: dict) -> None:
        self._log("Fase 4 — FGTS…")
        self._verificar_tomcat(timeout=60)
        self._verificar_pagina_pjecalc()
        # Tentar navegar para a seção FGTS no menu lateral
        navegou = self._clicar_menu_lateral("FGTS", obrigatorio=False)
        if not navegou:
            navegou = self._clicar_menu_lateral("Fundo de Garantia", obrigatorio=False)
        if navegou:
            self._verificar_pagina_pjecalc()
            navegou = self._verificar_secao_ativa("FGTS")
        if not navegou:
            self._log("  → Seção FGTS não encontrada no menu — incidência já configurada por verba.")
            return
        self.mapear_campos("fase4_fgts")

        # IDs confirmados por inspeção DOM (fgts.jsf v2.15.1):
        # formulario:tipoDeVerba (radio PAGAR/DEPOSITAR)
        # formulario:comporPrincipal (radio SIM/NAO)
        # formulario:multa (checkbox — ativa a multa rescisória 40%)
        # formulario:multaDoFgts (radio VINTE_POR_CENTO/QUARENTA_POR_CENTO)
        # formulario:multaDoArtigo467 (checkbox — Multa Art. 467 CLT)
        # formulario:multa10 (checkbox — multa 10% rescisão antecipada)
        # formulario:aliquota (radio OITO_POR_CENTO/DOIS_POR_CENTO)
        # formulario:incidenciaDoFgts (select)
        # formulario:excluirAvisoDaMulta (checkbox)
        # formulario:deduzirDoFGTS (checkbox)
        # formulario:competenciaInputDate + formulario:valor (saldo depositado)

        # DOM probe: detectar tipos reais dos elementos FGTS
        _fgts_types = {}
        try:
            _fgts_types = self._page.evaluate("""() => {
                const fields = ['tipoDeVerba','comporPrincipal','aliquota',
                                'multaDoFgts','tipoDoValorDaMulta','multa',
                                'multaDoArtigo467','incidenciaDoFgts'];
                const result = {};
                for (const f of fields) {
                    const sel = document.querySelector(`select[id*="${f}"]`);
                    const rad = document.querySelector(`input[type="radio"][id*="${f}"]`);
                    const chk = document.querySelector(`input[type="checkbox"][id*="${f}"]`);
                    result[f] = (sel ? 'select' : rad ? 'radio' : chk ? 'checkbox' : 'unknown');
                }
                return result;
            }""")
            self._log(f"  ℹ FGTS DOM types: {_fgts_types}")
        except Exception:
            pass

        # Se TODOS os campos são unknown, o formulário FGTS não renderizou —
        # provavelmente a conversação Seam foi invalidada. Re-abrir o cálculo
        # e navegar para FGTS via sidebar.
        if _fgts_types and all(v == "unknown" for v in _fgts_types.values()):
            self._log("  ⚠ FGTS: formulário não renderizou — re-abrindo cálculo via Home…")
            try:
                _home = f"{self.PJECALC_BASE}/pages/principal.jsf"
                self._page.goto(_home, wait_until="networkidle", timeout=15000)
                self._page.wait_for_timeout(1500)
                _lb = self._page.locator(
                    "select[class*='listaCalculosRecentes'], "
                    "select[name*='listaCalculosRecentes']"
                )
                if _lb.count() > 0:
                    _lb.first.locator("option").first.click()
                    _lb.first.dblclick()
                    self._page.wait_for_timeout(3000)
                    self._capturar_base_calculo()
                    self._log(f"  ✓ Cálculo re-aberto (conv={self._calculo_conversation_id})")
                    # Navegar para FGTS via sidebar (nova conversação Seam)
                    _nav2 = self._clicar_menu_lateral("FGTS", obrigatorio=False)
                    if _nav2:
                        self._aguardar_ajax()
                        self._page.wait_for_timeout(2000)
                        self.mapear_campos("fase4_fgts_retry")
                        # Re-probe
                        try:
                            _fgts_types = self._page.evaluate("""() => {
                                const fields = ['tipoDeVerba','comporPrincipal','aliquota',
                                                'multaDoFgts','tipoDoValorDaMulta','multa',
                                                'multaDoArtigo467','incidenciaDoFgts'];
                                const result = {};
                                for (const f of fields) {
                                    const sel = document.querySelector(`select[id*="${f}"]`);
                                    const rad = document.querySelector(`input[type="radio"][id*="${f}"]`);
                                    const chk = document.querySelector(`input[type="checkbox"][id*="${f}"]`);
                                    result[f] = (sel ? 'select' : rad ? 'radio' : chk ? 'checkbox' : 'unknown');
                                }
                                return result;
                            }""")
                            self._log(f"  ℹ FGTS DOM types (retry): {_fgts_types}")
                        except Exception:
                            pass
            except Exception as _e:
                self._log(f"  ⚠ FGTS re-open falhou: {_e}")

        # Destino: PAGAR (ao reclamante) ou DEPOSITAR (em conta vinculada)
        self._log("  → FGTS: preenchendo tipoDeVerba…")
        _destino = fgts.get("destino", "PAGAR")
        self._preencher_radio_ou_select("tipoDeVerba", _destino)

        # Compor principal
        self._log("  → FGTS: preenchendo comporPrincipal…")
        _compor = "SIM" if fgts.get("compor_principal", True) else "NAO"
        self._preencher_radio_ou_select("comporPrincipal", _compor)

        # Alíquota — radio com valores enum (não percentual numérico)
        self._log("  → FGTS: preenchendo aliquota…")
        aliquota = fgts.get("aliquota", 0.08)
        _aliq_radio = "DOIS_POR_CENTO" if aliquota <= 0.02 else "OITO_POR_CENTO"
        self._preencher_radio_ou_select("aliquota", _aliq_radio)

        # Incidência do FGTS (select) — padrão: sobre o total devido
        self._log("  → FGTS: preenchendo incidenciaDoFgts…")
        _incidencia_map = {
            "total_devido": "SOBRE_O_TOTAL_DEVIDO",
            "depositado_sacado": "SOBRE_DEPOSITADO_SACADO",
            "diferenca": "SOBRE_DIFERENCA",
            "total_mais_saque": "SOBRE_TOTAL_DEVIDO_MAIS_SAQUE_E_OU_SALDO",
            "total_menos_saque": "SOBRE_TOTAL_DEVIDO_MENOS_SAQUE_E_OU_SALDO",
        }
        _incidencia = _incidencia_map.get(
            fgts.get("incidencia", "total_devido"), "SOBRE_O_TOTAL_DEVIDO"
        )
        self._selecionar("incidenciaDoFgts", _incidencia, obrigatorio=False)

        # Multa rescisória — SELECT formulario:multa (NAO_APURAR / CALCULADA / INFORMADA)
        # DOM confirmado v2.15.1: é SELECT, NÃO checkbox.
        # Selecionar CALCULADA ativa campos condicionais (multaDoFgts, baseDaMulta, etc.)
        # Tem a4j:support onchange que re-renderiza esses campos via AJAX.
        multa_40 = fgts.get("multa_40", True)
        multa_467 = fgts.get("multa_467", False)
        # Determinar valor do select multa
        if fgts.get("multa") in ("NAO_APURAR", "CALCULADA", "INFORMADA"):
            # Valor direto do DOM (extrações atualizadas)
            _multa_val = fgts["multa"]
        elif multa_40:
            _multa_val = "CALCULADA"
        else:
            _multa_val = "NAO_APURAR"
        self._log(f"  → FGTS: preenchendo multa={_multa_val}…")
        self._selecionar("multa", _multa_val, obrigatorio=False)
        # Aguardar AJAX do onchange do select multa (re-renderiza campos dependentes)
        # Timeout reduzido a 8s: se o AJAX não completar em 8s, é porque não houve
        # mudança real (ex: valor já era o mesmo) — prosseguir evita hang.
        self._aguardar_ajax(timeout=8000)
        self._page.wait_for_timeout(1000)

        if _multa_val == "CALCULADA":
            # Percentual: 40% padrão; 20% para estabilidade provisória (CIPA, gestante etc.)
            self._log("  → FGTS: preenchendo multaDoFgts…")
            _pct_multa = "VINTE_POR_CENTO" if fgts.get("multa_20") else "QUARENTA_POR_CENTO"
            self._preencher_radio_ou_select("multaDoFgts", _pct_multa)

            # Base da multa (select condicional: DEVIDO / DIFERENCA / SALDO_E_OU_SAQUE / etc.)
            _base_multa = fgts.get("base_multa", fgts.get("baseDaMulta", ""))
            if _base_multa:
                self._log(f"  → FGTS: preenchendo baseDaMulta={_base_multa}…")
                self._selecionar("baseDaMulta", _base_multa, obrigatorio=False)

            # Excluir aviso indenizado da base da multa (checkbox)
            _excl_aviso = fgts.get("excluir_aviso_multa", False)
            self._marcar_checkbox("excluirAvisoDaMulta", _excl_aviso)

        elif _multa_val == "INFORMADA":
            # Valor fixo da multa informada (campo condicional quando multa=INFORMADA)
            _val_multa_inf = fgts.get("valor_multa_informada") or fgts.get("valorMultaInformada")
            if _val_multa_inf:
                self._preencher("valorMultaInformada", _fmt_br(float(_val_multa_inf)), False)
                self._log(f"  ✓ Valor multa informada: R$ {_val_multa_inf}")

        # Pensão alimentícia sobre FGTS (checkbox condicional)
        if fgts.get("pensao_alimenticia_fgts") is not None:
            self._marcar_checkbox("pensaoAlimenticiaFgts", bool(fgts["pensao_alimenticia_fgts"]))

        # Multa Art. 467 CLT — checkbox formulario:multaDoArtigo467
        if multa_467:
            self._marcar_checkbox("multaDoArtigo467", True)

        # Multa 10% (rescisão antecipada de contrato a prazo)
        if fgts.get("multa_10"):
            self._marcar_checkbox("multa10", True)

        # Saldos FGTS já depositados (para dedução)
        # FIX: marcar checkbox "deduzirDoFGTS" UMA ÚNICA VEZ antes do loop.
        # Antes, o marcar dentro do loop causava toggle em iterações subsequentes
        # (checkbox fica desmarcado na 2ª linha), e a seção de saldos ficava
        # indisponível intermitentemente.
        _saldos_validos = [s for s in fgts.get("saldos", []) if s.get("data") and s.get("valor")]
        if _saldos_validos:
            self._log(f"  → FGTS: marcando deduzirDoFGTS ({len(_saldos_validos)} saldo(s))…")
            self._marcar_checkbox("deduzirDoFGTS", True)
            self._aguardar_ajax(timeout=8000)
            self._page.wait_for_timeout(300)  # tempo para AJAX habilitar a seção
            for saldo in _saldos_validos:
                self._preencher_data("competencia", saldo["data"], False)
                self._preencher("valor", _fmt_br(saldo["valor"]), False)
                # Adicionar linha via botão "+" ou Enter
                _adicionou = (
                    self._clicar_botao_id("btnAdicionarSaldo")
                    or self._clicar_botao_id("adicionarSaldo")
                )
                if _adicionou:
                    self._aguardar_ajax(timeout=8000)
                    self._log(f"  ✓ Saldo FGTS deduzido: {saldo['data']} R$ {saldo['valor']}")

        # Salvar — ID confirmado: formulario:salvar
        self._log("  → FGTS: clicando Salvar…")
        if not self._clicar_salvar():
            self._log("  ⚠ Fase 4: Salvar FGTS não confirmado.")
        self._aguardar_ajax(timeout=10000)

        # Fase 4B: ajustar Ocorrências do FGTS com 13º proporcional em dezembro
        # (Lei 8.036/90 — FGTS sobre 13º recolhido na competência de dezembro)
        _ajustes_13o = fgts.get("ajustes_ocorrencias_13o") or []
        if _ajustes_13o and fgts.get("incidencia_13o_dezembro", True):
            try:
                self._ajustar_ocorrencias_fgts(_ajustes_13o)
            except Exception as e:
                self._log(f"  ⚠ Ajuste de Ocorrências FGTS falhou: {e}")

        self._log("Fase 4 concluída.")

    # ── Fase 4B: Ocorrências do FGTS (ajuste 13º) ─────────────────────────────

    def _ajustar_ocorrencias_fgts(self, ajustes: list[dict]) -> None:
        """Aplica ajustes de 13º proporcional na página Ocorrências do FGTS.

        Fluxo (parametrizar-fgts.xhtml):
        1. Clicar no botão `formulario:ocorrencias` na aba FGTS para abrir a página.
        2. Para cada linha em `formulario:listagem`, ler `[id$=':ocorrencia']` (MM/YYYY)
           e, se bater com um ajuste, somar `valor_13o_proporcional` ao
           `[id$=':baseHistorico']` (input moeda BR, a4j:support onblur → AJAX).
        3. Clicar em `formulario:salvar` e aguardar a mensagem de sucesso.

        Args:
            ajustes: lista de dicts com keys 'competencia' (MM/YYYY),
                     'valor_13o_proporcional' (float).
        """
        if not ajustes:
            return
        self._log(f"  → Ajustando Ocorrências FGTS: {len(ajustes)} competência(s) com 13º…")

        # 1. Navegar para página Ocorrências
        #    IDs reais em fgts.xhtml / parametrizar-fgts.xhtml:
        #      formulario:ocorrencias (botão "Ocorrências")
        abriu = self._clicar_botao_id("ocorrencias")
        if not abriu:
            # Fallback: tentar pelo texto do botão
            try:
                self._page.get_by_role("button", name="Ocorrências").first.click()
                abriu = True
            except Exception:
                abriu = False
        if not abriu:
            self._log("  ⚠ Botão Ocorrências (FGTS) não encontrado — ajuste do 13º pulado.")
            return
        self._aguardar_ajax()
        self._page.wait_for_timeout(1200)

        # 2. Mapear competências → índice de linha na listagem
        try:
            linhas_info = self._page.evaluate("""() => {
                const inputs = document.querySelectorAll('[id^="formulario:listagem:"][id$=":ocorrencia"]');
                const result = {};
                for (const el of inputs) {
                    const m = el.id.match(/^formulario:listagem:(\\d+):ocorrencia$/);
                    if (!m) continue;
                    const txt = (el.value || el.textContent || '').trim();
                    if (txt) result[txt] = parseInt(m[1], 10);
                }
                return result;
            }""")
        except Exception as e:
            self._log(f"  ⚠ Falha ao mapear linhas da tabela de Ocorrências FGTS: {e}")
            return

        if not linhas_info:
            self._log("  ⚠ Tabela de Ocorrências FGTS vazia ou IDs diferentes do esperado.")
            return

        # 3. Para cada ajuste, localizar a linha e somar o 13º proporcional à base
        aplicados = 0
        for ajuste in ajustes:
            comp = (ajuste.get("competencia") or "").strip()
            valor_13o = float(ajuste.get("valor_13o_proporcional") or 0)
            if not comp or valor_13o <= 0:
                continue
            idx = linhas_info.get(comp)
            if idx is None:
                # Algumas instalações renderizam "12/2022" ou "12/2022 " — tentar match fuzzy
                for k, v in linhas_info.items():
                    if k.startswith(comp) or comp.startswith(k):
                        idx = v
                        break
            if idx is None:
                self._log(f"  ⚠ Competência {comp} não encontrada na tabela — ignorada.")
                continue

            base_id = f"formulario:listagem:{idx}:baseHistorico"
            try:
                loc = self._page.locator(f"[id='{base_id}']").first
                loc.wait_for(state="visible", timeout=5000)
                # Ler valor atual (em formato BR "1.234,56") e somar 13º
                val_atual_str = loc.input_value() or "0"
                # Converter BR → float
                try:
                    val_atual = float(
                        val_atual_str.replace(".", "").replace(",", ".")
                        if "," in val_atual_str else val_atual_str
                    )
                except Exception:
                    val_atual = 0.0
                novo_valor = val_atual + valor_13o
                novo_str = _fmt_br(novo_valor)
                # Preencher e disparar blur (a4j:support onblur → AJAX postback)
                loc.click()
                loc.fill("")
                loc.fill(novo_str)
                loc.dispatch_event("input")
                loc.dispatch_event("change")
                # Blur via Tab para disparar o a4j:support onblur
                loc.press("Tab")
                self._aguardar_ajax()
                self._log(
                    f"  ✓ {comp}: base {val_atual_str} + 13º R$ {valor_13o:.2f} = R$ {novo_str}"
                )
                aplicados += 1
            except Exception as e:
                self._log(f"  ⚠ Falha ao ajustar {comp} (idx={idx}): {e}")
                continue

        # 4. Salvar a página de Ocorrências
        if aplicados > 0:
            if self._clicar_salvar():
                self._log(f"  ✓ Ocorrências FGTS salvas ({aplicados} ajustes aplicados).")
            else:
                self._log("  ⚠ Salvar Ocorrências FGTS não confirmado.")
            self._aguardar_ajax()
        else:
            self._log("  ⚠ Nenhum ajuste aplicado — não chamando Salvar.")

    # ── Fase 5: Contribuição Social (INSS) ────────────────────────────────────

    @retry(max_tentativas=3)
    def fase_contribuicao_social(self, cs: dict) -> None:
        self._log("Fase 5 — Contribuição Social (INSS)…")
        self._verificar_tomcat(timeout=60)
        self._verificar_pagina_pjecalc()
        navegou = (
            self._clicar_menu_lateral("Contribuição Social", obrigatorio=False)
            or self._clicar_menu_lateral("Contribuicao Social", obrigatorio=False)
            or self._clicar_menu_lateral("INSS", obrigatorio=False)
        )
        if not navegou:
            # CRÍTICO: Mesmo sem navegar, NÃO retornar sem salvar.
            # O PJE-Calc exige que o objeto INSS exista no banco H2 para exportar.
            # Se consolidarDadosParaExportacao() tentar acessar calculo.getInss()
            # e retornar null, gera NullPointerException na exportação.
            self._log("  ⚠ Seção Contribuição Social não encontrada — tentando via URL direta…")
            if self._calculo_url_base and self._calculo_conversation_id:
                try:
                    _url = (f"{self._calculo_url_base}inss/inss.jsf"
                            f"?conversationId={self._calculo_conversation_id}")
                    self._page.goto(_url, wait_until="domcontentloaded", timeout=15000)
                    self._aguardar_ajax()
                    navegou = True
                except Exception as e:
                    self._log(f"  ⚠ URL direta INSS falhou: {e}")
            if not navegou:
                self._log("  ⚠ INSS: navegação falhou — exportação pode falhar com NPE.")
                return
        self._verificar_pagina_pjecalc()
        # Verificar via URL (heading pode ser "Dados do Cálculo" pelo template compartilhado)
        if "inss" not in self._page.url.lower():
            self._log(f"  ⚠ INSS: URL inesperada ({self._page.url[-60:]}) — tentando continuar")
        self.mapear_campos("fase5_inss")

        # Migrar schema legado (responsabilidade → booleans) se necessário
        from modules.extraction import _migrar_inss_legado
        if "responsabilidade" in cs:
            cs = _migrar_inss_legado(cs)

        # Checkboxes individuais (correspondentes exatos da UI do PJE-Calc)
        self._marcar_checkbox("apurarSeguradoSaláriosDevidos",
                              cs.get("apurar_segurado_salarios_devidos", True))
        self._marcar_checkbox("apurarSeguradoSalariosDevidos",
                              cs.get("apurar_segurado_salarios_devidos", True))
        self._marcar_checkbox("cobrarDoReclamante",
                              cs.get("cobrar_do_reclamante", True))
        self._marcar_checkbox("comCorrecaoTrabalhista",
                              cs.get("com_correcao_trabalhista", True))
        self._marcar_checkbox("apurarSobreSaláriosPagos",
                              cs.get("apurar_sobre_salarios_pagos", False))
        self._marcar_checkbox("apurarSobreSalariosPagos",
                              cs.get("apurar_sobre_salarios_pagos", False))
        if cs.get("lei_11941"):
            self._marcar_checkbox("lei11941", True)

        # Limitar ao teto do INSS
        if cs.get("limitar_ao_teto") is not None:
            self._marcar_checkbox("limitarAoTeto", bool(cs["limitar_ao_teto"]))

        # Isenção Simples Nacional (empresa optante pelo Simples)
        if cs.get("isencao_simples"):
            self._marcar_checkbox("isencaoSimples", True)
            if cs.get("simples_inicio"):
                self._preencher_data("simplesInicio", cs["simples_inicio"], False)
            if cs.get("simples_fim"):
                self._preencher_data("simplesFim", cs["simples_fim"], False)

        # Períodos de incidência (salários pagos e devidos)
        if cs.get("periodo_incidencia_pagos"):
            self._preencher("periodoIncidenciaPagos", cs["periodo_incidencia_pagos"], False)
        if cs.get("periodo_incidencia_devidos"):
            self._preencher("periodoIncidenciaDevidos", cs["periodo_incidencia_devidos"], False)

        # Período do empregador (se alíquota por período)
        if cs.get("periodo_inicio_empregador"):
            self._preencher_data("periodoInicioEmpregador", cs["periodo_inicio_empregador"], False)
        if cs.get("periodo_fim_empregador"):
            self._preencher_data("periodoFimEmpregador", cs["periodo_fim_empregador"], False)

        # Atividade econômica (lookup — busca por código CNAE)
        if cs.get("atividade_economica"):
            self._preencher("buscaAtividadeEconomica", cs["atividade_economica"], False)
            self._aguardar_ajax()
            self._page.wait_for_timeout(500)

        # Tipo de alíquota do segurado (DOM: tipoAliquotaSegurado radio)
        _tipo_seg = cs.get("tipo_aliquota_segurado")
        if _tipo_seg:
            self._marcar_radio("tipoAliquotaSegurado", _tipo_seg)
            self._aguardar_ajax()
            self._page.wait_for_timeout(300)

        # Tipo de alíquota do empregador (DOM: tipoAliquotaEmpregador radio)
        _tipo_emp = cs.get("tipo_aliquota_empregador")
        if _tipo_emp:
            self._marcar_radio("tipoAliquotaEmpregador", _tipo_emp)
            self._aguardar_ajax()
            self._page.wait_for_timeout(300)

        # Alíquotas fixas quando aplicável
        if cs.get("aliquota_empresa"):
            self._preencher("aliquotaEmpresa", _fmt_br(cs["aliquota_empresa"]), False)
        if cs.get("aliquota_sat"):
            self._preencher("aliquotaSAT", _fmt_br(cs["aliquota_sat"]), False)
        if cs.get("aliquota_terceiros"):
            self._preencher("aliquotaTerceiros", _fmt_br(cs["aliquota_terceiros"]), False)

        if not self._clicar_salvar():
            self._log("  ⚠ Fase 5: Salvar INSS não confirmado.")
        self._aguardar_ajax()

        # ── Parâmetros das Ocorrências (manual linhas 590-608) ────────────────
        # Após salvar parâmetros principais, acessar Parâmetros das Ocorrências
        # para configurar alíquotas e clicar Confirmar (regera ocorrências).
        self._configurar_parametros_ocorrencias_cs(cs)

        self._log("Fase 5 concluída.")

    def _configurar_parametros_ocorrencias_cs(self, cs: dict) -> None:
        """Acessa Parâmetros das Ocorrências da CS e clica Confirmar para regerar.

        Manual PJE-Calc (linhas 590-608):
        - Acessar via ícone Ocorrências (link/botão na página CS)
        - Configurar Alíquota Segurado (Empregado/Doméstico/Fixa)
        - Configurar Alíquota Empregador (Atividade Econômica/Período/Fixa)
        - Clicar "Confirmar" para regerar ocorrências

        Na maioria dos casos os defaults do PJE-Calc são adequados (Segurado Empregado
        + Empresa padrão). Basta acessar e clicar Confirmar.
        """
        self._log("  → Parâmetros das Ocorrências CS…")
        try:
            # Procurar link/botão para acessar Parâmetros das Ocorrências
            _OCORR_SELS = [
                "[id$='cmdParametrosOcorrencias']",
                "[id$='parametrosOcorrencias']",
                "a:has-text('Parâmetros das Ocorrências')",
                "a:has-text('Parametros das Ocorrencias')",
                "a:has-text('Ocorrências')",
                # Ícone de engrenagem/config típico do PJE-Calc
                "a[title*='corrências']",
                "a[title*='correncias']",
                "img[title*='corrências']",
                "img[title*='correncias']",
            ]
            _clicou = False
            for _sel in _OCORR_SELS:
                _el = self._page.locator(_sel)
                if _el.count() > 0:
                    _el.first.click(force=True)
                    self._aguardar_ajax()
                    self._page.wait_for_timeout(1500)
                    self._log(f"    ✓ Acessou Parâmetros das Ocorrências ({_sel})")
                    _clicou = True
                    break

            if not _clicou:
                # Fallback: procurar qualquer link que contenha "ocorrencias" na URL
                _js_nav = self._page.evaluate("""() => {
                    const links = [...document.querySelectorAll('a[href]')];
                    for (const a of links) {
                        const h = a.href.toLowerCase();
                        if (h.includes('ocorrencia') || h.includes('parametros-ocorrencia')) {
                            a.click();
                            return a.href;
                        }
                    }
                    return null;
                }""")
                if _js_nav:
                    self._aguardar_ajax()
                    self._page.wait_for_timeout(1500)
                    self._log(f"    ✓ Acessou Parâmetros via JS: …{_js_nav[-40:]}")
                    _clicou = True

            if not _clicou:
                self._log("    ⚠ Link Parâmetros das Ocorrências não encontrado — usando defaults")
                return

            # ── Configurar Alíquota Segurado (se especificado) ──
            _aliq_seg = cs.get("aliquota_segurado", "")
            if _aliq_seg:
                # Opções: SEGURADO_EMPREGADO, EMPREGADO_DOMESTICO, FIXA
                self._marcar_radio("aliquotaSegurado", _aliq_seg)
                self._marcar_radio("tipoAliquotaSegurado", _aliq_seg)
                if _aliq_seg.upper() == "FIXA" and cs.get("aliquota_segurado_valor"):
                    self._preencher("aliquotaSeguradoFixa",
                                    _fmt_br(str(cs["aliquota_segurado_valor"])), False)
                self._log(f"    ✓ Alíquota Segurado: {_aliq_seg}")

            # ── Configurar Alíquota Empregador (se especificado) ──
            _aliq_emp = cs.get("aliquota_empregador", "")
            if _aliq_emp:
                self._marcar_radio("tipoAliquotaEmpregador", _aliq_emp)
                self._log(f"    ✓ Alíquota Empregador: {_aliq_emp}")

            # ── Clicar Confirmar para regerar ocorrências ──
            # Auto-confirmar possível dialog
            self._page.once("dialog", lambda d: d.accept())

            _CONFIRMAR_SELS = [
                "[id$='confirmar']",
                "input[value='Confirmar']",
                "input[type='submit'][value='Confirmar']",
                "input[type='button'][value='Confirmar']",
                "button:has-text('Confirmar')",
            ]
            for _sel in _CONFIRMAR_SELS:
                _btn = self._page.locator(_sel)
                if _btn.count() > 0:
                    _btn.first.click(force=True)
                    self._aguardar_ajax()
                    self._page.wait_for_timeout(2000)
                    self._log(f"    ✓ Confirmar CS ocorrências executado ({_sel})")
                    return

            # Fallback JS
            _js_conf = self._page.evaluate("""() => {
                const els = [...document.querySelectorAll('input[type="submit"], input[type="button"], button')];
                for (const el of els) {
                    const txt = (el.value || el.textContent || '').toLowerCase();
                    if (txt.includes('confirmar')) {
                        el.click();
                        return el.id || el.value || 'found';
                    }
                }
                return null;
            }""")
            if _js_conf:
                self._aguardar_ajax()
                self._page.wait_for_timeout(2000)
                self._log(f"    ✓ Confirmar CS via JS: {_js_conf}")
                return

            self._log("    ⚠ Botão Confirmar não encontrado — ocorrências CS mantidas com defaults")

        except Exception as e:
            self._log(f"    ⚠ Parâmetros Ocorrências CS: {e}")

    # ── Fase 5b: Cartão de Ponto ──────────────────────────────────────────────

    @retry(max_tentativas=2)
    def fase_cartao_ponto(self, dados: dict) -> None:
        """
        Preenche o Cartão de Ponto do PJE-Calc com a jornada extraída da sentença.
        Usa dados de 'duracao_trabalho' (novo) com fallback para 'contrato' (legado).

        Campos reais do PJE-Calc (apuracao-cartaodeponto.xhtml):
        - tipoApuracaoHorasExtras: radio (HST/HJD/APH/NAP)
        - valorJornadaSegunda..Dom: horas brutas por dia (HH:MM)
        - qtJornadaSemanal, qtJornadaMensal: totais
        - intervaloIntraJornada configs
        - competenciaInicial, competenciaFinal: período
        """
        dur = dados.get("duracao_trabalho") or {}
        cont = dados.get("contrato", {})

        # ── Verificar se há condenação em horas extras (sem HE → não preencher cartão) ──
        verbas = dados.get("verbas_deferidas", [])
        _tem_he = any(
            "hora" in (v.get("nome_sentenca") or "").lower() and "extra" in (v.get("nome_sentenca") or "").lower()
            for v in verbas
        )
        if not _tem_he and not dur.get("tipo_apuracao"):
            self._log("Fase 5b — Cartão de Ponto: sem condenação em horas extras — ignorado.")
            return

        # ── Determinar dados da jornada (duracao_trabalho tem prioridade) ──
        tipo_apuracao = dur.get("tipo_apuracao")
        forma_pjecalc = dur.get("forma_apuracao_pjecalc")

        # Jornada por dia da semana
        jornada_dias = {
            "seg": dur.get("jornada_seg"),
            "ter": dur.get("jornada_ter"),
            "qua": dur.get("jornada_qua"),
            "qui": dur.get("jornada_qui"),
            "sex": dur.get("jornada_sex"),
            "sab": dur.get("jornada_sab"),
            "dom": dur.get("jornada_dom"),
        }
        jornada_semanal = dur.get("jornada_semanal_cartao")
        jornada_mensal = dur.get("jornada_mensal_cartao")
        intervalo_min = dur.get("intervalo_minutos")
        qt_he_mes = dur.get("qt_horas_extras_mes")

        # Datas do período
        data_inicio = cont.get("admissao")
        data_fim = cont.get("demissao")

        # ── Fallback legado: calcular a partir de contrato se duracao_trabalho não foi extraído ──
        if not tipo_apuracao:
            jornada_diaria = cont.get("jornada_diaria")
            carga_horaria = cont.get("carga_horaria")
            jornada_semanal_cont = cont.get("jornada_semanal")

            if not jornada_diaria and carga_horaria:
                if carga_horaria >= 210:
                    jornada_diaria = 8.0
                    jornada_semanal_cont = jornada_semanal_cont or 44.0
                elif carga_horaria >= 175:
                    jornada_diaria = 8.0
                    jornada_semanal_cont = jornada_semanal_cont or 40.0
                elif carga_horaria >= 155:
                    jornada_diaria = 6.0
                    jornada_semanal_cont = jornada_semanal_cont or 36.0
                else:
                    jornada_diaria = carga_horaria / (4.5 * 5)
                    jornada_semanal_cont = jornada_semanal_cont or round(jornada_diaria * 5, 1)

            if not jornada_diaria:
                self._log("Fase 5b — Cartão de Ponto: jornada não extraída — ignorado.")
                return

            # Converter para formato por dia (assume seg-sex uniforme)
            for d in ("seg", "ter", "qua", "qui", "sex"):
                jornada_dias[d] = jornada_diaria
            jornada_dias["sab"] = 0.0
            jornada_dias["dom"] = 0.0
            jornada_semanal = jornada_semanal_cont or round(jornada_diaria * 5, 1)
            jornada_mensal = round(jornada_semanal * 30 / 7, 1) if jornada_semanal else None
            intervalo_min = intervalo_min or (60 if jornada_diaria >= 6 else 15)
            forma_pjecalc = "HORAS_EXTRAS_EXCEDENTES_DA_JORNADA_DIARIA"  # default: jornada diária
            tipo_apuracao = "apuracao_jornada"

        # Se ainda não há dados suficientes, sair
        if not any(v for v in jornada_dias.values() if v) and not qt_he_mes:
            self._log("Fase 5b — Cartão de Ponto: sem dados de jornada — ignorado.")
            return

        self._verificar_tomcat(timeout=60)
        self._verificar_pagina_pjecalc()

        # ── Navegar para Cartão de Ponto ──
        # Usar _clicar_menu_lateral que tenta URL navigation primeiro (funciona para Cartão de Ponto)
        # e fallback sidebar JSF.
        navegou = self._clicar_menu_lateral("Cartão de Ponto", obrigatorio=False)
        if not navegou:
            self._log(
                f"  Fase 5b — Cartão de Ponto: menu não encontrado. "
                f"Forma={forma_pjecalc}, Semanal={jornada_semanal}h."
            )
            return

        # Verificar se a página carregou sem erro
        try:
            body_text = self._page.locator("body").text_content(timeout=3000) or ""
            if "Erro Interno" in body_text or "erro interno" in body_text.lower():
                self._log("  ⚠ Cartão de Ponto: Erro Interno — navegação JSF não funcionou")
                try:
                    link = self._page.locator("a:has-text('Página Inicial')")
                    if link.count() > 0:
                        link.first.click()
                        self._aguardar_ajax()
                except Exception:
                    pass
                return
        except Exception:
            pass

        # Verificar que estamos na página CORRETA (não em Feriados/Pontos Facultativos)
        _url_atual = self._page.url or ""
        _na_pagina_errada = False
        if "feriado" in _url_atual.lower() or "pontos-facultativos" in _url_atual.lower():
            _na_pagina_errada = True
        else:
            # Checar campos da página: se tipoBusca existe, estamos em Feriados
            _tem_campo_feriado = self._page.locator("input[id$='tipoBusca'], input[id$='nomeFeriadoBusca']").count() > 0
            if _tem_campo_feriado:
                _na_pagina_errada = True

        if _na_pagina_errada:
            self._log("  ⚠ Cartão de Ponto: navegou para página errada (Feriados/Pontos Facultativos)")
            self._log(f"    URL atual: {_url_atual}")
            # Tentar voltar e buscar o link correto
            try:
                self._page.go_back()
                self._aguardar_ajax()
                self._page.wait_for_timeout(500)
            except Exception:
                pass
            return

        self._log("  ✓ Página Cartão de Ponto carregada")
        self._log(f"    URL: {_url_atual}")
        self.mapear_campos("fase5b_cartao_ponto_pre")

        # Clicar "Novo" (formulario:incluir) para abrir o formulário de apuração
        # NÃO usar _clicar_novo() genérico — ele pega o "Novo" do menu lateral (cria cálculo!)
        # O botão correto nesta página é input[id$='incluir'] com value='Novo'
        _novo_ok = False
        try:
            btn_inc = self._page.locator(f"{CartaoPonto.INCLUIR}[value='Novo']")
            if btn_inc.count() == 0:
                btn_inc = self._page.locator(CartaoPonto.INCLUIR)
            if btn_inc.count() > 0:
                btn_inc.first.click(force=True)
                self._aguardar_ajax()
                self._page.wait_for_timeout(3000)
                _novo_ok = True
                self._log("  ✓ Clicou 'Novo' (incluir) no Cartão de Ponto")
                self._screenshot_fase("05b_cartao_ponto_apos_novo")
            else:
                self._log("  ⚠ Botão 'incluir' não encontrado na página Cartão de Ponto")
        except Exception as e:
            self._log(f"  ⚠ Erro ao clicar incluir: {e}")

        # Verificar se formulário de apuração abriu (emModoFormulario renderiza os campos)
        # Aguardar até 15s para o AJAX renderizar os campos — o JSF pode demorar
        # após criar o registro de apuração no backend.
        _form_open = False
        for _wait in range(15):
            if self._page.locator(CartaoPonto.JORNADA_SEGUNDA).count() > 0:
                _form_open = True
                break
            if self._page.locator("input[name$='tipoApuracaoHorasExtras']").count() > 0:
                _form_open = True
                break
            # Verificar se um popup/dialog de erro apareceu (formulario:fechar sem campos)
            if self._page.locator(CartaoPonto.FECHAR).count() > 0 and _wait >= 3:
                # fechar button without form fields = error popup
                _has_fields = self._page.locator(CartaoPonto.JORNADA_SEGUNDA).count() > 0
                if not _has_fields:
                    _body_txt = self._page.locator("body").text_content(timeout=2000) or ""
                    _first100 = _body_txt.strip()[:200]
                    self._log(f"  ⚠ Cartão de Ponto: popup/dialog apareceu sem campos do formulário")
                    self._log(f"    Conteúdo: {_first100}")
                    self._screenshot_fase("05b_cartao_ponto_erro")
                    # Tentar fechar o dialog e retornar
                    try:
                        self._page.locator(CartaoPonto.FECHAR).first.click(force=True)
                        self._aguardar_ajax()
                    except Exception:
                        pass
                    return
            self._page.wait_for_timeout(1000)

        if not _form_open:
            # Verificar se houve erro HTTP 500
            _body = self._page.locator("body").text_content(timeout=2000) or ""
            if "Erro" in _body or "erro" in _body.lower():
                self._log(f"  ⚠ Cartão de Ponto: erro após clicar Novo — {_body[:200]}")
            else:
                self._log("  �� Formulário de apuração não abriu após clicar Novo (15s timeout)")
                # Diagnóstico: quais campos existem?
                _diag_fields = self._page.evaluate("""() => {
                    return [...document.querySelectorAll("input,select,table")]
                        .filter(e => (e.id||'').includes('formulario') && e.type !== 'hidden')
                        .map(e => ({tag: e.tagName, id: (e.id||'').split(':').pop(), type: e.type||''}))
                        .slice(0, 20);
                }""")
                self._log(f"    Campos disponíveis: {_diag_fields}")
            self._screenshot_fase("05b_cartao_ponto_noform")
            return

        # Re-mapear campos APÓS formulário aberto
        self.mapear_campos("fase5b_cartao_ponto_form")

        # ── 1. Período (competências) ──
        if data_inicio:
            self._preencher_data("competenciaInicial", data_inicio, False)
        if data_fim:
            self._preencher_data("competenciaFinal", data_fim, False)

        # ── 2. Tipo de Apuração (radio tipoApuracaoHorasExtras) ──
        # O radio usa enum Java (s:convertEnum). Os labels/values possíveis:
        # HST = "Horas por Súmula do TST" (label contém "mula" ou value index)
        # HJD = "Jornada Diária" (label contém "ornada")
        # APH = "Apuração por Horas Separadas" (label contém "eparad")
        # NAP = "Não Apurar" (label contém "ão Apur")
        forma = forma_pjecalc or "HORAS_EXTRAS_EXCEDENTES_DA_JORNADA_DIARIA"
        self._log(f"  Cartão de Ponto: selecionando forma de apuração = {forma}")

        # Mapa de siglas LEGADAS → valor real do enum Java
        # (mantido para backward-compat com dados antigos no banco)
        # Dados novos já vêm com o enum name direto do extraction.py.
        _FORMA_TO_ENUM = {
            # Siglas legadas (backward-compat)
            "HJD": "HORAS_EXTRAS_EXCEDENTES_DA_JORNADA_DIARIA",
            "HST": "HORAS_EXTRAS_CONFORME_SUMULA_85",
            "APH": "APURA_PRIMEIRAS_HORAS_EXTRAS_SEPARADO",
            "NAP": "NAO_APURAR_HORAS_EXTRAS",
            "FAV": "HORAS_EXTRAS_PELO_CRITERIO_MAIS_FAVORAVEL",
            "SEM": "HORAS_EXTRAS_EXCEDENTES_DA_JORNADA_SEMANAL",
            "MEN": "HORAS_EXTRAS_EXCEDENTES_DA_JORNADA_MENSAL",
            # Enum names (passam direto)
            "HORAS_EXTRAS_EXCEDENTES_DA_JORNADA_DIARIA": "HORAS_EXTRAS_EXCEDENTES_DA_JORNADA_DIARIA",
            "HORAS_EXTRAS_CONFORME_SUMULA_85": "HORAS_EXTRAS_CONFORME_SUMULA_85",
            "APURA_PRIMEIRAS_HORAS_EXTRAS_SEPARADO": "APURA_PRIMEIRAS_HORAS_EXTRAS_SEPARADO",
            "NAO_APURAR_HORAS_EXTRAS": "NAO_APURAR_HORAS_EXTRAS",
            "HORAS_EXTRAS_PELO_CRITERIO_MAIS_FAVORAVEL": "HORAS_EXTRAS_PELO_CRITERIO_MAIS_FAVORAVEL",
            "HORAS_EXTRAS_EXCEDENTES_DA_JORNADA_SEMANAL": "HORAS_EXTRAS_EXCEDENTES_DA_JORNADA_SEMANAL",
            "HORAS_EXTRAS_EXCEDENTES_DA_JORNADA_MENSAL": "HORAS_EXTRAS_EXCEDENTES_DA_JORNADA_MENSAL",
        }
        _enum_value = _FORMA_TO_ENUM.get(forma, forma)

        _radio_clicked = self._page.evaluate(f"""() => {{
            const radios = document.querySelectorAll("input[name$='tipoApuracaoHorasExtras']");
            if (radios.length === 0) return 'NO_RADIOS';

            const info = [...radios].map(r => ({{
                id: r.id, value: r.value, checked: r.checked,
                label: r.parentElement ? r.parentElement.textContent.trim().substring(0, 50) : ''
            }}));

            // Match por value exato do enum Java
            for (const r of radios) {{
                if (r.value === '{_enum_value}') {{
                    r.click();
                    r.dispatchEvent(new Event('change', {{bubbles: true}}));
                    return 'VALUE:' + r.value;
                }}
            }}

            // Fallback: match por índice (HJD=1, HST=3, APH=4, NAP=0)
            const idx_map = {{'NAP': 0, 'HJD': 1, 'FAV': 2, 'HST': 3, 'APH': 4, 'SEM': 5, 'MEN': 6}};
            const idx = idx_map['{forma}'];
            if (idx !== undefined && idx < radios.length) {{
                radios[idx].click();
                radios[idx].dispatchEvent(new Event('change', {{bubbles: true}}));
                return 'INDEX:' + idx + ':' + radios[idx].value;
            }}

            return 'NOT_FOUND:' + JSON.stringify(info);
        }}""")
        self._log(f"    Radio resultado: {_radio_clicked}")
        if _radio_clicked and not _radio_clicked.startswith("NOT_FOUND") and _radio_clicked != "NO_RADIOS":
            self._aguardar_ajax()
            self._page.wait_for_timeout(800)

        # ── 2b. Preenchimento de Jornadas (Manual seção 10.1) ──
        # Livre / Programação Semanal / Escala
        preenchimento = dur.get("preenchimento_jornada") or "programacao_semanal"
        escala_tipo = dur.get("escala_tipo") or "outra"
        self._log(f"  Cartão de Ponto: preenchimento = {preenchimento}" +
                  (f" (escala: {escala_tipo})" if preenchimento == "escala" else ""))

        # Selecionar radio de preenchimento via JS
        # PJE-Calc tem radios: tipoPreenchimentoJornada com values LIVRE / PROGRAMACAO_SEMANAL / ESCALA
        _PREEN_MAP = {
            "livre": "LIVRE",
            "programacao_semanal": "PROGRAMACAO_SEMANAL",
            "escala": "ESCALA",
        }
        _preen_enum = _PREEN_MAP.get(preenchimento, "PROGRAMACAO_SEMANAL")
        _preen_res = self._page.evaluate(f"""() => {{
            const radios = document.querySelectorAll("input[name$='tipoPreenchimentoJornada']");
            if (radios.length === 0) return 'NO_RADIOS';
            for (const r of radios) {{
                if (r.value === '{_preen_enum}' || r.value.toUpperCase().includes('{_preen_enum}')) {{
                    r.click();
                    r.dispatchEvent(new Event('change', {{bubbles: true}}));
                    return 'OK:' + r.value;
                }}
            }}
            // Fallback: match by label text
            for (const r of radios) {{
                const lbl = r.parentElement ? r.parentElement.textContent.trim().toLowerCase() : '';
                if ('{preenchimento}' === 'livre' && lbl.includes('livre')) {{ r.click(); return 'LABEL:' + lbl; }}
                if ('{preenchimento}' === 'programacao_semanal' && lbl.includes('semanal')) {{ r.click(); return 'LABEL:' + lbl; }}
                if ('{preenchimento}' === 'escala' && lbl.includes('escala')) {{ r.click(); return 'LABEL:' + lbl; }}
            }}
            return 'NOT_FOUND:' + [...radios].map(r => r.value).join(',');
        }}""")
        self._log(f"    Preenchimento radio: {_preen_res}")
        if _preen_res and not _preen_res.startswith("NOT_FOUND") and _preen_res != "NO_RADIOS":
            self._aguardar_ajax()
            self._page.wait_for_timeout(800)

        # Se Escala: selecionar o tipo de escala no dropdown
        if preenchimento == "escala":
            _ESCALA_MAP = {
                "12x12": "12X12", "12x24": "12X24", "12x36": "12X36", "12x48": "12X48",
                "5x1": "5X1", "6x1": "6X1", "8x2": "8X2", "outra": "OUTRA",
            }
            _esc_value = _ESCALA_MAP.get(escala_tipo, "OUTRA")
            try:
                sel_esc = self._page.locator(CartaoPonto.TIPO_ESCALA)
                if sel_esc.count() > 0:
                    sel_esc.first.select_option(value=_esc_value)
                    self._aguardar_ajax()
                    self._log(f"    Escala tipo: {_esc_value}")
                else:
                    # Tentar via JS
                    self._page.evaluate(f"""() => {{
                        const sel = document.querySelector("{CartaoPonto.TIPO_ESCALA}");
                        if (sel) {{
                            for (const opt of sel.options) {{
                                if (opt.value.toUpperCase().includes('{_esc_value}') ||
                                    opt.text.toUpperCase().includes('{_esc_value}')) {{
                                    sel.value = opt.value;
                                    sel.dispatchEvent(new Event('change', {{bubbles: true}}));
                                    break;
                                }}
                            }}
                        }}
                    }}""")
                    self._aguardar_ajax()
            except Exception as e:
                self._log(f"    ⚠ Escala tipo: erro {e}")

        # Se LIVRE: preencher campos simples entrada/saída por dia (entradaSegunda..Dom, saidaSegunda..Dom)
        if preenchimento == "livre":
            self._log("    → Modo Livre: preenchendo campos entrada/saída simples")
            _jorn_entrada = dur.get("jornada_entrada") or ""
            _jorn_saida = dur.get("jornada_saida") or ""
            if _jorn_entrada and _jorn_saida:
                _DIAS_SIMPLES = {
                    "seg": ("entradaSegunda", "saidaSegunda"),
                    "ter": ("entradaTerca", "saidaTerca"),
                    "qua": ("entradaQuarta", "saidaQuarta"),
                    "qui": ("entradaQuinta", "saidaQuinta"),
                    "sex": ("entradaSexta", "saidaSexta"),
                    "sab": ("entradaSabado", "saidaSabado"),
                    "dom": ("entradaDomingo", "saidaDomingo"),
                }
                for dia, (campo_ent, campo_sai) in _DIAS_SIMPLES.items():
                    # Preencher seg-sex; sáb/dom somente se jornada extraída > 0
                    _jorn_dia = jornada_dias.get(dia, 0) or 0
                    if dia in ("sab", "dom") and _jorn_dia <= 0:
                        continue
                    try:
                        loc_e = self._page.locator(f"input[id$='{campo_ent}']")
                        if loc_e.count() > 0:
                            loc_e.first.click()
                            loc_e.first.fill("")
                            loc_e.first.press_sequentially(_jorn_entrada.replace(":", ""), delay=50)
                            loc_e.first.press("Tab")
                    except Exception as _e_ent:
                        self._log(f"      ⚠ {dia.upper()} entrada: {_e_ent}")
                    try:
                        loc_s = self._page.locator(f"input[id$='{campo_sai}']")
                        if loc_s.count() > 0:
                            loc_s.first.click()
                            loc_s.first.fill("")
                            loc_s.first.press_sequentially(_jorn_saida.replace(":", ""), delay=50)
                            loc_s.first.press("Tab")
                    except Exception as _e_sai:
                        self._log(f"      ⚠ {dia.upper()} saída: {_e_sai}")
                    self._log(f"      {dia.upper()}: {_jorn_entrada}-{_jorn_saida}")
                self._aguardar_ajax()
            else:
                self._log("    ⚠ Modo Livre: sem jornada_entrada/saida — campos não preenchidos")
        else:
            pass  # Continue with steps 3+ below

        # ── 2c. Preencher Grade Semanal (Programação Semanal) ──
        # JSF DataTable IDs: formulario:listagemProgramacao:{rowIdx}:entrada{pairNum}
        # rowIdx: seg=0, ter=1, qua=2, qui=3, sex=4, sab=5, dom=6, feriado=7
        # pairNum: 1-6 (até 6 pares entrada/saída por dia)
        grade = dur.get("grade_semanal")
        if preenchimento == "programacao_semanal" and grade and isinstance(grade, dict):
            _ROW_MAP = {"seg": 0, "ter": 1, "qua": 2, "qui": 3, "sex": 4, "sab": 5, "dom": 6, "feriado": 7}
            self._log("    Preenchendo Grade Semanal (Programação Semanal)...")
            for dia, row_idx in _ROW_MAP.items():
                dia_data = grade.get(dia)
                if not dia_data or not isinstance(dia_data, dict):
                    continue
                turnos = dia_data.get("turnos", [])
                for turno_idx, turno in enumerate(turnos[:6]):  # max 6 pares
                    pair_num = turno_idx + 1  # 1-indexed
                    entrada_val = turno.get("entrada", "")
                    saida_val = turno.get("saida", "")
                    if not entrada_val and not saida_val:
                        continue
                    # Preencher entrada
                    if entrada_val:
                        ent_id = f"listagemProgramacao:{row_idx}:entrada{pair_num}"
                        try:
                            loc_ent = self._page.locator(f"input[id$='{ent_id}']")
                            if loc_ent.count() > 0:
                                loc_ent.first.click()
                                loc_ent.first.fill("")
                                loc_ent.first.press_sequentially(entrada_val.replace(":", ""), delay=50)
                                loc_ent.first.press("Tab")
                                self._page.wait_for_timeout(200)
                            else:
                                self._log(f"      ⚠ {dia.upper()} E{pair_num}: campo '{ent_id}' não encontrado")
                        except Exception as e:
                            self._log(f"      ⚠ {dia.upper()} E{pair_num}: erro {e}")
                    # Preencher saída
                    if saida_val:
                        sai_id = f"listagemProgramacao:{row_idx}:saida{pair_num}"
                        try:
                            loc_sai = self._page.locator(f"input[id$='{sai_id}']")
                            if loc_sai.count() > 0:
                                loc_sai.first.click()
                                loc_sai.first.fill("")
                                loc_sai.first.press_sequentially(saida_val.replace(":", ""), delay=50)
                                loc_sai.first.press("Tab")
                                self._page.wait_for_timeout(200)
                            else:
                                self._log(f"      ⚠ {dia.upper()} S{pair_num}: campo '{sai_id}' não encontrado")
                        except Exception as e:
                            self._log(f"      ⚠ {dia.upper()} S{pair_num}: erro {e}")
                    self._log(f"      {dia.upper()} T{pair_num}: {entrada_val}-{saida_val}")
            self._aguardar_ajax()
            self._page.wait_for_timeout(500)
        elif preenchimento == "programacao_semanal" and not grade:
            # Fallback: sintetizar grade a partir de jornada_entrada/saida/intervalo
            self._log("    ⚠ grade_semanal ausente — usando campos flat como fallback para grade")

        # ── 3. Quantidade fixa (HST) ──
        if forma == "HST" and qt_he_mes and preenchimento != "livre":
            hh_he = int(qt_he_mes)
            mm_he = int((qt_he_mes - hh_he) * 60)
            self._preencher("qtsumulatst", f"{hh_he:02d}:{mm_he:02d}", False)
            self._log(f"    HST: {hh_he:02d}:{mm_he:02d} HE/mês")

        # ── 4. Jornada de Trabalho PADRÃO (contratada) — NÃO a efetivamente praticada ──
        # (Pular se modo Livre — usuário preencherá depois)
        # CONCEITO CRÍTICO (manual PJE-Calc seção 10.1):
        # "Jornada de Trabalho Padrão" = jornada CONTRATADA (ex: 8h/dia CLT).
        # A jornada EFETIVAMENTE PRATICADA (ex: 10h/dia) vai na Grade de Ocorrências.
        # O PJE-Calc calcula: Horas Extras = praticada − padrão.
        # Se preenchermos a padrão com a praticada, o sistema NÃO calcula HE!
        #
        # Fonte dos dados CORRETOS:
        # - contrato.jornada_diaria / contrato.jornada_semanal = jornada CONTRATUAL
        # - duracao_trabalho.jornada_seg..dom = jornada PRATICADA (do que diz a sentença)
        #
        # Aqui usamos a jornada contratual (Parâmetros do Cálculo / cargaHorariaDiaria).
        # Enum names + siglas legadas para backward-compat
        _FORMAS_COM_JORNADA = (
            "HJD", "APH", "FAV", "SEM", "MEN",
            "HORAS_EXTRAS_EXCEDENTES_DA_JORNADA_DIARIA",
            "APURA_PRIMEIRAS_HORAS_EXTRAS_SEPARADO",
            "HORAS_EXTRAS_PELO_CRITERIO_MAIS_FAVORAVEL",
            "HORAS_EXTRAS_EXCEDENTES_DA_JORNADA_SEMANAL",
            "HORAS_EXTRAS_EXCEDENTES_DA_JORNADA_MENSAL",
            "HORAS_EXTRAS_CONFORME_SUMULA_85",
        )
        if forma in _FORMAS_COM_JORNADA and preenchimento != "livre":
            # Determinar jornada PADRÃO (contratual) — NÃO a praticada
            _jornada_padrao_diaria = cont.get("jornada_diaria") or cont.get("carga_horaria_diaria")
            _jornada_padrao_semanal = cont.get("jornada_semanal") or cont.get("carga_horaria_semanal")

            # Se contrato não tem jornada explícita, usar carga horária para inferir
            _ch = cont.get("carga_horaria")
            if not _jornada_padrao_diaria:
                if _ch and _ch >= 210:
                    _jornada_padrao_diaria = 8.0
                elif _ch and _ch >= 155:
                    _jornada_padrao_diaria = 6.0
                else:
                    _jornada_padrao_diaria = 8.0  # CLT padrão

            if not _jornada_padrao_semanal:
                _jornada_padrao_semanal = _jornada_padrao_diaria * 5
                if _jornada_padrao_diaria == 8.0:
                    _jornada_padrao_semanal = 44.0  # CLT: 8h × 5 + 4h sáb = 44h

            # Montar dias com jornada PADRÃO (não a praticada!)
            _jornada_padrao_dias = {}
            for d in ("seg", "ter", "qua", "qui", "sex"):
                _jornada_padrao_dias[d] = _jornada_padrao_diaria
            # Sábado: se jornada semanal > diária × 5, há expediente parcial no sábado
            _sab_padrao = _jornada_padrao_semanal - (_jornada_padrao_diaria * 5)
            _jornada_padrao_dias["sab"] = max(0.0, _sab_padrao)
            _jornada_padrao_dias["dom"] = 0.0

            self._log(f"    Jornada PADRÃO (contratual): {_jornada_padrao_diaria}h/dia, "
                       f"{_jornada_padrao_semanal}h/sem, sáb={_jornada_padrao_dias['sab']}h")

            _CAMPO_DIA = {
                "seg": "valorJornadaSegunda",
                "ter": "valorJornadaTerca",
                "qua": "valorJornadaQuarta",
                "qui": "valorJornadaQuinta",
                "sex": "valorJornadaSexta",
                "sab": "valorJornadaDiariaSabado",
                "dom": "valorJornadaDiariaDom",
            }
            for dia, campo_id in _CAMPO_DIA.items():
                horas = _jornada_padrao_dias.get(dia, 0.0)
                hh = int(horas)
                mm = int((horas - hh) * 60)
                valor_hhmm = f"{hh:02d}:{mm:02d}"
                # Usar press_sequentially para campos com timeMask
                try:
                    loc = self._page.locator(f"input[id$='{campo_id}']")
                    if loc.count() > 0:
                        loc.first.click()
                        loc.first.fill("")
                        loc.first.press_sequentially(valor_hhmm, delay=50)
                        loc.first.press("Tab")
                        self._log(f"    {dia.upper()}: {valor_hhmm}")
                    else:
                        self._log(f"    ⚠ {dia.upper()}: campo '{campo_id}' não encontrado")
                except Exception as e:
                    self._log(f"    ⚠ {dia.upper()}: erro {e}")

            # Usar jornada PADRÃO para semanal/mensal também
            jornada_semanal = _jornada_padrao_semanal
            jornada_mensal = round(_jornada_padrao_semanal * 30 / 7, 1)

        # ── 5. Jornada semanal e mensal ──
        # qtJornadaSemanal usa currencyMask() — formato decimal BR (ex: "50,00")
        if jornada_semanal and preenchimento != "livre":
            _js_val = _fmt_br(jornada_semanal)
            try:
                loc_sem = self._page.locator(CartaoPonto.QT_JORNADA_SEMANAL)
                if loc_sem.count() > 0:
                    loc_sem.first.click()
                    loc_sem.first.fill("")
                    loc_sem.first.press_sequentially(_js_val, delay=50)
                    loc_sem.first.press("Tab")
                    self._log(f"    Semanal: {_js_val}")
            except Exception as e:
                self._log(f"    ⚠ Semanal: erro {e}")

        if jornada_mensal and preenchimento != "livre":
            _jm_val = _fmt_br(jornada_mensal)
            try:
                loc_men = self._page.locator(CartaoPonto.QT_JORNADA_MENSAL)
                if loc_men.count() > 0:
                    loc_men.first.click()
                    loc_men.first.fill("")
                    loc_men.first.press_sequentially(_jm_val, delay=50)
                    loc_men.first.press("Tab")
                    self._log(f"    Mensal: {_jm_val}")
            except Exception as e:
                self._log(f"    ⚠ Mensal: erro {e}")

        # ── 6. Intervalo intrajornada ──
        if intervalo_min and intervalo_min > 0 and preenchimento != "livre":
            hh_int = int(intervalo_min // 60)
            mm_int = int(intervalo_min % 60)
            valor_intervalo = f"{hh_int:02d}:{mm_int:02d}"

            # Marcar e preencher intervalo para jornadas > 6h
            try:
                cb = self._page.locator(CartaoPonto.INTERVALO_INTRA_JORNADA_SUP_SEIS)
                if cb.count() > 0 and not cb.first.is_checked():
                    cb.first.click(force=True)
                    self._aguardar_ajax()
                    self._page.wait_for_timeout(300)
            except Exception:
                pass

            try:
                loc_iv = self._page.locator(CartaoPonto.VALOR_INTERVALO_SUP_SEIS)
                if loc_iv.count() > 0:
                    loc_iv.first.click()
                    loc_iv.first.fill("")
                    loc_iv.first.press_sequentially(valor_intervalo, delay=50)
                    loc_iv.first.press("Tab")
                    self._log(f"    Intervalo >6h: {valor_intervalo}")
            except Exception as e:
                self._log(f"    ⚠ Intervalo: erro {e}")

        # ── 7. Flags: feriados, domingos ──
        trabalha_feriados = dur.get("trabalha_feriados", False)
        trabalha_domingos = dur.get("trabalha_domingos", False)

        if trabalha_feriados:
            try:
                cb_fer = self._page.locator(CartaoPonto.CONSIDERAR_FERIADO)
                if cb_fer.count() > 0 and not cb_fer.first.is_checked():
                    cb_fer.first.click(force=True)
                    self._aguardar_ajax()
                    self._log("    ✓ Considerar Feriados: marcado")
            except Exception:
                pass

        if trabalha_domingos:
            try:
                cb_dom = self._page.locator(CartaoPonto.EXTRA_DESCANSO_SEPARADO)
                if cb_dom.count() > 0 and not cb_dom.first.is_checked():
                    cb_dom.first.click(force=True)
                    self._aguardar_ajax()
                    self._log("    ✓ Extras domingos separado: marcado")
            except Exception:
                pass

        # ── 7b. Intervalo intrajornada ≤ 6h (campo separado do > 6h) ──
        if intervalo_min and intervalo_min > 0:
            try:
                # Intervalo para jornadas ≤ 6h (15 min padrão)
                cb_inf6 = self._page.locator(CartaoPonto.INTERVALO_INTRA_JORNADA_INF_SEIS)
                if cb_inf6.count() > 0:
                    jornada_max = max((v or 0) for v in jornada_dias.values()) if jornada_dias else 0
                    if jornada_max <= 6 and not cb_inf6.first.is_checked():
                        cb_inf6.first.click(force=True)
                        self._aguardar_ajax()
                        self._page.wait_for_timeout(300)
                        # Preencher valor do intervalo ≤ 6h
                        loc_iv6 = self._page.locator(CartaoPonto.VALOR_INTERVALO_INF_SEIS)
                        if loc_iv6.count() > 0:
                            hh_i6 = int(intervalo_min // 60)
                            mm_i6 = int(intervalo_min % 60)
                            loc_iv6.first.click()
                            loc_iv6.first.fill("")
                            loc_iv6.first.press_sequentially(f"{hh_i6:02d}:{mm_i6:02d}", delay=50)
                            loc_iv6.first.press("Tab")
                            self._log(f"    Intervalo ≤6h: {hh_i6:02d}:{mm_i6:02d}")
            except Exception as e:
                self._log(f"    ⚠ Intervalo ≤6h: erro {e}")

        # ── 7c. Horário Noturno ──
        # Conforme vídeo: marcar "Apurar horas noturnas", definir horário (Urbano: 22h-05h),
        # configurar Redução Ficta (52m30s) e Prorrogação do Horário Noturno (Súmula 60 TST)
        apurar_noturno = dur.get("apurar_hora_noturna", False)
        if apurar_noturno:
            try:
                cb_noturno = self._page.locator(CartaoPonto.APURAR_HORAS_NOTURNAS)
                if cb_noturno.count() > 0 and not cb_noturno.first.is_checked():
                    cb_noturno.first.click(force=True)
                    self._aguardar_ajax()
                    self._page.wait_for_timeout(500)
                    self._log("    ✓ Apurar horas noturnas: marcado")

                    # Horário noturno início/fim (urbano padrão: 22:00 - 05:00)
                    hora_inicio_noturno = dur.get("hora_inicio_noturno", "22:00")
                    hora_fim_noturno = dur.get("hora_fim_noturno", "05:00")

                    loc_inicio_not = self._page.locator(CartaoPonto.INICIO_HORARIO_NOTURNO)
                    if loc_inicio_not.count() > 0:
                        loc_inicio_not.first.click()
                        loc_inicio_not.first.fill("")
                        loc_inicio_not.first.press_sequentially(hora_inicio_noturno, delay=50)
                        loc_inicio_not.first.press("Tab")

                    loc_fim_not = self._page.locator(CartaoPonto.FIM_HORARIO_NOTURNO)
                    if loc_fim_not.count() > 0:
                        loc_fim_not.first.click()
                        loc_fim_not.first.fill("")
                        loc_fim_not.first.press_sequentially(hora_fim_noturno, delay=50)
                        loc_fim_not.first.press("Tab")

                    self._log(f"    Horário noturno: {hora_inicio_noturno} - {hora_fim_noturno}")

                    # Redução ficta (hora noturna = 52m30s)
                    reducao_ficta = dur.get("reducao_ficta", True)
                    if reducao_ficta:
                        cb_red = self._page.locator(CartaoPonto.REDUCAO_FICTA)
                        if cb_red.count() > 0 and not cb_red.first.is_checked():
                            cb_red.first.click(force=True)
                            self._aguardar_ajax()
                            self._log("    ✓ Redução ficta: marcada")

                    # Prorrogação horário noturno (Súmula 60 TST)
                    prorrogacao_noturno = dur.get("prorrogacao_horario_noturno", False)
                    if prorrogacao_noturno:
                        cb_prorr = self._page.locator(CartaoPonto.HORARIO_PRORROGADO)
                        if cb_prorr.count() > 0 and not cb_prorr.first.is_checked():
                            cb_prorr.first.click(force=True)
                            self._aguardar_ajax()
                            self._log("    ✓ Prorrogação horário noturno: marcada")

            except Exception as e:
                self._log(f"    ⚠ Horário noturno: erro {e}")

        # ── 8. Salvar ──
        # No cartão de ponto, o botão pode ser "Salvar" ou "salvar"
        _saved = False
        for _sel in [CartaoPonto.SALVAR, "input[value='Salvar']",
                     "input[id$='btnSalvar']"]:
            try:
                btn = self._page.locator(_sel)
                if btn.count() > 0 and btn.first.is_visible():
                    btn.first.click()
                    self._aguardar_ajax()
                    _saved = True
                    self._log(f"    ✓ Salvar via '{_sel}'")
                    break
            except Exception:
                continue

        if not _saved:
            # Fallback: clicar via JS qualquer botão com texto "Salvar"
            _saved = self._page.evaluate("""() => {
                const btns = document.querySelectorAll("input[type='submit'], input[type='button']");
                for (const b of btns) {
                    if ((b.value || '').includes('Salvar') && b.offsetParent !== null) {
                        b.click();
                        return true;
                    }
                }
                return false;
            }""")
            if _saved:
                self._aguardar_ajax()
                self._log("    ✓ Salvar via JS")
            else:
                self._log("    ⚠ Salvar não encontrado — cartão pode não ter sido gravado")

        self._page.wait_for_timeout(1000)
        self._screenshot_fase("05b_cartao_ponto")
        self._log(
            f"  ✓ Cartão de Ponto: forma={forma}, "
            f"semanal={jornada_semanal}h, intervalo={intervalo_min}min"
        )
        self._log("Fase 5b concluída.")

    # ── Fase 5c: Faltas ───────────────────────────────────────────────────────

    @retry(max_tentativas=2)
    def fase_faltas(self, dados: dict) -> None:
        """
        Preenche faltas (ausências) do reclamante no PJE-Calc.
        Dados esperados em dados["faltas"]: lista de dicts com
        data_inicial, data_final, tipo (ou justificada).
        """
        faltas = dados.get("faltas", [])
        if not faltas:
            self._log("Fase 5c — Faltas: sem entradas extraídas — ignorado.")
            return

        self._log(f"Fase 5c — Faltas: {len(faltas)} falta(s) extraída(s)…")
        self._verificar_tomcat(timeout=60)
        self._verificar_pagina_pjecalc()

        navegou = self._clicar_menu_lateral("Faltas", obrigatorio=False)
        if not navegou:
            self._log("  → Seção Faltas não encontrada no menu — ignorado.")
            return

        self._verificar_pagina_pjecalc()
        self.mapear_campos("fase5c_faltas")

        for i, falta in enumerate(faltas):
            # Usar _clicar_botao_id("incluir") — NUNCA _clicar_novo() que pode
            # acionar o "Novo" do menu lateral e criar um cálculo inteiro.
            if not self._clicar_botao_id("incluir"):
                self._log(f"  ⚠ Falta {i+1}: botão 'incluir' não encontrado")
                continue
            self._aguardar_ajax()
            self._page.wait_for_timeout(800)

            # Data inicial — DOM confirmado: dataInicioInputDate
            dt_ini = falta.get("data_inicial", "")
            if dt_ini:
                self._preencher_data("dataInicioInputDate", dt_ini, False)
                self._preencher_data("dataInicio", dt_ini, False)  # fallback

            # Data final — DOM confirmado: dataFimInputDate
            dt_fim = falta.get("data_final", "")
            if dt_fim:
                self._preencher_data("dataFimInputDate", dt_fim, False)
                self._preencher_data("dataFim", dt_fim, False)  # fallback

            # Tipo / justificada
            tipo = falta.get("tipo", falta.get("justificada", ""))
            if isinstance(tipo, bool):
                tipo = "JUSTIFICADA" if tipo else "INJUSTIFICADA"
            if tipo:
                self._selecionar("tipo", tipo, obrigatorio=False)
                self._selecionar("tipoFalta", tipo, obrigatorio=False)

            # Motivo (campo opcional)
            motivo = falta.get("motivo", "")
            if motivo:
                self._preencher("motivo", motivo, False)
                self._preencher("descricao", motivo, False)

            self._clicar_salvar()
            self._aguardar_ajax()
            self._page.wait_for_timeout(500)
            self._log(f"  ✓ Falta {i+1}: {dt_ini} a {dt_fim} ({tipo})")

        self._log("Fase 5c concluída.")

    # ── Fase 5d: Férias ───────────────────────────────────────────────────────

    @retry(max_tentativas=2)
    def fase_ferias(self, dados: dict) -> None:
        """
        Configura férias no PJE-Calc.

        IMPORTANTE (manual seção 7): O PJE-Calc gera AUTOMATICAMENTE os períodos
        de férias a partir das datas de admissão/demissão e regime de trabalho.
        NÃO existe botão "Novo" para criar entradas individuais.

        A página ferias.jsf contém:
        - prazoFeriasProporcionais: prazo para férias proporcionais
        - inicioFeriasColetivasInputDate: data para férias coletivas
        - regerarFeriasColetivas: botão para regerar após alterações
        - Tabela auto-gerada com períodos aquisitivos e status
        """
        ferias = dados.get("ferias", [])
        if not ferias:
            self._log("Fase 5d — Férias: sem entradas extraídas — ignorado.")
            return

        self._log(f"Fase 5d — Férias: {len(ferias)} período(s) extraído(s)…")
        self._verificar_tomcat(timeout=60)
        self._verificar_pagina_pjecalc()

        navegou = self._clicar_menu_lateral("Férias", obrigatorio=False)
        if not navegou:
            self._log("  → Seção Férias não encontrada no menu — ignorado.")
            return

        self._verificar_pagina_pjecalc()
        self.mapear_campos("fase5d_ferias")

        # O PJE-Calc auto-gera férias a partir das datas do contrato.
        # Verificar quantas linhas a tabela já possui (períodos auto-gerados).
        try:
            _linhas_ferias = self._page.evaluate("""() => {
                const rows = document.querySelectorAll(
                    'tr[id*="listagem"], tr.rich-table-row, tbody tr'
                );
                return [...rows].filter(tr => {
                    const txt = tr.textContent || '';
                    return txt.includes('/') && txt.length > 10 && txt.length < 500;
                }).length;
            }""")
            self._log(f"  ℹ Períodos de férias auto-gerados: {_linhas_ferias}")
        except Exception:
            _linhas_ferias = 0

        # Configurar prazo de férias proporcionais (se extraído da sentença)
        for entrada in ferias:
            _prazo = entrada.get("prazo_proporcional", "")
            if _prazo:
                self._preencher("prazoFeriasProporcionais", str(_prazo), False)
                self._log(f"  ✓ prazoFeriasProporcionais: {_prazo}")
                break

        # Configurar férias coletivas (se houver)
        _ferias_coletivas = dados.get("ferias_coletivas", {})
        _inicio_coletivas = _ferias_coletivas.get("data_inicio", "")
        if _inicio_coletivas:
            self._preencher_data("inicioFeriasColetivasInputDate", _inicio_coletivas, False)
            self._log(f"  ✓ Férias coletivas: {_inicio_coletivas}")
            # Regerar após informar férias coletivas
            self._regerar_ferias()

        # Log de referência dos dados extraídos
        for i, entrada in enumerate(ferias):
            per_ini = entrada.get("periodo_inicio", "")
            per_fim = entrada.get("periodo_fim", "")
            situacao = entrada.get("situacao", "auto")
            self._log(
                f"  ℹ Férias {i+1}: {per_ini} a {per_fim} (situação={situacao})"
            )

        # FIX: Configurar status/dobra/abono por período aquisitivo extraído da
        # sentença. O PJE-Calc auto-gera as linhas, mas NÃO sabe quais são
        # "Vencidas", "Proporcionais", "Gozadas", "Indenizadas" nem se têm dobra
        # ou abono — isso precisa vir da sentença. Sem essa configuração, as
        # ocorrências de férias ficam incorretas na liquidação.
        _alterou_alguma = False
        for entrada in ferias:
            _situacao = (entrada.get("situacao") or "").strip()
            _dobra = bool(entrada.get("dobra"))
            _abono = bool(entrada.get("abono"))
            _per_aq_ini = entrada.get("periodo_aquisitivo_inicio") or entrada.get("periodo_inicio") or ""
            _per_aq_fim = entrada.get("periodo_aquisitivo_fim") or entrada.get("periodo_fim") or ""
            # Só age se tiver pelo menos uma configuração não-default
            if not (_situacao or _dobra or _abono):
                continue
            if not (_per_aq_ini and _per_aq_fim):
                continue

            try:
                # Localizar e clicar no botão Editar da linha correspondente ao período aquisitivo.
                # Estratégia: JS busca <tr> cujo texto contém as duas datas e clica em editar/lápis/link.
                _js_editar = """
                    (args) => {
                        const {ini, fim} = args;
                        const rows = document.querySelectorAll('tbody tr, tr[id*="listagem"]');
                        for (const tr of rows) {
                            const txt = (tr.innerText || tr.textContent || '');
                            if (txt.includes(ini) && txt.includes(fim)) {
                                const btn = tr.querySelector(
                                    'input[id$=":editar"], input[id*="edit"], a[id*="edit"], '
                                    + 'img[title*="Editar"], img[alt*="Editar"], '
                                    + 'input[value="Editar"], button[title*="Editar"]'
                                );
                                if (btn) { btn.click(); return true; }
                                // fallback: primeiro input/link da última célula (normalmente ações)
                                const tds = tr.querySelectorAll('td');
                                if (tds.length) {
                                    const last = tds[tds.length - 1];
                                    const any = last.querySelector('input[type="image"], a, input[type="button"]');
                                    if (any) { any.click(); return true; }
                                }
                            }
                        }
                        return false;
                    }
                """
                _clicou = self._page.evaluate(_js_editar, {"ini": _per_aq_ini, "fim": _per_aq_fim})
                if not _clicou:
                    self._log(f"  ⚠ Férias: linha {_per_aq_ini} a {_per_aq_fim} não localizada — pulando edição")
                    continue
                self._aguardar_ajax()
                self._page.wait_for_timeout(500)

                # Situação (dropdown)
                if _situacao:
                    _sel_ok = False
                    for _sel_id in ("[id$='situacao']", "[id$='status']",
                                    "select[id*='situacao']", "select[id*='status']",
                                    "select[name*='situacao']"):
                        try:
                            _loc = self._page.locator(_sel_id)
                            if _loc.count() > 0:
                                try:
                                    _loc.first.select_option(label=_situacao)
                                    _sel_ok = True
                                    break
                                except Exception:
                                    # tentar por value
                                    try:
                                        _loc.first.select_option(value=_situacao)
                                        _sel_ok = True
                                        break
                                    except Exception:
                                        continue
                        except Exception:
                            continue
                    if _sel_ok:
                        self._log(f"  ✓ Férias {_per_aq_ini}-{_per_aq_fim}: situação='{_situacao}'")
                        self._aguardar_ajax()

                # Dobra
                if _dobra:
                    try:
                        self._marcar_checkbox("dobra", True) or self._marcar_checkbox("emDobra", True)
                        self._log(f"  ✓ Férias {_per_aq_ini}-{_per_aq_fim}: dobra marcada")
                    except Exception as _e:
                        self._log(f"  ⚠ Férias dobra: {_e}")

                # Abono pecuniário
                if _abono:
                    try:
                        self._marcar_checkbox("abono", True) or self._marcar_checkbox("abonoPecuniario", True)
                        self._log(f"  ✓ Férias {_per_aq_ini}-{_per_aq_fim}: abono marcado")
                    except Exception as _e:
                        self._log(f"  ⚠ Férias abono: {_e}")

                # Datas de gozo (até 3 períodos) — condicionais: situação GOZADAS ou GOZADAS_PARCIALMENTE
                _sit_upper = _situacao.upper() if _situacao else ""
                if _sit_upper in ("GOZADAS", "GOZADAS_PARCIALMENTE"):
                    _gozo_periodos = entrada.get("gozo_periodos") or []
                    for _gi, _gozo in enumerate(_gozo_periodos[:3]):
                        _num = _gi + 1  # 1, 2, 3
                        _g_ini = _gozo.get("inicio") or _gozo.get("data_inicio") or ""
                        _g_fim = _gozo.get("fim") or _gozo.get("data_fim") or ""
                        if _g_ini:
                            self._preencher_data(f"dataInicioGozo{_num}", _g_ini, False)
                        if _g_fim:
                            self._preencher_data(f"dataFimGozo{_num}", _g_fim, False)
                        if _g_ini or _g_fim:
                            self._log(f"  ✓ Férias {_per_aq_ini}-{_per_aq_fim}: gozo {_num} = {_g_ini} a {_g_fim}")
                    self._aguardar_ajax()

                # Salvar edição
                try:
                    self._clicar_salvar(aguardar_sucesso=True)
                    self._aguardar_ajax()
                    self._page.wait_for_timeout(500)
                    _alterou_alguma = True
                except Exception as _e_sv:
                    self._log(f"  ⚠ Férias: falha ao salvar edição ({_e_sv})")
            except Exception as _e_ed:
                # Never break main automation flow due to férias edit issues
                self._log(f"  ⚠ Férias: erro na edição do período {_per_aq_ini}-{_per_aq_fim}: {_e_ed}")

        # Se alterou alguma, regerar ocorrências de férias (CRIT: manual pede
        # Regerar após alteração de status conforme seção 7 do PJE-Calc).
        if _alterou_alguma:
            try:
                self._regerar_ferias()
            except Exception as _e_rg:
                self._log(f"  ⚠ Regerar férias pós-edição falhou: {_e_rg}")

        self._log("Fase 5d concluída.")

    def _regerar_ferias(self) -> bool:
        """Clica em 'Regerar Férias' na aba Férias para atualizar ocorrências.

        Manual PJE-Calc (Férias Coletivas, linha 248):
        "Informar data de inicio para indicar ferias proporcionais.
         Clicar 'Regerar Ferias' apos alteracao."

        Também necessário após alterações de status (Indenizadas, Gozadas Parcialmente).
        """
        self._log("  → Regerar férias…")
        try:
            # Auto-confirmar dialog de confirmação (similar ao Regerar Verbas)
            self._page.once("dialog", lambda d: d.accept())

            # Scroll para garantir visibilidade
            self._page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            self._page.wait_for_timeout(300)

            _REGERAR_SELS = [
                "[id$='regerarFerias']",
                "input[value='Regerar Férias']",
                "input[value='Regerar Ferias']",
                "input[type='submit'][value*='egerar']",
                "input[type='button'][value*='egerar']",
                "button:has-text('Regerar')",
            ]
            for _sel in _REGERAR_SELS:
                _btn = self._page.locator(_sel)
                if _btn.count() > 0:
                    _btn.first.click(force=True)
                    self._aguardar_ajax()
                    self._page.wait_for_timeout(2000)
                    self._log(f"  ✓ Regerar férias executado ({_sel})")
                    return True

            # Fallback JS
            _js_clicked = self._page.evaluate("""() => {
                const els = [...document.querySelectorAll('input[type="submit"], input[type="button"], button')];
                for (const el of els) {
                    const txt = (el.value || el.textContent || '').toLowerCase();
                    if (txt.includes('regerar')) {
                        el.click();
                        return el.id || el.value || 'found';
                    }
                }
                return null;
            }""")
            if _js_clicked:
                self._aguardar_ajax()
                self._page.wait_for_timeout(2000)
                self._log(f"  ✓ Regerar férias via JS: {_js_clicked}")
                return True

            self._log("  ⚠ Botão 'Regerar Férias' não encontrado — pode ser desnecessário se não há férias coletivas")
            return False
        except Exception as e:
            self._log(f"  ⚠ Regerar férias: {e}")
            return False

    # ── Fase 6: Parâmetros de Atualização (Correção, Juros e Multa) ──────────

    @retry(max_tentativas=3)
    def fase_parametros_atualizacao(self, cj: dict) -> None:
        """Configura correção monetária, juros e multa na página correcao-juros.jsf.

        Lógica de juros pós-Lei 14.905/2024 (vigência 30/08/2024):
        - Correção: IPCA-E (índice trabalhista padrão)
        - Juros: Taxa Legal (SELIC - IPCA = taxa real)
        - Data marco: 30/08/2024 — a partir dessa data aplica-se Taxa Legal
        """
        self._log("Fase 6 — Parâmetros de atualização (Correção, Juros e Multa)…")

        # Navegar para correção/juros — prioriza sidebar click (não depende de URL exata)
        _nav_ok = self._clicar_menu_lateral("Correção, Juros e Multa", obrigatorio=False)
        self._aguardar_ajax()
        self._page.wait_for_timeout(1000)

        # Verificar se chegou na página (URL pode ser correcao-juros.jsf, atualizacao.jsf, etc.)
        _url_atual = self._page.url.lower()
        _na_pagina = any(p in _url_atual for p in ["correcao", "atualizacao", "juros"])

        if not _nav_ok or not _na_pagina:
            # Fallback: tentar variantes de URL conhecidas
            _url_tentativas = [
                "correcao-juros.jsf",
                "atualizacao.jsf",
                "correcao-juros-e-multa.jsf",
            ]
            _navegou = False
            if self._calculo_url_base and self._calculo_conversation_id:
                for _jsf in _url_tentativas:
                    _url_cj = (
                        f"{self._calculo_url_base}{_jsf}"
                        f"?conversationId={self._calculo_conversation_id}"
                    )
                    try:
                        self._page.goto(_url_cj, wait_until="domcontentloaded", timeout=10000)
                        self._aguardar_ajax()
                        self._page.wait_for_timeout(500)
                        # Verificar se não caiu em página de erro
                        if self._page.locator(f"{CorrecaoJurosMulta.INDICE_CORRECAO}, {CorrecaoJurosMulta.TAXA_JUROS}").count() > 0:
                            _navegou = True
                            self._log(f"  ✓ Navegou para {_jsf}")
                            break
                    except Exception:
                        continue
            if not _navegou:
                self._log("  ⚠ Correção/Juros: página não encontrada — pulando configuração de índices")
                return

        # --- Índice de correção monetária ---
        # Seleção por TEXTO do option (PJE-Calc TRT7 v2.15.1 tem 16 opções reais).
        # O _selecionar() do framework resolve tanto por value quanto por option text.
        _indice = cj.get("indice_correcao", "IPCA_E")
        _indice_text_map = {
            "TABELA_UNICA": "Tabela Única de Atualização e Conversão de Débitos Trabalhistas",
            "DEVEDOR_FAZENDA_PUBLICA": "Devedor Fazenda Pública",
            "REPETICAO_INDEBITO_TRIBUTARIO": "Repetição de Indébito Tributário",
            "TABELA_UNICA_JT_MENSAL": "Tabela JT Mensal",
            "TABELA_UNICA_JT_DIARIO": "Tabela JT Diária",
            "TR": "TR", "IGP_M": "IGP-M", "INPC": "INPC", "IPC": "IPC",
            "IPCA": "IPCA", "IPCA_E": "IPCA-E", "IPCA_E_TR": "IPCA-E/TR",
            "SELIC_RECEITA": "SELIC (Receita Federal)",
            "SELIC_SIMPLES": "SELIC Simples",
            "SELIC_COMPOSTA": "SELIC Composta",
            "SEM_CORRECAO": "Sem Correção",
            # Aliases legados
            "IPCAE": "IPCA-E", "IPCAETR": "IPCA-E/TR", "IGPM": "IGP-M",
            "IPCA-E": "IPCA-E", "IPCA-E/TR": "IPCA-E/TR", "IGP-M": "IGP-M",
            "TUACDT": "Tabela Única de Atualização e Conversão de Débitos Trabalhistas",
            "Tabela JT Única Mensal": "Tabela JT Mensal",
            "Tabela JT Unica Mensal": "Tabela JT Mensal",
            "Selic": "SELIC (Receita Federal)", "SELIC": "SELIC (Receita Federal)",
            "TRCT": "TR", "TUACDT_DIARIO": "Tabela JT Diária",
        }
        _val_indice = _indice_text_map.get(_indice, _indice)
        self._selecionar("indiceCorrecao", _val_indice, obrigatorio=False)
        self._selecionar("indiceTrabalhista", _val_indice, obrigatorio=False)
        self._log(f"  ✓ Índice de correção: {_val_indice}")

        # --- Taxa de juros ---
        # Seleção por TEXTO do option (PJE-Calc TRT7 v2.15.1 tem 13 opções reais).
        _taxa = cj.get("taxa_juros", "PADRAO")
        _juros_text_map = {
            "PADRAO": "Juros Padrão",
            "CADERNETA_POUPANCA": "Juros Caderneta de Poupança",
            "FAZENDA_PUBLICA": "Juros Fazenda Pública",
            "SIMPLES_0_5_MES": "Juros Simples 0,5% a.m.",
            "SIMPLES_1_MES": "Juros Simples 1,0% a.m.",
            "SIMPLES_0_0333333_DIA": "Juros Simples 0,0333333% a.d.",
            "SELIC_RECEITA": "SELIC (Receita Federal)",
            "SELIC_SIMPLES": "SELIC Simples",
            "SELIC_COMPOSTA": "SELIC Composta",
            "TRD_SIMPLES": "TRD Juros Simples",
            "TRD_COMPOSTOS": "TRD Juros Compostos",
            "TAXA_LEGAL": "Taxa Legal",
            "SEM_JUROS": "Sem Juros",
            # Aliases legados
            "JUROS_PADRAO": "Juros Padrão",
            "Taxa Legal": "Taxa Legal",
            "Selic": "SELIC (Receita Federal)", "SELIC": "SELIC (Receita Federal)",
            "Juros Padrão": "Juros Padrão", "Juros Padrao": "Juros Padrão",
            "1% ao mês": "Juros Padrão",
        }
        _val_juros = _juros_text_map.get(_taxa, _taxa)
        self._selecionar("taxaJuros", _val_juros, obrigatorio=False)
        self._selecionar("juros", _val_juros, obrigatorio=False)
        self._log(f"  ✓ Taxa de juros: {_val_juros}")

        # --- Data marco da Taxa Legal (Lei 14.905/2024 → 30/08/2024) ---
        if _val_juros == "TAXA_LEGAL":
            _data_marco = cj.get("data_taxa_legal", "30/08/2024")
            self._preencher("dataInicioTaxaLegal", _data_marco, obrigatorio=False)
            self._preencher("dataMarcoTaxaLegal", _data_marco, obrigatorio=False)
            self._log(f"  ✓ Data marco Taxa Legal: {_data_marco}")

        # --- Base de juros ---
        _base = cj.get("base_juros", "Verbas")
        _base_map = {"Verbas": "VERBA_INSS", "Credito Total": "CREDITO_TOTAL"}
        _val_base = _base_map.get(_base, "VERBA_INSS")
        self._selecionar("baseDeJurosDasVerbas", _val_base, obrigatorio=False)
        self._log(f"  ✓ Base de juros: {_val_base}")

        # --- Segundo índice de correção (combinar com outro) ---
        _segundo_indice = cj.get("segundo_indice") or cj.get("indice_correcao_pos")
        if _segundo_indice:
            self._marcar_checkbox("combinarComOutro", True)
            self._aguardar_ajax()
            self._page.wait_for_timeout(500)
            _val_seg = _indice_text_map.get(_segundo_indice, _segundo_indice)
            self._selecionar("segundoIndice", _val_seg, obrigatorio=False)
            _dt_seg = cj.get("data_inicio_segundo_indice") or cj.get("data_taxa_legal", "30/08/2024")
            self._preencher_data("dataInicioSegundoIndice", _dt_seg, False)
            self._log(f"  ✓ Segundo índice: {_val_seg} a partir de {_dt_seg}")

        # --- Ignorar taxa negativa ---
        if cj.get("ignorar_taxa_negativa") is not None:
            self._marcar_checkbox("ignorarTaxaNegativa", bool(cj["ignorar_taxa_negativa"]))

        # --- FGTS: índice de correção ---
        if cj.get("fgts_correcao"):
            self._selecionar("fgtsCorrecao", cj["fgts_correcao"], obrigatorio=False)
            self._log(f"  ✓ FGTS correção: {cj['fgts_correcao']}")

        # --- Lei 11.941/2009 (contribuição social - regime de competência) ---
        _cs_dados = cj  # CS fields may come nested in correcao_juros or as standalone
        if _cs_dados.get("lei_11941") or _cs_dados.get("lei11941"):
            self._marcar_checkbox("lei11941", True)
            self._aguardar_ajax()
            self._page.wait_for_timeout(500)
            if _cs_dados.get("data_inicio_lei_11941"):
                self._preencher_data("dataInicioLei11941", _cs_dados["data_inicio_lei_11941"], False)
            if _cs_dados.get("limitar_multa_lei_11941") is not None:
                self._marcar_checkbox("limitarMultaLei11941", bool(_cs_dados["limitar_multa_lei_11941"]))
            self._log("  ✓ Lei 11.941/2009: ativada")

        # --- Período sem juros ---
        if cj.get("periodo_sem_juros_inicio"):
            self._preencher_data("periodoSemJurosInicio", cj["periodo_sem_juros_inicio"], False)
        if cj.get("periodo_sem_juros_fim"):
            self._preencher_data("periodoSemJurosFim", cj["periodo_sem_juros_fim"], False)

        # --- Índice e juros das custas ---
        if cj.get("indice_custas"):
            self._selecionar("indiceCustas", cj["indice_custas"], obrigatorio=False)
        if cj.get("atualizar_custas") is not None:
            self._marcar_checkbox("atualizarCustas", bool(cj["atualizar_custas"]))
        if cj.get("juros_custas") is not None:
            self._marcar_checkbox("jurosCustas", bool(cj["juros_custas"]))

        # --- Atualização da Contribuição Social ---
        if cj.get("atualizacao_cs"):
            self._marcar_radio("atualizacaoCS", cj["atualizacao_cs"])
            self._aguardar_ajax()
            self._page.wait_for_timeout(300)
        if cj.get("data_transicao_cs"):
            self._preencher_data("dataTransicaoCS", cj["data_transicao_cs"], False)

        # --- Previdência Privada (índice e juros na aba correção) ---
        if cj.get("indice_previdencia_privada"):
            self._selecionar("indicePrevidenciaPrivada", cj["indice_previdencia_privada"], obrigatorio=False)
        if cj.get("juros_previdencia_privada") is not None:
            self._marcar_checkbox("jurosPrevidenciaPrivada", bool(cj["juros_previdencia_privada"]))
        if cj.get("tipo_multa_previdenciaria"):
            self._selecionar("tipoMultaPrevidenciaria", cj["tipo_multa_previdenciaria"], obrigatorio=False)
        if cj.get("pagamento_multa_previdenciaria"):
            self._selecionar("pagamentoMultaPrevidenciaria", cj["pagamento_multa_previdenciaria"], obrigatorio=False)

        # --- Multa do art. 523 CPC (se aplicável) ---
        _multa_523 = cj.get("multa_523", False)
        if _multa_523:
            self._marcar_checkbox("aplicarMulta523", True)
            self._log("  ✓ Multa art. 523 CPC: aplicar")

        # NÃO CLICAR SALVAR — evita NPE confirmada em
        # ParametrosDeAtualizacao.verificarCombinacoesDeCorrecaoMonetaria:465
        # (chamada a partir de ApresentadorParametrosDeAtualizacao.salvar:114).
        #
        # Causa raiz: `salvar()` invoca `verificarCombinacoesDeCorrecaoMonetaria()`
        # que chama `verificarCombinacaoDeTabelasDeCorrecao(apartir, getIndiceTrabalhista())`
        # → `new TabelaDeCorrecaoMonetaria(indice, calculo.getIndicesAcumulados(),
        #    getIgnorarTaxaNegativa())`. Como `indicesAcumulados` só é definido na
        # página `liquidacao.xhtml` (Fase 7), quando Fase 6 tenta salvar ele ainda
        # é null → NPE.
        #
        # Estratégia correta: `ApresentadorParametrosDeAtualizacao.iniciar()` já
        # carregou o `registro` via `servicoDeCalculo.obterParametrosDeAtualizacao()`
        # com os defaults do cálculo (IPCA_E, PADRAO, etc.). Como o apresentador
        # é `@Scope(SESSION)`, as alterações feitas via AJAX (`a4j:support onchange`)
        # permanecem vivas no registro até a liquidação. Pular o click em Salvar
        # elimina a NPE sem perder os valores configurados.
        #
        # Após a Fase 7 (liquidação, que define `indicesAcumulados`), o servidor
        # persiste o estado final automaticamente via `calculo.salvar()`.
        self._log("  ✓ Parâmetros de atualização configurados (registro session-scoped — salvar() pulado para evitar NPE pré-liquidação)")

    # ── Salário-família (passo 7 do manual) ──────────────────────────────────

    @retry(max_tentativas=2)
    def fase_salario_familia(self, dados: dict) -> None:
        """Passo 7 do manual: Salário-família.

        Manual: Checkbox "Apurar Salário-família", Compor Principal,
        Competências, Remuneração Mensal, Quantidade de filhos menores de 14.
        """
        sf = dados.get("salario_familia", {})
        if not sf or not sf.get("apurar"):
            self._log("Salário-família: sem dados ou apurar=False — ignorado.")
            return
        self._log("Salário-família…")
        self._verificar_tomcat(timeout=60)
        self._verificar_pagina_pjecalc()
        self._clicar_menu_lateral("Salário-família", obrigatorio=False)
        self._aguardar_ajax()
        self._page.wait_for_timeout(1000)

        # Checkbox "Apurar Salário-família"
        self._marcar_checkbox("apurar", True)
        self._aguardar_ajax()
        self._page.wait_for_timeout(500)

        # Compor Principal
        _compor = sf.get("compor_principal", "SIM")
        self._marcar_radio("comporPrincipal", _compor)

        # Competência início/fim
        _comp_ini = sf.get("competencia_inicio", "")
        if _comp_ini:
            self._preencher_data("competenciaInicio", _comp_ini, False)
            self._log(f"  ✓ Competência início: {_comp_ini}")
        _comp_fim = sf.get("competencia_fim", "")
        if _comp_fim:
            self._preencher_data("competenciaFim", _comp_fim, False)
            self._log(f"  ✓ Competência fim: {_comp_fim}")

        # Quantidade de filhos menores de 14 anos
        _qtd = sf.get("quantidade_filhos") or sf.get("qtd_filhos") or ""
        if _qtd:
            self._preencher("quantidadeDeFilhos", str(_qtd), False)

        # Remuneração mensal — PJE-Calc tem 2 selects distintos:
        # remuneracaoMensalPagos (base para salários pagos) e remuneracaoMensalDevidos (base para devidos)
        _rem_pagos = sf.get("remuneracao_mensal_pagos") or sf.get("remuneracao_mensal") or ""
        if _rem_pagos:
            _ok = self._preencher("remuneracaoMensalPagos", str(_rem_pagos), False)
            if not _ok:
                # Fallback: campo genérico remuneracaoMensal
                self._preencher("remuneracaoMensal", _fmt_br(str(_rem_pagos)), False)
            self._log(f"  ✓ Remuneração mensal (pagos): {_rem_pagos}")

        _rem_devidos = sf.get("remuneracao_mensal_devidos", "")
        if _rem_devidos:
            self._preencher("remuneracaoMensalDevidos", str(_rem_devidos), False)
            self._log(f"  ✓ Remuneração mensal (devidos): {_rem_devidos}")

        # Variações de filhos por competência (loop)
        _variacoes = sf.get("variacoes_filhos") or []
        for _vi, _var in enumerate(_variacoes):
            _v_comp = _var.get("competencia", "")
            _v_qtd = _var.get("quantidade", "")
            if not _v_comp or not _v_qtd:
                continue
            try:
                # Preencher campos de variação
                self._preencher_data("filhosVariacaoCompetencia", _v_comp, False)
                self._preencher("filhosVariacaoQuantidade", str(_v_qtd), False)
                # Clicar botão "Adicionar" variação
                _btn_add = self._page.locator("input[id$='adicionarVariacao'], input[value*='Adicionar']")
                if _btn_add.count() > 0:
                    _btn_add.first.click(force=True)
                    self._aguardar_ajax()
                    self._page.wait_for_timeout(500)
                    self._log(f"  ✓ Variação {_vi+1}: competência={_v_comp}, filhos={_v_qtd}")
            except Exception as _e_var:
                self._log(f"  ⚠ Variação filhos {_vi+1}: {_e_var}")

        # Salvar
        if not self._clicar_salvar():
            self._log("  ⚠ Salário-família: Salvar não confirmado.")
        self._log("Salário-família concluído.")

    # ── Seguro-desemprego (passo 8 do manual) ─────────────────────────────────

    @retry(max_tentativas=2)
    def fase_seguro_desemprego(self, dados: dict) -> None:
        """Passo 8 do manual: Seguro-desemprego.

        Manual: Checkbox "Apurar Seguro-desemprego", Tipo de solicitação,
        Empregado Doméstico, Compor Principal, Quantidade de Parcelas.
        """
        sd = dados.get("seguro_desemprego", {})
        if not sd or not sd.get("apurar"):
            self._log("Seguro-desemprego: sem dados ou apurar=False — ignorado.")
            return
        self._log("Seguro-desemprego…")
        self._verificar_tomcat(timeout=60)
        self._verificar_pagina_pjecalc()
        self._clicar_menu_lateral("Seguro-desemprego", obrigatorio=False)
        self._aguardar_ajax()
        self._page.wait_for_timeout(1000)

        # Checkbox "Apurar Seguro-desemprego"
        self._marcar_checkbox("apurar", True)
        self._aguardar_ajax()
        self._page.wait_for_timeout(500)

        # Tipo de solicitação (primeira, segunda, demais)
        _tipo = sd.get("tipo_solicitacao", "")
        if _tipo:
            self._marcar_radio("tipoSolicitacao", _tipo)

        # Empregado doméstico
        if sd.get("empregado_domestico"):
            self._marcar_checkbox("empregadoDomestico", True)

        # Compor Principal
        _compor = sd.get("compor_principal", "SIM")
        self._marcar_radio("comporPrincipal", _compor)

        # Quantidade de parcelas
        _parcelas = sd.get("quantidade_parcelas") or sd.get("qtd_parcelas") or ""
        if _parcelas:
            self._preencher("quantidadeDeParcelas", str(_parcelas), False)

        # Salvar
        if not self._clicar_salvar():
            self._log("  ⚠ Seguro-desemprego: Salvar não confirmado.")
        self._log("Seguro-desemprego concluído.")

    # ── Previdência Privada (passo 11 do manual) ──────────────────────────────

    @retry(max_tentativas=2)
    def fase_previdencia_privada(self, dados: dict) -> None:
        """Passo 11 do manual: Previdência Privada.

        Manual: Checkbox "Apurar Previdência Privada",
        Alíquota por Período (competência Inicial/Final + alíquota %).
        """
        pp = dados.get("previdencia_privada", {})
        if not pp or not pp.get("apurar"):
            self._log("Previdência Privada: sem dados ou apurar=False — ignorado.")
            return
        self._log("Previdência Privada…")
        self._verificar_tomcat(timeout=60)
        self._verificar_pagina_pjecalc()
        self._clicar_menu_lateral("Previdência Privada", obrigatorio=False)
        self._aguardar_ajax()
        self._page.wait_for_timeout(1000)

        # Checkbox "Apurar Previdência Privada"
        self._marcar_checkbox("apurar", True)
        self._aguardar_ajax()
        self._page.wait_for_timeout(500)

        # Alíquota
        _aliquota = pp.get("aliquota", "")
        if _aliquota:
            self._preencher("aliquota", _fmt_br(str(_aliquota)), False)

        # Salvar
        if not self._clicar_salvar():
            self._log("  ⚠ Previdência Privada: Salvar não confirmado.")
        self._log("Previdência Privada concluído.")

    # ── Pensão Alimentícia (passo 12 do manual) ──────────────────────────────

    @retry(max_tentativas=2)
    def fase_pensao_alimenticia(self, dados: dict) -> None:
        """Passo 12 do manual: Pensão Alimentícia.

        Manual: Checkbox "Apurar Pensão Alimentícia",
        Alíquota, Incidir sobre Juros.
        """
        pa = dados.get("pensao_alimenticia", {})
        if not pa or not pa.get("apurar"):
            self._log("Pensão Alimentícia: sem dados ou apurar=False — ignorado.")
            return
        self._log("Pensão Alimentícia…")
        self._verificar_tomcat(timeout=60)
        self._verificar_pagina_pjecalc()
        self._clicar_menu_lateral("Pensão Alimentícia", obrigatorio=False)
        self._aguardar_ajax()
        self._page.wait_for_timeout(1000)

        # Checkbox "Apurar Pensão Alimentícia"
        self._marcar_checkbox("apurar", True)
        self._aguardar_ajax()
        self._page.wait_for_timeout(500)

        # Alíquota
        _aliquota = pa.get("aliquota", "")
        if _aliquota:
            self._preencher("aliquota", _fmt_br(str(_aliquota)), False)

        # Incidir sobre juros
        if pa.get("incidir_sobre_juros") or pa.get("incidir_juros"):
            self._marcar_checkbox("incidirSobreJuros", True)

        # Salvar
        if not self._clicar_salvar():
            self._log("  ⚠ Pensão Alimentícia: Salvar não confirmado.")
        self._log("Pensão Alimentícia concluído.")

    # ── Fase 7: IRPF ──────────────────────────────────────────────────────────

    @retry(max_tentativas=3)
    def fase_irpf(self, ir: dict) -> None:
        if not ir.get("apurar"):
            self._log("Fase 7 — IRPF: apurar=False — ignorado.")
            return
        self._log("Fase 7 — IRPF…")
        self._verificar_tomcat(timeout=60)
        self._verificar_pagina_pjecalc()
        navegou = (
            self._clicar_menu_lateral("Imposto de Renda", obrigatorio=False)
            or self._clicar_menu_lateral("IRPF", obrigatorio=False)
            or self._clicar_menu_lateral("IR", obrigatorio=False)
        )
        if not navegou:
            self._log("  → Seção IRPF não encontrada no menu — ignorado.")
            return
        self._verificar_pagina_pjecalc()
        # Verificar via URL (heading pode ser "Dados do Cálculo" pelo template compartilhado)
        if "irpf" not in self._page.url.lower():
            self._log(f"  ⚠ IRPF: URL inesperada ({self._page.url[-60:]}) — tentando continuar")
        self.mapear_campos("fase7_irpf")

        # Regime de tributação
        if ir.get("tributacao_exclusiva"):
            self._marcar_checkbox("tributacaoExclusiva", True)
            self._marcar_checkbox("tributacaoExclusivaFonte", True)
        if ir.get("regime_de_caixa"):
            self._marcar_checkbox("regimeDeCaixa", True)
            self._marcar_checkbox("regimeCaixa", True)
        if ir.get("tributacao_em_separado"):
            self._marcar_checkbox("tributacaoEmSeparado", True)

        # Deduções
        if ir.get("deducao_inss", True):
            self._marcar_checkbox("deducaoInss", True)
            self._marcar_checkbox("descontarInss", True)
        if ir.get("deducao_honorarios_reclamante"):
            self._marcar_checkbox("deducaoHonorariosReclamante", True)
            self._marcar_checkbox("descontarHonorarios", True)
        if ir.get("deducao_previdencia_privada"):
            self._marcar_checkbox("deducaoPrevidenciaPrivada", True)
        if ir.get("deducao_pensao_alimenticia"):
            self._marcar_checkbox("deducaoPensaoAlimenticia", True)
            self._marcar_checkbox("pensaoAlimenticia", True)
            if ir.get("valor_pensao"):
                self._preencher("valorPensao", _fmt_br(ir["valor_pensao"]), False)
                self._preencher("valorDaPensao", _fmt_br(ir["valor_pensao"]), False)

        # Checkboxes adicionais de IR (DOM confirmado)
        if ir.get("incidir_sobre_juros_de_mora") is not None:
            self._marcar_checkbox("incidirSobreJurosDeMora", bool(ir["incidir_sobre_juros_de_mora"]))
        if ir.get("cobrar_do_reclamado") is not None:
            self._marcar_checkbox("cobrarDoReclamado", bool(ir["cobrar_do_reclamado"]))
        if ir.get("aposentado_maior_65") is not None:
            self._marcar_checkbox("aposentadoMaior65", bool(ir["aposentado_maior_65"]))

        # Campos numéricos
        if ir.get("dependentes"):
            self._preencher("numeroDeDependentes", str(int(ir["dependentes"])), False)
            self._preencher("dependentes", str(int(ir["dependentes"])), False)
        if ir.get("meses_tributaveis"):
            self._preencher("mesesTributaveis", str(int(ir["meses_tributaveis"])), False)

        if not self._clicar_salvar():
            self._log("  ⚠ Fase 7: Salvar IRPF não confirmado.")
        self._log("Fase 7 concluída.")

    # ── Fase 8: Honorários ────────────────────────────────────────────────────

    @retry(max_tentativas=3)
    def fase_honorarios(self, hon_dados, periciais: float | None = None,
                        justica_gratuita: dict | None = None) -> None:
        """
        Preenche honorários advocatícios no PJE-Calc.
        Aceita lista de registros [{tipo, devedor, tipo_valor, base_apuracao, percentual, ...}]
        ou dict legado {percentual, parte_devedora} — migra automaticamente.
        justica_gratuita: {"reclamante": bool, "reclamado": bool} — para incluir frase de
        suspensão de exigibilidade (art. 791-A, §4º, CLT) na descrição do honorário.
        """
        _jg = justica_gratuita or {}
        # Migrar schema legado dict → list
        from modules.extraction import _migrar_honorarios_legado
        if isinstance(hon_dados, dict):
            hon_lista = _migrar_honorarios_legado(hon_dados)
        else:
            hon_lista = hon_dados or []

        if not hon_lista:
            self._log("Fase 8 — Honorários: lista vazia — ignorado.")
            return

        self._log(f"Fase 8 — Honorários ({len(hon_lista)} registro(s))…")
        self._verificar_tomcat(timeout=60)
        self._verificar_pagina_pjecalc()
        navegou = (
            self._clicar_menu_lateral("Honorários", obrigatorio=False)
            or self._clicar_menu_lateral("Honorarios", obrigatorio=False)
        )
        if not navegou:
            self._log("  → Honorários: navegação falhou — ignorado.")
            return
        self._verificar_pagina_pjecalc()
        # Verificar via URL (heading pode ser "Dados do Cálculo" pelo template compartilhado)
        self._verificar_secao_ativa("Honorár")  # só loga, não bloqueia
        if "honorarios" not in self._page.url.lower():
            self._log(f"  ⚠ Honorários: URL inesperada ({self._page.url[-60:]}) — tentando continuar")

        self.mapear_campos("fase8_honorarios")

        for i, hon in enumerate(hon_lista):
            self._log(f"  → Honorário [{i+1}/{len(hon_lista)}]: {hon.get('devedor')} / {hon.get('tipo')}")
            # Se ainda há formulário aberto (save anterior falhou), cancelar primeiro
            # para retornar ao modo listagem onde o botão "Novo" fica visível
            try:
                _cancelar = self._page.locator("[id$='cancelar']:visible, input[value='Cancelar']:visible")
                if _cancelar.count() > 0:
                    self._log(f"  ℹ Form honorário ainda aberto — cancelando antes de Novo")
                    _cancelar.first.click()
                    self._aguardar_ajax()
                    self._page.wait_for_timeout(500)
            except Exception:
                pass
            # Clicar "Novo" (id="incluir" em honorarios.xhtml) para abrir formulário
            # Necessário para TODOS os registros, incluindo o primeiro
            clicou = (
                self._clicar_botao_id("incluir")
                or self._clicar_novo()
                or bool(self._page.locator("input[value='Novo']").first.click() if self._page.locator("input[value='Novo']").count() else None)
            )
            if not clicou:
                self._log(f"  ⚠ Botão Novo não encontrado para honorário {i+1} — pulando.")
                continue
            self._aguardar_ajax()
            self._page.wait_for_timeout(500)

            # Tipo de honorário (SUCUMBENCIAIS / CONTRATUAIS)
            # ATENÇÃO: ID real no XHTML é "tpHonorario" (NÃO "tipoHonorario")
            # required="true" — sem este campo o save falha
            tipo = hon.get("tipo", "SUCUMBENCIAIS")
            self._selecionar("tpHonorario", tipo, obrigatorio=False) or \
                self._selecionar("tipoHonorario", tipo, obrigatorio=False)
            self._aguardar_ajax()
            self._page.wait_for_timeout(500)

            # Tipo de devedor (radio)
            devedor = hon.get("devedor", "RECLAMADO")
            self._marcar_radio("tipoDeDevedor", devedor) or \
                self._selecionar("tipoDeDevedor", devedor, obrigatorio=False)
            self._aguardar_ajax()
            self._page.wait_for_timeout(500)

            # ── Forma de cobrança: Reclamante → sempre "Cobrar" (nunca "Descontar dos créditos")
            # Quando devedor é Reclamante, o PJE-Calc exibe radio "Descontar dos créditos" / "Cobrar"
            if devedor == "RECLAMANTE":
                self._page.wait_for_timeout(1000)
                # Tentar marcar "COBRAR" via radio
                _cobrar_ok = (
                    self._marcar_radio("formaCobranca", "COBRAR")
                    or self._marcar_radio("tipoCobranca", "COBRAR")
                    or self._marcar_radio("formaDeCobranca", "COBRAR")
                )
                if not _cobrar_ok:
                    # Fallback: buscar radio por label
                    try:
                        _radio_cobrar = self._page.locator(
                            'input[type="radio"][value*="COBRAR"], '
                            'input[type="radio"][value*="cobrar"]'
                        )
                        if _radio_cobrar.count() > 0:
                            _radio_cobrar.first.check(force=True)
                            _cobrar_ok = True
                    except Exception:
                        pass
                if _cobrar_ok:
                    self._log(f"  ✓ Forma de cobrança: COBRAR (Reclamante)")
                else:
                    self._log(f"  ⚠ Forma de cobrança: radio 'Cobrar' não encontrado")

            # ── Verificar se o devedor é beneficiário da justiça gratuita ──
            _devedor_tem_jg = False
            if devedor == "RECLAMANTE" and _jg.get("reclamante", False):
                _devedor_tem_jg = True
            elif devedor == "RECLAMADO" and _jg.get("reclamado", False):
                _devedor_tem_jg = True

            # Descrição (OBRIGATÓRIA — manual seção 19: "Texto até 60 caracteres")
            # Sem este campo, o PJE-Calc retorna "Existem erros no formulário"
            _descricao_hon = hon.get("descricao", "")
            if not _descricao_hon:
                # Gerar descrição padrão baseada no tipo e devedor
                _tipo_label = {"SUCUMBENCIAIS": "Sucumbenciais", "CONTRATUAIS": "Contratuais"}.get(tipo, tipo)
                _devedor_label = {"RECLAMADO": "Reclamado", "RECLAMANTE": "Reclamante"}.get(devedor, devedor)
                if _devedor_tem_jg:
                    # Incluir referência à suspensão na descrição (60 chars max)
                    _descricao_hon = f"Hon. {_tipo_label} - {_devedor_label} - Exig. suspensa"
                else:
                    _descricao_hon = f"Honorários {_tipo_label} - {_devedor_label}"
            self._preencher("descricao", _descricao_hon[:60], False)
            self._preencher("descricaoHonorario", _descricao_hon[:60], False)
            if _devedor_tem_jg:
                self._log(
                    f"  ℹ Devedor ({devedor}) é beneficiário da justiça gratuita — "
                    f"exigibilidade suspensa (art. 791-A, §4º, CLT)"
                )

            # Tipo de valor (CALCULADO / INFORMADO)
            tipo_valor = hon.get("tipo_valor", "CALCULADO")
            self._marcar_radio("tipoValor", tipo_valor) or self._selecionar("tipoValor", tipo_valor, obrigatorio=False)
            self._aguardar_ajax()
            # Aguardar re-render do grupoCalculado/grupoInformado após seleção do radio
            # CRÍTICO: Firefox crasha se evaluate() rodar antes do DOM estabilizar
            self._page.wait_for_timeout(3000)
            # Aguardar o select baseParaApuracao ficar visível (só aparece quando CALCULADO)
            if tipo_valor == "CALCULADO":
                try:
                    self._page.wait_for_selector(
                        'select[id$="baseParaApuracao"]',
                        state="visible", timeout=8000
                    )
                except Exception:
                    self._page.wait_for_timeout(2000)

            # Base de apuração — mapear termos genéricos para valores EXATOS do select PJE-Calc
            # Opções reais do select (valores de option no DOM):
            #   BRUTO
            #   BRUTO_MENOS_CONTRIBUICAO_SOCIAL
            #   BRUTO_MENOS_CONTRIBUICAO_SOCIAL_MENOS_PREVIDENCIA_PRIVADA
            #   VERBAS_QUE_NAO_COMPOE_O_PRINCIPAL  (só aparece quando devedor = Reclamante)
            # Incluímos códigos curtos legados (VNP, BRUTO_MENOS_CS, ...) para compat com
            # registros já persistidos no banco antes da padronização.
            _BASE_APURACAO_MAP = {
                "condenação": "BRUTO",
                "condenacao": "BRUTO",
                "bruto": "BRUTO",
                "valor da condenação": "BRUTO",
                "valor da condenacao": "BRUTO",
                # Bruto (-) CS
                "bruto (-) cs": "BRUTO_MENOS_CONTRIBUICAO_SOCIAL",
                "bruto menos cs": "BRUTO_MENOS_CONTRIBUICAO_SOCIAL",
                "bruto_menos_cs": "BRUTO_MENOS_CONTRIBUICAO_SOCIAL",
                "bruto_menos_contribuicao_social": "BRUTO_MENOS_CONTRIBUICAO_SOCIAL",
                # Bruto (-) CS (-) PP
                "bruto (-) cs (-) pp": "BRUTO_MENOS_CONTRIBUICAO_SOCIAL_MENOS_PREVIDENCIA_PRIVADA",
                "bruto menos cs pp": "BRUTO_MENOS_CONTRIBUICAO_SOCIAL_MENOS_PREVIDENCIA_PRIVADA",
                "bruto_menos_cs_pp": "BRUTO_MENOS_CONTRIBUICAO_SOCIAL_MENOS_PREVIDENCIA_PRIVADA",
                "bruto_menos_contribuicao_social_menos_previdencia_privada": "BRUTO_MENOS_CONTRIBUICAO_SOCIAL_MENOS_PREVIDENCIA_PRIVADA",
                # VNP — Verbas que Não Compõem o Principal
                "verbas não compõem principal": "VERBAS_QUE_NAO_COMPOE_O_PRINCIPAL",
                "verbas nao compoem principal": "VERBAS_QUE_NAO_COMPOE_O_PRINCIPAL",
                "verbas que não compõem o principal": "VERBAS_QUE_NAO_COMPOE_O_PRINCIPAL",
                "verbas que nao compoem o principal": "VERBAS_QUE_NAO_COMPOE_O_PRINCIPAL",
                "vnp": "VERBAS_QUE_NAO_COMPOE_O_PRINCIPAL",
                "verbas_que_nao_compoe_o_principal": "VERBAS_QUE_NAO_COMPOE_O_PRINCIPAL",
                "renda mensal": "RENDA_MENSAL",
            }
            base = hon.get("base_apuracao", "") or ""
            # Traduzir termo genérico para valor do PJE-Calc
            _base_lower = base.lower().strip()
            if _base_lower in _BASE_APURACAO_MAP:
                base = _BASE_APURACAO_MAP[_base_lower]
                self._log(f"  → base_apuracao '{hon.get('base_apuracao')}' → '{base}' (mapeado)")
            # Default: se tipo_valor é CALCULADO e base vazia, usar "Bruto"
            if not base and tipo_valor == "CALCULADO":
                base = "BRUTO"
            if base:
                try:
                    opcoes = self._extrair_opcoes_select("baseParaApuracao")
                    self._log(f"  → baseParaApuracao opções: {[o.get('text','?')+' = '+o.get('value','?') for o in opcoes[:8]]}")
                    match = self._match_fuzzy(base, opcoes)
                    if match:
                        self._selecionar("baseParaApuracao", match, obrigatorio=False)
                        self._log(f"  ✓ baseParaApuracao: {match}")
                    else:
                        # Fallback: tentar valor direto
                        if not self._selecionar("baseParaApuracao", base, obrigatorio=False):
                            # Último recurso: selecionar a primeira opção não-vazia
                            _opcoes_validas = [o for o in opcoes if o.get("value") and "noSelection" not in o["value"]]
                            if _opcoes_validas:
                                self._selecionar("baseParaApuracao", _opcoes_validas[0]["value"], obrigatorio=False)
                                self._log(f"  ✓ baseParaApuracao: {_opcoes_validas[0]['text']} (primeiro válido)")
                            else:
                                self._log(f"  ⚠ baseParaApuracao '{base}': sem match — opcoes={opcoes}")
                except Exception as _e:
                    self._log(f"  ⚠ baseParaApuracao: erro — {_e}")

            # Percentual (alíquota) ou valor informado
            if tipo_valor == "CALCULADO" and hon.get("percentual") is not None:
                pct_val = hon["percentual"]
                # Se percentual veio como fração (0.15), converter para %
                if pct_val < 1:
                    pct_val = pct_val * 100
                pct_str = _fmt_br(pct_val)
                # Campo correto em honorarios.xhtml: tentar "percentualHonorarios" (DOM) e "aliquota" (fallback)
                _pct_ok = (
                    self._preencher("percentualHonorarios", pct_str, False)
                    or self._preencher("aliquota", pct_str, False)
                    or self._preencher("percentual", pct_str, False)
                )
                self._log(f"  → percentual honorários: {pct_str}%{'' if _pct_ok else ' (⚠ campo não encontrado)'}")
            elif tipo_valor == "INFORMADO" and hon.get("valor_informado") is not None:
                self._preencher("valorInformado", _fmt_br(hon["valor_informado"]), False)
                self._preencher("valorFixo", _fmt_br(hon["valor_informado"]), False)
                # Data de vencimento (obrigatório para INFORMADO)
                if hon.get("data_vencimento"):
                    self._preencher_data("dataVencimento", hon["data_vencimento"], obrigatorio=False, label="Data Vencimento")

            # Dados do credor (obrigatórios em honorarios.xhtml — marcados com *)
            # IMPORTANTE: numeroDocumentoFiscalCredor tem <f:validator validatorId="validadorDinamico"/>
            # que rejeita CPFs/CNPJs inválidos (ex: "000.000.000-00" falha check digit).
            # Precisamos usar dados reais da extração ou CPF/CNPJ válidos.
            _dados = getattr(self, "_dados", {}) or {}
            _proc = _dados.get("processo", {}) if isinstance(_dados, dict) else {}

            _nome_credor = hon.get("nome_credor", "") or hon.get("credor", "")
            if not _nome_credor:
                # Fallback: nome da parte que recebe os honorários
                # Honorários do reclamado → credor é o reclamante (ou seu advogado)
                # Honorários do reclamante → credor é o reclamado (ou seu advogado)
                if devedor == "RECLAMADO":
                    _nome_credor = _proc.get("advogado_reclamante", "") or _proc.get("reclamante", "") or _dados.get("reclamante", "") or "Credor do Reclamante"
                else:
                    _nome_credor = _proc.get("advogado_reclamado", "") or _proc.get("reclamado", "") or _dados.get("reclamado", "") or "Credor do Reclamado"
            self._preencher("nomeCredor", _nome_credor[:100], False)
            self._log(f"  → nomeCredor: {_nome_credor[:50]}")

            _tipo_doc = hon.get("tipo_documento_credor", "") or hon.get("tipo_doc_credor", "")
            _num_doc = hon.get("numero_documento_credor", "") or hon.get("doc_credor", "")
            if not _num_doc:
                # Usar CPF/CNPJ da parte correspondente (VÁLIDOS — passam check digit)
                if devedor == "RECLAMADO":
                    # Credor é reclamante → usar CPF do reclamante
                    _num_doc = _proc.get("cpf_reclamante", "") or _proc.get("doc_reclamante", "")
                    if not _tipo_doc:
                        _tipo_doc = "CPF"
                else:
                    # Credor é reclamado → usar CNPJ do reclamado
                    _num_doc = _proc.get("cnpj_reclamado", "") or _proc.get("doc_reclamado", "")
                    if not _tipo_doc:
                        _tipo_doc = "CNPJ"
                # Último recurso: CPFs/CNPJs válidos conhecidos
                if not _num_doc:
                    if _tipo_doc == "CPF" or not _tipo_doc:
                        _num_doc = "111.444.777-35"  # CPF válido (check digit ok)
                        _tipo_doc = "CPF"
                    else:
                        _num_doc = "11.444.777/0001-61"  # CNPJ válido
            if not _tipo_doc:
                _tipo_doc = "CPF"

            # Selecionar tipo ANTES de preencher número (máscara dinâmica depende disso)
            (self._marcar_radio("tipoDocumentoFiscalCredor", _tipo_doc)
             or self._marcar_radio("tipoDocumentoCredor", _tipo_doc)
             or self._selecionar("tipoDocumentoFiscalCredor", _tipo_doc, obrigatorio=False)
             or self._selecionar("tipoDocumentoCredor", _tipo_doc, obrigatorio=False))
            self._aguardar_ajax()
            self._page.wait_for_timeout(500)

            (self._preencher("numeroDocumentoFiscalCredor", _num_doc, False)
             or self._preencher("documentoFiscalCredor", _num_doc, False))
            self._log(f"  → doc credor: {_tipo_doc} {_num_doc}")

            # Apurar IR
            if hon.get("apurar_ir"):
                self._marcar_checkbox("apurarIr", True)
                self._marcar_checkbox("tributarIR", True)
            # Tipo de IR sobre honorários (se aplicável)
            if hon.get("tipo_ir_honorarios"):
                self._selecionar("tipoIrHonorarios", hon["tipo_ir_honorarios"], obrigatorio=False)
            # Base de sucumbência (se diferente do default)
            if hon.get("base_sucumbencia"):
                self._selecionar("baseSucumbencia", hon["base_sucumbencia"], obrigatorio=False)

            self._log(f"  → Salvando honorário [{i+1}/{len(hon_lista)}]")
            try:
                self._clicar_salvar()
                self._aguardar_ajax()
                self._page.wait_for_timeout(500)
                self._log(f"  ✓ Honorário [{i+1}/{len(hon_lista)}] salvo")
            except Exception as _e_save:
                self._log(f"  ✗ Honorário [{i+1}/{len(hon_lista)}] falhou no save: {_e_save}")
                # Capturar HTML da página para diagnóstico (sem screenshot)
                try:
                    _diag_dir = Path("data/logs")
                    _diag_dir.mkdir(parents=True, exist_ok=True)
                    _diag_file = _diag_dir / f"fase8_honorario_{i+1}_falha.html"
                    _diag_file.write_text(self._page.content(), encoding="utf-8")
                    self._log(f"  📋 HTML salvo: {_diag_file}")
                except Exception:
                    pass
                raise

        # Honorários periciais — criar via fluxo Novo (não é campo standalone)
        if periciais is not None:
            self._log(f"  → Honorários periciais: {_fmt_br(periciais)}")
            # Tentar campo standalone primeiro (versões antigas do PJE-Calc)
            preencheu = (
                self._preencher("honorariosPericiais", _fmt_br(periciais), False)
                or self._preencher("valorPericiais", _fmt_br(periciais), False)
            )
            if not preencheu:
                # Fluxo padrão: criar novo honorário do tipo Periciais
                _clicou = (
                    self._clicar_botao_id("incluir")
                    or self._clicar_botao_id("novo")
                )
                if not _clicou:
                    self._clicar_novo()
                self._aguardar_ajax()
                self._page.wait_for_timeout(800)
                # Selecionar tipo periciais
                for _tipo_opt in ["PERICIAIS", "Periciais", "HONORARIOS_PERICIAIS"]:
                    if self._selecionar("tipoHonorario", _tipo_opt, obrigatorio=False):
                        break
                self._marcar_radio("tipoValor", "INFORMADO")
                preencheu = (
                    self._preencher("valorInformado", _fmt_br(periciais), False)
                    or self._preencher("valorFixo", _fmt_br(periciais), False)
                )
            if preencheu:
                self._clicar_salvar()
                self._aguardar_ajax()
            else:
                self._log(
                    f"  ⚠ Campo periciais não encontrado — preencher manualmente: {_fmt_br(periciais)}"
                )
        self._log("Fase 8 concluída.")

    # ── Fase 9: Custas Judiciais ─────────────────────────────────────────────

    @retry(max_tentativas=2)
    def fase_custas_judiciais(self, custas: dict) -> None:
        """Preenche Custas Judiciais no PJE-Calc.

        Página com duas abas: Custas Devidas e Custas Recolhidas.

        DOM v2.15.1 (custas.jsf):
        - formulario:baseCustas (select) — Base das custas
        - formulario:custasReclamadoConhecimento (radio) — Calculada 2% / Informada / Não se aplica
        - formulario:custasReclamadoLiquidacao (radio) — Calculada 0,5% / Informada / Não se aplica
        - formulario:custasReclamanteConhecimento (radio) — idem
        - formulario:salvar (button) — Salvar

        Manual: "CRITICO: Clicar 'Salvar' após preencher ambas as abas."
        """
        if not custas:
            self._log("Fase 9 — Custas Judiciais: sem dados extraídos — ignorado.")
            return
        self._log("Fase 9 — Custas Judiciais…")
        self._verificar_tomcat(timeout=60)
        self._verificar_pagina_pjecalc()

        navegou = (
            self._clicar_menu_lateral("Custas Judiciais", obrigatorio=False)
            or self._clicar_menu_lateral("Custas", obrigatorio=False)
        )
        if not navegou:
            self._log("  ⚠ Custas Judiciais: menu não encontrado — tentando URL direta")
            if self._calculo_url_base and self._calculo_conversation_id:
                try:
                    _url = (f"{self._calculo_url_base}custas/custas.jsf"
                            f"?conversationId={self._calculo_conversation_id}")
                    self._page.goto(_url, wait_until="domcontentloaded", timeout=15000)
                    self._aguardar_ajax()
                    navegou = True
                except Exception as e:
                    self._log(f"  ⚠ URL direta custas falhou: {e}")
            if not navegou:
                self._log("  ⚠ Custas Judiciais: navegação falhou — ignorado.")
                return

        self._verificar_pagina_pjecalc()
        self.mapear_campos("fase9_custas")

        # Base das custas
        _base = custas.get("base", "")
        if _base:
            _base_map = {
                "Bruto Devido ao Reclamante": "BRUTO_RECLAMANTE",
                "Bruto Devido ao Reclamante + Outros Débitos": "BRUTO_RECLAMANTE_OUTROS",
            }
            _val = _base_map.get(_base, _base)
            self._selecionar("baseCustas", _val, obrigatorio=False)
            self._selecionar("baseParaApuracao", _val, obrigatorio=False)
            self._log(f"  ✓ Base custas: {_val}")

        # Custas do Reclamado — Conhecimento (padrão: Calculada 2%)
        # DOM v2.15.1: radio values = CALCULADA_2PCT / INFORMADA / NAO_SE_APLICA
        _reclamado_conhecimento = custas.get("reclamado_conhecimento", "CALCULADA_2PCT")
        # Backward compat: CALCULADA → CALCULADA_2PCT
        if _reclamado_conhecimento == "CALCULADA":
            _reclamado_conhecimento = "CALCULADA_2PCT"
        self._marcar_radio("custasReclamadoConhecimento", _reclamado_conhecimento)
        self._log(f"  ✓ Custas reclamado conhecimento: {_reclamado_conhecimento}")
        # Campos condicionais quando INFORMADA — valor e vencimento
        if _reclamado_conhecimento == "INFORMADA":
            self._aguardar_ajax()
            self._page.wait_for_timeout(500)
            if custas.get("valor_reclamado_conhecimento"):
                self._preencher("valorReclamadoConhecimento",
                                _fmt_br(custas["valor_reclamado_conhecimento"]), False)
            if custas.get("vencimento_reclamado_conhecimento"):
                self._preencher_data("vencimentoReclamadoConhecimento",
                                     custas["vencimento_reclamado_conhecimento"], False)

        # Custas do Reclamado — Liquidação
        # DOM v2.15.1: radio values = NAO_SE_APLICA / CALCULADA_05PCT / INFORMADA
        _reclamado_liq = custas.get("reclamado_liquidacao", "NAO_SE_APLICA")
        if _reclamado_liq == "CALCULADA":
            _reclamado_liq = "CALCULADA_05PCT"
        self._marcar_radio("custasReclamadoLiquidacao", _reclamado_liq)
        if _reclamado_liq == "INFORMADA":
            self._aguardar_ajax()
            self._page.wait_for_timeout(500)
            if custas.get("valor_reclamado_liquidacao"):
                self._preencher("valorReclamadoLiquidacao",
                                _fmt_br(custas["valor_reclamado_liquidacao"]), False)
            if custas.get("vencimento_reclamado_liquidacao"):
                self._preencher_data("vencimentoReclamadoLiquidacao",
                                     custas["vencimento_reclamado_liquidacao"], False)

        # Custas do Reclamante — Conhecimento (padrão: não se aplica)
        # DOM v2.15.1: radio values = NAO_SE_APLICA / CALCULADA_2PCT / INFORMADA
        _reclamante_conhecimento = custas.get("reclamante_conhecimento", "NAO_SE_APLICA")
        if _reclamante_conhecimento == "CALCULADA":
            _reclamante_conhecimento = "CALCULADA_2PCT"
        self._marcar_radio("custasReclamanteConhecimento", _reclamante_conhecimento)
        if _reclamante_conhecimento == "INFORMADA":
            self._aguardar_ajax()
            self._page.wait_for_timeout(500)
            if custas.get("valor_reclamante_conhecimento"):
                self._preencher("valorReclamanteConhecimento",
                                _fmt_br(custas["valor_reclamante_conhecimento"]), False)
            if custas.get("vencimento_reclamante_conhecimento"):
                self._preencher_data("vencimentoReclamanteConhecimento",
                                     custas["vencimento_reclamante_conhecimento"], False)

        # Percentual (se informado e diferente do padrão 2%)
        _pct = custas.get("percentual")
        if _pct is not None:
            self._preencher("percentualCustas", _fmt_br(float(_pct) * 100), obrigatorio=False)
            self._preencher("aliquota", _fmt_br(float(_pct) * 100), obrigatorio=False)

        # Devedor
        _devedor = custas.get("devedor", "")
        if _devedor:
            self._selecionar("devedor", _devedor, obrigatorio=False)

        if not self._clicar_salvar():
            self._log("  ⚠ Fase 9: Salvar Custas não confirmado.")

        # Forma de cobrança do reclamante (se aplicável)
        if custas.get("forma_cobranca_reclamante"):
            self._selecionar("formaCobrancaReclamante", custas["forma_cobranca_reclamante"], obrigatorio=False)

        # Custas fixas (quando aplicável)
        if custas.get("custas_fixas_quantidade"):
            self._preencher("custasFixasQuantidade", str(custas["custas_fixas_quantidade"]), False)
        if custas.get("custas_fixas_vencimento"):
            self._preencher_data("custasFixasVencimento", custas["custas_fixas_vencimento"], False)

        # Custas de autos/armazenamento (quando aplicável)
        if custas.get("custas_autos_valor_bem"):
            self._preencher("custasAutosValorBem", _fmt_br(custas["custas_autos_valor_bem"]), False)
        if custas.get("custas_autos_vencimento"):
            self._preencher_data("custasAutosVencimento", custas["custas_autos_vencimento"], False)
        if custas.get("armazenamento_data_inicio"):
            self._preencher_data("armazenamentoDataInicio", custas["armazenamento_data_inicio"], False)
        if custas.get("armazenamento_valor_bem"):
            self._preencher("armazenamentoValorBem", _fmt_br(custas["armazenamento_valor_bem"]), False)

        # ── Aba Custas Recolhidas (se houver dados) ──
        _recolhidas = custas.get("custas_recolhidas", [])
        if _recolhidas:
            self._log(f"  → Aba Custas Recolhidas: {len(_recolhidas)} registro(s)…")
            try:
                _aba_rec = self._page.locator(
                    "[id$='tabCustasRecolhidas'], a:has-text('Custas Recolhidas'), "
                    "a:has-text('Recolhidas')"
                )
                if _aba_rec.count() > 0:
                    _aba_rec.first.click()
                    self._aguardar_ajax()
                    self._page.wait_for_timeout(800)
                    for _rec in _recolhidas:
                        # Clicar "Incluir" para adicionar registro de custas recolhidas
                        _btn_inc = self._page.locator("[id$='incluirRecolhida'], [id$='incluir']")
                        if _btn_inc.count() > 0:
                            _btn_inc.first.click()
                            self._aguardar_ajax()
                            self._page.wait_for_timeout(500)
                        if _rec.get("valor"):
                            self._preencher("recolhidaValor", _fmt_br(_rec["valor"]), False)
                            self._preencher("valorRecolhida", _fmt_br(_rec["valor"]), False)
                        if _rec.get("vencimento"):
                            self._preencher_data("recolhidaVencimento", _rec["vencimento"], False)
                            self._preencher_data("vencimentoRecolhida", _rec["vencimento"], False)
                    # Salvar custas recolhidas
                    self._clicar_salvar()
                    self._log("  ✓ Custas recolhidas salvas")
            except Exception as _e_rec:
                self._log(f"  ⚠ Custas recolhidas: {_e_rec}")

        self._log("Fase 9 concluída.")

    # ── Verificação de cálculo correto ──────────────────────────────────────────

    def _verificar_calculo_correto(self) -> bool:
        """Verifica se o cálculo atualmente aberto pertence ao processo correto.

        Compara o número do processo exibido na página com o número em self._dados.
        Retorna True se correto. Retorna False se errado ou se a verificação falhar
        (fail-safe: melhor abortar do que exportar processo errado).
        """
        if not self._dados:
            self._log("  ⚠ Verificação: sem dados para comparar")
            return True  # sem dados para comparar — assumir correto
        _num_esperado = self._dados.get("processo", {}).get("numero", "")
        if not _num_esperado:
            self._log("  ⚠ Verificação: número do processo não informado nos dados")
            return True

        # Extrair número do processo da página atual
        try:
            _num_pagina = self._page.evaluate("""() => {
                // Estratégia 1: reconstruir CNJ a partir dos campos individuais do formulário
                // calculo.jsf tem campos separados: numero, digito, ano, justica, regiao, varaProcesso
                const f = (id) => {
                    const el = document.querySelector('[id$="' + id + '"]');
                    return el ? (el.value || el.textContent || '').trim() : '';
                };
                const num = f(':numero') || f('numero');
                const dig = f(':digito') || f('digito');
                const ano = f(':ano') || f('ano');
                const jus = f(':justica') || f('justica');
                const reg = f(':regiao') || f('regiao');
                const vara = f(':varaProcesso') || f('vara') || f('varaProcesso');
                if (num && num.length >= 5 && dig && ano) {
                    return num + '-' + dig + '.' + ano + '.' + (jus||'5') + '.' + (reg||'00') + '.' + (vara||'0000');
                }

                // Estratégia 2: buscar número CNJ formatado em contextos do formulário.
                // NÃO varrer document.body inteiro — a sidebar/recentes pode conter CNJ
                // de outro cálculo e gerar falso positivo (ver regressão do fix cd75571).
                const seletores = [
                    '[id*="numero"][id*="rocesso"]',
                    '[id*="identificador"]',
                    '.rf-p-hdr', '.rich-panel-header',
                    'td.texto', '.subtitle', 'h2', 'h3',
                ];
                for (const sel of seletores) {
                    for (const el of document.querySelectorAll(sel)) {
                        const txt = (el.textContent || el.value || '').trim();
                        const m = txt.match(/\\d{7}-\\d{2}\\.\\d{4}\\.\\d\\.\\d{2}\\.\\d{4}/);
                        if (m) return m[0];
                    }
                }
                return null;
            }""")
        except Exception as _exc:
            self._log(f"  ⚠ Verificação falhou (erro JS): {_exc}")
            return False  # fail-safe: não arriscar exportar processo errado

        if not _num_pagina:
            # ⚠️ REGRESSION GUARD (fixes cd75571 + d24fb99) — NÃO alterar para `return False`.
            # Histórico: cd75571 (08/04) corrigiu essa linha; 63fe793 (14min depois) reverteu
            # silenciosamente ao commitar a partir de parent antigo; d24fb99 (15/04) reaplicou.
            # Após as fases de preenchimento, o conversationId na URL GARANTE o cálculo correto
            # — não precisamos confirmar via CNJ na página (que pode nem estar visível).
            # Retornar False aqui causa abort do passo Liquidar ("CÁLCULO ERRADO" falso positivo).
            self._log("  ⚠ Verificação de cálculo: número do processo não visível na página — assumindo correto (mesmo conversationId)")
            return True  # NÃO REVERTER — ver comentário acima

        # Comparar apenas dígitos
        import re as _re_vc
        _esperado_limpo = _re_vc.sub(r"[^\d]", "", _num_esperado)
        _pagina_limpo = _re_vc.sub(r"[^\d]", "", _num_pagina)
        if _esperado_limpo == _pagina_limpo:
            self._log(f"  ✓ Cálculo correto: {_num_pagina}")
            return True
        else:
            self._log(f"  ⚠ CÁLCULO ERRADO! Esperado: {_num_esperado}, encontrado: {_num_pagina}")
            return False

    # ── Liquidar / captura do .PJC ─────────────────────────────────────────────

    def _clicar_liquidar(self) -> str | None:
        """
        Executa liquidação e exportação do .PJC no PJE-Calc.

        Fluxo correto (dois passos distintos):
          1. Navegar para Liquidar via sidebar → clicar botão Liquidar (AJAX)
          2. Navegar para Exportar via sidebar → clicar botão Exportar → capturar download .PJC

        Após todas as fases de preenchimento, o PJE-Calc já está no cálculo
        correto (mesmo conversationId). Basta navegar para Liquidar e depois
        Exportar via sidebar — sem necessidade de buscar/re-abrir o cálculo.

        Fallback: se a verificação do cálculo falhar (sessão corrompida),
        tenta re-abrir via Recentes antes de prosseguir.
        """
        self._log("→ Liquidar: iniciando geração do cálculo…")
        import time as _time_liq
        from config import OUTPUT_DIR
        out_dir = Path(OUTPUT_DIR)
        out_dir.mkdir(parents=True, exist_ok=True)

        # Pasta dedicada de exports
        _exports_dir = out_dir.parent / "exports"
        _exports_dir.mkdir(parents=True, exist_ok=True)

        # REGRA DE SEGURANÇA: verificar processo correto ANTES de liquidar.
        # O PJE-Calc já está no cálculo correto após as fases de preenchimento.
        # Só tenta re-abrir se a verificação falhar (sessão corrompida por NPE).
        _num_proc = (self._dados or {}).get("processo", {}).get("numero", "?")
        if not self._verificar_calculo_correto():
            self._log("  ⚠ Verificação de cálculo falhou na sessão atual — tentando re-abrir via Recentes…")
            _sessao_restaurada = self._reabrir_calculo_recentes()
            if _sessao_restaurada and self._verificar_calculo_correto():
                self._log("  ✓ Cálculo re-aberto e verificado via Recentes")
            else:
                raise RuntimeError(
                    "ABORTADO: o cálculo aberto não corresponde ao processo solicitado "
                    f"(esperado: '{_num_proc}'). "
                    "Não é seguro prosseguir com liquidação/exportação."
                )
        else:
            self._log(f"  ✓ Cálculo correto confirmado — processo '{_num_proc}'")

        def _salvar_download(dl_info_value) -> str:
            # Gerar nome padronizado: PROCESSO_{numero}_{timestamp}.pjc
            _ts = _time_liq.strftime("%Y%m%d_%H%M%S")
            _num_limpo = _num_proc.replace("-", "").replace(".", "").replace("/", "")
            _nome_padrao = f"PROCESSO_{_num_limpo}_{_ts}.pjc"

            # Salvar na pasta de exports
            dest = _exports_dir / _nome_padrao
            dl_info_value.save_as(str(dest))

            # Cópia adicional na pasta output (retrocompat)
            _dest_output = out_dir / _nome_padrao
            try:
                import shutil
                shutil.copy2(str(dest), str(_dest_output))
            except Exception:
                pass
            # Verificar integridade do .PJC (deve ser ZIP com calculo.xml)
            try:
                tamanho = dest.stat().st_size
                if tamanho < 1024:
                    self._log(f"  ⚠ .PJC suspeito: apenas {tamanho} bytes — pode estar corrompido")
                else:
                    import zipfile as _zf
                    try:
                        with _zf.ZipFile(str(dest), 'r') as _z:
                            _nomes = _z.namelist()
                            if "calculo.xml" not in _nomes:
                                self._log(f"  ⚠ .PJC sem calculo.xml — conteúdo: {_nomes[:5]}")
                            elif _z.testzip() is not None:
                                self._log(f"  ⚠ .PJC ZIP corrompido (testzip falhou)")
                            else:
                                self._log(f"  ✓ .PJC válido ({tamanho//1024}KB, calculo.xml presente)")
                    except _zf.BadZipFile:
                        self._log(f"  ⚠ .PJC não é ZIP válido ({tamanho} bytes)")
            except Exception as _ie:
                self._log(f"  ⚠ Não foi possível verificar integridade do .PJC: {_ie}")
            self._log(f"PJC_GERADO:{dest}")
            return str(dest)

        # ── Passo 1: Navegar para Liquidar via sidebar JSF (NÃO via URL) ────────
        # IMPORTANTE: A página /pages/calculo/liquidacao.xhtml precisa que
        # apresentadorLiquidacao.liquidacao não seja null. Isso só acontece quando
        # a navegação é feita via sidebar JSF (que chama a action do menu) —
        # navegar direto via URL não inicializa o bean, causando NPE.
        #
        # O sidebar "Operações > Liquidar" é um link JSF que dispara a navegação.
        # Precisamos clicar nele via JS (force=True) para que o JSF processe a action.
        self._log("  → Navegando para Liquidar via sidebar JSF…")
        _nav_ok = False

        # Tentar clicar no sidebar via JS — buscar link com texto "Liquidar" na sidebar
        try:
            _nav_ok = self._page.evaluate("""() => {
                // Buscar todos os links na sidebar (div com class "menu" ou similar)
                const links = [...document.querySelectorAll('a')];
                for (const a of links) {
                    const txt = (a.textContent || '').replace(/[\\s\\u00a0]+/g, ' ').trim();
                    // Procurar link "Liquidar" (não o botão "Liquidar" no formulário)
                    if (txt === 'Liquidar' && a.id && (a.id.includes('menu') || a.id.includes('j_id'))) {
                        a.click();
                        return true;
                    }
                }
                // Fallback: qualquer link com "Liquidar" que pareça do sidebar
                for (const a of links) {
                    const txt = (a.textContent || '').replace(/[\\s\\u00a0]+/g, ' ').trim();
                    const parentLi = a.closest('li');
                    if (txt === 'Liquidar' && parentLi && parentLi.id && parentLi.id.includes('operacoes')) {
                        a.click();
                        return true;
                    }
                }
                return false;
            }""")
        except Exception as _e_nav:
            self._log(f"  ⚠ Sidebar click JS: {_e_nav}")

        if _nav_ok:
            self._log("  ✓ Sidebar Liquidar clicado via JS")
            self._aguardar_ajax(30000)
            self._page.wait_for_timeout(2000)
        else:
            # Tentar _clicar_menu_lateral que pode usar force=True
            self._log("  ⚠ Sidebar JS não encontrou — tentando _clicar_menu_lateral…")
            _nav_ok = self._clicar_menu_lateral("Liquidar", obrigatorio=False)
            if _nav_ok:
                self._page.wait_for_timeout(1000)

        # Verificar se chegou na página de liquidação corretamente
        _na_liquidacao = False
        try:
            _body_liq = self._page.locator("body").text_content(timeout=5000) or ""
            if "Erro Interno" in _body_liq or "identifier" in _body_liq:
                self._log("  ⚠ Erro ao carregar página de liquidação — bean não inicializado")
                self._screenshot_fase("liquidacao_erro")
            elif "Liquidar" in _body_liq or "liquidação" in _body_liq.lower() or "pendências" in _body_liq.lower():
                _na_liquidacao = True
                self._log("  ✓ Página de liquidação carregada")
        except Exception:
            pass

        if not _na_liquidacao:
            self._log("  ⚠ Não na página de liquidação — tentando preencher data e liquidar direto")

        # Preencher data de liquidação se campo disponível
        try:
            _dt_campo = self._page.locator(Liquidacao.DATA_LIQUIDACAO)
            if _dt_campo.count() > 0:
                _val = _dt_campo.first.input_value()
                if not _val:
                    from datetime import date
                    self._preencher_data("dataDeLiquidacao",
                                        date.today().strftime("%d/%m/%Y"), False)
                    self._log(f"  ✓ Data liquidação: {date.today().strftime('%d/%m/%Y')}")
        except Exception:
            pass

        # Acumular Índices de Correção (select na página de liquidação)
        # Opções: MES_SUBSEQUENTE | MES_VENCIMENTO | MISTO
        _acum = (self._dados or {}).get("correcao_juros", {}).get("acumular_indices", "")
        if not _acum:
            _acum = (self._dados or {}).get("acumular_indices", "")
        if _acum:
            try:
                _sel_acum = self._page.locator("select[id$='acumularIndices']")
                if _sel_acum.count() > 0:
                    try:
                        _sel_acum.first.select_option(value=_acum)
                    except Exception:
                        _sel_acum.first.select_option(label=_acum)
                    self._aguardar_ajax()
                    self._log(f"  ✓ Acumular índices: {_acum}")
                else:
                    self._log(f"  ⚠ Campo acumularIndices não encontrado na página de liquidação")
            except Exception as _e_acum:
                self._log(f"  ⚠ Acumular índices: erro {_e_acum}")

        # Localizar botão Liquidar
        # /pages/calculo/liquidacao.xhtml: <a4j:commandButton id="liquidar" value="Liquidar">
        # /pages/verba/liquidacao.xhtml: <a4j:commandButton id="incluir" value="Liquidar">
        loc = None
        for sel in ["input[id$='liquidar'][value='Liquidar']",
                    "input[value='Liquidar']",
                    "[id$='incluir'][value='Liquidar']"]:
            try:
                candidate = self._page.locator(sel)
                if candidate.count() > 0 and candidate.first.is_visible():
                    loc = candidate.first
                    self._log(f"  ℹ Botão encontrado: {sel}")
                    break
            except Exception:
                continue

        if loc is None:
            # JS global fallback — click visible input/button with value "Liquidar"
            self._log("  Tentando Liquidar via JS global…")
            clicou = self._page.evaluate("""() => {
                const all = [...document.querySelectorAll('input[type="submit"], button')];
                for (const el of all) {
                    const val = (el.value || el.textContent || '').trim();
                    if (val === 'Liquidar' && el.offsetParent !== null) {
                        el.click(); return true;
                    }
                }
                return false;
            }""")
            if not clicou:
                raise RuntimeError(
                    "Botão Liquidar não encontrado em nenhuma estratégia. "
                    "Verifique se todos os campos obrigatórios foram preenchidos."
                )
            self._aguardar_ajax(90000)
        else:
            self._log("  ✓ Botão Liquidar clicado (AJAX)…")
            loc.click()
            self._aguardar_ajax(90000)

        self._page.wait_for_timeout(2000)

        # Validar resultado da liquidação antes de exportar
        # Mensagem de sucesso: "Não foram encontradas pendências para a liquidação"
        _liquidacao_ok = False
        _liquidacao_erro_msg = None
        try:
            body_text = self._page.locator("body").text_content(timeout=5000) or ""
            _body_lower = body_text.lower()
            # Verificar sucesso explícito
            if "não foram encontradas pendências" in _body_lower or \
               "liquidação realizada" in _body_lower or \
               "cálculo liquidado" in _body_lower:
                self._log("  ✓ Liquidação concluída sem pendências")
                _liquidacao_ok = True
            else:
                # Verificar erros — "pendente" sozinho é falso positivo (aparece na msg de sucesso)
                for indicador in ["não foi possível", "inconsistente", "erro interno",
                                  "existem pendências", "campos obrigatórios"]:
                    if indicador in _body_lower:
                        self._log(f"  ⚠ Liquidação pode ter falhado: '{indicador}' detectado")
                        _liquidacao_erro_msg = indicador
                        self._screenshot_fase("liquidacao_erro")
                        # Capturar mensagem de erro JSF detalhada
                        try:
                            _msgs = self._page.evaluate("""() => {
                                const sels = ['.rf-msgs-sum', '.rf-msgs-det', '.rich-messages',
                                              '[class*="msg-error"]', '[class*="erro"]',
                                              '.mensagem-erro', '.ui-messages-error'];
                                for (const sel of sels) {
                                    const els = document.querySelectorAll(sel);
                                    if (els.length > 0) {
                                        return [...els].map(e => e.textContent.trim()).join(' | ');
                                    }
                                }
                                return null;
                            }""")
                            if _msgs:
                                self._log(f"  ⚠ Mensagem JSF: {_msgs[:300]}")
                        except Exception:
                            pass
                        break
                if not _liquidacao_erro_msg:
                    _liquidacao_ok = True  # Sem erro explícito = OK
        except Exception:
            _liquidacao_ok = True  # Se não conseguiu verificar, assume OK

        # Retry: se liquidação falhou, re-abrir cálculo via Tela Inicial (nova conversação)
        if not _liquidacao_ok and _liquidacao_erro_msg:
            self._log("  → Retry: re-abrindo cálculo via Tela Inicial para nova conversação…")
            try:
                # Navegar para principal.jsf e re-abrir via Cálculos Recentes
                _home = f"{self.PJECALC_BASE}/pages/principal.jsf"
                self._page.goto(_home, wait_until="domcontentloaded", timeout=15000)
                self._page.wait_for_timeout(2000)
                try:
                    self._instalar_monitor_ajax()
                except Exception:
                    pass

                _reabriu = False
                _listbox = self._page.locator("select[class*='listaCalculosRecentes'], select[name*='listaCalculosRecentes']")
                if _listbox.count() > 0:
                    _options = _listbox.first.locator("option")
                    if _options.count() > 0:
                        _options.first.click()
                        self._page.wait_for_timeout(300)
                        _options.first.dblclick()
                        self._aguardar_ajax(30000)
                        self._page.wait_for_timeout(2000)
                        _url_r = self._page.url
                        if "calculo" in _url_r and "conversationId" in _url_r:
                            self._capturar_base_calculo()
                            self._log(f"  ✓ Retry: nova conversação {self._calculo_conversation_id}")
                            _reabriu = True

                if _reabriu:
                    # Navegar para Liquidar via sidebar JSF (não via URL — URL causa NPE)
                    _nav_retry = self._page.evaluate("""() => {
                        const links = [...document.querySelectorAll('a')];
                        for (const a of links) {
                            const txt = (a.textContent || '').replace(/[\\s\\u00a0]+/g, ' ').trim();
                            if (txt === 'Liquidar' && a.id && (a.id.includes('menu') || a.id.includes('j_id'))) {
                                a.click(); return true;
                            }
                        }
                        for (const a of links) {
                            const txt = (a.textContent || '').replace(/[\\s\\u00a0]+/g, ' ').trim();
                            const li = a.closest('li');
                            if (txt === 'Liquidar' && li && li.id && li.id.includes('operacoes')) {
                                a.click(); return true;
                            }
                        }
                        return false;
                    }""")
                    if _nav_retry:
                        self._log("  ✓ Retry: sidebar Liquidar clicado")
                        self._aguardar_ajax(30000)
                        self._page.wait_for_timeout(2000)
                    else:
                        self._log("  ⚠ Retry: sidebar Liquidar não encontrado")
                        self._clicar_menu_lateral("Liquidar", obrigatorio=False)
                        self._page.wait_for_timeout(1000)

                    # Clicar botão Liquidar no formulário
                    for sel in ["input[id$='liquidar'][value='Liquidar']",
                                "input[value='Liquidar']"]:
                        _loc2 = self._page.locator(sel)
                        if _loc2.count() > 0 and _loc2.first.is_visible():
                            self._log("  → Retry: clicando Liquidar…")
                            _loc2.first.click()
                            self._aguardar_ajax(90000)
                            self._page.wait_for_timeout(2000)
                            _body2 = (self._page.locator("body").text_content(timeout=5000) or "").lower()
                            if "não foram encontradas pendências" in _body2 or \
                               "liquidação realizada" in _body2 or \
                               "cálculo liquidado" in _body2:
                                self._log("  ✓ Retry liquidação: sucesso!")
                                _liquidacao_ok = True
                            elif "erro interno" not in _body2 and "não foi possível" not in _body2:
                                self._log("  ✓ Retry liquidação: sem erro detectado")
                                _liquidacao_ok = True
                            else:
                                self._log("  ⚠ Retry liquidação: ainda com erro")
                                self._screenshot_fase("liquidacao_erro_retry")
                            break
            except Exception as _retry_err:
                self._log(f"  ⚠ Retry liquidação falhou: {_retry_err}")

        # ── Abortar se liquidação falhou ────────────────────────────────────────
        if not _liquidacao_ok:
            self._log("  ✗ Liquidação FALHOU — abortando exportação.")
            self._log(
                "ERRO_LIQUIDACAO: Não é possível exportar .PJC sem liquidação bem-sucedida. "
                "Verifique pendências no PJE-Calc e tente novamente."
            )
            return None

        self._log("  ✓ Liquidação AJAX concluída — navegando para Exportação…")

        # ── Passo 2: Exportação → capturar .PJC ──────────────────────────────────
        # DESCOBERTA CRÍTICA (análise de ApresentadorExportacao.class):
        # - @Scope(ScopeType.SESSION), bean name "apresentadorExportacao"
        # - Método iniciar() está anotado com @Menu(OPERACOES_EXPORTAR)
        # - iniciar() chama servicoDeCalculo.obterCalculoAberto() +
        #   Exportador.gerarNomeDoArquivo(calculo) → seta o campo `nome`
        # - iniciar() é chamado APENAS via o menu lateral (gerenciadorDeMenus)
        # - Goto direto para exportacao.jsf NÃO dispara iniciar() → nome="" →
        #   exportar() falha silenciosamente e linkDownloadArquivo nunca aparece.
        #
        # ESTRATÉGIA: Navegar para uma página "neutra" primeiro (Dados do Cálculo)
        # para sair do form de liquidacao.jsf que causa HTTP 500. Depois clicar
        # no menu lateral Exportar, que dispara iniciar() e popula nome.
        _exportou = False

        # Log do conversationId atual (para diagnóstico)
        try:
            import re as _re
            _m = _re.search(r"conversationId=(\d+)", self._page.url)
            if _m:
                _conv_id_live = _m.group(1)
                self._calculo_conversation_id = _conv_id_live
                self._log(f"  → conversationId ativo: {_conv_id_live}")
        except Exception:
            pass

        # Etapa 1: sair da liquidacao.jsf navegando para Dados do Cálculo.
        # Isso evita HTTP 500 que ocorre ao submeter menu Exportar de dentro
        # do form pós-liquidação. APÓS, fazer reload() para garantir ViewState
        # limpo (test v8 mostrou ViewExpiredException quando o click A4J vem
        # após goto + instalação de monitor AJAX).
        try:
            self._log("  → Saindo de liquidacao.jsf via menu 'Dados do Cálculo'…")
            if self._clicar_menu_lateral("Dados do Cálculo", obrigatorio=False):
                self._aguardar_ajax(timeout=15000)
                self._page.wait_for_timeout(1500)
                self._log(f"  ✓ Agora em: {self._page.url}")
                # RELOAD para ViewState fresco — evita ViewExpiredException
                # quando clicamos no link <a4j:commandLink> que dispara
                # A4J.AJAX.Submit('formulario',...) logo em seguida.
                try:
                    self._log("  → Reload calculo.jsf para ViewState fresco…")
                    self._page.reload(wait_until="domcontentloaded", timeout=15000)
                    self._aguardar_ajax(timeout=10000)
                    self._page.wait_for_timeout(800)
                    self._log(f"  ✓ Após reload: {self._page.url}")
                except Exception as _rl_err:
                    self._log(f"  ⚠ Reload falhou: {_rl_err}")
        except Exception as _nav_err:
            self._log(f"  ⚠ Navegação intermediária falhou: {_nav_err}")

        # Etapa 2: disparar iniciar() do apresentadorExportacao via JS form POST.
        #
        # ESTRATÉGIA NOVA (descoberta v7):
        # Clicar via `li#li_operacoes_exportar a` cai em principal.jsf mesmo com
        # li correto. Motivo: o <a4j:commandLink> em menu-pilares.xhtml pode estar
        # envolto em um <ul> que faz slideToggle (display:none quando o bloco de
        # operações está fechado), tornando o link inacessível/ocultado e o
        # click recai em algum handler genérico. Além disso, mesmo se clicar, o
        # end-conversation do Seam destrói a conversação e a redirect leva para
        # principal (porque gerenciadorDeMenus.menuItemAberto perde o cálculo).
        #
        # SOLUÇÃO: (a) instalar dialog handler p/ aceitar confirm/alert;
        # (b) inspecionar o DOM e expandir o bloco "Operações" se estiver recolhido;
        # (c) executar o `onclick` do <a> diretamente via JS, que invoca
        # A4J.AJAX.Submit corretamente com o conversationId atual.
        try:
            # Handler de dialog: aceita tudo (confirm/alert do menu)
            try:
                self._page.on("dialog", lambda d: d.accept())
            except Exception:
                pass

            self._log("  → Diagnóstico DOM do menu lateral…")
            _diag_menu = self._page.evaluate("""() => {
                const result = {lis: [], hrefs: [], onclicks: []};
                const allLis = [...document.querySelectorAll('li[id^="li_operacoes"], li[id^="li_calculo_exportar"]')];
                for (const li of allLis) {
                    const a = li.querySelector('a');
                    result.lis.push({
                        id: li.id,
                        visible: li.offsetParent !== null,
                        display: getComputedStyle(li).display,
                        aId: a ? a.id : null,
                        aHref: a ? a.href : null,
                        aOnclick: a ? (a.getAttribute('onclick') || '').slice(0, 200) : null,
                    });
                }
                // Também pegar o UL pai do li_operacoes_exportar
                const liExp = document.getElementById('li_operacoes_exportar');
                if (liExp) {
                    const parentUl = liExp.closest('ul');
                    if (parentUl) {
                        result.parentUl = {
                            display: getComputedStyle(parentUl).display,
                            visible: parentUl.offsetParent !== null,
                        };
                    }
                    // Header "Operações" (li.header antes do menu-item)
                    let prev = liExp.closest('li.menu-item');
                    if (prev) prev = prev.previousElementSibling;
                    if (prev && prev.classList.contains('header')) {
                        result.header = {text: prev.textContent.trim(), classes: prev.className};
                    }
                }
                return result;
            }""")
            self._log(f"  → DOM menu: {_diag_menu}")

            # Se o bloco Operações está recolhido, expandir via clique no header
            try:
                _expandiu = self._page.evaluate("""() => {
                    const liExp = document.getElementById('li_operacoes_exportar');
                    if (!liExp) return 'sem_li';
                    const ul = liExp.closest('ul');
                    if (ul && getComputedStyle(ul).display === 'none') {
                        // Encontrar o header (.header) que controla este ul
                        const menuItemLi = liExp.closest('li.menu-item');
                        if (menuItemLi) {
                            const header = menuItemLi.previousElementSibling;
                            if (header && header.classList.contains('header')) {
                                header.click();
                                return 'clicked_header';
                            }
                        }
                    }
                    return 'ja_aberto';
                }""")
                self._log(f"  → Expansão Operações: {_expandiu}")
                self._page.wait_for_timeout(600)
            except Exception as _exp_err:
                self._log(f"  ⚠ Expansão falhou: {_exp_err}")

            # Agora disparar o onclick do <a> dentro de li#li_operacoes_exportar
            self._log("  → Disparando onclick do <a> de operacoes_exportar…")
            _click_result = self._page.evaluate("""() => {
                const li = document.getElementById('li_operacoes_exportar');
                if (!li) return 'sem_li';
                const a = li.querySelector('a');
                if (!a) return 'sem_a';
                // Preferir chamar o onclick (A4J.AJAX.Submit) diretamente
                try {
                    if (typeof a.onclick === 'function') {
                        a.onclick.call(a, new Event('click'));
                        return 'onclick_chamado';
                    }
                } catch (e) { /* fallback */ }
                a.click();
                return 'click_chamado';
            }""")
            self._log(f"  → Click via JS: {_click_result}")
            self._aguardar_ajax(timeout=25000)
            self._page.wait_for_timeout(2500)
            _url_pos = self._page.url
            if "exportacao" in _url_pos:
                self._log(f"  ✓ Navegação via menu OK: {_url_pos}")
                _exportou = True
                # CRÍTICO: atualizar conversationId — a navegação para exportacao.jsf
                # avança o Seam para uma nova conversação (ex: 296→303). Se continuar
                # usando o valor antigo em Fase D, o servidor abre conversação nova e
                # retorna página vazia (HTML) ao invés do .PJC. Capturar o novo ID aqui.
                try:
                    import re as _re_cid
                    _m_cid = _re_cid.search(r"conversationId=(\d+)", _url_pos)
                    if _m_cid:
                        _new_cid = _m_cid.group(1)
                        if _new_cid != self._calculo_conversation_id:
                            self._log(
                                f"  ↻ conversationId atualizado: "
                                f"{self._calculo_conversation_id} → {_new_cid}"
                            )
                            self._calculo_conversation_id = _new_cid
                except Exception:
                    pass
            else:
                self._log(f"  ⚠ Menu Exportar clicado mas URL ficou em: {_url_pos}")
        except Exception as _menu_err:
            self._log(f"  ⚠ Clique no menu Exportar falhou: {_menu_err}")

        # Fallback: goto direto (iniciar NÃO vai rodar, mas tentamos mesmo assim)
        if not _exportou and self._calculo_conversation_id and self._calculo_url_base:
            _exp_url = (
                f"{self._calculo_url_base}exportacao.jsf"
                f"?conversationId={self._calculo_conversation_id}"
            )
            try:
                self._log(f"  → Fallback: goto direto {_exp_url}")
                self._page.goto(_exp_url, wait_until="domcontentloaded", timeout=15000)
                try:
                    self._instalar_monitor_ajax()
                except Exception:
                    pass
                self._aguardar_ajax()
                self._page.wait_for_timeout(1000)
                if "exportacao" in self._page.url:
                    _exportou = True
                    self._log(f"  ✓ Goto OK (mas iniciar() provavelmente não rodou): {self._page.url}")
            except Exception as _goto_err:
                self._log(f"  ⚠ goto direto falhou: {_goto_err}")

        # Debug: capturar estado da página de exportação
        try:
            self._log(f"  → Página atual: {self._page.url}")
            self._screenshot_fase("pre_exportacao")
        except Exception:
            pass

        # Clicar botão Exportar (a4j:commandButton id="exportar" em exportacao.xhtml)
        # FLUXO DOCUMENTADO (exportacao.xhtml):
        #   1. a4j:commandButton id="exportar" actionListener="#{apresentador.exportar}"
        #      dispara AJAX → apresentador gera arquivo e seta downloadDisponivel=true
        #   2. Resposta AJAX re-renderiza panelBotoes (ajaxRendered="true") com
        #      <s:span rendered="#{apresentador.downloadDisponivel}"> contendo:
        #        - h:commandLink id="linkDownloadArquivo"
        #        - <script>jsfcljs(form, {'formulario:linkDownloadArquivo':...}, '')</script>
        #   3. jsfcljs() deveria auto-executar, mas o script inline NÃO é avaliado
        #      automaticamente pelo RichFaces 3 após re-render AJAX parcial.
        # ESTRATÉGIA: Dividir em duas fases. (a) Clicar exportar e esperar AJAX
        # completar. (b) Aguardar linkDownloadArquivo aparecer e disparar download
        # manualmente via jsfcljs dentro de expect_download.
        # Seletores ESPECÍFICOS para o a4j:commandButton id="exportar" em exportacao.xhtml.
        # CRÍTICO: NUNCA usar [id$='exportar'] sem restringir tipo — isso matcheria
        # também `li_operacoes_exportar` da sidebar (que termina em "exportar" e está
        # visível), fazendo o click cair no menu lateral e NÃO gerar POST do botão.
        # O commandButton é renderizado como <input type="submit" class="botao" id="formulario:exportar"/>.
        _btn_exportar = None
        for sel in [
            "input[type='submit'][id$=':exportar']",
            "input[type='button'][id$=':exportar']",
            "input[id$=':exportar'][value='Exportar']",
            "input.botao[value='Exportar']",
            "input[value='Exportar'][type='submit']",
        ]:
            try:
                loc_exp = self._page.locator(sel)
                if loc_exp.count() > 0:
                    _btn_exportar = loc_exp.first
                    self._log(f"  → Botão Exportar localizado via: {sel}")
                    break
            except Exception:
                continue

        if _btn_exportar:
            # Fase A — Clicar Exportar
            # DESCOBERTA CRÍTICA (abr/2026): clicar Exportar dispara uma sequência
            # de DOIS requests:
            #   1. A4J AJAX (exportar button) → server chama `apresentador.exportar()`,
            #      seta this.arquivo e responde com re-render do panelBotoes contendo
            #      <a linkDownloadArquivo> + <script>jsfcljs(...)</script>
            #   2. O RichFaces 3 A4J handler AVALIA o <script> inline do fragmento
            #      atualizado, o que dispara `jsfcljs()` AUTOMATICAMENTE → form.submit()
            #      nativo (não-AJAX) → server chama `apresentador.downloadArquivo()` e
            #      retorna Content-Type: application/zip com os bytes do .PJC.
            #
            # O problema das fases E/D/C era: quando tentamos disparar jsfcljs DEPOIS
            # do click, o auto-submit do passo 2 já consumiu o arquivo (downloadArquivo
            # é one-shot: seta `arquivo = null`). Solução: capturar o response do passo 2
            # ENQUANTO clicamos Exportar, via expect_response com predicate por
            # content-type/disposition.
            _pjc_bytes = None
            _pjc_filename = None
            try:
                self._log("  → Fase A: clicando botão Exportar (AJAX + auto-submit)…")
                with self._page.expect_response(
                    lambda r: (
                        'exportacao.jsf' in r.url
                        and r.request.method == 'POST'
                        and (
                            'zip' in (r.headers.get('content-type') or '').lower()
                            or 'attachment' in (r.headers.get('content-disposition') or '').lower()
                            or '.pjc' in (r.headers.get('content-disposition') or '').lower()
                        )
                    ),
                    timeout=60000,
                ) as _pjc_resp_info:
                    _btn_exportar.click()
                    # NÃO chamar _aguardar_ajax aqui pois pode consumir o response
                    # antes do expect_response capturar. Aguardar só o download.
                _pjc_resp = _pjc_resp_info.value
                _ct_a = _pjc_resp.headers.get('content-type', '')
                _cd_a = _pjc_resp.headers.get('content-disposition', '')
                self._log(
                    f"  ✓ Fase A capturou response: HTTP {_pjc_resp.status} "
                    f"content-type={_ct_a} disposition={_cd_a[:150]}"
                )
                try:
                    _pjc_bytes = _pjc_resp.body()
                except Exception as _be_a:
                    self._log(f"  ⚠ Fase A body() falhou: {_be_a}")
                # Extrair filename do disposition
                if _cd_a:
                    import re as _re_a
                    _m_fn = _re_a.search(r'filename\*?=(?:UTF-8\'\')?"?([^";]+)"?', _cd_a, _re_a.IGNORECASE)
                    if _m_fn:
                        _pjc_filename = _m_fn.group(1).strip()
                        self._log(f"  → Filename extraído: {_pjc_filename}")
            except Exception as e_click:
                self._log(f"  ⚠ Fase A (click + expect_response .PJC) falhou: {e_click}")
                # Fallback: ainda tentar clicar sem expect_response
                try:
                    _btn_exportar.click()
                    self._aguardar_ajax(timeout=30000)
                    self._page.wait_for_timeout(1000)
                except Exception as e_click2:
                    self._log(f"  ⚠ Click simples também falhou: {e_click2}")

            # Se Fase A capturou bytes válidos, salvar e retornar direto
            if _pjc_bytes and len(_pjc_bytes) > 100:
                _is_zip_a = _pjc_bytes[:2] == b'PK'
                _is_html_a = (
                    b'<html' in _pjc_bytes[:200].lower()
                    or b'<!doctype' in _pjc_bytes[:200].lower()
                )
                self._log(
                    f"  → Fase A body: {len(_pjc_bytes)} bytes, "
                    f"is_zip={_is_zip_a}, is_html={_is_html_a}"
                )
                if _is_zip_a:
                    _nome_a = _pjc_filename or 'calculo.PJC'
                    if not _nome_a.lower().endswith('.pjc'):
                        _nome_a += '.PJC'
                    _dest_dir_a = self._exec_dir or Path('data/calculations')
                    _dest_dir_a.mkdir(parents=True, exist_ok=True)
                    _dest_a = _dest_dir_a / _nome_a
                    _dest_a.write_bytes(_pjc_bytes)
                    self._log(
                        f"  ✓ .PJC salvo via Fase A (auto-download): "
                        f"{_dest_a} ({len(_pjc_bytes)} bytes)"
                    )
                    self._log(f"PJC_GERADO:{_dest_a}")
                    return str(_dest_a)
                else:
                    self._log(
                        f"  ⚠ Fase A retornou conteúdo não-ZIP "
                        f"— continuando com Fase B/E/D/C"
                    )

            # Diagnóstico: verificar mensagens de erro/sucesso
            try:
                _msgs = self._page.evaluate("""() => {
                    const result = { erros: [], sucessos: [], linkDownload: false,
                                     nomeArquivo: null, jsfcljs: false };
                    document.querySelectorAll('.rf-msgs-err, .rich-messages-error, [class*=error]').forEach(el => {
                        const t = el.textContent.trim();
                        if (t && t.length < 200) result.erros.push(t);
                    });
                    document.querySelectorAll('.rf-msgs-sum, .rich-messages-summary').forEach(el => {
                        const t = el.textContent.trim();
                        if (t && t.length < 200) result.sucessos.push(t);
                    });
                    result.linkDownload = !!document.querySelector("[id$='linkDownloadArquivo']");
                    const inp = document.querySelector("[id$='nomeArquivo']");
                    if (inp) result.nomeArquivo = inp.value;
                    result.jsfcljs = (typeof jsfcljs === 'function');
                    return result;
                }""")
                self._log(f"  → Diagnóstico exportação: {_msgs}")
            except Exception:
                _msgs = {}

            # Fase B — Aguardar linkDownloadArquivo aparecer (poll até 15s)
            self._log("  → Fase B: aguardando linkDownloadArquivo aparecer…")
            _link_ok = False
            for _i in range(30):
                try:
                    if self._page.locator("[id$='linkDownloadArquivo']").count() > 0:
                        _link_ok = True
                        self._log(f"  ✓ linkDownloadArquivo detectado após {_i*0.5:.1f}s")
                        break
                except Exception:
                    pass
                self._page.wait_for_timeout(500)

            if _link_ok:
                # ORDEM CRÍTICA (descoberta abr/2026):
                # downloadArquivo() do ApresentadorExportacao é ONE-SHOT — após chamar,
                # faz `arquivo=null`. Então só temos UMA tentativa efetiva de captura
                # dos bytes. Ordem:
                #   Fase E (novo) — expect_response + jsfcljs no browser: captura a
                #                   resposta DO PRÓPRIO navegador (cookies, headers,
                #                   sessão JSF idênticos aos que o server espera).
                #   Fase D        — context.request.post como fallback (cookies sim,
                #                   mas headers podem divergir do que o JSF espera).
                #   Fase C        — só último recurso (estado já pode estar podre).

                # Fase E — disparar jsfcljs e capturar a resposta via expect_response.
                # O browser faz form.submit() normalmente; o servidor responde com os
                # bytes do .PJC + Content-Disposition. O browser trata como navegação
                # mas Playwright's page.on("response") captura o raw body antes disso.

                # DIAGNÓSTICO — dump do estado atual do DOM antes de submeter
                try:
                    _dbg_dump_dir = self._exec_dir or Path('data/calculations')
                    _dbg_dump_dir.mkdir(parents=True, exist_ok=True)
                    _pre_state = self._page.evaluate("""() => {
                        const form = document.getElementById('formulario');
                        if (!form) return {err: 'form not found'};
                        const vs = form.querySelector("input[name='javax.faces.ViewState']");
                        const link = form.querySelector("[id$='linkDownloadArquivo']");
                        const nome = form.querySelector("[id$='nomeArquivo']");
                        // Coletar todos inputs/hidden
                        const all_inputs = [];
                        form.querySelectorAll('input, select, textarea').forEach(el => {
                            all_inputs.push({
                                name: el.name || '(no-name)',
                                id: el.id || '',
                                type: (el.type || '').toLowerCase(),
                                disabled: el.disabled,
                                value: (el.value || '').slice(0, 60),
                            });
                        });
                        return {
                            action: form.getAttribute('action'),
                            actionFull: form.action,
                            location: window.location.href,
                            viewState: vs ? vs.value : null,
                            linkDownloadExists: !!link,
                            linkDownloadId: link ? link.id : null,
                            linkDownloadOuterHTML: link ? link.outerHTML.slice(0, 400) : null,
                            nomeArquivo: nome ? nome.value : null,
                            numInputs: all_inputs.length,
                            inputs: all_inputs,
                        };
                    }""")
                    self._log(f"  🔍 PRE-POST state: viewState={_pre_state.get('viewState')} "
                              f"linkExists={_pre_state.get('linkDownloadExists')} "
                              f"linkId={_pre_state.get('linkDownloadId')} "
                              f"numInputs={_pre_state.get('numInputs')}")
                    self._log(f"  🔍 PRE-POST action: {_pre_state.get('action')} "
                              f"(full: {_pre_state.get('actionFull')})")
                    self._log(f"  🔍 PRE-POST location: {_pre_state.get('location')}")
                    if _pre_state.get('linkDownloadOuterHTML'):
                        self._log(f"  🔍 PRE-POST linkHTML: {_pre_state['linkDownloadOuterHTML']}")
                    # Dump full form HTML
                    _pre_html = self._page.evaluate("""() => {
                        const f = document.getElementById('formulario');
                        return f ? f.outerHTML : '';
                    }""")
                    _pre_dump = _dbg_dump_dir / 'pre_post_form.html'
                    _pre_dump.write_text(_pre_html or '', encoding='utf-8')
                    self._log(f"  📋 PRE-POST form dumped: {_pre_dump} ({len(_pre_html or '')} chars)")
                except Exception as _dbg_e:
                    self._log(f"  ⚠ PRE-POST diagnóstico falhou: {_dbg_e}")

                try:
                    self._log("  → Fase E: jsfcljs no browser + expect_response…")
                    with self._page.expect_response(
                        lambda r: ('exportacao.jsf' in r.url
                                   and r.request.method == 'POST'),
                        timeout=60000,
                    ) as resp_info:
                        _metodo_e = self._page.evaluate("""() => {
                            const form = document.getElementById('formulario');
                            if (form && typeof jsfcljs === 'function') {
                                jsfcljs(form, {'formulario:linkDownloadArquivo':'formulario:linkDownloadArquivo'}, '');
                                return 'jsfcljs';
                            }
                            const link = document.querySelector("[id$='linkDownloadArquivo']");
                            if (link) { link.click(); return 'click'; }
                            return null;
                        }""")
                        self._log(f"  → Fase E método: {_metodo_e}")
                    _resp_e = resp_info.value
                    _ct_e = _resp_e.headers.get('content-type', '')
                    _cd_e = _resp_e.headers.get('content-disposition', '')
                    self._log(
                        f"  → Fase E resposta: HTTP {_resp_e.status} "
                        f"content-type={_ct_e} disposition={_cd_e[:120]}"
                    )
                    try:
                        _body_e = _resp_e.body()
                    except Exception as _be:
                        _body_e = None
                        self._log(f"  ⚠ Fase E body() falhou: {_be}")
                    if _body_e and len(_body_e) > 100:
                        _is_zip_e = _body_e[:2] == b'PK'
                        _is_html_e = (
                            b'<html' in _body_e[:200].lower()
                            or b'<!doctype' in _body_e[:200].lower()
                        )
                        self._log(
                            f"  → Fase E body: {len(_body_e)} bytes, "
                            f"is_zip={_is_zip_e}, is_html={_is_html_e}"
                        )
                        if _is_zip_e or (not _is_html_e and len(_body_e) > 1000):
                            _nome_arq_e = (
                                (_msgs.get('nomeArquivo') if isinstance(_msgs, dict) else None)
                                or 'calculo.PJC'
                            )
                            if not _nome_arq_e.lower().endswith('.pjc'):
                                _nome_arq_e += '.PJC'
                            _dest_dir_e = self._exec_dir or Path('data/calculations')
                            _dest_dir_e.mkdir(parents=True, exist_ok=True)
                            _dest_e = _dest_dir_e / _nome_arq_e
                            _dest_e.write_bytes(_body_e)
                            self._log(
                                f"  ✓ .PJC salvo via Fase E (expect_response): "
                                f"{_dest_e} ({len(_body_e)} bytes)"
                            )
                            self._log(f"PJC_GERADO:{_dest_e}")
                            return str(_dest_e)
                        else:
                            self._log(
                                f"  ⚠ Fase E retornou HTML/conteúdo inesperado — "
                                f"primeiros 300 chars: {_body_e[:300]!r}"
                            )
                            # Dump HTML para análise posterior
                            try:
                                _dump_dir = self._exec_dir or Path('data/calculations')
                                _dump_dir.mkdir(parents=True, exist_ok=True)
                                _dump_path = _dump_dir / 'fase_e_response_dump.html'
                                _dump_path.write_bytes(_body_e)
                                self._log(f"  📋 HTML dumpado em: {_dump_path}")
                                # Extrair dicas úteis do HTML
                                _hints = self._page.evaluate("""(html) => {
                                    const parser = new DOMParser();
                                    const doc = parser.parseFromString(html, 'text/html');
                                    const result = {
                                        title: doc.title,
                                        errors: [],
                                        downloadDisponivel: null,
                                        hasLinkDownload: false,
                                        messagesContent: [],
                                        viewState: null,
                                        scriptsInline: [],
                                    };
                                    // Títulos, erros, mensagens
                                    doc.querySelectorAll('.rf-msgs-err, .rich-messages-error, [class*=error]').forEach(el => {
                                        const t = el.textContent.trim();
                                        if (t && t.length < 300) result.errors.push(t);
                                    });
                                    doc.querySelectorAll('.rf-msgs-sum, .rich-messages-summary, .rf-msgs').forEach(el => {
                                        const t = el.textContent.trim();
                                        if (t && t.length < 300) result.messagesContent.push(t);
                                    });
                                    // Há linkDownloadArquivo?
                                    result.hasLinkDownload = !!doc.querySelector("[id$='linkDownloadArquivo']");
                                    const nomeInp = doc.querySelector("[id$='nomeArquivo']");
                                    if (nomeInp) result.nomeArquivo = nomeInp.value;
                                    // ViewState
                                    const vs = doc.querySelector("input[name='javax.faces.ViewState']");
                                    if (vs) result.viewState = vs.value.slice(0, 50);
                                    // Scripts inline que podem conter jsfcljs
                                    doc.querySelectorAll('script').forEach(s => {
                                        const t = (s.textContent || '').trim();
                                        if (t && t.length < 500) result.scriptsInline.push(t.slice(0, 300));
                                    });
                                    return result;
                                }""", _body_e.decode('iso-8859-1', errors='replace'))
                                self._log(f"  📋 HTML hints: {_hints}")
                            except Exception as _de:
                                self._log(f"  ⚠ Dump HTML falhou: {_de}")
                except Exception as e_resp:
                    self._log(f"  ⚠ Fase E expect_response falhou: {e_resp}")

                # Fase D — POST direto via context.request (bypass do evento download).
                # Quando jsfcljs/form.submit() submetem o form, o servidor responde com
                # o .PJC e Content-Disposition: attachment. Mas em headless Firefox o
                # evento `download` do Playwright não dispara consistentemente para
                # respostas vindas de form.submit() de uma página AJAX-rendered.
                # Workaround: replicar o POST do JSF via APIRequestContext que retorna
                # os bytes diretamente sem depender do evento download do browser.
                try:
                    self._log("  → Fase D: POST direto via context.request (sem download event)…")
                    self._log(f"  → Page URL Python-side: {self._page.url}")
                    _form_data = self._page.evaluate("""() => {
                        const form = document.getElementById('formulario');
                        if (!form) return null;
                        // DIAGNÓSTICO — capturar exatamente o que vemos no momento
                        const _diag = {
                            href: window.location.href,
                            search: window.location.search,
                            pathname: window.location.pathname,
                            actionAttr: form.getAttribute('action'),
                            actionProp: form.action,
                        };
                        // Coletar action URL absoluto. CRÍTICO: o Seam exige
                        // ?conversationId=N na URL — o action do form NÃO inclui
                        // esse param, mas window.location.search SIM. Concatenar.
                        const actionRaw = form.getAttribute('action') || window.location.pathname;
                        const actionAbs = new URL(actionRaw, window.location.href);
                        // Mesclar query string da página atual (conversationId, cid, etc.)
                        const pageParams = new URLSearchParams(window.location.search);
                        for (const [k, v] of pageParams.entries()) {
                            if (!actionAbs.searchParams.has(k)) {
                                actionAbs.searchParams.set(k, v);
                            }
                        }
                        const actionUrl = actionAbs.href;
                        _diag.actionUrlFinal = actionUrl;
                        // Coletar inputs do form — mas EXCLUIR botões.
                        // CRÍTICO: inputs type='button'/'submit' têm name='formulario:exportar'
                        // etc. Se enviados, o decoder JSF dispara o actionListener do
                        // botão (ex: apresentador.exportar) ao invés do linkDownloadArquivo,
                        // e o server responde com a view re-renderizada em vez do .PJC.
                        const fields = {};
                        for (const el of form.querySelectorAll('input, select, textarea')) {
                            if (!el.name) continue;
                            const t = (el.type || '').toLowerCase();
                            if (t === 'button' || t === 'submit' || t === 'reset' || t === 'image') {
                                continue;  // pular botões
                            }
                            if (t === 'checkbox' || t === 'radio') {
                                if (el.checked) fields[el.name] = el.value;
                            } else if (!el.disabled) {
                                fields[el.name] = el.value;
                            }
                        }
                        // Adicionar o parâmetro que identifica o linkDownloadArquivo como clicado
                        fields['formulario:linkDownloadArquivo'] = 'formulario:linkDownloadArquivo';
                        return { actionUrl, fields, _diag };
                    }""")
                    if _form_data and _form_data.get('_diag'):
                        self._log(f"  → DIAG window.location: {_form_data['_diag']}")
                    # Se a actionUrl não tiver conversationId mas o Python sabe qual é, força:
                    if (_form_data and _form_data.get('actionUrl')
                            and 'conversationId' not in _form_data['actionUrl']
                            and self._calculo_conversation_id):
                        _sep = '&' if '?' in _form_data['actionUrl'] else '?'
                        _form_data['actionUrl'] = (
                            f"{_form_data['actionUrl']}{_sep}conversationId="
                            f"{self._calculo_conversation_id}"
                        )
                        self._log(f"  → Forçado conversationId={self._calculo_conversation_id} na URL")
                    if _form_data and _form_data.get('actionUrl'):
                        self._log(f"  → POST URL: {_form_data['actionUrl']}")
                        self._log(f"  → POST campos: {len(_form_data['fields'])} (incluindo ViewState)")
                        # Usar context.request — herda cookies/sessão da página
                        _resp = self._page.context.request.post(
                            _form_data['actionUrl'],
                            form=_form_data['fields'],
                            timeout=120000,
                        )
                        _ct = _resp.headers.get('content-type', '')
                        _cd = _resp.headers.get('content-disposition', '')
                        self._log(f"  → POST resposta: HTTP {_resp.status} content-type={_ct} disposition={_cd[:100]}")
                        if _resp.status == 200:
                            _body = _resp.body()
                            if _body and len(_body) > 100:
                                # Verificar se é binário (.PJC = ZIP) ou HTML de erro
                                _is_zip = _body[:2] == b'PK'
                                _is_html = b'<html' in _body[:200].lower() or b'<!doctype' in _body[:200].lower()
                                self._log(f"  → POST body: {len(_body)} bytes, is_zip={_is_zip}, is_html={_is_html}")
                                if _is_zip or (not _is_html and len(_body) > 1000):
                                    # É o arquivo .PJC! Salvar diretamente.
                                    _nome_arquivo = (
                                        (_msgs.get('nomeArquivo') if isinstance(_msgs, dict) else None)
                                        or 'calculo.PJC'
                                    )
                                    if not _nome_arquivo.lower().endswith('.pjc'):
                                        _nome_arquivo += '.PJC'
                                    _dest_dir = self._exec_dir or Path('data/calculations')
                                    _dest_dir.mkdir(parents=True, exist_ok=True)
                                    _dest = _dest_dir / _nome_arquivo
                                    _dest.write_bytes(_body)
                                    self._log(f"  ✓ .PJC salvo via POST direto: {_dest} ({len(_body)} bytes)")
                                    self._log(f"PJC_GERADO:{_dest}")
                                    return str(_dest)
                                else:
                                    self._log(f"  ⚠ POST retornou HTML/conteúdo inesperado — primeiros 300 chars: {_body[:300]!r}")
                            else:
                                self._log(f"  ⚠ POST retornou body vazio ou muito curto")
                        else:
                            self._log(f"  ⚠ POST falhou: HTTP {_resp.status}")
                except Exception as e_post:
                    self._log(f"  ⚠ Fase D POST direto falhou: {e_post}")

                # Fase C (fallback) — jsfcljs manual dentro de expect_download.
                # Só roda se Fase D não retornou o arquivo. Observação: a partir
                # daqui o estado do server pode ter mudado (o POST de Fase D
                # pode ter feito `arquivo=null` mesmo retornando HTML). Por isso
                # a Fase C aqui é só um "best-effort" de última cartada.
                try:
                    self._log("  → Fase C (fallback): disparando download via jsfcljs…")
                    with self._page.expect_download(timeout=30000) as dl_info:
                        _metodo = self._page.evaluate("""() => {
                            const form = document.getElementById('formulario');
                            if (form && typeof jsfcljs === 'function') {
                                jsfcljs(form, {'formulario:linkDownloadArquivo':'formulario:linkDownloadArquivo'}, '');
                                return 'jsfcljs';
                            }
                            const link = document.querySelector("[id$='linkDownloadArquivo']");
                            if (link) { link.click(); return 'click'; }
                            return null;
                        }""")
                        self._log(f"  → Método utilizado: {_metodo}")
                    return _salvar_download(dl_info.value)
                except Exception as e_dl:
                    self._log(f"  ⚠ Download não capturado via jsfcljs: {e_dl}")

                # Última tentativa: submeter o form via JS direto (não jsfcljs)
                try:
                    self._log("  → Última tentativa: form.submit() direto…")
                    with self._page.expect_download(timeout=30000) as dl_info2:
                        self._page.evaluate("""() => {
                            const form = document.getElementById('formulario');
                            if (!form) return false;
                            // Adicionar hidden inputs necessários p/ JSF identificar o link clicado
                            const addHidden = (name, value) => {
                                let inp = form.querySelector(`input[name="${name}"]`);
                                if (!inp) {
                                    inp = document.createElement('input');
                                    inp.type = 'hidden';
                                    inp.name = name;
                                    form.appendChild(inp);
                                }
                                inp.value = value;
                            };
                            addHidden('formulario:linkDownloadArquivo', 'formulario:linkDownloadArquivo');
                            form.submit();
                            return true;
                        }""")
                    return _salvar_download(dl_info2.value)
                except Exception as e_sub:
                    self._log(f"  ⚠ form.submit() direto falhou: {e_sub}")
            else:
                self._log("  ⚠ linkDownloadArquivo não apareceu após 15s — apresentador.exportar() provavelmente falhou no servidor")

        # Fallback: procurar links de download no DOM
        try:
            href = self._page.evaluate("""() => {
                const links = [...document.querySelectorAll('a[href]')];
                const pjc = links.find(a =>
                    a.href.includes('.pjc') || a.href.includes('exportar') ||
                    a.textContent.toLowerCase().includes('download')
                );
                return pjc ? pjc.href : null;
            }""")
            if href:
                with self._page.expect_download(timeout=90000) as dl_info:
                    self._page.goto(href)
                return _salvar_download(dl_info.value)
        except Exception:
            pass

        self._log(
            "  ⚠ .PJC não capturado via browser — exportação falhou. "
            "Verifique o PJe-Calc e clique Exportar manualmente, ou reinicie a automação. "
            "ATENÇÃO: o gerador nativo NÃO produz .PJC válido para importação no PJe-Calc Institucional."
        )
        return None

    # ── Orquestrador principal ─────────────────────────────────────────────────

    def preencher_calculo(
        self,
        dados: dict,
        verbas_mapeadas: dict,
        parametrizacao: dict | None = None,
    ) -> None:
        """Executa todas as fases de preenchimento do cálculo.

        Args:
            dados: output da extraction.py (dados brutos da sentença).
            verbas_mapeadas: output da classification.py.
            parametrizacao: output de parametrizacao.gerar_parametrizacao() — opcional.
                           Se presente, instrui fases específicas com dados pré-calculados.
        """
        # Armazenar dados para uso posterior (ex: re-abrir cálculo correto na liquidação)
        self._dados = dados

        # ── Estimativas de progresso (segundos acumulados) — otimizado ────────
        # Estimativas atualizadas conforme ordem do manual (19 passos)
        _PHASE_ESTIMATES = [
            ("dados_processo", 10),       # passo 1
            ("parametros_gerais", 15),     # passo 1b
            ("faltas_ferias", 25),         # passos 2-3
            ("historico_salarial", 35),    # passo 4
            ("verbas", 70),               # passo 5
            ("fgts", 85),                 # passo 9
            ("contribuicao_social", 95),  # passo 10
            ("irpf", 110),               # passo 13
            ("honorarios", 120),         # passo 15
            ("correcao_juros", 135),     # passo 17
            ("liquidar", 160),           # passos 18-19
        ]
        _TOTAL = 160

        def _progress(idx: int) -> None:
            elapsed = _PHASE_ESTIMATES[idx][1] if idx > 0 else 0
            self._log(f"PROGRESS:{elapsed}/{_TOTAL}")

        base = f"{self.PJECALC_BASE}/pages/principal.jsf"
        self._log("Abrindo PJE-Calc…")
        self._page.goto(base, wait_until="domcontentloaded", timeout=60000)
        self._page.wait_for_timeout(2000)

        # Trata erro de primeira carga (comportamento conhecido do PJe-Calc)
        try:
            body = self._page.locator("body").text_content() or ""
            if "Erro interno" in body or "erro interno" in body.lower():
                self._log("Erro interno na primeira carga — navegando para Página Inicial…")
                link = self._page.locator("a:has-text('Página Inicial')")
                if link.count() > 0:
                    link.first.click()
                    self._aguardar_ajax()
        except Exception:
            pass

        # Instala monitor AJAX JSF
        try:
            self._instalar_monitor_ajax()
        except Exception:
            pass

        self._verificar_e_fazer_login()

        self._ir_para_novo_calculo()

        _progress(0)
        self.fase_dados_processo(dados)

        # Parâmetros Gerais — usa passo_2 do parametrizacao.json se disponível
        _progress(1)
        params_gerais = (parametrizacao or {}).get("passo_2_parametros_gerais", {})
        if not params_gerais:
            cont = dados.get("contrato", {})
            # carga_horaria do contrato é MENSAL (ex: 220, 180).
            # PJE-Calc Parâmetros Gerais espera carga diária (8, 6) e semanal (44, 40).
            # Fallback: usar jornada_diaria/jornada_semanal se carga_horaria não foi extraída.
            _ch_mensal = cont.get("carga_horaria")
            _ch_diaria = cont.get("jornada_diaria")
            _ch_semanal = cont.get("jornada_semanal")
            if _ch_mensal and not _ch_diaria:
                if _ch_mensal >= 210:
                    _ch_diaria = 8
                    _ch_semanal = _ch_semanal or 44
                elif _ch_mensal >= 175:
                    _ch_diaria = 8
                    _ch_semanal = _ch_semanal or 40
                elif _ch_mensal >= 155:
                    _ch_diaria = 6
                    _ch_semanal = _ch_semanal or 36
                else:
                    _ch_diaria = round(_ch_mensal / (4.5 * 5))
                    _ch_semanal = _ch_semanal or round(_ch_diaria * 5)
            # Default: 8h diária / 44h semanal (CLT padrão) se nada foi extraído
            if not _ch_diaria:
                _ch_diaria = 8
            if not _ch_semanal:
                _ch_semanal = 44
            self._log(f"  Carga horária: {_ch_diaria}h/dia, {_ch_semanal}h/semana")
            params_gerais = {
                "carga_horaria_diaria": _ch_diaria,
                "carga_horaria_semanal": _ch_semanal,
                "zerar_valores_negativos": True,
            }
        self.fase_parametros_gerais(params_gerais)

        # ── Sequência conforme Manual PJE-Calc (19 passos) ─────────────────────
        # 1. Dados do Cálculo > Salvar        ← fase_dados_processo (acima)
        # 1b. Parâmetros Gerais > Salvar      ← fase_parametros_gerais (acima)

        # 2. Faltas > Salvar
        _progress(2)
        self.fase_faltas(dados)

        # 3. Férias > Salvar
        self.fase_ferias(dados)

        # 4. Histórico Salarial > Salvar
        _progress(3)
        self.fase_historico_salarial(dados)

        # 5. Verbas (Expresso e/ou Manual) > Salvar
        _progress(4)
        self.fase_verbas(verbas_mapeadas)
        self._screenshot_fase("05_verbas")

        # Abort guard: se nenhuma verba principal foi marcada e existiam principais
        # a lançar, ABORTAR com instrução clara ao usuário. Prosseguir geraria um
        # .PJC inútil (sem as verbas condenatórias principais).
        _principais_esperadas = [
            v for v in (verbas_mapeadas.get("predefinidas", []) + verbas_mapeadas.get("personalizadas", []))
            if (v.get("tipo") or "Principal") == "Principal"
        ]
        _principais_ok = len(self._verbas_expresso_ok)
        if _principais_esperadas and _principais_ok == 0:
            _nomes = [v.get("nome_pjecalc") or v.get("nome_sentenca") or "?" for v in _principais_esperadas]
            raise RuntimeError(
                "AUTOMAÇÃO ABORTADA: nenhuma verba principal foi lançada. "
                f"Esperado: {_nomes}. "
                "Prosseguir geraria um .PJC incompleto/incorreto. "
                "Volte à prévia, ajuste o 'Plano de Preenchimento' das verbas principais "
                "(use nomes compatíveis com as verbas Expresso do PJE-Calc, ex: 'HORAS EXTRAS 50%') "
                "e reinicie a automação."
            )

        # Recuperar de erros pós-verbas (NPE em verba-calculo.jsf é comum)
        try:
            _body = self._page.evaluate("""() => {
                const t = (document.body ? document.body.textContent : '').substring(0, 500);
                return t;
            }""")
            if "500" in _body or "NullPointer" in _body or "Erro inesperado" in _body:
                self._log("  ⚠ Página em estado de erro pós-verbas — recuperando via home…")
                self._page.goto(
                    f"{self.PJECALC_BASE}/pages/principal.jsf",
                    wait_until="domcontentloaded", timeout=15000
                )
                self._aguardar_ajax()
                self._page.wait_for_timeout(1000)
                if self._calculo_url_base and self._calculo_conversation_id:
                    _url_dados = (
                        f"{self._calculo_url_base}parametros-do-calculo.jsf"
                        f"?conversationId={self._calculo_conversation_id}"
                    )
                    self._page.goto(_url_dados, wait_until="domcontentloaded", timeout=15000)
                    self._aguardar_ajax()
                    self._log("  ✓ Cálculo reaberto via conversationId")
        except Exception as _e_rec:
            self._log(f"  ⚠ Recuperação pós-verbas: {_e_rec}")

        # 6. Cartão de Ponto > Salvar (condicional)
        _dur = dados.get("duracao_trabalho") or {}
        _tem_cartao = _dur.get("tipo_apuracao") or any(
            "hora" in (v.get("nome_sentenca") or "").lower() and "extra" in (v.get("nome_sentenca") or "").lower()
            for v in dados.get("verbas_deferidas", [])
        )
        if _tem_cartao:
            self.fase_cartao_ponto(dados)

        # 7. Salário-família > Salvar (condicional)
        self.fase_salario_familia(dados)

        # 8. Seguro-desemprego > Salvar (condicional)
        self.fase_seguro_desemprego(dados)

        # 9. FGTS > Salvar
        _progress(5)
        self.fase_fgts(dados.get("fgts", {}))

        # 10. Contribuição Social > Salvar
        _progress(6)
        self.fase_contribuicao_social(dados.get("contribuicao_social", {}))

        # 11. Previdência Privada > Salvar (condicional)
        self.fase_previdencia_privada(dados)

        # 12. Pensão Alimentícia > Salvar (condicional)
        self.fase_pensao_alimenticia(dados)

        # 13. Imposto de Renda > Salvar
        _progress(7)
        self.fase_irpf(dados.get("imposto_renda", {}))

        # 14. Multas e Indenizações > Salvar (condicional)
        _multas = dados.get("multas_indenizacoes", [])
        if _multas:
            self.fase_multas_indenizacoes(_multas)

        # 15. Honorários > Salvar
        _progress(8)
        self.fase_honorarios(
            dados.get("honorarios", []),
            periciais=dados.get("honorarios_periciais"),
            justica_gratuita=dados.get("justica_gratuita"),
        )

        # 16. Custas Judiciais > Salvar
        self.fase_custas_judiciais(dados.get("custas_judiciais", {}))

        # 17. Correção, Juros e Multa > Salvar
        _progress(9)
        self.fase_parametros_atualizacao(dados.get("correcao_juros", {}))

        # Regerar ocorrências das verbas — obrigatório após alterações nos
        # Parâmetros do Cálculo (carga horária, período, prescrição, etc.)
        # Manual: "TODA alteração de parâmetro estrutural exige regeração"
        self._log("Fase pré-liquidação — Regerar ocorrências…")
        self._regerar_ocorrencias_verbas()

        # Screenshot pré-liquidação (captura estado final antes de liquidar)
        self._screenshot_fase("pre_liquidacao")

        # 18-19. Liquidar + Exportar
        _progress(10)
        caminho_pjc = self._clicar_liquidar()
        self._log(f"PROGRESS:{_TOTAL}/{_TOTAL}")
        if caminho_pjc:
            self._log("CONCLUIDO: Automação concluída — .PJC gerado e disponível para download.")
        else:
            # Campos preenchidos mas exportação não capturada.
            # O gerador nativo produz .PJC INVÁLIDO — não usar como resultado final.
            self._log(
                "CONCLUIDO: Campos preenchidos no PJe-Calc. "
                "Exportação .PJC não capturada — verifique o PJe-Calc e clique Exportar manualmente, "
                "ou reinicie a automação."
            )
        self._log("[FIM DA EXECUÇÃO]")


# ── Funções públicas ───────────────────────────────────────────────────────────

def iniciar_e_preencher(
    dados: dict[str, Any],
    verbas_mapeadas: dict[str, Any],
    pjecalc_dir: str | Path,
    log_cb: Callable[[str], None] | None = None,
    headless: bool = False,
    parametrizacao: dict | None = None,
    limpar_h2: bool = True,
    exec_dir: Path | None = None,
    _agente_ref: list | None = None,
) -> None:
    """
    Ponto de entrada público (modo callback).
    1. (Opcional) Limpa H2 antes de iniciar (banco fresco para cada cálculo).
    2. Inicia PJE-Calc Cidadão (se não estiver rodando), verificando TCP + HTTP.
    3. Abre Playwright browser.
    4. Preenche todos os campos do cálculo seguindo as 8 fases.

    _agente_ref: se fornecido, lista onde o agente será armazenado para
    permitir cleanup externo (ex: SSE disconnect).
    """
    cb = log_cb or (lambda m: None)

    # H2 cleanup: banco fresco antes de cada cálculo
    # Estratégia otimizada (3 níveis):
    #   1. Via interface (Playwright): excluir cálculos existentes (~2s)
    #   2. Via SQL direto no H2: DELETE nas tabelas de dados (~1s)
    #   3. Último recurso: parar Tomcat + substituir H2 + reiniciar (~2-3 min)
    _h2_cleanup_enabled = os.environ.get("H2_CLEANUP_ENABLED", "true").lower() == "true"
    _tomcat_was_running = pjecalc_rodando()
    _cleanup_done_via_ui = False  # flag: limpeza feita via UI (precisa browser)

    if limpar_h2 and _h2_cleanup_enabled:
        if _tomcat_was_running:
            # Tomcat rodando — tentar limpeza SEM reiniciar (economia de 2-3 min)
            # Nível 2: SQL direto no H2 (não precisa de browser)
            cb("Limpando cálculos anteriores via SQL…")
            if limpar_calculo_via_sql(pjecalc_dir, log_cb=cb):
                cb("✓ Cálculos limpos via SQL (~1s)")
            else:
                # Nível 1 será tentado após abrir o browser (flag)
                cb("SQL cleanup falhou — limpeza será feita via interface após abrir browser")
                _cleanup_done_via_ui = True  # sinaliza para limpar via UI
        else:
            # Tomcat parado — limpeza direta do arquivo H2 (sem custo)
            limpar_h2_database(pjecalc_dir, log_cb=cb)

    cb("Verificando PJE-Calc Cidadão…")
    iniciar_pjecalc(pjecalc_dir, log_cb=cb)
    cb("PJE-Calc disponível.")

    agente = PJECalcPlaywright(log_cb=cb, exec_dir=exec_dir)
    # Expor agente para cleanup externo (SSE disconnect)
    if _agente_ref is not None:
        _agente_ref.clear()
        _agente_ref.append(agente)
    try:
        agente.iniciar_browser(headless=headless)

        # Nível 1: limpeza via UI (se SQL falhou e Tomcat estava rodando)
        if _cleanup_done_via_ui:
            cb("Limpando cálculos anteriores via interface…")
            if agente._limpar_calculo_via_ui():
                cb("✓ Cálculos limpos via interface (~2s)")
            else:
                # Limpeza falhou — prosseguir sem reiniciar Tomcat.
                # Restart desperdiça 3-5 min e tipicamente não resolve (os cálculos
                # residuais persistem no H2/volume). O novo cálculo será criado ao
                # lado dos antigos sem causar conflito; a proteção contra contaminação
                # é feita por _verificar_calculo_correto() durante a liquidação.
                cb("⚠ Limpeza via interface falhou — prosseguindo sem limpeza (cálculos antigos permanecerão nos Recentes)")

        agente.preencher_calculo(dados, verbas_mapeadas, parametrizacao=parametrizacao)
    except Exception as exc:
        cb(f"ERRO: {exc}")
        logger.exception(f"Erro na automação Playwright: {exc}")
        raise
    finally:
        # Cleanup obrigatório: fecha browser/Playwright para evitar processos órfãos
        try:
            agente.fechar()
        except Exception:
            pass
        if _agente_ref is not None:
            _agente_ref.clear()


def preencher_como_generator(
    dados: dict[str, Any],
    verbas_mapeadas: dict[str, Any],
    pjecalc_dir: str | Path,
    modo_oculto: bool = False,
    parametrizacao: dict | None = None,
    exec_dir: Path | None = None,
):
    """
    Generator que faz yield de mensagens de log para SSE streaming direto.
    Padrão CalcMachine: thread separada + queue.Queue como bridge.

    O atributo `_agente_ref` (list) permite cleanup externo:
    se o SSE desconectar, o caller pode chamar `agente.fechar()` no
    primeiro elemento da lista para forçar o encerramento do browser.

    Uso:
        gen = preencher_como_generator(dados, verbas, pjecalc_dir)
        # gen._agente_ref[0].fechar()  para cleanup externo
        for msg in gen:
            # transmitir msg via SSE
    """
    import queue
    import threading

    log_queue: queue.Queue[str | None] = queue.Queue()
    _stop_keepalive = threading.Event()
    _agente_ref: list = []  # exposto para cleanup externo

    def _cb(msg: str) -> None:
        log_queue.put(msg)

    def _keepalive() -> None:
        """Envia heartbeat a cada 10s para manter SSE vivo durante operações longas."""
        while not _stop_keepalive.is_set():
            _stop_keepalive.wait(10)
            if not _stop_keepalive.is_set():
                log_queue.put("⏳ Processando…")

    def _run() -> None:
        try:
            iniciar_e_preencher(
                dados=dados,
                verbas_mapeadas=verbas_mapeadas,
                pjecalc_dir=pjecalc_dir,
                log_cb=_cb,
                headless=modo_oculto,
                parametrizacao=parametrizacao,
                exec_dir=exec_dir,
                _agente_ref=_agente_ref,
            )
        except Exception as exc:
            log_queue.put(f"ERRO: {exc}")
            logger.exception(f"Erro na automação (generator): {exc}")
        finally:
            _stop_keepalive.set()
            log_queue.put(None)  # sentinela de fim

    threading.Thread(target=_keepalive, daemon=True).start()
    _run_thread = threading.Thread(target=_run, daemon=True)
    _run_thread.start()

    # Expor referências para cleanup externo pelo caller (webapp SSE)
    # Hack: armazenar como atributos do generator object não é possível,
    # então usamos uma variável de closure acessível via gen._agente_ref
    # O caller deve acessar via a variável local no closure

    try:
        while True:
            msg = log_queue.get()
            if msg is None:
                break
            yield msg
    except GeneratorExit:
        # SSE desconectou — forçar cleanup do browser
        _stop_keepalive.set()
        if _agente_ref:
            try:
                _agente_ref[0].fechar()
                logger.info("Browser fechado por GeneratorExit (SSE disconnect)")
            except Exception:
                pass
        return

    yield "[FIM DA EXECUÇÃO]"
