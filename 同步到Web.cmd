@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo.
echo 正在同步正文到本地 Web（prepare + mkdocs serve）...
echo.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0sync-web.ps1"
set ERR=%ERRORLEVEL%
echo.
if %ERR% neq 0 (
  echo 失败，退出码 %ERR%。请把上方报错截图排查。
  pause
  exit /b %ERR%
)
echo 可关闭本窗口。serve 若新启动则在后台最小化运行。
pause
