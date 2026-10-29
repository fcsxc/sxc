@echo off
REM ---------------------------------------------------------------------------
REM 重置本地状态（Windows）：删除 .data 目录。
REM ---------------------------------------------------------------------------
setlocal
set "HERE=%~dp0"
cd /d "%HERE%"
if exist "%HERE%.data" rmdir /s /q "%HERE%.data"
echo 已重置：.data\ 已删除（seekdb 索引 + PowerContext 本地库）
endlocal
