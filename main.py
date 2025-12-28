from fastapi import FastAPI, Request, Form, Response
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse
from app.nostr_client import nostr_manager
from nostr_sdk import Keys
from contextlib import asynccontextmanager
from typing import Optional

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
    user_nsec = request.cookies.get("user_nsec")
    return templates.TemplateResponse("index.html", {
        "request": request, 
        "events": events,
        "logged_in": user_nsec is not None
    })

@app.get("/post")
async def post_page(request: Request):
    user_nsec = request.cookies.get("user_nsec")
    return templates.TemplateResponse("post.html", {
        "request": request,
        "logged_in": user_nsec is not None
    })

@app.post("/post")
async def post_submit(request: Request, content: str = Form(...), nsec: Optional[str] = Form(None)):
    user_nsec = nsec or request.cookies.get("user_nsec")
    
    if not user_nsec:
        return templates.TemplateResponse("post.html", {
            "request": request,
            "error": "Private key (nsec) is required to post.",
            "logged_in": False
        })

    try:
        keys = Keys.parse(user_nsec)
        await nostr_manager.publish_note(content, keys)
        return RedirectResponse(url="/", status_code=303)
    except Exception as e:
        return templates.TemplateResponse("post.html", {
            "request": request,
            "error": f"Error publishing note: {str(e)}",
            "logged_in": request.cookies.get("user_nsec") is not None
        })

@app.get("/login")
async def login_page(request: Request):
    user_nsec = request.cookies.get("user_nsec")
    return templates.TemplateResponse("login.html", {
        "request": request,
        "logged_in": user_nsec is not None
    })

@app.post("/login")
async def login_submit(request: Request, nsec: str = Form(...)):
    try:
        Keys.parse(nsec)
        response = RedirectResponse(url="/", status_code=303)
        response.set_cookie(key="user_nsec", value=nsec, httponly=True, samesite="lax")
        return response
    except Exception as e:
        return templates.TemplateResponse("login.html", {
            "request": request,
            "error": f"Invalid nsec: {str(e)}",
            "logged_in": False
        })

@app.get("/logout")
async def logout():
    response = RedirectResponse(url="/", status_code=303)
    response.delete_cookie("user_nsec")
    return response
