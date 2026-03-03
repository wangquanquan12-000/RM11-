# 项目记忆摘要修复 · PRD + 开发实施文档

> **问题现象**：项目记忆 Tab 的「导入历史」区块，条目显示「生成中…」但始终没有摘要内容；「生成中…」状态下也没有重试按钮，用户无法手动触发摘要生成。
>
> **创建日期**：2026-03-XX

---

## 一、Bug 复盘：为什么摘要没有总结？

### 1.1 代码走读

摘要的完整链路：

```
用户导入文档
  └─ add_entry_with_dedup(...)
       └─ 返回 (rowid, status)
            └─ status != "skipped" 时
                 └─ _generate_entry_summary(rowid, content, gemini_key)
                      ├─ 成功 → update_agent_summary(id, summary, "success")
                      └─ 失败 → update_agent_summary(id, "", "failed")

UI 展示（list_import_history）
  └─ agent_summary_status = "success" → 展示摘要文字 + tag "有摘要✓"
  └─ agent_summary_status = "failed"  → tag "失败 ✗" + 重试按钮
  └─ 其他（pending / NULL）           → tag "生成中…"，只有 caption，无任何操作按钮
```

### 1.2 根因列表（三个）

| 编号 | 根因 | 触发条件 |
|------|------|----------|
| **Bug-1** | `_generate_entry_summary` 内容为空分支（第 117-118 行）没有调用 `update_agent_summary`，status 永远留在 `pending` | content 为空字符串时 |
| **Bug-2** | 数据库中老条目 `agent_summary_status = NULL`，被 `COALESCE(...,'pending')` 变成 pending，而 UI 的 pending 分支只显示文字，没有重试按钮 | 功能上线前已存在的历史导入记录 |
| **Bug-3** | Gemini Key 未配置时，`_generate_entry_summary` 返回 "failed" 并调用 `update_agent_summary(..., "failed")`，这是正确的；但如果 Key 是后来才配置的（用户先导入再配置 Key），对应条目永久留在 "failed" 状态，需要用户手动重试 |

### 1.3 为什么「生成中…」会永远停留？

Streamlit 无后台线程，每次页面刷新都是全量重新渲染，不会自动轮询重试。"生成中…"只是个静态文字标签，并不代表有任务在运行——这是一个**状态命名误导问题**：`pending` 在这里的真实含义应该是「待生成」，而不是「正在生成」。

### 1.4 影响范围

- **不影响**：生成用例核心流程、全回归用例导入、需求导入、Agent 知识库刷新。
- **影响**：项目记忆 Tab 的导入历史区块，部分条目的摘要无法展示。

---

## 二、产品修复方案

### 2.1 UI 层修复（P0）

**变更前**：
- `pending` 状态：只显示 `st.caption("生成中…")`，无任何操作入口

**变更后**：
- `pending` 状态：显示「待生成」提示 + **「生成摘要」按钮**（与 failed 的重试按钮逻辑完全相同）
- 状态 Tag 文案调整：`"生成中…"` → `"待生成"`，避免用户误以为系统在后台运行

### 2.2 批量生成入口（P1）

在「导入历史」区块顶部，新增「批量生成缺失摘要」按钮：
- 点击后，对所有 `agent_summary_status IN (pending, failed, NULL)` 的条目，串行调用 `_generate_entry_summary`
- 每条生成后实时刷新进度（`st.progress` 或 `st.spinner`）
- 成功/失败数量汇总展示

### 2.3 代码层修复（P0）

`_generate_entry_summary` 的内容为空分支，补充 `update_agent_summary` 调用：

```python
# 修复前
if not (content or "").strip():
    return False, "内容为空"

# 修复后
if not (content or "").strip():
    update_agent_summary(entry_id, "", "failed")  # 补上这行
    return False, "内容为空"
```

### 2.4 验收标准

| 编号 | 验收项 |
|------|--------|
| AC1 | 新导入文档，Gemini Key 已配置，摘要在 30 秒内生成，状态变为「有摘要✓」 |
| AC2 | 所有 pending 状态条目，展示「待生成」 + 「生成摘要」按钮 |
| AC3 | 点击「生成摘要」成功后，状态变为「有摘要✓」，摘要文字展示 |
| AC4 | 点击「批量生成缺失摘要」，所有 pending/failed 条目依次生成摘要 |
| AC5 | 无 API Key 时，点击「生成摘要」显示错误提示，而非静默失败 |

---

## 三、开发实施细节

### 3.1 `_generate_entry_summary` Bug 修复

**文件**：`app_ui.py` 第 117-118 行

```python
# 改前
def _generate_entry_summary(entry_id: int, content: str, gemini_key: str = "") -> tuple[bool, str]:
    if not (content or "").strip():
        return False, "内容为空"

# 改后
def _generate_entry_summary(entry_id: int, content: str, gemini_key: str = "") -> tuple[bool, str]:
    if not (content or "").strip():
        update_agent_summary(entry_id, "", "failed")  # ← 补上，避免 status 永久停留 pending
        return False, "内容为空"
```

