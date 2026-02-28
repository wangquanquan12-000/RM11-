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
    chat_with_document_agent,
    get_project_context_for_agent,
    is_product_requirement_doc,
    load_agents_config,
    load_demand_from_quip,
    load_demands_from_quip_folder,
    load_project_memory,
    run_pipeline,
    update_project_memory,
)
from memory_store import add_entry, delete_entry, search, list_recent

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


def _load_defaults():
    """从环境变量或 config/defaults.json 读取默认 Token / API Key。"""
    import json
    out = {"quip_token": "", "gemini_key": ""}
    out["quip_token"] = os.getenv("QUIP_ACCESS_TOKEN", "")
    out["gemini_key"] = os.getenv("GEMINI_API_KEY", "")
    if os.path.isfile(DEFAULTS_PATH):
        try:
            with open(DEFAULTS_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
                out["quip_token"] = out["quip_token"] or data.get("quip_token", "")
                out["gemini_key"] = out["gemini_key"] or data.get("gemini_key", "")
        except Exception:
            pass
    return out


def _save_defaults(quip_token: str, gemini_key: str):
    """将默认 Token / Key 写入 config/defaults.json（本地仅自己使用）。"""
    import json
    os.makedirs(CONFIG_DIR, exist_ok=True)
    with open(DEFAULTS_PATH, "w", encoding="utf-8") as f:
        json.dump({"quip_token": quip_token, "gemini_key": gemini_key}, f, ensure_ascii=False, indent=2)


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
    /* 优化 UI：简洁专业 */
    .main .block-container { padding-top: 1.2rem; padding-bottom: 2.5rem; max-width: 900px; }
    h1 {
        font-size: 1.5rem !important; font-weight: 600 !important;
        color: #0f172a !important; margin-bottom: 0.8rem !important;
        letter-spacing: -0.02em; line-height: 1.3;
    }
    h2 {
        font-size: 1.05rem !important; font-weight: 500 !important;
        color: #475569 !important; margin-top: 1.2rem !important; margin-bottom: 0.6rem !important;
    }
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
    [data-testid="stMetricValue"] { font-weight: 600; }
    .stTextInput > div > div { border-radius: 8px; }
    .stSuccess, .stInfo, .stWarning, .stError {
        border-radius: 8px; padding: 0.75rem 1rem;
    }
    p { line-height: 1.6; }
    /* 项目记忆：搜索区与结果卡片 */
    div[data-testid="stExpander"] summary {
        font-size: 0.9rem; padding: 0.6rem 0.75rem;
    }
    .stSelectbox > div { border-radius: 8px; }
    /* 信息提示框更柔和 */
    [data-testid="stAlert"] { border-radius: 8px; }
    /* 分隔线 */
    hr { margin: 1.5rem 0; border-color: #e2e8f0; opacity: 0.8; }
    /* 隐藏 Streamlit 默认装饰 */
    #MainMenu { visibility: hidden; }
    footer { visibility: hidden; }
    header { visibility: hidden; }
    </style>
    """, unsafe_allow_html=True)
    st.title(app_title)
    defaults = _load_defaults()
    tab_run, tab_agents, tab_memory, tab_chat = st.tabs([
        _get_text(T, "tabs.run") or "运行流水线",
        _get_text(T, "tabs.agents") or "编辑 Agent",
        _get_text(T, "tabs.memory") or "项目记忆",
        _get_text(T, "tabs.chat") or "与文档 Agent 沟通",
    ])

    # ---------- 运行流水线 ----------
    with tab_run:
        st.subheader(_get_text(T, "run_tab.section_config") or "输入与配置")
        quip_url = st.text_input(
            _get_text(T, "run_tab.quip_url_label") or "Quip 文档链接或 thread_id",
            placeholder=_get_text(T, "run_tab.quip_url_placeholder") or "https://quip.com/xxx 或 thread_id",
        )
        col1, col2 = st.columns(2)
        with col1:
            quip_token = st.text_input(
                _get_text(T, "run_tab.quip_token_label") or "Quip Access Token",
                value=defaults["quip_token"], type="password",
                help=_get_text(T, "run_tab.quip_token_help") or "可从 https://quip.com/dev/token 生成",
            )
        with col2:
            gemini_key = st.text_input(
                _get_text(T, "run_tab.gemini_key_label") or "Gemini API Key",
                value=defaults["gemini_key"], type="password",
                help=_get_text(T, "run_tab.gemini_key_help") or "用于驱动四个 Agent",
            )
        if st.button(_get_text(T, "run_tab.save_defaults_btn_full") or "保存为默认 Token/Key（仅写本地 config/defaults.json）"):
            _save_defaults(quip_token or defaults["quip_token"], gemini_key or defaults["gemini_key"])
            st.success(_get_text(T, "run_tab.save_success") or "已保存到本地默认值")
            st.rerun()

        export_quip = st.checkbox(_get_text(T, "run_tab.export_quip") or "导出到 Quip", value=False)
        export_quip_target = st.text_input(
            _get_text(T, "run_tab.export_quip_target_label") or "导出目标文档链接（可选，填写则追加到该文档，并自动写入需求标题+用例）",
            placeholder=_get_text(T, "run_tab.export_quip_target_placeholder") or "https://quip.com/xxx 留空则新建文档",
            key="export_quip_target",
        )
        export_sheets = st.checkbox(_get_text(T, "run_tab.export_sheets") or "导出到 Google 表格", value=False)

        if st.button(_get_text(T, "run_tab.run_btn") or "运行流水线", type="primary"):
            if not quip_url or not quip_url.strip():
                st.error(_get_text(T, "run_tab.quip_url_required") or "请填写 Quip 文档链接或 thread_id")
            else:
                os.environ["QUIP_ACCESS_TOKEN"] = quip_token or os.environ.get("QUIP_ACCESS_TOKEN", "")
                os.environ["GEMINI_API_KEY"] = gemini_key or os.environ.get("GEMINI_API_KEY", "")
                if not os.environ.get("GEMINI_API_KEY"):
                    st.error(_get_text(T, "run_tab.gemini_required") or "请填写 Gemini API Key 或保存默认值")
                else:
                    with st.spinner(_get_text(T, "run_tab.run_spinner") or "正在从 Quip 拉取需求并运行四 Agent…"):
                        try:
                            demand, demand_title = load_demand_from_quip(quip_url.strip(), return_title=True)
                        except Exception as e:
                            st.error(f"{_get_text(T, 'run_tab.quip_fetch_fail') or '拉取 Quip 文档失败'}: {e}")
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
                                st.error(f"{_get_text(T, 'run_tab.pipeline_fail') or '流水线执行失败'}: {e}")
                                raise
                            if isinstance(out, dict):
                                st.session_state["last_run"] = out
                                st.session_state["last_demand_snippet"] = demand[:500] + ("..." if len(demand) > 500 else "")
                                st.session_state["last_demand_full"] = demand
                            else:
                                st.session_state["last_run"] = {"result_str": out, "step_outputs": [], "excel_path": None, "quip_url": None, "sheets_url": None, "timestamp": "", "txt_path": ""}
                                st.session_state["last_demand_snippet"] = demand[:500] + ("..." if len(demand) > 500 else "")
                                st.session_state["last_demand_full"] = demand
                            st.success(_get_text(T, "run_tab.run_success") or "流水线执行完成")

        if st.session_state.get("last_run"):
            r = st.session_state["last_run"]
            st.subheader(_get_text(T, "run_tab.section_steps") or "Agent 沟通过程")
            step_outputs = r.get("step_outputs") or []
            if step_outputs:
                for i, step in enumerate(step_outputs, 1):
                    with st.expander(f"步骤 {i}: {step.get('task', '')} — {step.get('agent', '')}", expanded=(i == len(step_outputs))):
                        st.markdown(step.get("content", ""))
            else:
                st.info(_get_text(T, "run_tab.no_step_output") or "本次未采集到分步输出（可能未使用 stream），下方为最终结果。")

            st.subheader(_get_text(T, "run_tab.section_result") or "最终结果")
            st.markdown(r.get("result_str", ""))

            st.subheader(_get_text(T, "run_tab.section_links") or "表格链接")
            excel_path = r.get("excel_path")
            quip_link = r.get("quip_url")
            sheets_link = r.get("sheets_url")
            txt_path = r.get("txt_path", "")
            if excel_path and os.path.isfile(excel_path):
                with open(excel_path, "rb") as f:
                    st.download_button(
                        _get_text(T, "run_tab.download_excel") or "下载 Excel",
                        f, file_name=os.path.basename(excel_path),
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    )
                st.caption(f"{_get_text(T, 'run_tab.excel_path_label') or '本地路径'}: `{excel_path}`")
            else:
                st.caption(_get_text(T, "run_tab.excel_not_found") or "未生成 Excel 或文件不存在")
            if quip_link:
                st.markdown(f"**{_get_text(T, 'run_tab.quip_doc_label') or 'Quip 文档'}**: [打开链接]({quip_link})")
            if sheets_link:
                st.markdown(f"**{_get_text(T, 'run_tab.google_sheets_label') or 'Google 表格'}**: [打开链接]({sheets_link})")
            if txt_path and os.path.isfile(txt_path):
                st.caption(f"{_get_text(T, 'run_tab.result_saved') or '完整结果已保存'}: `{txt_path}`")

    # ---------- 编辑 Agent ----------
    with tab_agents:
        st.subheader(_get_text(T, "agents_tab.section_title") or "编辑四 Agent 定义与 Task")
        config = load_agents_config()
        if not config:
            st.warning("未找到 config/agents.yaml 或 PyYAML 未安装；可在此编辑并保存为新配置。")
            raw_yaml = st.text_area("agents.yaml 内容", height=400, placeholder="agents:\n  - id: ...\n    role: ...\n    goal: ...\n    backstory: |\n      ...")
            if st.button("保存 agents.yaml"):
                if raw_yaml.strip():
                    os.makedirs(CONFIG_DIR, exist_ok=True)
                    with open(AGENTS_CONFIG_PATH, "w", encoding="utf-8") as f:
                        f.write(raw_yaml.strip())
                    st.success("已保存")
                    st.rerun()
        else:
            agents = config.get("agents") or []
            tasks = config.get("tasks") or []
            for i, a in enumerate(agents):
                with st.expander(f"Agent: {a.get('role', a.get('id', ''))}", expanded=True):
                    a_id = st.text_input("id", value=a.get("id", ""), key=f"agent_id_{i}")
                    a_role = st.text_input("role", value=a.get("role", ""), key=f"agent_role_{i}")
                    a_goal = st.text_area("goal", value=a.get("goal", ""), key=f"agent_goal_{i}", height=100)
                    a_back = st.text_area("backstory", value=(a.get("backstory") or "").strip(), key=f"agent_back_{i}", height=200)
                    a["id"], a["role"], a["goal"], a["backstory"] = a_id, a_role, a_goal, a_back
            st.divider()
            for i, t in enumerate(tasks):
                with st.expander(f"Task: {t.get('id', '')} (agent: {t.get('agent_id', '')})", expanded=False):
                    t_id = st.text_input("id", value=t.get("id", ""), key=f"task_id_{i}")
                    t_agent_id = st.text_input("agent_id", value=t.get("agent_id", ""), key=f"task_agent_{i}")
                    t_desc = st.text_area("description", value=(t.get("description") or "").strip(), key=f"task_desc_{i}", height=120)
                    t_out = st.text_input("expected_output", value=t.get("expected_output", ""), key=f"task_out_{i}")
                    t["id"], t["agent_id"], t["description"], t["expected_output"] = t_id, t_agent_id, t_desc, t_out
            if st.button("保存到 config/agents.yaml"):
                try:
                    import yaml
                    with open(AGENTS_CONFIG_PATH, "w", encoding="utf-8") as f:
                        yaml.dump(config, f, allow_unicode=True, default_flow_style=False, sort_keys=False)
                    st.success("已保存，下次运行将使用新配置")
                except Exception as e:
                    st.error(str(e))

    # ---------- 项目记忆 ----------
    with tab_memory:
        st.subheader(_get_text(T, "memory_tab.section_title") or "项目记忆（可搜索，供 Agent 保持对项目的熟悉）")

        # 搜索（仅搜索后显示结果）
        st.caption(_get_text(T, "memory_tab.caption_browse") or "干净的需求文档历史。输入关键词搜索后显示匹配文档。")
        kw = st.text_input(
            _get_text(T, "memory_tab.search_label") or "搜索项目记忆",
            placeholder=_get_text(T, "memory_tab.search_placeholder") or "输入关键词检索",
            key="mem_search",
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
                        src = f"{base}/{sid}" if sid and len(sid) >= 10 else sid
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
        st.subheader(_get_text(T, "memory_tab.import_section") or "导入历史需求")
        quip_for_import = st.text_input(
            _get_text(T, "memory_tab.quip_token_import_label") or "Quip Token（导入时使用，可与运行流水线共用）",
            value=defaults["quip_token"], type="password", key="quip_token_import",
        )

        # 从 Quip 文件夹批量导入
        folder_url = st.text_input(
            _get_text(T, "memory_tab.folder_label") or "Quip 文件夹链接或 folder_id",
            placeholder=_get_text(T, "memory_tab.folder_placeholder") or "https://quip.com/XXXXX/文件夹名 或 12 字符 folder_id",
            key="quip_folder",
        )
        st.caption(_get_text(T, "memory_tab.filter_hint") or "拉取时会自动过滤测试用例、UI走查、进度汇总等非需求文档，仅导入 PRD。规则见 config/doc_filter.yaml")
        stable = _load_stable_quip_batch()
        with st.expander("分批拉取设置（降低 503 风险）", expanded=False):
            batch_size = st.number_input("每批文档数", min_value=1, max_value=50, value=int(stable["batch_size"]), help="遇 503 会自动降批；上次稳定值已预填")
            batch_pause = st.number_input("批间暂停秒数", min_value=0, max_value=300, value=int(stable["batch_pause"]), help="每批之间暂停，给 Quip API 恢复时间")
        if st.button("从 Quip 文件夹批量导入"):
            if not folder_url or not folder_url.strip():
                st.error("请填写 Quip 文件夹链接或 ID")
            else:
                os.environ["QUIP_ACCESS_TOKEN"] = quip_for_import or os.getenv("QUIP_ACCESS_TOKEN", "")
                if not os.environ.get("QUIP_ACCESS_TOKEN"):
                    st.warning("请先在「运行流水线」页保存 Quip Token，或在环境变量中设置 QUIP_ACCESS_TOKEN")
                else:
                    progress_bar = st.progress(0)
                    status_text = st.empty()
                    progress_info = {}
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
                            progress_info=progress_info,
                        )
                        for d in docs:
                            add_entry("quip_folder", d["content"], source_id=d["thread_id"], title=d["title"], summary=d["content"][:500])
                        progress_bar.progress(1.0)
                        status_text.caption("")
                        _save_stable_quip_batch(stats["stable_batch_size"], stats["stable_batch_pause"])
                        filtered = stats.get("filtered_count", 0)
                        msg = f"已导入 {len(docs)} 条需求文档"
                        if filtered > 0:
                            msg += f"，自动过滤 {filtered} 条非需求文档（测试用例/UI走查/进度汇总等）"
                        msg += "，可在上方搜索查看。"
                        if stats.get("batch_reduced"):
                            msg += f" 本次遇 503 已自动降批，稳定批次：每批 {stats['stable_batch_size']} 个，已保存供下次使用。"
                        else:
                            msg += f" 当前稳定批次：每批 {stats['stable_batch_size']} 个。"
                        st.success(msg)
                    except Exception as ex:
                        st.error(f"导入失败: {ex}")

        # 从 Quip 单文档导入（补充：若用户只想导入单文档）
        single_url = st.text_input(
            _get_text(T, "memory_tab.single_label") or "或导入单个 Quip 文档",
            placeholder=_get_text(T, "memory_tab.single_placeholder") or "https://quip.com/xxx（可选）",
            key="quip_single",
        )
        if st.button("从单文档导入"):
            if single_url and single_url.strip():
                try:
                    content, doc_title = load_demand_from_quip(single_url.strip(), return_title=True)
                    keep, reason = is_product_requirement_doc("", content)
                    if not keep:
                        st.warning(f"该文档被识别为非需求文档（{reason}），已跳过导入。若确为需求文档，可在 config/doc_filter.yaml 中调整过滤规则。")
                    else:
                        add_entry("quip_single", content, source_id=single_url.strip(), title=doc_title, summary=content[:500])
                        st.success("已导入，可在上方搜索查看。")
                except Exception as ex:
                    st.error(str(ex))

        st.divider()
        st.subheader(_get_text(T, "memory_tab.memory_summary_section") or "项目记忆摘要（手动编辑，注入 Agent 上下文）")
        mem = load_project_memory()
        new_mem = st.text_area(
            _get_text(T, "memory_tab.memory_text_label") or "项目记忆内容",
            value=mem, height=200, key="project_memory_text",
        )
        if st.button("保存项目记忆摘要"):
            os.makedirs(CONFIG_DIR, exist_ok=True)
            with open(PROJECT_MEMORY_PATH, "w", encoding="utf-8") as f:
                f.write(new_mem)
            st.success("已保存")

        if st.button("从本次运行更新（追加摘要到记忆库 + 摘要文件）"):
            if st.session_state.get("last_run") and st.session_state.get("last_demand_snippet"):
                snippet = st.session_state["last_demand_snippet"]
                result = st.session_state["last_run"].get("result_str", "")[:2000]
                addition = f"【最近一次需求摘要】\n{snippet}\n\n【产出摘要】\n{result}"
                update_project_memory(addition)
                add_entry("run_summary", result, title="最近一次运行", summary=snippet)
                st.success("已追加到项目记忆；Agent 下次运行将带上这些上下文。")
            else:
                st.info("请先运行一次流水线后再点击「从本次运行更新」。")

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
