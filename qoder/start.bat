@echo off
rem 学记 StudyMemo 一键启动（Windows）
rem 1) 准备 PowerContext 配置（SQLite + 基础记忆）
rem 2) 启动 PowerContext Server（后台，端口 8000）
rem 3) 启动学记 Flask 应用（端口 5000）
setlocal
cd /d "%~dp0"

if "%PC_PORT%"=="" set PC_PORT=8000
if "%APP_PORT%"=="" set APP_PORT=5000
set CONFIG_DIR=powercontext-config

if not exist "%CONFIG_DIR%" mkdir "%CONFIG_DIR%"
if not exist "%CONFIG_DIR%\.env" (
  echo == 生成 PowerContext 配置（模板模式：SQLite + 基础记忆） ==
  echo Y | powercontext config init --template --language zh --output "%CONFIG_DIR%\.env"
)

echo == 启动 PowerContext Server（端口 %PC_PORT%） ==
start "PowerContext" /D "%CONFIG_DIR%" cmd /c "powercontext server run --env-file .env > powercontext.log 2>&1"

echo == 等待 PowerContext 就绪 ==
timeout /t 8 /nobreak > nul

echo == 启动学记应用（端口 %APP_PORT%） ==
set POWERCONTEXT_URL=http://127.0.0.1:%PC_PORT%
set PORT=%APP_PORT%
python -m app.main
endlocal