### 3.2 UI 层：pending 分支增加「生成摘要」按钮

**文件**：`app_ui.py` 约第 1268-1285 行（`render_memory_tab` 内的历史列表渲染）

```python
# 改前
else:  # pending
    st.caption(_get_text(T, "memory_tab.agent_summary_pending") or "生成中…")

# 改后
else:  # pending → 待生成
    st.caption(_get_text(T, "memory_tab.agent_summary_pending_hint") or "摘要待生成")
    if st.button(
        _get_text(T, "memory_tab.agent_summary_generate_btn") or "生成摘要",
        key=f"gen_summary_{e.get('id')}",
    ):
        ok, err = _generate_entry_summary(e["id"], content, defaults.get("gemini_key", ""))
        if ok:
            st.rerun()
        else:
            st.error(f"摘要生成失败：{err}")
```

### 3.3 UI 层：status Tag 文案修正

```python
# 改前
else:
    tag = _get_text(T, "memory_tab.agent_summary_pending") or "生成中…"

# 改后
else:
    tag = _get_text(T, "memory_tab.agent_summary_pending_tag") or "待生成"
```

### 3.4 批量生成按钮

在 `st.markdown("**导入历史**")` 下方插入：

```python
# 检查是否有 pending/failed 条目，如有则显示批量按钮
_pending_entries = [
    e for e in hist
    if (e.get("agent_summary_status") or "pending") in ("pending", "failed")
]
if _pending_entries:
    if st.button(
        f"批量生成缺失摘要（{len(_pending_entries)} 条）",
        key="batch_gen_summary",
        type="secondary",
    ):
        gemini_key = defaults.get("gemini_key", "")
        success_count = 0
        fail_count = 0
        prog = st.progress(0.0, text="批量生成摘要中…")
        for idx, e in enumerate(_pending_entries):
            _content = e.get("content", "") or e.get("summary", "")
            ok, _ = _generate_entry_summary(e["id"], _content, gemini_key)
            if ok:
                success_count += 1
            else:
                fail_count += 1
            prog.progress(
                (idx + 1) / len(_pending_entries),
                text=f"进度 {idx+1}/{len(_pending_entries)}（成功 {success_count}，失败 {fail_count}）",
            )
        prog.empty()
        st.success(f"批量生成完成：成功 {success_count} 条，失败 {fail_count} 条")
        st.rerun()
```

### 3.5 ui_texts.yaml 新增文案

在 `memory_tab:` 节点下补充：

```yaml
  agent_summary_pending_tag: "待生成"
  agent_summary_pending_hint: "摘要待生成"
  agent_summary_generate_btn: "生成摘要"
```

---

## 四、风险推演

| 风险 | 触发场景 | 缓解措施 |
|------|----------|----------|
| **批量生成超 Gemini 限速** | 一次性对 20+ 条触发批量生成 | 串行处理（非并发），每条之间无额外延迟（失败条件不需要间隔）；限速则报错单条 failed，继续下一条 |
| **批量生成中断（用户切 Tab）** | Streamlit 页面切换 → 当前渲染中断 | 已生成的条目状态已写入 DB，不会回滚；用户再次进入页面，继续批量生成未完成的条目 |
| **st.button 在 expander 内的 key 冲突** | 多条 pending 条目各自的 button key 相同 | 已用 `f"gen_summary_{e.get('id')}"` 做动态 key，不冲突 |
| **content 取值为 None** | 旧库条目 content 字段为 NULL | 已用 `e.get("content", "") or e.get("summary", "")` 兜底 |
| **update_agent_summary 在 JsonFileBackend 下的兼容性** | sqlite3 不可用时走 JSON 后端 | JsonFileBackend 的 `update_agent_summary` 方法需与 SqliteBackend 接口一致（开发实施阶段 0 的范围） |

---

## 五、改动文件清单

| 文件 | 改动行 | 改动说明 |
|------|--------|----------|
| `app_ui.py` | ~117 | `_generate_entry_summary` Bug 修复（内容为空时写 failed） |
| `app_ui.py` | ~1265 | status tag 文案：「生成中…」→「待生成」 |
| `app_ui.py` | ~1281-1283 | pending 分支增加「生成摘要」按钮 |
| `app_ui.py` | ~1256 | 历史标题下方插入「批量生成缺失摘要」按钮 |
| `config/ui_texts.yaml` | memory_tab 节 | 新增 `agent_summary_pending_tag`、`agent_summary_pending_hint`、`agent_summary_generate_btn` |

**不需要改动**：`memory_store.py`、`crew_test.py`、`pipeline_service.py`。

---

## 六、与重新规划实施方案的关系

本次修复完全在 UI + `_generate_entry_summary` 层，不涉及存储后端。

- `update_agent_summary` 函数已存在于 memory_store.py，sqlite 和 JSON 后端均需实现此方法（按实施方案阶段 0 要求）。
- 若阶段 0 尚未完成，本修复在 sqlite 可用的环境下仍然有效；在 JSON 后端环境下，需确认 `update_agent_summary` 已在 JsonFileBackend 中实现。
