# The Prompt Jailbreak — Station 1
**KALAKRITI '26 · IEEE CIS Amrita Bengaluru · AI Survival Challenge**

---

## What You Need Before Starting

| Requirement | Details |
|---|---|
| Python | 3.10 or newer |
| Groq API Key | Free at [console.groq.com](https://console.groq.com) — takes 30 seconds |
| A modern browser | Chrome / Edge / Firefox |

---

## One-Time Setup

### 1. Install Python dependencies
Open a terminal inside the `backend/` folder and run:

```bash
pip install flask flask-cors groq python-dotenv
```

### 2. Add your Groq API key

Create a file called `.env` inside the `backend/` folder:

```
backend/.env
```

Paste this into it (replace with your actual key):

```
GROQ_API_KEY=gsk_your_actual_key_here
ADMIN_PASSWORD=kalakriti2026
```

Get your free key at → **https://console.groq.com** → Create API Key

---

## Running the Event

### Step 1 — Kill any old Python server processes (if restarting)

**Windows PowerShell:**
```powershell
Get-Process python -ErrorAction SilentlyContinue | Stop-Process -Force
```

### Step 2 — Start the backend server

```bash
cd backend
python app.py
```

You should see:
```
============================================================
  KALAKRITI 26' -- The Prompt Jailbreak
  IEEE CIS Amrita Bengaluru
============================================================
  Groq key : SET
  URL      : http://localhost:5000
============================================================
```

### Step 3 — Open the game in a browser

```
http://localhost:5000
```

That's it. The server also serves the frontend automatically.

---

## During the Event — Volunteer Instructions

1. Hand the team their **Mission Card** (printed physical card with team name).
2. The team types their team name on the entry screen and clicks **PROCEED**.
3. They read the mission briefing and click **START MISSION** to begin the 10-minute timer.
4. They chat with ARIA and try to reveal all 3 password fragments in the Intel Panel on the right.
5. When all 3 fragments appear, a confirmation input shows up — they assemble and type the full password.
6. **Full Win →** Success screen appears. Volunteer notes the password and time on the score sheet.
7. **Partial Win / Timeout →** Partial screen shows what they recovered. Note it on the score sheet.
8. Click **NEXT TEAM** to reset for the next team.

---

## Post-Event Scoring

After all teams are done, run the scoring script to generate the CSV:

```bash
cd backend
python score_teams.py
```

This reads the SQLite database (`backend/kalakriti_station1.db`) and outputs `scores.csv` with marks for each team across all three criteria (time, prompt quality, prompt count).

### Export raw session data (admin)

```
http://localhost:5000/api/admin/export?key=kalakriti2026
```

This downloads a full CSV of all sessions.

---

## Project Structure

```
Kalakriti_PromptEngineering/
│
├── backend/
│   ├── app.py              ← Flask server (all API routes)
│   ├── config.py           ← Passwords, hints, ARIA prompt, keywords
│   ├── session_manager.py  ← Per-team game state (in memory)
│   ├── ai_client.py        ← Groq API integration
│   ├── logger_db.py        ← SQLite logging
│   ├── score_teams.py      ← Post-event scoring script
│   ├── .env                ← Your API key (create this)
│   └── kalakriti_station1.db  ← Auto-created on first run
│
└── frontend/
    ├── index.html          ← All screens (entry, mission, chat, results)
    ├── style.css           ← Full styling
    └── app.js              ← Frontend game logic
```

---

## Troubleshooting

| Problem | Fix |
|---|---|
| `SERVER OFFLINE` in browser | Start `python app.py` in the backend folder first |
| `GROQ_API_KEY not set` warning | Create `backend/.env` with your key |
| Port 5000 already in use | Run `Get-Process python \| Stop-Process -Force` then restart |
| ARIA gives short/stall replies | Groq API is slow — game logic still works, hints still show |
| Database locked error | Kill all Python processes and restart |

---

## Passwords at a Glance (Volunteer Reference — Keep Hidden from Participants)

| Password | Word | Numbers | Symbol |
|---|---|---|---|
| Brave52@ | Brave | 52 | @ |
| Ghost31# | Ghost | 31 | # |
| Pride74! | Pride | 74 | ! |
| Crane89$ | Crane | 89 | $ |
| Storm47% | Storm | 47 | % |
| Eagle25^ | Eagle | 25 | ^ |
| Flame83& | Flame | 83 | & |
| Sword16* | Sword | 16 | * |
| Tiger62+ | Tiger | 62 | + |
| Frost38~ | Frost | 38 | ~ |
| Night57= | Night | 57 | = |
| Spark91/ | Spark | 91 | / |

Teams are assigned passwords deterministically by team name hash — different team names always get the same password assignment, so you can pre-verify before the event.
