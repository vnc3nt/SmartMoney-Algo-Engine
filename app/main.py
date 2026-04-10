# app/main.py
from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv

# 1. .env ZUERST laden — bevor irgendetwas anderes importiert wird
load_dotenv()

from fastapi import FastAPI  # noqa: E402  (nach load_dotenv, das ist Absicht)
import uvicorn  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402

from app.routers.portfolio import router as portfolio_router  # noqa: E402
from app.routers.trigger import router as trigger_router  # noqa: E402


# 2. Lifespan with startup database seeding
@asynccontextmanager
async def lifespan(_app: FastAPI):
    # Startup: Seed database
    try:
        from seed_database import seed_database
        await seed_database()
    except Exception as e:
        print(f"Warning: Database seeding failed: {e}")

    yield

    # Shutdown: TODO: APScheduler stoppen


# 3. app erstellen
app = FastAPI(
    title="SmartMoney Algo-Engine",
    version="0.1.0",
    lifespan=lifespan,
)

# 3.5 CORS Middleware hinzufügen
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",      # Local development
        "http://192.168.105.87:3000", # Network development
        "http://192.168.1.0/24",      # Any local network
        "http://127.0.0.1:3000",      # Localhost
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# 4. Router registrieren
app.include_router(portfolio_router, tags=["Portfolios"])
app.include_router(trigger_router, tags=["Trigger"])


# 5. Health-Endpunkt
@app.get("/health", tags=["Health"])
async def healthcheck() -> dict[str, str]:
    return {"status": "ok"}


# 6. Direktstart (nur lokal)
if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",           # Modul-Pfad, nicht "main:app"
        host="0.0.0.0",
        port=int(os.getenv("PORT", "8000")),
        reload=True,
    )