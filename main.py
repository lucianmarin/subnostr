from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager
from app.client import nostr_manager
from app.routes import router as app_router

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Start the nostr client connection
    await nostr_manager.start()
    yield

app = FastAPI(lifespan=lifespan)
application = app

app.mount("/static", StaticFiles(directory="static"), name="static")

# Include consolidated router
app.include_router(app_router)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
