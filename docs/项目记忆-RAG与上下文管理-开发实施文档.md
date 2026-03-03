# 项目记忆 · RAG 与上下文管理 - 开发实施文档

> **文档用途**：在现有 `memory_store.py`、`app_ui.py`、`crew_test.py` 架构上，落地 PRD 中的缓存机制、哈希校验与 Librarian Agent，供开发直接实施。
>
> **依赖**：`docs/项目记忆-RAG与上下文管理-PRD.md`

---

## 一、实施总览

| 阶段 | 内容 | 涉及文件 | 优先级 |
|------|------|----------|--------|
| **0** | **存储后端可插拔 + 惰性初始化（消除 sqlite3 硬依赖）** | **memory_store.py** | **P0 最高** |
| 1 | 哈希指纹与去重 | memory_store.py、app_ui.py | P0 |
| 2 | Metadata 层与历史记录表 | memory_store.py | P1 |
| 3 | Librarian Agent 总结 | memory_store.py、新增或复用 agent 调用 | P1 |
| 4 | Gemini Context Caching | crew_test.py、pipeline_service.py | P2 |
| 5 | UI 历史记录与总结展示 | app_ui.py、config/ui_texts.yaml | P1 |

---

## 一-A、阶段 0：存储后端可插拔 + 惰性初始化（P0）

> **目的**：彻底消除 `sqlite3` 硬依赖导致云端白屏的风险。详见 `docs/项目记忆-重新规划实施方案.md`。

### 0.1 重构 memory_store.py 结构

**之前**（崩溃结构）：
```python
import sqlite3          # ← 顶层，云端直接 ImportError
def _get_conn():
    conn = sqlite3.connect(...)  # ← 立即 IO
```

**之后**（安全结构）：
```python
import os, json, hashlib
from typing import Any
from datetime import datetime

_SQLITE_AVAILABLE = False
try:
    import sqlite3
    _SQLITE_AVAILABLE = True
except ImportError:
    pass

class SqliteBackend:
    """sqlite3 可用时使用，全功能。"""
    def __init__(self):
        self._conn = None           # 惰性：不在 __init__ 连接
        self._tables_ready = False

    def _get_conn(self):
        if self._conn is None:
            os.makedirs(CONFIG_DIR, exist_ok=True)
            self._conn = sqlite3.connect(MEMORY_DB_PATH)
            self._conn.row_factory = sqlite3.Row
        if not self._tables_ready:
            self._ensure_tables(self._conn)
            self._tables_ready = True
        return self._conn
    # ... 其余方法与现有实现一致，仅移入 class 内

class JsonFileBackend:
    """sqlite3 不可用时的 fallback，纯 JSON 文件读写。"""
    JSON_PATH = os.path.join(CONFIG_DIR, "memory_entries.json")

    def __init__(self):
        self._data = None  # 惰性

    def _load(self):
        if self._data is not None:
            return self._data
        if os.path.isfile(self.JSON_PATH):
            with open(self.JSON_PATH, "r", encoding="utf-8") as f:
                self._data = json.load(f)
        else:
            self._data = {"entries": [], "next_id": 1}
        return self._data

    def _save(self):
        os.makedirs(CONFIG_DIR, exist_ok=True)
        with open(self.JSON_PATH, "w", encoding="utf-8") as f:
            json.dump(self._data, f, ensure_ascii=False, indent=2)
    # ... 实现与 SqliteBackend 相同的接口方法

# 自动选择后端
if _SQLITE_AVAILABLE:
    _backend = SqliteBackend()
else:
    _backend = JsonFileBackend()

# 对外函数全部委托给 _backend
def add_entry(source_type, content, source_id="", title="", summary=""):
    return _backend.add_entry(source_type, content, source_id, title, summary)

def add_entry_with_dedup(source_type, content, source_id="", title="", summary=""):
    return _backend.add_entry_with_dedup(source_type, content, source_id, title, summary)
# ... 其余函数同理
```

