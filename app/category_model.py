"""分类预设表（账号选型 / 部门），可由用户增删和导入"""
from typing import Optional
from sqlmodel import SQLModel, Field


class Category(SQLModel, table=True):
    __tablename__ = "categories"

    id: Optional[int] = Field(default=None, primary_key=True)
    kind: str = Field(index=True)   # 'plan_type' 或 'department'
    value: str = Field(index=True)  # 实际值
    sort_order: int = Field(default=0)
