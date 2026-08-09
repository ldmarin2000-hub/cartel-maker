@echo off
cd /d "%~dp0"
py -3 -m venv .venv
streamlit run app.py
pause
