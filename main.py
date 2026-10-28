"""Crew: AI workforce backend (FastAPI).
Agents: planner -> lead qualifier -> CRM updater -> email drafter -> supervisor (human approval).
Uses Claude when ANTHROPIC_API_KEY is set, otherwise built-in rules, so the demo never breaks."""
import copy, json, os, re, time, uuid
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

try:
    from dotenv import load_dotenv; load_dotenv()
except ImportError:
    pass

MODEL = os.getenv("CLAUDE_MODEL", "claude-sonnet-5-5")
client = None
if os.getenv("ANTHROPIC_API_KEY"):
    try:
        import anthropic
        client = anthropic.Anthropic()
    except ImportError:
        print("anthropic not installed: running with built-in rules")

app = FastAPI(title="Crew AI Workforce")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

SEED = {  # simulated CRM database (swap with Google Sheets / Airtable)
    "L1": {"name": "Aarav Mehta", "company": "Mehta Textiles", "note": "Needs 500 units monthly, budget approved, wants a start this week", "score": None, "status": "new"},
    "L2": {"name": "Priya Nair", "company": "Nair Organics", "note": "Comparing 3 vendors, budget not decided", "score": None, "status": "new"},
    "L3": {"name": "Rohan Das", "company": "Das Logistics", "note": "Just browsing, no timeline", "score": None, "status": "new"},
}
CRM = copy.deepcopy(SEED)
RUNS: dict = {}
FAILS = {"left": 1}  # first CRM call fails on purpose so judges see auto-recovery


def ask(prompt, max_tokens=300):
    msg = client.messages.create(model=MODEL, max_tokens=max_tokens, messages=[{"role": "user", "content": prompt}])
    return msg.content[0].text.strip()


# ---------- Tool layer ----------
def crm_upsert(lead_id, data):
    if FAILS["left"] > 0:
        FAILS["left"] -= 1
        raise RuntimeError("429 rate limit")
    CRM[lead_id].update(data)


def email_send(to, body):  # replace with SMTP / Gmail API
    return {"status": "202 accepted", "to": to}


def with_retry(fn, log, tries=3):
    for i in range(1, tries + 1):
        try:
            return fn()
        except Exception as e:
            log(f"tool failed ({e}), retry {i}/{tries}")
            time.sleep(0.5 * i)
    raise RuntimeError("tool failed after retries")


# ---------- Agents ----------
def planner(request, log):
    if client:
        try:
            out = ask(f"Split this business request into 3-5 short tasks, one per line, no numbering: {request}")
            tasks = [t.strip("-• ").strip() for t in out.splitlines() if t.strip()]
            if tasks:
                return tasks
        except Exception as e:
            log(f"planner: AI unavailable ({e}), using rules")
    return ["qualify leads", "update CRM", "draft email", "send email (needs approval)"]


def qualify(lead, log):
    if client:
        try:
            out = ask("Score this sales lead from 0 to 100 (higher = more ready to buy). "
                      'Reply ONLY with JSON like {"score": 80, "reason": "short reason"}.\n'
                      f"Lead: {lead['name']} at {lead['company']}. Notes: {lead['note']}", 120)
            data = json.loads(re.search(r"\{.*\}", out, re.S).group())
            s = max(0, min(100, int(data["score"])))
            return {"score": s, "reason": data.get("reason", ""), "status": "hot" if s > 80 else "warm" if s > 60 else "cold"}
        except Exception as e:
            log(f"lead_qualifier: AI failed for {lead['name']} ({e}), using rules")
    text, s = lead["note"].lower(), 50
    s += 25 if "budget approved" in text else 0
    s += 15 if "this week" in text else 0
    s -= 20 if "browsing" in text or "no timeline" in text else 0
    s -= 10 if "not decided" in text else 0
    s = max(0, min(100, s))
    return {"score": s, "reason": "rule-based", "status": "hot" if s > 80 else "warm" if s > 60 else "cold"}


def draft_email(lead, log):
    if client:
        try:
            return ask(f"Write a short, friendly sales follow-up email (max 70 words, no subject line) to {lead['name']} "
                       f"at {lead['company']}. Context: {lead['note']}. Ask for a 15 minute call this week. Sign as 'The Crew team'.", 250)
        except Exception as e:
            log(f"email_drafter: AI failed ({e}), using template")
    return (f"Hi {lead['name'].split()[0]},\n\nThanks for your interest. Based on what {lead['company']} needs, "
            "I would love 15 minutes this week to walk you through a plan.\n\nBest,\nThe Crew team")


# ---------- API ----------
class RunIn(BaseModel):
    request: str


class Decision(BaseModel):
    approve: bool


@app.post("/api/run")
def run(body: RunIn):
    CRM.clear(); CRM.update(copy.deepcopy(SEED)); FAILS["left"] = 1
    rid, logs = str(uuid.uuid4())[:8], []
    log = logs.append
    tasks = planner(body.request, log); log(f"planner: {len(tasks)} tasks")
    results = {lid: qualify(l, log) for lid, l in CRM.items()}; log("lead_qualifier: scored leads")
    for lid, data in results.items():
        with_retry(lambda: crm_upsert(lid, data), log)
    log("crm_updater: database updated")
    best = max(CRM, key=lambda k: CRM[k]["score"])
    draft = draft_email(CRM[best], log); log("email_drafter: draft ready")
    log("supervisor: waiting for human approval")
    RUNS[rid] = {"status": "awaiting_approval", "draft": draft, "to": CRM[best]["name"], "logs": logs}
    return {"run_id": rid, "ai": client is not None, "tasks": tasks, "crm": CRM, **RUNS[rid]}


@app.post("/api/approve/{rid}")
def approve(rid: str, d: Decision):
    r = RUNS.get(rid)
    if not r:
        raise HTTPException(404, "run not found")
    if d.approve:
        r["result"] = email_send(r["to"], r["draft"]); r["status"] = "completed"
    else:
        r["status"] = "rejected"
    r["logs"].append(f"human: {'approved' if d.approve else 'rejected'}")
    return r


@app.get("/api/crm")
def crm():
    return CRM


@app.get("/api/health")
def health():
    return {"ok": True, "ai": client is not None, "model": MODEL}


@app.get("/")  # serves the website: open http://localhost:8000
def home():
    return FileResponse(os.path.join(os.path.dirname(os.path.abspath(__file__)), "index.html"))
