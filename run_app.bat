@echo off
cd /d "%~dp0"
echo ^>^>^> 检查依赖...
python -c "import streamlit" 2>nul || pip install -q -r requirements.txt
echo ^>^>^> 启动应用，请在浏览器打开：
echo.
echo     http://localhost:8501
echo.
python -m streamlit run app_ui.py --server.port 8501 --server.headless true
pause
