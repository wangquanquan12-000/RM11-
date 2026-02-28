# -*- coding: utf-8 -*-
"""
项目记忆存储：结构化记录、可搜索、支持「最新需求逻辑」检索
"""
import sqlite3
import os
from datetime import datetime
from typing import Any

CONFIG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config")
MEMORY_DB_PATH = os.path.join(CONFIG_DIR, "memory.db")


def _get_conn():
    os.makedirs(CONFIG_DIR, exist_ok=True)
    conn = sqlite3.connect(MEMORY_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _ensure_tables(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS memory_entries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            source_type TEXT NOT NULL,
            source_id TEXT,
            title TEXT,
            content TEXT NOT NULL,
            summary TEXT
        )
    """)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_memory_created ON memory_entries(created_at DESC)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_memory_source ON memory_entries(source_type)"
    )
    conn.commit()


def add_entry(
    source_type: str,
    content: str,
    source_id: str = "",
    title: str = "",
    summary: str = "",
) -> int:
    """添加一条记忆。source_type: manual | quip_single | quip_folder | run_summary"""
    conn = _get_conn()
    _ensure_tables(conn)
    now = datetime.now().isoformat()
    cur = conn.execute(
        "INSERT INTO memory_entries (created_at, source_type, source_id, title, content, summary) VALUES (?,?,?,?,?,?)",
        (now, source_type, source_id, title or "", content, summary or ""),
    )
    conn.commit()
    rowid = cur.lastrowid
    conn.close()
    return rowid or 0


def search(keyword: str, limit: int = 50) -> list[dict[str, Any]]:
    """按关键词搜索，返回按时间倒序的结果（最新的在前）"""
    if not keyword or not keyword.strip():
        return list_recent(limit=limit)
    conn = _get_conn()
    _ensure_tables(conn)
    kw = f"%{keyword.strip()}%"
    rows = conn.execute(
        """SELECT id, created_at, source_type, source_id, title, content, summary
           FROM memory_entries
           WHERE content LIKE ? OR summary LIKE ? OR title LIKE ?
           ORDER BY created_at DESC
           LIMIT ?""",
        (kw, kw, kw, limit),
    ).fetchall()
    conn.close()
    return [_row_to_dict(r) for r in rows]


def list_recent(limit: int = 50) -> list[dict[str, Any]]:
    """按时间倒序列出最近记录"""
    conn = _get_conn()
    _ensure_tables(conn)
    rows = conn.execute(
        """SELECT id, created_at, source_type, source_id, title, content, summary
           FROM memory_entries
           ORDER BY created_at DESC
           LIMIT ?""",
        (limit,),
    ).fetchall()
    conn.close()
    return [_row_to_dict(r) for r in rows]


def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "created_at": row["created_at"],
        "source_type": row["source_type"],
        "source_id": row["source_id"],
        "title": row["title"],
        "content": row["content"],
        "summary": row["summary"],
    }


def get_recent_for_agent(limit: int = 10, max_content_len: int = 3000) -> str:
    """获取最近 N 条记录，格式化为 Agent 上下文字符串"""
    entries = list_recent(limit=limit)
    if not entries:
        return ""
    parts = []
    for e in entries:
        title = e.get("title") or f"[{e.get('source_type')}]"
        summary = (e.get("summary") or e.get("content", "")[:500]).strip()
        if len(summary) > max_content_len // limit:
            summary = summary[: max_content_len // limit] + "..."
        parts.append(f"【{title}】{e.get('created_at', '')}\n{summary}")
    return "\n\n---\n\n".join(parts)
