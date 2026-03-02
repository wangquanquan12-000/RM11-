# -*- coding: utf-8 -*-
"""auth 模块单元测试"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_auth_imports():
    from auth import verify_user, register_user, verify_captcha, generate_captcha
    from auth import create_session_token, validate_session_token
    assert callable(verify_user)
    assert callable(register_user)
    assert callable(verify_captcha)
    assert callable(generate_captcha)
    assert callable(create_session_token)
    assert callable(validate_session_token)


def test_register_and_verify():
    """临时 DB 测试注册与登录"""
    import auth
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.unlink(path)
    old_path = auth.USERS_DB_PATH
    try:
        auth.USERS_DB_PATH = path
        ok, msg = auth.register_user("testuser_auth_xyz", "password123")
        assert ok, msg
        ok2, msg2 = auth.verify_user("testuser_auth_xyz", "password123")
        assert ok2
        assert msg2 == "testuser_auth_xyz"
        ok3, _ = auth.verify_user("testuser_auth_xyz", "wrong")
        assert not ok3
    finally:
        auth.USERS_DB_PATH = old_path
        if os.path.isfile(path):
            os.unlink(path)


def test_captcha_master():
    """万能验证码通过"""
    from auth import verify_captcha, _get_master_captcha
    master = _get_master_captcha()
    assert verify_captcha(master, "任意") is True
    assert verify_captcha(master.upper(), "任意") is True


def test_captcha_normal():
    """正常验证码校验"""
    from auth import verify_captcha
    assert verify_captcha("1234", "1234") is True
    assert verify_captcha("1234", "1234") is True
    assert verify_captcha(" 1234 ", "1234") is True
    assert verify_captcha("wrong", "1234") is False


def test_generate_captcha():
    from auth import generate_captcha
    c = generate_captcha(4)
    assert len(c) == 4
    assert c.isdigit()


def test_session_token_7days():
    """7 天免登 Token 生成与校验"""
    from auth import create_session_token, validate_session_token
    token = create_session_token("testuser")
    assert token
    username = validate_session_token(token)
    assert username == "testuser"
    assert validate_session_token("") is None
    assert validate_session_token("invalid") is None
