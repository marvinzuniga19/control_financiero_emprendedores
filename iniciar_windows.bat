@echo off
setlocal

set "PY="
where python >nul 2>nul
if not errorlevel 1 set "PY=python"
if not defined PY (
    where py >nul 2>nul
    if not errorlevel 1 set "PY=py -3"
)

if not defined PY (
    echo Python no esta instalado o no esta en el PATH.
    pause
    exit /b 1
)

if not exist .venv (
    %PY% -m venv .venv
    if errorlevel 1 goto :error
)

call .venv\Scripts\activate
python -m pip install -r requirements.txt
if errorlevel 1 goto :error

python main.py
pause
exit /b 0

:error
echo.
echo Se produjo un error al iniciar Control Financiero Pro.
echo Revise el mensaje anterior.
pause
exit /b 1