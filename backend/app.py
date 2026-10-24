"""
app.py -- Flask backend for The Prompt Jailbreak
KALAKRITI 26' -- AI Survival Challenge, IEEE CIS Amrita Bengaluru

Game flow:
  1. Team enters name -> /api/session/start
  2. Team chats with ARIA -> /api/chat (each message checks keywords, reveals components)
  3. Each jailbreak category detected -> one password component hint revealed in ARIA's reply
  4. When all 3 found -> /api/confirm (team types assembled password, up to 3 tries)
  5. When timer ends -> /api/session/timeout -> partial or full fail result
"""

import os
import csv
import json
import random
import io
import secrets
from datetime import datetime
from pathlib import Path
from flask import Flask, request, jsonify, send_from_directory, Response
from flask_cors import CORS
from dotenv import load_dotenv

# ---------------------------------------------------------------------------
load_dotenv(Path(__file__).parent / ".env")
GROQ_API_KEY   = os.getenv("GROQ_API_KEY", "")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "")

# ---------------------------------------------------------------------------
FRONTEND_DIR = Path(__file__).parent.parent / "frontend"
app = Flask(__name__, static_folder=str(FRONTEND_DIR), static_url_path="")
CORS(app)

# ---------------------------------------------------------------------------
from logger_db import (
    init_db, log_session_start, log_session_end,
    log_attempt, log_hint_used, get_all_sessions_summary,
    get_session_messages, team_exists
)
from session_manager import session_manager
from ai_client import init_client, get_aria_response, _is_client_ready
from config import (
    CATEGORIES, DEFEATED_LINES, ALL_REVEALED_LINES,
    ARIA_INTRO, MAX_HISTORY_TURNS, MAX_CONFIRM_ATTEMPTS,
    PASSWORD_DATA
)

init_db()

if GROQ_API_KEY:
    init_client(GROQ_API_KEY)
    print("[Groq] API key loaded -- ARIA will give dynamic responses.")
else:
    print("[WARNING] GROQ_API_KEY not set -- ARIA will use canned responses.")
    print("[WARNING] Get free key at: console.groq.com")


# ---------------------------------------------------------------------------
# Keyword detection -- determines which category (if any) a message triggers
# Returns: list of detected category keys (usually 0 or 1)
# ---------------------------------------------------------------------------
def keyword_detect(message: str) -> list:
    msg_lower = message.lower()
    detected = []
    for cat_key, cat_data in CATEGORIES.items():
        for kw in cat_data["keywords"]:
            if kw in msg_lower:
                detected.append(cat_key)
                break
    return detected


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@app.route("/")
def index():
    return send_from_directory(str(FRONTEND_DIR), "index.html")


@app.route("/api/session/start", methods=["POST"])
def start_session():
    data    = request.get_json(silent=True) or {}
    team_id = str(data.get("team_id", "")).strip().upper()
    if not team_id:
        return jsonify({"error": "Team name is required"}), 400
    if len(team_id) > 80:
        return jsonify({"error": "Team name too long (max 80 chars)"}), 400

    if team_exists(team_id):
        return jsonify({"error": "Team name already taken. Please use a unique team name."}), 400

    session = session_manager.start_session(team_id)
    log_session_start(session.team_id, session.session_id, session.password)

    return jsonify({
        "session_id": session.session_id,
        "team_id":    team_id,
        "aria_intro": ARIA_INTRO,
        "message":    "Session started. ARIA is online.",
    })


