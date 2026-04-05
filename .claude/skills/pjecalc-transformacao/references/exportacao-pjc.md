# Fase 6: Exportação do .PJC

## Índice

1. [Regra fundamental](#1-regra-fundamental)
2. [Como o PJe-Calc gera o .PJC](#2-como-o-pje-calc-gera-o-pjc)
3. [Coleta via Playwright](#3-coleta-via-playwright)
4. [Entrega ao usuário](#4-entrega-ao-usuário)
5. [Troubleshooting de exportação](#5-troubleshooting-de-exportação)

---

## 1. Regra fundamental

**O arquivo .PJC só pode ser gerado pelo PJe-Calc Cidadão.**

Esta regra existe por um motivo prático e definitivo: o **PJe-Calc Institucional** (sistema
do TRT para inserção do cálculo no processo judicial) **rejeita arquivos .PJC que não tenham
sido gerados pelo próprio PJe-Calc ou PJe-Calc Cidadão**. Qualquer .PJC gerado externamente
— mesmo com XML sintaticamente correto, encoding ISO-8859-1, e estrutura ZIP válida — será
marcado como "inválido" na importação.

Portanto:

- ✅ Playwright abre PJe-Calc → preenche → Calcular → Exportar → coleta .PJC
- ❌ Python gera ZIP + XML ISO-8859-1 → .PJC "nativo" → REJEITADO na importação
- ❌ Manipular .PJC existente alterando XML interno → REJEITADO
- ❌ Copiar assinatura/hash de .PJC válido para outro → REJEITADO

**Se a automação Playwright falhar na exportação, a resposta é corrigir a automação —
nunca contornar gerando o arquivo por fora.**

## 2. Como o PJe-Calc gera o .PJC

O PJe-Calc Cidadão, ao clicar "Exportar", gera internamente:

1. Serializa o cálculo em XML (`calculo.xml`)
2. Opcionalmente inclui histórico (`calculo_historico.xml`)
3. Empacota em ZIP com extensão `.pjc`
4. Encoding: ISO-8859-1 no XML
5. Inclui metadados internos que identificam a origem (PJe-Calc Cidadão)

Estes metadados de origem são o que torna impossível replicar o .PJC externamente —
o PJe-Calc Institucional verifica a assinatura/origem durante a importação.

## 3. Coleta via Playwright

O momento crítico: capturar o download do .PJC gerado pelo PJe-Calc.

```python
async def exportar_pjc(page) -> str:
    """
    Clica Exportar no PJe-Calc e coleta o .PJC gerado.
    Retorna o caminho do arquivo salvo.
    """
    import os

    # Criar diretório de exports se não existe
    os.makedirs("/tmp/exports", exist_ok=True)

    # Configurar expectativa de download ANTES de clicar
    async with page.expect_download(timeout=60000) as download_info:
        # Localizar e clicar botão Exportar
        botao_exportar = page.locator("[id$='exportar']")
        if await botao_exportar.count() == 0:
            # Fallback: tentar por texto
            botao_exportar = page.get_by_text("Exportar")
        await botao_exportar.click()

    download = await download_info.value

    # Salvar com nome sugerido pelo PJe-Calc
    nome_arquivo = download.suggested_filename or "calculo.pjc"
    caminho = f"/tmp/exports/{nome_arquivo}"
    await download.save_as(caminho)

    # Verificar integridade básica
    tamanho = os.path.getsize(caminho)
    if tamanho < 100:
        raise ValueError(f"Arquivo .PJC muito pequeno ({tamanho} bytes) — pode estar corrompido")

    return caminho
```

### Verificação de integridade

Após coletar o .PJC, verificar que é um ZIP válido (sem abrir ou modificar o conteúdo):

```python
import zipfile

def verificar_pjc(caminho: str) -> bool:
    """Verifica que o .PJC é um ZIP válido com calculo.xml dentro."""
    try:
        with zipfile.ZipFile(caminho, 'r') as zf:
            nomes = zf.namelist()
            # Deve conter calculo.xml
            if "calculo.xml" not in nomes:
                return False
            # Verificar que o ZIP não está corrompido
            resultado = zf.testzip()
            return resultado is None
    except (zipfile.BadZipFile, Exception):
        return False
```

## 4. Entrega ao usuário

### Via API (webapp)

```python
from fastapi.responses import FileResponse

@app.get("/download/pjc/{nome_arquivo}")
async def download_pjc(nome_arquivo: str):
    caminho = f"/tmp/exports/{nome_arquivo}"
    if not os.path.exists(caminho):
        raise HTTPException(404, "Arquivo não encontrado")

    return FileResponse(
        path=caminho,
        filename=nome_arquivo,
        media_type="application/octet-stream"
    )
```

### Via SSE (protocolo CalcMACHINE)

O CalcMACHINE sinaliza a disponibilidade do .PJC via SSE:

```python
# Após exportação bem-sucedida:
yield f"data: DOWNLOAD_LINK_CALC:/download/pjc/{nome_arquivo}\n\n"
```

O frontend recebe e exibe link de download para o usuário.

## 5. Troubleshooting de exportação

### Problema: botão Exportar não aparece

**Causa provável:** o cálculo não foi executado com sucesso. Verificar:
- O botão Calcular foi clicado?
- O resultado do cálculo está visível na tela?
- Há mensagens de erro do PJe-Calc na tela?

**Solução:** Garantir que Fase 9 executa Calcular ANTES de Exportar, e aguarda resultado.

### Problema: download timeout

**Causa provável:** o PJe-Calc está gerando um cálculo complexo que demora.

**Solução:** Aumentar timeout do `expect_download` (padrão 60s, pode precisar de 120s+).

### Problema: .PJC gerado com 0 bytes

**Causa provável:** erro interno do PJe-Calc durante serialização.

**Solução:** Verificar logs do Tomcat, reexecutar o cálculo, tentar exportar novamente.

### Problema: .PJC não é ZIP válido

**Causa provável:** download incompleto ou corrompido.

**Solução:** Verificar conexão com Tomcat, retentar exportação. Se persistir, reiniciar
PJe-Calc e reexecutar o fluxo completo (Fases 1-9).
