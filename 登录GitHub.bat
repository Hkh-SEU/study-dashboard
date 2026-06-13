@echo off
chcp 65001 >nul

set "GH_EXE=C:\Program Files\GitHub CLI\gh.exe"

if not exist "%GH_EXE%" (
  echo GitHub CLI was not found at:
  echo %GH_EXE%
  echo.
  echo Please restart PowerShell or reinstall GitHub CLI.
  pause
  exit /b 1
)

"%GH_EXE%" auth login --web --git-protocol https

echo.
echo If login succeeded, you can close this window.
pause
