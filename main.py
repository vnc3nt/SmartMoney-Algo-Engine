import os
from dotenv import load_dotenv

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