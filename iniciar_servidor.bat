@echo off
:: iniciar_servidor.bat — Inicia o servidor web do Agente PJE-Calc
:: Execute este arquivo sempre que quiser usar o sistema

title Agente PJE-Calc — Servidor Web

cd /d "%~dp0"

:: Verificar se o ambiente virtual existe
IF NOT EXIST venv\Scripts\uvicorn.exe (
    echo ERRO: Ambiente virtual nao encontrado.
    echo Execute primeiro o arquivo instalar.bat
    pause
    exit /b 1
)

:: Verificar se já está rodando na porta 8000
netstat -ano | findstr ":8000 " >NUL 2>&1
IF NOT ERRORLEVEL 1 (
    echo AVISO: Porta 8000 ja em uso.
    echo O servidor pode ja estar rodando.
    echo Acesse: http://localhost:8000
    echo.
    pause
    exit /b 0
)

echo ============================================================
echo  AGENTE PJE-CALC — Servidor Web
echo ============================================================
echo.
echo  Iniciando servidor em http://localhost:8000
echo  Para encerrar: feche esta janela ou pressione CTRL+C
echo.

:: Abrir o navegador automaticamente após 2 segundos
start "" /b cmd /c "timeout /t 2 >NUL && start http://localhost:8000"

:: Iniciar o servidor (mantém a janela aberta)
venv\Scripts\uvicorn webapp:app --host 0.0.0.0 --port 8000

pause
