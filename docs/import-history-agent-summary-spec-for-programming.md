# 导入历史 + Agent 摘要 · 实施规范

> **角色**：@产品  
> **给**：@编程  
> **用途**：严格按本文档实施「导入历史」与「每份导入对应一份 Agent 摘要」，不得超出范围。

---

## 一、范围与红线

| 项目 | 说明 |
|------|------|
| **范围** | 1）扩展 memory_entries，增加 agent_summary 字段；2）每次导入成功后触发 Agent 生成摘要；3）项目记忆页展示「导入历史」及对应摘要；4）摘要失败时的提示与重试 |
| **红线** | 不得重构现有导入逻辑、不得修改 crew_test 流水线、不得改变侧栏与主流程布局。仅增量扩展。 |

---

## 二、数据模型

### 2.1 扩展 memory_entries

在 `memory_store.py` 中，为 `memory_entries` 表增加列：

```
agent_summary TEXT   -- Agent 生成的摘要，空表示未生成或失败
agent_summary_status TEXT  -- 'pending' | 'success' | 'failed'，默认 'pending'
```

- 使用 SQLite `ALTER TABLE` 在 `_ensure_tables` 或初始化时兼容性添加列（若列已存在则跳过）。
- `add_entry` 调用时，`agent_summary` 与 `agent_summary_status` 默认为空和 `'pending'`。
- 新增函数：`update_agent_summary(entry_id, summary: str, status: 'success'|'failed')`。

### 2.2 摘要生成

- 调用方：在 `app_ui.py` 的导入成功回调中（单文档、批量、测试用例），在 `add_entry` 返回后，调用摘要生成逻辑。
- 摘要生成函数：新建 `generate_entry_summary(entry_id, content: str) -> str | None`，使用现有 Gemini 配置，prompt 固定为：「请用 200 字以内总结以下文档的核心要点与测试相关风险。」，输入为 content 前 8000 字符。
- 生成成功后调用 `update_agent_summary(entry_id, summary, 'success')`；失败调用 `update_agent_summary(entry_id, '', 'failed')`。

---

## 三、UI 规范

### 3.1 导入历史区块

在「项目记忆」页，在「搜索」与「导入需求」之间，新增区块「导入历史」：

- 标题：**导入历史**
- 展示：按 `created_at` 倒序，最多 20 条，每条一行。
- 每行格式：`【标题/来源】 导入时间 · [有摘要✓ / 生成中… / 失败 ✗]`
- 点击行可展开，展开内容分两块：
  - **导入内容**：content 前 2000 字 + 省略号（与现有 expander 一致）
  - **Agent 摘要**：若 status=success 则展示 agent_summary；若 pending 则「生成中…」；若 failed 则「摘要生成失败」+ **「重试」按钮**

### 3.2 重试逻辑

- 仅当 `agent_summary_status == 'failed'` 时展示「重试」按钮。
- 点击重试：调用 `generate_entry_summary` 并更新 status；成功则 success，失败则保持 failed 并 `st.error` 提示「摘要生成失败：{错误信息}」。

### 3.3 文案配置化

以下文案必须放入 `config/ui_texts.yaml` 的 `memory_tab` 下，并用 `_get_text` 读取：

| key | 默认值 |
|-----|--------|
| `import_history_section` | 导入历史 |
| `agent_summary_label` | Agent 摘要 |
| `agent_summary_pending` | 生成中… |
| `agent_summary_failed` | 摘要生成失败 |
| `agent_summary_retry_btn` | 重试 |

---

## 四、触发时机（严格按此实现）

| 导入方式 | 触发时机 |
|----------|----------|
| 方式一：文件夹批量导入 | 每成功 `add_entry` 一条后，顺序调用 `generate_entry_summary`；可 combined 为「导入完成 → 再逐条生成摘要」，用 status_text 展示「正在生成摘要 3/10…」 |
| 方式二：单文档导入 | `add_entry` 返回后立即调用 `generate_entry_summary` |
| 方式三：全回归测试用例 | `add_entry`(test_cases, full_regression) 后立即调用 `generate_entry_summary`（注意 content 可能较长，仍只取前 8000 字符） |

**约束**：摘要生成过程需有明确状态（spinner 或「生成中…」），不得阻塞导入完成反馈。若采用异步，需在下次 rerun 或轮询时更新状态。

---

## 五、失败与重试策略

| 场景 | 处理 |
|------|------|
| 生成超时（建议 30s） | 视为失败，status=failed，允许用户手动重试 |
| API 报错（如 429、500） | 视为失败，status=failed，st.error 展示简短的「摘要生成失败：{原因}」 |
| 内容为空 | 不调用生成，status 保持 pending，展示「内容为空，跳过摘要」 |

---

## 六、禁止事项

1. 不得修改 `get_project_context_for_agent`、`get_recent_for_agent` 等现有函数的签名与主逻辑；若需把 agent_summary 纳入上下文，可单独扩展调用链，且需产品确认。
2. 不得增加新的侧栏入口或 Tab；所有 UI 均在「项目记忆」页内完成。
3. 不得改动 `add_entry` 的 source_type、source_id 等现有约定。

---

## 七、验收标准

- [ ] 单文档导入成功后，该条在「导入历史」中展示，且 Agent 摘要自动生成并展示
- [ ] 批量导入时，每条均有对应摘要（或 pending/failed 状态）
- [ ] 全回归用例导入后，full_regression 条目的 agent_summary 可生成并展示
- [ ] status=failed 时展示「重试」按钮，点击后重新生成并更新状态
- [ ] 所有新增文案均从 ui_texts.yaml 读取
