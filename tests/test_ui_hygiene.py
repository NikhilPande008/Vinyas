"""Hygiene & anti-regression tests for UI, backend, and edge client."""

from __future__ import annotations

import re
from pathlib import Path

from backend.config import PROJECT_ROOT


def test_app_jsx_has_no_fake_numeric_defaults_or_tiny_text():
    app_src = (PROJECT_ROOT / "frontend" / "src" / "App.jsx").read_text(encoding="utf-8")
    # No ?? <number> defaults shown as latencies or savings
    assert not re.search(r"\?\?\s*\d+", app_src), "Found made-up numeric ?? default in App.jsx"
    # No text under 12px
    assert not re.search(r"text-\[(?:[1-9]|10|11)px\]", app_src), "Found text smaller than 12px in App.jsx"


def test_no_banned_claims_in_live_code():
    banned = re.compile(
        r"synthid|95\.4|<50 ms|3x faster|sub-10ms|exponential backoff|Live via|Streaming Session via|AlloyDB Express|4\.21 kHz BPFO|Tata Motors",
        flags=re.IGNORECASE,
    )
    paths_to_check = [
        *(PROJECT_ROOT / "backend").rglob("*.py"),
        *(PROJECT_ROOT / "frontend" / "src").rglob("*.js*"),
        PROJECT_ROOT / "edge_client" / "edge_gateway.py",
    ]
    for p in paths_to_check:
        text = p.read_text(encoding="utf-8")
        m = banned.search(text)
        assert m is None, f"Banned claim '{m.group(0)}' found in {p}"


def test_no_hardcoded_healthy_scenario_branch():
    for p in [*(PROJECT_ROOT / "backend").rglob("*.py"), PROJECT_ROOT / "edge_client" / "edge_gateway.py"]:
        text = p.read_text(encoding="utf-8")
        assert '== "LINE_D_HEALTHY"' not in text, f"Hard-coded LINE_D_HEALTHY branch in {p}"
        assert "== 'LINE_D_HEALTHY'" not in text, f"Hard-coded LINE_D_HEALTHY branch in {p}"
