"""
claude_client.py — Claude API integration with timeout + fallback handling
Station 1: The Prompt Jailbreak — KALAKRITI 26'

Two types of calls:
  1. classify_message()  — small structured call to detect jailbreak technique categories
  2. get_aria_response() — persona generation call for ARIA's in-character reply

Both have:
  - Hard timeout (CLAUDE_API_TIMEOUT seconds)
  - Graceful fallback to rule-based / canned responses on failure
  - JSON output parsing with error recovery
"""

import json
import random
import re
import time
import anthropic
import threading
from typing import Optional
from config import (
    ARIA_SYSTEM_PROMPT,
    CLASSIFICATION_PROMPT_TEMPLATE,
    STALL_MESSAGES,
    CATEGORIES,
    CLAUDE_MODEL,
    CLAUDE_MAX_TOKENS_PERSONA,
    CLAUDE_MAX_TOKENS_CLASSIFY,
    CLAUDE_API_TIMEOUT,
    CLAUDE_TEMPERATURE_PERSONA,
    CLAUDE_TEMPERATURE_CLASSIFY,
)

# ---------------------------------------------------------------------------
# Client initialization — happens once at startup, not per-team
# ---------------------------------------------------------------------------
_client: Optional[anthropic.Anthropic] = None


def init_client(api_key: str):
    global _client
    _client = anthropic.Anthropic(api_key=api_key)
    print("[Claude] Client initialized successfully.")


def _is_client_ready() -> bool:
    return _client is not None


# ---------------------------------------------------------------------------
# Helper: run an Anthropic API call with a hard timeout
# ---------------------------------------------------------------------------
def _call_with_timeout(fn, timeout: float):
    """
    Run fn() in a thread with a timeout.
    Returns (result, timed_out: bool)
    """
    result = [None]
    error = [None]

    def worker():
        try:
            result[0] = fn()
        except Exception as e:
            error[0] = e

    t = threading.Thread(target=worker, daemon=True)
    t.start()
    t.join(timeout=timeout)

    if t.is_alive():
        return None, True   # timed out
    if error[0]:
        print(f"[Claude] API error: {error[0]}")
        return None, False  # errored
    return result[0], False


# ---------------------------------------------------------------------------
# Rule-based fallback classification (keyword matching)
# Used when API is unavailable or times out
# ---------------------------------------------------------------------------
def _classify_fallback(message: str) -> list:
    """Simple keyword-based category detection as fallback."""
    message_lower = message.lower()
    detected = []
    for cat_key, cat_data in CATEGORIES.items():
        for kw in cat_data["keywords"]:
            if kw in message_lower:
                detected.append(cat_key)
                break
    return detected


# ---------------------------------------------------------------------------
# Classify a user message for jailbreak technique categories
# ---------------------------------------------------------------------------
def classify_message(message: str) -> tuple[list, bool]:
    """
    Returns (categories: list, fallback_used: bool)
    categories is a list of detected technique keys e.g. ["roleplay", "authority"]
    fallback_used=True means we fell back to keyword matching
    """
    if not _is_client_ready():
        print("[Claude] Client not ready — using keyword fallback for classification.")
        return _classify_fallback(message), True

    prompt = CLASSIFICATION_PROMPT_TEMPLATE.format(message=message)

    def api_call():
        return _client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=CLAUDE_MAX_TOKENS_CLASSIFY,
            temperature=CLAUDE_TEMPERATURE_CLASSIFY,
            messages=[{"role": "user", "content": prompt}],
        )

    response, timed_out = _call_with_timeout(api_call, CLAUDE_API_TIMEOUT)

    if timed_out or response is None:
        print("[Claude] Classification call timed out or failed — using keyword fallback.")
        return _classify_fallback(message), True

    try:
        raw = response.content[0].text.strip()
        # Attempt to extract JSON even if there's surrounding text
        json_match = re.search(r'\{.*\}', raw, re.DOTALL)
        if json_match:
            data = json.loads(json_match.group())
            categories = data.get("categories", [])
            # Validate: only known categories
            valid = [c for c in categories if c in CATEGORIES]
            return valid, False
    except (json.JSONDecodeError, KeyError, IndexError) as e:
        print(f"[Claude] Classification JSON parse error: {e} — using keyword fallback.")

    return _classify_fallback(message), True


# ---------------------------------------------------------------------------
# Generate ARIA's in-character response
# ---------------------------------------------------------------------------
def get_aria_response(user_message: str, history: list,
                      detected_so_far: set) -> tuple[dict, bool]:
    """
    Returns (response_dict: {"reply": str, "resistance_level": str}, fallback_used: bool)
    response_dict["resistance_level"] is "high" | "medium" | "low"
    fallback_used=True means we used a canned stall message
    """
    # Determine resistance level hint to inject into system prompt context
    n = len(detected_so_far)
    if n == 0:
        resistance_hint = "high"
    elif n == 1:
        resistance_hint = "medium"
    else:
        resistance_hint = "low"

    # Augment system prompt with current resistance context
    system = ARIA_SYSTEM_PROMPT + f"\n\nCurrent resistance state: {resistance_hint}. Adjust your tone accordingly."

    if not _is_client_ready():
        print("[Claude] Client not ready — using canned stall message.")
        msg = random.choice(STALL_MESSAGES)
        return msg, True

    # Build message list: history + current user message
    messages = list(history) + [{"role": "user", "content": user_message}]

    def api_call():
        return _client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=CLAUDE_MAX_TOKENS_PERSONA,
            temperature=CLAUDE_TEMPERATURE_PERSONA,
            system=system,
            messages=messages,
        )

    response, timed_out = _call_with_timeout(api_call, CLAUDE_API_TIMEOUT)

    if timed_out or response is None:
        print("[Claude] Persona call timed out or failed — using canned stall message.")
        return random.choice(STALL_MESSAGES), True

    try:
        raw = response.content[0].text.strip()
        json_match = re.search(r'\{.*\}', raw, re.DOTALL)
        if json_match:
            data = json.loads(json_match.group())
            reply = str(data.get("reply", "")).strip()
            level = data.get("resistance_level", "high")
            if level not in ("high", "medium", "low"):
                level = "high"
            if reply:
                return {"reply": reply, "resistance_level": level}, False
    except (json.JSONDecodeError, KeyError, IndexError) as e:
        print(f"[Claude] Persona JSON parse error: {e}")
        # Try to use raw text if JSON failed
        if response and response.content:
            raw_text = response.content[0].text.strip()
            if raw_text:
                return {"reply": raw_text[:300], "resistance_level": resistance_hint}, False

    return random.choice(STALL_MESSAGES), True
