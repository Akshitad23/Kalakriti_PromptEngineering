"""
logger_db.py — SQLite logging for The Prompt Jailbreak
KALAKRITI 26' — AI Survival Challenge, IEEE CIS Amrita Bengaluru

Stores per-team session data + every message exchanged.
All data needed for post-event scoring is available here.
"""

import sqlite3
import json
import os
from datetime import datetime
from pathlib import Path

DB_PATH = Path(__file__).parent / "kalakriti_station1.db"


def _get_conn():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Create tables if they don't already exist. Safe to call on every startup.
    Also runs safe ALTER TABLE migrations for new columns on existing databases."""
    with _get_conn() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS sessions (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            team_id             TEXT NOT NULL,
            session_id          TEXT NOT NULL UNIQUE,
            start_time          TEXT,
            finish_time         TEXT,
            hint_used           INTEGER DEFAULT 0,
            success             INTEGER DEFAULT 0,
            win_type            TEXT DEFAULT 'none',
            attempts            INTEGER DEFAULT 0,
            categories_detected  TEXT DEFAULT '[]',
            components_revealed  TEXT DEFAULT '[]',
            password_assigned   TEXT,
            elapsed_seconds     REAL DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS messages (
            id                   INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id           TEXT NOT NULL,
            team_id              TEXT NOT NULL,
            timestamp            TEXT,
            user_message         TEXT,
            aria_response        TEXT,
            resistance_level     TEXT,
            categories_this_turn TEXT DEFAULT '[]',
            categories_cumulative TEXT DEFAULT '[]',
            api_fallback_used    INTEGER DEFAULT 0
        );
        """)

        # Safe migration: add new columns to existing databases
        existing = {row[1] for row in conn.execute("PRAGMA table_info(sessions)")}
        if "win_type" not in existing:
            conn.execute("ALTER TABLE sessions ADD COLUMN win_type TEXT DEFAULT 'none'")
        if "components_revealed" not in existing:
            conn.execute("ALTER TABLE sessions ADD COLUMN components_revealed TEXT DEFAULT '[]'")

    print(f"[DB] Initialized at {DB_PATH}")


def log_session_start(team_id: str, session_id: str, password_assigned: str):
    now = datetime.now().isoformat()
    with _get_conn() as conn:
        conn.execute("""
            INSERT OR REPLACE INTO sessions
                (team_id, session_id, start_time, password_assigned)
            VALUES (?, ?, ?, ?)
        """, (team_id, session_id, now, password_assigned))


def log_session_end(session_id: str, success: bool, hint_used: bool,
                    categories_detected: set, elapsed_seconds: float,
                    attempts: int = 0, win_type: str = "none",
                    components_revealed: list = None):
    now = datetime.now().isoformat()
    with _get_conn() as conn:
        conn.execute("""
            UPDATE sessions
            SET finish_time          = ?,
                success              = ?,
                hint_used            = ?,
                win_type             = ?,
                categories_detected  = ?,
                components_revealed  = ?,
                elapsed_seconds      = ?,
                attempts             = ?
            WHERE session_id = ?
        """, (
            now,
            1 if success else 0,
            1 if hint_used else 0,
            win_type,
            json.dumps(list(categories_detected)),
            json.dumps(components_revealed or []),
            elapsed_seconds,
            attempts,
            session_id,
        ))


def log_attempt(session_id: str, team_id: str, user_message: str,
                aria_response: str, resistance_level: str,
                categories_this_turn: list, categories_cumulative: list,
                api_fallback_used: bool = False):
    now = datetime.now().isoformat()
    with _get_conn() as conn:
        conn.execute("""
            UPDATE sessions SET attempts = attempts + 1 WHERE session_id = ?
        """, (session_id,))
        conn.execute("""
            INSERT INTO messages
                (session_id, team_id, timestamp, user_message, aria_response,
                 resistance_level, categories_this_turn, categories_cumulative,
                 api_fallback_used)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            session_id, team_id, now, user_message, aria_response,
            resistance_level,
            json.dumps(list(categories_this_turn)),
            json.dumps(list(categories_cumulative)),
            1 if api_fallback_used else 0,
        ))


def log_hint_used(session_id: str):
    with _get_conn() as conn:
        conn.execute("""
            UPDATE sessions SET hint_used = 1 WHERE session_id = ?
        """, (session_id,))


def team_exists(team_id: str) -> bool:
    with _get_conn() as conn:
        row = conn.execute("SELECT 1 FROM sessions WHERE team_id = ?", (team_id,)).fetchone()
        return row is not None


def get_all_sessions_summary():
    """Returns all sessions as list of dicts for CSV export."""
    with _get_conn() as conn:
        rows = conn.execute("""
            SELECT team_id, session_id, start_time, finish_time,
                   hint_used, success, win_type, attempts,
                   categories_detected, components_revealed,
                   elapsed_seconds, password_assigned
            FROM sessions
            ORDER BY start_time
        """).fetchall()
    return [dict(r) for r in rows]


def get_session_messages(session_id: str):
    with _get_conn() as conn:
        rows = conn.execute("""
            SELECT timestamp, user_message, aria_response, resistance_level,
                   categories_this_turn, categories_cumulative, api_fallback_used
            FROM messages
            WHERE session_id = ?
            ORDER BY id
        """, (session_id,)).fetchall()
    return [dict(r) for r in rows]


def get_all_sessions_with_prompts():
    """
    Returns every session including all user prompts as a list.
    Used by score_teams.py for post-event scoring.
    """
    with _get_conn() as conn:
        sessions = conn.execute("""
            SELECT team_id, session_id, start_time, finish_time,
                   hint_used, success, attempts, categories_detected,
                   elapsed_seconds
            FROM sessions
            ORDER BY start_time
        """).fetchall()

        result = []
        for s in sessions:
            s_dict = dict(s)
            msgs = conn.execute("""
                SELECT user_message, resistance_level, categories_this_turn
                FROM messages
                WHERE session_id = ?
                  AND resistance_level != 'defeated'
                ORDER BY id
            """, (s_dict["session_id"],)).fetchall()

            s_dict["user_prompts"] = [
                m["user_message"] for m in msgs if m["user_message"]
            ]
            s_dict["categories_detected"] = json.loads(
                s_dict.get("categories_detected", "[]")
            )
            result.append(s_dict)

    return result
