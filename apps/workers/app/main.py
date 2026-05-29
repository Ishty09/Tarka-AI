from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.observability import init_sentry
from app.routes import admin, chat, couples, cron, onboarding, safety, tools, webhooks

# Sentry must initialise before FastAPI creates middleware so the
# integration can hook the request lifecycle (§27 step 60).
init_sentry()

app = FastAPI(
    title="Quarrel Workers",
    description="Quarrel AI background workers and API.",
    version="0.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(safety.router)
app.include_router(chat.router)
app.include_router(cron.router)
app.include_router(tools.router)
app.include_router(admin.router)
app.include_router(webhooks.router)
app.include_router(couples.router)
app.include_router(onboarding.router)


@app.get("/health")
async def health() -> dict[str, str]:
    # build_marker is bumped on every meaningful change so the
    # /api/diagnostics endpoint in apps/web can verify the workers
    # container is actually running the latest code, not a stale
    # Coolify image. Bump this string in the same commit as the
    # corresponding web-side fix when you need to be sure.
    return {
        "status": "ok",
        "build_marker": "2026-05-29-council-structured-errors",
    }
