# AI 账号资产管理系统 — 实施计划

**Goal:** 单机/局域网使用的 AI 账号资产管理系统，SQLite 存储，FastAPI + Jinja2 Web 界面，简单密码登录。

**Architecture:** 单仓库 FastAPI 应用。SQLite 数据库文件本地存储。前端用服务端渲染（Jinja2 + HTMX），避免前后端分离的复杂度。敏感字段（密码、vless 节点）用 Fernet 对称加密存储，密钥由主密码派生。

**Tech Stack:** Python 3.11、FastAPI、Uvicorn、Jinja2、SQLModel、cryptography (Fernet)、python-multipart。

---

## 字段设计（7 个域，27 字段 + 1 张封号历史子表）

### 主表 `accounts` (1 个账号 = 1 行)
| 域 | 字段 | 类型 | 备注 |
|---|---|---|---|
| A 基础 | id | int PK | 自增 |
| A | user_name | text | 用户姓名 |
| A | department | text | 部门枚举 |
| A | plan_type | text | 账号选型枚举 |
| A | first_open_date | date | 首次开号日期 |
| A | status | text | 可用/被封/待交付/已停用 |
| B 交付 | delivered | bool | 是否已交付 |
| B | delivery_date | date | 交付日期 |
| B | installed | bool | 是否安装 |
| B | installer | text | 安装人/方式 |
| B | os_version | text | 电脑系统及版本 |
| C VPS | server_order | text | 服务器订单号 |
| C | vps_ip_masked | text | IP 脱敏 (39/71/123/187) |
| C | vps_pure | bool | 是否纯净 |
| C | vps_in_use | bool | VPS 是否使用中 |
| C | new_vps_address | text | 新 VPS 地址 |
| D 节点 | verge_url | text(enc) | clash 配置地址 |
| D | vlmess_url | text(enc) | 小火箭 vless 地址 |
| E 凭证 | cc_email | text | CC 邮箱 |
| E | email_password_enc | blob | 邮箱密码(加密) |
| E | gpt_password_enc | blob | GPT 密码(加密) |
| E | plan_amount | text | 套餐金额 |
| E | converted_to_codex | bool | 是否转 Codex |
| F 订阅 | plan_start_date | date | 当前套餐开始日期 |
| F | plan_end_date | date | 当前套餐到期日期 |
| F | distributed | bool | 当前账号是否已发放 |

### 子表 `ban_history` (封号/补号历史，一对多)
| 字段 | 类型 | 备注 |
|---|---|---|
| id | int PK | |
| account_id | int FK | 关联 accounts.id |
| ban_sequence | int | 第几次封号 (1/2/3...) |
| ban_date | date | 封号日期 |
| ban_reason | text | 封号原因 |
| replacement_date | date | 补号日期 |
| replacement_voucher | text | 补号凭证 (截图路径或链接) |
| status_after | text | 补号后状态 |

---

## Tasks

### Task 1: 项目骨架 + 依赖
- 创建 `requirements.txt`、`app/__init__.py`、`app/main.py`、`app/database.py`、`app/models.py`、`app/security.py`、`app/auth.py`、`templates/`、`static/`
- `pip install -r requirements.txt`

### Task 2: 数据库模型 (SQLModel)
- 定义 `Account`、`BanHistory` SQLModel 模型
- 初始化连接、建表函数

### Task 3: 加密模块
- `security.py`: 用主密码通过 PBKDF2 派生 Fernet 密钥
- 提供 `encrypt_field()` / `decrypt_field()`

### Task 4: 简单鉴权
- 单一管理员密码（环境变量 `ADMIN_PASSWORD`）
- Session cookie 登录

### Task 5: 路由
- GET `/` 账号列表（搜索、过滤）
- GET `/accounts/new` 新增表单
- POST `/accounts` 创建
- GET `/accounts/{id}` 详情（含封号历史）
- POST `/accounts/{id}/ban` 添加封号记录
- POST `/accounts/{id}/delete` 删除
- GET `/export` 导出 Excel
- POST `/import` 导入 Excel

### Task 6: 模板
- `base.html` 布局
- `login.html` 登录
- `list.html` 列表（搜索 + 部门/状态过滤）
- `form.html` 新增/编辑
- `detail.html` 详情 + 封号历史子表

### Task 7: 启动脚本
- `run.sh` / `run.bat`: 设置默认密码、启动 uvicorn 监听 0.0.0.0:8000

### Task 8: 验证
- 启动服务、登录、新增账号、查看列表、加封号记录、导出

---

## 安全注意
- 局域网部署仍需主密码登录
- 敏感字段数据库中为密文
- 导出 Excel 时提示"将包含明文敏感字段"
- 不记录任何密码到日志
