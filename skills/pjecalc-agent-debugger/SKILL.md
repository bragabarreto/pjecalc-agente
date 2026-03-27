# PJE-Calc Agent Debugger

**Premissa**: Xvfb+xdotool, Bootstrap direto, Java agent e patch de bytecode **já foram tentados**.
Esta skill investiga por que falharam e aponta o próximo passo real.

O log para em `[TRT8] Configurando variaveis basicas.` — isso significa que o bloqueio ocorre
*dentro* do Lancador, antes de qualquer inicialização do Tomcat.

---

## Arquitetura do agente (contexto para diagnóstico)

```
PDF/DOCX → ingestion.py → extraction.py (Claude API) → classification.py
→ prévia web (FastAPI + SQLite/PostgreSQL)
→ Playwright headless → PJE-Calc Cidadão (Tomcat :9257, JSF/RichFaces)
→ .PJC exportado
```

**Fases da automação** (`modules/playwright_pjecalc.py`):
1. `fase_dados_processo` — preenche Parâmetros do Cálculo + aba Parâmetros
2. `fase_parametros_gerais` — Data Inicial/Final de apuração, carga horária
3. `fase_historico_salarial` — períodos salariais (btnNovoHistorico, btnGerarOcorrencias)
4. `fase_verbas` — modo Expresso (checkboxes predefinidas) + Manual (personalizadas)
5. `fase_fgts` — alíquota, multa, saldos depositados
6. `fase_contribuicao_social` — INSS empregado/empregador
7. `fase_irpf` — tributação, deduções
8. `fase_honorarios` — advocatícios + periciais
9. `_clicar_liquidar` → gera .PJC

---

## Endpoints de diagnóstico (Railway)

| Endpoint | O que mostra |
|---|---|
| `GET /api/logs/python` | Últimos 300 logs do processo uvicorn |
| `GET /api/logs/java` | stdout+stderr do processo Java (Lancador + Tomcat) |
| `GET /api/logs/tomcat` | catalina.out do Tomcat embarcado |
| `GET /api/screenshot` | Screenshot do display Xvfb :99 |
| `GET /api/ps` | Processos em execução no container |
| `GET /api/verificar_pjecalc` | Testa se localhost:9257 responde |
| `GET /api/executar/{sessao_id}` | SSE stream com log linha a linha |

---

## Passo 1 — Coletar evidências antes de qualquer ação

Sem evidências, qualquer mudança é chute. Sempre começar aqui:

```bash
curl https://<app>.railway.app/api/logs/java     # stdout+stderr do Java
curl https://<app>.railway.app/api/logs/tomcat   # catalina.out
curl https://<app>.railway.app/api/ps            # processos em execução
curl https://<app>.railway.app/api/screenshot    # PNG do Xvfb :99 agora
curl https://<app>.railway.app/api/verificar_pjecalc  # :9257 responde?
```

**O que procurar no `/api/logs/java`:**

| Sintoma no log | O que está acontecendo | Seção |
|---|---|---|
| Para em `Configurando variaveis basicas.` sem mais nada | Thread bloqueado — não é só JOptionPane | §2 |
| `java.awt.HeadlessException` aparece | `-Djava.awt.headless=true` não chegou ao processo | §3 |
| `ClassNotFoundException: org.apache.catalina...` | Bootstrap falhou — classpath incompleto | §4 |
| OOM ou stack overflow | Memória insuficiente no Railway | §5 |
| Log totalmente vazio | O processo Java nem iniciou | §6 |
| Para em linha diferente (avançou!) | Nova barreira descoberta | §7 |

---

## §2 — JOptionPane silenciado mas o log ainda trava no mesmo lugar

Se o agent ou patch está ativo mas o log continua parando em `Configurando variaveis basicas.`,
o bloqueio **não é o JOptionPane**. Há outra causa.

### 2.1 Forçar um thread dump para ver o bloqueio real

