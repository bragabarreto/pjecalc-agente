@echo off
:: iniciar_servidor.bat — Agente PJE-Calc
:: Duplo-clique para instalar (1ª vez) e iniciar o servidor
chcp 65001 >NUL 2>&1
title Agente PJE-Calc

cd /d "%~dp0"

:: ============================================================
:: VERIFICAR PYTHON
:: ============================================================
python --version >NUL 2>&1
IF ERRORLEVEL 1 (
    echo.
    echo  ERRO: Python nao encontrado.
    echo  Instale Python 3.10 ou superior em:
    echo    https://python.org/downloads
    echo  IMPORTANTE: marque "Add Python to PATH" durante a instalacao.
    echo.
    pause
    exit /b 1
)

:: ============================================================
:: PRIMEIRA VEZ — instalar dependencias automaticamente
:: ============================================================
IF NOT EXIST venv\Scripts\python.exe (
    echo.
    echo  ============================================================
    echo   PRIMEIRA EXECUCAO — Instalando dependencias...
    echo   Isso pode levar de 2 a 5 minutos. Aguarde.
    echo  ============================================================
    echo.

    python -m venv venv
    IF ERRORLEVEL 1 (
        echo ERRO ao criar ambiente virtual.
        pause
        exit /b 1
    )

    venv\Scripts\python -m pip install --upgrade pip --quiet
    IF ERRORLEVEL 1 goto erro_pip

    venv\Scripts\pip install -r requirements.txt --quiet
    IF ERRORLEVEL 1 goto erro_pip

    venv\Scripts\playwright install chromium
    IF ERRORLEVEL 1 (
        echo AVISO: Falha ao instalar Playwright. A automacao pode nao funcionar.
    )

    :: Criar pastas de dados
    if not exist data\logs\sessions     mkdir data\logs\sessions
    if not exist data\logs\screenshots  mkdir data\logs\screenshots
    if not exist data\output            mkdir data\output

    echo.
    echo  Instalacao concluida com sucesso!
    echo.
)

:: ============================================================
:: VERIFICAR CHAVE DA API (ANTHROPIC_API_KEY)
:: ============================================================
IF NOT EXIST .env (
    :: Verificar se está na variável de ambiente do sistema
    IF "%ANTHROPIC_API_KEY%"=="" (
        echo.
        echo  ============================================================
        echo   CONFIGURACAO NECESSARIA
        echo  ============================================================
        echo.
        echo  Crie o arquivo  .env  nesta pasta com o seguinte conteudo:
        echo.
        echo    ANTHROPIC_API_KEY=sk-ant-SUA-CHAVE-AQUI
        echo.
        echo  Para obter sua chave de API, acesse:
        echo    https://console.anthropic.com
        echo.
        echo  Depois de criar o arquivo .env, execute este bat novamente.
        echo  ============================================================
        echo.
        :: Criar arquivo .env modelo para o usuario editar
        echo ANTHROPIC_API_KEY=sk-ant-COLOQUE-SUA-CHAVE-AQUI > .env
        echo.
        echo  Arquivo .env criado. Edite-o com sua chave e execute novamente.
        pause
        exit /b 1
    )
)

:: ============================================================
:: VERIFICAR SE JA ESTA RODANDO
:: ============================================================
netstat -ano | findstr ":8000 " >NUL 2>&1
IF NOT ERRORLEVEL 1 (
    echo  Servidor ja esta rodando. Abrindo navegador...
    start http://localhost:8000
    exit /b 0
)

:: ============================================================
:: INICIAR SERVIDOR
:: ============================================================
echo.
echo  ============================================================
echo   Agente PJE-Calc — http://localhost:8000
echo   Para encerrar: feche esta janela ou pressione CTRL+C
echo  ============================================================
echo.

:: Abrir navegador automaticamente apos 3 segundos
start "" /b cmd /c "timeout /t 3 >NUL && start http://localhost:8000"

:: Iniciar servidor (mantém janela aberta)
venv\Scripts\uvicorn webapp:app --host 0.0.0.0 --port 8000

pause
exit /b 0

:erro_pip
echo.
echo  ERRO: Falha ao instalar dependencias.
echo  Verifique sua conexao com a internet e tente novamente.
echo.
pause
exit /b 1
