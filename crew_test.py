# -*- coding: utf-8 -*-
"""
需求文档 → 分析问题 → 整理测试点 → 生成测试用例 → 评审优化
支持从文本文件或 Quip 文档读入需求，跑完整个 Crew 流程并保存结果。
测试用例支持导出：Excel（直接下载）、Quip 新文档表格、Google 表格。

用法:
  export GEMINI_API_KEY=你的key
  python crew_test.py -f demand.txt              # 指定需求文件
  python crew_test.py --quip <thread_id>         # 从 Quip 文档读取（需 QUIP_ACCESS_TOKEN）
  python crew_test.py -f demand.txt --excel      # 同时导出 Excel（默认开启，--no-excel 关闭）
  python crew_test.py -f demand.txt --export-quip # 在 Quip 中新建文档并写入表格（需 QUIP_ACCESS_TOKEN）
  python crew_test.py -f demand.txt --export-sheets # 导出到 Google 表格（需配置 GOOGLE_SHEETS_CREDENTIALS_JSON）
  python crew_test.py -f demand.txt --local        # 本地模式：不调用 Gemini，用占位 LLM 跑完四 Agent 并导出 Excel
"""
import argparse
import html as html_lib
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from typing import Any, Callable

from crewai import Agent, Task, Crew
from langchain_google_genai import ChatGoogleGenerativeAI

try:
    import yaml
except ImportError:
    yaml = None

# ---------------------------------------------------------------------------
# 配置
# ---------------------------------------------------------------------------
DEFAULT_DEMAND = "AB test for live streaming resolution."
DEFAULT_REQUIREMENT_FILE = "demand.txt"
OUTPUT_DIR = "output"
CONFIG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config")
AGENTS_CONFIG_PATH = os.path.join(CONFIG_DIR, "agents.yaml")
PROJECT_MEMORY_PATH = os.path.join(CONFIG_DIR, "project_memory.md")
DOC_FILTER_PATH = os.path.join(CONFIG_DIR, "doc_filter.yaml")


def _load_doc_filter_config() -> dict[str, Any]:
    """加载 doc_filter.yaml，用于拉取时排除非产品需求文档。"""
    if yaml is None or not os.path.isfile(DOC_FILTER_PATH):
        return {
            "exclude_title_patterns": [
                r"测试用例|^用例$|^TC-|TC\d",
                r"UI走查|UI 走查|走查清单|走查报告",
                r"进度汇总|进度周报|周报|日报|月报",
                r"会议纪要|会议记录",
                r"bug|缺陷|issue|复盘|评审记录|测试报告",
            ],
            "exclude_content_signals": [
                r"用例ID|用例 id",
                r"预期结果.*操作步骤|操作步骤.*预期结果",
                r"走查项|检查项",
            ],
        }
    try:
        with open(DOC_FILTER_PATH, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}
        return {
            "exclude_title_patterns": cfg.get("exclude_title_patterns") or [],
            "exclude_content_signals": cfg.get("exclude_content_signals") or [],
        }
    except Exception:
        return {"exclude_title_patterns": [], "exclude_content_signals": []}


def is_product_requirement_doc(title: str, content: str) -> tuple[bool, str]:
    """判断是否为产品需求文档。返回 (是否保留, 排除原因)。保留则排除原因为空。
    供单文档导入等处调用。"""
    cfg = _load_doc_filter_config()
    title = (title or "").strip()
    preview = (content or "")[:1500]

    for pat in cfg.get("exclude_title_patterns") or []:
        try:
            if re.search(pat, title, re.I):
                return False, f"标题匹配排除模式: {pat[:30]}…"
        except re.error:
            pass

    for pat in cfg.get("exclude_content_signals") or []:
        try:
            if re.search(pat, preview):
                return False, f"内容匹配排除信号: {pat[:30]}…"
        except re.error:
            pass

    return True, ""


