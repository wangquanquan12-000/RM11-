# 本地文件模式 · PRD

> **文档用途**：将「需求文档来源」与「生成用例输出」从 Quip 切换为本地文件目录模式。6.6 版本的需求从指定本地目录读取，生成用例也保存到该目录。
>
> **创建日期**：2025-03-02  
> **默认工作目录**：`/Users/wangqilong/Desktop/需求文档及测试用例/6.6`

---

## 一、需求概述

### 1.1 当前模式

- 需求文档：从 Quip 链接拉取
- 生成用例：导出到 Excel（output/）、Quip、Google Sheets

### 1.2 目标模式（本地文件）

- **需求文档（输入）**：从指定本地目录读取 **Word 文件（.docx）**
- **生成用例（输出）**：保存到同一目录，主要为 **Excel 文件**（.xlsx），另可保留 txt 全文
- **工作目录**：可配置，如 `/Users/wangqilong/Desktop/需求文档及测试用例/6.6`

---

## 二、范围与边界

### 2.1 在范围内

| 项目 | 说明 |
|------|------|
| 工作目录配置 | 支持通过配置文件或 UI 指定工作目录路径 |
| 需求文档读取 | 扫描工作目录下的 **Word 文件（.docx）**，支持多文件合并或选择单文件 |
| 生成用例输出 | Excel 与 txt 保存到工作目录，文件名含时间戳与需求标题 |
| 「生成用例」页 | 支持「本地文件」与「Quip」双模式切换 |
| 「项目记忆」 | 本地模式时可从工作目录导入需求到 memory_store |

### 2.2 不在范围内（本期）

| 项目 | 说明 |
|------|------|
| 完全移除 Quip | 保留 Quip 模式，与本地模式并存 |
| 工作目录内子目录规范 | 本期可扁平存储；后续可约定 `需求/`、`测试用例/` 子目录 |

---

## 三、目录结构约定

### 3.1 默认工作目录示例

```
/Users/wangqilong/Desktop/需求文档及测试用例/6.6/
├── 需求_xxx.docx         # 需求文档（Word，用户放入）
├── 需求_yyy.docx
├── 测试用例_20250302_143022.xlsx   # 生成产出（Excel）
├── 测试用例_20250302_143022.txt    # 可选，全文备份
└── ...
```

### 3.2 需求文档识别规则（输入）

- 扩展名：**`.docx`**（Word 文档）
- 可选：按文件名前缀过滤（如 `需求_`、`PRD_`），可配置
- 解析：使用 `python-docx` 提取段落文本

### 3.3 生成用例命名规则（输出）

- **Excel**：`测试用例_{需求标题简写}_{timestamp}.xlsx`（主输出）
- Txt：`测试用例_{需求标题简写}_{timestamp}.txt`（可选，全文备份）
- 若需求标题含非法文件名字符，替换为下划线

---

## 四、UI 与交互设计

### 4.1 「生成用例」页：输入源切换

| 模式 | 说明 | UI 表现 |
|------|------|----------|
| **Quip** | 从 Quip 链接拉取需求 | 输入框：Quip 文档链接（当前逻辑） |
| **本地文件** | 从工作目录读取需求 | 显示工作目录路径；支持「选择文件」或「合并全部需求」 |

**切换方式**：  
- 顶部增加「需求来源」单选：`Quip 链接` | `本地文件`
- 选「本地文件」时：
  - 展示工作目录路径（可编辑或从配置读取）
  - 列出该目录下的 **.docx（Word）** 文件，支持单选或多选
  - 或提供「合并目录下全部需求文档」选项

### 4.2 工作目录配置

- **配置位置**：`config/local_workspace.yaml` 或 `config/defaults.json` 增加 `workspace_path`
- **默认值**：`/Users/wangqilong/Desktop/需求文档及测试用例/6.6`
- **UI**：在「生成用例」页本地模式区域，或「设置」页增加「工作目录」输入框

### 4.3 输出保存逻辑

- 当选择「本地文件」模式时，`output_dir` 优先使用工作目录；否则使用 `output/`
- Excel 与 txt 写入工作目录
- 若目录不存在，自动创建（需防御目录遍历，限制在用户配置的父路径下）

---

## 五、数据流（逻辑）

### 5.1 读取需求（本地模式）

```
工作目录 → 扫描 .docx（Word）→ 用户选择（单文件/多文件/全部合并）
       → python-docx 提取文本 → content: str
       → demand_title: 文件名（去掉扩展名）或首个文件标题
```

### 5.2 生成与保存

```
content → run_pipeline(demand=content, output_dir=workspace_path, ...)
        → Excel: workspace_path/测试用例_{title}_{ts}.xlsx
        → Txt:   workspace_path/测试用例_{title}_{ts}.txt
```

---

## 六、与现有模块的关系

| 模块 | 影响 |
|------|------|
| pipeline_service | `run_quip_to_cases` 需支持 `demand` 直接传入，或新增 `run_local_demand_to_cases` |
| crew_test.run_pipeline | 已支持 `demand` 入参，`output_dir` 可传入工作目录 |
| 项目记忆 | 本地模式时可将工作目录下的需求导入 memory_store（可选） |
| 需求风险分析 | 文档来源可增加「工作目录下的文件」选项 |

---

## 七、安全与防御

| 项 | 说明 |
|------|------|
| 目录遍历 | 工作目录必须限定在配置的根路径下，禁止 `../` 逃逸 |
| 路径校验 | 使用 `os.path.abspath` + 白名单父路径校验 |
| 文件类型 | 仅读取 .docx（Word），不执行脚本；需依赖 `python-docx` |

---

## 八、验收标准

| 编号 | 验收项 |
|------|--------|
| AC1 | 可在「生成用例」页选择「本地文件」模式，并指定工作目录 |
| AC2 | 选择工作目录下的 .docx（Word）后，能正确解析并作为需求传入流水线 |
| AC3 | 生成完成后，Excel 与 txt 保存到工作目录，文件名符合命名规则 |
| AC4 | 工作目录可配置，默认支持 `/Users/wangqilong/Desktop/需求文档及测试用例/6.6` |
| AC5 | Quip 模式保留，两种模式可切换 |
| AC6 | 路径非法或目录不可写时，有明确错误提示 |

---

## 九、实现要点（供开发参考）

### 9.1 新增配置

```yaml
# config/local_workspace.yaml（新建）
workspace_path: "/Users/wangqilong/Desktop/需求文档及测试用例/6.6"
demand_extensions: [".docx"]   # Word 文档
```

### 9.2 新增服务函数

```python
def list_demand_files(workspace_path: str) -> list[dict]:
    """扫描工作目录，返回 [{path, name, size}, ...]"""

def load_demand_from_local(file_path: str) -> str:
    """从本地 Word 文件（.docx）读取需求文本，使用 python-docx 解析"""
```

### 9.3 UI 改造（生成用例页）

- 增加 `demand_source` 单选：`quip` | `local`
- 当 `local`：展示工作目录输入、文件列表、选择逻辑，调用 `load_demand_from_local`；`output_dir = workspace_path`
- 当 `quip`：保持现有逻辑

### 9.4 pipeline_service 改造

- `run_quip_to_cases` 保持 Quip 拉取逻辑
- 新增或扩展：当 `demand` 已直接传入且 `output_dir` 指定时，跳过 Quip 拉取，直接 `run_pipeline(demand=..., output_dir=...)`

### 9.5 Word 解析依赖

- 需安装：`pip install python-docx`
- 解析逻辑：`Document(file_path).paragraphs` 提取段落文本，拼接为字符串
