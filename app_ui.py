# -*- coding: utf-8 -*-
"""
可视化界面：Quip 文档链接 → 四 Agent 流水线 → 表格链接
文案可在 config/ui_texts.yaml 中编辑，无需改代码。
"""
import os
import sys

import streamlit as st

# 将项目根目录加入 path，以便导入 crew_test
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

UI_TEXTS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config", "ui_texts.yaml")

from crew_test import (
    AGENTS_CONFIG_PATH,
    PROJECT_MEMORY_PATH,
    _parse_markdown_tables,
    chat_with_document_agent,
    get_project_context_for_agent,
    is_product_requirement_doc,
    load_agents_config,
    load_demand_from_quip,
    load_demands_from_quip_folder,
    parse_test_cases_file,
    run_pipeline,
    tables_to_text,
    update_project_memory,
)
from memory_store import TEST_CASES_SOURCE_TYPE, add_entry, delete_entry, get_entry_content, list_recent, search

CONFIG_DIR = os.path.dirname(AGENTS_CONFIG_PATH)
DEFAULTS_PATH = os.path.join(CONFIG_DIR, "defaults.json")
STABLE_QUIP_BATCH_PATH = os.path.join(CONFIG_DIR, "stable_quip_batch.json")
OUTPUT_DIR = "output"


