@echo off
setlocal
cd /d "%~dp0.."
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0pack-content.ps1"
exit /b %ERRORLEVEL%
