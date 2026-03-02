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

- [ ] 显示登录/注册页
- [ ] 注册新用户（用户名≥2 字符，密码≥6 字符，验证码或万能码 ADMIN888）
- [ ] 登录成功进入主应用
- [ ] 侧边栏显示「当前用户」及「7 天内免登录」提示
- [ ] 关闭浏览器后重新打开，7 天内无需再次登录
- [ ] 点击退出后回到登录页
- [ ] 四个 Tab：生成用例、编辑 Agent、项目记忆、文档问答 可正常切换

## 5. 凭证存储（Keyring）
- [ ] 在「生成用例」→ 账号与模型 保存 Token/Key
- [ ] 刷新页面，凭证仍存在（Keyring 或 JSON 降级）
- [ ] 成功提示显示存储方式（Keyring / JSON）
