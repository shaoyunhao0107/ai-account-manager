@echo off
REM AI 账号资产管理系统 - Windows 启动脚本
REM 第一次用：先改下面的密码（AAM_ADMIN_PASSWORD 和 AAM_MASTER_PASSWORD）
REM 数据库：默认 SQLite，如要用 PostgreSQL 设 AAM_DB_URL

set AAM_ADMIN_PASSWORD=admin123
set AAM_MASTER_PASSWORD=please-change-this-key
set AAM_SESSION_SECRET=local-dev-secret-xyz

REM === 用 PostgreSQL（推荐）===
set AAM_DB_URL=postgresql://aam_user:aam_pass_2026@localhost:5432/ai_account_manager

REM === 用 SQLite（默认，取消下面注释切换）===
REM set AAM_DB_URL=
REM set AAM_DB_PATH=./data/accounts.db

cd /d "%~dp0"

"C:\Program Files\Python310\python.exe" -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
pause
