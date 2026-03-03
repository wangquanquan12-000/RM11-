# 手动验收清单

上线前请按此清单本地验证。

## 1. 单元测试
```bash
pytest tests/ -v --tb=short
```
预期：全部通过。

## 2. 密钥检查
```bash
./scripts/check_no_secrets.sh
```
预期：`check_no_secrets: OK`

## 3. 流水线回归（不调用 API）
```bash
echo "测试需求：登录功能" | python3 crew_test.py -f - --mock
python3 crew_test.py -f - --local
```
预期：生成 Excel，无报错。

## 4. Web 应用
```bash
python3 -m streamlit run app_ui.py --server.port 8501
```
浏览器访问 http://localhost:8501：

- [ ] 直接进入主应用（无登录/注册）
- [ ] 侧栏导航：工作台（生成用例、项目记忆、文档问答）、高级（编辑 Agent、设置）可切换；默认首屏为「生成用例」
- [ ] 设计系统：主色 #0d9488、卡片圆角 12px、max-width 960px 居中
- [ ] 生成用例首屏：链接输入 + 配置可折叠 + 主按钮；空状态显示「暂无生成记录，输入链接开始第一次」
- [ ] 生成用例运行中时按钮显示「运行中…」且禁用；归档失败时提示「归档失败：未解析到有效表格」
- [ ] 编辑 Agent 有未保存修改时顶部提示「您有未保存的修改」；文档问答区上方显示「当前文档：xxx」

## 5. 凭证存储（Keyring）
- [ ] 在「设置」页保存 Gemini Key
- [ ] 刷新页面，凭证仍存在（Keyring 或 JSON 降级）
- [ ] 成功提示显示存储方式（Keyring / JSON）
