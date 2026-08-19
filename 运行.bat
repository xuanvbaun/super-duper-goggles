@echo off
title 工艺清单生成程序
cd /d "%~dp0"

echo ================================================
echo         工艺清单生成程序（图纸材料表PDF -^> Excel）
echo ================================================
echo.

set "SRC=%~1"
if not "%SRC%"=="" goto run

echo 用法：把清单文件夹拖到这个窗口里，或手动输入完整路径，然后回车
echo （拖文件夹进窗口会自动填入路径，再按回车即可）
echo.
set /p "SRC=清单文件夹路径："
if "%SRC%"=="" goto end

:run
echo.
echo 正在处理：%SRC%
echo.
where python >nul 2>nul
if errorlevel 1 (
    echo 未找到 Python 或依赖库未安装，请先在电脑上装好 Python 环境和程序所需依赖库。
    goto end
)
python run.py "%SRC%"

:end
echo.
pause
