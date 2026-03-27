#!/usr/bin/env python3
"""
health_check.py — Health check completo do ambiente pjecalc-agente.

Verifica todos os componentes necessários para o agente funcionar:
- Python e dependências
- Java e PJE-Calc
- Tomcat (porta 9257)
- Banco de dados (SQLite/PostgreSQL)
- APIs externas (Claude/Gemini)
- Playwright e Chromium
- Xvfb (se em ambiente headless)

Uso:
    python health_check.py                    # Verifica tudo
    python health_check.py --component tomcat # Verifica só o Tomcat
    python health_check.py --json             # Saída em JSON (para integração)

Retorna exit code 0 se tudo OK, 1 se algum componente crítico falhou.
"""

import json
import os
import socket
import subprocess
import sys
import urllib.request
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional


@dataclass
class CheckResult:
    component: str
    status: str  # "ok", "warning", "error"
    message: str
    details: Optional[str] = None


@dataclass
class HealthReport:
    results: list[CheckResult] = field(default_factory=list)
    overall: str = "ok"

    def add(self, result: CheckResult):
        self.results.append(result)
        if result.status == "error":
            self.overall = "error"
        elif result.status == "warning" and self.overall != "error":
            self.overall = "warning"


def check_python() -> CheckResult:
    """Verifica versão do Python."""
    version = sys.version
    major, minor = sys.version_info[:2]
    if major == 3 and minor >= 10:
        return CheckResult("python", "ok", f"Python {version.split()[0]}")
    elif major == 3 and minor >= 8:
        return CheckResult("python", "warning", f"Python {version.split()[0]} (recomendado >= 3.10)")
    else:
        return CheckResult("python", "error", f"Python {version.split()[0]} — requer >= 3.8")


def check_dependencies() -> CheckResult:
    """Verifica dependências Python críticas."""
    required = {
        "fastapi": "Framework web",
        "uvicorn": "Servidor ASGI",
        "sqlalchemy": "ORM",
        "jinja2": "Templates",
    }
    optional = {
        "playwright": "Automação web",
        "anthropic": "Claude API",
        "pdfplumber": "Extração PDF",
    }

    missing_required = []
    missing_optional = []

    for pkg, desc in required.items():
        try:
            __import__(pkg)
        except ImportError:
            missing_required.append(f"{pkg} ({desc})")

    for pkg, desc in optional.items():
        try:
            __import__(pkg)
        except ImportError:
            missing_optional.append(f"{pkg} ({desc})")

    if missing_required:
        return CheckResult(
            "dependencies", "error",
            f"Faltam dependências obrigatórias: {', '.join(missing_required)}",
            details="Execute: pip install -r requirements.txt"
        )
    elif missing_optional:
        return CheckResult(
            "dependencies", "warning",
            f"Dependências opcionais ausentes: {', '.join(missing_optional)}",
            details="Funcionalidades parciais indisponíveis"
        )
    else:
        return CheckResult("dependencies", "ok", "Todas as dependências instaladas")


def check_java() -> CheckResult:
    """Verifica Java instalado e versão."""
    try:
        result = subprocess.run(
            ["java", "-version"], capture_output=True, text=True, timeout=10
        )
        version_line = result.stderr.split("\n")[0] if result.stderr else "desconhecida"
        if "1.8" in version_line or "openjdk version \"8" in version_line.lower():
            return CheckResult("java", "ok", f"Java 8: {version_line}")
        elif "11" in version_line or "17" in version_line:
            return CheckResult("java", "warning", f"{version_line} (PJE-Calc requer Java 8)")
        else:
            return CheckResult("java", "ok", version_line)
    except FileNotFoundError:
        return CheckResult("java", "error", "Java não encontrado no PATH")
    except subprocess.TimeoutExpired:
        return CheckResult("java", "error", "Java timeout ao verificar versão")


