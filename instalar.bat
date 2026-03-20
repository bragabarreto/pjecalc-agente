@echo off
:: instalar.bat — Configuração do ambiente do Agente PJE-Calc
:: Execute como Administrador se necessário

echo ============================================================
echo  AGENTE PJE-CALC — Instalacao de Dependencias
echo ============================================================
echo.

:: Verificar Python
python --version 2>NUL
IF ERRORLEVEL 1 (
    echo ERRO: Python nao encontrado. Instale Python 3.10+ em python.org
    pause
    exit /b 1
)

:: Criar ambiente virtual
echo [1/6] Criando ambiente virtual...
python -m venv venv
call venv\Scripts\activate.bat

:: Instalar dependências
echo [2/6] Instalando dependencias principais...
pip install --upgrade pip
pip install -r requirements.txt

:: Instalar Playwright
echo [3/6] Configurando Playwright (automacao web PJE-Calc)...
playwright install firefox chromium

:: Criar estrutura de dados
echo [4/6] Criando estrutura de dados...
if not exist data mkdir data
if not exist output mkdir output
if not exist logs\sessions mkdir logs\sessions
if not exist logs\screenshots mkdir logs\screenshots

:: Verificar Tesseract (OCR)
echo [5/6] Verificando Tesseract OCR...
tesseract --version 2>NUL
IF ERRORLEVEL 1 (
    echo AVISO: Tesseract nao encontrado.
    echo Para PDFs escaneados, instale Tesseract:
    echo   https://github.com/UB-Mannheim/tesseract/wiki
    echo   Instale com suporte ao idioma Portugues (por)
) ELSE (
    echo Tesseract encontrado.
)

:: Configurar ANTHROPIC_API_KEY
echo [6/7] Configurando chave de API...
IF "%ANTHROPIC_API_KEY%"=="" (
    echo.
    echo IMPORTANTE: Configure sua chave da API Anthropic:
    echo   Edite o arquivo .env na pasta do agente e adicione:
    echo   ANTHROPIC_API_KEY=sua-chave-aqui
    echo.
) ELSE (
    echo ANTHROPIC_API_KEY ja configurada.
)

:: Criar atalhos na area de trabalho e na Inicializacao do Windows
echo [7/7] Criando atalhos (area de trabalho e inicializacao automatica)...
set "PJECALC_BASE=%~dp0"
set "PJECALC_BASE=%PJECALC_BASE:~0,-1%"
powershell -NoProfile -Command ^
  "& { $base = $env:PJECALC_BASE; $pyW = $base + '\venv\Scripts\pythonw.exe'; $ws = New-Object -ComObject WScript.Shell; $desk = [Environment]::GetFolderPath('Desktop'); $s = $ws.CreateShortcut($desk + '\Agente PJE-Calc.lnk'); $s.TargetPath = $pyW; $s.Arguments = 'launcher.pyw'; $s.WorkingDirectory = $base; $s.Description = 'Agente PJE-Calc - Automacao de Calculos Trabalhistas'; $s.Save(); $startup = [Environment]::GetFolderPath('Startup'); $s2 = $ws.CreateShortcut($startup + '\Agente PJE-Calc.lnk'); $s2.TargetPath = $pyW; $s2.Arguments = 'launcher.pyw'; $s2.WorkingDirectory = $base; $s2.Description = 'Agente PJE-Calc - Automacao de Calculos Trabalhistas'; $s2.Save(); Write-Host 'Atalhos criados com sucesso.' }"

echo.
echo ============================================================
echo  Instalacao concluida!
echo.
echo  COMO USAR:
echo    Duplo clique no atalho "Agente PJE-Calc" na area de trabalho.
echo    O aplicativo abre automaticamente no browser.
echo.
echo    O servidor tambem inicia sozinho ao ligar o computador.
echo.
echo  Configure as chaves de API no arquivo .env antes de usar.
echo ============================================================
pause
