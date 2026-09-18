@echo off
rem OscLab — atalho do Windows.
rem
rem COM argumentos, repassa tudo para o app.py:  osclab.cmd --port 9000
rem SEM argumentos, abre um menu.
rem
rem O menu e' burro de proposito: le uma tecla e chama o Python. Tudo que pode
rem dar errado fica do lado do Python, onde existe teste. Aqui so' fica o que um
rem .cmd sabe fazer sozinho: escolher.
setlocal

set "HERE=%~dp0"
if "%HERE:~-1%"=="\" set "HERE=%HERE:~0,-1%"

if not exist "%HERE%\app.py" (
  echo [ERRO] Nao encontrei app.py em %HERE%.
  echo        Esta copia da pasta esta incompleta.
  exit /b 1
)

rem PACOTE_ROOT e' a versao em execucao; DATA_DIR sao os dados do usuario.
rem Hoje sao a mesma pasta. Numa instalacao versionada deixam de ser, e o
rem src\osclab\paths.py ja' esta preparado para isso.
set "OSCLAB_ROOT=%HERE%"
set "OSCLAB_DATA_DIR=%HERE%"

set "PY=%HERE%\.venv\Scripts\python.exe"
if not exist "%PY%" set "PY=python"

if not "%~1"=="" (
  "%PY%" "%HERE%\app.py" %*
  exit /b %ERRORLEVEL%
)

:menu
cls
echo.
echo   OscLab
echo   ======
echo   Leitor e analisador de oscilografia
echo.
echo     1^) Rodar o programa
echo     2^) Preparar esta pasta ^(instalar dependencias^)
echo     3^) Ler uma oscilografia ^(no terminal^)
echo     4^) Rodar os testes
echo     5^) Versao
echo     0^) Sair
echo.
set "OPC="
set /p "OPC=  Opcao: "
rem Sem tirar as aspas, um caminho colado aqui vira `if ""C:\..""==""`, que e'
rem erro de sintaxe — e o cmd encerra o script fechando a janela.
if defined OPC set OPC=%OPC:"=%
if not defined OPC goto menu

if "%OPC%"=="1" goto rodar
if "%OPC%"=="2" goto preparar
if "%OPC%"=="3" goto ler
if "%OPC%"=="4" goto testes
if "%OPC%"=="5" goto versao
if "%OPC%"=="0" exit /b 0
goto menu

:rodar
echo.
echo Abra http://localhost:8770/ no navegador. Ctrl+C encerra.
echo.
"%PY%" "%HERE%\app.py" --web
goto fim

:preparar
echo.
echo Preparando a pasta: criando o virtualenv e instalando as dependencias...
"%PY%" "%HERE%\app.py" --preparar
echo.
echo Pronto. A opcao 1 ja' roda daqui.
goto fim

:ler
echo.
echo Arraste o arquivo .cfg para esta janela e pressione Enter.
echo ^(ou cole o caminho, com ou sem aspas^)
echo.
set "ARQ="
set /p "ARQ=  Arquivo: "
rem `if not defined` aguenta qualquer conteudo. Comparar com "" nao aguenta:
rem o caminho vem com aspas quando o arquivo e' arrastado, e a comparacao vira
rem erro de sintaxe que fecha a janela sem dizer nada.
if not defined ARQ goto menu
echo.
"%PY%" "%HERE%\app.py" --ler %ARQ%
goto fim

:testes
echo.
"%PY%" "%HERE%\app.py" --testes
goto fim

:versao
echo.
"%PY%" "%HERE%\app.py" --versao
goto fim

:fim
echo.
pause
goto menu
