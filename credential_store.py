# -*- coding: utf-8 -*-
"""
凭证存储：优先使用 Keyring，失败时降级到 config/defaults.json
- Keyring：系统密钥环（macOS Keychain、Windows 凭据管理器等）
- 降级：无 UI 环境或 Keyring 不可用时回退 JSON
"""
import json
import os
CONFIG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config")
DEFAULTS_PATH = os.path.join(CONFIG_DIR, "defaults.json")
SERVICE_NAME = "test_case_pipeline"
KEYS = ("quip_token", "gemini_key", "gemini_model")

_keyring_available: bool | None = None


def _keyring_ok() -> bool:
    """检测 Keyring 是否可用。"""
    global _keyring_available
    if _keyring_available is not None:
        return _keyring_available
    try:
        import keyring
        # 简单探测：能否 get（失败正常）
        keyring.get_password(SERVICE_NAME, "_probe")
        _keyring_available = True
    except Exception:
        _keyring_available = False
    return _keyring_available


def _load_from_keyring() -> dict[str, str]:
    """从 Keyring 读取凭证。"""
    import keyring
    out: dict[str, str] = {}
    for k in KEYS:
        v = keyring.get_password(SERVICE_NAME, k)
        if v is not None:
            out[k] = v
    return out


def _save_to_keyring(data: dict[str, str]) -> None:
    """写入 Keyring。"""
    import keyring
    for k in KEYS:
        v = data.get(k)
        if v is not None and str(v).strip():
            keyring.set_password(SERVICE_NAME, k, str(v).strip())


def _load_from_json() -> dict[str, str]:
    """从 defaults.json 读取。"""
    out: dict[str, str] = {}
    if os.path.isfile(DEFAULTS_PATH):
        try:
            with open(DEFAULTS_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
                for k in KEYS:
                    if k in data and data[k]:
                        out[k] = str(data[k])
        except Exception:
            pass
    return out


def _save_to_json(data: dict[str, str]) -> None:
    """写入 defaults.json。"""
    os.makedirs(CONFIG_DIR, exist_ok=True)
    payload = {k: data.get(k, "") for k in KEYS}
    with open(DEFAULTS_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    try:
        os.chmod(DEFAULTS_PATH, 0o600)
    except OSError:
        pass


def get_credentials() -> dict[str, str]:
    """
    读取凭证：环境变量优先，其次 Keyring，最后 JSON。
    返回 {quip_token, gemini_key, gemini_model}，缺省为 ""。
    若 Keyring 可用且为空、defaults.json 有数据，则自动迁移。
    """
    out: dict[str, str] = {
        "quip_token": os.getenv("QUIP_ACCESS_TOKEN", ""),
        "gemini_key": os.getenv("GEMINI_API_KEY", ""),
        "gemini_model": os.getenv("GEMINI_MODEL", ""),
    }
    if _keyring_ok():
        migrate_json_to_keyring()
    store: dict[str, str] = {}
    if _keyring_ok():
        try:
            store = _load_from_keyring()
        except Exception:
            store = _load_from_json()
    else:
        store = _load_from_json()
    for k in KEYS:
        if not out.get(k) and store.get(k):
            out[k] = store[k]
    if not out.get("gemini_model"):
        out["gemini_model"] = "gemini-2.5-flash-lite"
    return out


def set_credentials(quip_token: str, gemini_key: str, gemini_model: str = "") -> tuple[bool, str]:
    """
    保存凭证。优先 Keyring，失败则 JSON。
    返回 (成功, 存储方式说明)
    """
    data: dict[str, str] = {
        "quip_token": (quip_token or "").strip(),
        "gemini_key": (gemini_key or "").strip(),
        "gemini_model": (gemini_model or "gemini-2.5-flash-lite").strip(),
    }
    if _keyring_ok():
        try:
            _save_to_keyring(data)
            return True, "Keyring"
        except Exception:
            _save_to_json(data)
            return True, "JSON（Keyring 不可用）"
    _save_to_json(data)
    return True, "JSON"


def migrate_json_to_keyring() -> bool:
    """若存在 defaults.json 且 Keyring 可用且 Keyring 为空，则迁移。"""
    if not _keyring_ok():
        return False
    stored = _load_from_keyring()
    if any(stored.get(k) for k in KEYS):
        return False  # Keyring 已有数据，不覆盖
    jdata = _load_from_json()
    if not any(jdata.get(k) for k in KEYS):
        return False
    try:
        _save_to_keyring(jdata)
        return True
    except Exception:
        return False


def get_storage_mode() -> str:
    """返回当前实际使用的存储方式，用于 UI 提示。"""
    if _keyring_ok():
        s = _load_from_keyring()
        if any(s.get(k) for k in KEYS):
            return "Keyring"
    return "JSON"
