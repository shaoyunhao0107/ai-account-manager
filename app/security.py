"""加密模块：基于主密码派生 Fernet 密钥"""
import base64
import hashlib
import os

from cryptography.fernet import Fernet, InvalidToken

_master_password = os.environ.get("AAM_MASTER_PASSWORD", "change-me-please")


def _derive_key(password: str) -> bytes:
    """PBKDF2 派生 Fernet 兼容的 32 字节 key（base64 编码）"""
    # 固定 salt — 同主密码产生同密钥，方便换机迁移；
    # 真正多机部署应改用每机随机 salt 存在 .env，这里为了"便携"用固定值。
    salt = b"ai-account-manager-static-salt-v1"
    raw = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, iterations=200_000, dklen=32)
    return base64.urlsafe_b64encode(raw)


def _get_fernet() -> Fernet:
    return Fernet(_derive_key(_master_password))


def encrypt_field(plaintext: str) -> str:
    """加密字符串，返回 base64 密文（可入库）。空串原样返回。"""
    if not plaintext:
        return ""
    token = _get_fernet().encrypt(plaintext.encode("utf-8"))
    return token.decode("ascii")


def decrypt_field(ciphertext: str) -> str:
    """解密 base64 密文。空串原样返回。失败返回 '[解密失败]'。"""
    if not ciphertext:
        return ""
    try:
        return _get_fernet().decrypt(ciphertext.encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError):
        return "[解密失败]"
