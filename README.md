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


