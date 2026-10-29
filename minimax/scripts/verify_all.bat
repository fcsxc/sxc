@echo off
REM ---------------------------------------------------------------------------
REM 跑完整个验证样例。用法：scripts\verify_all.bat
REM ---------------------------------------------------------------------------
setlocal
set "HERE=%~dp0.."
cd /d "%HERE%"

set "PYTHON_BIN=%PYTHON%"
if "%PYTHON_BIN%"=="" set "PYTHON_BIN=python"
if exist "%HERE%\.venv\Scripts\python.exe" set "PYTHON_BIN=%HERE%\.venv\Scripts\python.exe"

"%PYTHON_BIN%" scripts\verify_all.py
exit /b %ERRORLEVEL%
