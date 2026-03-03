# -*- coding: utf-8 -*-
"""
业务逻辑层：四 Agent → 测试用例流水线
与 Streamlit UI 解耦，供 app_ui 调用。
支持：文件上传（.md + .xlsx）、粘贴文本两种输入方式。
"""
from __future__ import annotations

import os
from datetime import datetime
from typing import Any, TypedDict

from crew_test import (
    run_pipeline,
    _parse_markdown_tables,
    tables_to_text,
    export_tables_to_excel_bytes,
)


def _debug_save_parse_fail(raw_content: str) -> None:
    """解析失败时保存原始内容到 output/parse_fail_debug.txt，便于排查。"""
    try:
        base = os.path.dirname(os.path.abspath(__file__))
        out_dir = os.path.join(base, "output")
        os.makedirs(out_dir, exist_ok=True)
        debug_path = os.path.join(out_dir, "parse_fail_debug.txt")
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(debug_path, "a", encoding="utf-8") as f:
            f.write(f"\n\n=== 解析失败 {ts} ===\n\n")
            f.write((raw_content or "")[:8000])
            f.write("\n")
    except Exception:
        pass


TABLE_REPAIR_PROMPT = """以下内容应为测试用例的 Markdown 表格，但可能存在格式错误。请将其修正为合法的 Markdown 表格并直接输出，不要任何说明、问候或前后文字。

格式要求：
- 每行必须以 | 开头、以 | 结尾
- 表头固定为：| 序号 | 用例编号 | 主模块 | 子场景 | 用例概述 | 优先级 | 前置条件 | 测试步骤 | 预期结果 |
- 第二行应为分隔行：| --- | --- | --- | --- | --- | --- | --- | --- | --- |
- 之后为数据行

原始内容：
"""


def _repair_markdown_table_via_llm(
    raw_text: str,
    gemini_key: str,
    gemini_model: str,
) -> str:
    """解析失败时，调用 LLM 尝试修正 Markdown 表格格式。返回修正后的文本，失败返回空串。"""
    if not raw_text or not (gemini_key or "").strip():
        return ""
    try:
        from langchain_google_genai import ChatGoogleGenerativeAI
        from crew_test import _resolve_gemini_model

        os.environ["GEMINI_API_KEY"] = gemini_key or os.environ.get("GEMINI_API_KEY", "")
        # 通过统一的模型映射函数规避已下线/弃用模型（如 gemini-2.0-flash）
        model = _resolve_gemini_model(
            gemini_model or os.environ.get("GEMINI_MODEL", "gemini-2.5-flash-lite")
        )
        if not os.environ.get("GEMINI_API_KEY"):
            return ""
        llm = ChatGoogleGenerativeAI(
            model=model,
            google_api_key=gemini_key,
            temperature=0.1,
        )
        prompt = TABLE_REPAIR_PROMPT + (raw_text or "")[:6000]
        resp = llm.invoke(prompt)
        out = (getattr(resp, "content", None) or str(resp) or "").strip()
        return out if out else ""
    except Exception:
        return ""


def _log_pipeline_result(
    tables_count: int,
    has_excel: bool,
    cases_md_len: int,
    result_str_len: int,
    step_outputs: list[dict],
    raw_for_debug: str,
) -> None:
    """每次流水线结束写入日志；解析失败时额外保存原始内容。便于排查「未生成日志」或「未解析到表格」问题。"""
    try:
        base = os.path.dirname(os.path.abspath(__file__))
        out_dir = os.path.join(base, "output")
        os.makedirs(out_dir, exist_ok=True)
        log_path = os.path.join(out_dir, "parse_fail_log.txt")
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        task_ids = [s.get("task", "") for s in step_outputs]
        task3_len = 0
        for s in step_outputs:
            if s.get("task") == "task3":
                task3_len = len(str(s.get("content", "")))
                break
        status = "解析成功" if tables_count else "解析失败"
        raw_preview = repr((raw_for_debug or "")[:200])
        lines = [
            f"[{ts}] {status} | tables={tables_count} excel={has_excel}",
            f"  日志路径: {os.path.abspath(log_path)}",
            f"  step_outputs: {task_ids}",
            f"  cases_md_len={cases_md_len} task3_len={task3_len} result_str_len={result_str_len}",
            f"  raw_preview: {raw_preview}",
            "",
        ]
        with open(log_path, "a", encoding="utf-8") as f:
            f.write("\n".join(lines))
        # 解析失败时额外保存完整原始内容
        if tables_count == 0 and raw_for_debug:
            _debug_save_parse_fail(raw_for_debug)
    except Exception as e:
        # 写入失败时至少输出到 stderr，便于在终端/系统日志中看到
        import sys
        print(f"[pipeline] 日志写入失败: {e}", file=sys.stderr)
