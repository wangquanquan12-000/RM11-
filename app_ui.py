# -*- coding: utf-8 -*-
"""
可视化界面：Quip 文档链接 → 四 Agent 流水线 → 表格链接
- 支持默认填入 Quip Token、Gemini API Key
- 显示 Agent 沟通过程（步骤输出）
- 生成可打开的表格链接（Excel 下载、Quip 文档、Google 表格）
- 编辑四个 Agent 定义并可扩展
- 项目记忆：Agent 可据此保持对项目的熟悉，支持从本次运行更新
"""
import os
import sys

import streamlit as st

# 将项目根目录加入 path，以便导入 crew_test
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from crew_test import (
    AGENTS_CONFIG_PATH,
    PROJECT_MEMORY_PATH,
    load_agents_config,
    load_demand_from_quip,
    load_demands_from_quip_folder,
    load_project_memory,
    run_pipeline,
    update_project_memory,
)
from memory_store import add_entry, search, list_recent

CONFIG_DIR = os.path.dirname(AGENTS_CONFIG_PATH)
DEFAULTS_PATH = os.path.join(CONFIG_DIR, "defaults.json")
OUTPUT_DIR = "output"


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


def main():
    st.set_page_config(page_title="需求 → 测试用例流水线", layout="wide")
    st.title("需求 → 测试用例流水线")
    defaults = _load_defaults()

    tab_run, tab_agents, tab_memory = st.tabs(["运行流水线", "编辑 Agent", "项目记忆"])

    # ---------- 运行流水线 ----------
    with tab_run:
        st.subheader("输入与配置")
        quip_url = st.text_input("Quip 文档链接或 thread_id", placeholder="https://quip.com/xxx 或 thread_id")
        col1, col2 = st.columns(2)
        with col1:
            quip_token = st.text_input("Quip Access Token", value=defaults["quip_token"], type="password", help="可从 https://quip.com/dev/token 生成")
        with col2:
            gemini_key = st.text_input("Gemini API Key", value=defaults["gemini_key"], type="password", help="用于驱动四个 Agent")
        if st.button("保存为默认 Token/Key（仅写本地 config/defaults.json）"):
            _save_defaults(quip_token or defaults["quip_token"], gemini_key or defaults["gemini_key"])
            st.success("已保存到本地默认值")
            st.rerun()

        export_quip = st.checkbox("导出到 Quip 新文档", value=False)
        export_sheets = st.checkbox("导出到 Google 表格", value=False)

        if st.button("运行流水线", type="primary"):
            if not quip_url or not quip_url.strip():
                st.error("请填写 Quip 文档链接或 thread_id")
            else:
                os.environ["QUIP_ACCESS_TOKEN"] = quip_token or os.environ.get("QUIP_ACCESS_TOKEN", "")
                os.environ["GEMINI_API_KEY"] = gemini_key or os.environ.get("GEMINI_API_KEY", "")
                if not os.environ.get("GEMINI_API_KEY"):
                    st.error("请填写 Gemini API Key 或保存默认值")
                else:
                    with st.spinner("正在从 Quip 拉取需求并运行四 Agent…"):
                        try:
                            demand = load_demand_from_quip(quip_url.strip())
                        except Exception as e:
                            st.error(f"拉取 Quip 文档失败: {e}")
                            demand = None
                        if demand:
                            try:
                                out = run_pipeline(
                                    demand,
                                    output_dir=OUTPUT_DIR,
                                    export_excel=True,
                                    export_quip=export_quip,
                                    export_sheets=export_sheets,
                                    return_details=True,
                                )
                            except Exception as e:
                                st.error(f"流水线执行失败: {e}")
                                raise
                            if isinstance(out, dict):
                                st.session_state["last_run"] = out
                                st.session_state["last_demand_snippet"] = demand[:500] + ("..." if len(demand) > 500 else "")
                            else:
                                st.session_state["last_run"] = {"result_str": out, "step_outputs": [], "excel_path": None, "quip_url": None, "sheets_url": None, "timestamp": "", "txt_path": ""}
                                st.session_state["last_demand_snippet"] = demand[:500] + ("..." if len(demand) > 500 else "")
                            st.success("流水线执行完成")

        if st.session_state.get("last_run"):
            r = st.session_state["last_run"]
            st.subheader("Agent 沟通过程")
            step_outputs = r.get("step_outputs") or []
            if step_outputs:
                for i, step in enumerate(step_outputs, 1):
                    with st.expander(f"步骤 {i}: {step.get('task', '')} — {step.get('agent', '')}", expanded=(i == len(step_outputs))):
                        st.markdown(step.get("content", ""))
            else:
                st.info("本次未采集到分步输出（可能未使用 stream），下方为最终结果。")

            st.subheader("最终结果")
            st.markdown(r.get("result_str", ""))

            st.subheader("表格链接")
            excel_path = r.get("excel_path")
            quip_link = r.get("quip_url")
            sheets_link = r.get("sheets_url")
            txt_path = r.get("txt_path", "")
            if excel_path and os.path.isfile(excel_path):
                with open(excel_path, "rb") as f:
                    st.download_button("下载 Excel", f, file_name=os.path.basename(excel_path), mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
                st.caption(f"本地路径: `{excel_path}`")
            else:
                st.caption("未生成 Excel 或文件不存在")
            if quip_link:
                st.markdown(f"**Quip 文档**: [打开链接]({quip_link})")
            if sheets_link:
                st.markdown(f"**Google 表格**: [打开链接]({sheets_link})")
            if txt_path and os.path.isfile(txt_path):
                st.caption(f"完整结果已保存: `{txt_path}`")

    # ---------- 编辑 Agent ----------
    with tab_agents:
        st.subheader("编辑四 Agent 定义与 Task")
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
        st.subheader("项目记忆（可搜索，供 Agent 保持对项目的熟悉）")

        # 搜索与浏览
        st.caption("记录文档更新与需求逻辑；支持关键词搜索，按时间倒序展示最新内容。")
        kw = st.text_input("搜索项目记忆", placeholder="输入关键词检索需求逻辑（如：直播分辨率、禁言、AB test）", key="mem_search")
        entries = search(kw, limit=30) if kw and kw.strip() else list_recent(limit=30)
        if entries:
            base = "https://quip.com"
            for e in entries:
                label = f"【{e.get('source_type', '')}】{e.get('title', '') or e.get('source_id', '')} — {e.get('created_at', '')}"
                with st.expander(label, expanded=False):
                    content = e.get("content", "") or e.get("summary", "")
                    sid = e.get("source_id", "")
                    src = f"{base}/{sid}" if sid and len(sid) >= 10 else sid
                    st.caption(f"来源: {src}")
                    st.markdown(content[:2000] + ("..." if len(content) > 2000 else ""))
        else:
            st.info("暂无记录。可通过下方「从 Quip 文件夹导入」或「从本次运行更新」添加。")

        st.divider()
        st.subheader("导入历史需求")
        quip_for_import = st.text_input("Quip Token（导入时使用，可与运行流水线共用）", value=defaults["quip_token"], type="password", key="quip_token_import")

        # 从 Quip 文件夹批量导入
        folder_url = st.text_input("Quip 文件夹链接或 folder_id", placeholder="https://quip.com/XXXXX/文件夹名 或 12 字符 folder_id", key="quip_folder")
        if st.button("从 Quip 文件夹批量导入"):
            if not folder_url or not folder_url.strip():
                st.error("请填写 Quip 文件夹链接或 ID")
            else:
                os.environ["QUIP_ACCESS_TOKEN"] = quip_for_import or os.getenv("QUIP_ACCESS_TOKEN", "")
                if not os.environ.get("QUIP_ACCESS_TOKEN"):
                    st.warning("请先在「运行流水线」页保存 Quip Token，或在环境变量中设置 QUIP_ACCESS_TOKEN")
                else:
                    with st.spinner("正在拉取文件夹内所有文档…"):
                        try:
                            docs = load_demands_from_quip_folder(folder_url.strip())
                            for d in docs:
                                add_entry("quip_folder", d["content"], source_id=d["thread_id"], title=d["title"], summary=d["content"][:500])
                            st.success(f"已导入 {len(docs)} 条需求文档，可在上方搜索查看。")
                        except Exception as ex:
                            st.error(f"导入失败: {ex}")

        # 从 Quip 单文档导入（补充：若用户只想导入单文档）
        single_url = st.text_input("或导入单个 Quip 文档", placeholder="https://quip.com/xxx（可选）", key="quip_single")
        if st.button("从单文档导入"):
            if single_url and single_url.strip():
                try:
                    content = load_demand_from_quip(single_url.strip())
                    add_entry("quip_single", content, source_id=single_url.strip(), title="", summary=content[:500])
                    st.success("已导入，可在上方搜索查看。")
                except Exception as ex:
                    st.error(str(ex))

        st.divider()
        st.subheader("项目记忆摘要（手动编辑，注入 Agent 上下文）")
        mem = load_project_memory()
        new_mem = st.text_area("项目记忆内容", value=mem, height=200, key="project_memory_text")
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


if __name__ == "__main__":
    main()
