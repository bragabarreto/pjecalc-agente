#!/usr/bin/env python3
"""
split_webapp.py — Divide o webapp.py monolítico em módulos FastAPI organizados.

Analisa o webapp.py e gera uma proposta de divisão em routers separados.
Não modifica o arquivo original — gera os novos arquivos em um diretório de saída.

Uso:
    python split_webapp.py /caminho/para/webapp.py
    python split_webapp.py /caminho/para/webapp.py --output /caminho/para/saida
    python split_webapp.py /caminho/para/webapp.py --dry-run  # Apenas mostra o plano

Lógica de categorização:
- Rotas GET que retornam HTML → routes/pages.py
- Rotas POST/PATCH/DELETE /api/* → routes/api.py
- Rotas GET /api/logs/*, /api/ps, /api/screenshot → routes/diagnostics.py
- Rotas SSE (StreamingResponse) → routes/sse.py
- Funções auxiliares sem decorator de rota → services/
"""

import ast
import re
import sys
from collections import defaultdict
from pathlib import Path


# Categorias de rotas
CATEGORIES = {
    "pages": {
        "description": "Páginas HTML (GET que retornam template)",
        "filename": "routes/pages.py",
        "patterns": [],  # Decidido por heurística
    },
    "api": {
        "description": "API REST (POST/PATCH/DELETE + GET de dados)",
        "filename": "routes/api.py",
        "patterns": ["/api/"],
    },
    "diagnostics": {
        "description": "Endpoints de diagnóstico (logs, ps, screenshot)",
        "filename": "routes/diagnostics.py",
        "patterns": ["/api/logs/", "/api/ps", "/api/screenshot", "/api/verificar"],
    },
    "sse": {
        "description": "Server-Sent Events (streaming)",
        "filename": "routes/sse.py",
        "patterns": [],  # Decidido por StreamingResponse
    },
}


def parse_webapp(filepath: Path) -> dict:
    """Analisa o webapp.py e extrai rotas, helpers e imports."""
    source = filepath.read_text(encoding="utf-8")
    lines = source.splitlines()
    tree = ast.parse(source)

    routes = []
    helpers = []
    imports_block = []
    global_vars = []

    for node in ast.iter_child_nodes(tree):
        # Imports
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            imports_block.append({
                "start": node.lineno,
                "end": node.end_lineno or node.lineno,
                "code": "\n".join(lines[node.lineno - 1 : (node.end_lineno or node.lineno)]),
            })

        # Assign (variáveis globais)
        elif isinstance(node, ast.Assign):
            global_vars.append({
                "start": node.lineno,
                "end": node.end_lineno or node.lineno,
                "code": "\n".join(lines[node.lineno - 1 : (node.end_lineno or node.lineno)]),
            })

        # Funções e rotas
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            is_route = False
            http_method = None
            path = None
            has_streaming = False

            for decorator in node.decorator_list:
                dec_source = ast.get_source_segment(source, decorator) or ""
                if any(m in dec_source for m in [".get(", ".post(", ".put(", ".patch(", ".delete("]):
                    is_route = True
                    for m in ["get", "post", "put", "patch", "delete"]:
                        if f".{m}(" in dec_source:
                            http_method = m.upper()
                            break
                    # Extrair path
                    match = re.search(r'\("([^"]+)"\)', dec_source)
                    if match:
                        path = match.group(1)

            # Verificar se retorna StreamingResponse (SSE)
            func_source = "\n".join(lines[node.lineno - 1 : (node.end_lineno or node.lineno)])
            if "StreamingResponse" in func_source or "text/event-stream" in func_source:
                has_streaming = True

            entry = {
                "name": node.name,
                "start": node.lineno,
                "end": node.end_lineno or node.lineno,
                "code": func_source,
                "is_route": is_route,
                "method": http_method,
                "path": path,
                "has_streaming": has_streaming,
                "decorators": [ast.get_source_segment(source, d) or "" for d in node.decorator_list],
            }

            if is_route:
                routes.append(entry)
            else:
                helpers.append(entry)

        # Classes
        elif isinstance(node, ast.ClassDef):
            class_source = "\n".join(lines[node.lineno - 1 : (node.end_lineno or node.lineno)])
            helpers.append({
                "name": node.name,
                "start": node.lineno,
                "end": node.end_lineno or node.lineno,
                "code": class_source,
                "is_route": False,
                "is_class": True,
            })

    return {
        "routes": routes,
        "helpers": helpers,
        "imports": imports_block,
        "global_vars": global_vars,
        "total_lines": len(lines),
    }


def categorize_route(route: dict) -> str:
    """Determina a categoria de uma rota."""
    path = route.get("path", "") or ""

    # SSE tem prioridade
    if route.get("has_streaming"):
        return "sse"

    # Diagnóstico
    for pattern in CATEGORIES["diagnostics"]["patterns"]:
        if pattern in path:
            return "diagnostics"

    # API (POST/PATCH/DELETE ou GET /api/)
    if route.get("method") in ("POST", "PATCH", "PUT", "DELETE"):
        return "api"
    if "/api/" in path:
        return "api"

    # Páginas HTML (GET sem /api/)
    if route.get("method") == "GET":
        return "pages"

    return "api"  # fallback


def generate_plan(analysis: dict) -> dict:
    """Gera o plano de divisão."""
    plan = defaultdict(lambda: {"routes": [], "helpers": [], "line_count": 0})

    for route in analysis["routes"]:
        category = categorize_route(route)
        plan[category]["routes"].append(route)
        plan[category]["line_count"] += route["end"] - route["start"] + 1

    # Helpers vão para services/processing.py (background tasks) ou services/utils.py
    for helper in analysis["helpers"]:
        plan["services"]["helpers"].append(helper)
        plan["services"]["line_count"] += helper["end"] - helper["start"] + 1

    return dict(plan)


