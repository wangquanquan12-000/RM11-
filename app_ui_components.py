# -*- coding: utf-8 -*-
"""
公用 UI 组件：供工作台各模块复用，符合《高扩展性 UI 架构规范》2.4
- 进度/状态：Agent 执行、批量导入等
- 文件上传器：类型/大小限制，统一返回结构
- 日志/终端：步骤或日志行列表，可折叠、可复制
"""
import streamlit as st
from typing import Callable


def render_progress_status(
    current: int,
    total: int,
    message: str = "",
    key: str = "progress_status",
) -> None:
    """
    进度/状态组件：展示当前步/总步与状态文案。
    供「生成用例」运行中、「项目记忆」批量导入等复用。
    """
    if total > 0:
        st.progress(min(1.0, current / total), key=key)
    if message:
        st.caption(message[:120] + ("…" if len(message) > 120 else ""))


def render_file_uploader(
    accepted_types: list[str] | None = None,
    max_size_mb: int = 10,
    key: str = "file_upload",
    label: str = "上传文件",
) -> dict | None:
    """
    文件上传组件：类型与大小限制，返回统一结构 { path, name, size } 或 None。
    注意：Streamlit file_uploader 返回 UploadedFile，无 path；返回 { name, size, file } 供调用方读内容。
    """
    if accepted_types is None:
        accepted_types = ["xlsx", "xls", "csv", "txt"]
    f = st.file_uploader(
        label,
        type=accepted_types,
        key=key,
        label_visibility="collapsed" if label == "上传文件" else "visible",
    )
    if f is None:
        return None
    size_mb = (f.size or 0) / (1024 * 1024)
    if max_size_mb and size_mb > max_size_mb:
        st.warning(f"文件超过 {max_size_mb}MB 限制，请缩小后重试。")
        return None
    return {"name": f.name, "size": f.size or 0, "file": f}


def render_log_terminal(
    lines: list[dict] | list[str],
    title: str = "日志",
    expanded: bool = False,
    key: str = "log_terminal",
) -> None:
    """
    日志/终端组件：接收步骤列表或字符串行列表，可折叠展示。
    lines: 若为 dict 列表，每项需含 content 或 content 键；若为 str 列表则直接展示。
    供「查看 Agent 沟通过程」及后续模块复用。
    """
    # Streamlit 新版本的 st.expander 不再支持 key 参数，这里仅使用标题区分
    with st.expander(title, expanded=expanded):
        if not lines:
            st.info("暂无输出。")
            return
        for i, item in enumerate(lines):
            if isinstance(item, dict):
                step_title = item.get("task", "") or item.get("agent", "") or f"步骤 {i + 1}"
                content = item.get("content", "")
                with st.expander(f"{i + 1}. {step_title}", expanded=False):
                    st.markdown(content or "")
            else:
                st.text(item)
