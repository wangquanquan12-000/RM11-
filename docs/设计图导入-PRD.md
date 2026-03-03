# 设计图导入 · 产品需求文档

> **功能定位**：在「项目记忆」Tab 新增「导入设计图」入口，与「导入全回归测试用例」并列，将设计图的视觉信息转化为结构化文本描述，作为 Agent 生成测试用例时的 UI 背景参考。
>
> **创建日期**：2026-03-XX

---

## 一、背景与目标

### 1.1 为什么需要导入设计图

测试用例的质量与 UI 设计强相关：
- Agent 缺乏对界面控件、交互层级、状态变化的感知，生成的用例容易遗漏 UI 细节（如按钮置灰、弹窗层级、Toast 时机）；
- 现有项目记忆仅支持文本（需求文档、全回归表格），设计图是独立的信息维度，需要补入。

### 1.2 目标

| 目标 | 说明 |
|------|------|
| 支持上传设计图 | 接受 PNG / JPG / JPEG / PDF（Figma 导出的常用格式） |
| 自动提取结构化描述 | 通过 Gemini Vision 分析图中 UI 组件、交互状态、文案，生成结构化文本 |
| 入库与去重 | 与全回归用例同等待遇，走 `add_entry_with_dedup` 流程，哈希去重 |
| Agent 可参考 | 描述文本存入 memory_store，`get_recent_for_agent()` 时可被 4 个 Agent 读取 |

---

## 二、功能详细定义

### 2.1 入口位置

「项目记忆」Tab → 「导入全回归测试用例」下方 → 新增「导入设计图」区块。

```
项目记忆 Tab 内容结构（从上到下）：
  ① Agent 知识库
  ② 搜索
  ③ 导入历史时间轴
  ④ 导入需求（粘贴）            ← 现有
  ⑤ 导入全回归测试用例          ← 现有
  ⑥ 导入设计图                  ← 新增
  ⑦ 项目记忆摘要（高级）        ← 现有
```

### 2.2 用户操作流程

```
用户上传设计图（支持多图）
        │
        ▼
系统计算图片 SHA-256 哈希 → 哈希已存在 → 提示"设计图未变更，已跳过"
        │（哈希不存在）
        ▼
st.spinner("正在解析设计图...")
        │
        ▼
调用 Gemini Vision，发送图片 + 结构化 Prompt
        │
        ▼
返回结构化文本描述（包含：模块名称、页面层级、组件列表、交互状态、关键文案）
        │
        ▼
以描述文本调用 add_entry_with_dedup("design_mockup", text, title=文件名)
        │
        ▼
触发 Librarian Agent 生成 150 字摘要（与现有流程一致）
        │
        ▼
st.success("设计图已解析导入，Agent 下次生成用例时将参考。")
```

### 2.3 支持的文件格式

| 格式 | 说明 | 是否支持 |
|------|------|:---:|
| PNG | Figma、Sketch 导出主格式 | 支持 |
| JPG / JPEG | 截图类 | 支持 |
| PDF | Figma 多画板导出 | 支持（按页逐一解析，最多 5 页） |

**不支持格式**：`.fig`（Figma 源文件）、`.sketch`（Sketch 源文件）、`.psd`（Photoshop）—— 这些格式需要专用 SDK，风险过高，当前阶段不做。

### 2.4 单次上传限制

| 限制项 | 值 | 说明 |
|--------|-----|------|
| 单文件最大 | 10MB | 与现有上传逻辑一致 |
| 单次最多文件数 | 5 个 | 避免 Gemini Vision 并发超限 |
| PDF 最多页数 | 5 页 | 超出则只处理前 5 页，用户提示 |

### 2.5 Gemini Vision 解析 Prompt

```
你是一位资深 UI/UX 测试工程师。请分析这张界面设计图，输出结构化的描述，
供自动化测试用例生成系统参考。

输出格式：
## 页面 / 模块名称
（根据图中标题或推断得出）

## 页面层级与布局
（描述顶栏、底栏、侧栏、主内容区的大体布局）

## 关键 UI 组件
（逐一列出按钮、输入框、列表项、弹窗、Toast 等，说明其标签文案和状态）

## 可见的交互入口
（可点击/可操作的元素：如 Tab 切换、下拉菜单、长按操作等）

## 状态与条件展示
（不同数据状态下界面的差异：空态、加载态、错误态、权限不足态等，如图中有体现）

## 关键文案
（图中重要的 UI 文案、错误提示、占位符文字等）

要求：只输出上述结构，不加多余说明。
```

### 2.6 store_type 定义

新增 `source_type = "design_mockup"`，与已有类型并列：

| source_type | 含义 |
|-------------|------|
| `manual` | 粘贴导入的需求文档 |
| `test_cases` | 全回归测试用例 |
| `design_mockup` | 设计图（本次新增） |
| `run_summary` | 运行产出摘要（历史） |

### 2.7 Agent 上下文注入

在 `crew_test.py` 的 `get_recent_for_agent()` 调用中，`design_mockup` 类型自动纳入：

