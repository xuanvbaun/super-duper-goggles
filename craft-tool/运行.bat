@echo off
title 工艺清单生成程序
cd /d "%~dp0"

echo ================================================
echo         工艺清单生成程序（图纸材料表PDF -^> Excel）
echo ================================================
echo.

rem ---- 1. 找一个装好了依赖库的 Python（自动扫描机器上所有版本）----
set "PYEXE="
for /f "delims=" %%P in ('py -3 find_python.py 2^>nul') do set "PYEXE=%%P"
if "%PYEXE%"=="" for /f "delims=" %%P in ('python find_python.py 2^>nul') do set "PYEXE=%%P"
if "%PYEXE%"=="" (
    echo [×] 没有找到装好依赖库的 Python！
    echo     请先安装 Python 和依赖库，再运行本程序：
    echo       python -m pip install -r requirements.txt
    goto end
)
echo [√] 使用 Python：%PYEXE%
echo.

rem ---- 2. 获取项目文件夹：支持拖到 bat 图标（%%1）或拖进窗口/手输 ----
set "SRC=%~1"
if not "%SRC%"=="" goto check

echo 用法：把清单文件夹拖到这个窗口里（路径会自动填入），然后按回车；
echo       或直接输入完整路径后回车。
echo.
set /p "SRC=清单文件夹路径："
if "%SRC%"=="" goto end

rem ---- 3. 启动自检（含项目文件夹）----
:check
echo.
echo 正在检查运行环境...
"%PYEXE%" precheck.py "%SRC%"
if errorlevel 1 goto end

rem ---- 4. 执行生成 ----
echo.
echo 正在处理：%SRC%
echo.
"%PYEXE%" run.py "%SRC%"

:end
echo.
pause
