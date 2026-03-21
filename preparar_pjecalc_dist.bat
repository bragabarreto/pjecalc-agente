@echo off
REM preparar_pjecalc_dist.bat
REM Cria a pasta pjecalc-dist/ com os arquivos necessários para o Docker
REM (sem o JRE Windows e sem o navegador Windows — apenas Java puro)
REM
REM Execute este script UMA VEZ para preparar o build Docker.
REM Depois: docker build -t pjecalc-agent .

echo Preparando pjecalc-dist/ para build Docker...

SET ORIGEM=%~dp0..\pjecalc-windows64-2.14.0
SET DESTINO=%~dp0pjecalc-dist

IF NOT EXIST "%ORIGEM%" (
    echo ERRO: PJE-Calc nao encontrado em %ORIGEM%
    echo Verifique o caminho ou ajuste a variavel ORIGEM neste script.
    pause
    exit /b 1
)

REM Limpar destino anterior
IF EXIST "%DESTINO%" (
    echo Removendo pjecalc-dist/ anterior...
    rmdir /s /q "%DESTINO%"
)

echo Copiando bin\pjecalc.jar...
mkdir "%DESTINO%\bin"
copy "%ORIGEM%\bin\pjecalc.jar" "%DESTINO%\bin\"

echo Copiando bin\lib\ (JARs do Tomcat)...
xcopy /e /i "%ORIGEM%\bin\lib" "%DESTINO%\bin\lib"

echo Copiando tomcat\ (servidor web + aplicacao)...
xcopy /e /i "%ORIGEM%\tomcat" "%DESTINO%\tomcat"

echo.
echo pjecalc-dist/ criado com sucesso!
echo Conteudo:
dir /b "%DESTINO%"
echo.
echo Proximo passo: docker build -t pjecalc-agent .
pause
