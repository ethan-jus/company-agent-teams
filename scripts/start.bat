@echo off
setlocal
cd /d "%~dp0.."
set PYTHON=C:\Python314\python.exe

:: 1. 启动额度代理
echo [1/3] Starting quota proxy...
start "proxy" %PYTHON% proxy\proxy.py
timeout /t 2 /nobreak > nul

:: 2. 启动管理面板
echo [2/3] Starting admin panel...
start "admin" %PYTHON% admin\app.py
timeout /t 2 /nobreak > nul

:: 3. 启动 Agent Teams
echo [3/3] Starting Agent Teams...
%PYTHON% scripts\launch_agents.py
