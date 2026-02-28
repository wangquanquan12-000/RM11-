# -*- coding: utf-8 -*-
"""文档过滤 is_product_requirement_doc 单元测试"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from crew_test import is_product_requirement_doc


def test_exclude_test_case_by_title():
    keep, reason = is_product_requirement_doc("测试用例 v1", "")
    assert keep is False
    assert "排除" in reason or len(reason) > 0


def test_exclude_ui_walkthrough():
    keep, _ = is_product_requirement_doc("UI走查清单", "")
    assert keep is False


def test_exclude_progress_report():
    keep, _ = is_product_requirement_doc("进度周报 2024", "")
    assert keep is False


def test_include_prd():
    keep, reason = is_product_requirement_doc("需求：直播分辨率", "功能说明：支持多档位")
    assert keep is True
    assert reason == ""


def test_exclude_by_content():
    keep, _ = is_product_requirement_doc("某文档", "用例ID 预期结果 操作步骤 表格")
    assert keep is False
