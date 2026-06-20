# Ubuntu 安装指南

> **版本说明**：本系统支持分支化部署。
> - `main` 分支 = 稳定版本（已合并到主线的功能）
> - `feat/expiry-reminder` 分支 = **含账号到期提醒 + 智能到期日期**（待合并的预览版）
>
> 首次部署推荐直接用 `feat/expiry-reminder` 分支，功能更完整。生产环境等 PR 合并到 main 后再切回 main 也可以。

---

## 方式 A：Docker Compose（最简单，推荐）

### 首次部署

```bash
# 1. 安装 Docker
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER
# 注销重新登录让 docker 组生效

# 2. 克隆仓库（用 -b 指定分支）
git clone -b feat/expiry-reminder https://github.com/shaoyunhao0107/ai-account-manager.git
cd ai-account-manager

# 3. 修改默认密码（重要！别用默认值）
# 编辑 docker-compose.yml，修改以下项：
#   POSTGRES_PASSWORD=aam_pass_2026          ← 数据库密码，改成强密码
#   AAM_ADMIN_PASSWORD=admin123              ← 登录密码，改成强密码
#   AAM_MASTER_PASSWORD=please-change-this-key  ← 加密主密码（设置后不可改）
#   AAM_SESSION_SECRET=local-dev-secret-xyz     ← session 签名密钥，随机字符串
# 同时把 app 服务里的 AAM_DB_URL 里的 aam_pass_2026 改成上面的新数据库密码

# 4. 一键启动（PostgreSQL + 应用）
docker compose up -d --build

# 5. 查看日志（确认启动成功）
docker compose logs -f app

# 6. 访问
# http://你的服务器IP:8000
# 用你在第 3 步设置的 AAM_ADMIN_PASSWORD 登录
```

### 从已有 main 分支升级到 feat/expiry-reminder

如果你之前已经用 `main` 分支部署过，想切到新分支拿到期提醒功能：

```bash
cd /path/to/ai-account-manager

# 1. 拉取新分支代码
git fetch origin
git checkout feat/expiry-reminder
git pull

# 2. 重新构建并重启（数据自动保留）
docker compose up -d --build

# 3. 【重要】回填已有账号的到期日期
# 新代码会自动给"新导入的账号"算到期日（开号日 + 30 天），
# 但你之前用 main 分支导入的老账号没有 plan_end_date，需要一次性补算：
docker compose exec app python -c "
import os
from datetime import timedelta
from sqlmodel import Session, select
from app import database, models
database.init_db()
with Session(database.engine) as s:
    rows = s.exec(select(models.Account).where(
        models.Account.deleted_at.is_(None),
        models.Account.plan_start_date.is_not(None),
        models.Account.plan_end_date.is_(None),
    )).all()
    for a in rows:
        a.plan_end_date = a.plan_start_date + timedelta(days=30)
        s.add(a)
    s.commit()
    print(f'已回填 {len(rows)} 个账号的到期日（= 开号日 + 30 天）')
"

# 4. 访问 http://你的服务器IP:8000/expiry 查看到期提醒
```

**常用命令：**
```bash
docker compose stop          # 停止
docker compose start         # 启动
docker compose restart       # 重启
docker compose down          # 停止并删除容器（数据保留在 volume）
docker compose logs -f       # 实时日志
docker compose pull && docker compose up -d  # 拉取最新代码更新
```

**数据备份：**
```bash
# 备份 PostgreSQL 数据库
docker compose exec db pg_dump -U aam_user ai_account_manager > backup-$(date +%Y%m%d).sql

# 备份凭证图片（在 ./data/vouchers/ 目录）
tar -czf vouchers-$(date +%Y%m%d).tar.gz data/vouchers/
```

---

## 方式 B：原生 Python 安装

### 1. 系统依赖

```bash
sudo apt update
sudo apt install -y python3 python3-pip python3-venv git
```

### 2. 克隆 + 虚拟环境

```bash
# 拉取 feat/expiry-reminder 分支（含到期提醒功能）
git clone -b feat/expiry-reminder https://github.com/shaoyunhao0107/ai-account-manager.git
cd ai-account-manager

python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 3. 配置环境变量

```bash
# 生成随机密钥
export AAM_ADMIN_PASSWORD="你的登录密码"
export AAM_MASTER_PASSWORD="你的加密主密码_一旦设置不可更改"
export AAM_SESSION_SECRET=$(python3 -c "import secrets; print(secrets.token_hex(32))")

# 数据库（任选其一）：
# - PostgreSQL（推荐，生产用）：
export AAM_DB_URL="postgresql://aam_user:你的数据库密码@localhost:5432/ai_account_manager"
# - SQLite（默认，无需配置）：
# export AAM_DB_PATH=./data/accounts.db

# 持久化到 .env
cat > .env << EOF
AAM_ADMIN_PASSWORD=$AAM_ADMIN_PASSWORD
AAM_MASTER_PASSWORD=$AAM_MASTER_PASSWORD
AAM_SESSION_SECRET=$AAM_SESSION_SECRET
AAM_DB_URL=$AAM_DB_URL
EOF
```

### 4. 启动（前台测试）

```bash
source .env
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

