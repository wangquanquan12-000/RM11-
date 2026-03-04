# 需求 → 测试用例流水线

从需求文档出发，经四个 Agent（文档分析 → 测试点拆解 → 测试用例生成 → 评审）产出符合规范的测试用例，支持 Excel 导出。

## 本地运行

```bash
# 安装依赖
pip install -r requirements.txt

# 启动网页（浏览器打开 http://localhost:8501）
python3 -m streamlit run app_ui.py --server.port 8501
```

或执行 `./run_app.sh`（Mac/Linux）、双击 `run_app.bat`（Windows）。

## 部署到 Streamlit Community Cloud（share.streamlit.io）

部署后即可获得**永久公网链接**（如 `https://xxx.streamlit.app`）。

1. **把本仓库推到 GitHub**
   ```bash
   git add .
   git commit -m "init"
   git remote add origin https://github.com/你的用户名/你的仓库名.git
   git push -u origin main
   ```
   （若默认分支是 `master`，上面改为 `git push -u origin master`。）

2. **在 [share.streamlit.io](https://share.streamlit.io) 创建应用**
   - 用 **GitHub** 登录 [share.streamlit.io](https://share.streamlit.io)。
   - 点击 **New app**。
   - **Repository**：选刚推送的仓库（如 `你的用户名/你的仓库名`）。
   - **Branch**：选 `main`（或 `master`）。
   - **Main file path**：填 `app_ui.py`。
   - 点击 **Deploy**，等待构建完成。

3. **配置密钥（云端必填）**
   - 打开该应用的 **Settings → Secrets**，在 TOML 中填写：
   ```toml
   GEMINI_API_KEY = "你的 Gemini API Key"
   ```
   可选：指定模型时增加一行：
   ```toml
   GEMINI_MODEL = "gemini-2.5-flash-lite"
   ```
   - 保存后应用会自动重载，无需在界面反复粘贴 Key。

## 项目结构

| 文件/目录       | 说明 |
|----------------|------|
| `app_ui.py`    | Streamlit 网页入口（运行流水线 / 编辑 Agent / 项目记忆） |
| `crew_test.py` | 四 Agent 流水线核心逻辑（解析需求、Crew 执行、Excel 导出） |
| `config/agents.yaml` | Agent 与 Task 定义，可在界面中编辑 |
| `requirements.txt` | Python 依赖 |
| `run_app.sh` / `run_app.bat` | 本地启动脚本 |

## 凭证安全

- **本地**：点击「保存到本地」时，Key 会写入 `config/defaults.json`（已 gitignore），并设置为仅当前用户可读写。
- **共享电脑**：建议使用环境变量 `GEMINI_API_KEY`，不要保存到本地。
- **云端部署**：在 Streamlit Cloud 的 Settings → Secrets 中配置，切勿将凭证提交到仓库。

## 使用说明

- **运行流水线**：上传或粘贴需求文档，配置 Gemini Key，点击运行即可看到 Agent 沟通过程与结果，并下载 Excel。
- **编辑 Agent**：在「编辑 Agent」页修改 `config/agents.yaml` 中的角色与任务，保存后下次运行生效。
- **项目记忆**：在「项目记忆」页维护项目摘要，或从本次运行追加，供 Agent 保持对项目的熟悉。
