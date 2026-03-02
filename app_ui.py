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
    load_project_memory,
    parse_test_cases_file,
    run_pipeline,
    tables_to_text,
    update_project_memory,
)
from memory_store import TEST_CASES_SOURCE_TYPE, add_entry, delete_entry, get_entry_content, list_recent, search

CONFIG_DIR = os.path.dirname(AGENTS_CONFIG_PATH)
DEFAULTS_PATH = os.path.join(CONFIG_DIR, "defaults.json")
STABLE_QUIP_BATCH_PATH = os.path.join(CONFIG_DIR, "stable_quip_batch.json")
MODELS_CONFIG_PATH = os.path.join(CONFIG_DIR, "models.yaml")
WORKBENCH_APPS_PATH = os.path.join(CONFIG_DIR, "workbench_apps.yaml")
OUTPUT_DIR = "output"
LAST_RUN_JSON = os.path.join(OUTPUT_DIR, "last_run.json")

MODULE_QUIP_TO_CASES = "quip_to_cases"
MODULE_AGENTS = "agents"
MODULE_MEMORY = "memory"
MODULE_CHAT = "chat"
MODULE_SETTINGS = "settings"


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


def _save_last_run(r: dict) -> None:
    """持久化上次运行结果到 JSON，刷新后仍可展示。"""
    try:
        import json
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        out = {
            "excel_path": r.get("excel_path"),
            "txt_path": r.get("txt_path"),
            "quip_url": r.get("quip_url"),
            "sheets_url": r.get("sheets_url"),
            "demand_title": r.get("demand_title", ""),
            "timestamp": r.get("timestamp", ""),
        }
        with open(LAST_RUN_JSON, "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def _load_last_run() -> dict | None:
    """从 JSON 恢复上次运行结果（刷新后使用）。"""
    try:
        import json
        if not os.path.isfile(LAST_RUN_JSON):
            return None
        with open(LAST_RUN_JSON, "r", encoding="utf-8") as f:
            data = json.load(f)
        excel_path = data.get("excel_path") or ""
        txt_path = data.get("txt_path") or ""
        if not excel_path and not txt_path:
            return None
        result_str = ""
        if txt_path and os.path.isfile(txt_path):
            with open(txt_path, "r", encoding="utf-8") as f:
                result_str = f.read()
        return {
            "excel_path": excel_path if os.path.isfile(excel_path) else None,
            "txt_path": txt_path,
            "quip_url": data.get("quip_url"),
            "sheets_url": data.get("sheets_url"),
            "result_str": result_str,
            "step_outputs": [],
            "timestamp": data.get("timestamp", ""),
            "demand_title": data.get("demand_title", ""),
        }
    except Exception:
        return None


def _save_stable_quip_batch(batch_size: int, batch_pause: float):
    """保存稳定拉取参数，供下次使用。"""
    import json
    os.makedirs(CONFIG_DIR, exist_ok=True)
    with open(STABLE_QUIP_BATCH_PATH, "w", encoding="utf-8") as f:
        json.dump({"batch_size": batch_size, "batch_pause": batch_pause}, f, ensure_ascii=False, indent=2)


def _load_models() -> tuple[list[tuple[str, str]], str]:
    """从 config/models.yaml 读取模型列表，返回 ((key, label), ...) 与默认 key。"""
    try:
        import yaml
        if os.path.isfile(MODELS_CONFIG_PATH):
            with open(MODELS_CONFIG_PATH, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
                models = data.get("models") or []
                out = []
                default_key = "gemini-2.5-flash-lite"
                for m in models:
                    k = (m.get("key") or "").strip()
                    label = (m.get("label") or k).strip()
                    if k:
                        out.append((k, label))
                        if m.get("default") is True:
                            default_key = k
                if out:
                    return out, default_key
    except Exception:
        pass
    return [
        ("gemini-1.5-flash", "1.5 Flash（免费实验推荐）"),
        ("gemini-1.5-pro", "1.5 Pro（免费，质量高限额低）"),
        ("gemini-2.5-flash-lite", "2.5 Flash-Lite（免费额度较高）"),
        ("gemini-2.5-flash", "2.5 Flash（付费/免费皆可）"),
    ], "gemini-2.5-flash-lite"


def _load_workbench_apps(T: dict) -> list[dict]:
    """从 config/workbench_apps.yaml 读取工作台模块列表，仅返回 enabled 且按 order 排序的项。"""
    try:
        import yaml
        if os.path.isfile(WORKBENCH_APPS_PATH):
            with open(WORKBENCH_APPS_PATH, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
                apps = data.get("apps") or []
                out = [a for a in apps if a.get("enabled", True)]
                out.sort(key=lambda x: (x.get("order", 99), x.get("id", "")))
                for a in out:
                    label_key = a.get("label_key")
                    a["label"] = _get_text(T, label_key) or a.get("label", a.get("id", ""))
                return out
    except Exception:
        pass
    return [
        {"id": MODULE_QUIP_TO_CASES, "label": _get_text(T, "tabs.run") or "生成用例"},
        {"id": MODULE_AGENTS, "label": _get_text(T, "tabs.agents") or "编辑 Agent"},
        {"id": MODULE_MEMORY, "label": _get_text(T, "tabs.memory") or "项目记忆"},
        {"id": MODULE_CHAT, "label": _get_text(T, "tabs.chat") or "文档问答"},
        {"id": MODULE_SETTINGS, "label": _get_text(T, "app.settings") or "设置"},
    ]


def _get_module_state_key(module_id: str, suffix: str) -> str:
    return f"app_{module_id}_{suffix}"


def _ensure_task_context(module_id: str) -> None:
    """初始化或更新 current_task_context，约定见 docs/ui-architecture-spec.md"""
    if "current_task_context" not in st.session_state:
        st.session_state["current_task_context"] = {
            "module_id": module_id,
            "task_id": "",
            "input_summary": {},
            "output_summary": {},
            "started_at": "",
            "status": "pending",
        }
    st.session_state["current_task_context"]["module_id"] = module_id


def _load_defaults():
    """从环境变量、Keyring 或 config/defaults.json 读取默认 Token / Key / 模型。"""
    try:
        from credential_store import get_credentials
        return get_credentials()
    except ImportError:
        pass
    # 降级：无 credential_store 时用 JSON
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
        except Exception:
            pass
    if not out["gemini_model"]:
        out["gemini_model"] = "gemini-2.5-flash-lite"
    return out


def _save_defaults(quip_token: str, gemini_key: str, gemini_model: str = "") -> str:
    """将默认 Token / Key / 模型写入 Keyring 或 config/defaults.json。返回存储方式。"""
    try:
        from credential_store import set_credentials
        ok, mode = set_credentials(quip_token, gemini_key, gemini_model)
        return mode
    except ImportError:
        pass
    import json
    os.makedirs(CONFIG_DIR, exist_ok=True)
    payload = {"quip_token": quip_token or "", "gemini_key": gemini_key or ""}
    if gemini_model:
        payload["gemini_model"] = gemini_model
    with open(DEFAULTS_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    try:
        os.chmod(DEFAULTS_PATH, 0o600)
    except OSError:
        pass
    return "JSON"


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


def _render_main_app(T: dict, cookies=None):
    """主应用：侧栏导航 + 主区内容。"""
    app_title = _get_text(T, "app.title") or "用例工坊 · AI 测试协作平台"
    defaults = _load_defaults()
    workbench_apps = _load_workbench_apps(T)

    # 设计系统 CSS（见 docs/implementation-handoff-for-programming.md）
    st.markdown("""
    <style>
    :root {
        --color-primary: #0d9488;
        --color-primary-dark: #0f766e;
        --color-primary-light: #5eead4;
        --color-bg-main: #f8fafc;
        --color-bg-card: #ffffff;
        --color-success: #059669;
        --color-error: #dc2626;
        --color-warning: #d97706;
        --radius-card: 12px;
        --radius-button: 10px;
    }
    .main .block-container {
        padding-top: 1.2rem; padding-bottom: 2.5rem;
        max-width: 960px; margin-left: auto; margin-right: auto;
    }
    .main { background: var(--color-bg-main); }
    h1 { font-size: 1.6rem !important; font-weight: 600 !important; color: #0f172a !important; margin-bottom: 0.6rem !important; letter-spacing: -0.02em; }
    h2 { font-size: 1.1rem !important; font-weight: 600 !important; color: #334155 !important; margin-top: 1.25rem !important; margin-bottom: 0.5rem !important; }
    h3 { font-size: 0.95rem !important; font-weight: 500 !important; color: #64748b !important; margin-top: 0.75rem !important; margin-bottom: 0.4rem !important; }
    p { line-height: 1.6; color: #334155; font-size: 0.95rem; }
    .step-label { font-size: 0.8rem; font-weight: 600; color: var(--color-primary); text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 0.35rem; }
    .step-label.step-3, .step-label.step-4 { margin-top: 1.25rem; }
    div[data-testid="stExpander"] {
        margin-top: 0.5rem; margin-bottom: 0.25rem;
        border: 1px solid #e2e8f0; border-radius: var(--radius-card);
        background: var(--color-bg-card); box-shadow: 0 1px 3px rgba(0,0,0,0.08);
    }
    div[data-testid="stExpander"] > div:first-child { border-radius: var(--radius-card); }
    .stButton > button { border-radius: var(--radius-button) !important; font-weight: 500 !important; transition: opacity 0.15s; }
    .stButton > button:hover { opacity: 0.9; }
    .main .stButton > button[kind="primary"] { font-weight: 600 !important; background: var(--color-primary) !important; }
    .stTextInput > div > div, .stSelectbox > div { border-radius: var(--radius-card); }
    .stSuccess { border-radius: var(--radius-card); padding: 0.75rem 1rem; background: #ecfdf5; color: var(--color-success); }
    .stError { border-radius: var(--radius-card); padding: 0.75rem 1rem; color: var(--color-error); }
    .stWarning { border-radius: var(--radius-card); padding: 0.75rem 1rem; color: var(--color-warning); }
    .stInfo { border-radius: var(--radius-card); padding: 0.75rem 1rem; }
    [data-testid="stAlert"] { border-radius: var(--radius-card); }
    div[data-testid="stExpander"] summary { font-size: 0.9rem; padding: 0.6rem 0.75rem; }
    hr { margin: 1.25rem 0; border-color: #e2e8f0; opacity: 0.8; }
    .card-style { background: var(--color-bg-card); border-radius: var(--radius-card); box-shadow: 0 1px 3px rgba(0,0,0,0.08); padding: 1rem; margin-bottom: 1rem; }
    #MainMenu { visibility: hidden; }
    footer { visibility: hidden; }
    header { visibility: hidden; }
    </style>
    """, unsafe_allow_html=True)

    # 侧栏导航
    if "current_page" not in st.session_state:
        st.session_state["current_page"] = MODULE_QUIP_TO_CASES

    with st.sidebar:
        st.markdown(f"**{app_title}**")
        st.caption(_get_text(T, "app.slogan") or "需求即输入，用例即输出，AI 全程协同一键生成")
        st.divider()
        st.markdown("**工作台**")
        for app in workbench_apps:
            module_id = app["id"]
            if module_id in (MODULE_QUIP_TO_CASES, MODULE_MEMORY, MODULE_CHAT):
                if st.button(
                    app["label"],
                    key=f"nav_{module_id}",
                    use_container_width=True,
                    type="primary" if st.session_state["current_page"] == module_id else "secondary",
                ):
                    st.session_state["current_page"] = module_id
                    st.rerun()
        st.markdown("**高级**")
        for app in workbench_apps:
            module_id = app["id"]
            if module_id in (MODULE_AGENTS, MODULE_SETTINGS):
                if st.button(
                    app["label"],
                    key=f"nav_{module_id}",
                    use_container_width=True,
                    type="primary" if st.session_state["current_page"] == module_id else "secondary",
                ):
                    st.session_state["current_page"] = module_id
                    st.rerun()
        st.divider()

    # 主区内容
    current_page = st.session_state["current_page"]
    _ensure_task_context(current_page)

    _page_labels = {a["id"]: a["label"] for a in workbench_apps}
    _page_title = _page_labels.get(current_page, current_page)

    if current_page == MODULE_QUIP_TO_CASES:
        st.title(_get_text(T, "run_tab.run_btn") or "生成测试用例")
    else:
        st.title(_page_title)

    if current_page == MODULE_QUIP_TO_CASES:
        _render_module_quip_to_cases(T, defaults)
    elif current_page == MODULE_AGENTS:
        _render_module_agents(T)
    elif current_page == MODULE_MEMORY:
        _render_module_memory(T, defaults)
    elif current_page == MODULE_CHAT:
        _render_module_chat(T, defaults)
    elif current_page == MODULE_SETTINGS:
        _render_module_settings(T, defaults)
    else:
        st.info(f"模块「{current_page}」尚未实现。")


def _render_module_quip_to_cases(T: dict, defaults: dict):
    """工作台模块：Quip 转用例。首屏精简：链接 + 配置折叠 + 主按钮。"""
    st.caption(_get_text(T, "run_tab.page_caption") or "从 Quip 需求文档生成测试用例，支持导出 Excel / Quip / Google 表格。")
    st.markdown("<div style='margin-bottom:0.5rem'></div>", unsafe_allow_html=True)

    # ① 需求链接（突出）
    st.markdown('<p class="step-label">① 需求文档</p>', unsafe_allow_html=True)
    quip_url = st.text_input(
        _get_text(T, "run_tab.quip_url_label") or "需求文档链接",
        placeholder=_get_text(T, "run_tab.quip_url_placeholder") or "粘贴 Quip 文档链接或 thread_id",
        key="run_quip_url",
        label_visibility="collapsed",
    )
    if not quip_url or not quip_url.strip():
        st.caption(_get_text(T, "run_tab.quip_url_hint") or "示例：https://quip.com/xxx 或 12 位 thread_id")
        if st.button(_get_text(T, "app.try_example") or "试试示例", key="run_try_example"):
            st.session_state["run_quip_url"] = "https://quip.com/example"
            st.rerun()

    # ② 配置区（可折叠：模型+导出+账号状态）
    _has_saved = bool(defaults.get("quip_token") and defaults.get("gemini_key"))
    _exp_label = "配置（已保存 ✓）" if _has_saved else "配置（未保存，请填写）"
    with st.expander(_exp_label, expanded=not _has_saved):
        gemini_models_list, default_model = _load_models()
        _model_opts = [m[0] for m in gemini_models_list]
        _model_idx = next((i for i, (k, _) in enumerate(gemini_models_list) if k == (defaults.get("gemini_model") or default_model)), 0)
        c1, c2 = st.columns([2, 1])
        with c1:
            gemini_model = st.selectbox(
                _get_text(T, "run_tab.gemini_model_label") or "Gemini 模型",
                options=_model_opts,
                index=_model_idx,
                format_func=lambda x: dict(gemini_models_list).get(x, x),
                key="run_gemini_model",
            )
        with c2:
            if st.button(_get_text(T, "run_tab.go_settings") or "去设置", key="run_go_settings"):
                st.session_state["current_page"] = MODULE_SETTINGS
                st.rerun()
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
        )
        auto_archive = st.checkbox(
            _get_text(T, "run_tab.auto_archive_label") or "生成后自动归档到全回归用例",
            value=False,
            key="run_auto_archive",
            help=_get_text(T, "run_tab.auto_archive_help"),
        )

    quip_token = defaults.get("quip_token", "")
    gemini_key = defaults.get("gemini_key", "")

    pipeline_running = st.session_state.get(_get_module_state_key(MODULE_QUIP_TO_CASES, "running"), False)
    st.markdown("<div style='margin-top:1rem'></div>", unsafe_allow_html=True)
    run_btn_label = (_get_text(T, "run_tab.run_spinner") or "运行中…") if pipeline_running else (_get_text(T, "run_tab.run_btn") or "生成测试用例")
    if st.button(run_btn_label, type="primary", use_container_width=True, key="run_pipeline_btn", disabled=pipeline_running):
            if not quip_url or not quip_url.strip():
                st.error(_get_text(T, "run_tab.quip_url_required") or "请先填写需求文档链接")
            else:
                os.environ["QUIP_ACCESS_TOKEN"] = quip_token or os.environ.get("QUIP_ACCESS_TOKEN", "")
                os.environ["GEMINI_API_KEY"] = gemini_key or os.environ.get("GEMINI_API_KEY", "")
                os.environ["GEMINI_MODEL"] = gemini_model or os.environ.get("GEMINI_MODEL", "gemini-2.5-flash-lite")
                if not os.environ.get("GEMINI_API_KEY"):
                    st.error(_get_text(T, "run_tab.gemini_required") or "请填写 Gemini API Key 或先在「账号与模型」中保存")
                else:
                    st.session_state[_get_module_state_key(MODULE_QUIP_TO_CASES, "last_error")] = None
                    st.session_state[_get_module_state_key(MODULE_QUIP_TO_CASES, "running")] = True
                    _progress_placeholder = st.empty()
                    try:
                        with _progress_placeholder.container():
                            st.progress(0.2, text="需求拉取…")
                        with st.spinner(_get_text(T, "run_tab.run_spinner") or "正在拉取需求并生成用例…"):
                            try:
                                demand, demand_title = load_demand_from_quip(quip_url.strip(), return_title=True)
                            except Exception as e:
                                _err_msg = f"{_get_text(T, 'run_tab.quip_fetch_fail') or '拉取文档失败'}: {e}"
                                st.session_state[_get_module_state_key(MODULE_QUIP_TO_CASES, "last_error")] = _err_msg
                                st.error(_err_msg)
                                demand = None
                        if demand:
                            try:
                                _progress_placeholder.progress(0.5, text="四 Agent 执行中…")
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
                                _err_msg = f"{_get_text(T, 'run_tab.pipeline_fail') or '执行失败'}: {e}"
                                st.session_state[_get_module_state_key(MODULE_QUIP_TO_CASES, "last_error")] = _err_msg
                                st.error(_err_msg)
                                raise
                            finally:
                                st.session_state[_get_module_state_key(MODULE_QUIP_TO_CASES, "running")] = False
                            if isinstance(out, dict):
                                _r = dict(out)
                                _r["demand_title"] = demand_title or ""
                                st.session_state[_get_module_state_key(MODULE_QUIP_TO_CASES, "last_error")] = None
                                st.session_state["app_last_run"] = _r
                                st.session_state[_get_module_state_key(MODULE_QUIP_TO_CASES, "last_run")] = _r
                                _save_last_run(_r)
                                st.session_state["app_last_demand_snippet"] = demand[:500] + ("..." if len(demand) > 500 else "")
                                st.session_state["app_last_demand_full"] = demand
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
                                    else:
                                        st.warning("归档失败：未解析到有效表格。")
                                _progress_placeholder.progress(1.0, text="完成")
                                _progress_placeholder.empty()
                                st.success((_get_text(T, "run_tab.run_success") or "生成完成") + _archive_msg)
                            else:
                                _r = {"result_str": out, "step_outputs": [], "excel_path": None, "quip_url": None, "sheets_url": None, "timestamp": "", "txt_path": "", "demand_title": demand_title or ""}
                                st.session_state["app_last_run"] = _r
                                st.session_state[_get_module_state_key(MODULE_QUIP_TO_CASES, "last_run")] = _r
                                st.session_state["app_last_demand_snippet"] = demand[:500] + ("..." if len(demand) > 500 else "")
                                st.session_state["app_last_demand_full"] = demand
                                _progress_placeholder.progress(1.0, text="完成")
                                _progress_placeholder.empty()
                                st.success(_get_text(T, "run_tab.run_success") or "生成完成")
                        else:
                            st.session_state[_get_module_state_key(MODULE_QUIP_TO_CASES, "running")] = False
                    finally:
                        _progress_placeholder.empty()
                        st.session_state[_get_module_state_key(MODULE_QUIP_TO_CASES, "running")] = False

    r = st.session_state.get("app_last_run") or st.session_state.get(_get_module_state_key(MODULE_QUIP_TO_CASES, "last_run"))
    if not r:
        r = _load_last_run()
        if r:
            st.session_state["app_last_run"] = r
            st.session_state[_get_module_state_key(MODULE_QUIP_TO_CASES, "last_run")] = r
    _last_error = st.session_state.get(_get_module_state_key(MODULE_QUIP_TO_CASES, "last_error"))
    if _last_error and not st.session_state.get(_get_module_state_key(MODULE_QUIP_TO_CASES, "running"), False):
        st.markdown("""
        <div class="card-style" style="border-left: 4px solid var(--color-error); background: #fef2f2;">
            <p style="margin:0 0 0.5rem 0; font-weight: 500;">执行失败</p>
            <p style="margin:0; color: var(--color-error);">{error_msg}</p>
        </div>
        """.format(error_msg=_last_error.replace("<", "&lt;").replace(">", "&gt;")), unsafe_allow_html=True)
        if st.button(_get_text(T, "run_tab.retry_btn") or "重试", key="run_retry_btn"):
            st.session_state[_get_module_state_key(MODULE_QUIP_TO_CASES, "last_error")] = None
            st.rerun()
    if not r:
        st.info(_get_text(T, "app.empty_state_hint") or "暂无生成记录，输入链接开始第一次")
    if r:
        st.subheader(_get_text(T, "run_tab.section_links") or "最近生成")
        excel_path = r.get("excel_path")
        quip_link = r.get("quip_url")
        sheets_link = r.get("sheets_url")
        txt_path = r.get("txt_path", "")
        demand_title = (r.get("demand_title", "") or "最近生成").replace("<", "&lt;").replace(">", "&gt;")
        _path_info = excel_path if (excel_path and os.path.isfile(excel_path)) else (_get_text(T, "run_tab.excel_not_found") or "未生成 Excel")
        _path_info = _path_info.replace("<", "&lt;").replace(">", "&gt;")
        _txt_safe = txt_path.replace("<", "&lt;").replace(">", "&gt;") if txt_path else ""
        _txt_line = f'<p style="margin:0.25rem 0 0; font-size:0.9rem; color:#64748b;">{_get_text(T, "run_tab.result_saved") or "完整结果已保存"}: {_txt_safe}</p>' if (txt_path and os.path.isfile(txt_path)) else ""
        st.markdown(f"""
        <div class="card-style">
            <p style="margin:0 0 0.25rem 0; font-weight: 500;">{demand_title}</p>
            <p style="margin:0; font-size:0.9rem; color:#64748b;">{_get_text(T, "run_tab.excel_path_label") or "本地路径"}: {_path_info}</p>
            {_txt_line}
        </div>
        """, unsafe_allow_html=True)
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

        step_outputs = r.get("step_outputs") or []
        try:
            from app_ui_components import render_log_terminal
            render_log_terminal(step_outputs, title=_get_text(T, "run_tab.section_steps") or "查看 Agent 沟通过程", key="run_log")
        except ImportError:
            with st.expander(_get_text(T, "run_tab.section_steps") or "查看 Agent 沟通过程", expanded=False):
                if step_outputs:
                    for i, step in enumerate(step_outputs, 1):
                        with st.expander(f"步骤 {i}: {step.get('task', '')} — {step.get('agent', '')}", expanded=False):
                            st.markdown(step.get("content", ""))
                else:
                    st.info(_get_text(T, "run_tab.no_step_output") or "本次未采集到分步输出。")

        with st.expander(_get_text(T, "run_tab.section_result") or "查看最终结果全文", expanded=False):
            st.markdown(r.get("result_str", ""))

def _render_module_agents(T: dict):
    """工作台模块：编辑 Agent。"""
    _agents_dirty = st.session_state.get(_get_module_state_key(MODULE_AGENTS, "dirty"), False)
    if _agents_dirty:
        st.warning("您有未保存的修改，请点击底部「保存配置」后再切换页面。")
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
        _last_hash_key = _get_module_state_key(MODULE_AGENTS, "last_saved_hash")
        if _last_hash_key not in st.session_state:
            st.session_state[_last_hash_key] = str(config)
        elif st.session_state[_last_hash_key] != str(config):
            st.session_state[_get_module_state_key(MODULE_AGENTS, "dirty")] = True
        if st.button(_get_text(T, "agents_tab.save_btn") or "保存配置到 config/agents.yaml", type="primary", key="agents_save_config"):
            try:
                import yaml
                with open(AGENTS_CONFIG_PATH, "w", encoding="utf-8") as f:
                    yaml.dump(config, f, allow_unicode=True, default_flow_style=False, sort_keys=False)
                st.session_state[_get_module_state_key(MODULE_AGENTS, "dirty")] = False
                st.session_state[_get_module_state_key(MODULE_AGENTS, "last_saved_hash")] = str(config)
                st.success("已保存，下次生成用例将使用新配置")
            except Exception as e:
                st.error(str(e))

def _render_module_memory(T: dict, defaults: dict):
    """工作台模块：项目记忆。"""
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
            st.error(_get_text(T, "memory_tab.quip_url_required") or "请填写 Quip 文档链接")

    st.markdown(_get_text(T, "memory_tab.test_cases_section") or "方式三：导入全回归测试用例")
    st.caption(_get_text(T, "memory_tab.test_cases_caption") or "从 Quip 链接拉取、上传文件或粘贴内容，Agent 将参考既有用例理解项目。")

    _full_regression = get_entry_content(TEST_CASES_SOURCE_TYPE, "full_regression")
    if _full_regression:
        _len_chars = len(_full_regression)
        _tpl = _get_text(T, "memory_tab.full_regression_status") or "全回归用例已导入（{count} 字），生成用例时 Agent 将参考理解。"
        st.success("✓ " + _tpl.format(count=_len_chars))

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
                st.warning(_get_text(T, "memory_tab.quip_token_required") or "请先填写上方 Quip Token")
            else:
                with st.spinner(_get_text(T, "memory_tab.import_spinner_quip") or "拉取中…"):
                    try:
                        content, doc_title = load_demand_from_quip(test_cases_quip_url.strip(), return_title=True)
                        add_entry(TEST_CASES_SOURCE_TYPE, content, source_id="full_regression", title=doc_title or "全回归测试用例", summary=content[:500])
                        st.success(f"已导入「{doc_title or '全回归'}」（{len(content)} 字），Agent 将参考既有用例。")
                        st.rerun()
                    except Exception as ex:
                        st.error(f"拉取失败: {ex}")
        else:
            st.error(_get_text(T, "memory_tab.quip_url_required") or "请填写 Quip 文档链接")

    try:
        from app_ui_components import render_file_uploader
        test_cases_upload_result = render_file_uploader(
            accepted_types=["xlsx", "xls", "csv", "txt"],
            key="test_cases_upload",
            label=_get_text(T, "memory_tab.test_cases_upload_placeholder") or "上传文件",
        )
        test_cases_file = test_cases_upload_result["file"] if test_cases_upload_result else None
    except ImportError:
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
        if test_cases_file:
            with st.spinner(_get_text(T, "memory_tab.import_spinner_file") or "解析文件中…"):
                try:
                    content, rows = parse_test_cases_file(test_cases_file)
                    if not content.strip():
                        st.warning(_get_text(T, "memory_tab.file_empty") or "文件内容为空")
                    else:
                        add_entry(TEST_CASES_SOURCE_TYPE, content, source_id="full_regression", title="全回归测试用例", summary=content[:500])
                        st.success(f"已导入 {rows} 行（{len(content)} 字），Agent 将参考既有用例。")
                        st.rerun()
                except Exception as ex:
                    st.error(f"{_get_text(T, 'memory_tab.parse_fail') or '解析失败'}: {ex}")
        elif test_cases_paste and test_cases_paste.strip():
            content = test_cases_paste.strip()
            add_entry(TEST_CASES_SOURCE_TYPE, content, source_id="full_regression", title="全回归测试用例", summary=content[:500])
            st.success(f"已导入（{len(content)} 字），Agent 将参考既有用例。")
            st.rerun()
        else:
            st.error(_get_text(T, "memory_tab.import_required") or "请上传文件或粘贴内容")

    st.divider()
    with st.expander(_get_text(T, "memory_tab.memory_summary_section") or "项目记忆摘要（高级）", expanded=False):
        mem = load_project_memory()
        new_mem = st.text_area(
            _get_text(T, "memory_tab.memory_text_label") or "内容",
            value=mem, height=180, key="project_memory_text",
        )
        c1, c2 = st.columns(2)
        with c1:
            if st.button(_get_text(T, "memory_tab.save_summary_btn") or "保存摘要", key="mem_save_summary"):
                os.makedirs(CONFIG_DIR, exist_ok=True)
                with open(PROJECT_MEMORY_PATH, "w", encoding="utf-8") as f:
                    f.write(new_mem)
                st.success("已保存")
        with c2:
            if st.button(_get_text(T, "memory_tab.append_from_run_btn") or "从本次运行追加", key="mem_update_from_run"):
                if st.session_state.get("app_last_run") and st.session_state.get("app_last_demand_snippet"):
                    snippet = st.session_state["app_last_demand_snippet"]
                    result = st.session_state["app_last_run"].get("result_str", "")[:2000]
                    addition = f"【最近一次需求摘要】\n{snippet}\n\n【产出摘要】\n{result}"
                    update_project_memory(addition)
                    add_entry("run_summary", result, title="最近一次运行", summary=snippet)
                    st.success("已追加到项目记忆")
                else:
                    st.info(_get_text(T, "memory_tab.run_first_hint") or "请先在「生成用例」页运行一次")

def _render_module_chat(T: dict, defaults: dict):
    """工作台模块：文档问答。"""
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

    if "app_doc_chat_messages" not in st.session_state:
        st.session_state["app_doc_chat_messages"] = []

    if st.session_state["app_doc_chat_messages"] and st.button(_get_text(T, "chat_tab.clear_btn") or "清空对话", key="chat_clear"):
        st.session_state["app_doc_chat_messages"] = []
        st.rerun()

    _doc_title = "无文档"
    if doc_context:
        _doc_title = (_get_text(T, "chat_tab.doc_source_memory") or "项目整体记忆") if doc_source == "memory" else (_get_text(T, "chat_tab.doc_source_paste") or "当前文档")
    st.caption(f"**当前文档：** {_doc_title}")

    for msg in st.session_state["app_doc_chat_messages"]:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    if doc_context:
        if st.button(_get_text(T, "chat_tab.quick_summary") or "请总结这份文档的核心要点与潜在风险", key="quick_summary_btn"):
            user_q = _get_text(T, "chat_tab.quick_summary") or "请总结这份文档的核心要点与潜在风险"
            st.session_state["app_doc_chat_messages"].append({"role": "user", "content": user_q})
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
            st.session_state["app_doc_chat_messages"].append({"role": "assistant", "content": reply})
            st.rerun()

    user_input = st.chat_input(_get_text(T, "chat_tab.chat_placeholder") or "输入问题…")
    if user_input and doc_context:
        st.session_state["app_doc_chat_messages"].append({"role": "user", "content": user_input})
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
        st.session_state["app_doc_chat_messages"].append({"role": "assistant", "content": reply})
        st.rerun()
    elif user_input and not doc_context:
        st.warning(_get_text(T, "chat_tab.doc_source_empty") or "请先选择并加载文档内容。")


def _render_module_settings(T: dict, defaults: dict):
    """工作台模块：设置（模型、凭证）。"""
    if st.button(_get_text(T, "app.back_btn") or "← 返回", key="settings_back"):
        st.session_state["current_page"] = MODULE_QUIP_TO_CASES
        st.rerun()
    st.caption("配置 API 凭证与模型，保存后生成用例时将自动使用。")
    with st.container():
        col1, col2 = st.columns(2)
        with col1:
            quip_token = st.text_input(
                _get_text(T, "run_tab.quip_token_label") or "Quip Access Token",
                value=defaults.get("quip_token", ""), type="password",
                help=_get_text(T, "run_tab.quip_token_help") or "从 Quip 获取，用于拉取需求文档",
                key="settings_quip_token",
            )
        with col2:
            gemini_key = st.text_input(
                _get_text(T, "run_tab.gemini_key_label") or "Gemini API Key",
                value=defaults.get("gemini_key", ""), type="password",
                help=_get_text(T, "run_tab.gemini_key_help") or "用于驱动四个 Agent 生成用例",
                key="settings_gemini_key",
            )
        gemini_models_list, default_model = _load_models()
        _model_opts = [m[0] for m in gemini_models_list]
        _model_idx = next((i for i, (k, _) in enumerate(gemini_models_list) if k == (defaults.get("gemini_model") or default_model)), 0)
        _model_col, _quota_col = st.columns([3, 1])
        with _model_col:
            gemini_model = st.selectbox(
                _get_text(T, "run_tab.gemini_model_label") or "Gemini 模型",
                options=_model_opts,
                index=_model_idx,
                format_func=lambda x: dict(gemini_models_list).get(x, x),
                help=_get_text(T, "run_tab.gemini_model_help") or "免费推荐：2.5 Flash-Lite；高质量：2.5 Flash。",
                key="settings_gemini_model",
            )
        with _quota_col:
            _quota_url = _get_text(T, "run_tab.gemini_quota_url") or "https://aistudio.google.com/rate-limit"
            st.link_button(
                _get_text(T, "run_tab.gemini_quota_btn") or "查看剩余额度",
                _quota_url,
                help=_get_text(T, "run_tab.gemini_quota_help") or "在 Google AI Studio 查看用量与限额（新开页）",
            )
        if st.button(_get_text(T, "run_tab.save_defaults_btn") or "保存到本地（下次无需再填）", type="primary", key="settings_save_defaults", help=_get_text(T, "run_tab.save_defaults_help") or "仅限本机；共享电脑建议用环境变量"):
            mode = _save_defaults(quip_token or "", gemini_key or "", gemini_model)
            st.success((_get_text(T, "run_tab.save_success") or "已保存到本地") + f"（{mode}）")
            st.rerun()


def main():
    """入口：直接进入主应用。"""
    T = _load_ui_texts()
    page_title = _get_text(T, "app.page_title") or "用例工坊 · AI 测试协作平台"
    st.set_page_config(page_title=page_title, layout="wide", initial_sidebar_state="expanded")
    _render_main_app(T)


if __name__ == "__main__":
    main()