### 5. 从 main 分支升级到 feat/expiry-reminder（原生部署）

```bash
cd /path/to/ai-account-manager
source venv/bin/activate

# 切换分支
git fetch origin
git checkout feat/expiry-reminder
git pull

# 重启服务（systemd 用户）
sudo systemctl restart ai-account-manager

# 回填已有账号的到期日（同 Docker 部署的脚本）
source .env
python -c "
from datetime import timedelta
from sqlmodel import Session, select
from app import database, models
database.init_db()
with Session(database.engine) as s:
    rows = s.exec(select(models.Account).where(
        models.Account.deleted_at.is_(None),
        models.Account.plan_start_date.is_not(None),
        models.Account.plan_end_date.is_(None),
    )).all()
    for a in rows:
        a.plan_end_date = a.plan_start_date + timedelta(days=30)
        s.add(a)
    s.commit()
    print(f'已回填 {len(rows)} 个账号的到期日')
"
```

### 6. 设为系统服务（生产环境）

```bash
sudo cat > /etc/systemd/system/ai-account-manager.service << 'EOF'
[Unit]
Description=AI Account Manager
After=network.target

[Service]
Type=simple
User=你的用户名
WorkingDirectory=/home/你的用户名/ai-account-manager
EnvironmentFile=/home/你的用户名/ai-account-manager/.env
ExecStart=/home/你的用户名/ai-account-manager/venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable ai-account-manager
sudo systemctl start ai-account-manager

# 查看状态
sudo systemctl status ai-account-manager

# 查看日志
sudo journalctl -u ai-account-manager -f
```

### 7. Nginx 反向代理（可选，支持 HTTPS）

```bash
sudo apt install -y nginx

sudo cat > /etc/nginx/sites-available/ai-account << 'EOF'
server {
    listen 80;
    server_name your-domain.com;  # 改成你的域名或 IP

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # 凭证图片上传大小
    client_max_body_size 10M;
}
EOF

sudo ln -s /etc/nginx/sites-available/ai-account /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl restart nginx

# 如需 HTTPS：
# sudo apt install certbot python3-certbot-nginx
# sudo certbot --nginx -d your-domain.com
```

---

## 常见问题

### Q: 如何备份数据？
```bash
# 备份数据库（Docker 部署用 pg_dump，原生部署同样适用）
docker compose exec db pg_dump -U aam_user ai_account_manager > backup-$(date +%Y%m%d).sql

# 备份凭证图片
tar -czf vouchers-$(date +%Y%m%d).tar.gz data/vouchers/
```

### Q: 如何恢复数据？
```bash
# 停止服务
docker compose down  # 或 sudo systemctl stop ai-account-manager

# 恢复 PostgreSQL 数据库
docker compose up -d db              # 先起数据库
cat backup-20260101.sql | docker compose exec -T db psql -U aam_user ai_account_manager

# 恢复凭证图片
tar -xzf vouchers-20260101.tar.gz

# 重启完整服务
docker compose up -d
```

### Q: 忘记登录密码？
修改环境变量 `AAM_ADMIN_PASSWORD` 重启即可。

### Q: 加密主密码忘了？
无法恢复。旧密码密文会变成 `[解密失败]`，需重新录入邮箱/GPT 密码。

### Q: 防火墙配置？
```bash
sudo ufw allow 8000/tcp  # 开放 8000 端口
sudo ufw status
```

---

## 新功能说明（feat/expiry-reminder 分支）

### ⏰ 账号到期提醒

针对 **Claude Code / Codex / Claude Pro** 等订阅制账号，到期前自动提醒。

**功能点：**
- 列表页顶部**红色脉冲横幅**：显示"X 个账号将在 N 天内到期"
- 独立的 `/expiry` 页面：按 **已过期 / 3 天内 / 7 天内 / 15 天内** 四档分组展示
- 导航栏 **⏰ 提醒** 按钮带红色数字角标（每分钟自动轮询）
- 只对 **"可用" / "待交付"** 状态的账号提醒（"被封" / "已停用" 不打扰）

**提醒档位调整：** 编辑 `app/main.py` 第 348 行附近的 `EXPIRY_THRESHOLDS = [3, 7, 15]`。

### 📅 智能到期日期

填写"第一次套餐开始时间"后，系统自动按 **+30 天** 计算到期日。

**规则：**
| 场景 | 用户填的开始日 | 用户填的到期日 | 系统算出的结果 |
|------|----------------|----------------|----------------|
| 只填开始日 | 2026-06-20 | (空) | **自动 = 2026-07-20**（+30 天） |
| 手动覆盖 | 2026-06-20 | 2026-08-19 | 2026-08-19（保留用户填的） |
| 都不填 | (空) | (空) | 空 |
| 只填到期日 | (空) | 2026-12-31 | 2026-12-31 |

**默认周期调整：** 编辑 `app/main.py` 第 584 行附近的 `DEFAULT_PLAN_DAYS = 30`，改成 60 / 90 等。

**前端体验：** 编辑表单的"F · 订阅周期"区块有 "🔁 自动" 按钮，点击可预览 +30 天后的到期日。手动填写到期日后会自动禁用覆盖（避免误操作）。

