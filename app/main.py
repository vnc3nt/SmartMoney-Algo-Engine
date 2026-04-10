import os
from dotenv import load_dotenv

from app.routers.trigger import router as trigger_router
from app.routers.portfolio import router as portfolio_router

app.include_router(trigger_router)
app.include_router(portfolio_router)

load_dotenv()  # .env vor allem anderen laden!

import uvicorn
from app.base import app  # FastAPI-Instanz mit lifespan aus deinem Code

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", "8000")),
        reload=True,      # nur lokal; für Render entfernen
    )