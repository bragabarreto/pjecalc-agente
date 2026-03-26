---
name: playwright-skill
description: Battle-tested Playwright patterns for E2E, API, component, visual, accessibility, and security testing. Covers locators, fixtures, POM, network mocking, auth flows, debugging, CI/CD (GitHub Actions, GitLab, CircleCI, Azure, Jenkins), framework recipes (React, Next.js, Vue, Angular), and migration guides from Cypress/Selenium. TypeScript and JavaScript.
license: MIT
---

# Playwright Skill

> **Atenção:** Este é um stub. O conteúdo completo desta skill precisa ser re-instalado
> via Claude Code plugin marketplace (`playwright-skill`).
>
> Estrutura original tinha: `core/` (60+ guias), `ci/`, `migration/`, `playwright-cli/`, `pom/`

## Referência rápida para este projeto

O agente usa Playwright em `modules/playwright_pjecalc.py` para automatizar o PJE-Calc (JSF/RichFaces, Tomcat 7, porta 9257).

### Padrões críticos para JSF/RichFaces

```python
# Aguardar AJAX após cada ação
await page.wait_for_function("typeof jsf !== 'undefined'")

# Seletores por sufixo (IDs dinâmicos do JSF)
await page.locator("[id$='dataAdmissao']").fill("01/01/2020")

# Viewport explícito obrigatório em headless (evita offsetParent=null)
browser = await playwright.chromium.launch(args=["--no-sandbox"])
context = await browser.new_context(viewport={"width": 1920, "height": 1080})

# Detectar visibilidade via bounding box (não offsetParent)
is_visible = await page.evaluate(
    "el => { const r = el.getBoundingClientRect(); return r.width > 0 && r.height > 0; }",
    element
)
```

### Documentação de referência do projeto
- `skills/pjecalc-preenchimento/references/07-automacao-playwright.md`
- `docs/decisions.md` (FASE 3, D1–D10)
