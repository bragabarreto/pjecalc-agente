#!/usr/bin/env python3
"""
find_dead_code.py — Identifica código morto no repositório pjecalc-agente.

Analisa:
1. Funções/classes definidas mas nunca referenciadas em outros arquivos
2. Imports não utilizados
3. Rotas HTTP definidas mas possivelmente órfãs
4. Arquivos Python que não são importados por ninguém

Uso:
    python find_dead_code.py /caminho/para/pjecalc-agente
    python find_dead_code.py .  # se já estiver no diretório do repo

Saída: relatório em texto com candidatos a remoção, organizados por prioridade.
"""

import ast
import os
import re
import sys
from collections import defaultdict
from pathlib import Path


def find_python_files(repo_dir: Path) -> list[Path]:
    """Encontra todos os .py no repo, excluindo venv/node_modules/.git."""
    skip = {"venv", "node_modules", ".git", "__pycache__", "pjecalc-dist"}
    result = []
    for root, dirs, files in os.walk(repo_dir):
        dirs[:] = [d for d in dirs if d not in skip]
        for f in files:
            if f.endswith(".py"):
                result.append(Path(root) / f)
    return result


def extract_definitions(filepath: Path) -> dict:
    """Extrai funções, classes e rotas de um arquivo Python."""
    try:
        source = filepath.read_text(encoding="utf-8", errors="replace")
        tree = ast.parse(source)
    except (SyntaxError, UnicodeDecodeError):
        return {"functions": [], "classes": [], "routes": [], "imports": []}

    functions = []
    classes = []
    routes = []
    imports = []

    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) or isinstance(node, ast.AsyncFunctionDef):
            # Detectar rotas FastAPI/Flask
            is_route = False
            for decorator in node.decorator_list:
                dec_str = ast.dump(decorator)
                if any(method in dec_str for method in ["get", "post", "put", "patch", "delete"]):
                    # Tentar extrair o path da rota
                    if isinstance(decorator, ast.Call) and decorator.args:
                        if isinstance(decorator.args[0], ast.Constant):
                            routes.append({
                                "name": node.name,
                                "path": decorator.args[0].value,
                                "line": node.lineno,
                            })
                            is_route = True
            functions.append({
                "name": node.name,
                "line": node.lineno,
                "is_route": is_route,
                "is_private": node.name.startswith("_"),
            })
        elif isinstance(node, ast.ClassDef):
            classes.append({"name": node.name, "line": node.lineno})
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            if isinstance(node, ast.ImportFrom) and node.module:
                imports.append({"module": node.module, "line": node.lineno})
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    imports.append({"module": alias.name, "line": node.lineno})

    return {
        "functions": functions,
        "classes": classes,
        "routes": routes,
        "imports": imports,
    }


def find_references(name: str, all_files: list[Path], defining_file: Path) -> list[Path]:
    """Encontra arquivos que referenciam um nome (excluindo o arquivo de definição)."""
    refs = []
    pattern = re.compile(r"\b" + re.escape(name) + r"\b")
    for fp in all_files:
        if fp == defining_file:
            continue
        try:
            content = fp.read_text(encoding="utf-8", errors="replace")
            if pattern.search(content):
                refs.append(fp)
        except Exception:
            pass
    return refs


def analyze_routes_usage(routes: list[dict], all_files: list[Path], repo_dir: Path) -> list[dict]:
    """Verifica se rotas são referenciadas em templates HTML ou JS."""
    template_files = []
    for root, dirs, files in os.walk(repo_dir):
        for f in files:
            if f.endswith((".html", ".js", ".jsx", ".ts")):
                template_files.append(Path(root) / f)

    orphan_routes = []
    for route in routes:
        path = route["path"]
        # Simplificar path para busca (remover parâmetros FastAPI)
        search_path = re.sub(r"\{[^}]+\}", "", path).rstrip("/")
        if not search_path or search_path == "/":
            continue

        found = False
        for tf in template_files:
            try:
                content = tf.read_text(encoding="utf-8", errors="replace")
                if search_path in content:
                    found = True
                    break
            except Exception:
                pass

        # Também buscar em arquivos Python (chamadas internas)
        if not found:
            for pf in all_files:
                try:
                    content = pf.read_text(encoding="utf-8", errors="replace")
                    if search_path in content and route["name"] not in content.split("def " + route["name"])[0][-50:]:
                        found = True
                        break
                except Exception:
                    pass

        if not found:
            orphan_routes.append(route)

    return orphan_routes


