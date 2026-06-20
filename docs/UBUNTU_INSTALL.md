# Ubuntu 安装指南

## 方式 A：Docker Compose（最简单，推荐）

```bash
# 1. 安装 Docker
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER
# 注销重新登录让 docker 组生效

# 2. 克隆仓库
git clone https://github.com/shaoyunhao0107/ai-account-manager.git
cd ai-account-manager

# 3. 修改默认密码（重要！）
# 编辑 docker-compose.yml，修改 AAM_ADMIN_PASSWORD 和 AAM_MASTER_PASSWORD

# 4. 启动
docker-compose up -d

# 5. 查看日志
docker-compose logs -f

# 6. 访问
# http://你的服务器IP:8000
```

**常用命令：**
```bash
docker-compose stop          # 停止
docker-compose start         # 启动
docker-compose restart       # 重启
docker-compose down          # 停止并删除容器（数据保留在 volume）
docker-compose logs -f       # 实时日志
```

**数据备份：**
```bash
# 数据库和凭证图片在 ./data/ 目录
cp -r data/ /backup/data-$(date +%Y%m%d)/
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
git clone https://github.com/shaoyunhao0107/ai-account-manager.git
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

# 持久化到 .env（可选）
cat > .env << EOF
AAM_ADMIN_PASSWORD=$AAM_ADMIN_PASSWORD
AAM_MASTER_PASSWORD=$AAM_MASTER_PASSWORD
AAM_SESSION_SECRET=$AAM_SESSION_SECRET
EOF
```

### 4. 启动（前台测试）

```bash
source .env  # 如果用了 .env
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

### 5. 设为系统服务（生产环境）

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

### 6. Nginx 反向代理（可选，支持 HTTPS）

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
# 备份数据库 + 凭证图片
tar -czf backup-$(date +%Y%m%d).tar.gz data/
```

### Q: 如何恢复数据？
```bash
# 停止服务
docker-compose down  # 或 sudo systemctl stop ai-account-manager

# 恢复
tar -xzf backup-20260101.tar.gz

# 重新启动
docker-compose up -d  # 或 sudo systemctl start ai-account-manager
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
