@echo off
REM AI 账号资产管理系统 - Windows 启动脚本
REM 第一次用：先改下面的两个密码（AAM_ADMIN_PASSWORD 和 AAM_MASTER_PASSWORD）

set AAM_ADMIN_PASSWORD=admin123
set AAM_MASTER_PASSWORD=change-this-master-key
set AAM_SESSION_SECRET=any-random-string-works-here

cd /d "%~dp0"

"C:\Program Files\Python310\python.exe" -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
pause
