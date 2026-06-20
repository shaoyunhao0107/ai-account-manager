"""数据模型 (SQLModel)"""
from datetime import date
from typing import Optional, List
from sqlmodel import SQLModel, Field, Relationship

from .category_model import Category  # noqa: F401  (注册到 SQLModel.metadata)


class Account(SQLModel, table=True):
    __tablename__ = "accounts"

    id: Optional[int] = Field(default=None, primary_key=True)
    deleted_at: Optional[date] = Field(default=None, index=True)  # NULL=正常, 有值=回收站

    # A 基础信息
    user_name: str = Field(index=True)
    department: str = Field(default="", index=True)
    plan_type: str = Field(default="")
    first_open_date: Optional[date] = Field(default=None)
    status: str = Field(default="可用", index=True)  # 可用/被封/待交付/已停用

    # B 交付与安装
    delivered: bool = Field(default=False)
    delivery_date: Optional[date] = Field(default=None)
    installed: bool = Field(default=False)
    installer: str = Field(default="")
    os_version: str = Field(default="")

    # C 服务器 / VPS
    server_order: str = Field(default="", index=True)
    vps_ip_masked: str = Field(default="")  # 39/71/123/187 脱敏格式
    vps_pure: bool = Field(default=False)
    vps_in_use: bool = Field(default=False)
    new_vps_address: str = Field(default="")

    # D 节点配置（存原文，前端展示时按需脱敏）
    verge_url: str = Field(default="")
    vlmess_url: str = Field(default="")

    # E 账号凭证
    cc_email: str = Field(default="", index=True)
    email_password_enc: str = Field(default="")  # base64 密文
    gpt_password_enc: str = Field(default="")    # base64 密文
    plan_amount: str = Field(default="")
    converted_to_codex: bool = Field(default=False)

    # F 订阅周期
    plan_start_date: Optional[date] = Field(default=None)
    plan_end_date: Optional[date] = Field(default=None)
    distributed: bool = Field(default=False)

    # H 第一批账号凭证（原 CSV 里"第一批账号分配"多合一字段，原样存）
    first_batch_alloc: str = Field(default="")

    # I 第 1/2/3 次账号交付与封号（来自原 CSV 宽表字段）
    # 第 1 次
    ban1_is_banned: bool = Field(default=False)
    ban1_date: Optional[date] = Field(default=None)
    ban1_voucher: str = Field(default="")  # 第一次账号交付凭证（图片路径）
    # 第 2 次
    ban2_delivered: str = Field(default="")  # 第二次账号交付（多合一文本）
    second_voucher: str = Field(default="")  # 第二次账号交付凭证（图片路径）
    ban2_is_banned: bool = Field(default=False)
    ban2_date: Optional[date] = Field(default=None)
    # 第 3 次
    ban3_delivered: str = Field(default="")  # 第三次账号交付（多合一文本）
    third_voucher: str = Field(default="")   # 第三次账号交付凭证（图片路径）
    ban3_is_banned: bool = Field(default=False)

    # J 备注
    notes: str = Field(default="")

    # G 封号历史（一对多）
    ban_history: List["BanHistory"] = Relationship(back_populates="account")


class BanHistory(SQLModel, table=True):
    __tablename__ = "ban_history"

    id: Optional[int] = Field(default=None, primary_key=True)
    account_id: int = Field(foreign_key="accounts.id", index=True)
    ban_sequence: int = Field(default=1)
    ban_date: Optional[date] = Field(default=None)
    ban_reason: str = Field(default="")
    replacement_date: Optional[date] = Field(default=None)
    replacement_voucher: str = Field(default="")
    status_after: str = Field(default="")

    account: Optional[Account] = Relationship(back_populates="ban_history")
