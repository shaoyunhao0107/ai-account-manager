"""会话鉴权：单一管理员密码"""
import os
from fastapi import Request, HTTPException, status
from itsdangerous import URLSafeSerializer, BadSignature

ADMIN_PASSWORD = os.environ.get("AAM_ADMIN_PASSWORD", "admin123")
SESSION_SECRET = os.environ.get("AAM_SESSION_SECRET", "dev-secret-change-in-prod")

_serializer = URLSafeSerializer(SESSION_SECRET, salt="aam-session")


def make_session_cookie(user: str = "admin") -> str:
    return _serializer.dumps({"u": user})


def verify_session_cookie(cookie_value: str) -> bool:
    try:
        _serializer.loads(cookie_value)
        return True
    except BadSignature:
        return False


def check_login(password: str) -> bool:
    return password == ADMIN_PASSWORD


def require_auth(request: Request):
    """FastAPI 依赖：未登录则 401"""
    cookie = request.cookies.get("aam_session")
    if not cookie or not verify_session_cookie(cookie):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="请先登录",
            headers={"Location": "/login"},
        )
