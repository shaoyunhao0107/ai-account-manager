"""数据库连接与初始化"""
import os
from sqlmodel import SQLModel, Session, create_engine, select

DB_PATH = os.environ.get("AAM_DB_PATH", os.path.join(os.path.dirname(__file__), "..", "data", "accounts.db"))
DB_PATH = os.path.abspath(DB_PATH)
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

engine = create_engine(f"sqlite:///{DB_PATH}", echo=False, connect_args={"check_same_thread": False})


def init_db():
    """建表（如不存在）"""
    # 确保模型被导入，触发 SQLModel.metadata 注册
    from . import models  # noqa: F401
    SQLModel.metadata.create_all(engine)


def get_session():
    with Session(engine) as s:
        yield s
