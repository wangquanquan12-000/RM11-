@echo off
cd /d "%~dp0"
echo 正在启动应用，请在浏览器中打开下方链接：
echo.
echo   http://localhost:8501
echo.
python -m streamlit run app_ui.py --server.port 8501 --server.headless true
pause
