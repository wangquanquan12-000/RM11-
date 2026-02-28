# 需求 → 测试用例流水线

从 Quip 需求文档出发，经四个 Agent（文档分析 → 测试点拆解 → 测试用例生成 → 评审）产出符合规范的测试用例，支持 Excel / Quip / Google 表格导出。

## 本地运行

```bash
# 安装依赖
pip install -r requirements.txt

# 启动网页（浏览器打开 http://localhost:8501）
python3 -m streamlit run app_ui.py --server.port 8501
```

或执行 `./run_app.sh`（Mac/Linux）、双击 `run_app.bat`（Windows）。

## 部署到 Streamlit Cloud（获得永久公网链接）

1. **推送本仓库到 GitHub**
   ```bash
   git add .
   git commit -m "init"
   git remote add origin https://github.com/你的用户名/你的仓库名.git
   git push -u origin main
   ```

2. **在 Streamlit Cloud 创建应用**
   - 打开 [share.streamlit.io](https://share.streamlit.io)，用 GitHub 登录。
   - 点击 **New app**，选择该仓库，主文件填 `app_ui.py`，分支选 `main`。
   - 部署完成后会得到形如 `https://xxx.streamlit.app` 的**永久链接**。

3. **配置密钥（云端必填）**
   - 在应用的 **Settings → Secrets** 中填写：
   ```toml
   QUIP_ACCESS_TOKEN = "你的 Quip Token"
   GEMINI_API_KEY = "你的 Gemini API Key"
   ```
   - 应用会从环境变量读取，无需在界面反复粘贴。

## 项目结构

| 文件/目录       | 说明 |
|----------------|------|
| `app_ui.py`    | Streamlit 网页入口（运行流水线 / 编辑 Agent / 项目记忆） |
| `crew_test.py` | 四 Agent 流水线核心逻辑（Quip 拉取、Crew 执行、Excel/Quip/Sheets 导出） |
| `config/agents.yaml` | Agent 与 Task 定义，可在界面中编辑 |
| `requirements.txt` | Python 依赖 |
| `run_app.sh` / `run_app.bat` | 本地启动脚本 |

## 使用说明

- **运行流水线**：填写 Quip 文档链接与 Token、Gemini Key，点击运行即可看到 Agent 沟通过程与结果，并下载 Excel 或打开 Quip/Sheets 链接。
- **编辑 Agent**：在「编辑 Agent」页修改 `config/agents.yaml` 中的角色与任务，保存后下次运行生效。
- **项目记忆**：在「项目记忆」页维护项目摘要，或从本次运行追加，供 Agent 保持对项目的熟悉。

详细步骤见 `如何打开应用.md`。
