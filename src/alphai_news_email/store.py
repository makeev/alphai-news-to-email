"""Dedup state.

A capped, insertion-ordered set of article UIDs we've already emailed, persisted
to a JSON file between runs. This is what keeps the bot from re-sending the same
story on every poll.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path


class SeenStore:
    """Persisted set of delivered article UIDs, capped to the most recent ``cap``."""

    def __init__(self, file: str | Path, cap: int = 5000) -> None:
        self._file = Path(file)
        self._cap = cap
        self._seen: set[str] = set()
        self._order: list[str] = []
        self._fresh_run = True

    @property
    def is_first_run(self) -> bool:
        """True when no state file existed at :meth:`load` time (first ever run)."""
        return self._fresh_run

    @property
    def size(self) -> int:
        return len(self._seen)

    def load(self) -> None:
        """Read prior state from disk. A missing file means this is the first run."""
        try:
            data = json.loads(self._file.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return  # first run — start empty
        except (json.JSONDecodeError, OSError):
            return  # corrupt/unreadable — treat as empty rather than crash
        order = data.get("seen", []) if isinstance(data, dict) else []
        self._order = [u for u in order if isinstance(u, str)]
        self._seen = set(self._order)
        self._fresh_run = False

    def has(self, uid: str) -> bool:
        return uid in self._seen

    def add(self, uid: str) -> None:
        if uid in self._seen:
            return
        self._seen.add(uid)
        self._order.append(uid)
        if len(self._order) > self._cap:
            drop = self._order[: len(self._order) - self._cap]
            self._order = self._order[len(self._order) - self._cap :]
            for u in drop:
                self._seen.discard(u)

    def save(self) -> None:
        """Atomically write current state to disk."""
        parent = self._file.parent
        if parent and not parent.exists():
            parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "seen": self._order,
            "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        tmp = self._file.with_suffix(self._file.suffix + ".tmp")
        tmp.write_text(json.dumps(payload), encoding="utf-8")
        tmp.replace(self._file)
