# Live Security Verification (`eval/security_check.md`)

- **Target URL:** https://vinyas-ai-65216244490.asia-south1.run.app
- **Revision:** `vinyas-ai-00004-srs`
- **Timestamp (UTC):** 2026-11-20T18:41:56Z

| Check | Result |
| --- | --- |
| SPA path traversal (`GET /..%2f..%2frequirements.txt`) | HTTP `404` — Blocked (`True`), zero file contents leaked |
| Secret Manager (`gemini-api-key:latest`) | Bound via `--set-secrets=GEMINI_API_KEY=gemini-api-key:latest` (removed from `--set-env-vars`) |
| CORS policy | Explicit local dev origins only, `allow_credentials=False` |
| Rate limiter | Active per-IP token bucket (`120 req / 10 min` default, env-configurable via `RATE_LIMIT_CAPACITY`, HTTP `429`) |
