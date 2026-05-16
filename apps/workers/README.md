# Quarrel Workers

FastAPI service powering Quarrel AI's chat streaming, safety screening, memory pipeline, and background jobs.

## Local development

```bash
uv sync
uv run uvicorn app.main:app --reload --port 8000
```

Or via Turborepo from the repo root: `pnpm dev` (runs the web app and workers concurrently).

Hosted on the DigitalOcean droplet via Coolify (see `infra/coolify/`). Behind Caddy with auto-TLS.
