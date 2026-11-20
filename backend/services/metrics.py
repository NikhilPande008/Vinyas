"""Per-model runtime metrics tracker for `/health` and `/api/metrics`."""

from __future__ import annotations

from collections import deque
from datetime import datetime, timezone
import statistics
import threading
from typing import Any, Optional


class ModelMetricsRegistry:
    """Tracks real per-model call outcomes and measured latencies since startup."""

    def __init__(self, max_latencies: int = 200) -> None:
        self._max_latencies = max_latencies
        self._lock = threading.Lock()
        self._stats: dict[str, dict[str, Any]] = {}

    def _entry(self, model_id: str) -> dict[str, Any]:
        entry = self._stats.get(model_id)
        if entry is None:
            entry = {
                "ok": 0,
                "fallback": 0,
                "errors": 0,
                "last_ok_at": None,
                "latencies_ms": deque(maxlen=self._max_latencies),
            }
            self._stats[model_id] = entry
        return entry

    def record_attempt(
        self,
        model_id: str,
        status: str,
        latency_ms: int,
        is_fallback: bool = False,
    ) -> None:
        with self._lock:
            entry = self._entry(model_id)
            if status == "OK":
                entry["ok"] += 1
                if is_fallback:
                    entry["fallback"] += 1
                entry["last_ok_at"] = datetime.now(timezone.utc).isoformat()
                entry["latencies_ms"].append(int(latency_ms))
            elif status != "SKIPPED":
                entry["errors"] += 1

    def record_fallback_used(self, stage: str) -> None:
        with self._lock:
            entry = self._entry(f"fallback:{stage}")
            entry["fallback"] += 1

    def snapshot(self) -> dict[str, dict[str, Any]]:
        with self._lock:
            out: dict[str, dict[str, Any]] = {}
            for model_id, entry in sorted(self._stats.items()):
                lats = list(entry["latencies_ms"])
                p50: Optional[int] = int(statistics.median(lats)) if lats else None
                out[model_id] = {
                    "ok": entry["ok"],
                    "fallback": entry["fallback"],
                    "errors": entry["errors"],
                    "last_ok_at": entry["last_ok_at"],
                    "p50_ms": p50,
                }
            return out

    def reset(self) -> None:
        with self._lock:
            self._stats.clear()
