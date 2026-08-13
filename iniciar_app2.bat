@echo off
python -m venv .venv
.\setup_ia3d.bat
streamlit run app.py
pause

