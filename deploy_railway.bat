@echo off
cd /d "%~dp0"
title Deploy Railway - Agente PJE-Calc

echo.
echo ---------------------------------------------------------------
echo   DEPLOY ONLINE - Agente PJE-Calc - Railway.app
echo ---------------------------------------------------------------
echo Diretorio: %CD%
echo.

REM -- Verificar Git --
git --version >nul 2>&1
if errorlevel 1 (
    echo [ERRO] Git nao encontrado.
    echo Instale em: https://git-scm.com/download/win
    echo.
    pause
    exit /b 1
)
echo [OK] Git encontrado.
echo.

REM -- Inicializar repositorio Git local --
echo [1/4] Preparando repositorio Git local...
if not exist ".git" (
    git init -b main
    echo [OK] Repositorio iniciado.
) else (
    echo [OK] Repositorio ja existe.
)

git add -A
git diff --cached --quiet
if errorlevel 1 (
    git -c user.email="deploy@pjecalc" -c user.name="PJECalc Deploy" commit -m "deploy agente pjecalc"
    echo [OK] Commit criado.
) else (
    echo [OK] Nada novo para commitar.
)
echo.

REM -- Instrucoes GitHub --
echo [2/4] Crie um repositorio no GitHub:
echo.
echo   1. Acesse https://github.com/new
echo   2. Nome sugerido: pjecalc-agente
echo   3. Deixe PRIVADO (dados judiciais sigilosos)
echo   4. NAO marque "Add README" nem .gitignore
echo   5. Clique "Create repository"
echo   6. Copie a URL que aparecer (ex: https://github.com/SEU_USUARIO/pjecalc-agente.git)
echo.
set /p GIT_REMOTE=Cole aqui a URL do repositorio GitHub e pressione ENTER:
echo.

REM -- Conectar ao GitHub --
echo [3/4] Conectando e enviando codigo para o GitHub...
git remote remove origin 2>nul
git remote add origin %GIT_REMOTE%
git branch -M main
echo.
echo ATENCAO: O GitHub vai pedir suas credenciais.
echo Use seu usuario GitHub e um Personal Access Token como senha.
echo Para criar um token: https://github.com/settings/tokens/new
echo (Marque a permissao "repo" e gere o token)
echo.
git push -u origin main
if errorlevel 1 (
    echo.
    echo [ERRO] Falha ao enviar para o GitHub.
    echo Verifique usuario/token e tente novamente.
    echo.
    pause
    exit /b 1
)
echo [OK] Codigo enviado ao GitHub.
echo.

REM -- Instrucoes Railway --
echo [4/4] Agora configure o Railway:
echo.
echo   1. Acesse https://railway.app e crie uma conta gratuita
echo   2. Clique em "New Project"
echo   3. Escolha "Deploy from GitHub repo"
echo   4. Autorize o Railway a acessar seus repositorios
echo   5. Selecione o repositorio "pjecalc-agente"
echo   6. Railway vai detectar o Dockerfile automaticamente
echo.
echo   Depois de criar o projeto, adicione o PostgreSQL:
echo   "+ New" ^> "Database" ^> "PostgreSQL"
echo.
echo   Por fim, adicione as variaveis de ambiente em:
echo   Settings ^> Variables:
echo.
echo     ANTHROPIC_API_KEY = sua chave sk-ant-...
echo     CLOUD_MODE        = true
echo     DATA_DIR          = /app/data
echo.
echo   Para obter a URL publica:
echo   Settings ^> Networking ^> "Generate Domain"
echo.
echo ---------------------------------------------------------------
echo   Codigo enviado ao GitHub com sucesso!
echo   Siga as instrucoes acima no Railway para finalizar o deploy.
echo ---------------------------------------------------------------
echo.
pause
