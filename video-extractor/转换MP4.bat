@echo off
chcp 65001 >nul
title 视频转MP4工具
setlocal enabledelayedexpansion

:: 检查 FFmpeg
where ffmpeg >nul 2>&1
if %errorlevel%==0 (
    set FFMPEG=ffmpeg
) else if exist "%~dp0ffmpeg\bin\ffmpeg.exe" (
    set FFMPEG=%~dp0ffmpeg\bin\ffmpeg.exe
) else (
    echo [错误] 找不到 ffmpeg.exe
    echo 安装方法: winget install Gyan.FFmpeg
    pause
    exit /b 1
)

echo ══════════════════════════════════════════
echo   🎬 视频转 MP4 工具
echo ══════════════════════════════════════════
echo.

set INPUT=%~1

if "%INPUT%"=="" (
    echo 用法:
    echo   拖拽视频文件到此 bat 文件上即可转换
    echo   或者: 转换MP4.bat "视频文件路径"
    echo.
    set /p INPUT="请输入视频文件路径: "
)

if not exist "%INPUT%" (
    echo [错误] 文件不存在: %INPUT%
    pause
    exit /b 1
)

:: 生成输出文件名
for %%F in ("%INPUT%") do (
    set "DIR=%%~dpF"
    set "NAME=%%~nF"
    set "EXT=%%~xF"
)

set OUTPUT=%DIR%%NAME%_mp4.mp4

echo 输入: %INPUT%
echo 输出: %OUTPUT%
echo.

:: ==== 格式校验 ====
:: 检查是不是 HTML 文件（下载错误的情况）
"%FFMPEG%" -i "%INPUT%" -f null NUL 2>&1 | findstr /i "Invalid data found" >nul
if %errorlevel%==0 (
    echo ❌ 这不是有效的视频文件！
    echo.
    echo 可能的原因:
    echo   1. 下载到的是网页(HTML)而非视频 — 视频源可能是HLS流
    echo   2. 文件损坏或不完整
    echo.
    echo 解决方法:
    echo   1. 回到视频网页，点击右下角紫色按钮📹
    echo   2. 双击“启动下载面板.bat”，在网页面板中重新解析并下载
    pause
    exit /b 1
)

:: ==== 转换 ====

:: 检查是否是 M3U8/HLS
echo %INPUT% | findstr /i "\.m3u8" >nul
if %errorlevel%==0 (
    echo [M3U8流] 正在下载并转换为 MP4...
    "%FFMPEG%" -i "%INPUT%" -c copy -bsf:a aac_adtstoasc "%OUTPUT%" -y
    goto done
)

:: 检查是否已经是 MP4
echo %INPUT% | findstr /i "\.mp4$" >nul
if %errorlevel%==0 (
    echo [已经是 MP4] 无需转换
    if "%~2"=="--reencode" goto reencode
    pause
    exit /b 0
)

:reencode
echo 正在转换为 MP4 (H.264 + AAC)...
"%FFMPEG%" -i "%INPUT%" -c:v libx264 -preset fast -crf 23 -c:a aac -b:a 128k -movflags +faststart "%OUTPUT%" -y

:done
if %errorlevel%==0 (
    echo.
    echo ✅ 转换完成！
    echo    输出文件: %OUTPUT%
    explorer /select,"%OUTPUT%"
) else (
    echo.
    echo ❌ 转换失败，请检查输入文件是否损坏
)
pause