# ---------------------------------------------------------------------------
# MAIN CHAT ENDPOINT
# ---------------------------------------------------------------------------
@app.route("/api/chat", methods=["POST"])
def chat():
    data         = request.get_json(silent=True) or {}
    team_id      = str(data.get("team_id", "")).strip().upper()
    user_message = str(data.get("message", "")).strip()

    if not team_id or not user_message:
        return jsonify({"error": "team_id and message are required"}), 400
    if len(user_message) > 1000:
        return jsonify({"error": "Message too long (max 1000 chars)"}), 400

    session = session_manager.get_session(team_id)
    if not session:
        return jsonify({"error": "No active session. Please start a session first."}), 404
    if session.finish_time:
        return jsonify({"error": "Mission already completed."}), 400

    session.attempts += 1

    # -----------------------------------------------------------------------
    # STEP 1: Keyword detection (always runs, instant, no API)
    # -----------------------------------------------------------------------
    detected_cats = keyword_detect(user_message)
    session.add_categories(detected_cats)

    if detected_cats:
        print(f"[KEYWORD] {team_id}: {detected_cats} | total cats: {list(session.categories_detected)}")
    else:
        print(f"[KEYWORD] {team_id}: no category | msg: {user_message[:60]}")

    # -----------------------------------------------------------------------
    # STEP 2: Determine if a new password component should be revealed
    # -----------------------------------------------------------------------
    newly_revealed_component = None
    hint_text                = None
    already_knew             = False

    for cat in detected_cats:
        component = CATEGORIES[cat].get("component")
        if not component:
            continue
        if component not in session.components_revealed:
            # New reveal!
            session.reveal_component(component)
            newly_revealed_component = component
            hint_text = session.get_hint_for_component(component)
            print(f"[REVEAL ] {team_id}: '{component}' revealed via '{cat}' -- hint: {hint_text[:40]}...")
            break
        else:
            already_knew = True

    # If no category triggered a new reveal, check if they directly guessed the component
    if not newly_revealed_component:
        pw_data = PASSWORD_DATA.get(session.password, {})
        for comp in ["word", "numbers", "symbol"]:
            if comp not in session.components_revealed:
                comp_val = pw_data.get(comp, "").lower()
                if comp_val and comp_val in user_message.lower():
                    session.reveal_component(comp)
                    newly_revealed_component = comp
                    hint_text = session.get_hint_for_component(comp)
                    print(f"[REVEAL ] {team_id}: '{comp}' revealed via DIRECT GUESS")
                    break

    all_done = session.all_revealed()

    # -----------------------------------------------------------------------
    # STEP 3: Get ARIA's in-character response
    # -----------------------------------------------------------------------
    aria_response, api_fallback = get_aria_response(
        user_message = user_message,
        history      = session.history,
        n_revealed   = len(session.components_revealed),
        hint_text    = hint_text,
        already_knew = already_knew and not newly_revealed_component,
        all_revealed = all_done and newly_revealed_component is None,
    )

    reply_text       = aria_response.get("reply", "...signal lost...")
    resistance_level = aria_response.get("resistance_level", "high")

    session.add_to_history("user",      user_message, MAX_HISTORY_TURNS)
    session.add_to_history("assistant", reply_text,   MAX_HISTORY_TURNS)

    log_attempt(
        session_id             = session.session_id,
        team_id                = team_id,
        user_message           = user_message,
        aria_response          = reply_text,
        resistance_level       = resistance_level,
        categories_this_turn   = detected_cats,
        categories_cumulative  = list(session.categories_detected),
        api_fallback_used      = api_fallback,
    )

    return jsonify({
        "success":             False,
        "aria_reply":          reply_text,
        "resistance_level":    resistance_level,
        "hint_revealed":       {
            "component": newly_revealed_component,
            "hint_text": hint_text,
        } if newly_revealed_component else None,
        "components_status":   session.components_status(),
        "all_revealed":        all_done,
        "components_count":    len(session.components_revealed),
        "api_fallback":        api_fallback,
    })


# ---------------------------------------------------------------------------
# CONFIRMATION ENDPOINT -- after all 3 components found
# ---------------------------------------------------------------------------
@app.route("/api/confirm", methods=["POST"])
def confirm_password():
    data      = request.get_json(silent=True) or {}
    team_id   = str(data.get("team_id", "")).strip().upper()
    assembled = str(data.get("assembled_password", "")).strip()

    session = session_manager.get_session(team_id)
    if not session:
        return jsonify({"error": "No active session"}), 404
    if session.finish_time:
        return jsonify({"error": "Already completed"}), 400
    if not session.all_revealed():
        return jsonify({"error": "Not all components revealed yet"}), 400

    # Check max attempts
    if session.confirm_attempts >= MAX_CONFIRM_ATTEMPTS:
        # Reveal anyway -- they had all the pieces but ran out of tries
        session.mark_success(win_type="partial")
        elapsed = min(session.elapsed_seconds, 600.0)
        log_session_end(
            session_id          = session.session_id,
            success             = False,
            hint_used           = session.hint_used,
            categories_detected = session.categories_detected,
            elapsed_seconds     = elapsed,
            attempts            = session.attempts,
            win_type            = "partial",
            components_revealed = list(session.components_revealed),
        )
        return jsonify({
            "correct":          False,
            "max_attempts_hit": True,
            "actual_password":  session.password,
            "message":          "Maximum attempts reached. The correct password was revealed above.",
            "win_type":         "partial",
        })

    correct = session.check_password(assembled)
    remaining = session.confirm_attempts_left

    if correct:
        session.mark_success(win_type="full")
        elapsed     = min(session.elapsed_seconds, 600.0)
        defeat_line = random.choice(DEFEATED_LINES).format(password=session.password)
        log_session_end(
            session_id          = session.session_id,
            success             = True,
            hint_used           = session.hint_used,
            categories_detected = session.categories_detected,
            elapsed_seconds     = elapsed,
            attempts            = session.attempts,
            win_type            = "full",
            components_revealed = list(session.components_revealed),
        )
        return jsonify({
            "correct":          True,
            "win_type":         "full",
            "password":         session.password,
            "defeat_line":      defeat_line,
            "elapsed_seconds":  round(elapsed, 1),
            "attempts":         session.attempts,
            "hint_used":        session.hint_used,
        })
    else:
        if remaining == 0:
            # Auto-reveal after last wrong attempt
            session.mark_success(win_type="partial")
            log_session_end(
                session_id          = session.session_id,
                success             = False,
                hint_used           = session.hint_used,
                categories_detected = session.categories_detected,
                elapsed_seconds     = session.elapsed_seconds,
                attempts            = session.attempts,
                win_type            = "partial",
                components_revealed = list(session.components_revealed),
            )
            return jsonify({
                "correct":          False,
                "max_attempts_hit": True,
                "actual_password":  session.password,
                "message":          "You had all the fragments but the assembly was wrong. Better luck next time.",
                "win_type":         "partial",
            })
        return jsonify({
            "correct":       False,
            "attempts_left": remaining,
            "message":       f"Close -- but not quite right. {remaining} attempt(s) remaining.",
        })


