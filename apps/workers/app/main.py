from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routes import chat, cron, safety

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


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
