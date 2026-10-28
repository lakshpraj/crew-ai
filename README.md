# Crew: AI Workforce for Businesses

## Chalane ka tareeka
1. Python 3.9+ install hona chahiye.
2. Is folder mein terminal kholo:
   pip install -r requirements.txt
3. (Optional, real AI ke liye) .env.example ko copy karke .env banao aur ANTHROPIC_API_KEY daalo.
4. Run:
   uvicorn main:app --reload
5. Browser mein kholo: http://localhost:8000
   Upar green "Live backend connected" dikhna chahiye.

Key ke bina bhi sab chalta hai (built-in rules). Key ke saath planner, lead scoring aur email Claude likhta hai.

## Files
- main.py: backend (agents, tools, retry, human approval)
- index.html: frontend (cursor glow, animations, live workflow)

## API
POST /api/run, POST /api/approve/{run_id}, GET /api/crm, GET /api/health

## Shortcut
Windows: run.bat par double click. Mac/Linux: ./run.sh
Agar "uvicorn not found" aaye to hamesha `python -m uvicorn main:app --reload` use karo.
Backend ke bina bhi index.html double click karke khol sakte ho (preview mode, sab animation chalega).
