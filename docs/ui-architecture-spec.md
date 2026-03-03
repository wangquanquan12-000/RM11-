# AI 测试流水线平台 · 高扩展性 UI 架构规范

> **角色来源**：@产品（B 端产品专家 × 前端架构师）  
> **落地执行**：由 @编程 按本规范重构 `app_ui.py`，不得将业务逻辑写死在 UI 布局中。

---

## 一、项目现状与目标

| 项目 | 说明 |
|------|------|
| **产品** | AI 测试流水线平台（Streamlit） |
| **当前核心业务** | 4 个 Agent 协作，将需求文档 → 标准测试用例，支持追加归档 |
| **架构目标** | 预判 Jira 来源、API 测试生成 Agent、飞书对接等大量新需求；新需求以「工作台模块」形式接入，与现有需求转用例模块互不干扰 |

---

## 二、高扩展性 UI 设计规范（必须严格执行）

### 2.1 配置驱动 (Config-Driven) UI

- **原则**：页面上所有「可配置的入口与选项」均来自 `config/` 下配置文件，代码只负责「读取配置 + 渲染」，不写死文案、不写死选项列表。
- **必须配置化的内容**：
  - **工具/应用入口**：工作台顶部或侧栏的模块列表（名称、图标、路由 key）→ 建议 `config/workbench_apps.yaml` 或扩展 `ui_texts.yaml`。
  - **Agent 配置项**：角色、目标、任务描述等 → 已存在 `config/agents.yaml`，UI 仅根据该文件动态渲染表单或编辑器。
  - **模型选择下拉框**：可选模型列表（如 Gemini 1.5/2.5 等）→ 从 `config/` 的 YAML/JSON 读取（如 `config/models.yaml`），新增模型只改配置不改代码。
- **禁止**：在 Python 里写死 `GEMINI_MODELS = [(...), (...)]`、写死 Tab 名称列表、写死工具入口的文案与顺序。

### 2.2 插件化 / 模块化布局（工作台模式）

- **原则**：整体形态为「应用市场 / 工作台」，当前「需求转用例」仅为其中一个独立 App/Plugin；未来新增 Jira、API 测试、飞书等，均为新模块。
- **实现方式**（二选一或组合）：
  - **动态 Tab**：Tab 列表来自配置，每个 Tab 对应一个模块的渲染函数；新增模块 = 配置中增加一项 + 实现一个渲染函数并注册。
  - **st.navigation**（Streamlit 1.30+）：若版本支持，采用 `st.navigation` 做多页/多应用切换，每页对应一个业务模块。
- **约束**：
  - 模块之间无直接依赖；单个模块内部可依赖 `crew_test`、`memory_store` 等，但不允许模块 A 的 UI 逻辑里 import 或调用模块 B 的 UI。
  - 新增模块的接入方式：在配置中声明 + 在「模块注册表」中注册渲染函数，**不**改现有模块的布局代码。

### 2.3 统一状态总线 (Session State Contract)

- **原则**：在 `st.session_state` 中建立**标准化、命名规范**的上下文结构，所有页面与各阶段 Agent 只通过约定 key 存取，避免散落 key 与命名冲突。
- **约定结构（示例，可增字段不可删约定前缀）**：

  ```yaml
  # 当前任务/上下文（各模块读写时使用）
  session_state.current_task_context:
    module_id: str          # 当前所在模块 id，如 "run"
    task_id: str            # 当前任务/运行 id，便于日志与进度关联
    input_summary: dict     # 当前输入摘要（如 demand_title 等）
    output_summary: dict    # 当前输出摘要（如 excel_path 等）
    started_at: str         # ISO 时间
    status: str             # pending | running | success | error
  
  # 各模块自己的状态（必须带模块前缀，避免冲突）
  session_state["app_<module_id>_*"]
  ```

- **禁止**：在未约定命名空间下随意使用 `st.session_state["xxx"]`；历史已有 key（如 `app_last_run`）在重构时迁入上述约定并保留兼容。

### 2.4 组件解耦（可复用 UI 组件）

- **原则**：将跨模块复用的 UI 抽成独立函数或轻量类，放在统一位置（如 `ui_components/` 或 `app_ui_components.py`），供各业务线调用。
- **必须抽出的组件**（或等价能力）：
  - **Agent 执行进度条**：接收「当前步骤 / 总步骤 / 状态文案」，统一展示样式与刷新方式。
  - **文件上传器**：支持类型/大小限制、白名单路径（若已有安全规范），返回统一数据结构（如 `{ path, name, size }`）。
  - **日志/终端展示**：流式或分段展示运行日志，支持折叠、复制；与具体 Agent 解耦，仅接收「行列表」或「流」。
- **调用方式**：业务模块只传数据与回调，不内联实现进度条、上传、日志的 DOM 结构；新模块直接复用同一组件，保证体验一致。

---

## 三、配置与目录建议（供实现参考）

| 用途 | 建议路径 | 说明 |
|------|----------|------|
| 工作台模块列表 | `config/workbench_apps.yaml` | 定义模块 id、名称、图标、顺序、是否启用 |
| 文案 | `config/ui_texts.yaml` | 已有；可扩展 workbench、common 等节点 |
| 模型列表 | `config/models.yaml` 或并入现有配置 | 模型 key、展示名、默认选中 |
| Agent 定义 | `config/agents.yaml` | 已有 |
| 公用组件 | `ui_components/` 或 `app_ui_components.py` | 进度条、上传器、日志终端等 |

---

## 四、交付给 @编程 的检查清单

实现完成后，需满足：

- [ ] 所有工具入口、Agent 配置项、模型下拉框均来自 config，无写死列表。
- [ ] 工作台为「模块列表 + 当前模块内容」布局，需求转用例仅为其中一个模块；新增一个「占位模块」即可验证扩展路径。
- [ ] `session_state` 存在约定的 `current_task_context` 及模块前缀规范，文档中注明 key 表。

### session_state key 一览表（约定）

| Key | 说明 |
|-----|------|
| `current_task_context` | 当前任务上下文：module_id, task_id, input_summary, output_summary, started_at, status |
| `app_run_last_run` | 生成用例模块上次运行结果（与 app_last_run 兼容） |
| `app_run_running` | 生成用例是否正在运行 |
| `app_agents_dirty` | 编辑 Agent 是否有未保存修改 |
| `app_agents_last_saved_hash` | 上次保存的 agents 配置摘要，用于比对 |
| `app_doc_chat_messages` | 文档问答对话列表 |
| `app_last_run` | （兼容）同 app_run_last_run |
| `app_last_demand_snippet` / `app_last_demand_full` | （兼容）上次需求摘要 |
- [ ] 至少 3 个公用组件（进度条 / 上传 / 日志）已抽出并在至少 2 处复用。
- [ ] 现有「需求转用例 + 编辑 Agent + 项目记忆 + 文档问答」功能行为保持不变（可做回归用例）。

---

**文档版本**：1.0  
**维护**：@产品 负责规范与演进；@编程 负责按此规范实现与自测。
