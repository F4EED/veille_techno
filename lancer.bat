@echo off
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0lancer.ps1" %*
exit /b %ERRORLEVEL%
