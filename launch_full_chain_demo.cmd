@echo off
setlocal
cd /d "%~dp0"

pythonw launch_full_chain_demo.pyw
if %ERRORLEVEL% EQU 0 exit /b 0

python -B scripts\full_chain_frontend\app.py
if %ERRORLEVEL% EQU 0 exit /b 0

py -3 scripts\full_chain_frontend\app.py
