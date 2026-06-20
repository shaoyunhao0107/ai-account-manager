# AI 账号资产管理系统

> 单机/局域网使用的 AI 账号（Codex / Claude Code 等）资产管理系统。
> SQLite 存储，FastAPI + Jinja2 Web 界面，密码加密，支持凭证图片、回收站、分类管理、CSV 导入导出。

## 功能特性

- 📋 **账号管理**：28 字段完整管理（开号/交付/VPS/节点/凭证/封号记录等）
- 🔐 **密码加密**：邮箱密码、GPT 密码用 Fernet 对称加密存储
- 📋 **凭证图片**：支持拖拽 / 上传 / 粘贴截图，点击放大查看
- 🗑️ **回收站**：软删除 + 恢复，批量删除，多选
- 🏷️ **分类管理**：账号选型 / 部门 预设管理，可增删改查、批量导入、用户-部门对应表
- 📥 **CSV 导入**：中文字段名自动识别，UTF-8/GBK 编码兼容
- 📊 **导出 Excel**：严格按 CSV 28 字段顺序导出
- 🔍 **搜索**：支持用户/邮箱/订单号/IP/verge/vless 节点地址搜索
- 🎚️ **筛选**：部门 / 选型 / 状态三维筛选
- ↕️ **排序**：ID / 用户 / 部门 / 选型 / 状态 点击表头排序
- 📄 **分页**：每页 20/50/100/200 条可调
- 🎛️ **列显示/隐藏**：自定义列表显示哪些列（localStorage 记忆）
- 🔁 **节点配置**：verge / vless 地址显示 + 一键复制
- 🔑 **简单鉴权**：单一管理员密码 + Session Cookie

## 快速开始

### 方式 1：Docker Compose（推荐）

```bash
# 1. 克隆仓库
git clone https://github.com/shaoyunhao0107/ai-account-manager.git
cd ai-account-manager

# 2. 一键启动
docker-compose up -d

# 3. 访问
# http://localhost:8000
# 默认密码：admin123
```

### 方式 2：Ubuntu 原生安装

详见 [docs/UBUNTU_INSTALL.md](docs/UBUNTU_INSTALL.md)

### 方式 3：Windows

```bat
:: 1. 双击 run.bat
:: 2. 访问 http://localhost:8000
:: 默认密码：admin123
```

## 配置

所有配置通过环境变量：

| 变量 | 说明 | 默认值 |
|---|---|---|
| `AAM_ADMIN_PASSWORD` | 登录密码 | `admin123` |
| `AAM_MASTER_PASSWORD` | 数据加密主密码（**不可更改**） | `change-me-please` |
| `AAM_SESSION_SECRET` | Session 签名密钥 | `dev-secret-change-in-prod` |
| `AAM_DB_URL` | 数据库连接（PostgreSQL） | 空（用 SQLite） |
| `AAM_DB_PATH` | SQLite 数据库路径（仅 SQLite 模式） | `./data/accounts.db` |

### 数据库选择

| 模式 | 配置 | 适用场景 |
|---|---|---|
| **PostgreSQL**（推荐） | `AAM_DB_URL=postgresql://user:pass@host/db` | 生产、多人、大数据量 |
| **SQLite**（默认） | 不设 `AAM_DB_URL` | 开发、单机、小数据量 |

⚠️ **重要**：`AAM_MASTER_PASSWORD` 一旦设置后不可更改，否则旧密文无法解密。正式使用前务必修改。

## 技术栈

- **后端**：Python 3.10+ / FastAPI / SQLModel / SQLite
- **前端**：Jinja2 服务端渲染 / 原生 JS / 暗色主题 CSS
- **加密**：cryptography (Fernet / PBKDF2)
- **Excel**：openpyxl

## 项目结构

```
ai-account-manager/
├── app/
│   ├── main.py              # FastAPI 路由（账号 CRUD + 导入导出 + 分类 + 回收站）
│   ├── models.py            # SQLModel 数据模型
│   ├── category_model.py    # 分类预设模型
│   ├── database.py          # SQLite 连接
│   ├── security.py          # Fernet 加解密
│   └── auth.py              # Session 鉴权
├── templates/               # Jinja2 模板
├── static/                  # CSS / CSV 模板
├── data/                    # 数据库 + 凭证图片（运行时生成）
├── docs/
│   └── UBUNTU_INSTALL.md    # Ubuntu 安装文档
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
├── run.bat                  # Windows 启动脚本
└── README.md
```

## License

MIT
