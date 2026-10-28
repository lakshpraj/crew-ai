@echo off
python -m pip install -r requirements.txt
start http://localhost:8000
python -m uvicorn main:app --reload
pause
