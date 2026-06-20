"""数据库连接与初始化（支持 PostgreSQL 和 SQLite，通过 AAM_DB_URL 环境变量切换）"""
import os
from sqlmodel import SQLModel, Session, create_engine

# 数据库连接：优先用环境变量 AAM_DB_URL（PostgreSQL），否则回退到 SQLite
DB_URL = os.environ.get("AAM_DB_URL", "")

if DB_URL:
    # PostgreSQL 模式（如 postgresql://user:pass@localhost/dbname）
    engine = create_engine(DB_URL, echo=False, pool_pre_ping=True)
else:
    # SQLite 模式（默认，单文件）
    DB_PATH = os.environ.get("AAM_DB_PATH", os.path.join(os.path.dirname(__file__), "..", "data", "accounts.db"))
    DB_PATH = os.path.abspath(DB_PATH)
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    engine = create_engine(f"sqlite:///{DB_PATH}", echo=False, connect_args={"check_same_thread": False})


def init_db():
    """建表（如不存在）"""
    from . import models  # noqa: F401  确保模型被导入，触发 SQLModel.metadata 注册
    SQLModel.metadata.create_all(engine)


def get_session():
    with Session(engine) as s:
        yield s