```bash
# Enviar SIGQUIT ao processo Java — força dump de todas as threads para stdout
railway run bash -c "
  PID=\$(pgrep -f pjecalc.jar | head -1)
  echo \"PID do Java: \$PID\"
  kill -3 \$PID
  sleep 3
"
# Depois acessar /api/logs/java para ler o thread dump
```

O thread dump mostra o stack trace exato de onde o main thread está bloqueado:

```
# Exemplo — bloqueio em dialog diferente de JOptionPane:
"main" #1 prio=5 os_prio=0 tid=... in Object.wait()
   at javax.swing.JDialog.show(JDialog.java:...)
   at com.trt8.pjecalc.Lancador.mostrarSplash(Lancador.java:203)  ← bloqueio real

# Exemplo — bloqueio em leitura de arquivo:
"main" #1 prio=5 os_prio=0 tid=... runnable
   at java.io.FileInputStream.readBytes(Native Method)
   at com.trt8.pjecalc.Lancador.lerConfiguracao(Lancador.java:89)  ← arquivo inexistente

# Exemplo — bloqueio em conexão de rede:
"main" #1 prio=5 os_prio=0 tid=... in Object.wait()
   at java.net.Socket.connect(Socket.java:...)
   at com.trt8.pjecalc.Lancador.validarLicenca(Lancador.java:156)  ← servidor de licença
```

### 2.2 Outros componentes Swing que bloqueiam além de JOptionPane

```java
// Qualquer um desses cria uma janela e bloqueia sem Xvfb adequado:
new JFrame(...)          // janela principal
new JDialog(...)         // dialog genérico
new JWindow(...)         // janela sem borda
splash.setVisible(true)  // splash screen
```

Se o thread dump mostrar qualquer um desses, o Java agent precisa interceptá-los também:

```java
// Expandir SilenceSwingAgent.java para silenciar mais classes:
String[] CLASSES_GUI = {
    "javax/swing/JFrame",
    "javax/swing/JDialog",
    "javax/swing/JWindow",
    "javax/swing/JOptionPane",
    "java/awt/Dialog",
    "java/awt/Frame"
};
// Para cada uma: sobrescrever setVisible() para ser no-op quando arg=true
```

### 2.3 Bloqueio em I/O ou rede

```bash
# Rastrear syscalls do processo Java para ver o que está esperando
railway run bash -c "
  PID=\$(pgrep -f pjecalc.jar | head -1)
  timeout 10 strace -p \$PID -e trace=read,write,connect,openat 2>&1 | head -40
"
```

Causas comuns além de GUI:
- **Leitura de arquivo de config** que não existe → cria-se o arquivo vazio
- **Conexão TCP para servidor de licença** → mock do host ou variável de ambiente para desabilitar
- **`System.console()`** em ambiente sem TTY → `java ... < /dev/null`
- **`Scanner(System.in)`** aguardando stdin → `java ... < /dev/null`

```bash
# Redirecionar stdin para /dev/null — elimina bloqueios de leitura de console
java -Djava.awt.headless=true -jar pjecalc.jar < /dev/null >> java.log 2>&1 &
```

---

## §3 — `-Djava.awt.headless=true` não chega ao processo

### 3.1 O JAR pode relançar um novo processo Java internamente

Alguns JARs do PJE-Calc têm launcher interno que chama `Runtime.exec()` com novo Java **sem
herdar as flags**. Para confirmar:

```bash
# Se aparecerem 2+ processos Java, o segundo foi lançado sem flags
curl /api/ps | grep java
```

**Solução**: `JAVA_TOOL_OPTIONS` é herdada por qualquer JVM filha:

```dockerfile
# No Dockerfile — vale para o processo principal e qualquer sub-processo Java
ENV JAVA_TOOL_OPTIONS="-Djava.awt.headless=true -DDISPLAY=:99 -Xms128m -Xmx384m"
```