def print_plan(analysis: dict, plan: dict):
    """Imprime o plano de divisão."""
    print("═" * 60)
    print("  Plano de Divisão do webapp.py")
    print(f"  Total: {analysis['total_lines']} linhas → {len(plan)} módulos")
    print("═" * 60)
    print()

    for category, data in sorted(plan.items()):
        cat_info = CATEGORIES.get(category, {"description": "Serviços e helpers", "filename": f"services/{category}.py"})
        print(f"📁 {cat_info['filename']}")
        print(f"   {cat_info['description']}")
        print(f"   ~{data['line_count']} linhas")

        if data.get("routes"):
            print(f"   Rotas ({len(data['routes'])}):")
            for r in data["routes"]:
                method = r.get("method", "?")
                path = r.get("path", "?")
                print(f"     {method:6s} {path:40s}  ({r['name']})")

        if data.get("helpers"):
            print(f"   Helpers ({len(data['helpers'])}):")
            for h in data["helpers"]:
                kind = "class" if h.get("is_class") else "def"
                print(f"     {kind:5s} {h['name']}")

        print()

    # Novo webapp.py residual
    print("📁 webapp.py (refatorado)")
    print("   Apenas: app = FastAPI(...), include_router(), middleware, startup events")
    print("   ~30-50 linhas")
    print()


def generate_files(analysis: dict, plan: dict, output_dir: Path):
    """Gera os arquivos divididos."""
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "routes").mkdir(exist_ok=True)
    (output_dir / "services").mkdir(exist_ok=True)

    generated = []

    for category, data in plan.items():
        cat_info = CATEGORIES.get(category, {"filename": f"services/{category}.py"})
        filepath = output_dir / cat_info["filename"]

        parts = []
        parts.append(f'"""Módulo gerado por split_webapp.py — {CATEGORIES.get(category, {}).get("description", category)}"""')
        parts.append("")
        parts.append("from fastapi import APIRouter, Request, Depends, HTTPException")
        parts.append("from fastapi.responses import JSONResponse, HTMLResponse")
        parts.append("")
        parts.append(f'router = APIRouter(tags=["{category}"])')
        parts.append("")

        for route in data.get("routes", []):
            # Substituir @app.method por @router.method
            code = route["code"]
            code = re.sub(r"@app\.(get|post|put|patch|delete)", r"@router.\1", code)
            parts.append(code)
            parts.append("")

        for helper in data.get("helpers", []):
            parts.append(helper["code"])
            parts.append("")

        filepath.write_text("\n".join(parts), encoding="utf-8")
        generated.append(filepath)

    # Gerar novo webapp.py
    main_app = output_dir / "webapp_refactored.py"
    main_parts = [
        '"""webapp.py refatorado — apenas setup e roteamento."""',
        "",
        "from fastapi import FastAPI",
        "from fastapi.staticfiles import StaticFiles",
        "from fastapi.templating import Jinja2Templates",
        "from pathlib import Path",
        "",
        "app = FastAPI(",
        '    title="Agente PJE-Calc",',
        '    description="Automação de Liquidação de Sentenças Trabalhistas",',
        '    version="2.0.0",',
        ")",
        "",
        "# Templates e estáticos",
        'templates = Jinja2Templates(directory="templates")',
        'app.mount("/static", StaticFiles(directory="static"), name="static")',
        "",
        "# Registrar routers",
    ]

    for category in plan:
        cat_info = CATEGORIES.get(category, {"filename": f"services/{category}.py"})
        module = cat_info["filename"].replace("/", ".").replace(".py", "")
        main_parts.append(f"from {module} import router as {category}_router")

    main_parts.append("")
    for category in plan:
        if category != "services":
            prefix = "" if category == "pages" else f"/api" if category != "sse" else ""
            main_parts.append(f"app.include_router({category}_router)")

    main_parts.append("")
    main_app.write_text("\n".join(main_parts), encoding="utf-8")
    generated.append(main_app)

    # __init__.py
    for d in ["routes", "services"]:
        init = output_dir / d / "__init__.py"
        init.write_text("", encoding="utf-8")
        generated.append(init)

    return generated


def main():
    if len(sys.argv) < 2:
        print("Uso: python split_webapp.py /caminho/para/webapp.py [--output DIR] [--dry-run]")
        sys.exit(1)

    webapp_path = Path(sys.argv[1])
    if not webapp_path.exists():
        print(f"Erro: '{webapp_path}' não encontrado.")
        sys.exit(1)

    dry_run = "--dry-run" in sys.argv
    output_dir = Path("webapp_split_output")
    for i, arg in enumerate(sys.argv):
        if arg == "--output" and i + 1 < len(sys.argv):
            output_dir = Path(sys.argv[i + 1])

    print(f"Analisando: {webapp_path}")
    analysis = parse_webapp(webapp_path)
    plan = generate_plan(analysis)

    print_plan(analysis, plan)

    if dry_run:
        print("(--dry-run: nenhum arquivo gerado)")
        return

    generated = generate_files(analysis, plan, output_dir)
    print(f"✅ {len(generated)} arquivos gerados em: {output_dir}/")
    for f in generated:
        print(f"   {f.relative_to(output_dir)}")


if __name__ == "__main__":
    main()
