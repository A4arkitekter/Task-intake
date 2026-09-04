from __future__ import annotations

import threading
import time

_lock = threading.Lock()
_last_seen = 0.0


def mark_inbox_seen() -> None:
    """Kaldes når en browserfane henter indbakken, så vi ved at nogen kigger."""
    global _last_seen
    with _lock:
        _last_seen = time.monotonic()


def seconds_since_inbox_seen() -> float:
    with _lock:
        if not _last_seen:
            return float("inf")
        return time.monotonic() - _last_seen


def reset() -> None:
    global _last_seen
    with _lock:
        _last_seen = 0.0
