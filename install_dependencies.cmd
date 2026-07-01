@echo off
setlocal
cd /d "%~dp0"

echo Installing PURE-JADE Python dependencies...
python -m pip install -r requirements.txt
if %ERRORLEVEL% EQU 0 goto done

echo.
echo python command failed, trying py -3...
py -3 -m pip install -r requirements.txt
if %ERRORLEVEL% EQU 0 goto done

echo.
echo Dependency installation failed. Please install Python 3 and run:
echo python -m pip install -r requirements.txt
pause
exit /b 1

:done
echo.
echo Dependencies installed. You can now run launch_full_chain_demo.cmd
pause