### 0.2 JsonFileBackend 数据结构

`config/memory_entries.json`：
```json
{
  "entries": [
    {
      "id": 1,
      "created_at": "2026-03-03T14:00:00",
      "source_type": "manual",
      "source_id": "",
      "title": "直播分辨率ABtest",
      "content": "...",
      "summary": "",
      "content_hash": "abcd1234...",
      "agent_summary": "涵盖直播画质分流实验...",
      "agent_summary_status": "success"
    }
  ],
  "next_id": 2
}
```

### 0.3 关键验证（必须通过才能上线）

```bash
# 模拟 sqlite3 不可用
python -c "
import sys
# 屏蔽 sqlite3
sys.modules['sqlite3'] = None
import memory_store
print('SQLITE_AVAILABLE:', memory_store._SQLITE_AVAILABLE)
print('后端类型:', type(memory_store._backend).__name__)
# 测试基础操作
rid, status = memory_store.add_entry_with_dedup('manual', '测试内容', title='测试')
print(f'add_entry_with_dedup: id={rid}, status={status}')
results = memory_store.search('测试')
print(f'search: {len(results)} 条')
"
```

预期输出：
```
SQLITE_AVAILABLE: False
后端类型: JsonFileBackend
add_entry_with_dedup: id=1, status=added
search: 1 条
```

### 0.4 调用方无需改动

以下文件中的 import 已有保护，阶段 0 重构后它们完全不需要改动：

| 文件 | 保护方式 | 说明 |
|------|----------|------|
| `app_ui.py:34-50` | try-except → MEMORY_AVAILABLE | 保留作为最后防线 |
| `crew_test.py:852-858` | try-except → pass | Agent 上下文降级 |
| `agent_knowledge_service.py:23` | try-except → return "" | 知识库构建降级 |
| `app_ui.py:1468` | try-except | 文档问答降级 |

---

## 二、阶段 1：哈希指纹与去重

### 2.1 数据结构扩展

在 `memory_store.py` 中：

- **memory_entries 表**：新增列 `content_hash TEXT`，存储 SHA-256 哈希值。
- **memory_index 表（可选）**：若需快速按哈希查询，可建索引表：
  ```sql
  CREATE TABLE IF NOT EXISTS memory_index (
      content_hash TEXT PRIMARY KEY,
      entry_id INTEGER NOT NULL,
      file_name TEXT,
      created_at TEXT
  );
  ```

### 2.2 哈希计算与校验逻辑

```python
import hashlib

def _compute_content_hash(content: str) -> str:
    """计算内容的 SHA-256 哈希，用于去重。"""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()

def add_entry_with_dedup(
    source_type: str,
    content: str,
    source_id: str = "",
    title: str = "",
    summary: str = "",
) -> tuple[int, str]:
    """
    添加记忆，带哈希去重。
    返回 (rowid, status)。
    status: "added" | "updated" | "skipped"（重复时）
    """
    h = _compute_content_hash(content)
    existing = conn.execute(
        "SELECT id FROM memory_entries WHERE content_hash = ?", (h,)
    ).fetchone()
    if existing:
        return existing["id"], "skipped"
    # 否则执行原有 add_entry 逻辑，并写入 content_hash
    ...
```

### 2.3 调用方修改

- `app_ui.py` 中「导入需求」「导入全回归用例」「上传 Word/Excel」等入口，统一改为调用 `add_entry_with_dedup`。
- 当 `status == "skipped"` 时，`st.info("文件未变更，已跳过")`，不触发后续总结与缓存刷新。

---

## 三、阶段 2：Metadata 层与历史记录