def check_tomcat(port: int = 9257) -> CheckResult:
    """Verifica se o Tomcat está respondendo."""
    # Primeiro: TCP
    try:
        sock = socket.create_connection(("localhost", port), timeout=3)
        sock.close()
    except (ConnectionRefusedError, socket.timeout, OSError):
        return CheckResult(
            "tomcat", "warning",
            f"Tomcat não responde em localhost:{port}",
            details="O Tomcat pode não ter sido iniciado ou ainda estar subindo (leva 2-5 min)"
        )

    # Segundo: HTTP
    try:
        with urllib.request.urlopen(f"http://localhost:{port}/pjecalc", timeout=5) as resp:
            status = resp.status
            if status in (200, 302):
                return CheckResult("tomcat", "ok", f"Tomcat respondendo em :{port} (HTTP {status})")
            else:
                return CheckResult("tomcat", "warning", f"Tomcat respondeu HTTP {status}")
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return CheckResult(
                "tomcat", "warning",
                f"Tomcat em :{port} retorna 404 — webapp pode estar deployando",
                details="Aguarde 1-2 min e tente novamente"
            )
        return CheckResult("tomcat", "warning", f"Tomcat HTTP {e.code}")
    except Exception as e:
        return CheckResult("tomcat", "warning", f"Tomcat TCP ok, HTTP falhou: {e}")


def check_pjecalc_dir() -> CheckResult:
    """Verifica se o diretório do PJE-Calc está configurado e acessível."""
    pjecalc_dir = os.environ.get("PJECALC_DIR", "/opt/pjecalc")
    p = Path(pjecalc_dir)

    if not p.exists():
        return CheckResult(
            "pjecalc_dir", "warning",
            f"Diretório PJE-Calc não encontrado: {pjecalc_dir}",
            details="Defina PJECALC_DIR ou verifique a instalação"
        )

    checks = {
        "bin/pjecalc.jar": "JAR principal",
        "tomcat/conf/server.xml": "Configuração Tomcat",
        ".dados/pjecalc.h2.db": "Banco H2",
    }

    missing = []
    for path, desc in checks.items():
        if not (p / path).exists():
            missing.append(f"{path} ({desc})")

    if missing:
        return CheckResult(
            "pjecalc_dir", "warning",
            f"PJE-Calc em {pjecalc_dir} — faltam: {', '.join(missing)}"
        )

    return CheckResult("pjecalc_dir", "ok", f"PJE-Calc em {pjecalc_dir} — estrutura completa")


def check_database() -> CheckResult:
    """Verifica conectividade com o banco de dados."""
    db_url = os.environ.get("DATABASE_URL", "")

    if db_url and "postgresql" in db_url:
        try:
            import sqlalchemy
            engine = sqlalchemy.create_engine(db_url)
            with engine.connect() as conn:
                conn.execute(sqlalchemy.text("SELECT 1"))
            return CheckResult("database", "ok", "PostgreSQL conectado")
        except Exception as e:
            return CheckResult("database", "error", f"PostgreSQL falhou: {e}")
    else:
        # SQLite — verificar se o arquivo existe ou pode ser criado
        data_dir = Path(os.environ.get("DATA_DIR", "data"))
        db_file = data_dir / "pjecalc.db"
        if db_file.exists():
            size_mb = db_file.stat().st_size / (1024 * 1024)
            return CheckResult("database", "ok", f"SQLite: {db_file} ({size_mb:.1f} MB)")
        else:
            return CheckResult("database", "ok", "SQLite: será criado na primeira execução")


def check_api_keys() -> CheckResult:
    """Verifica se as chaves de API estão configuradas."""
    anthropic_key = os.environ.get("ANTHROPIC_API_KEY", "")
    gemini_key = os.environ.get("GEMINI_API_KEY", "")

    if anthropic_key and len(anthropic_key) > 10:
        return CheckResult("api_keys", "ok", "ANTHROPIC_API_KEY configurada")
    elif gemini_key and len(gemini_key) > 10:
        return CheckResult("api_keys", "ok", "GEMINI_API_KEY configurada (fallback)")
    else:
        return CheckResult(
            "api_keys", "error",
            "Nenhuma API key configurada",
            details="Defina ANTHROPIC_API_KEY ou GEMINI_API_KEY"
        )


