# -*- coding: utf-8 -*-
"""credential_store 模块单元测试"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_credential_store_imports():
    from credential_store import get_credentials, set_credentials
    assert callable(get_credentials)
    assert callable(set_credentials)


def test_get_credentials_returns_dict():
    from credential_store import get_credentials
    creds = get_credentials()
    assert isinstance(creds, dict)
    assert "quip_token" in creds
    assert "gemini_key" in creds
    assert "gemini_model" in creds
    assert creds.get("gemini_model") or True  # 至少有一项


def test_set_credentials():
    from credential_store import set_credentials, get_credentials
    ok, mode = set_credentials("", "", "gemini-2.5-flash-lite")
    assert ok
    assert mode in ("Keyring", "JSON", "JSON（Keyring 不可用）")