Se `JAVA_TOOL_OPTIONS` está ativa, a JVM imprime na inicialização:
```
Picked up JAVA_TOOL_OPTIONS: -Djava.awt.headless=true ...
```
Isso deve aparecer na primeira linha de `/api/logs/java`. Se não aparecer, a env não chegou.

---

## §4 — Bootstrap direto falhou: diagnosticar o classpath

### 4.1 Verificar se Bootstrap está dentro ou fora do pjecalc.jar

```bash
jar tf /opt/pjecalc/bin/pjecalc.jar | grep "Bootstrap.class"
# Presente → -cp pjecalc.jar funciona
# Ausente  → precisa de JARs externos em bin/lib/

# Ver o Class-Path declarado no MANIFEST:
python3 -c "
import zipfile, re
with zipfile.ZipFile('/opt/pjecalc/bin/pjecalc.jar') as z:
    m = z.read('META-INF/MANIFEST.MF').decode()
print(m)
"
```

### 4.2 Montar classpath correto a partir do MANIFEST

```bash
python3 << 'EOF'
import zipfile, re, os

jar = "/opt/pjecalc/bin/pjecalc.jar"
jar_dir = os.path.dirname(jar)

with zipfile.ZipFile(jar) as z:
    manifest = z.read("META-INF/MANIFEST.MF").decode()

cp_match = re.search(r"Class-Path: (.+?)(?=\n\S|\Z)", manifest, re.DOTALL)
entries = []
if cp_match:
    entries = cp_match.group(1).replace("\n ", "").split()

all_jars = [jar] + [
    os.path.join(jar_dir, e) for e in entries
] + [
    os.path.join(jar_dir, "lib", f)
    for f in os.listdir(os.path.join(jar_dir, "lib"))
    if f.endswith(".jar")
] if os.path.isdir(os.path.join(jar_dir, "lib")) else [jar]

classpath = ":".join(all_jars)
print("CLASSPATH=" + classpath)
print("\nComando sugerido:")
print(f"java -Djava.awt.headless=true -cp '{classpath}' org.apache.catalina.startup.Bootstrap start")
EOF
```

---

## §5 — Memória insuficiente no Railway

```bash
# Verificar limite de memória do container
cat /proc/meminfo | grep MemTotal
# Railway Starter: ~512MB total — deixar ~256MB para Python/uvicorn

# Configuração conservadora para Java:
ENV JAVA_TOOL_OPTIONS="-Djava.awt.headless=true -Xms64m -Xmx256m -XX:+UseSerialGC -XX:MaxMetaspaceSize=96m"
# UseSerialGC: menos overhead que G1GC (padrão), melhor para containers pequenos
```

---

## §6 — Log Java totalmente vazio

```bash
# 1. O script de inicialização tem permissão de execução?
ls -la /opt/pjecalc/iniciarPjeCalc.sh
# Precisa de 'x': -rwxr-xr-x

# 2. O Java 8 está no PATH?
which java && java -version 2>&1
# Deve mostrar: openjdk version "1.8.0_..."

# 3. Adicionar echo de diagnóstico no topo do iniciarPjeCalc.sh
echo "[INIT] script iniciado em \$(date)" >> /opt/pjecalc/java.log
echo "[INIT] DISPLAY=\$DISPLAY" >> /opt/pjecalc/java.log
echo "[INIT] JAVA=\$(which java)" >> /opt/pjecalc/java.log
```

---

## §7 — O log avançou para nova linha (nova barreira)

Se uma das abordagens fez o log avançar para além de `Configurando variaveis basicas.`,
identifique a categoria da nova parada:

