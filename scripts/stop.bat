@echo off
echo Stopping proxy and admin panel...
taskkill /fi "WINDOWTITLE eq proxy" /f > nul 2>&1
taskkill /fi "WINDOWTITLE eq admin" /f > nul 2>&1
echo Done.
