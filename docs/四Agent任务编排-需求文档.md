# 四 Agent 任务编排 · 需求文档

> **文档用途**：定义用例工坊四 Agent 流水线的业务流程、接力关系、占位符约定及验收标准。
>
> **创建日期**：2025-03-02

---

## 一、业务流程与接力关系说明

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  Agent 1        │     │  Agent 2        │     │  Agent 3        │     │  Agent 4        │
│  文档分析师     │ ──► │  测试点拆解师   │ ──► │  测试用例工程师 │ ──► │  用例审查官     │
│  (The Auditor)  │     │  (The Planner)  │     │  (Case Eng)      │     │  (The Reviewer) │
└────────┬────────┘     └────────┬────────┘     └────────┬────────┘     └────────┬────────┘
         │                       │                       │                       │
         ▼                       ▼                       ▼                       ▼
    task1_output            task2_output            task3_output            最终输出
    《需求风险评估报告》      《测试点骨架》         《测试用例表格》        《审查结论》
```

| 阶段 | Task | Agent | 输入 | 输出 |
|------|------|-------|------|------|
| 1 | task1 | doubt_agent | prd_content + project_context | 《需求风险评估报告》 |
| 2 | task2 | organize_agent | task1_output + prd_content + project_context | 《测试点骨架》 |
| 3 | task3 | case_agent | task2_output + project_context | 《测试用例表格》 |
| 4 | task4 | review_agent | task3_output | 《审查结论》 |

---

## 二、占位符约定

| 占位符 | 含义 | 来源 |
|--------|------|------|
| `{prd_content}` | 需求文档全文（PRD 内容） | 用户输入 / Quip 拉取 / 本地文件 |
| `{project_context}` | 项目记忆与 Agent 知识库摘要 | `load_project_memory()` + `load_agent_knowledge()` |
| `{task1_output}` | task1 的输出（《需求风险评估报告》） | 上游 Agent 执行结果 |
| `{task2_output}` | task2 的输出（《测试点骨架》） | 上游 Agent 执行结果 |
| `{task3_output}` | task3 的输出（《测试用例表格》） | 上游 Agent 执行结果 |

---

## 三、四 Agent 定义（原样保留）

### 3.1 Agents

| id | role | goal |
|----|------|------|
| doubt_agent | Document Analyst | 文档分析师（The Auditor）找茬专家、逻辑推演者。在写用例前，把需求文档"撕碎"，找出所有可能导致测试阻塞或上线故障的坑。 |
| organize_agent | Requirements Analyst | 测试点拆解师（The Planner）将文档和 1 号的质疑转化为"原子化"的测试点（Test Points），为生成具体步骤做骨架。 |
| case_agent | Test Case Engineer | 你是由 Nicholas 调教的【Fambase 专属资深全栈测试专家】。根据输入产出符合《Nicholas 交付宪法》的完美测试用例。 |
| review_agent | QA Reviewer | 用例审查官（The Reviewer）洁癖症晚期、规范捍卫者。拿着"宪法"检查生成的用例，确保无格式错误和逻辑漏洞。 |

（backstory 详细内容见 `config/agents.yaml`，此处从略。）

### 3.2 Tasks（完整描述与预期输出）

#### Task 1

- **id**: task1  
- **agent_id**: doubt_agent  
- **description**:

```
请以【文档分析师（The Auditor）】的身份，对以下需求文档进行深度扫描，并输出《需求风险评估报告》。
要求覆盖：1) 模糊性审查；2) 逻辑冲突与遗漏；3) 极端场景推演。
{project_context}
需求文档：
{prd_content}
```

- **expected_output**: 《需求风险评估报告》：以列表形式输出，每条包含【风险类型】+【问题描述】+【建议/疑问】；若无明显问题则列出最复杂的 3 个逻辑确认点。

#### Task 2

- **id**: task2  
- **agent_id**: organize_agent  
- **context**: [task1]  
- **description**:

```
请以【测试点拆解师（The Planner）】的身份，基于上一任务（文档分析师）输出的《需求风险评估报告》与需求文档，将内容转化为结构清晰、覆盖全面的「测试点」骨架。
须遵循：模块化分组、原子化原则、逻辑继承。

【task1 输出 - 需求风险评估报告】
{task1_output}

【需求文档】
{prd_content}
{project_context}
```

- **expected_output**: 测试点思维导图：Markdown 层级列表，结构为「模块名称 → 子模块/场景 → [P0] 核心测试点 / [P1] 异常边界 / [P2] UI 文案」。

#### Task 3

- **id**: task3  
- **agent_id**: case_agent  
- **context**: [task2]  
- **description**:

```
请以【Fambase 专属资深全栈测试专家】的身份，根据上一任务产出的测试点，输出符合《Nicholas 交付宪法》的测试用例。
表头为 | 用例ID | 模块 | 场景 | 用例概述 | 优先级 | 前置条件 | 操作步骤 | 预期结果 |；呼吸感排版；预期结果去动词化；覆盖极端场景与回归验证。

【task2 输出 - 测试点骨架】
{task2_output}
{project_context}
```

- **expected_output**: 符合《Nicholas 交付宪法》的测试用例：Markdown 表格，固定表头，呼吸感排版，预期结果去动词化。

#### Task 4

- **id**: task4  
- **agent_id**: review_agent  
- **context**: [task3]  
- **description**:

```
请以【用例审查官（The Reviewer）】的身份，对上一任务产出的测试用例，严格按照四大验收标准逐条审查（呼吸感、预期结果、逻辑覆盖率、冗余、表格字段）。
若有问题请指出【用例ID】+【错误类型】+【修改建议】或给出修正后的完整 Markdown 表格；若完美则输出：「✅ 通过审查，用例符合 Fambase 交付标准。」

【task3 输出 - 测试用例】
{task3_output}
```

- **expected_output**: 审查结论：若存在问题则列出【用例ID】+【错误类型】+【修改建议】；若通过则输出：「✅ 通过审查，用例符合 Fambase 交付标准。」

---

## 四、验收标准（AC1–AC6）

| 编号 | 验收项 |
|------|--------|
| AC1 | task1 能正确接收 `{prd_content}` 与 `{project_context}`，输出《需求风险评估报告》 |
| AC2 | task2 能正确接收 `{task1_output}`、`{prd_content}`、`{project_context}`，输出《测试点骨架》 |
| AC3 | task3 能正确接收 `{task2_output}`、`{project_context}`，输出《测试用例》Markdown 表格 |
| AC4 | task4 能正确接收 `{task3_output}`，输出《审查结论》 |
| AC5 | 占位符在运行时被正确替换，无遗漏或重复 |
| AC6 | 最终产出的 Markdown 表格可被解析并导出为 Excel，表头与列与约定一致 |
