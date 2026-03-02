# 需求风险分析 · 独立功能 PRD

> **文档用途**：供开发实施「需求风险分析」独立功能。该功能仅调用 doubt_agent 对单份文档做风险评估，产出表格报告，**不参与四 Agent 协作流程**。
>
> **创建日期**：2025-03-02

---

## 一、业务价值与用户故事

| 项目 | 说明 |
|------|------|
| **业务价值** | 在跑四 Agent 生成用例前，可单独对一份需求文档做结构化风险评估，产出可查看/导出的表格，辅助人工评审、提前发现遗漏 |
| **用户故事** | 作为测试/产品，我希望在不执行完整四 Agent 流水线的前提下，对某份文档单独做风险分析，并以表格形式查看结果 |

---

## 二、功能边界

- **独立功能**：不参与四 Agent 协作，仅调用 doubt_agent（或等价分析 Agent）对文档做一次性分析
- **输入**：单份需求文档（Quip 链接拉取 / 粘贴内容 / 项目记忆中选择）
- **输出**：结构化表格（支持 Markdown 展示，可选导出 Excel）

---

## 三、表格结构与风险维度

表头固定为：**| 维度 | 模块 | 风险类型 | 风险概述 | 优先级建议 | 问题描述 | 建议/疑问 |**

三个分析维度（对应「维度」列取值）：

| 维度 | 说明 |
|------|------|
| **模糊性审查** | 找出文档中描述不清的词汇，确认 UI 交互细节是否缺失 |
| **逻辑冲突与遗漏** | 新老逻辑互斥、状态闭环、权限边界 |
| **极端场景推演** | 数值边界、并发场景 |

风险类型可选：功能 / 交互 / 权限 / 数据 / 性能 / 文案 / 兼容性 等。

---

## 四、UI 结构树（Streamlit 布局）

```
侧栏 / 工作台
  └─ 新增模块「需求风险分析」
        ├─ 文档来源（单选）
        │     ├─ Quip 链接（输入框 + 拉取）
        │     ├─ 粘贴内容（textarea）
        │     └─ 项目记忆（下拉选择近期文档）
        ├─ [生成风险报告] 按钮
        ├─ 加载中（spinner）
        └─ 结果区
              ├─ Markdown 表格展示
              └─ 导出 Excel（可选）
```

在 `config/workbench_apps.yaml` 中新增 `risk_report` 模块，并在主工作台增加对应入口。

---

## 五、状态机与 session_state

| 状态 | 变量 | 说明 |
|------|------|------|
| 初始 | `risk_report_doc_context` | 当前选中的文档内容 |
| 执行中 | `risk_report_running` | 是否正在生成 |
| 完成 | `risk_report_result` | 分析结果（Markdown 字符串） |
| 错误 | `risk_report_error` | 错误信息 |

---

## 六、异常分支

| 场景 | 处理 |
|------|------|
| 文档为空 | `st.warning("请先输入或拉取文档内容")` |
| Gemini API 超时/限流 | `st.error("分析超时，请稍后重试")`，允许重试 |
| 返回非表格 | 尝试解析 Markdown 表格；解析失败则展示原始文本并 `st.warning("未能解析为表格，展示原始输出")` |

---

## 七、实现方案

### 7.1 新增服务函数

在 `crew_test.py` 中新增，或新建 `risk_report_service.py`：

```python
def generate_risk_assessment_report(document_content: str, gemini_model: str = "") -> str:
    """
    独立调用 doubt_agent 对文档做需求 risk 分析，返回 Markdown 表格。
    不参与四 Agent 流水线。
    """
    if not (document_content or "").strip():
        raise ValueError("文档内容为空")

    from langchain_google_genai import ChatGoogleGenerativeAI
    import os

    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        raise ValueError("请先配置 GEMINI_API_KEY")

    model = gemini_model or os.environ.get("GEMINI_MODEL", "gemini-2.5-flash-lite")
    llm = ChatGoogleGenerativeAI(model=model, google_api_key=key, temperature=0.3)

    prompt = """你是一位资深需求分析师。请对以下需求文档进行深度扫描，产出《需求风险评估报告》。

必须按以下三个维度分析，并以 **Markdown 表格** 输出，表头固定为：
| 维度 | 模块 | 风险类型 | 风险概述 | 优先级建议 | 问题描述 | 建议/疑问 |

维度取值：模糊性审查、逻辑冲突与遗漏、极端场景推演。

要求：
1. **模糊性审查**：找出描述不清的词汇、缺失的 UI 交互细节。
2. **逻辑冲突与遗漏**：新老逻辑互斥、状态闭环、权限边界。
3. **极端场景推演**：数值边界、并发场景。

若某维度无明显问题，可写「无」；每条风险占一行。直接输出表格，不要多余说明。

【需求文档】
{document}
"""

    msg = llm.invoke(prompt.replace("{document}", document_content.strip()[:30000]))
    return (msg.content or "").strip()
```

### 7.2 UI 渲染函数

在 `app_ui.py` 中新增 `_render_module_risk_report(T, defaults)`，结构参考「文档问答」模块，包含：

- 文档来源选择（Quip / 粘贴 / 项目记忆）
- 生成按钮
- 结果展示（`st.markdown`）
- 可选：解析表格并导出 Excel（复用 `_parse_markdown_tables`、`_export_to_excel`）

### 7.3 配置