### 3.1 历史记录表结构（沿用 memory_entries 扩展）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER | 主键 |
| created_at | TEXT | 导入时间 |
| source_type | TEXT | manual / test_cases / upload_docx 等 |
| source_id | TEXT | 来源标识（如 thread_id、文件名） |
| title | TEXT | 用户输入或解析出的标题 |
| content_hash | TEXT | SHA-256，用于去重 |
| content | TEXT | 原始内容（Context 层） |
| summary | TEXT | 用户输入的简短摘要（可选） |
| agent_summary | TEXT | Librarian Agent 生成的 150 字总结 |
| agent_summary_status | TEXT | pending / success / failed |

### 3.2 查询接口

- `list_import_history(limit)`：按时间倒序，返回 id、created_at、source_type、title、agent_summary、agent_summary_status、content 前 500 字等，供 UI 渲染。
- 已有 `list_import_history` 可复用，确保包含 `agent_summary` 与 `agent_summary_status`。

---

## 四、阶段 3：Librarian Agent 总结

### 4.1 触发时机

- 在 `add_entry_with_dedup` 返回 `status in ("added", "updated")` 后，异步或同步调用总结逻辑。
- 建议：在 UI 导入成功后，`st.spinner("生成摘要中…")` 下同步调用，与现有 `_generate_entry_summary` 类似。

### 4.2 Prompt 模板

```
你是一位资深需求与测试架构师。这是一份新上传/导入的测试或需求文档。
请用 150 字以内的中文，总结该文档主要涵盖的业务模块、核心操作流程以及增删改的重点逻辑。
不要输出多余解释，直接给出总结。
```

### 4.3 模型选择

- 使用 `gemini-2.0-flash` 或 `gemini-1.5-flash`，成本低，满足总结需求。
- 复用 `_generate_entry_summary` 的调用方式，或抽成独立函数 `_generate_librarian_summary(entry_id, content, gemini_key, model)`。

### 4.4 持久化

- 总结结果写入 `memory_entries.agent_summary`，`agent_summary_status` 置为 `success` 或 `failed`。
- 与现有 `update_agent_summary` 逻辑一致。

---

## 五、阶段 4：Gemini Context Caching

### 5.1 流程说明

1. **创建缓存**：当项目记忆有更新（新增/更新条目且未跳过）时，将当前「项目记忆全文」打包，调用 Gemini API 的 Context Caching 接口创建 Cached Content。
2. **获取 cache_name**：API 返回 `cachedContents/{id}` 形式的资源名，持久化到 `config/agent_knowledge_meta.json` 或新增 `config/context_cache_meta.json`。
3. **多 Agent 共享**：在构造 Crew、调用各 Agent 时，将 `cached_content=cache.name` 传入 Gemini 请求配置，使模型直接使用缓存，无需再次接收全文。

### 5.2 Gemini API 用法（参考）

```python
# 创建缓存（伪代码，需按实际 SDK 调整）
from google import genai

client = genai.Client()
cache = client.caches.create(
    model="gemini-2.0-flash",
    config=genai.types.CreateCachedContentConfig(
        display_name="project_memory",
        contents=[project_memory_text],  # 项目记忆全文
        ttl="86400s",  # 24 小时，可按需调整
    ),
)
cache_name = cache.name  # 如 "cachedContents/xxx"

# 后续请求时挂载
response = client.models.generate_content(
    model="gemini-2.0-flash",
    contents="用户问题",
    config=genai.types.GenerateContentConfig(cached_content=cache_name),
)
```

### 5.3 与 CrewAI / LangChain 的集成

- CrewAI 底层使用 LangChain 的 LLM 封装。需确认 LangChain 的 `ChatGoogleGenerativeAI` 是否支持 `cached_content` 参数。
- 若官方封装暂不支持，可考虑：
  - 使用 `google-genai` 原生 SDK 创建缓存，再在 LangChain 中通过自定义 Client 传入；
  - 或采用「预生成知识库摘要 + 限制注入长度」的降级方案，在 PRD 阶段 2 无法完美落地时使用。

### 5.4 缓存刷新策略