```python
# 现有调用（crew_test.py 第 854 行）
store_ctx = get_recent_for_agent(limit=10, demand_only=True, include_test_cases=True)
```

需新增 `include_design_mockup=True` 参数（默认 True），或直接在 `DEMAND_SOURCE_TYPES` 元组中加入 `"design_mockup"`，使其被 Agent 默认读取。

---

## 三、架构约束与风险推演

### 3.1 云端支持性分析

| 能力 | 是否支持 | 说明 |
|------|:--------:|------|
| Streamlit Cloud 文件上传 | 支持 | `st.file_uploader` 原生支持图片 |
| Gemini Vision（langchain_google_genai） | 支持 | 已有依赖，无需新增 |
| 图片存储到服务器 | **不做** | 只存 Gemini 解析出的文本描述，不持久化图片字节 |
| openpyxl / docx | 无关 | 设计图解析不依赖这两个库 |
| sqlite3 / JSON 后端 | 兼容 | 存储的是文本，走现有 memory_store 流程 |

**结论**：架构上完全兼容云端，无新增硬依赖。

### 3.2 风险推演

| 风险 | 触发场景 | 缓解措施 |
|------|----------|----------|
| **Gemini Vision API Key 未配置** | 用户点击导入，key 为空 | 在调用前检查 key，st.error 提示，不进入 Vision 调用 |
| **图片尺寸过大导致 API 超时** | 上传了超高分辨率设计稿 | 客户端限制 10MB；服务端 try-except，超时提示"图片过大，建议压缩后重试" |
| **PDF 页数超限** | 导出了几十页的设计稿 PDF | 只取前 5 页并在 UI 提示"已只处理前 5 页" |
| **Gemini Vision 返回空或格式不符** | 图片内容无法识别（全黑/空白） | 检查返回是否为空；为空时提示"无法识别图中内容，请确认图片清晰度" |
| **多图并发超 Gemini 限速** | 一次上传 5 张图，快速并发调用 | 改为**串行处理**，每图间隔 1s，单图失败不影响其他图 |
| **哈希去重误判（不同图哈希相同）** | SHA-256 碰撞概率极低，可忽略 | 已有机制，无额外处理 |
| **旧版 langchain 不支持图片消息** | 部分低版本 langchain | 检查版本；退化方案：提示用户手动填写设计描述 |
| **重复导入同一图（哈希命中）** | 用户二次上传 | 正常提示"已跳过" |

### 3.3 与 sqlite3 风险的关系

- 设计图导入**不引入任何新库**，存储层完全走现有 memory_store（无论 sqlite 还是 JSON 后端）。
- Gemini Vision 调用在 try-except 内，失败只影响当前导入，不崩溃。
- 图片字节**不写入文件系统**，不存在路径权限问题。

---

## 四、UI 文案（新增部分）

需在 `config/ui_texts.yaml` 的 `memory_tab` 下补充：

```yaml
design_mockup_section: "导入设计图"
design_mockup_caption: "上传 Figma/截图等设计稿，Agent 将理解界面布局与交互细节。"
design_mockup_upload_label: "上传设计图（PNG / JPG / PDF，最多 5 个，单文件 ≤10MB）"
design_mockup_import_btn: "解析并导入"
design_mockup_parsing: "正在用 Gemini Vision 解析设计图…"
design_mockup_success: "设计图已解析导入，下次生成用例时 Agent 将参考。"
design_mockup_skipped: "设计图未变更，已跳过"
design_mockup_empty: "图片内容无法识别，请确认图片清晰度"
design_mockup_key_missing: "请先在设置中配置 Gemini API Key"
design_mockup_pdf_truncated: "PDF 超过 5 页，已只处理前 5 页"
design_mockup_parse_fail: "解析失败，请稍后重试"
```

---

## 五、验收标准

| 编号 | 验收项 |
|------|--------|
| AC1 | 上传 PNG/JPG 单张图，成功解析并在导入历史中看到条目，source_type 为 design_mockup |
| AC2 | 上传同一张图片，第二次提示"已跳过"，历史记录条数不增加 |
| AC3 | 上传 PDF（≤5 页），每页解析后合并入库 |
| AC4 | Gemini Key 未配置时，点击导入后弹出 st.error 提示，不崩溃 |
| AC5 | 图片解析成功后，150 字 Librarian 摘要在导入历史中展示 |
| AC6 | 4 个 Agent 生成用例时，design_mockup 描述文本出现在 project_context 中 |
| AC7 | memory_store 使用 JsonFileBackend（sqlite3 不可用）时，导入设计图流程正常 |

---

## 六、不做的事（范围边界）

- 不支持 Figma URL 直接导入（需 Figma API 授权，风险高，后续迭代）
- 不在界面展示图片缩略图（图片不持久化，展示文本描述即可）
- 不支持手动编辑 Gemini 解析结果（导入后如需修改，删除后重新导入）
- 不做图片与用例的直接关联追踪（后续 RAG 增强时可做）
