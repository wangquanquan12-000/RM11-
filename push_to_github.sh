#!/bin/bash
# 一键推送到 GitHub，便于在 Streamlit Cloud 部署得到永久链接
# 用法：./push_to_github.sh https://github.com/你的用户名/仓库名.git
# 请先在 https://github.com/new 新建一个空仓库（不要勾选 README），复制仓库地址填入上面

set -e
cd "$(dirname "$0")"

REPO_URL="$1"
if [ -z "$REPO_URL" ]; then
  echo "用法: $0 <GitHub 仓库地址>"
  echo "示例: $0 https://github.com/你的用户名/crew-test-app.git"
  echo ""
  echo "请先在 https://github.com/new 新建一个空仓库，复制地址后执行上述命令。"
  exit 1
fi

echo ">>> 添加并提交当前文件..."
git add -A
git status -s
if git diff --staged --quiet 2>/dev/null; then
  echo ">>> 无新改动，直接推送。"
else
  git commit -m "chore: 推送以部署 Streamlit Cloud 永久链接"
fi

echo ">>> 设置远程仓库并推送..."
git remote remove origin 2>/dev/null || true
git remote add origin "$REPO_URL"
git push -u origin main

echo ""
echo "=========================================="
echo "  已推送到 GitHub"
echo "=========================================="
echo ""
echo "下一步：在浏览器打开 https://share.streamlit.io"
echo "  → 用 GitHub 登录 → New app"
echo "  → 选择刚推送的仓库，主文件填: app_ui.py"
echo "  → 在 Settings → Secrets 里填："
echo "     QUIP_ACCESS_TOKEN = \"你的 Quip Token\""
echo "     GEMINI_API_KEY = \"你的 Gemini Key\""
echo ""
echo "部署完成后会得到永久链接: https://xxx.streamlit.app"
echo ""
