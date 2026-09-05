@echo off
chcp 65001 >nul 2>&1
cd /d "%~dp0"

:: 启动服务
where node >nul 2>&1
if errorlevel 1 (
    echo [错误] 未找到 Node.js，请先安装 Node.js 后重试。
    pause
    exit /b 1
)
start "" /B node "%~dp0视频嗅探面板.js"

:: 等待
timeout /t 2 /nobreak >nul 2>&1

:: 打开面板
start "" http://localhost:8765
