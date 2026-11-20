"""Deterministic Tier-1A signal processing and process-window gate (`backend/dsp/`)."""

from backend.dsp.envelope import T1AResult, evaluate_t1a_signal_gate

__all__ = ["T1AResult", "evaluate_t1a_signal_gate"]