def _load_stable_quip_batch():
    """读取上次保存的稳定拉取参数。"""
    import json
    out = {"batch_size": 10, "batch_pause": 60}
    if os.path.isfile(STABLE_QUIP_BATCH_PATH):
        try:
            with open(STABLE_QUIP_BATCH_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
                out["batch_size"] = data.get("batch_size", 10)
                out["batch_pause"] = data.get("batch_pause", 60)
        except Exception:
            pass
    return out


def _save_stable_quip_batch(batch_size: int, batch_pause: float):
    """保存稳定拉取参数，供下次使用。"""
    import json
    os.makedirs(CONFIG_DIR, exist_ok=True)
    with open(STABLE_QUIP_BATCH_PATH, "w", encoding="utf-8") as f:
        json.dump({"batch_size": batch_size, "batch_pause": batch_pause}, f, ensure_ascii=False, indent=2)


GEMINI_MODELS = [
    ("gemini-1.5-flash", "1.5 Flash（免费实验推荐）"),
    ("gemini-1.5-pro", "1.5 Pro（免费，质量高限额低）"),
    ("gemini-2.5-flash-lite", "2.5 Flash-Lite（免费额度较高）"),
    ("gemini-2.5-flash", "2.5 Flash（付费/免费皆可）"),
]


def _load_defaults():
    """从环境变量或 config/defaults.json 读取默认 Token / Key / 模型。"""
    import json
    out = {"quip_token": "", "gemini_key": "", "gemini_model": "gemini-2.5-flash-lite"}
    out["quip_token"] = os.getenv("QUIP_ACCESS_TOKEN", "")
    out["gemini_key"] = os.getenv("GEMINI_API_KEY", "")
    out["gemini_model"] = os.getenv("GEMINI_MODEL", "")
    if os.path.isfile(DEFAULTS_PATH):
        try:
            with open(DEFAULTS_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
                out["quip_token"] = out["quip_token"] or data.get("quip_token", "")
                out["gemini_key"] = out["gemini_key"] or data.get("gemini_key", "")
                out["gemini_model"] = out["gemini_model"] or data.get("gemini_model", "gemini-2.5-flash-lite")
            try:
                os.chmod(DEFAULTS_PATH, 0o600)  # 确保已存在文件也限制为仅当前用户可读写
            except OSError:
                pass
        except Exception:
            pass
    if not out["gemini_model"]:
        out["gemini_model"] = "gemini-2.5-flash-lite"
    return out


def _save_defaults(quip_token: str, gemini_key: str, gemini_model: str = ""):
    """将默认 Token / Key / 模型 写入 config/defaults.json（本地仅自己使用）。"""
    import json
    os.makedirs(CONFIG_DIR, exist_ok=True)
    payload = {"quip_token": quip_token, "gemini_key": gemini_key}
    if gemini_model:
        payload["gemini_model"] = gemini_model
    with open(DEFAULTS_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    try:
        os.chmod(DEFAULTS_PATH, 0o600)  # 仅当前用户可读写，降低泄露风险
    except OSError:
        pass


def _load_ui_texts():
    """从 config/ui_texts.yaml 加载文案，便于编辑。"""
    try:
        import yaml
        if os.path.isfile(UI_TEXTS_PATH):
            with open(UI_TEXTS_PATH, "r", encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
    except Exception:
        pass
    return {}


def _get_text(data: dict, path: str, default: str = "") -> str:
    """从嵌套 dict 取文案，如 app.title。"""
    keys = path.split(".")
    for k in keys:
        if not isinstance(data, dict):
            return default
        data = data.get(k, {})
    return data if isinstance(data, str) else default


def main():
    T = _load_ui_texts()
    page_title = _get_text(T, "app.page_title") or "需求 → 测试用例流水线"
    app_title = _get_text(T, "app.title") or page_title
    st.set_page_config(page_title=page_title, layout="wide", initial_sidebar_state="collapsed")
    st.markdown("""
    <style>
    /* 布局与层次 */
    .main .block-container { padding-top: 1.2rem; padding-bottom: 2.5rem; max-width: 920px; }
    h1 {
        font-size: 1.45rem !important; font-weight: 600 !important;
        color: #0f172a !important; margin-bottom: 0.6rem !important;
        letter-spacing: -0.02em; line-height: 1.3;
    }
    h2 {
        font-size: 1rem !important; font-weight: 600 !important;
        color: #334155 !important; margin-top: 1.25rem !important; margin-bottom: 0.5rem !important;
    }
    h3 {
        font-size: 0.95rem !important; font-weight: 500 !important;
        color: #64748b !important; margin-top: 0.75rem !important; margin-bottom: 0.4rem !important;
    }
    /* 步骤标题与区块间距 */
    .step-label { font-size: 0.8rem; font-weight: 600; color: #0d9488; text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 0.35rem; }
    .step-label.step-3, .step-label.step-4 { margin-top: 1.25rem; }
    div[data-testid="stExpander"] { margin-top: 0.5rem; margin-bottom: 0.25rem; }
    .step-label + .step-label { margin-top: 1rem; }
    .run-section { margin-top: 1rem; }
    .export-row { margin-bottom: 0.5rem; }
    .stCheckbox { margin-bottom: 0.25rem; }
    .stTabs [data-baseweb="tab-list"] {
        gap: 0.25rem; margin-bottom: 1rem;
        border-bottom: 1px solid #e2e8f0;
    }
    .stTabs [data-baseweb="tab"] {
        padding: 0.5rem 1rem; font-size: 0.9rem; font-weight: 500;
    }
    .stTabs [aria-selected="true"] {
        color: #0d9488; border-bottom: 2px solid #0d9488; margin-bottom: -1px;
    }
    div[data-testid="stExpander"] {
        border: 1px solid #e2e8f0; border-radius: 8px;
        margin-bottom: 0.5rem; background: #fafafa;
    }
    div[data-testid="stExpander"] > div:first-child { border-radius: 8px; }
    .stButton > button {
        border-radius: 8px; font-weight: 500;
        transition: opacity 0.15s;
    }
    .stButton > button:hover { opacity: 0.9; }
    /* 主按钮更突出 */
    .main div[data-testid="column"] + div[data-testid="column"] .stButton > button[kind="primary"],
    .main .stButton > button[kind="primary"] { font-weight: 600; }
    [data-testid="stMetricValue"] { font-weight: 600; }
    .stTextInput > div > div { border-radius: 8px; }
    .stSuccess, .stInfo, .stWarning, .stError {
        border-radius: 8px; padding: 0.75rem 1rem;
    }
    p { line-height: 1.6; }
    div[data-testid="stExpander"] summary { font-size: 0.9rem; padding: 0.6rem 0.75rem; }
    .stSelectbox > div { border-radius: 8px; }
    [data-testid="stAlert"] { border-radius: 8px; }
    hr { margin: 1.25rem 0; border-color: #e2e8f0; opacity: 0.8; }
    #MainMenu { visibility: hidden; }
    footer { visibility: hidden; }
    header { visibility: hidden; }
    </style>
    """, unsafe_allow_html=True)
    st.title(app_title)
    defaults = _load_defaults()
    tab_run, tab_agents, tab_memory, tab_chat = st.tabs([
        _get_text(T, "tabs.run") or "生成用例",
        _get_text(T, "tabs.agents") or "编辑 Agent",
        _get_text(T, "tabs.memory") or "项目记忆",
        _get_text(T, "tabs.chat") or "文档问答",
    ])

    # ---------- 运行流水线 ----------
    with tab_run:
        st.caption(_get_text(T, "run_tab.page_caption") or "从 Quip 需求文档生成测试用例，支持导出 Excel / Quip / Google 表格。")
        st.markdown("<div style='margin-bottom:0.5rem'></div>", unsafe_allow_html=True)

        st.markdown('<p class="step-label">① 需求文档</p>', unsafe_allow_html=True)
        quip_url = st.text_input(
            _get_text(T, "run_tab.quip_url_label") or "需求文档链接",
            placeholder=_get_text(T, "run_tab.quip_url_placeholder") or "粘贴 Quip 文档链接或 thread_id",
            key="run_quip_url",
            label_visibility="collapsed",
        )
        if not quip_url or not quip_url.strip():
            st.caption(_get_text(T, "run_tab.quip_url_hint") or "示例：https://quip.com/xxx 或 12 位 thread_id")

        _has_saved = bool(defaults.get("quip_token") and defaults.get("gemini_key"))
        _exp_label = "② 账号与模型（已保存 ✓）" if _has_saved else "② 账号与模型"
        with st.expander(_exp_label, expanded=not _has_saved):
            col1, col2 = st.columns(2)
            with col1:
                quip_token = st.text_input(
                    _get_text(T, "run_tab.quip_token_label") or "Quip Access Token",
                    value=defaults["quip_token"], type="password",
                    help=_get_text(T, "run_tab.quip_token_help") or "从 Quip 获取，用于拉取需求文档",
                    key="run_quip_token",
                )
            with col2:
                gemini_key = st.text_input(
                    _get_text(T, "run_tab.gemini_key_label") or "Gemini API Key",
                    value=defaults["gemini_key"], type="password",
                    help=_get_text(T, "run_tab.gemini_key_help") or "用于驱动四个 Agent 生成用例",
                    key="run_gemini_key",
                )
            _model_opts = [m[0] for m in GEMINI_MODELS]
            _model_idx = next((i for i, (k, _) in enumerate(GEMINI_MODELS) if k == (defaults.get("gemini_model") or "gemini-2.5-flash-lite")), 0)
            _model_col, _quota_col = st.columns([3, 1])
            with _model_col:
                gemini_model = st.selectbox(
                    _get_text(T, "run_tab.gemini_model_label") or "Gemini 模型",
                    options=_model_opts,
                    index=_model_idx,
                    format_func=lambda x: dict(GEMINI_MODELS).get(x, x),
                    help=_get_text(T, "run_tab.gemini_model_help") or "免费推荐：2.5 Flash-Lite；高质量：2.5 Flash。",
                    key="run_gemini_model",
                )
            with _quota_col:
                _quota_url = _get_text(T, "run_tab.gemini_quota_url") or "https://aistudio.google.com/rate-limit"
                st.link_button(
                    _get_text(T, "run_tab.gemini_quota_btn") or "查看剩余额度",
                    _quota_url,
                    help=_get_text(T, "run_tab.gemini_quota_help") or "在 Google AI Studio 查看用量与限额（新开页）",
                )
            if st.button(_get_text(T, "run_tab.save_defaults_btn") or "保存到本地（下次无需再填）", key="run_save_defaults", help=_get_text(T, "run_tab.save_defaults_help") or "仅限本机；共享电脑建议用环境变量"):
                _save_defaults(quip_token or defaults["quip_token"], gemini_key or defaults["gemini_key"], gemini_model)
                st.success(_get_text(T, "run_tab.save_success") or "已保存到本地")
                st.rerun()

        st.markdown('<p class="step-label step-3">③ 导出方式</p>', unsafe_allow_html=True)
        st.caption("Excel 默认生成并可下载。")
        ex_row1, ex_row2 = st.columns([1, 1])
        with ex_row1:
            export_quip = st.checkbox(_get_text(T, "run_tab.export_quip") or "导出到 Quip", value=False, key="run_export_quip")
        with ex_row2:
            export_sheets = st.checkbox(_get_text(T, "run_tab.export_sheets") or "导出到 Google 表格", value=False, key="run_export_sheets")
        export_quip_target = st.text_input(
            _get_text(T, "run_tab.export_quip_target_label") or "Quip 目标文档（可选）",
            placeholder=_get_text(T, "run_tab.export_quip_target_placeholder") or "留空则新建；填写则追加到该文档末尾",
            key="export_quip_target",
            help="勾选「导出到 Quip」后，可填写目标文档链接以追加内容；留空则新建文档。",
        )
        auto_archive = st.checkbox(
            _get_text(T, "run_tab.auto_archive_label") or "生成后自动归档到全回归用例",
            value=False,
            key="run_auto_archive",
            help=_get_text(T, "run_tab.auto_archive_help") or "将本次生成的新用例追加到项目记忆中的全回归用例，供下次生成时参考。",
        )

        st.markdown('<p class="step-label step-4">④ 执行</p>', unsafe_allow_html=True)
        if st.button(_get_text(T, "run_tab.run_btn") or "生成测试用例", type="primary", use_container_width=True, key="run_pipeline_btn"):
            if not quip_url or not quip_url.strip():
                st.error(_get_text(T, "run_tab.quip_url_required") or "请先填写需求文档链接")
            else:
                os.environ["QUIP_ACCESS_TOKEN"] = quip_token or os.environ.get("QUIP_ACCESS_TOKEN", "")
                os.environ["GEMINI_API_KEY"] = gemini_key or os.environ.get("GEMINI_API_KEY", "")
                os.environ["GEMINI_MODEL"] = gemini_model or os.environ.get("GEMINI_MODEL", "gemini-2.5-flash-lite")
                if not os.environ.get("GEMINI_API_KEY"):
                    st.error(_get_text(T, "run_tab.gemini_required") or "请填写 Gemini API Key 或先在「账号与模型」中保存")
                else:
                    with st.spinner(_get_text(T, "run_tab.run_spinner") or "正在拉取需求并生成用例…"):
                        try:
                            demand, demand_title = load_demand_from_quip(quip_url.strip(), return_title=True)
                        except Exception as e:
                            st.error(f"{_get_text(T, 'run_tab.quip_fetch_fail') or '拉取文档失败'}: {e}")
                            demand = None
                        if demand:
                            try:
                                out = run_pipeline(
                                    demand,
                                    output_dir=OUTPUT_DIR,
                                    export_excel=True,
                                    export_quip=export_quip or bool(export_quip_target and export_quip_target.strip()),
                                    export_sheets=export_sheets,
                                    export_quip_target=(export_quip_target or "").strip() or None,
                                    demand_title=demand_title,
                                    return_details=True,
                                )
                            except Exception as e:
                                st.error(f"{_get_text(T, 'run_tab.pipeline_fail') or '执行失败'}: {e}")
                                raise
                            if isinstance(out, dict):
                                st.session_state["last_run"] = out
                                st.session_state["last_demand_snippet"] = demand[:500] + ("..." if len(demand) > 500 else "")
                                st.session_state["last_demand_full"] = demand
                                _archive_msg = ""
                                if auto_archive:
                                    result_str = out.get("result_str", "")
                                    tables = _parse_markdown_tables(result_str)
                                    if tables:
                                        from datetime import datetime
                                        new_text = tables_to_text(tables)
                                        section = f"\n\n【{datetime.now().strftime('%Y-%m-%d %H:%M')} 新增】\n{new_text}"
                                        current = get_entry_content(TEST_CASES_SOURCE_TYPE, "full_regression") or ""
                                        updated = (current + section).strip()
                                        add_entry(TEST_CASES_SOURCE_TYPE, updated, source_id="full_regression", title="全回归测试用例", summary=updated[:500])
                                        _archive_msg = "，已归档到全回归用例"
                                st.success((_get_text(T, "run_tab.run_success") or "生成完成") + _archive_msg)
                            else:
                                st.session_state["last_run"] = {"result_str": out, "step_outputs": [], "excel_path": None, "quip_url": None, "sheets_url": None, "timestamp": "", "txt_path": ""}
                                st.session_state["last_demand_snippet"] = demand[:500] + ("..." if len(demand) > 500 else "")
                                st.session_state["last_demand_full"] = demand
                                st.success(_get_text(T, "run_tab.run_success") or "生成完成")

        if st.session_state.get("last_run"):
            r = st.session_state["last_run"]
            # 先展示「输出与下载」，最常用
            st.subheader(_get_text(T, "run_tab.section_links") or "输出与下载")
            excel_path = r.get("excel_path")
            quip_link = r.get("quip_url")
            sheets_link = r.get("sheets_url")
            txt_path = r.get("txt_path", "")
            link_cols = st.columns([1, 1, 1])
            with link_cols[0]:
                if excel_path and os.path.isfile(excel_path):
                    with open(excel_path, "rb") as f:
                        st.download_button(
                            _get_text(T, "run_tab.download_excel") or "📥 下载 Excel",
                            f, file_name=os.path.basename(excel_path),
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            key="dl_excel",
                        )
                else:
                    st.caption(_get_text(T, "run_tab.excel_not_found") or "未生成 Excel")
            with link_cols[1]:
                if quip_link:
                    st.markdown(f"[{_get_text(T, 'run_tab.quip_doc_label') or '打开 Quip 文档'}]({quip_link})")
            with link_cols[2]:
                if sheets_link:
                    st.markdown(f"[{_get_text(T, 'run_tab.google_sheets_label') or '打开 Google 表格'}]({sheets_link})")
            if txt_path and os.path.isfile(txt_path):
                st.caption(f"{_get_text(T, 'run_tab.result_saved') or '完整结果已保存'}: `{txt_path}`")

            # 步骤与全文折叠展示
            step_outputs = r.get("step_outputs") or []
            with st.expander(_get_text(T, "run_tab.section_steps") or "查看 Agent 沟通过程", expanded=False):
                if step_outputs:
                    for i, step in enumerate(step_outputs, 1):
                        with st.expander(f"步骤 {i}: {step.get('task', '')} — {step.get('agent', '')}", expanded=False):
                            st.markdown(step.get("content", ""))
                else:
                    st.info(_get_text(T, "run_tab.no_step_output") or "本次未采集到分步输出。")

            with st.expander(_get_text(T, "run_tab.section_result") or "查看最终结果全文", expanded=False):
                st.markdown(r.get("result_str", ""))

    # ---------- 编辑 Agent ----------
    with tab_agents:
        st.subheader(_get_text(T, "agents_tab.section_title") or "编辑 Agent 与 Task")
        st.caption(_get_text(T, "agents_tab.section_caption") or "修改角色、目标与任务描述后，点击底部「保存配置」生效；下次生成用例将使用新配置。")
        config = load_agents_config()
        if not config:
            st.warning("未找到 config/agents.yaml 或 PyYAML 未安装；可在此编辑并保存。")
            raw_yaml = st.text_area("agents.yaml 内容", height=400, placeholder="agents:\n  - id: ...\n    role: ...\n    goal: ...\n    backstory: |\n      ...", key="agents_raw_yaml")
            if st.button("保存 agents.yaml", key="agents_save_raw"):
                if raw_yaml.strip():
                    os.makedirs(CONFIG_DIR, exist_ok=True)
                    with open(AGENTS_CONFIG_PATH, "w", encoding="utf-8") as f:
                        f.write(raw_yaml.strip())
                    st.success("已保存")
                    st.rerun()
        else:
            agents = config.get("agents") or []
            tasks = config.get("tasks") or []
            st.markdown("**Agent（角色）**")
            for i, a in enumerate(agents):
                with st.expander(f"Agent {i + 1}/{len(agents)}: {a.get('role', a.get('id', '未命名'))}", expanded=False):
                    a_id = st.text_input("id", value=a.get("id", ""), key=f"agent_id_{i}", help="唯一标识，Task 中通过 agent_id 引用")
                    a_role = st.text_input("role", value=a.get("role", ""), key=f"agent_role_{i}")
                    a_goal = st.text_area("goal", value=a.get("goal", ""), key=f"agent_goal_{i}", height=80)
                    a_back = st.text_area("backstory", value=(a.get("backstory") or "").strip(), key=f"agent_back_{i}", height=120)
                    a["id"], a["role"], a["goal"], a["backstory"] = a_id, a_role, a_goal, a_back
            st.divider()
            st.markdown("**Task（任务）**")
            for i, t in enumerate(tasks):
                with st.expander(f"Task {i + 1}/{len(tasks)}: {t.get('id', '')} ← {t.get('agent_id', '')}", expanded=False):
                    t_id = st.text_input("id", value=t.get("id", ""), key=f"task_id_{i}")
                    t_agent_id = st.text_input("agent_id", value=t.get("agent_id", ""), key=f"task_agent_{i}", help="对应上方某 Agent 的 id")
                    t_desc = st.text_area("description", value=(t.get("description") or "").strip(), key=f"task_desc_{i}", height=100)
                    t_out = st.text_input("expected_output", value=t.get("expected_output", ""), key=f"task_out_{i}")
                    t["id"], t["agent_id"], t["description"], t["expected_output"] = t_id, t_agent_id, t_desc, t_out
            if st.button(_get_text(T, "agents_tab.save_btn") or "保存配置到 config/agents.yaml", type="primary", key="agents_save_config"):
                try:
                    import yaml
                    with open(AGENTS_CONFIG_PATH, "w", encoding="utf-8") as f:
                        yaml.dump(config, f, allow_unicode=True, default_flow_style=False, sort_keys=False)
                    st.success("已保存，下次生成用例将使用新配置")
                except Exception as e:
                    st.error(str(e))

    # ---------- 项目记忆 ----------
    with tab_memory:
        st.subheader(_get_text(T, "memory_tab.section_title") or "项目记忆")
        st.caption(_get_text(T, "memory_tab.caption_browse") or "导入的需求文档供 Agent 参考；先搜索查看已有内容，再按需导入。")

        st.markdown("**搜索**")
        kw = st.text_input(
            _get_text(T, "memory_tab.search_label") or "搜索",
            placeholder=_get_text(T, "memory_tab.search_placeholder") or "输入关键词（如：直播、禁言、AB test）",
            key="mem_search",
            label_visibility="collapsed",
        )
        entries = search(kw, limit=20) if kw and kw.strip() else []
        if entries:
            base = os.getenv("QUIP_BASE_URL", "https://quip.com").rstrip("/")
            for e in entries:
                label = f"【{e.get('source_type', '')}】{e.get('title', '') or e.get('source_id', '')} — {e.get('created_at', '')}"
                col_title, col_del = st.columns([1, 0.12])
                with col_title:
                    with st.expander(label, expanded=False):
                        content = e.get("content", "") or e.get("summary", "")
                        sid = e.get("source_id", "")
                        src_type = e.get("source_type", "")
                        if src_type == TEST_CASES_SOURCE_TYPE:
                            src = "导入（Excel/CSV/粘贴）"
                        elif sid and len(sid) >= 10:
                            src = f"{base}/{sid}"
                        else:
                            src = sid or "-"
                        st.caption(f"来源: {src}")
                        st.markdown(content[:2000] + ("..." if len(content) > 2000 else ""))
                with col_del:
                    if st.button("🗑", key=f"del_{e.get('id')}", type="secondary", help="删除此条"):
                        delete_entry(e.get("id"))
                        st.rerun()
        elif kw and kw.strip():
            st.info(_get_text(T, "memory_tab.search_empty") or "未找到匹配文档。")
        else:
            st.info(_get_text(T, "memory_tab.search_first") or "输入关键词搜索，或通过下方导入后搜索。")

        st.divider()
        st.markdown("**导入需求**")
        quip_for_import = st.text_input(
            _get_text(T, "memory_tab.quip_token_import_label") or "Quip Token",
            value=defaults["quip_token"], type="password", key="quip_token_import",
            help="与「生成用例」页共用；已保存则自动带出",
        )

        st.markdown("方式一：从文件夹批量导入")
        folder_url = st.text_input(
            _get_text(T, "memory_tab.folder_label") or "文件夹链接或 folder_id",
            placeholder=_get_text(T, "memory_tab.folder_placeholder") or "https://quip.com/xxx/文件夹名 或 12 位 folder_id",
            key="quip_folder",
            label_visibility="collapsed",
        )
        st.caption(_get_text(T, "memory_tab.filter_hint") or "仅导入需求类文档，自动过滤测试用例、UI走查、周报等。")
        stable = _load_stable_quip_batch()
        with st.expander("高级：分批拉取（遇 503 时调整）", expanded=False):
            batch_size = st.number_input("每批文档数", min_value=1, max_value=50, value=int(stable["batch_size"]), key="mem_batch_size")
            batch_pause = st.number_input("批间暂停（秒）", min_value=0, max_value=300, value=int(stable["batch_pause"]), key="mem_batch_pause")
        if st.button("从文件夹批量导入", key="mem_import_folder"):
            if not folder_url or not folder_url.strip():
                st.error("请填写文件夹链接或 ID")
            else:
                os.environ["QUIP_ACCESS_TOKEN"] = quip_for_import or os.getenv("QUIP_ACCESS_TOKEN", "")
                if not os.environ.get("QUIP_ACCESS_TOKEN"):
                    st.warning("请先填写上方 Quip Token 或在「生成用例」页保存")
                else:
                    progress_bar = st.progress(0)
                    status_text = st.empty()
                    def on_progress(cur, tot, msg):
                        if tot > 0:
                            progress_bar.progress(min(1.0, cur / tot))
                        status_text.caption(f"正在拉取 {cur}/{tot}: {(msg or '')[:60]}{'…' if len(msg or '') > 60 else ''}")
                    try:
                        docs, stats = load_demands_from_quip_folder(
                            folder_url.strip(),
                            progress_callback=on_progress,
                            batch_size=int(batch_size),
                            batch_pause=float(batch_pause),
                            progress_info={},
                        )
                        for d in docs:
                            add_entry("quip_folder", d["content"], source_id=d["thread_id"], title=d["title"], summary=d["content"][:500])
                        progress_bar.progress(1.0)
                        status_text.caption("")
                        _save_stable_quip_batch(stats["stable_batch_size"], stats["stable_batch_pause"])
                        filtered = stats.get("filtered_count", 0)
                        msg = f"已导入 {len(docs)} 条"
                        if filtered > 0:
                            msg += f"，过滤 {filtered} 条非需求"
                        msg += "。可在上方搜索查看。"
                        st.success(msg)
                    except Exception as ex:
                        st.error(f"导入失败: {ex}")

        st.markdown("方式二：从单文档导入")
        single_url = st.text_input(
            _get_text(T, "memory_tab.single_label") or "文档链接",
            placeholder=_get_text(T, "memory_tab.single_placeholder") or "https://quip.com/xxx",
            key="quip_single",
            label_visibility="collapsed",
        )
        if st.button("导入该文档", key="mem_import_single"):
            if single_url and single_url.strip():
                try:
                    content, doc_title = load_demand_from_quip(single_url.strip(), return_title=True)
                    keep, reason = is_product_requirement_doc("", content)
                    if not keep:
                        st.warning(f"被识别为非需求文档（{reason}），已跳过。")
                    else:
                        add_entry("quip_single", content, source_id=single_url.strip(), title=doc_title, summary=content[:500])
                        st.success("已导入，可在上方搜索查看")
                except Exception as ex:
                    st.error(str(ex))
            else:
                st.error("请填写文档链接")

        st.markdown(_get_text(T, "memory_tab.test_cases_section") or "方式三：导入全回归测试用例")
        st.caption(_get_text(T, "memory_tab.test_cases_caption") or "从 Quip 链接拉取、上传文件或粘贴内容，Agent 将参考既有用例理解项目。")
        test_cases_quip_url = st.text_input(
            "Quip 文档链接",
            placeholder=_get_text(T, "memory_tab.test_cases_quip_placeholder") or "https://quip.com/xxx/全回归用例",
            key="test_cases_quip_url",
            label_visibility="collapsed",
        )
        if st.button(_get_text(T, "memory_tab.test_cases_from_quip_btn") or "从该 Quip 文档导入", key="mem_import_test_cases_quip"):
            if test_cases_quip_url and test_cases_quip_url.strip():
                os.environ["QUIP_ACCESS_TOKEN"] = quip_for_import or os.getenv("QUIP_ACCESS_TOKEN", "")
                if not os.environ.get("QUIP_ACCESS_TOKEN"):
                    st.warning("请先填写上方 Quip Token")
                else:
                    try:
                        content, doc_title = load_demand_from_quip(test_cases_quip_url.strip(), return_title=True)
                        add_entry(TEST_CASES_SOURCE_TYPE, content, source_id="full_regression", title=doc_title or "全回归测试用例", summary=content[:500])
                        st.success(f"已导入「{doc_title or '全回归'}」，Agent 将参考既有用例。")
                        st.rerun()
                    except Exception as ex:
                        st.error(f"拉取失败: {ex}")
            else:
                st.error("请填写 Quip 文档链接")
        test_cases_file = st.file_uploader(
            _get_text(T, "memory_tab.test_cases_upload_placeholder") or "上传文件",
            type=["xlsx", "xls", "csv", "txt"],
            key="test_cases_upload",
            label_visibility="collapsed",
        )
        test_cases_paste = st.text_area(
            _get_text(T, "memory_tab.test_cases_paste_placeholder") or "或粘贴内容",
            placeholder=_get_text(T, "memory_tab.test_cases_paste_placeholder") or "表格（| 分隔）或纯文本",
            key="test_cases_paste",
            height=100,
            label_visibility="collapsed",
        )
        if st.button(_get_text(T, "memory_tab.test_cases_import_btn") or "导入测试用例", key="mem_import_test_cases"):
            content = ""
            if test_cases_file:
                try:
                    content, rows = parse_test_cases_file(test_cases_file)
                    if not content.strip():
                        st.warning("文件内容为空")
                    else:
                        add_entry(TEST_CASES_SOURCE_TYPE, content, source_id="full_regression", title="全回归测试用例", summary=content[:500])
                        st.success(f"已导入 {rows} 行，Agent 将参考既有用例。")
                        st.rerun()
                except Exception as ex:
                    st.error(f"解析失败: {ex}")
            elif test_cases_paste and test_cases_paste.strip():
                content = test_cases_paste.strip()
                add_entry(TEST_CASES_SOURCE_TYPE, content, source_id="full_regression", title="全回归测试用例", summary=content[:500])
                st.success("已导入，Agent 将参考既有用例。")
                st.rerun()
            else:
                st.error("请上传文件或粘贴内容")

        st.divider()
        with st.expander(_get_text(T, "memory_tab.memory_summary_section") or "项目记忆摘要（高级）", expanded=False):
            mem = load_project_memory()
            new_mem = st.text_area(
                _get_text(T, "memory_tab.memory_text_label") or "内容",
                value=mem, height=180, key="project_memory_text",
            )
            c1, c2 = st.columns(2)
            with c1:
                if st.button("保存摘要", key="mem_save_summary"):
                    os.makedirs(CONFIG_DIR, exist_ok=True)
                    with open(PROJECT_MEMORY_PATH, "w", encoding="utf-8") as f:
                        f.write(new_mem)
                    st.success("已保存")
            with c2:
                if st.button("从本次运行追加", key="mem_update_from_run"):
                    if st.session_state.get("last_run") and st.session_state.get("last_demand_snippet"):
                        snippet = st.session_state["last_demand_snippet"]
                        result = st.session_state["last_run"].get("result_str", "")[:2000]
                        addition = f"【最近一次需求摘要】\n{snippet}\n\n【产出摘要】\n{result}"
                        update_project_memory(addition)
                        add_entry("run_summary", result, title="最近一次运行", summary=snippet)
                        st.success("已追加到项目记忆")
                    else:
                        st.info("请先在「生成用例」页运行一次")

    # ---------- 与文档 Agent 沟通 ----------
    with tab_chat:
        st.subheader(_get_text(T, "chat_tab.section_title") or "与产品文档管理 Agent 沟通")
        st.caption(_get_text(T, "chat_tab.section_desc") or "Agent 可理解全部需求文档。选择项目整体记忆或手动填入 Quip 文档。")

        doc_source = st.radio(
            _get_text(T, "chat_tab.doc_source_label") or "文档来源",
            options=["memory", "paste"],
            format_func=lambda x: {
                "memory": _get_text(T, "chat_tab.doc_source_memory") or "项目整体记忆（全部需求文档）",
                "paste": _get_text(T, "chat_tab.doc_source_paste") or "手动填入 Quip 文档",
            }[x],
            key="chat_doc_source",
        )
        doc_context = ""
        if doc_source == "memory":
            from memory_store import get_all_demands_full_for_chat
            doc_context = get_all_demands_full_for_chat(limit=30).strip()
            if not doc_context:
                st.info(_get_text(T, "chat_tab.doc_source_empty") or "项目记忆暂无需求文档。请先在「项目记忆」页从 Quip 导入。")
        else:
            quip_url_input = st.text_input(
                _get_text(T, "chat_tab.quip_url_label") or "Quip 文档链接（可选，填写则自动拉取）",
                placeholder="https://quip.com/xxx",
                key="chat_quip_url",
            )
            if quip_url_input and quip_url_input.strip():
                os.environ["QUIP_ACCESS_TOKEN"] = defaults.get("quip_token") or os.environ.get("QUIP_ACCESS_TOKEN", "")
                try:
                    doc_context, _ = load_demand_from_quip(quip_url_input.strip(), return_title=True)
                except Exception as e:
                    st.error(f"拉取失败: {e}")
                    doc_context = ""
            if not doc_context:
                doc_context = st.text_area(
                    _get_text(T, "chat_tab.paste_placeholder") or "或在此粘贴需求文档内容",
                    height=150,
                    key="chat_paste_doc",
                ).strip()

        if "doc_chat_messages" not in st.session_state:
            st.session_state["doc_chat_messages"] = []

        if st.session_state["doc_chat_messages"] and st.button(_get_text(T, "chat_tab.clear_btn") or "清空对话", key="chat_clear"):
            st.session_state["doc_chat_messages"] = []
            st.rerun()

        for msg in st.session_state["doc_chat_messages"]:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])

        if doc_context:
            if st.button(_get_text(T, "chat_tab.quick_summary") or "请总结这份文档的核心要点与潜在风险", key="quick_summary_btn"):
                user_q = _get_text(T, "chat_tab.quick_summary") or "请总结这份文档的核心要点与潜在风险"
                st.session_state["doc_chat_messages"].append({"role": "user", "content": user_q})
                with st.chat_message("assistant"):
                    with st.spinner(_get_text(T, "chat_tab.thinking") or "文档 Agent 正在思考…"):
                        try:
                            os.environ["GEMINI_API_KEY"] = defaults.get("gemini_key") or os.environ.get("GEMINI_API_KEY", "")
                            os.environ["GEMINI_MODEL"] = defaults.get("gemini_model") or os.environ.get("GEMINI_MODEL", "gemini-1.5-flash")
                            reply = chat_with_document_agent(
                                user_message=user_q,
                                document_context=doc_context,
                                project_context=get_project_context_for_agent(include_store=False),
                            )
                        except Exception as e:
                            reply = f"调用失败: {e}"
                    st.markdown(reply)
                st.session_state["doc_chat_messages"].append({"role": "assistant", "content": reply})
                st.rerun()

        user_input = st.chat_input(_get_text(T, "chat_tab.chat_placeholder") or "输入问题…")
        if user_input and doc_context:
            st.session_state["doc_chat_messages"].append({"role": "user", "content": user_input})
            with st.chat_message("assistant"):
                with st.spinner(_get_text(T, "chat_tab.thinking") or "文档 Agent 正在思考…"):
                    try:
                        os.environ["GEMINI_API_KEY"] = defaults.get("gemini_key") or os.environ.get("GEMINI_API_KEY", "")
                        os.environ["GEMINI_MODEL"] = defaults.get("gemini_model") or os.environ.get("GEMINI_MODEL", "gemini-1.5-flash")
                        reply = chat_with_document_agent(
                            user_message=user_input,
                            document_context=doc_context,
                            project_context=get_project_context_for_agent(include_store=False),
                        )
                    except Exception as e:
                        reply = f"调用失败: {e}"
                st.markdown(reply)
            st.session_state["doc_chat_messages"].append({"role": "assistant", "content": reply})
            st.rerun()
        elif user_input and not doc_context:
            st.warning(_get_text(T, "chat_tab.doc_source_empty") or "请先选择并加载文档内容。")


if __name__ == "__main__":
    main()
