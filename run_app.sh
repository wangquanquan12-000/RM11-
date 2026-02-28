#!/bin/bash
# 一键启动「需求 → 测试用例流水线」（自动安装依赖）
cd "$(dirname "$0")"
echo ">>> 检查依赖..."
python3 -c "import streamlit" 2>/dev/null || pip install -q -r requirements.txt
echo ">>> 启动应用，请在浏览器打开："
echo ""
echo "    http://localhost:8501"
echo ""
exec python3 -m streamlit run app_ui.py --server.port 8501 --server.headless true
