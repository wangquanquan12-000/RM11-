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
    """按关键词搜索，按相关性排序（匹配词越多越靠前），其次按时间倒序。"""
    if not keyword or not keyword.strip():
        return list_recent(limit=limit)
    conn = _get_conn()
    _ensure_tables(conn)
    kw = keyword.strip()
    # 多词：按空白切分，每个词都要匹配（AND），按匹配词数排序
    terms = [t.strip() for t in kw.split() if t.strip()]
    if not terms:
        return list_recent(limit=limit)
    where_clause = " AND ".join(
        [f"(content LIKE ? OR summary LIKE ? OR title LIKE ?)" for _ in terms]
    )
    args_where = []
    for t in terms:
        p = f"%{t}%"
        args_where.extend([p, p, p])
    # 先取更多候选，再在 Python 中按相关性打分排序
    rows = conn.execute(
        f"""SELECT id, created_at, source_type, source_id, title, content, summary
            FROM memory_entries
            WHERE {where_clause}
            ORDER BY created_at DESC
            LIMIT ?""",
        (*args_where, limit * 3),
    ).fetchall()
    conn.close()
    entries = [_row_to_dict(r) for r in rows]
    if not entries:
        return []
    # 相关性：匹配到的词数越多、越靠前
    def score(e):
        text = f"{e.get('title','')} {e.get('summary','')} {e.get('content','')}"
        return sum(1 for t in terms if t in text)
    entries.sort(key=lambda e: (score(e), e.get("created_at", "")), reverse=True)
    return entries[:limit]


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
