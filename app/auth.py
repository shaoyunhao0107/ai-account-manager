"""会话鉴权：用户名 + 密码"""
import os
import json
from fastapi import Request, HTTPException, status
from itsdangerous import URLSafeSerializer, BadSignature

SESSION_SECRET = os.environ.get("AAM_SESSION_SECRET", "dev-secret-change-in-prod")

# 用户列表：从环境变量 AAM_USERS 加载（JSON 格式），或用默认
# 格式：[{"username":"admin","password":"admin123","name":"管理员"}]
DEFAULT_USERS = json.dumps([{"username": "admin", "password": "admin123", "name": "管理员"}])
_users_raw = os.environ.get("AAM_USERS", DEFAULT_USERS)
try:
    USERS = json.loads(_users_raw)
except (json.JSONDecodeError, TypeError):
    USERS = [{"username": "admin", "password": "admin123", "name": "管理员"}]

_serializer = URLSafeSerializer(SESSION_SECRET, salt="aam-session")


def make_session_cookie(user: str = "admin") -> str:
    return _serializer.dumps({"u": user})


def verify_session_cookie(cookie_value: str) -> bool:
    try:
        _serializer.loads(cookie_value)
        return True
    except BadSignature:
        return False


def check_login(username: str, password: str) -> bool:
    """检查用户名+密码是否匹配"""
    for u in USERS:
        if u.get("username") == username and u.get("password") == password:
            return True
    return False


def get_user_name(username: str) -> str:
    """获取用户显示名"""
    for u in USERS:
        if u.get("username") == username:
            return u.get("name", username)
    return username


def require_auth(request: Request):
    """FastAPI 依赖：未登录则 401"""
    cookie = request.cookies.get("aam_session")
    if not cookie or not verify_session_cookie(cookie):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="请先登录",
            headers={"Location": "/login"},
        )
