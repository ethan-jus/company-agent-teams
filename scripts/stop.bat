@echo off
echo Stopping all components...
taskkill /fi "WINDOWTITLE eq QuotaProxy" /f > nul 2>&1
taskkill /fi "WINDOWTITLE eq AdminPanel" /f > nul 2>&1
taskkill /fi "WINDOWTITLE eq ClaudeCode" /f > nul 2>&1
echo All components stopped.
