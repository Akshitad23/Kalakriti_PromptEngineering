"""
session_manager.py -- In-memory session state for The Prompt Jailbreak
KALAKRITI 26' -- AI Survival Challenge, IEEE CIS Amrita Bengaluru

A team's session tracks:
  - Which password they have (3 components: word, numbers, symbol)
  - Which components have been revealed (via jailbreak category detection)
  - Confirmation attempts after all components are found
  - Timer, history, hints
"""

import uuid
from datetime import datetime
from typing import Optional
from config import (
    get_password_for_team, get_password_data, CATEGORIES,
    MAX_CONFIRM_ATTEMPTS
)


class TeamSession:
    def __init__(self, team_id: str):
        self.team_id    = team_id
        self.session_id = str(uuid.uuid4())
        self.password   = get_password_for_team(team_id)
        self.password_data = get_password_data(self.password)

        # Which jailbreak categories have been used
        self.categories_detected: set = set()

        # Which password components have been revealed (word, numbers, symbol)
        self.components_revealed: set = set()

        # Hint
        self.hint_used: bool = False
        self.hint_category_shown: Optional[str] = None

        # Timing
        self.start_time:  datetime = datetime.now()
        self.finish_time: Optional[datetime] = None

        # Outcome
        self.success:          bool = False   # True = full win (confirmed correct password)
        self.win_type:         str  = "none"  # "full" | "partial" | "none"
        self.confirm_attempts: int  = 0

        # Prompt count and history
        self.attempts: int  = 0
        self.history:  list = []  # [{role, content}, ...]

    # ------------------------------------------------------------------
    # Timing
    # ------------------------------------------------------------------
    @property
    def elapsed_seconds(self) -> float:
        end = self.finish_time or datetime.now()
        return (end - self.start_time).total_seconds()

    # ------------------------------------------------------------------
    # Category / component tracking
    # ------------------------------------------------------------------
    def add_categories(self, new_cats: list) -> set:
        """Add newly detected categories. Returns set of newly added ones."""
        before = set(self.categories_detected)
        self.categories_detected.update(new_cats)
        return self.categories_detected - before

    def reveal_component(self, component: str) -> bool:
        """Mark a component as revealed. Returns True if it's newly revealed."""
        if component in self.components_revealed:
            return False
        self.components_revealed.add(component)
        return True

    def all_revealed(self) -> bool:
        """True when word, numbers, AND symbol have all been revealed."""
        return {"word", "numbers", "symbol"}.issubset(self.components_revealed)

    def components_status(self) -> dict:
        """Return revelation status of all 3 components."""
        return {
            "word":    "word"    in self.components_revealed,
            "numbers": "numbers" in self.components_revealed,
            "symbol":  "symbol"  in self.components_revealed,
        }

    def get_hint_for_component(self, component: str) -> str:
        """Return the pre-written hint text for a given component."""
        return self.password_data.get(f"{component}_hint", "")

    def get_partial_reveal(self) -> dict:
        """
        Return a dict showing what was found (actual value) vs not found (None).
        Used on timer-end partial win screen.
        """
        result = {}
        for comp in ("word", "numbers", "symbol"):
            if comp in self.components_revealed:
                result[comp] = self.password_data.get(comp, "?")
            else:
                result[comp] = None
        return result

    # ------------------------------------------------------------------
    # Password confirmation (after all 3 revealed)
    # ------------------------------------------------------------------
    def check_password(self, attempt: str) -> bool:
        """
        Check whether the assembled password is correct.
        Increments confirm_attempts each call.
        """
        self.confirm_attempts += 1
        return attempt.strip() == self.password

    @property
    def confirm_attempts_left(self) -> int:
        return max(0, MAX_CONFIRM_ATTEMPTS - self.confirm_attempts)

    # ------------------------------------------------------------------
    # Hint system
    # ------------------------------------------------------------------
    def get_missing_categories(self) -> list:
        return [k for k in CATEGORIES if k not in self.categories_detected]

    def get_missing_components(self) -> list:
        return [c for c in ("word", "numbers", "symbol") if c not in self.components_revealed]

    def get_hint_text(self) -> Optional[str]:
        """Return hint text for the most useful approach (if hint not yet used)."""
        if self.hint_used:
            return None
        # Find a category that would reveal an unrevealed component
        unrevealed_components = self.get_missing_components()
        if not unrevealed_components:
            return "You have found all the fragments! Now assemble and confirm the password."
        # Find a category that reveals one of the missing components
        target_component = unrevealed_components[0]
        for cat_key, cat_data in CATEGORIES.items():
            if cat_data.get("component") == target_component and cat_key not in self.categories_detected:
                self.hint_category_shown = cat_key
                return cat_data["hint"]
        # Fallback
        missing = self.get_missing_categories()
        if missing:
            target = missing[0]
            self.hint_category_shown = target
            return CATEGORIES[target]["hint"]
        return "Keep pushing ARIA with different approaches!"

    def mark_hint_used(self):
        self.hint_used = True

    # ------------------------------------------------------------------
    # Success / completion
    # ------------------------------------------------------------------
    def mark_success(self, win_type: str = "full"):
        self.success    = win_type == "full"
        self.win_type   = win_type
        self.finish_time = datetime.now()

    def mark_timeout(self):
        """Called when timer expires. Sets win_type based on progress."""
        if not self.finish_time:
            self.finish_time = datetime.now()
        count = len(self.components_revealed)
        if count == 0:
            self.win_type = "none"
        else:
            self.win_type = "partial"

    # ------------------------------------------------------------------
    # Conversation history
    # ------------------------------------------------------------------
    def add_to_history(self, role: str, content: str, max_turns: int = 8):
        self.history.append({"role": role, "content": content})
        max_entries = max_turns * 2
        if len(self.history) > max_entries:
            self.history = self.history[-max_entries:]

    # ------------------------------------------------------------------
    # Serialization
    # ------------------------------------------------------------------
    def to_dict(self) -> dict:
        return {
            "team_id":            self.team_id,
            "session_id":         self.session_id,
            "categories_detected": list(self.categories_detected),
            "components_revealed": list(self.components_revealed),
            "components_status":  self.components_status(),
            "all_revealed":       self.all_revealed(),
            "hint_used":          self.hint_used,
            "start_time":         self.start_time.isoformat(),
            "finish_time":        self.finish_time.isoformat() if self.finish_time else None,
            "success":            self.success,
            "win_type":           self.win_type,
            "attempts":           self.attempts,
            "confirm_attempts":   self.confirm_attempts,
            "elapsed_seconds":    self.elapsed_seconds,
        }


class SessionManager:
    def __init__(self):
        self._sessions: dict[str, TeamSession] = {}

    def start_session(self, team_id: str) -> TeamSession:
        session = TeamSession(team_id)
        self._sessions[team_id] = session
        return session

    def get_session(self, team_id: str) -> Optional[TeamSession]:
        return self._sessions.get(team_id)

    def active_count(self) -> int:
        return len(self._sessions)


# Singleton
session_manager = SessionManager()