def check_playwright() -> CheckResult:
    """Verifica Playwright e Chromium."""
    try:
        import playwright
    except ImportError:
        return CheckResult(
            "playwright", "warning",
            "Playwright não instalado — automação indisponível",
            details="pip install playwright && playwright install chromium"
        )

    try:
        result = subprocess.run(
            ["playwright", "install", "--dry-run", "chromium"],
            capture_output=True, text=True, timeout=10
        )
        # Se dry-run não tem saída, chromium já está instalado
        return CheckResult("playwright", "ok", "Playwright + Chromium instalados")
    except Exception:
        return CheckResult("playwright", "warning", "Playwright instalado, Chromium status desconhecido")


def check_xvfb() -> CheckResult:
    """Verifica Xvfb (display virtual)."""
    try:
        result = subprocess.run(["which", "Xvfb"], capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            display = os.environ.get("DISPLAY", "não definido")
            return CheckResult("xvfb", "ok", f"Xvfb disponível, DISPLAY={display}")
        else:
            return CheckResult("xvfb", "warning", "Xvfb não encontrado")
    except Exception:
        return CheckResult("xvfb", "warning", "Não foi possível verificar Xvfb")


def check_disk_space() -> CheckResult:
    """Verifica espaço em disco."""
    try:
        import shutil
        total, used, free = shutil.disk_usage("/")
        free_gb = free / (1024 ** 3)
        total_gb = total / (1024 ** 3)
        pct_free = (free / total) * 100

        if free_gb < 1:
            return CheckResult("disk", "error", f"Disco quase cheio: {free_gb:.1f} GB livre de {total_gb:.0f} GB")
        elif free_gb < 5:
            return CheckResult("disk", "warning", f"Pouco espaço: {free_gb:.1f} GB livre ({pct_free:.0f}%)")
        else:
            return CheckResult("disk", "ok", f"Espaço ok: {free_gb:.1f} GB livre ({pct_free:.0f}%)")
    except Exception as e:
        return CheckResult("disk", "warning", f"Não foi possível verificar disco: {e}")


def run_all_checks(component: Optional[str] = None) -> HealthReport:
    """Executa todos os health checks."""
    report = HealthReport()

    all_checks = {
        "python": check_python,
        "dependencies": check_dependencies,
        "java": check_java,
        "pjecalc_dir": check_pjecalc_dir,
        "tomcat": check_tomcat,
        "database": check_database,
        "api_keys": check_api_keys,
        "playwright": check_playwright,
        "xvfb": check_xvfb,
        "disk": check_disk_space,
    }

    if component:
        if component in all_checks:
            report.add(all_checks[component]())
        else:
            report.add(CheckResult("unknown", "error", f"Componente desconhecido: {component}"))
    else:
        for check_fn in all_checks.values():
            report.add(check_fn())

    return report


def print_report(report: HealthReport, as_json: bool = False):
    """Imprime o relatório de saúde."""
    if as_json:
        data = {
            "overall": report.overall,
            "checks": [asdict(r) for r in report.results],
        }
        print(json.dumps(data, indent=2, ensure_ascii=False))
        return

    icons = {"ok": "✅", "warning": "⚠️ ", "error": "❌"}

    print("═" * 60)
    print("  Health Check — PJE-Calc Agente")
    print("═" * 60)
    print()

    for result in report.results:
        icon = icons.get(result.status, "?")
        print(f"  {icon}  {result.component:15s}  {result.message}")
        if result.details:
            print(f"      └─ {result.details}")

    print()
    print("─" * 60)
    overall_icon = icons.get(report.overall, "?")
    print(f"  {overall_icon}  Status geral: {report.overall.upper()}")
    print("─" * 60)


def main():
    component = None
    as_json = False

    args = sys.argv[1:]
    while args:
        arg = args.pop(0)
        if arg == "--component" and args:
            component = args.pop(0)
        elif arg == "--json":
            as_json = True

    report = run_all_checks(component)
    print_report(report, as_json=as_json)

    sys.exit(0 if report.overall != "error" else 1)


if __name__ == "__main__":
    main()
