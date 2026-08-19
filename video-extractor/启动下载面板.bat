@echo off
chcp 65001 >nul 2>&1
cd /d "D:\视频测试\1号文件夹"

:: 启动服务
start "" /B node 视频嗅探面板.js

:: 等待
timeout /t 2 /nobreak >nul 2>&1

:: 打开面板
start "" http://localhost:8765
