@echo off
chcp 65001 > nul
setlocal
cd /d "%~dp0.."
set PYTHON=C:\Python314\python.exe

:: Kill old processes on ports 8800 and 5000 (if any)
powershell -Command "Get-NetTCPConnection -LocalPort 8800 -ErrorAction SilentlyContinue | ForEach-Object { taskkill /f /pid $_.OwningProcess } 2>$null" >nul 2>&1
powershell -Command "Get-NetTCPConnection -LocalPort 5000 -ErrorAction SilentlyContinue | ForEach-Object { taskkill /f /pid $_.OwningProcess } 2>$null" >nul 2>&1
timeout /t 1 /nobreak > nul

:: Step 1: Start quota proxy
echo [1/3] Starting quota proxy on :8800...
start "proxy" %PYTHON% proxy\proxy.py
timeout /t 2 /nobreak > nul

:: Step 2: Start admin panel
echo [2/3] Starting admin panel on :5000...
start "admin" %PYTHON% admin\app.py
timeout /t 2 /nobreak > nul

:: Step 3: Launch Agent Teams
echo [3/3] Starting Agent Teams...
%PYTHON% scripts\launch_agents.py

pause
