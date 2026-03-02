# -*- coding: utf-8 -*-
"""
登录、注册及验证码逻辑
- 用户数据存于 config/users.db（SQLite）
- 验证码支持万能码（配置文件中的 master_captcha），输入即通过
- 登录态保持 7 天：签名 Token 存于 Cookie，无需 DB 查表
"""
import hashlib
import hmac
import os
import random
import sqlite3
import string
import time
CONFIG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config")
USERS_DB_PATH = os.path.join(CONFIG_DIR, "users.db")
AUTH_CONFIG_PATH = os.path.join(CONFIG_DIR, "auth_config.yaml")
SESSION_DAYS = 7
COOKIE_NAME = "auth_session"


def _get_session_secret() -> str:
    """从配置读取会话签名密钥，用于 7 天免登。"""
    try:
        import yaml
        if os.path.isfile(AUTH_CONFIG_PATH):
            with open(AUTH_CONFIG_PATH, "r", encoding="utf-8") as f:
                cfg = yaml.safe_load(f) or {}
                s = str(cfg.get("session_cookie_secret", "")).strip()
                if s:
                    return s
    except Exception:
        pass
    return os.environ.get("AUTH_SESSION_SECRET", "test_case_pipeline_session_v1")


def _get_master_captcha() -> str:
    """从配置读取万能验证码，默认 ADMIN888"""
    try:
        import yaml
        if os.path.isfile(AUTH_CONFIG_PATH):
            with open(AUTH_CONFIG_PATH, "r", encoding="utf-8") as f:
                cfg = yaml.safe_load(f) or {}
                return str(cfg.get("master_captcha", "ADMIN888")).strip() or "ADMIN888"
    except Exception:
        pass
    return "ADMIN888"


def _get_conn():
    os.makedirs(CONFIG_DIR, exist_ok=True)
    conn = sqlite3.connect(USERS_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _ensure_users_table(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_users_username ON users(username)")
    conn.commit()


def _hash_password(password: str) -> str:
    """使用 SHA-256 加盐哈希密码（内部使用，非高安全场景）"""
    salt = "test_case_pipeline_v1"
    return hashlib.sha256(f"{salt}{password}".encode()).hexdigest()


def register_user(username: str, password: str) -> tuple[bool, str]:
    """注册新用户。返回 (成功, 消息)"""
    username = (username or "").strip()
    password = (password or "").strip()
    if not username or len(username) < 2:
        return False, "用户名至少 2 个字符"
    if not password or len(password) < 6:
        return False, "密码至少 6 个字符"
    if not all(c.isalnum() or c in "_-" for c in username):
        return False, "用户名仅允许字母、数字、下划线、连字符"
    conn = _get_conn()
    _ensure_users_table(conn)
    try:
        pw_hash = _hash_password(password)
        conn.execute(
            "INSERT INTO users (username, password_hash, created_at) VALUES (?, ?, datetime('now'))",
            (username, pw_hash),
        )
        conn.commit()
        return True, "注册成功"
    except sqlite3.IntegrityError:
        return False, "用户名已存在"
    except Exception as e:
        return False, f"注册失败: {str(e)}"
    finally:
        conn.close()


def verify_user(username: str, password: str) -> tuple[bool, str]:
    """验证用户名密码。返回 (成功, 消息)"""
    username = (username or "").strip()
    password = (password or "").strip()
    if not username or not password:
        return False, "请输入用户名和密码"
    conn = _get_conn()
    _ensure_users_table(conn)
    try:
        row = conn.execute(
            "SELECT password_hash FROM users WHERE username = ?",
            (username,),
        ).fetchone()
        if not row:
            return False, "用户名或密码错误"
        pw_hash = _hash_password(password)
        if pw_hash != row["password_hash"]:
            return False, "用户名或密码错误"
        return True, username
    finally:
        conn.close()


def verify_captcha(user_input: str, expected: str) -> bool:
    """
    验证验证码。
    - 若 user_input 等于万能码（master_captcha），直接通过
    - 否则需与 expected 一致（忽略大小写与首尾空格）
    """
    user_input = (user_input or "").strip()
    expected = (expected or "").strip()
    master = _get_master_captcha()
    if user_input.lower() == master.lower():
        return True
    return user_input.lower() == expected.lower()


def generate_captcha(length: int = 4) -> str:
    """生成随机数字验证码"""
    return "".join(random.choices(string.digits, k=length))


def create_session_token(username: str) -> str:
    """
    生成 7 天有效的签名 Token，用于 Cookie 持久化登录。
    格式: base64(username|expires_ts|hmac)
    """
    import base64
    secret = _get_session_secret().encode()
    expires_ts = int(time.time()) + SESSION_DAYS * 86400
    payload = f"{username}|{expires_ts}"
    sig = hmac.new(secret, payload.encode(), "sha256").hexdigest()
    raw = f"{payload}|{sig}"
    return base64.urlsafe_b64encode(raw.encode()).decode().rstrip("=")


def validate_session_token(token: str) -> str | None:
    """
    验证 Token，若有效返回用户名，否则返回 None。
    """
    if not token or not token.strip():
        return None
    import base64
    try:
        raw = token.strip()
        padding = 4 - len(raw) % 4
        if padding != 4:
            raw += "=" * padding
        decoded = base64.urlsafe_b64decode(raw).decode()
        parts = decoded.rsplit("|", 1)
        if len(parts) != 2:
            return None
        payload, sig = parts
        sub = payload.rsplit("|", 1)
        if len(sub) != 2:
            return None
        username, expires_str = sub
        expires_ts = int(expires_str)
        if expires_ts < int(time.time()):
            return None
        secret = _get_session_secret().encode()
        expected = hmac.new(secret, payload.encode(), "sha256").hexdigest()
        if not hmac.compare_digest(expected, sig):
            return None
        return username.strip()
    except Exception:
        return None
