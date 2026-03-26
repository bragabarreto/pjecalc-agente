---
name: test-driven-development
description: Use when implementing any feature or bugfix, before writing implementation code
---

# Test-Driven Development Skill

> **Atenção:** Este é um stub. O conteúdo completo desta skill precisa ser re-instalado
> via Claude Code plugin marketplace (`test-driven-development`).
>
> Estrutura original tinha: `SKILL.md`, `testing-anti-patterns.md`

## Fluxo TDD

```
1. RED   → Escreva o teste que falha
2. GREEN → Escreva o mínimo de código para passar
3. REFACTOR → Limpe sem quebrar os testes
```

## Para este projeto

Testes estão em `tests/`. Execute com:
```bash
python -m pytest tests/ -v
```

Anti-padrões a evitar:
- Mockar o banco nos testes de integração (use SQLite em memória)
- Testar implementação em vez de comportamento
- Testes que dependem de ordem de execução
