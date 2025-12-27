from fastapi import FastAPI, Request, Form
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse
from app.nostr_client import nostr_manager
from nostr_sdk import Keys
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Start the nostr client connection
    await nostr_manager.start()
    yield

app = FastAPI(lifespan=lifespan)

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

@app.get("/")
async def index(request: Request):
    events = await nostr_manager.get_global_feed()
    return templates.TemplateResponse("index.html", {"request": request, "events": events})

@app.get("/post")
async def post_page(request: Request):
    return templates.TemplateResponse("post.html", {"request": request})

@app.post("/post")
async def post_submit(request: Request, nsec: str = Form(...), content: str = Form(...)):
    try:
        keys = Keys.parse(nsec)
        await nostr_manager.publish_note(content, keys)
        return RedirectResponse(url="/", status_code=303)
    except Exception as e:
        return templates.TemplateResponse("post.html", {
            "request": request,
            "error": f"Error publishing note: {str(e)}"
        })

@app.get("/login")
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})