- **触发**：`add_entry_with_dedup` 返回 `added` 或 `updated` 时，标记 `project_memory_dirty = True`。
- **执行**：在下次 `get_project_context_for_agent()` 被调用前，或在 pipeline 启动时，检查 dirty 标志；若为 True，则重新打包全文、创建新缓存、更新 cache_name，并清除 dirty。
- **TTL**：建议 24 小时（86400s），超时后需重新创建。

### 5.5 降级方案（若 Context Caching 暂不可用）

- 保持现有逻辑：`get_project_context_for_agent()` 返回 project_memory 文本 + agent_knowledge 摘要。
- 对 project_memory 做长度截断（如 20000 字符），并优先保留最近导入的条目，减少 Token 消耗。
- 在 PRD 中注明「阶段 2 的 Context Caching 为优化项，可后续迭代」。

---

## 六、阶段 5：UI 历史记录与总结展示

### 6.1 展示结构

在「项目记忆」Tab 下，新增或调整「导入历史」区域：

```
🕒 2026-03-03 14:00 | 导入全回归用例 | 来源：上传 · 支付模块回归.xlsx
   [展开] 总结：涵盖 USDT 充值核心链路，包含生成地址、链上转账确认及端内代币到账校验等 12 个极端场景...

🕒 2026-03-03 13:45 | 导入需求文档 | 来源：上传 · 直播分辨率ABtest.docx
   [展开] 总结：直播画质分流实验，涉及分辨率档位、降级策略与实验周期配置...
```

### 6.2 实现要点

- 使用 `st.expander` 或 `st.dataframe` 展示 `list_import_history` 返回的列表。
- 每条展示：`created_at`、`title` 或 `source_id`、`source_type`、`agent_summary`（若有）。
- 状态标签：`agent_summary_status` 为 success 显示「有摘要✓」，failed 显示「失败」，pending 显示「生成中…」。
- 与现有 `list_import_history`、`_generate_entry_summary` 的 UI 逻辑对齐，避免重复实现。

### 6.3 文案配置

在 `config/ui_texts.yaml` 中增加：

```yaml
memory_tab:
  history_timeline_title: "导入历史"
  history_item_skipped: "文件未变更，已跳过"
  librarian_summary_label: "总结"
  # ... 其他已有 key 保持不变
```

---

## 七、实施顺序建议

1. **阶段 0（P0 最高）**：存储后端可插拔 + 惰性初始化，消除 sqlite3 硬依赖，通过 mock 验证后上线。
2. **阶段 1 + 2**：哈希、去重、Metadata 扩展，先保证「重复上传不入库」。
3. **阶段 3**：Librarian Agent 总结，保证「新导入有总结可看」。
4. **阶段 5**：UI 历史与总结展示，提升可用性。
5. **阶段 4**：Gemini Context Caching，需确认 SDK 支持后再实施；若不支持，采用降级方案。

---

## 八、回归与测试要点

### 8.1 阶段 0 专项验证（P0）

- **云端无 sqlite3**：`import memory_store` 不报错，`_SQLITE_AVAILABLE = False`，自动切换 JsonFileBackend。
- **项目记忆可用性**：JsonFileBackend 下 add / search / delete / list_history 均正常。
- **核心链路不受影响**：MEMORY_AVAILABLE = True 或 False 时，生成用例、文档问答均正常。
- **Agent 上下文**：`get_project_context_for_agent()` 在任何后端状态下都正常返回。

### 8.2 常规回归

- 重复上传同一文档，第二次应提示「已跳过」，且 `memory_entries` 不新增记录。
- 新导入后，`agent_summary` 应在合理时间内（如 30 秒内）生成并展示。
- 4 个 Agent 生成用例时，能正确使用 project_context（无论来自缓存还是降级文本）。
- 项目记忆 Tab 的搜索、删除、展开等交互与现有逻辑兼容，无布局错位。
