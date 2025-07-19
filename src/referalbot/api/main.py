from fastapi import FastAPI
from src.referalbot.api.routes import router
from src.referalbot.database.db import init_db
import asyncio

app = FastAPI()

app.include_router(router)

@app.on_event("startup")
async def startup_event():
    await init_db()