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


def compute_gate_token_accounting(
    n_parts: int,
    t1_tokens_total: int,
    n_escalated: int,
    t2_success_tokens: list[int],
) -> dict[str, Any]:
    """Token effect of the Tier-1 gate, independent of Tier-2 API failures.

    A failed Tier-2 call spends ~0 tokens; counting it as a "saving" would reward outages.
    So every escalated part is charged the mean measured Tier-2 cost of the calls that
    succeeded, and the cloud-only baseline charges that same mean to every part:

        gated      = sum(T1 tokens over all parts) + n_escalated x mean(T2 tokens)
        cloud_only = n_parts x mean(T2 tokens)
        saving_pct = 100 x (1 - gated / cloud_only)   (negative when the gate escalates everything)
    """
    mean_t2 = int(statistics.mean(t2_success_tokens)) if t2_success_tokens else 0
    gated = int(t1_tokens_total + n_escalated * mean_t2)
    cloud_only = int(n_parts * mean_t2)
    saving_pct = round(100.0 * (1.0 - gated / cloud_only), 1) if cloud_only > 0 else None
    return {
        "n_parts": n_parts,
        "n_escalated": n_escalated,
        "t1_tokens_total": int(t1_tokens_total),
        "t2_calls_succeeded": len(t2_success_tokens),
        "t2_calls_failed": max(0, n_escalated - len(t2_success_tokens)),
        "mean_t2_tokens": mean_t2,
        "gated_tokens": gated,
        "cloud_only_tokens": cloud_only,
        "saving_pct": saving_pct,
        "method": "gated = T1 tokens (all parts) + escalations x mean measured T2 tokens; cloud_only = N x mean measured T2 tokens",
    }