**config/workbench_apps.yaml** 新增：

```yaml
  - id: risk_report
    label_key: "risk_report.title"
    order: 3
    enabled: true
```

**config/ui_texts.yaml** 新增：

```yaml
risk_report:
  title: "需求风险分析"
  section_title: "需求风险分析"
  section_desc: "单独对文档做风险评估，产出表格报告，不参与四 Agent 流程。"
  doc_source: "文档来源"
  run_btn: "生成风险报告"
```

### 7.4 路由

在 `_render_main_app` 中增加 `risk_report` 模块的分支，调用 `_render_module_risk_report`。

---

## 八、验收标准（AC）

| AC | 说明 |
|----|------|
| AC1 | 可从 Quip / 粘贴 / 项目记忆中选择文档来源 |
| AC2 | 点击「生成风险报告」后，能展示 Markdown 表格结果 |
| AC3 | 表格包含列：维度、模块、风险类型、风险概述、优先级建议、问题描述、建议/疑问 |
| AC4 | 覆盖模糊性审查、逻辑冲突与遗漏、极端场景推演三个维度 |
| AC5 | 文档为空或拉取失败时，有明确提示且不崩溃 |
| AC6 | 该功能不调用 `run_pipeline`，不参与四 Agent 协作 |

---

## 九、交付前自检

| 自检项 | 说明 |
|--------|------|
| 扩展性 | 文案、模块配置均来自 YAML |
| 异常兜底 | 文档空、API 失败、非表格均有处理 |
| 组件复用 | 复用 `load_demand_from_quip`、`_parse_markdown_tables` 等 |
| 状态隔离 | 使用 `st.session_state` 存储结果与错误 |
| MVC | 分析逻辑在 service 层，UI 仅负责展示 |

---

## 十、doubt_agent 提示词规范

**开发说明**：仅替换 `config/agents.yaml` 中 `doubt_agent` 的 `backstory` 字段，`id` / `role` / `goal` / `tasks` 保持不变。

```yaml
agents:
  - id: doubt_agent
    role: "Document Analyst"
    goal: "文档分析师（The Auditor）找茬专家、逻辑推演者。在写用例前，把需求文档"撕碎"，找出所有可能导致测试阻塞或上线故障的坑。"
    backstory: |
      【角色设定】
      你是一位在Fambase项目深耕多年的【资深需求分析师/QA Lead】。你的核心任务是通过"攻击性阅读"撕碎产品需求文档(PRD)，在测试设计开始前，精准挖出所有可能导致测试阻塞或线上故障的逻辑地雷。

      【审查维度】（必须严格执行）
      请基于Fambase作为【群组聊天核心社交生态】的业务背景（涵盖：群大厅聊天、群内Live直播、群主/Performer开播机制、成员发言互动、充值与礼物打赏体系等），从以下四大维度进行深度扫描：

      1. 模糊性审查(Ambiguity Check)
      - 文案陷阱：揪出文档中"同之前"、"样式待定"、"通用交互"等指代不明的描述。
      - UI闭环缺失：核查是否遗漏了异常态展示（如：Loading态、空数据态、断网态、超长字符截断显示）。

      2. 逻辑冲突与回归风险(Conflict & Regression)
      - 核心底座护航：新功能的加入绝不能破坏Fambase"群组聊天"与"群内直播"的基础双线通信（例如：直播间的高频送礼动画/Socket消息不能导致群大厅聊天卡顿或消息丢失）。
      - 状态机闭环：生命周期是否完整？（如：断网/杀进程后，本地状态是否正确持久化保存？群与直播间的联动状态是否一致？）。
      - 权限与身份边界：多角色（群主/Performer/普通成员/游客）在同一群组或直播间内的操作阻断逻辑是否明确。

      3. 极端与边界场景推演(Edge Cases)
      - 数值与并发：临界值（0、1、最大值、负Coins余额）、多端同时操作、极速连续点击。
      - 网络与硬件：弱网降级、网络彻底断开与重连、退后台与杀进程后的定时器销毁或状态接续。

      4. 隐性数据链路(Data Tracking)
      - 前后端一致性：前端触发的核心动作（如充值、送礼扣除Coins），V3后台或对应的数据看板是否有严密的数据校验与日志对齐逻辑。

      【排版与视觉红线】（最高纪律）
      - 中英/数字/符号边界绝对零空格：中文字符与英文、数字或符号之间严禁出现空格（例如：必须输出Fambase项目，严禁输出Fambase 项目）。
      - 英文保留呼吸感：英文短语内部原始空格必须保留（例如：Ambiguity Check）。
      - 绝对去动词化：在输出问题与建议时，描述客观状态，剔除无意义的过程动词（禁用"点击查看是否""测试用户能否"等）。

      【输出格式规范】
      请以结构化列表形式输出《需求风险评估报告》，如果没有发现某类风险，也必须清晰列出你认为最复杂的3个"逻辑确认点"。输出格式必须如下：

      ### 模块名称：[填写具体模块]
      【风险类型】：[如：逻辑冲突/极端场景]
      【风险概述】：[一句话极简概括对象与状态]
      【优先级建议】：[P0阻断风险/P1逻辑遗漏/P2体验瑕疵]
      【问题描述】：[详细说明文档中逻辑缺失或未定义清楚的具体漏洞]
      【建议/疑问】：[给出QA视角的解决方案或向PM提出的确认问题]
```
