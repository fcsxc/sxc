@echo off
REM ---------------------------------------------------------------------------
REM 启动 PowerContext Server（Windows）。用法：scripts\start_powercontext.bat
REM ---------------------------------------------------------------------------
setlocal
set "HERE=%~dp0.."
cd /d "%HERE%"

if "%POWERCONTEXT_CONFIG_DIR%"=="" set "POWERCONTEXT_CONFIG_DIR=%HERE%\.data\powercontext"
set "ENV_FILE=%POWERCONTEXT_CONFIG_DIR%\.env"
if not exist "%POWERCONTEXT_CONFIG_DIR%" mkdir "%POWERCONTEXT_CONFIG_DIR%"

if not exist "%ENV_FILE%" (
  echo [powercontext] 首次启动，生成配置：%ENV_FILE%
  where powercontext >nul 2>nul
  if errorlevel 1 (
    echo [powercontext] 未找到 powercontext 命令，请先安装：pip install "powercontext[cli,server]==1.4.1"
    exit /b 1
  )
  echo y | powercontext config init --template --language zh --output "%ENV_FILE%"
)

if "%POWERCONTEXT_URL%"=="" set "POWERCONTEXT_URL=http://127.0.0.1:8000"
echo [powercontext] 启动服务：%POWERCONTEXT_URL%
powercontext server run --env-file "%ENV_FILE%"
endlocal
