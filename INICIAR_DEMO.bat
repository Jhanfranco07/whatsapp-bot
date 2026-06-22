@echo off
setlocal
cd /d "%~dp0"
title Verificacion del Orientador USIL

echo Verificando la configuracion...
python scripts\check_setup.py
if errorlevel 1 (
  echo.
  echo Corrige los puntos marcados como ERROR antes de continuar.
  pause
  exit /b 1
)

echo.
echo Iniciando los servicios en ventanas separadas...
start "1 - Orientador USIL - API" cmd /k "cd /d ""%~dp0"" && python scripts\start_api.py"
timeout /t 3 /nobreak >nul
start "2 - Orientador USIL - WhatsApp" cmd /k "cd /d ""%~dp0bridge"" && npm start"
timeout /t 2 /nobreak >nul
start "3 - Orientador USIL - Worker" cmd /k "cd /d ""%~dp0"" && python scripts\process_outbound.py --watch --poll 1 --sent-delay 2"
timeout /t 2 /nobreak >nul
start "" "http://127.0.0.1:8000/admin"

echo Servicios iniciados. Mantiene abiertas las tres ventanas.
exit /b 0
