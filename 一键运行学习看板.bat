@echo off
chcp 65001 >nul
cd /d "%~dp0"

if exist "D:\Python3_13\python.exe" (
  set "PYTHON_EXE=D:\Python3_13\python.exe"
) else (
  set "PYTHON_EXE=python"
)

"%PYTHON_EXE%" run.py
pause