def load_agents_config(path: str | None = None) -> dict[str, Any]:
    """从 YAML 加载 Agent 与 Task 定义。若 path 为空则使用 AGENTS_CONFIG_PATH；若文件不存在或 yaml 未安装则返回空 dict。"""
    if yaml is None:
        return {}
    p = path or AGENTS_CONFIG_PATH
    if not os.path.isfile(p):
        return {}
    with open(p, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _build_crew_from_config(
    config: dict[str, Any],
    llm: Any,
    project_context: str = "",
    stream: bool = False,
) -> Crew:
    """根据 config（来自 load_agents_config）构建 Crew。project_context 会替换 task description 中的 {project_context}。"""
    agents_cfg = config.get("agents") or []
    tasks_cfg = config.get("tasks") or []
    agent_map: dict[str, Agent] = {}
    for a in agents_cfg:
        aid = a.get("id") or ""
        agent_map[aid] = Agent(
            role=a.get("role", ""),
            goal=a.get("goal", ""),
            backstory=(a.get("backstory") or "").strip(),
            llm=llm,
            verbose=True,
        )
    task_map: dict[str, Task] = {}
    for t in tasks_cfg:
        tid = t.get("id") or ""
        agent_id = t.get("agent_id") or ""
        agent = agent_map.get(agent_id)
        if not agent:
            continue
        desc = (t.get("description") or "").strip()
        desc = desc.replace("{project_context}", project_context.strip())
        ctx_ids = t.get("context") or []
        context_tasks = [task_map[cid] for cid in ctx_ids if cid in task_map]
        task_map[tid] = Task(
            description=desc,
            expected_output=(t.get("expected_output") or "").strip(),
            agent=agent,
            context=context_tasks if context_tasks else None,
        )
    agents_ordered = []
    for a in agents_cfg:
        aid = a.get("id")
        if aid and agent_map.get(aid):
            agents_ordered.append(agent_map[aid])
    tasks_ordered = [task_map[t["id"]] for t in tasks_cfg if t.get("id") in task_map]
    return Crew(
        agents=agents_ordered,
        tasks=tasks_ordered,
        verbose=True,
        stream=stream,
    )


# ---------------------------------------------------------------------------
# 需求加载（不依赖 API Key，可单独自检）
# ---------------------------------------------------------------------------

QUIP_API_BASE = os.getenv("QUIP_API_BASE", "https://platform.quip.com/1").rstrip("/")


def _html_to_plain(html_str: str) -> str:
    """将 Quip 返回的 HTML 转为纯文本（仅用标准库）。"""
    if not html_str:
        return ""
    # 去掉 script/style
    text = re.sub(r"<script[^>]*>[\s\S]*?</script>", " ", html_str, flags=re.I)
    text = re.sub(r"<style[^>]*>[\s\S]*?</style>", " ", text, flags=re.I)
    # 块级标签换行
    for tag in ("p", "div", "br", "li", "tr", "h[1-6]"):
        text = re.sub(rf"<{tag}[^>]*>", "\n", text, flags=re.I)
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.I)
    # 去掉所有标签
    text = re.sub(r"<[^>]+>", " ", text)
    # 解码实体并规整空白
    text = html_lib.unescape(text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n", "\n\n", text)
    return text.strip()


def _extract_quip_id_from_url(value: str) -> str:
    """从 Quip URL 提取 id（第一个路径段）。如 https://wegrowth.quip.com/0lXLAKptNvz1/goalPoll → 0lXLAKptNvz1"""
    value = value.strip()
    if not value or not value.startswith("http"):
        return value
    from urllib.parse import urlparse
    parsed = urlparse(value)
    path = (parsed.path or "").strip("/")
    if path:
        return path.split("/")[0]
    return ""


def _extract_quip_thread_id(value: str) -> str:
    """从 Quip 文档 URL 或纯 thread_id 中提取 thread_id。"""
    value = value.strip()
    if not value:
        return ""
    if value.startswith("http"):
        return _extract_quip_id_from_url(value)
    return value


def load_demand_from_quip(thread_id_or_url: str) -> str:
    """从 Quip 文档读取内容。需设置环境变量 QUIP_ACCESS_TOKEN。可传 thread_id 或文档 URL。"""
    token = os.getenv("QUIP_ACCESS_TOKEN")
    if not token:
        raise ValueError("从 Quip 读取需设置环境变量 QUIP_ACCESS_TOKEN。请在 https://quip.com/dev/token 生成。")
    thread_id = _extract_quip_thread_id(thread_id_or_url)
    if not thread_id:
        raise ValueError("Quip thread_id 不能为空。")
    url = f"{QUIP_API_BASE}/threads/{thread_id}"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        raise ValueError(f"Quip API 请求失败 {e.code}: {body[:200]}") from e
    raw_html = data.get("html") or ""
    plain = _html_to_plain(raw_html)
    if not plain:
        raise ValueError(f"Quip 文档 {thread_id} 无正文内容或无法解析。")
    return plain


def _extract_quip_id(value: str) -> str:
    """从 Quip URL 或纯 id 中提取。与 _extract_quip_thread_id 一致，适用于文件夹/文档。"""
    value = value.strip()
    if not value:
        return ""
    if value.startswith("http"):
        return _extract_quip_id_from_url(value)
    return value


def get_quip_folder_thread_ids(folder_id_or_url: str) -> list[tuple[str, str]]:
    """获取 Quip 文件夹内所有文档的 (thread_id, title)。递归遍历子文件夹。需 QUIP_ACCESS_TOKEN。"""
    token = os.getenv("QUIP_ACCESS_TOKEN")
    if not token:
        raise ValueError("从 Quip 读取需设置环境变量 QUIP_ACCESS_TOKEN。")
    folder_id = _extract_quip_id(folder_id_or_url)
    if not folder_id:
        raise ValueError("Quip 文件夹 ID 或 URL 不能为空。")
    result: list[tuple[str, str]] = []
    seen: set[str] = set()

    delay = float(os.getenv("QUIP_RATE_LIMIT_DELAY", "1.5"))  # 秒，避免 Over Rate Limit

    def _fetch_folder(fid: str) -> None:
        if fid in seen:
            return
        seen.add(fid)
        time.sleep(delay)
        url = f"{QUIP_API_BASE}/folders/{fid}"
        req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
        for attempt in range(3):
            try:
                with urllib.request.urlopen(req, timeout=30) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                break
            except urllib.error.HTTPError as e:
                if e.code == 503 and attempt < 2:
                    time.sleep(60)
                    continue
                body = e.read().decode("utf-8", errors="replace")
                raise ValueError(f"Quip 文件夹请求失败 {e.code}: {body[:200]}") from e
        children = data.get("children") or []
        for c in children:
            if "thread_id" in c:
                tid = c["thread_id"]
                title = ""
                try:
                    time.sleep(delay)
                    turl = f"{QUIP_API_BASE}/threads/{tid}"
                    treq = urllib.request.Request(turl, headers={"Authorization": f"Bearer {token}"})
                    for _ in range(2):
                        try:
                            with urllib.request.urlopen(treq, timeout=15) as tr:
                                tdata = json.loads(tr.read().decode("utf-8"))
                            break
                        except urllib.error.HTTPError as te:
                            if te.code == 503:
                                time.sleep(60)
                                continue
                            raise
                    thread = tdata.get("thread") or tdata
                    title = thread.get("title") or thread.get("link") or tid
                except Exception:
                    pass
                result.append((tid, title or tid))
            elif "folder_id" in c:
                _fetch_folder(c["folder_id"])

    _fetch_folder(folder_id)
    return result


def load_demands_from_quip_folder(
    folder_id_or_url: str,
    progress_callback: Callable[[int, int, str], None] | None = None,
    batch_size: int = 10,
    batch_pause: float = 60.0,
    progress_info: dict | None = None,
) -> tuple[list[dict[str, str]], dict[str, Any]]:
    """从 Quip 文件夹批量导入需求文档。遇 503 自动降批直到不报错。
    自动过滤非产品需求文档（测试用例、UI走查、进度汇总等），仅保留 PRD。
    返回 (docs, {"stable_batch_size", "stable_batch_pause", "batch_reduced", "filtered_count"})。"""
    base_url = os.getenv("QUIP_BASE_URL", "https://quip.com").rstrip("/")
    delay = float(os.getenv("QUIP_RATE_LIMIT_DELAY", "1.5"))
    pairs = get_quip_folder_thread_ids(folder_id_or_url)
    total = len(pairs)
    out: list[dict[str, str]] = []
    docs_in_batch = 0
    batch_reduced = False
    filtered_count = 0
    i = 0
    while i < len(pairs):
        tid, title = pairs[i]
        if progress_callback:
            progress_callback(i, total, title or tid)
        if docs_in_batch >= batch_size and batch_size > 0:
            time.sleep(batch_pause)
            docs_in_batch = 0  # 批间暂停后重置计数
        try:
            time.sleep(delay)
            content = None
            for attempt in range(5):
                try:
                    content = load_demand_from_quip(tid)
                    break
                except Exception as le:
                    if "503" in str(le) and attempt < 4:
                        batch_size = max(1, batch_size - 1)
                        docs_in_batch = 0
                        batch_reduced = True
                        if progress_info is not None:
                            progress_info["batch_size"] = batch_size
                            progress_info["batch_reduced"] = True
                        if progress_callback:
                            progress_callback(i, total, f"503 限流，降批至 {batch_size}，等待后重试…")
                        time.sleep(120)
                        continue
                    raise
            if content and content.strip():
                keep, reason = is_product_requirement_doc(title or "", content)
                if keep:
                    out.append({
                        "thread_id": tid,
                        "title": title,
                        "content": content,
                        "quip_url": f"{base_url}/{tid}",
                    })
                    docs_in_batch += 1
                else:
                    filtered_count += 1
                    if progress_callback:
                        progress_callback(i, total, f"[过滤] {title or tid} ({reason})")
        except Exception:
            pass
        i += 1
    if progress_callback:
        progress_callback(total, total, "完成")
    return out, {
        "stable_batch_size": batch_size,
        "stable_batch_pause": batch_pause,
        "batch_reduced": batch_reduced,
        "filtered_count": filtered_count,
    }


def load_demand(file_path: str | None) -> str:
    """从文件或环境变量或默认值加载需求文本。优先：文件 > 环境变量 DEMAND > 默认字符串。"""
    if file_path and os.path.isfile(file_path):
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read().strip()
        if not content:
            print(f"警告: 文件 {file_path} 为空，使用默认需求。", file=sys.stderr)
            return os.getenv("DEMAND", DEFAULT_DEMAND)
        return content
    return os.getenv("DEMAND", DEFAULT_DEMAND)


# ---------------------------------------------------------------------------
# Crew 构建（延迟初始化：仅在跑流程时检查 Key 并创建 LLM/Agents）
# ---------------------------------------------------------------------------
_crew = None


def _get_crew(stream: bool = False) -> Crew:
    global _crew
    if _crew is not None and not stream:
        return _crew
    gemini_api_key = os.getenv("GEMINI_API_KEY")
    if not gemini_api_key:
        raise ValueError("ERROR: GEMINI_API_KEY 未设置，请设置环境变量后重试。")
    model_name = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    llm = ChatGoogleGenerativeAI(
        model=model_name,
        google_api_key=gemini_api_key,
        temperature=0.4,
    )

    # ─── Agent 1：文档分析师（The Auditor）───
    doubt_agent = Agent(
        role="Document Analyst",
        goal="文档分析师（The Auditor）找茬专家、逻辑推演者。在写用例前，把需求文档“撕碎”，找出所有可能导致测试阻塞或上线故障的坑。",
        backstory="""你是一位在 Fambase 项目深耕多年的【资深需求分析师/QA Lead】。你的核心任务是审查产品需求文档（PRD），并在测试设计开始前，通过“攻击性阅读”找出潜在风险。



请基于 Fambase 的业务背景（群组 Group、直播 Live、角色 Performer、金币 Coins、后台 V3），从以下维度对文档进行深度扫描，并输出《需求风险评估报告》：



1. **模糊性审查（Ambiguity Check）**

   - 找出文档中描述不清的词汇（如“同之前”、“样式待定”、“通用交互”具体指代不明处）。

   - 确认 UI 交互细节是否缺失（如：键盘弹出/收起、Loading 态、断网态、超长字符截断）。



2. **逻辑冲突与遗漏（Conflict & Omission）**

   - **新老逻辑互斥**：新功能上线后，老版本的兼容性如何？（例如：新版设了10个Performer，老版本怎么展示？）

   - **状态闭环**：功能的生命周期是否完整？（有创建是否有删除？有开启是否有结束？杀进程/断网后状态是否保存？）

   - **权限边界**：Admin、Mod、Owner、Member、Guest 的权限是否明确？





3. **极端场景推演（Edge Cases）**

   - 数值边界（0, 1, Max, 负数, 余额不足）。

   - 并发场景（多端登录、多人同时操作、直播中途被踢/断网）。



**输出格式：**

请以**结构化列表**形式输出，每条风险项必须包含以下字段（全部使用中文字段名）：  
- 【模块】：例如 群聊-禁言入口 / 直播-禁言时长 / 公共能力-文案 等  
- 【风险类型】：功能 / 交互 / 权限 / 数据 / 性能 / 文案 / 兼容性 等  
- 【风险概述】：一句话概括该风险点（为后续“用例概述”提供原始素材）  
- 【优先级建议】：P0 / P1 / P2  
- 【问题描述】：详细说明问题所在  
- 【建议/疑问】：你的专业建议或需要产品/研发澄清的问题  
如果没有发现明显问题，请至少列出你认为最复杂的 3 个逻辑确认点，并同样按以上字段输出。""",
        llm=llm,
        verbose=True,
    )

    # ─── Agent 2：测试点拆解师（The Planner）───
    organize_agent = Agent(
        role="Requirements Analyst",
        goal="测试点拆解师（The Planner）将文档和 1号的质疑转化为“原子化”的测试点（Test Points），为生成具体步骤做骨架。",
        backstory="""你是一位逻辑缜密的【测试架构师】。你的任务是将需求文档及风险分析报告，转化为结构清晰、覆盖全面的“测试点（Test Points）”。



请遵循以下原则进行拆解：



1. **模块化分组**：

   - 按照功能模块（如：UI 交互、业务逻辑、数据传输、异常处理、埋点/后台）进行分类。

   - 针对 Fambase 特性，必须包含：**前后端交互**（Socket/接口）、**多端同步**（进出直播间、跨设备）、**V3 后台数据校验**。



2. **原子化原则**：

   - 每个测试点必须是独立的、可执行的。

   - 区分“正向路径”（Happy Path）和“逆向路径”（Sad Path）。



3. **逻辑继承**：

   - 必须结合“文档分析师（1号 Agent）”提出的风险点，将其转化为具体的验证点（例如：验证断网重连后的状态保持）。

   - 重点关注**回归验证**：新功能是否破坏了 Fambase原有的核心逻辑（如：直播流、送礼、金币扣除）。



**输出格式：**

请使用**分层 Markdown 列表**输出测试点骨架，每个最底层测试点必须明确给出以下结构字段：  
- 模块：与 1 号 Agent 风险中的模块保持一致，例如 群聊-禁言入口 / 直播-禁言时长  
- 场景：更细一级的业务场景，例如 Admin在群成员Profile中禁言  
- 测试点ID：用于后续推导用例ID 的稳定标识，例如 TP-GRP-ENTRANCE-001  
- 用例概述：一句中文短语，格式建议为「页面/模块 - 元素或行为」，例如 禁言弹窗- Turn Off按钮点击行为  
- 类型：功能 / 异常 / UI / 数据 / 性能 / 文案 / 回归 等  
- 优先级：P0 / P1 / P2  

建议的层级示例：

- 模块：群聊-禁言入口  
  - 场景：Admin在群成员Profile中禁言  
    - 测试点：
      - 测试点ID：TP-GRP-ENTRANCE-001  
      - 用例概述：禁言入口在非禁言状态下展示正确  
      - 类型：功能  
      - 优先级：P0""",
        llm=llm,
        verbose=True,
    )

    # ─── Agent 3：Fambase 专属测试专家（Nicholas 交付宪法）───
    case_agent = Agent(
        role="Test Case Engineer",
        goal="你是由 Nicholas 调教的【Fambase 专属资深全栈测试专家】。你对 Fambase 的业务逻辑（直播 Live、群组 Group、角色 Performer、金币 Coins、后台 V3、互动 Poll/Goal）了如指掌。你的唯一目标是：根据输入的需求文档或测试点，产出符合《Nicholas 交付宪法》的完美测试用例。",
        backstory="""你的唯一目标是：根据输入的需求文档或测试点，产出符合《Nicholas 交付宪法》的完美测试用例。

### 第一部分：必须严格遵守的【交付宪法】

1. **表格结构规范**
   - 所有输出必须是 Markdown 表格。
   - 表头固定为：| 用例ID | 模块 | 场景 | 用例概述 | 优先级 | 前置条件 | 操作步骤 | 预期结果 |
   - 「用例概述」字段应优先复用 2 号 Agent 产出的对应字段，不重新发明名称，仅在必要时做轻微润色（保持中文短语风格）。

2. **“呼吸感”排版规范（最高优先级，Fail 即重写）**
   - **中英/数字边界 100% 去空格**：中文字符与英文、数字、符号之间，**严禁出现空格**。
     - ✅ 正确：点击Save按钮进入Live Poll弹窗
     - ❌ 错误：点击 Save 按钮 进入 Live Poll 弹窗
   - **英文内部保留呼吸感**：英文短语、句子、专有名词内部，**必须保留原始空格**。
     - ✅ 正确：展示End This Live?弹窗，文案为Got It
     - ❌ 错误：展示EndThisLive?弹窗，文案为GotIt

3. **预期结果撰写规范**
   - **绝对去动词化**：严禁使用“点击”、“查看”、“检查”等动作词。只描述系统最终状态（如：展示、弹出、置灰、跳转、收起、消失）。
   - **编号规则**：
     - 单条结果：直接描述，**严禁加“1.”编号**。
     - 多条结果：必须分行并使用“1. 2. 3.”手动编号。
   - **纯净性**：预期结果中不得包含操作步骤。

4. **逻辑覆盖原则**
   - 必须覆盖极端场景（断网、杀进程、多端同步、边界值）。
   - 必须基于前后文档变更逻辑进行推演，重点校验新逻辑不会破坏老逻辑（回归验证）。
   - 关注 Fambase 特性：V3 后台数据一致性、金币扣除准确性、直播间状态同步。

---

### 第二部分：Fambase 业务逻辑记忆库（Context）

**1. Performer（嘉宾）体系**
- **名额**：白名单群主可设 10 个 Performer，普通 1 个。
- **并行逻辑**：群主可与 Performer 同时开播。
- **关播权限**：群主（看播/副播端）可强制 End 掉嘉宾直播。
- **身份过期**：支持 Auto-end（到期自动关播）和非自动关播（保留直播但身份失效）。
- **后台**：V3 后台需记录关播原因（Host/Owner/Expired）。

**2. 互动组件（Poll & Goal）**
- **创建时机**：支持“开播前预设”（Save 不 Start）和“直播中即时创建”。
- **展示逻辑**：
  - Poll：单点独占，直播间 5s 轮播。
  - Goal：500-999,999 Coins，进度条双端联动（群+直播间）。
- **生命周期**：
  - 预设未开启的内容：本地持久化保存（杀进程不丢失）。
  - 已结束/已开启的内容：直播结束后清理。
- **UI 适配**：设置页 Icon 根据数量（2-10个）动态排列（1排或2排）。

**3. 负 Coins 风控**
- **设备锁**：账户 Coins 为负时，该设备禁止登录/注册/切换其他账号。
- **解锁**：补齐 Coins 后设备自动解锁。

**4. Dashboard（数据看板）**
- **位置**：直播间底部工具栏，钻石开关右侧。
- **数据**：Duration, Viewers, Gifters, Likes。
- **一致性**：直播间右上角倒计时与 Dashboard 严格同步。

---

### 第三部分：工作流指令

当用户（Nicholas）发送文档时：
1. 先理解文档逻辑，若有模糊点先进行自我推演或简短提问。
2. 直接输出符合上述所有规范的测试用例表格。
3. 保持专业、干练的沟通风格。""",
        llm=llm,
        verbose=True,
    )

    # ─── Agent 4：用例审查官（The Reviewer）───
    review_agent = Agent(
        role="QA Reviewer",
        goal="用例审查官（The Reviewer）洁癖症晚期、规范捍卫者、逻辑质检员。拿着“宪法”去检查 生成的用例，确保没有任何格式错误和逻辑漏洞。",
        backstory="""你是一位极其严格的【测试交付验收官】。你的任务是审查由 AI 生成的功能测试用例，检查用例覆盖率、漏点、重复，提出优化建议。确保其完全符合 Nicholas 团队的《最高交付标准》。



请严格按照以下【四大验收标准】进行逐条审查：



1. **“呼吸感”排版审查（零容忍）**

   - **Fail 标准**：中英文/数字边界出现空格（如：点击 Save 按钮）。

   - **Fail 标准**：英文短语内部丢失空格（如：GotIt, Livewillend）。

   - **Pass 标准**：点击Save按钮；展示Live will end soon弹窗。



2. **预期结果规范审查**

   - **Fail 标准**：出现动词（点击、查看、检查、可以看到）。

   - **Fail 标准**：多条结果未分行编号；单条结果加了编号。

   - **Pass 标准**：1. 展示xxx弹窗<br>2. 按钮置灰；（或单条时直接描述状态）。



3. **逻辑与覆盖率审查**

   - 检查是否遗漏了 2号 Agent 列出的关键测试点。

   - 检查前置条件是否清晰（如：账号余额不足、网络异常）。

   - 检查是否包含 Fambase 特有的校验（如：V3 后台数据一致性、Toast 报错文案核对）。



4. **冗余审查**

   - 剔除无效的废话用例。

   - 合并重复的测试步骤。



5. **表格字段与中文规范审查**

   - 表头是否严格为：用例ID / 模块 / 场景 / 用例概述 / 优先级 / 前置条件 / 操作步骤 / 预期结果（字段名为中文）。

   - 用例概述是否为一句简洁的中文短语，准确概括整条用例关注点，且未夹杂操作步骤或预期细节。

   - 优先级、模块名等字段是否仅使用约定集合（如 P0/P1/P2，或既定的模块命名），避免随意英文或混写。



**输出行为：**

- 如果发现问题，请直接指出具体的【用例ID】和【错误类型】，并给出【修改建议】；对纯格式/表头/字段规范类问题，请直接给出**修正后的完整 Markdown 表格版本**。

- 如果用例完美，请输出：“✅ 通过审查，用例符合 Fambase 交付标准。”""",
        llm=llm,
        verbose=True,
    )

    # ═══════════════════════════════════════════════════════════════════════
    # Tasks（与上述 Agent 设定一一对应，请勿脱节）
    # ═══════════════════════════════════════════════════════════════════════

    # Task 1：文档分析师 → 《需求风险评估报告》
    task1 = Task(
        description="请以【文档分析师（The Auditor）】的身份，对以下需求文档进行深度扫描，并输出《需求风险评估报告》。\n\n要求覆盖：1) 模糊性审查（Ambiguity Check）；2) 逻辑冲突与遗漏（Conflict & Omission）；3) 极端场景推演（Edge Cases）。\n\n需求文档：\n{demand}",
        expected_output="《需求风险评估报告》：以列表形式输出，每条包含【风险类型】+【问题描述】+【建议/疑问】；若无明显问题则列出最复杂的 3 个逻辑确认点。",
        agent=doubt_agent,
    )

    # Task 2：测试点拆解师 → 基于 1 号报告产出原子化测试点
    task2 = Task(
        description="请以【测试点拆解师（The Planner）】的身份，基于上一任务（文档分析师）输出的《需求风险评估报告》与需求文档，将内容转化为结构清晰、覆盖全面的「测试点（Test Points）」骨架。\n\n须遵循：模块化分组（如 UI 交互、业务逻辑、前后端交互、多端同步、V3 后台）；原子化原则（区分 Happy Path / Sad Path）；逻辑继承（将 1 号的风险点转化为具体验证点，含回归验证）。",
        expected_output="测试点思维导图：Markdown 层级列表，结构为「模块名称 → 子模块/场景 → [P0] 核心测试点 / [P1] 异常边界 / [P2] UI 文案」。",
        agent=organize_agent,
        context=[task1],
    )

    # Task 3：Fambase 测试专家 → 符合《Nicholas 交付宪法》的测试用例表
    task3 = Task(
        description="请以【Fambase 专属资深全栈测试专家】的身份，根据上一任务（测试点拆解师）产出的测试点，输出符合《Nicholas 交付宪法》的测试用例。\n\n必须遵守：1) 表头为 | 用例ID | 模块 | 场景 | 用例概述 | 优先级 | 前置条件 | 操作步骤 | 预期结果 |；2) 呼吸感排版（中英/数字边界去空格，英文内部保留空格）；3) 预期结果绝对去动词化、仅描述系统状态，多条结果用 1. 2. 3. 编号；4) 覆盖极端场景与回归验证（断网、杀进程、多端同步、V3 数据一致性等）。",
        expected_output="符合《Nicholas 交付宪法》的测试用例：Markdown 表格，固定表头，呼吸感排版，预期结果去动词化；覆盖 Happy Path、Sad Path 及回归验证点。",
        agent=case_agent,
        context=[task2],
    )

    # Task 4：用例审查官 → 按四大验收标准审查 3 号输出，输出修改建议或通过结论
    task4 = Task(
        description="请以【用例审查官（The Reviewer）】的身份，对上一任务（测试用例工程师）产出的测试用例，严格按照四大验收标准逐条审查：1) 呼吸感排版（中英/数字边界零空格、英文内部保留空格）；2) 预期结果规范（去动词化、单条不编号/多条分行编号）；3) 逻辑与覆盖率（是否覆盖 2 号 Agent 关键测试点、前置条件是否清晰、是否含 Fambase 特有校验如 V3 一致性）；4) 冗余审查（剔除废话、合并重复步骤）。若有问题请指出【用例ID】+【错误类型】+【修改建议】；若完美则输出：「✅ 通过审查，用例符合 Fambase 交付标准。」",
        expected_output="审查结论：若存在问题则列出【用例ID】+【错误类型】+【修改建议】；若通过则输出：「✅ 通过审查，用例符合 Fambase 交付标准。」",
        agent=review_agent,
        context=[task3],
    )

    # ─── Crew 组装 ───
    crew = Crew(
        agents=[doubt_agent, organize_agent, case_agent, review_agent],
        tasks=[task1, task2, task3, task4],
        verbose=True,
        stream=stream,
    )
    if not stream:
        _crew = crew
    return crew


def _get_crew_with_config(
    agents_config: dict[str, Any],
    project_context: str = "",
    stream: bool = False,
) -> Crew:
    """使用 YAML 配置构建 Crew（不缓存），并注入 project_context。"""
    gemini_api_key = os.getenv("GEMINI_API_KEY")
    if not gemini_api_key:
        raise ValueError("ERROR: GEMINI_API_KEY 未设置。")
    model_name = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    llm = ChatGoogleGenerativeAI(
        model=model_name,
        google_api_key=gemini_api_key,
        temperature=0.4,
    )
    return _build_crew_from_config(agents_config, llm, project_context, stream=stream)


def chat_with_document_agent(
    user_message: str,
    document_context: str,
    project_context: str = "",
    agents_config_path: str | None = None,
) -> str:
    """与产品文档管理 Agent（文档分析师）沟通：基于文档内容回答用户问题。
    用于验证 Agent 对文档的理解，或对文档进行问答。
    - document_context: 需求文档内容（来自 Quip 拉取、项目记忆或手动粘贴）
    - project_context: 项目记忆摘要（可选）
    """
    if not user_message or not user_message.strip():
        return "请输入你的问题。"
    if not document_context or not document_context.strip():
        return "请先提供文档内容：在「与文档 Agent 沟通」页选择「上次运行的需求」或「项目记忆」，或手动粘贴文档。"

    gemini_api_key = os.getenv("GEMINI_API_KEY")
    if not gemini_api_key:
        raise ValueError("GEMINI_API_KEY 未设置，请先配置。")

    model_name = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    llm = ChatGoogleGenerativeAI(
        model=model_name,
        google_api_key=gemini_api_key,
        temperature=0.3,
    )

    config = load_agents_config(agents_config_path or AGENTS_CONFIG_PATH)
    agents_cfg = config.get("agents") or []
    doubt_cfg = next((a for a in agents_cfg if a.get("id") == "doubt_agent"), None)
    if not doubt_cfg:
        doubt_cfg = agents_cfg[0] if agents_cfg else None

    if doubt_cfg:
        doc_agent = Agent(
            role=doubt_cfg.get("role", "Document Analyst"),
            goal=doubt_cfg.get("goal", "理解并分析产品需求文档"),
            backstory=(doubt_cfg.get("backstory") or "").strip() + "\n\n你现在需要基于文档内容，直接回答用户的问题。回答要准确、简洁、基于文档事实。",
            llm=llm,
            verbose=True,
        )
    else:
        doc_agent = Agent(
            role="Document Analyst",
            goal="理解产品需求文档并准确回答用户问题",
            backstory="你是资深需求分析师，熟悉产品文档。根据文档内容回答用户问题，回答要基于文档事实。",
            llm=llm,
            verbose=True,
        )

    proj_ctx = f"\n\n【项目背景】\n{project_context}" if project_context and project_context.strip() else ""
    doc_preview = document_context[:12000] + ("..." if len(document_context) > 12000 else "")

    task = Task(
        description="""你是一位产品文档管理专家。用户会向你提问，你需要基于下方提供的【需求文档】内容回答。

要求：
- 回答必须基于文档事实，不确定时明确说明
- 若文档中无相关信息，如实告知
- 回答简洁清晰，可直接用于与产品/研发沟通

【需求文档】
{doc}

【用户问题】
{question}
{project}
""".replace("{doc}", doc_preview).replace("{question}", user_message.strip()).replace("{project}", proj_ctx),
        expected_output="基于文档的准确回答",
        agent=doc_agent,
    )
    crew = Crew(agents=[doc_agent], tasks=[task], verbose=True)
    result = crew.kickoff()
    out = getattr(result, "raw", result)
    return str(out).strip() if out else ""


def _parse_markdown_tables(text: str) -> list[list[list[str]]]:
    """从文本中解析所有 Markdown 表格，返回 [表格1行列表, 表格2行列表, ...]，每表为 [row1, row2, ...]，每行为 [cell, ...]。"""
    tables = []
    lines = text.split("\n")
    i = 0
    while i < len(lines):
        line = lines[i]
        if not line.strip().startswith("|") or not line.strip().endswith("|"):
            i += 1
            continue
        rows = []
        while i < len(lines) and lines[i].strip().startswith("|") and lines[i].strip().endswith("|"):
            raw = lines[i]
            if re.match(r"^\s*\|[\s\-:]+\|\s*$", raw):
                i += 1
                continue
            cells = [c.strip() for c in raw.split("|")[1:-1]]
            if cells:
                rows.append(cells)
            i += 1
        if rows:
            tables.append(rows)
    return tables


def _export_to_excel(tables: list[list[list[str]]], excel_path: str) -> bool:
    """将解析出的表格写入 Excel，若有多个表则合并为同一 sheet（按顺序拼接）。返回是否成功。"""
    try:
        import openpyxl
    except ImportError:
        print("提示: 安装 openpyxl 后可导出 Excel，执行 pip install openpyxl", file=sys.stderr)
        return False
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "测试用例"
    row_num = 0
    for tbl in tables:
        for r in tbl:
            row_num += 1
            for col_num, cell in enumerate(r, 1):
                ws.cell(row=row_num, column=col_num, value=cell)
        if tbl:
            row_num += 1
    try:
        wb.save(excel_path)
        return True
    except Exception as e:
        print(f"导出 Excel 失败: {e}", file=sys.stderr)
        return False


def _export_to_quip_table(tables: list[list[list[str]]], title: str) -> str | None:
    """在 Quip 中新建文档并写入表格（HTML）。需 QUIP_ACCESS_TOKEN。返回新文档 URL 或 None。"""
    if not tables:
        return None
    token = os.getenv("QUIP_ACCESS_TOKEN")
    if not token:
        print("提示: 导出到 Quip 需设置 QUIP_ACCESS_TOKEN", file=sys.stderr)
        return None
    rows_html = []
    for tbl in tables:
        for i, row in enumerate(tbl):
            tag = "th" if i == 0 else "td"
            cells = "".join(f"<{tag}>{html_lib.escape(c)}</{tag}>" for c in row)
            rows_html.append(f"<tr>{cells}</tr>")
    table_html = "<table border=\"1\"><tbody>" + "".join(rows_html) + "</tbody></table>"
    body = f"<h1>{html_lib.escape(title)}</h1><p>以下为自动生成的测试用例表格。</p>{table_html}"
    url = f"{QUIP_API_BASE}/threads/new-document"
    data = urllib.parse.urlencode({"content": body, "format": "html", "title": title}).encode()
    req = urllib.request.Request(url, data=data, method="POST", headers={"Authorization": f"Bearer {token}", "Content-Type": "application/x-www-form-urlencoded"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            doc = json.loads(resp.read().decode())
        thread_id = doc.get("id") or (doc.get("thread") or {}).get("id")
        if thread_id:
            base = os.getenv("QUIP_BASE_URL", "https://quip.com").rstrip("/")
            return f"{base}/{thread_id}"
        return None
    except Exception as e:
        print(f"导出到 Quip 失败: {e}", file=sys.stderr)
        return None


def _export_to_google_sheets(tables: list[list[list[str]]], title: str) -> str | None:
    """将表格写入 Google Sheets 新建表格。需配置 GOOGLE_SHEETS_CREDENTIALS_JSON（服务账号 JSON 路径或内容）。返回表格 URL 或 None。"""
    if not tables:
        return None
    try:
        import gspread
        from google.oauth2.service_account import Credentials
    except ImportError:
        print("提示: 导出到 Google 表格需安装 gspread 与 google-auth，并配置 GOOGLE_SHEETS_CREDENTIALS_JSON", file=sys.stderr)
        return None
    creds_path_or_json = os.getenv("GOOGLE_SHEETS_CREDENTIALS_JSON")
    if not creds_path_or_json:
        print("提示: 请设置环境变量 GOOGLE_SHEETS_CREDENTIALS_JSON（服务账号 JSON 文件路径或 JSON 字符串）", file=sys.stderr)
        return None
    try:
        if creds_path_or_json.strip().startswith("{"):
            import tempfile
            with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
                f.write(creds_path_or_json)
                path = f.name
            creds = Credentials.from_service_account_file(path, scopes=["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"])
            os.unlink(path)
        else:
            creds = Credentials.from_service_account_file(creds_path_or_json.strip(), scopes=["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"])
        gc = gspread.authorize(creds)
        sh = gc.create(title)
        sheet = sh.sheet1
        row_offset = 0
        for tbl in tables:
            if tbl:
                sheet.update(f"A{1 + row_offset}", tbl)
                row_offset += len(tbl) + 1
        return sh.url
    except Exception as e:
        print(f"导出到 Google 表格失败: {e}", file=sys.stderr)
        return None


def _save_result(demand: str, result_str: str, output_dir: str) -> tuple[str, str]:
    """将需求和结果写入 output_dir，返回 (txt 路径, 时间戳)。"""
    os.makedirs(output_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = os.path.join(output_dir, f"crew_result_{timestamp}.txt")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("=== 需求 ===\n\n")
        f.write(demand)
        f.write("\n\n=== 输出 ===\n\n")
        f.write(result_str)
    return out_path, timestamp


def load_project_memory(path: str | None = None) -> str:
    """读取项目记忆文件内容，用于注入 Agent 上下文。"""
    p = path or PROJECT_MEMORY_PATH
    if not os.path.isfile(p):
        return ""
    try:
        with open(p, "r", encoding="utf-8") as f:
            return f.read().strip()
    except Exception:
        return ""


def get_project_context_for_agent(include_store: bool = True) -> str:
    """获取供 Agent 使用的项目上下文：md 文件 + 记忆库近期记录。"""
    md_ctx = load_project_memory()
    if not include_store:
        return md_ctx
    try:
        from memory_store import get_recent_for_agent
        store_ctx = get_recent_for_agent(limit=10)
        if store_ctx:
            md_ctx = (md_ctx + "\n\n【近期需求与产出记录】\n" + store_ctx).strip()
    except ImportError:
        pass
    return md_ctx


def update_project_memory(addition: str, path: str | None = None, max_chars: int = 20000) -> None:
    """在项目记忆文件末尾追加一段摘要，便于 Agent 保持对项目的熟悉。若超过 max_chars 则只保留尾部。"""
    p = path or PROJECT_MEMORY_PATH
    os.makedirs(os.path.dirname(p), exist_ok=True)
    existing = load_project_memory(p)
    sep = "\n\n---\n\n"
    new_content = (existing + sep + addition.strip()).strip()
    if len(new_content) > max_chars:
        new_content = "...\n\n" + new_content[-max_chars:]
    with open(p, "w", encoding="utf-8") as f:
        f.write(new_content)


def run_mock_pipeline(demand: str, output_dir: str = OUTPUT_DIR) -> str:
    """本地模拟流程（不调 API）：四步占位输出，用于自检流程与文件写入。"""
    print("[Mock] 需求摘要:", demand[:200] + ("..." if len(demand) > 200 else ""))
    print("[Mock] 模拟执行: 分析 → 测试点 → 测试用例 → 评审")
    step1 = "1. 需求分析（模拟）\n- 文档完整性待确认\n- 分流比例边界未定义\n- 实验周期与稳定性需明确"
    step2 = "2. 测试点（模拟）\n- 分流正确性\n- 配置下发与回退\n- 指标上报与延迟"
    step3 = "3. 测试用例（模拟）\n- TC01: 用户分流到对照组/实验组\n- TC02: 比例配置异常回退对照组"
    step4 = "4. 评审结论（模拟）\n- 覆盖主要功能与异常路径\n- 建议补充性能与稳定性用例"
    result_str = "\n\n".join([step1, step2, step3, step4])
    print("\n" + "=" * 60 + "\n")
    print(result_str)
    out_path, _ = _save_result(demand, result_str, output_dir)
    print(f"\n结果已保存: {out_path}")
    return result_str


# 本地四 Agent 占位输出（与真实 Crew 输出结构一致，含 Markdown 表格，便于导出 Excel）
_LOCAL_AGENT1 = "【需求风险评估报告 - 占位】\n- 模块：直播分辨率；风险类型：功能/兼容；风险概述：AB test 分流与降级策略需明确；优先级建议：P0；问题描述：分辨率档位与兜底逻辑；建议：与产品确认实验周期与回滚条件。"
_LOCAL_AGENT2 = "【测试点骨架 - 占位】\n- 模块：直播分辨率；场景：AB 分流；测试点ID：TP-001；用例概述：用户被正确分流到对照组/实验组；类型：功能；优先级：P0。\n- 模块：直播分辨率；场景：降级；测试点ID：TP-002；用例概述：异常时回退默认分辨率；类型：异常；优先级：P0。"
_LOCAL_AGENT3_TABLE = """| 用例ID | 模块 | 场景 | 用例概述 | 优先级 | 前置条件 | 操作步骤 | 预期结果 |
| TC-001 | 直播分辨率 | AB分流 | 用户被正确分流到对照组/实验组 | P0 | 用户已登录且实验开启 | 进入直播并查看分辨率档位 | 与实验组配置一致，对照组为默认档位 |
| TC-002 | 直播分辨率 | 降级 | 异常时回退默认分辨率 | P0 | 实验组服务异常或超时 | 触发拉流/切换分辨率 | 自动回退到默认分辨率，无黑屏或卡死 |
| TC-003 | 直播分辨率 | 配置下发 | 服务端配置生效 | P0 | 后端更新实验比例 | 新用户进入直播 | 按新比例分流，老用户会话不变 |
| TC-004 | 直播分辨率 | 边界 | 不支持分辨率时兜底 | P1 | 设备仅支持 360p | 进入直播 | 展示 360p 或友好提示，不崩溃 |"""
_LOCAL_AGENT4 = "✅ 审查通过。用例覆盖分流、降级、配置与边界，表头与字段符合 Fambase 交付宪法。（本地占位模式，未调用 Gemini）"


def run_local_crew_pipeline(
    demand: str,
    output_dir: str = OUTPUT_DIR,
    export_excel: bool = True,
    export_quip: bool = False,
    export_sheets: bool = False,
) -> str:
    """不调用 Gemini：按四 Agent 顺序产出占位结果（含 Markdown 表格），并复用保存/导出逻辑。"""
    print("需求摘要:", demand[:200] + ("..." if len(demand) > 200 else ""))
    print("[Local] 四 Agent 占位模式，不调用 Gemini；结果可正常导出 Excel。")
    print()
    result_str = "\n\n".join([_LOCAL_AGENT1, _LOCAL_AGENT2, _LOCAL_AGENT3_TABLE, _LOCAL_AGENT4])
    print("=" * 60)
    print(result_str)
    print("=" * 60)
    out_path, timestamp = _save_result(demand, result_str, output_dir)
    print(f"\n结果已保存: {out_path}")

    tables = _parse_markdown_tables(result_str)
    if tables:
        if export_excel:
            excel_path = os.path.join(output_dir, f"crew_result_{timestamp}.xlsx")
            if _export_to_excel(tables, excel_path):
                print(f"Excel 已导出: {excel_path}")
        if export_quip:
            quip_url = _export_to_quip_table(tables, f"测试用例_{timestamp}")
            if quip_url:
                print(f"Quip 文档已创建: {quip_url}")
        if export_sheets:
            sheets_url = _export_to_google_sheets(tables, f"测试用例_{timestamp}")
            if sheets_url:
                print(f"Google 表格已创建: {sheets_url}")
    return result_str


def run_pipeline(
    demand: str,
    output_dir: str = OUTPUT_DIR,
    mock: bool = False,
    local: bool = False,
    export_excel: bool = True,
    export_quip: bool = False,
    export_sheets: bool = False,
    agents_config_path: str | None = None,
    project_context: str | None = None,
    return_details: bool = False,
) -> str | dict[str, Any]:
    """跑完整个流程，并把结果写入 output_dir。可同时导出 Excel / Quip / Google 表格。
    若 return_details=True，返回 dict：result_str, step_outputs, excel_path, quip_url, sheets_url, timestamp；否则返回 result_str。"""
    if mock:
        return run_mock_pipeline(demand, output_dir)
    if local:
        return run_local_crew_pipeline(
            demand,
            output_dir=output_dir,
            export_excel=export_excel,
            export_quip=export_quip,
            export_sheets=export_sheets,
        )

    use_config = bool(agents_config_path or os.path.isfile(AGENTS_CONFIG_PATH))
    proj_ctx = project_context if project_context is not None else get_project_context_for_agent()
    stream = return_details

    if use_config and yaml:
        config = load_agents_config(agents_config_path or AGENTS_CONFIG_PATH)
        if config:
            crew = _get_crew_with_config(config, proj_ctx, stream=stream)
        else:
            use_config = False
    if not use_config:
        crew = _get_crew(stream=stream)

    inputs = {"demand": demand}
    step_outputs: list[dict[str, str]] = []
    quip_url: str | None = None
    sheets_url: str | None = None
    excel_path: str | None = None

    if stream:
        kickoff_result = crew.kickoff(inputs=inputs)
        try:
            current_task: str | None = None
            current_agent: str | None = None
            current_content: list[str] = []
            for chunk in kickoff_result:
                if getattr(chunk, "task_name", None):
                    if current_task and current_content:
                        step_outputs.append({
                            "task": current_task,
                            "agent": current_agent or "",
                            "content": "".join(current_content).strip(),
                        })
                    current_task = getattr(chunk, "task_name", None) or ""
                    current_agent = getattr(chunk, "agent_role", None) or ""
                    current_content = []
                if getattr(chunk, "content", None):
                    current_content.append(chunk.content)
            if current_task and current_content:
                step_outputs.append({
                    "task": current_task,
                    "agent": current_agent or "",
                    "content": "".join(current_content).strip(),
                })
        except Exception:
            step_outputs = []
        result = getattr(kickoff_result, "result", kickoff_result)
        result_str = str(getattr(result, "raw", result))
    else:
        print("需求摘要:", demand[:200] + ("..." if len(demand) > 200 else ""))
        print()
        result = crew.kickoff(inputs=inputs)
        result_str = str(result)
        print("\n" + "=" * 60 + "\n")
        print(result_str)

    out_path, timestamp = _save_result(demand, result_str, output_dir)
    if not stream:
        print(f"\n结果已保存: {out_path}")

    tables = _parse_markdown_tables(result_str)
    if tables:
        if export_excel:
            excel_path = os.path.join(output_dir, f"crew_result_{timestamp}.xlsx")
            if _export_to_excel(tables, excel_path):
                if not stream:
                    print(f"Excel 已导出（可直接下载）: {excel_path}")
        if export_quip:
            quip_url = _export_to_quip_table(tables, f"测试用例_{timestamp}")
            if quip_url and not stream:
                print(f"Quip 文档已创建: {quip_url}")
        if export_sheets:
            sheets_url = _export_to_google_sheets(tables, f"测试用例_{timestamp}")
            if sheets_url and not stream:
                print(f"Google 表格已创建: {sheets_url}")
    else:
        if export_excel or export_quip or export_sheets:
            if not stream:
                print("提示: 未从输出中解析到 Markdown 表格，未执行表格导出。", file=sys.stderr)
        excel_path = None

    if return_details:
        return {
            "result_str": result_str,
            "step_outputs": step_outputs,
            "excel_path": excel_path,
            "quip_url": quip_url,
            "sheets_url": sheets_url,
            "timestamp": timestamp,
            "txt_path": out_path,
        }
    return result_str


def main() -> int:
    parser = argparse.ArgumentParser(
        description="从文字版需求文档跑完分析→测试点→测试用例→评审流程，并保存结果。"
    )
    parser.add_argument(
        "-f",
        "--file",
        default=None,
        metavar="PATH",
        help=f"需求文档路径（文本）。不指定时尝试读当前目录下的 {DEFAULT_REQUIREMENT_FILE}，再回退到环境变量 DEMAND 或内置默认。",
    )
    parser.add_argument(
        "-o",
        "--output-dir",
        default=OUTPUT_DIR,
        metavar="DIR",
        help=f"结果输出目录，默认: {OUTPUT_DIR}",
    )
    parser.add_argument(
        "--mock",
        action="store_true",
        help="本地模拟流程（不调用 Gemini API），用于自检与 CI。",
    )
    parser.add_argument(
        "--local",
        action="store_true",
        help="本地占位模式：不调用 Gemini，按四 Agent 顺序产出占位结果并正常导出 Excel。",
    )
    parser.add_argument(
        "-q",
        "--quip",
        default=None,
        metavar="THREAD_ID",
        help="从 Quip 文档读取需求（需 QUIP_ACCESS_TOKEN）。可传 thread_id 或文档 URL，如 https://quip.com/xxx。",
    )
    parser.add_argument(
        "--no-excel",
        action="store_true",
        help="不导出 Excel（默认会从输出中解析表格并导出 .xlsx 到 output/）。",
    )
    parser.add_argument(
        "--export-quip",
        action="store_true",
        help="在 Quip 中新建文档并写入测试用例表格（需 QUIP_ACCESS_TOKEN）。",
    )
    parser.add_argument(
        "--export-sheets",
        action="store_true",
        help="导出到 Google 表格（需 GOOGLE_SHEETS_CREDENTIALS_JSON 环境变量）。",
    )
    args = parser.parse_args()

    if args.quip:
        demand = load_demand_from_quip(args.quip)
        tid = _extract_quip_thread_id(args.quip)
        print(f"已从 Quip 文档加载需求: thread_id={tid}")
    else:
        file_path = args.file
        if file_path is None and os.path.isfile(DEFAULT_REQUIREMENT_FILE):
            file_path = DEFAULT_REQUIREMENT_FILE
        demand = load_demand(file_path)
        if file_path:
            print(f"已从文件加载需求: {os.path.abspath(file_path)}")
        else:
            print("使用环境变量 DEMAND 或内置默认需求")

    try:
        run_pipeline(
            demand,
            output_dir=args.output_dir,
            mock=args.mock,
            local=args.local,
            export_excel=not args.no_excel,
            export_quip=args.export_quip,
            export_sheets=args.export_sheets,
        )
        return 0
    except Exception as e:
        print(f"执行失败: {e}", file=sys.stderr)
        raise


if __name__ == "__main__":
    sys.exit(main())
