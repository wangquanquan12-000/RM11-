#!/bin/bash
# 启动「需求 → 测试用例流水线」网页应用
cd "$(dirname "$0")"
echo "正在启动应用，请在浏览器中打开下方链接："
echo ""
echo "  http://localhost:8501"
echo ""
exec python3 -m streamlit run app_ui.py --server.port 8501 --server.headless true
