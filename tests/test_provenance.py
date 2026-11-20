"""Phase 1 provenance and metrics tests (fast & offline)."""

from __future__ import annotations

import json
from types import SimpleNamespace

from fastapi.testclient import TestClient

from backend.main import app, model_router, rate_limiter


class _FakeModels:
    def __init__(self, responses: dict[str, str]):
        self._responses = responses
        self.calls: list[str] = []

    def generate_content(self, model: str, contents, config=None):
        self.calls.append(model)
        if model not in self._responses:
            raise RuntimeError("503 UNAVAILABLE")
        return SimpleNamespace(
            text=self._responses[model],
            usage_metadata=SimpleNamespace(prompt_token_count=120, candidates_token_count=30),
        )


def test_health_and_metrics_are_truthful():
    model_router.metrics.reset()
    client = TestClient(app)
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert "routing_config" in data
    assert "model_metrics" in data
    assert "inference_mode" not in data
    assert "AlloyDB Express" not in json.dumps(data)

    m_resp = client.get("/api/metrics")
    assert m_resp.status_code == 200
    assert "models" in m_resp.json()


def test_provenance_records_exact_model_and_attempts():
    rate_limiter.reset()
    model_router.metrics.reset()
    orig_client = model_router._client
    fake_models = _FakeModels(
        {
            # Primary T1B fails (503), fallback succeeds
            model_router.settings.tier1_fallback_model: json.dumps(
                {"vote": "NOMINAL", "confidence": 0.92, "reason": "No defect visible"}
            )
        }
    )
    model_router.set_client(SimpleNamespace(models=fake_models))
    try:
        client = TestClient(app)
        resp = client.post(
            "/api/inspect",
            json={
                "line": "PCB",
                "sensor_telemetry": {
                    "vibration_khz": 0.3,
                    "vibration_rms_mms": 0.6,
                    "temperature_c": 242.0,
                    "line_speed_rpm": 1200,
                    "reflow_ramp_c_per_s": 2.0,
                    "reflow_peak_c": 242.0,
                    "reflow_tal_s": 65.0,
                },
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["tier1_triage"]["pass_status"] == "HEALTHY"
        t1_prov = body["tier1_triage"]["provenance_t1b"]
        assert t1_prov["model_id"] == model_router.settings.tier1_fallback_model
        assert t1_prov["producer"] == "FALLBACK_MODEL"
        assert len(t1_prov["attempts"]) == 2
        assert t1_prov["attempts"][0]["status"] == "HTTP_503"
        assert t1_prov["attempts"][1]["status"] == "OK"
        assert t1_prov["attempts"][1]["input_tokens"] == 120
        assert t1_prov["attempts"][1]["output_tokens"] == 30
    finally:
        model_router.set_client(orig_client)