```
Nova linha de parada → categoria:
  ├─ "Dialog", "Frame", "Window", "JPanel", "setVisible"
  │   → outro componente Swing — expandir o agent (§2.2)
  ├─ "FileNotFound", "NoSuchFile", "Permission denied"
  │   → arquivo de config faltando — criar arquivo vazio ou corrigir path
  ├─ "Connection refused", "UnknownHost", "SocketTimeout", "ConnectException"
  │   → conexão de rede bloqueando — mock do host via /etc/hosts ou env var
  ├─ "ClassNotFoundException", "NoClassDefFound"
  │   → classpath incompleto — revisar §4
  └─ Outra coisa
      → coletar thread dump (§2.1) e analisar stack trace completo
```

---

## Catálogo de falhas conhecidas na automação Playwright

### F1 — Tomcat não sobe no Railway
**Sintoma:** `/api/verificar_pjecalc` retorna erro; log Java para em `[TRT8] Configurando variaveis basicas.`
**Causa:** `Lancador.java` abre `JOptionPane` (GUI Swing) que bloqueia o thread em ambiente headless
**Diagnóstico:** `GET /api/logs/java` + `GET /api/screenshot`
**Solução candidata:** Iniciar Tomcat diretamente via `org.apache.catalina.startup.Bootstrap`

### F2 — Erro `asyncio: no running event loop` no Playwright
**Sintoma:** `RuntimeError: no running event loop` ou `There is no current event loop in thread`
**Causa:** `sync_playwright()` chamado em thread filho do uvicorn que herda o loop principal
**Correção:** `asyncio.set_event_loop(asyncio.new_event_loop())` antes de `sync_playwright().__enter__()` em `iniciar_browser()`

### F3 — "Execution context was destroyed" na fase_dados_processo
**Sintoma:** `playwright._impl._errors.Error: Execution context was destroyed`
**Causa:** JSF navega (redirect pós-"Novo") antes de `mapear_campos()` ser chamado
**Correção:** `wait_for_load_state("networkidle")` em `_ir_para_novo_calculo()` + `wait_for_load_state("domcontentloaded")` no início de `fase_dados_processo()`

### F4 — Verba manual loga `✓` sem ter aberto formulário (falso positivo)
**Sintoma:** log mostra `→ Manual Novo: 'None'` seguido de `✓ Verba manual: X`
**Causa:** `_clicou_novo` retorna `None` (botão não encontrado) mas o código continuava
**Correção:** guard após `_clicou_novo is None` — tenta `_clicar_novo()`, verifica campo visível, skip com aviso se falhar

### F5 — fase_parametros_gerais não persiste
**Sintoma:** Histórico Salarial aparece como "não disponível no menu" logo após fase 2a
**Causa:** `fase_parametros_gerais` preenchia campos mas não chamava `_clicar_salvar()`
**Correção:** adicionar `_clicar_salvar()` + `_aguardar_ajax()` antes do log final

### F6 — Menu lateral clica no elemento errado
**Sintoma:** após "clicar Verbas", a página abre uma seção diferente
**Causa:** `_clicar_menu_lateral` usava `textContent.includes()` em todos os `<a>`
**Correção:** dicionário `_MENU_ID_MAP` com seletores `a[id*='menuXxx']` tentados primeiro

### F7 — ViewState expirado (JSF 500)
**Sintoma:** HTTP 500 no meio da automação; log Playwright mostra `ViewExpiredException`
**Causa:** sessão JSF expirou (timeout ou reload forçado)
**Correção:** recarregar a URL base e redirecionar para `fase_dados_processo` via `@retry`

### F8 — 503 Service Unavailable ao editar campo na prévia
**Sintoma:** `PATCH /previa/{id}/editar` retorna 503 em produção
**Causa:** `_sincronizar_verbas` chamada em todo edit → timeout proxy Railway 30s
**Correção:** só chamar `_sincronizar_verbas` quando `campo.startswith("verba")`

### F9 — Liquidar falha com "campo obrigatório não preenchido"
**Sintoma:** clique em Liquidar gera alerta/erro JSF
**Causa:** fase upstream não salvou (F4 ou F5) ou campo obrigatório ausente
**Diagnóstico:** ler log SSE completo buscando `⚠` antes do Liquidar

