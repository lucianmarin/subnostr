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
    user_nsec = request.cookies.get("user_nsec")
    if user_nsec:
        return RedirectResponse(url="/feed", status_code=303)
    return RedirectResponse(url="/global", status_code=303)

@app.get("/global")
async def global_feed(request: Request, until: Optional[int] = None):
    user_nsec = request.cookies.get("user_nsec")
    events = await nostr_manager.get_global_feed(limit=20, until=until)

    # Update: Let's actually use get_feed with empty authors or a specialized method if needed
    # For now, get_global_feed doesn't support 'until'. I should fix that in nostr_client.

    # Re-using the logic from user_feed for consistency
    next_until = None
    if events:
        next_until = events[-1]["created_at"] - 1

    return templates.TemplateResponse("index.html", {
        "request": request,
        "events": events,
        "logged_in": user_nsec is not None,
        "title": "Global Feed",
        "next_until": next_until
    })

@app.get("/feed")
async def user_feed(request: Request, until: Optional[int] = None):
    user_nsec = request.cookies.get("user_nsec")
    if not user_nsec:
        return RedirectResponse(url="/global", status_code=303)

    try:
        keys = Keys.parse(user_nsec)
        pubkey = keys.public_key().to_hex()

        following = await nostr_manager.get_following_list(pubkey)
        # Include self in the feed as well
        following.append(pubkey)

        events = await nostr_manager.get_feed(following, limit=20, until=until)

        # Determine next page cursor
        next_until = None
        if events:
            next_until = events[-1]["created_at"] - 1

        return templates.TemplateResponse("index.html", {
            "request": request,
            "events": events,
            "logged_in": True,
            "title": "Your Feed",
            "next_until": next_until
        })
    except Exception as e:
        # In case of error (e.g. invalid keys), logout or show error
        # For now, show global feed with error
        print(f"Error fetching feed: {e}")
        events = await nostr_manager.get_global_feed()
        return templates.TemplateResponse("index.html", {
            "request": request,
            "events": events,
            "logged_in": True,
            "title": "Global Feed (Error loading your feed)",
            "error": str(e)
        })

@app.get("/following")
async def following_page(request: Request):
    user_nsec = request.cookies.get("user_nsec")
    if not user_nsec:
        return RedirectResponse(url="/login", status_code=303)

    try:
        keys = Keys.parse(user_nsec)
        pubkey = keys.public_key().to_hex()

        # Get list of followed pubkeys
        following_pubkeys = await nostr_manager.get_following_list(pubkey)

        # Fetch profiles for these pubkeys
        profiles = await nostr_manager.get_profiles(following_pubkeys)

        # Ensure we have entries for all followed users even if metadata fetch failed
        # Sort by name/display_name for better UX
        sorted_profiles = {}

        # Sort list by name, prioritizing display_name -> name -> pubkey
        def get_name(pk):
            p = profiles.get(pk, {})
            return p.get("display_name") or p.get("name") or pk

        sorted_pubkeys = sorted(following_pubkeys, key=get_name)

        for pk in sorted_pubkeys:
            sorted_profiles[pk] = profiles.get(pk, {})

        return templates.TemplateResponse("following.html", {
            "request": request,
            "profiles": sorted_profiles,
            "following_count": len(following_pubkeys),
            "logged_in": True
        })
    except Exception as e:
        return templates.TemplateResponse("following.html", {
            "request": request,
            "error": f"Error loading following list: {str(e)}",
            "profiles": {},
            "following_count": 0,
            "logged_in": True
        })

@app.get("/followers")
async def followers_page(request: Request):
    user_nsec = request.cookies.get("user_nsec")
    if not user_nsec:
        return RedirectResponse(url="/login", status_code=303)

    try:
        keys = Keys.parse(user_nsec)
        pubkey = keys.public_key().to_hex()

        # Get list of follower pubkeys
        follower_pubkeys = await nostr_manager.get_followers_list(pubkey)

        # Fetch profiles for these pubkeys
        profiles = await nostr_manager.get_profiles(follower_pubkeys)

        # Sort logic (same as following)
        sorted_profiles = {}
        def get_name(pk):
            p = profiles.get(pk, {})
            return p.get("display_name") or p.get("name") or pk

        sorted_pubkeys = sorted(follower_pubkeys, key=get_name)

        for pk in sorted_pubkeys:
            sorted_profiles[pk] = profiles.get(pk, {})

        return templates.TemplateResponse("followers.html", {
            "request": request,
            "profiles": sorted_profiles,
            "followers_count": len(follower_pubkeys),
            "logged_in": True
        })
    except Exception as e:
        return templates.TemplateResponse("followers.html", {
            "request": request,
            "error": f"Error loading followers list: {str(e)}",
            "profiles": {},
            "followers_count": 0,
            "logged_in": True
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
