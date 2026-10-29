@echo off
REM ---------------------------------------------------------------------------
REM 一键准备（Windows）：安装依赖 -> 导入工程资料到 seekdb -> 构造开发上下文。
REM 用法：start.bat
REM ---------------------------------------------------------------------------
setlocal
set "HERE=%~dp0"
cd /d "%HERE%"

if "%PYTHON%"=="" set "PYTHON=python"
if "%VENV_DIR%"=="" set "VENV_DIR=%HERE%.venv"
if "%TASK%"=="" set "TASK=为 OrderFlow 的 orderflow.refund 模块实现 SPEC-REFUND-014：按退款原因决定运费是否可退，优惠券按 SPEC-PRICE-003 分摊，并按 SPEC-REFUND-020 把单次退款金额限制为订单实付金额的 50%。需要实现的符号是 orderflow.refund.refundable_amount。"

if not exist "%VENV_DIR%" (
  echo [1/3] 创建虚拟环境：%VENV_DIR%
  %PYTHON% -m venv "%VENV_DIR%"
)
call "%VENV_DIR%\Scripts\activate.bat"

echo [2/3] 安装依赖
python -m pip install --quiet --upgrade pip
python -m pip install --quiet -r requirements.txt

echo [3/3] 导入工程资料到 seekdb 并构造上下文
python -m sddctx.cli import
python -m sddctx.cli context --task "%TASK%" --out artifacts\context-pack.md --quiet

echo.
echo 完成。上下文包：artifacts\context-pack.md
endlocal
