# -*- coding: utf-8 -*-
"""memory_store 单元测试"""
import os
import sys
import tempfile

import pytest

# 使用临时 DB 避免污染生产数据
TEST_DB = tempfile.NamedTemporaryFile(suffix=".db", delete=False).name

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 在导入 memory_store 前注入测试 DB 路径
import memory_store as ms  # noqa: E402

_orig_db = ms.MEMORY_DB_PATH
ms.MEMORY_DB_PATH = TEST_DB


def setup_module():
    """测试前清理可能存在的旧测试库"""
    if os.path.isfile(TEST_DB):
        os.remove(TEST_DB)


def teardown_module():
    """测试后清理"""
    if os.path.isfile(TEST_DB):
        os.remove(TEST_DB)
    ms.MEMORY_DB_PATH = _orig_db


def test_add_entry():
    rid = ms.add_entry("manual", "test content", title="单元测试文档")
    assert rid > 0


def test_list_recent():
    ms.add_entry("manual", "c2", title="T2")
    entries = ms.list_recent(limit=5)
    assert len(entries) >= 1
    assert "content" in entries[0]
    assert "id" in entries[0]


def test_search():
    ms.add_entry("manual", "直播分辨率 AB test 需求", title="直播PRD")
    results = ms.search("直播", limit=10)
    assert len(results) >= 1
    found = any("直播" in (e.get("content", "") + e.get("title", "")) for e in results)
    assert found


def test_delete_entry():
    rid = ms.add_entry("manual", "待删除", title="__delete_me__")
    assert ms.delete_entry(rid) is True
    assert ms.delete_entry(rid) is False
    results = ms.search("待删除")
    assert not any(e.get("id") == rid for e in results)


def test_get_recent_for_agent():
    ms.add_entry("quip_folder", "需求内容", source_id="abc123", title="需求A")
    s = ms.get_recent_for_agent(limit=2, demand_only=True)
    assert isinstance(s, str)
    assert "需求A" in s or len(s) == 0


def test_add_entry_upsert():
    rid1 = ms.add_entry("quip_single", "v1", source_id="tid1", title="T1")
    rid2 = ms.add_entry("quip_single", "v2", source_id="tid1", title="T1-upd")
    assert rid1 == rid2
    entries = ms.list_recent(limit=5)
    match = [e for e in entries if e.get("source_id") == "tid1"]
    assert len(match) == 1 and "v2" in (match[0].get("content") or "")


def test_get_all_demands_full_for_chat():
    ms.add_entry("quip_folder", "完整需求内容ABC", source_id="q1", title="需求Q1")
    s = ms.get_all_demands_full_for_chat(limit=5)
    assert isinstance(s, str)
    assert "完整需求内容ABC" in s
    assert "需求Q1" in s


def test_list_for_browse():
    ms.add_entry("quip_folder", "x", title="X")
    entries = ms.list_for_browse(limit=5)
    assert isinstance(entries, list)
    entries2 = ms.list_for_browse(source_type_filter="quip_folder", limit=5)
    assert all(e.get("source_type") == "quip_folder" for e in entries2)