def find_unreferenced_modules(all_files: list[Path], repo_dir: Path) -> list[Path]:
    """Encontra módulos .py que não são importados por nenhum outro arquivo."""
    # Arquivos que são entry points (não precisam ser importados)
    entry_points = {"webapp.py", "main.py", "config.py", "__init__.py", "launcher.pyw"}

    unreferenced = []
    for fp in all_files:
        if fp.name in entry_points:
            continue

        # Nome do módulo (sem .py)
        module_name = fp.stem
        # Caminho relativo para import (ex: modules.extraction)
        try:
            rel = fp.relative_to(repo_dir)
        except ValueError:
            continue

        module_path = ".".join(rel.with_suffix("").parts)

        found = False
        for other in all_files:
            if other == fp:
                continue
            try:
                content = other.read_text(encoding="utf-8", errors="replace")
                if module_name in content:
                    found = True
                    break
            except Exception:
                pass

        if not found:
            unreferenced.append(fp)

    return unreferenced


def main(repo_dir: str):
    repo = Path(repo_dir).resolve()
    if not repo.exists():
        print(f"Erro: diretório '{repo_dir}' não encontrado.")
        sys.exit(1)

    print(f"=== Análise de Código Morto: {repo} ===\n")

    all_files = find_python_files(repo)
    print(f"Arquivos Python encontrados: {len(all_files)}\n")

    # 1. Funções não referenciadas
    print("─" * 60)
    print("1. FUNÇÕES POSSIVELMENTE NÃO UTILIZADAS")
    print("─" * 60)
    unreferenced_funcs = []
    for fp in all_files:
        defs = extract_definitions(fp)
        for func in defs["functions"]:
            if func["is_private"] or func["is_route"]:
                continue  # Pular privadas e rotas (rotas são chamadas via HTTP)
            refs = find_references(func["name"], all_files, fp)
            if not refs:
                unreferenced_funcs.append((fp, func))

    if unreferenced_funcs:
        for fp, func in sorted(unreferenced_funcs, key=lambda x: str(x[0])):
            rel = fp.relative_to(repo)
            print(f"  {rel}:{func['line']}  →  {func['name']}()")
    else:
        print("  Nenhuma encontrada.")
    print()

    # 2. Classes não referenciadas
    print("─" * 60)
    print("2. CLASSES POSSIVELMENTE NÃO UTILIZADAS")
    print("─" * 60)
    unreferenced_classes = []
    for fp in all_files:
        defs = extract_definitions(fp)
        for cls in defs["classes"]:
            refs = find_references(cls["name"], all_files, fp)
            if not refs:
                unreferenced_classes.append((fp, cls))

    if unreferenced_classes:
        for fp, cls in sorted(unreferenced_classes, key=lambda x: str(x[0])):
            rel = fp.relative_to(repo)
            print(f"  {rel}:{cls['line']}  →  class {cls['name']}")
    else:
        print("  Nenhuma encontrada.")
    print()

    # 3. Rotas possivelmente órfãs
    print("─" * 60)
    print("3. ROTAS HTTP POSSIVELMENTE ÓRFÃS")
    print("─" * 60)
    all_routes = []
    for fp in all_files:
        defs = extract_definitions(fp)
        for route in defs["routes"]:
            route["file"] = fp
            all_routes.append(route)

    orphans = analyze_routes_usage(all_routes, all_files, repo)
    if orphans:
        for route in orphans:
            rel = route["file"].relative_to(repo)
            print(f"  {rel}:{route['line']}  →  {route['path']}  ({route['name']})")
    else:
        print("  Nenhuma encontrada.")
    print()

    # 4. Módulos não importados
    print("─" * 60)
    print("4. MÓDULOS PYTHON NÃO IMPORTADOS POR NINGUÉM")
    print("─" * 60)
    unreferenced_modules = find_unreferenced_modules(all_files, repo)
    if unreferenced_modules:
        for fp in sorted(unreferenced_modules):
            rel = fp.relative_to(repo)
            lines = len(fp.read_text(encoding="utf-8", errors="replace").splitlines())
            print(f"  {rel}  ({lines} linhas)")
    else:
        print("  Nenhum encontrado.")
    print()

    # Resumo
    total = len(unreferenced_funcs) + len(unreferenced_classes) + len(orphans) + len(unreferenced_modules)
    print("═" * 60)
    print(f"RESUMO: {total} candidatos a revisão encontrados")
    print(f"  - {len(unreferenced_funcs)} funções não referenciadas")
    print(f"  - {len(unreferenced_classes)} classes não referenciadas")
    print(f"  - {len(orphans)} rotas possivelmente órfãs")
    print(f"  - {len(unreferenced_modules)} módulos não importados")
    print()
    print("⚠️  Estes são CANDIDATOS — verifique manualmente antes de remover.")
    print("    Funções podem ser chamadas dinamicamente (getattr, templates, etc.)")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Uso: python find_dead_code.py /caminho/para/pjecalc-agente")
        sys.exit(1)
    main(sys.argv[1])
