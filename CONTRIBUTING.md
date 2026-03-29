# Contributing — PJECalc Agente

## Setup de Desenvolvimento

```bash
# Clone o repositório
git clone https://github.com/bragabarreto/pjecalc-agente.git
cd pjecalc-agente

# Criar e ativar ambiente virtual
python3 -m venv venv
source venv/bin/activate  # macOS/Linux
# venv\Scripts\activate   # Windows

# Instalar dependências completas (incluindo dev)
pip install -r requirements.txt
pip install pytest pytest-asyncio

# Instalar Playwright Chromium
playwright install chromium

# Copiar e configurar variáveis de ambiente
cp .env.example .env
# Editar .env com ANTHROPIC_API_KEY e (opcional) GEMINI_API_KEY

# Subir o servidor em modo desenvolvimento
uvicorn webapp:app --reload --port 8000
```

## Rodar Testes

```bash
pytest tests/ -v
```

## Convenções de Branch

- `main` — produção estável (Railway deploy automático)
- `feat/<nome>` — nova funcionalidade
- `fix/<nome>` — correção de bug
- `refactor/<nome>` — refatoração sem mudança de comportamento
- `docs/<nome>` — apenas documentação

## Como Adicionar uma Verba ao Catálogo

O catálogo de verbas predefinidas fica em `modules/classification.py` → `VERBAS_PREDEFINIDAS`.

Para adicionar uma nova verba:

```python
# Em modules/classification.py, adicionar ao dict VERBAS_PREDEFINIDAS:
"nome_normalizado_sem_acento": {
    "nome_pjecalc": "Nome Exato no PJE-Calc",     # string exata como aparece no sistema
    "caracteristica": "Comum",                      # Comum | Ferias | 13o Salario | Aviso Previo
    "ocorrencia": "Mensal",                         # Mensal | Desligamento | Periodo Aquisitivo | Dezembro
    "incidencia_fgts": True,
    "incidencia_inss": True,
    "incidencia_ir": True,
    "tipo": "Principal",                            # Principal | Reflexa
    "compor_principal": True,
    "campos_criticos": ["campo1", "campo2"],        # campos que precisam ser preenchidos
},
```

Após adicionar, atualizar também `knowledge/pje_calc_official/verba_catalog_official.md` com a nova entrada na tabela.

## Como Atualizar a Knowledge Base

A knowledge base fica em `knowledge/pje_calc_official/`. Edite os arquivos `.md` e `.txt` diretamente.

**`system_prompt_base.txt`**: modifique apenas se houver mudança no comportamento esperado do LLM (novos enums PJE-Calc, nova jurisprudência, etc.). Mudanças aqui afetam **todas** as extrações futuras.

**`verba_catalog_official.md`**: mantenha sincronizado com `VERBAS_PREDEFINIDAS` em `classification.py`.

**`manual_excerpts.md`** e **`tutorial_rules.md`**: atualize quando uma nova versão do Manual Oficial for publicada ou quando novas regras jurídicas relevantes forem estabelecidas (ex: novas decisões do TST/STF que afetam o cálculo).

## Como Depurar o Learning Engine

1. Faça 10+ correções na tela de Prévia de um cálculo
2. Acesse `/admin/aprendizado` para ver sessões de aprendizado
3. Clique em "Executar Sessão Agora" para disparar manualmente
4. Verifique as regras geradas na tabela "Regras Aprendidas"
5. Os snapshots JSON ficam em `data/learning/rules_latest.json`

## Pull Requests

1. Todos os PRs devem passar em `pytest tests/`
2. Mudanças em `modules/extraction.py` ou `knowledge/` devem incluir descrição do impacto nos prompts
3. Mudanças no schema do banco de dados (novos campos/modelos em `infrastructure/database.py`) precisam ser backward compatible (`create_all` com `checkfirst=True`)
4. Nunca remover a regra **IA-only** de `extraction.py` e `webapp.py`

## Estrutura de Imports

Os arquivos `config.py` e `database.py` na raiz são shims de backward compatibility:

```python
# config.py — não editar diretamente
from infrastructure.config import settings  # noqa: F401, F403
from infrastructure.config import *          # noqa: F401, F403
```

Para novas funcionalidades, importe sempre de `infrastructure.config` e `infrastructure.database`.
