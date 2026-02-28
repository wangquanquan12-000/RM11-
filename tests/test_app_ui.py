# -*- coding: utf-8 -*-
"""app_ui 导入与关键逻辑单元测试"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_app_ui_imports():
    from app_ui import (
        _load_defaults,
        _load_stable_quip_batch,
        _get_text,
        _load_ui_texts,
    )
    from app_ui import load_demands_from_quip_folder, delete_entry
    from memory_store import add_entry, search, list_recent
    assert callable(_load_defaults)
    assert callable(_load_ui_texts)


def test_stable_batch_types():
    from app_ui import _load_stable_quip_batch
    s = _load_stable_quip_batch()
    assert isinstance(int(s["batch_size"]), int)
    assert isinstance(int(s["batch_pause"]), int)


def test_get_text():
    from app_ui import _get_text
    data = {"a": {"b": "val"}}
    assert _get_text(data, "a.b") == "val"
    assert _get_text(data, "a.c") == ""
    assert _get_text({}, "x") == ""
