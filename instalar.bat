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
echo [6/6] Configurando chave de API...
IF "%ANTHROPIC_API_KEY%"=="" (
    echo.
    echo IMPORTANTE: Configure sua chave da API Anthropic:
    echo   set ANTHROPIC_API_KEY=sua-chave-aqui
    echo   (ou adicione ao arquivo .env na pasta do projeto)
    echo.
) ELSE (
    echo ANTHROPIC_API_KEY ja configurada.
)

echo.
echo ============================================================
echo  Instalacao concluida!
echo.
echo  MODO WEB (recomendado):
echo    venv\Scripts\activate
echo    uvicorn webapp:app --reload --port 8000
echo    Acesse: http://localhost:8000
echo.
echo  MODO LINHA DE COMANDO:
echo    venv\Scripts\activate
echo    python main.py --sentenca caminho\sentenca.pdf
echo ============================================================
pause
