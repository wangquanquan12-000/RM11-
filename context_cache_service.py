# -*- coding: utf-8 -*-
"""
Gemini Context Cache 服务：管理缓存创建、脏标记与元数据。
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timedelta

CONFIG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config")
CONTEXT_CACHE_META_PATH = os.path.join(CONFIG_DIR, "context_cache_meta.json")
DEFAULT_TTL_SECONDS = 86400


def _read_meta() -> dict:
    if not os.path.isfile(CONTEXT_CACHE_META_PATH):
        return {}
    try:
        with open(CONTEXT_CACHE_META_PATH, "r", encoding="utf-8") as f:
            return json.load(f) or {}
    except Exception:
        return {}


def _write_meta(data: dict) -> None:
    os.makedirs(CONFIG_DIR, exist_ok=True)
    with open(CONTEXT_CACHE_META_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def mark_context_cache_dirty(reason: str = "") -> None:
    meta = _read_meta()
    meta["dirty"] = True
    meta["dirty_reason"] = reason or meta.get("dirty_reason", "")
    meta["dirty_at"] = datetime.now().isoformat()
    _write_meta(meta)


def get_cached_content_name() -> str:
    return str(_read_meta().get("cache_name") or "")


def is_context_cache_dirty() -> bool:
    meta = _read_meta()
    if meta.get("dirty", False):
        return True
    updated_at = str(meta.get("updated_at") or "").strip()
    if not updated_at:
        return True
    try:
        dt = datetime.fromisoformat(updated_at)
        return datetime.now() - dt >= timedelta(seconds=int(meta.get("ttl_seconds") or DEFAULT_TTL_SECONDS))
    except Exception:
        return True


def refresh_context_cache_if_needed(
    project_context: str,
    gemini_key: str,
    gemini_model: str,
    force: bool = False,
) -> str:
    """若缓存脏/过期则刷新，返回可用 cache_name；失败返回空串。"""
    if not (project_context or "").strip():
        return ""
    if not (gemini_key or "").strip():
        return ""

    meta = _read_meta()
    cache_name = str(meta.get("cache_name") or "")
    if cache_name and not force and not is_context_cache_dirty():
        return cache_name

    try:
        from google import genai
        from google.genai import types
    except Exception:
        return ""

    try:
        client = genai.Client(api_key=gemini_key)
        # 在创建新缓存前，尽量删除旧缓存，避免长时间堆积。
        old_name = cache_name
        if old_name:
            try:
                client.caches.delete(name=old_name)
            except Exception:
                # 删除失败不影响后续创建新缓存
                pass
        cache = client.caches.create(
            model=gemini_model or "gemini-2.5-flash-lite",
            config=types.CreateCachedContentConfig(
                display_name="project_memory_context",
                contents=[project_context[:120000]],
                ttl=f"{DEFAULT_TTL_SECONDS}s",
            ),
        )
        new_name = str(getattr(cache, "name", "") or "")
        if not new_name:
            return ""
        meta.update(
            {
                "cache_name": new_name,
                "updated_at": datetime.now().isoformat(),
                "ttl_seconds": DEFAULT_TTL_SECONDS,
                "dirty": False,
                "dirty_reason": "",
                "dirty_at": "",
            }
        )
        _write_meta(meta)
        return new_name
    except Exception:
        return ""
