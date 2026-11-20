"""
frontend/components/fault_injection_studio_view.py
Unified wrapper delegating to `frontend/components/lyria_studio_view.py`
so both `render_fault_injection_studio_view` and `render_lyria_studio_view`
share the redesigned tactile 4-card scenario triggers, dual-channel oscilloscope,
and un-truncated responsive flex KPI cards.
"""
from frontend.components.lyria_studio_view import (
    render_lyria_studio_view,
    render_fault_injection_studio_view,
)

__all__ = ["render_lyria_studio_view", "render_fault_injection_studio_view"]
