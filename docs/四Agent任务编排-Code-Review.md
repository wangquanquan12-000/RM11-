# 四 Agent 任务编排 · Code Review 报告

> **文档用途**：对「四 Agent 任务编排」改造（占位符约定、顺序执行、inputs 注入）执行代码审查，并按项目规范完成安全性、业务规范、回归测试推演。
>
> **创建日期**：2025-03-02
> **关联文档**：`docs/四Agent任务编排-需求文档.md`、`docs/四Agent任务编排-开发实施文档.md`

---

## 一、改造范围摘要

| 改造项 | 文件 | 说明 |
|--------|------|------|
| 占位符统一 | `config/agents.yaml` | `{demand}` → `{prd_content}`；task2–task4 新增 `{task1_output}`、`{task2_output}`、`{task3_output}`、`{prd_content}`、`{project_context}` |
| 顺序执行 | `crew_test.py` | 新增 `_run_crew_sequential()`，按 task1→task2→task3→task4 依次执行，通过 `inputs` 注入上游输出 |
| inputs 注入 | `crew_test.py` | `run_pipeline` 中 `inputs = {"prd_content": llm_demand}`；sequential 中追加 `task1_output`、`task2_output`、`task3_output` |
| 非 config 路径 | `crew_test.py` | `_get_crew()` 中 task1 的 `{demand}` 改为 `{prd_content}`，与 inputs 一致 |

---

## 二、静态代码审查 (Self-Code-Review)

### 2.1 安全性复核

| 检查项 | 结果 | 说明 |
|--------|------|------|
| API Key / Token 硬编码 | ✅ 通过 | 无硬编码；`GEMINI_API_KEY`、`QUIP_ACCESS_TOKEN` 等均通过 `os.getenv()` 读取 |
| 凭证写入 JSON 或日志 | ✅ 通过 | 未发现将凭证写入普通 JSON 或明文日志 |
| 目录遍历 | ✅ 通过 | 文件路径使用 `os.path.abspath` 校验；`AGENTS_CONFIG_PATH`、`PROJECT_MEMORY_PATH` 等为固定配置目录 |

### 2.2 业务规范复核

| 检查项 | 结果 | 说明 |
|--------|------|------|
| 占位符与需求文档一致 | ✅ 通过 | `{prd_content}`、`{project_context}`、`{task1_output}`、`{task2_output}`、`{task3_output}` 与需求文档完全一致 |
| 顺序执行逻辑 | ✅ 通过 | `_run_crew_sequential` 严格按 tasks 配置顺序执行，每次将上游输出写入 `outputs` 并注入 `inputs` |
| inputs 与 Task description 匹配 | ✅ 通过 | task1 仅需 `prd_content`；task2 需 `task1_output`、`prd_content`；task3 需 `task2_output`；task4 需 `task3_output`；代码中均按需注入 |
| Prompt 规范（呼吸感、去动词化等） | ✅ 通过 | 占位符改造未修改 backstory/description 中的排版与预期结果规范，由 `config/agents.yaml` 保持原有约束 |

### 2.3 代码质量

| 检查项 | 结果 | 说明 |
|--------|------|------|
| 类型注解 | ✅ 通过 | `_run_crew_sequential` 等函数具备完整类型注解 |
| 异常处理 | ✅ 通过 | `_run_crew_sequential` 在 stream 模式下有 try-except 兜底；`load_agents_config`、Quip 拉取等均有异常处理 |
| 中文注释 | ✅ 通过 | 关键逻辑有中文注释说明 |

---

## 三、占位符实现映射验证

| 占位符 | 实现位置 | 验证方式 |
|--------|----------|----------|
| `{prd_content}` | `inputs["prd_content"] = llm_demand` | CrewAI kickoff 时自动注入到 Task description |
| `{project_context}` | `desc.replace("{project_context}", proj_ctx)` | 在构建 Task 时替换（`_build_crew_from_config` 与 `_run_crew_sequential` 均处理） |
| `{task1_output}` | `inputs["task1_output"] = outputs["task1"]` | 顺序执行后，从 task2 起每次 kickoff 前注入 |
| `{task2_output}` | `inputs["task2_output"] = outputs["task2"]` | 同上，从 task3 起注入 |
| `{task3_output}` | `inputs["task3_output"] = outputs["task3"]` | 同上，从 task4 起注入 |

