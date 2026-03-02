# -*- coding: utf-8 -*-
"""
项目记忆存储：干净的需求文档历史，供 Agent 与用户查阅
- 需求文档: quip_folder, quip_single（Agent 主要使用）
- 运行产出: run_summary（可选供 Agent）
"""
import sqlite3
import os
from datetime import datetime
from typing import Any

CONFIG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config")
MEMORY_DB_PATH = os.path.join(CONFIG_DIR, "memory.db")

# 视为「需求文档」的 source_type，供 Agent 使用
DEMAND_SOURCE_TYPES = ("quip_folder", "quip_single")
# 测试用例：导入后供 Agent 理解项目既有用例
TEST_CASES_SOURCE_TYPE = "test_cases"


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
    for col in ("agent_summary", "agent_summary_status"):
        try:
            conn.execute(f"ALTER TABLE memory_entries ADD COLUMN {col} TEXT")
            conn.commit()
        except sqlite3.OperationalError:
            pass  # 列已存在
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
    """添加或更新记忆。相同 source_type+source_id 时更新，避免重复。
    source_type: manual | quip_single | quip_folder | run_summary"""
    conn = _get_conn()
    _ensure_tables(conn)
    now = datetime.now().isoformat()
    sid = (source_id or "").strip()
    # 有 source_id 时尝试 upsert（唯一索引可能不存在于旧库，先尝试）
    if sid:
        existing = conn.execute(
            "SELECT id FROM memory_entries WHERE source_type = ? AND source_id = ?",
            (source_type, sid),
        ).fetchone()
        if existing:
            conn.execute(
                """UPDATE memory_entries SET created_at=?, title=?, content=?, summary=?,
                   agent_summary='', agent_summary_status='pending'
                   WHERE source_type=? AND source_id=?""",
                (now, title or "", content, summary or "", source_type, sid),
            )
            conn.commit()
            rowid = existing["id"]
            conn.close()
            return rowid
    cur = conn.execute(
        "INSERT INTO memory_entries (created_at, source_type, source_id, title, content, summary) VALUES (?,?,?,?,?,?)",
        (now, source_type, sid, title or "", content, summary or ""),
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


def delete_entry(entry_id: int) -> bool:
    """删除指定 id 的记忆条目。返回是否成功。"""
    conn = _get_conn()
    _ensure_tables(conn)
    cur = conn.execute("DELETE FROM memory_entries WHERE id = ?", (entry_id,))
    conn.commit()
    ok = cur.rowcount > 0
    conn.close()
    return ok


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
    d = dict(row)
    d.setdefault("agent_summary", "")
    d.setdefault("agent_summary_status", "pending")
    return d


def update_agent_summary(entry_id: int, summary: str, status: str) -> bool:
    """更新条目的 Agent 摘要。status: 'success' | 'failed'"""
    conn = _get_conn()
    _ensure_tables(conn)
    cur = conn.execute(
        "UPDATE memory_entries SET agent_summary=?, agent_summary_status=? WHERE id=?",
        (summary or "", status, entry_id),
    )
    conn.commit()
    ok = cur.rowcount > 0
    conn.close()
    return ok


def list_import_history(limit: int = 20) -> list[dict[str, Any]]:
    """导入历史：按时间倒序，含 agent_summary、agent_summary_status。"""
    conn = _get_conn()
    _ensure_tables(conn)
    try:
        rows = conn.execute(
            """SELECT id, created_at, source_type, source_id, title, content, summary,
                      COALESCE(agent_summary,'') as agent_summary,
                      COALESCE(agent_summary_status,'pending') as agent_summary_status
               FROM memory_entries
               ORDER BY created_at DESC LIMIT ?""",
            (limit,),
        ).fetchall()
    except sqlite3.OperationalError:
        rows = conn.execute(
            """SELECT id, created_at, source_type, source_id, title, content, summary
               FROM memory_entries ORDER BY created_at DESC LIMIT ?""",
            (limit,),
        ).fetchall()
    conn.close()
    return [_row_to_dict(r) for r in rows]


def get_recent_for_agent(
    limit: int = 10,
    max_content_len: int = 3000,
    demand_only: bool = True,
    include_test_cases: bool = False,
) -> str:
    """获取供 Agent 使用的需求文档上下文。
    demand_only=True 时只取需求文档（quip_folder, quip_single）。
    include_test_cases=True 时额外包含 test_cases 类型的全回归用例。"""
    conn = _get_conn()
    _ensure_tables(conn)
    if demand_only and not include_test_cases:
        types = DEMAND_SOURCE_TYPES
    elif include_test_cases:
        types = (*DEMAND_SOURCE_TYPES, TEST_CASES_SOURCE_TYPE)
    else:
        types = None
    if types:
        placeholders = ",".join(["?"] * len(types))
        rows = conn.execute(
            f"""SELECT id, created_at, source_type, source_id, title, content, summary
                FROM memory_entries
                WHERE source_type IN ({placeholders})
                ORDER BY created_at DESC
                LIMIT ?""",
            (*types, limit * 2),
        ).fetchall()
    else:
        rows = conn.execute(
            """SELECT id, created_at, source_type, source_id, title, content, summary
               FROM memory_entries ORDER BY created_at DESC LIMIT ?""",
            (limit * 2,),
        ).fetchall()
    conn.close()
    entries = [_row_to_dict(r) for r in rows]
    # 按 source_id 去重，保留最新
    seen: set[str] = set()
    unique: list[dict] = []
    for e in entries:
        sid = (e.get("source_id") or "").strip()
        key = f"{e.get('source_type')}:{sid}" if sid else f"_{e.get('id')}"
        if key not in seen:
            seen.add(key)
            unique.append(e)
        if len(unique) >= limit:
            break
    if not unique:
        return ""
    parts = []
    per_len = max(200, max_content_len // len(unique))
    for e in unique:
        title = (e.get("title") or "").strip() or f"[{e.get('source_type')}]"
        summary = (e.get("summary") or e.get("content", "")).strip()
        if len(summary) > per_len:
            summary = summary[:per_len] + "..."
        parts.append(f"【{title}】{e.get('created_at', '')}\n{summary}")
    return "\n\n---\n\n".join(parts)


def get_all_demands_full_for_chat(limit: int = 30, max_total_chars: int = 80000, include_test_cases: bool = True) -> str:
    """获取全部需求文档与测试用例的完整内容，供与 Agent 沟通时使用。
    include_test_cases=True 时包含已导入的全回归测试用例。"""
    conn = _get_conn()
    _ensure_tables(conn)
    types = (*DEMAND_SOURCE_TYPES, TEST_CASES_SOURCE_TYPE) if include_test_cases else DEMAND_SOURCE_TYPES
    placeholders = ",".join(["?"] * len(types))
    rows = conn.execute(
        f"""SELECT id, created_at, source_type, source_id, title, content, summary
            FROM memory_entries
            WHERE source_type IN ({placeholders})
            ORDER BY created_at DESC
            LIMIT ?""",
        (*types, limit * 2),
    ).fetchall()
    conn.close()
    entries = [_row_to_dict(r) for r in rows]
    seen: set[str] = set()
    unique: list[dict] = []
    for e in entries:
        sid = (e.get("source_id") or "").strip()
        key = f"{e.get('source_type')}:{sid}" if sid else f"_{e.get('id')}"
        if key not in seen:
            seen.add(key)
            unique.append(e)
        if len(unique) >= limit:
            break
    if not unique:
        return ""
    parts = []
    total = 0
    for e in unique:
        title = (e.get("title") or "").strip() or f"[{e.get('source_type')}]"
        content = (e.get("content") or e.get("summary") or "").strip()
        block = f"【{title}】{e.get('created_at', '')}\n\n{content}"
        if total + len(block) > max_total_chars:
            block = block[: max_total_chars - total - 20] + "\n...(已截断)"
        parts.append(block)
        total += len(block)
        if total >= max_total_chars:
            break
    return "\n\n---\n\n".join(parts)


def get_entry_content(source_type: str, source_id: str) -> str | None:
    """按 source_type + source_id 获取条目的 content。不存在则返回 None。"""
    conn = _get_conn()
    _ensure_tables(conn)
    row = conn.execute(
        "SELECT content FROM memory_entries WHERE source_type = ? AND source_id = ?",
        (source_type, source_id),
    ).fetchone()
    conn.close()
    return row["content"] if row else None


def list_for_browse(
    source_type_filter: str = "",
    limit: int = 50,
) -> list[dict[str, Any]]:
    """供用户浏览：按时间倒序，可选按类型筛选。source_type_filter 为空则全部。"""
    conn = _get_conn()
    _ensure_tables(conn)
    if source_type_filter and source_type_filter.strip():
        rows = conn.execute(
            """SELECT id, created_at, source_type, source_id, title, content, summary
               FROM memory_entries WHERE source_type = ? ORDER BY created_at DESC LIMIT ?""",
            (source_type_filter.strip(), limit),
        ).fetchall()
    else:
        rows = conn.execute(
            """SELECT id, created_at, source_type, source_id, title, content, summary
               FROM memory_entries ORDER BY created_at DESC LIMIT ?""",
            (limit,),
        ).fetchall()
    conn.close()
    return [_row_to_dict(r) for r in rows]