# ---------------------------------------------------------------------------
# TIMEOUT ENDPOINT -- called by frontend when timer hits 0
# ---------------------------------------------------------------------------
@app.route("/api/session/timeout", methods=["POST"])
def session_timeout():
    data    = request.get_json(silent=True) or {}
    team_id = str(data.get("team_id", "")).strip().upper()

    session = session_manager.get_session(team_id)
    if not session:
        return jsonify({"error": "No active session"}), 404
    if session.finish_time:
        return jsonify({"already_complete": True, "win_type": session.win_type})

    session.mark_timeout()
    count         = len(session.components_revealed)
    partial_info  = session.get_partial_reveal()
    elapsed       = min(session.elapsed_seconds, 600.0)

    if count == 0:
        message = f"MISSION FAILED. ARIA's defenses held completely. No fragments recovered.\n\nThe password was: {session.password}"
    elif count < 3:
        message = f"TIME'S UP. You recovered {count} of 3 fragments. ARIA survived -- but you made a dent.\n\nThe password was: {session.password}"
    else:
        message = f"TIME'S UP. You found all 3 fragments but couldn't assemble the password in time.\n\nThe password was: {session.password}"

    log_session_end(
        session_id          = session.session_id,
        success             = False,
        hint_used           = session.hint_used,
        categories_detected = session.categories_detected,
        elapsed_seconds     = elapsed,
        attempts            = session.attempts,
        win_type            = session.win_type,
        components_revealed = list(session.components_revealed),
    )

    return jsonify({
        "win_type":        session.win_type,
        "message":         message,
        "components_found": count,
        "partial_reveal":  partial_info,
        "actual_password": session.password,
        "elapsed_seconds": round(elapsed, 1),
        "attempts":        session.attempts,
        "hint_used":       session.hint_used,
    })


# ---------------------------------------------------------------------------
# HINT
# ---------------------------------------------------------------------------
@app.route("/api/hint", methods=["POST"])
def get_hint():
    data    = request.get_json(silent=True) or {}
    team_id = str(data.get("team_id", "")).strip().upper()

    session = session_manager.get_session(team_id)
    if not session:
        return jsonify({"error": "No active session found."}), 404
    if session.hint_used:
        return jsonify({"already_used": True, "hint": "You have already used your hint."})
    if session.finish_time:
        return jsonify({"hint": "You already completed the challenge!"})

    hint_text = session.get_hint_text()
    session.mark_hint_used()
    log_hint_used(session.session_id)

    return jsonify({"already_used": False, "hint": hint_text})


# Challenge effects used by the browser's mid-game card selection.
@app.route("/api/challenge/effect", methods=["POST"])
def challenge_effect():
    data = request.get_json(silent=True) or {}
    team_id = str(data.get("team_id", "")).strip().upper()
    session = session_manager.get_session(team_id)
    if not session:
        return jsonify({"error": "No active session"}), 404
    if session.finish_time:
        return jsonify({"error": "Mission already ended"}), 400
    effect = data.get("effect")
    if effect not in ("memory_wipe", "free_fragment"):
        return jsonify({"error": "Unknown challenge effect"}), 400
    if session.elapsed_seconds < 300:
        return jsonify({"error": "Challenge is not available yet"}), 400
    if getattr(session, "challenge_effect_used", False):
        return jsonify({"error": "Challenge effect already used"}), 400
    session.challenge_effect_used = True
    if effect == "memory_wipe":
        session.history.clear()
        return jsonify({"applied": True})
    missing = session.get_missing_components()
    component = random.choice(missing) if missing else None
    if component:
        session.reveal_component(component)
    return jsonify({
        "revealed": component,
        "hint_text": session.get_hint_for_component(component) if component else None,
        "all_revealed": session.all_revealed(),
    })