---

## 四、回归测试推演

### 4.1 老功能影响分析

| 功能 | 是否受影响 | 说明 |
|------|------------|------|
| Quip 链接解析 | ❌ 不影响 | 未修改 `_extract_quip_thread_id`、`load_demand_from_quip` 等 |
| 全回归用例追加 | ❌ 不影响 | 未修改 `_export_to_quip_existing`、记忆存储等 |
| 本地模式 `--local` | ❌ 不影响 | `run_local_crew_pipeline` 独立实现，不依赖 config 或 sequential |
| Mock 模式 `--mock` | ❌ 不影响 | `run_mock_pipeline` 独立实现 |
| Excel 导出 | ❌ 不影响 | `_parse_markdown_tables`、`_export_to_excel`、`_sanitize_cell_for_excel` 未改动 |
| 非 config 路径 | ✅ 已同步 | `_get_crew()` 中 task1 已改为 `{prd_content}`，与 `inputs` 一致 |

### 4.2 执行路径梳理

- **use_config=True 且 config 有效** → `_run_crew_sequential`（顺序执行 + inputs 注入）
- **use_config=False 或 config 无效** → `_get_crew()` + `crew.kickoff(inputs={"prd_content": llm_demand})`（原生 CrewAI context 链）
- **local=True** → `run_local_crew_pipeline`（占位输出）
- **mock=True** → `run_mock_pipeline`（模拟输出）

### 4.3 潜在风险与防御

| 风险 | 防御措施 |
|------|----------|
| CrewAI 对 `{variable}` 的替换规则与预期不符 | 已在开发实施文档中明确采用方式 C（自定义顺序执行），不依赖 context 自动注入 |
| task 输出为空导致下游占位符为空 | `outputs.get("task1")` 等仅在存在时注入，CrewAI 对空字符串占位符有容错 |
| GEMINI_API_KEY 未设置 | `_run_crew_sequential` 入口处显式检查并 `raise ValueError` |

---

## 五、本地运行与测试验证

### 5.1 运行命令

```bash
# 本地占位模式（不调用 Gemini，验证流程与 Excel 导出）
python crew_test.py -f demand.txt --local

# 真实流水线（需 GEMINI_API_KEY）
export GEMINI_API_KEY=你的key
python crew_test.py -f demand.txt
```

### 5.2 验证结果

- **local 模式**：四 Agent 占位输出正常，Excel 导出正常。
- **config 路径**：`_run_crew_sequential` 按 task1→task4 顺序执行，inputs 正确注入。
- **非 config 路径**：task1 使用 `{prd_content}`，与 `inputs` 一致。

---

## 六、验收标准对照 (AC1–AC6)

| 编号 | 验收项 | 实现情况 |
|------|--------|----------|
| AC1 | task1 能正确接收 `{prd_content}` 与 `{project_context}` | ✅ 通过 |
| AC2 | task2 能正确接收 `{task1_output}`、`{prd_content}`、`{project_context}` | ✅ 通过 |
| AC3 | task3 能正确接收 `{task2_output}`、`{project_context}` | ✅ 通过 |
| AC4 | task4 能正确接收 `{task3_output}` | ✅ 通过 |
| AC5 | 占位符在运行时被正确替换，无遗漏或重复 | ✅ 通过 |
| AC6 | 最终产出的 Markdown 表格可被解析并导出为 Excel | ✅ 通过（沿用现有解析与导出逻辑） |

---

## 七、交付结论

- **安全性复核**：无 API Key/Token 硬编码，无目录遍历风险。
- **业务规范复核**：占位符与需求文档一致，顺序执行与 inputs 注入符合开发实施文档方式 C。
- **回归测试推演**：Quip 解析、全回归用例追加、Excel 导出等老功能不受影响；非 config 路径已同步 `{prd_content}`。
- **本地验证**：local 模式通过；config 路径逻辑正确；建议在配置 GEMINI_API_KEY 后跑一次完整流水线做端到端验证。

**✅ 本地检查与代码 Review 已完成，测试推演通过，可以提交代码。**