class UploadToCasesResult(TypedDict):
    ok: bool
    error: str | None
    understanding: str
    issues: str
    cases_md: str
    excel_bytes: bytes | None


def run_upload_to_cases(
    demand_md: str,
    existing_cases: str,
    gemini_key: str,
    gemini_model: str,
    project_context: str = "",
) -> UploadToCasesResult:
    """文件上传模式：基于 .md 需求 + .xlsx 既有用例，跑四 Agent 流水线。
    返回理解内容（task2）、问题点（task1）、新用例表（task3）、Excel 二进制。
    仅支持 Excel 下载，不落盘、不导出 Sheets。"""
    from crew_test import get_project_context_for_agent

    os.environ["GEMINI_API_KEY"] = gemini_key or os.environ.get("GEMINI_API_KEY", "")
    os.environ["GEMINI_MODEL"] = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash-lite")
    from crew_test import _resolve_gemini_model
    os.environ["GEMINI_MODEL"] = _resolve_gemini_model(gemini_model or os.environ.get("GEMINI_MODEL", ""))

    if not os.environ.get("GEMINI_API_KEY"):
        return {
            "ok": False,
            "error": "未配置 Gemini API Key",
            "understanding": "",
            "issues": "",
            "cases_md": "",
            "excel_bytes": None,
        }

    demand = (demand_md or "").strip()
    if not demand:
        return {
            "ok": False,
            "error": "需求文档不能为空，请至少上传 1 个 .md 文件",
            "understanding": "",
            "issues": "",
            "cases_md": "",
            "excel_bytes": None,
        }

    base_ctx = (project_context or "").strip() or get_project_context_for_agent()
    if (existing_cases or "").strip():
        base_ctx = (base_ctx + "\n\n【既有测试用例】\n\n" + existing_cases.strip()).strip()

    try:
        out = run_pipeline(
            demand,
            output_dir="output",
            export_excel=False,
            export_sheets=False,
            project_context=base_ctx,
            return_details=True,
        )
    except Exception as e:
        return {
            "ok": False,
            "error": str(e),
            "understanding": "",
            "issues": "",
            "cases_md": "",
            "excel_bytes": None,
        }

    if not isinstance(out, dict):
        return {
            "ok": False,
            "error": "流水线返回格式异常",
            "understanding": "",
            "issues": "",
            "cases_md": "",
            "excel_bytes": None,
        }

    step_outputs = out.get("step_outputs") or []
    understanding = ""
    issues = ""
    cases_md = ""

    for s in step_outputs:
        tid = s.get("task") or ""
        content = str(s.get("content") or "").strip()
        if tid == "task1":
            issues = content
        elif tid == "task2":
            understanding = content
        elif tid == "task3":
            cases_md = content

    # 优先从 task3（用例表）解析；若无则从 result_str（task4 输出）尝试
    result_str = (out.get("result_str") or "").strip()
    tables = _parse_markdown_tables(cases_md) if (cases_md or "").strip() else []
    if not tables and result_str:
        tables = _parse_markdown_tables(result_str)

    # 解析失败时：LLM 修表兜底
    raw_for_repair = cases_md or result_str
    if not tables and raw_for_repair and gemini_key:
        repaired = _repair_markdown_table_via_llm(
            raw_for_repair,
            gemini_key=gemini_key,
            gemini_model=gemini_model or "",
        )
        if repaired:
            tables = _parse_markdown_tables(repaired)
            if tables:
                cases_md = repaired

    excel_bytes = export_tables_to_excel_bytes(tables) if tables else None

    # 解析失败或需排查时：保存原始内容 + 写入日志（放宽条件，覆盖 cases_md/result_str 全空等情况）
    _log_pipeline_result(
        tables_count=len(tables) if tables else 0,
        has_excel=excel_bytes is not None,
        cases_md_len=len(cases_md or ""),
        result_str_len=len(result_str or ""),
        step_outputs=out.get("step_outputs") or [],
        raw_for_debug=cases_md or result_str,
    )

    return {
        "ok": True,
        "error": None,
        "understanding": understanding,
        "issues": issues,
        "cases_md": cases_md,
        "excel_bytes": excel_bytes,
    }
