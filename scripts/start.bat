@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0.."
set PYTHON=C:\Python314\python.exe

:: 1. 启动额度代理
echo [1/3] Starting quota proxy...
start "QuotaProxy" cmd /c "%PYTHON% proxy\proxy.py > logs\proxy.log 2>&1"
timeout /t 2 /nobreak > nul

:: 2. 启动管理面板
echo [2/3] Starting admin panel...
start "AdminPanel" cmd /c "%PYTHON% admin\app.py > logs\admin.log 2>&1"
timeout /t 2 /nobreak > nul

:: 3. 启动 Claude Code
echo [3/3] Starting Claude Code...
start "ClaudeCode" cmd /c "claude"

echo.
echo ===============================================
echo  Company AI Agent System Started
echo  Admin Panel: http://localhost:5000
echo  Quota Proxy: http://localhost:8800
echo ===============================================
