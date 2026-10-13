@echo off
setlocal
title AgenticRAG Workbench
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\start-workbench.ps1" -Prepare -OpenBrowser %*
set "workbenchExit=%ERRORLEVEL%"
if not "%workbenchExit%"=="0" (
    echo.
    echo [ERROR] Workbench could not start. See the message above and README.md.
    pause
)
exit /b %workbenchExit%