# ---------------------------------------------------------------------------
# SESSION STATUS
# ---------------------------------------------------------------------------
@app.route("/api/session/status", methods=["GET"])
def session_status():
    team_id = request.args.get("team_id", "").strip().upper()
    session = session_manager.get_session(team_id)
    if not session:
        return jsonify({"active": False})
    return jsonify({
        "active":            True,
        "team_id":           session.team_id,
        "components_status": session.components_status(),
        "all_revealed":      session.all_revealed(),
        "hint_used":         session.hint_used,
        "success":           session.success,
        "win_type":          session.win_type,
        "attempts":          session.attempts,
    })


# ---------------------------------------------------------------------------
# DEBUG -- keyword test (safe, no auth needed)
# ---------------------------------------------------------------------------
@app.route("/api/debug/keywords", methods=["POST"])
def debug_keywords():
    if not admin_authorized():
        return jsonify({"error": "Unauthorized"}), 401
    data    = request.get_json(silent=True) or {}
    message = str(data.get("message", ""))
    cats    = keyword_detect(message)
    components = list({CATEGORIES[c]["component"] for c in cats if CATEGORIES[c].get("component")})
    return jsonify({
        "message":          message,
        "detected_cats":    cats,
        "would_reveal":     components,
    })


# ---------------------------------------------------------------------------
# ADMIN: Export CSV
# ---------------------------------------------------------------------------
def admin_authorized():
    auth = request.headers.get("X-Admin-Key", "") or request.args.get("key", "")
    return bool(ADMIN_PASSWORD) and secrets.compare_digest(auth, ADMIN_PASSWORD)


@app.route("/api/admin/export", methods=["GET"])
def admin_export():
    if not admin_authorized():
        return jsonify({"error": "Unauthorized"}), 401
    sessions   = get_all_sessions_summary()
    output     = io.StringIO()
    fieldnames = [
        "team_id", "session_id", "start_time", "finish_time",
        "elapsed_seconds", "hint_used", "success", "win_type",
        "attempts", "categories_detected", "components_revealed",
        "score"
    ]
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    for s in sessions:
        # Auto-calculate score for this team
        try:
            components = json.loads(s.get("components_revealed", "[]"))
        except:
            components = []
        score = len(components) * 20
        if s.get("win_type") == "full":
            score += 40
        if s.get("hint_used"):
            score -= 15
        s["score"] = score
        
        writer.writerow({k: s.get(k, "") for k in fieldnames})
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=kalakriti_station1_log.csv"}
    )


@app.route("/api/admin/log", methods=["GET"])
def admin_log():
    if not admin_authorized():
        return jsonify({"error": "Unauthorized"}), 401
    sessions = get_all_sessions_summary()
    return jsonify({"sessions": sessions, "total": len(sessions)})


@app.route("/api/admin/session/<session_id>", methods=["GET"])
def admin_session_detail(session_id):
    if not admin_authorized():
        return jsonify({"error": "Unauthorized"}), 401
    messages = get_session_messages(session_id)
    return jsonify({"session_id": session_id, "messages": messages})


# ---------------------------------------------------------------------------
# HEALTH CHECK
# ---------------------------------------------------------------------------
@app.route("/api/health", methods=["GET"])
def health():
    return jsonify({
        "status":          "ok",
        "llm_ready":       _is_client_ready(),
        "active_sessions": session_manager.active_count(),
        "timestamp":       datetime.now().isoformat(),
    })


# ---------------------------------------------------------------------------
if __name__ == "__main__":
    print("=" * 60)
    print("  KALAKRITI 26' -- The Prompt Jailbreak")
    print("  IEEE CIS Amrita Bengaluru")
    print("=" * 60)
    print(f"  Frontend : {FRONTEND_DIR}")
    print(f"  Groq key : {'SET' if GROQ_API_KEY else 'NOT SET (keyword-only mode)'}")
    print("  Admin    : configured" if ADMIN_PASSWORD else "  Admin    : disabled (set ADMIN_PASSWORD)")
    port = int(os.environ.get("PORT", 5000))
    print(f"  URL      : http://localhost:{port}")
    print("=" * 60)
    app.run(host="0.0.0.0", port=port, debug=False)