### F10 — `DeprecationWarning: invalid escape sequence \s` em JS strings
**Sintoma:** warning Python sobre `\s` em strings multi-linha
**Causa:** strings JavaScript embutidas em Python precisam de `\\s`
**Correção:** substituir `\s` por `\\s` nos `page.evaluate("""...""")` afetados

---

## Debugging do pipeline de 6 fases

```python
# Fase 1: Ingestão
from modules.ingestion import ingerir_pdf
r = ingerir_pdf("path/to/sentenca.pdf")
assert r.get("texto"), f"Ingestão falhou: {r}"
print(f"✅ F1 — {len(r['texto'])} chars")

# Fase 2: Extração IA (requer ANTHROPIC_API_KEY com créditos)
from modules.extraction import extrair_dados
dados = extrair_dados(r["texto"])
if dados.get("_erro_ia"):
    raise RuntimeError("IA indisponível — verificar API key e créditos")
print(f"✅ F2 — confidence {dados.get('_confidence', '?')}")

# Fase 3: Classificação
from modules.classification import classificar_verbas
verbas = classificar_verbas(dados.get("verbas_raw", []))
nao_mapeadas = [v["nome"] for v in verbas if not v.get("codigo_pjecalc")]
print(f"✅ F3 — {len(verbas)} verbas | não mapeadas: {nao_mapeadas}")

# Fase 5: Playwright + PJE-Calc
# Problema mais comum: campo preenchido mas JSF não registra
# → dispatch_event("change") + ("blur") após fill()
```

---

## Padrões de log SSE esperados (automação saudável)

```
✓ Fase 1 concluída.
  ℹ Seção: 'Histórico Salarial' | url: .../historico-salarial
  ✓ Ocorrências geradas: Salário
  ✓ Período: 01/03/2023 a 28/02/2025 — R$ 3.000,00
  Fase 2 concluída.
  ℹ Seção: 'Verbas' | url: .../verbas
  ✓ Verbas Expresso salvas
  Fase 3 concluída.
  ℹ Seção: 'FGTS' | url: .../fgts
  Fase 4 concluída.
  ℹ Seção: 'Liquidar' | url: .../liquidar
PJC_GERADO:/app/output/calculo_xxx.pjc
```

**Red flags no log (indicam falha silenciosa):**
- `→ Manual Novo: 'None'` seguido de `✓ Verba manual:` → F4
- `Fase 2a concluída.` precedido de `⚠ Botão Salvar não encontrado` → F5
- `ℹ Seção: 'Dados do Processo'` quando esperava `'Verbas'` → F6
- `⚠ Histórico Salarial não disponível no menu` → F5 (parâmetros não salvos)
- `ViewExpiredException` → F7

---

## Checklist antes de cada deploy

- [ ] `/api/logs/java` mostra `Picked up JAVA_TOOL_OPTIONS:` na 1ª linha
- [ ] `/api/ps` mostra Xvfb `:99` rodando
- [ ] `/api/ps` mostra apenas 1 processo Java (não 2)
- [ ] `/api/screenshot` não mostra nenhum dialog aberto
- [ ] Bootstrap ou pjecalc.jar — classpath validado (§4)
- [ ] stdin redirecionado para `/dev/null` no comando Java
- [ ] Polling em `executar_automacao_sse()` aguarda até 600s

---

## Referências

- `references/tomcat-bootstrap.md` — classpath completo e troubleshooting do Bootstrap
- `references/joptionpane-patch.md` — script Python de patch de bytecode + reempacotamento do JAR

Combinar com:
- `skills/pjecalc-preenchimento/SKILL.md` — campos e seletores completos do PJE-Calc
- `skills/systematic-debugging/SKILL.md` — metodologia de debugging sistemático
- `skills/playwright-skill/SKILL.md` — padrões avançados de automação Playwright
