#!/bin/bash
# 一键启动「需求 → 测试用例流水线」（自动安装依赖）
set -e
cd "$(dirname "$0")"

# CrewAI / 类型注解依赖 Python ≥3.10；优先使用仓库内 venv
if [[ -x "./venv/bin/python" ]]; then
  PYTHON="./venv/bin/python"
else
  PYTHON="python3"
fi

if ! "$PYTHON" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)'; then
  echo ""
  echo "错误: 当前 Python 版本不满足要求（需要 3.10+）。执行: $PYTHON --version"
  echo ""
  echo "请先安装 Python 3.10+（例如 brew install python@3.12），然后重建虚拟环境："
  echo "  cd \"$(pwd)\""
  echo "  rm -rf venv"
  echo "  python3.12 -m venv venv"
  echo "  source venv/bin/activate && pip install -r requirements.txt"
  echo ""
  exit 1
fi

echo ">>> 检查依赖 ($PYTHON)..."
"$PYTHON" -c "import streamlit" 2>/dev/null || "$PYTHON" -m pip install -q -r requirements.txt
echo ">>> 启动应用，请在浏览器打开："
echo ""
echo "    http://localhost:8501"
echo ""
exec "$PYTHON" -m streamlit run app_ui.py --server.port 8501 --server.headless true
