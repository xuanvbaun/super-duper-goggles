@echo off
title 工艺清单生成程序
cd /d "%~dp0"

echo ================================================
echo         工艺清单生成程序（图纸材料表PDF -^> Excel）
echo ================================================
echo.

rem ---- 1. 找可用的 Python：优先 py -3，不行再试 python ----
set "PY="
where py >nul 2>nul && set "PY=py -3"
if "%PY%"=="" (
    where python >nul 2>nul && set "PY=python"
)
if "%PY%"=="" (
    echo [×] 未找到 Python！
    echo     请先在这台电脑上安装 Python（安装时勾选"Add Python to PATH"），
    echo     并安装本程序所需依赖库，再运行本程序。
    goto end
)

rem ---- 2. 启动前自检（环境/模板/修正文件；若拖了文件夹也一并检查）----
echo.
echo 正在检查运行环境...
%PY% precheck.py "%~1"
if errorlevel 1 goto end

rem ---- 3. 输入项目文件夹：支持拖到 bat 图标（%%1）或拖进窗口/手输 ----
set "SRC=%~1"
if not "%SRC%"=="" goto run

echo.
echo 用法：把清单文件夹拖到这个窗口里（路径会自动填入），然后按回车；
echo       或直接输入完整路径后回车。
echo.
set /p "SRC=清单文件夹路径："
if "%SRC%"=="" goto end

rem ---- 4. 执行生成 ----
:run
echo.
echo 正在处理：%SRC%
echo.
%PY% run.py "%SRC%"

:end
echo.
pause
