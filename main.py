from fastapi import FastAPI, Request, Form, Response
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse
from app.nostr_client import nostr_manager
from nostr_sdk import Keys
from contextlib import asynccontextmanager
from typing import Optional
from datetime import datetime, timezone
import re
import json

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Start the nostr client connection
    await nostr_manager.start()
    yield

app = FastAPI(lifespan=lifespan)

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

def time_ago(timestamp: int) -> str:
    now = datetime.now(timezone.utc).timestamp()
    diff = now - timestamp

    if diff < 60:
        return f"{int(diff)}s ago" if diff > 1 else "just now"
    
    minutes = diff / 60
    if minutes < 60:
        return f"{int(minutes)}m ago"
    
    hours = minutes / 60
    if hours < 24:
        return f"{int(hours)}h ago"
    
    days = hours / 24
    if days < 7:
        return f"{int(days)}d ago"
    
    weeks = days / 7
    if weeks < 4:
        return f"{int(weeks)}w ago"
    
    months = days / 30.44  # Average month length
    if months < 12:
        return f"{int(months)}mo ago"
    
    years = days / 365.25
    return f"{int(years)}y ago"

def format_content(text: str) -> str:
    if not text:
        return ""
    lines = text.split('\n')
    paragraphs = []
    for line in lines:
        if line.strip():
            paragraphs.append(f'<p>{line.strip()}</p>')
    return "".join(paragraphs)

def linkify_images(text: str) -> str:
    if not text:
        return ""
    # More robust regex to find image URLs
    url_pattern = r'(https?://[^\s<>\"]+?\.(?:jpg|jpeg|png|gif))'
    
    def replace_with_img(match):
        url = match.group(1)
        return f'<img src="{url}" class="embedded-image" loading="lazy">'

    return re.sub(url_pattern, replace_with_img, text, flags=re.IGNORECASE)

def linkify_urls(text: str) -> str:
    if not text:
        return ""
    # Match URLs but skip those already in src="..." or href="..."
    url_pattern = r'(?<!src=")(?<!href=")(https?://[^\s<>\"]+)'
    
    def replace(match):
        url = match.group(1)
        clean_url = url.rstrip('.,;!?')
        trailing = url[len(clean_url):]
        return f'<a href="{clean_url}" target="_blank" rel="noopener noreferrer" class="note-link">{clean_url}</a>{trailing}'

    return re.sub(url_pattern, replace, text, flags=re.IGNORECASE)

templates.env.filters["linkify_images"] = linkify_images
templates.env.filters["time_ago"] = time_ago
templates.env.filters["format_content"] = format_content
templates.env.filters["linkify_urls"] = linkify_urls

async def get_context(request: Request) -> dict:
    user_nsec = request.cookies.get("user_nsec")
    user_pubkey = None
    user_profile = None
    logged_in = False
    if user_nsec:
        try:
            keys = Keys.parse(user_nsec)
            user_pubkey = keys.public_key().to_hex()
            logged_in = True
            # Fetch user profile for sidebar
            profiles = await nostr_manager.get_profiles([user_pubkey])
            user_profile = profiles.get(user_pubkey)
        except:
            pass
    return {
        "request": request,
        "logged_in": logged_in,
        "user_pubkey": user_pubkey,
        "user_profile": user_profile
    }

@app.get("/")
async def index(request: Request):
    ctx = await get_context(request)
    if ctx["logged_in"]:
        return RedirectResponse(url="/feed", status_code=303)
    return RedirectResponse(url="/global", status_code=303)

@app.get("/global")
async def global_feed(request: Request, until: Optional[int] = None):
    ctx = await get_context(request)
    events = await nostr_manager.get_global_feed(limit=20, until=until)

    next_until = None
    if events:
        next_until = events[-1]["created_at"] - 1

    return templates.TemplateResponse("index.html", {
        **ctx,
        "events": events,
        "title": "Global Feed",
        "next_until": next_until
    })

@app.get("/feed")
async def user_feed(request: Request, until: Optional[int] = None):
    ctx = await get_context(request)
    if not ctx["logged_in"]:
        return RedirectResponse(url="/global", status_code=303)

    try:
        pubkey = ctx["user_pubkey"]
        following = await nostr_manager.get_following_list(pubkey)
        following.append(pubkey)

        events = await nostr_manager.get_feed(following, limit=20, until=until)

        next_until = None
        if events:
            next_until = events[-1]["created_at"] - 1

        return templates.TemplateResponse("index.html", {
            **ctx,
            "events": events,
            "title": "Your Feed",
            "next_until": next_until
        })
    except Exception as e:
        print(f"Error fetching feed: {e}")
        events = await nostr_manager.get_global_feed()
        return templates.TemplateResponse("index.html", {
            **ctx,
            "events": events,
            "title": "Global Feed (Error loading your feed)",
            "error": str(e)
        })

@app.get("/replies")
async def replies_feed(request: Request, until: Optional[int] = None):
    ctx = await get_context(request)
    if not ctx["logged_in"]:
        return RedirectResponse(url="/global", status_code=303)

    try:
        pubkey = ctx["user_pubkey"]
        following = await nostr_manager.get_following_list(pubkey)
        following.append(pubkey)

        events = await nostr_manager.get_replies_feed(following, limit=20, until=until)

        next_until = None
        if events:
            next_until = events[-1]["created_at"] - 1

        return templates.TemplateResponse("index.html", {
            **ctx,
            "events": events,
            "title": "Replies",
            "next_until": next_until
        })
    except Exception as e:
        print(f"Error fetching replies feed: {e}")
        return templates.TemplateResponse("index.html", {
            **ctx,
            "events": [],
            "title": "Replies (Error)",
            "error": str(e)
        })

@app.get("/user/{pubkey}")
async def user_profile(request: Request, pubkey: str, until: Optional[int] = None):
    ctx = await get_context(request)
    
    profiles = await nostr_manager.get_profiles([pubkey])
    profile = profiles.get(pubkey, {})
    
    events = await nostr_manager.get_user_posts(pubkey, limit=20, until=until)
    
    next_until = None
    if events:
        next_until = events[-1]["created_at"] - 1
        
    display_name = profile.get("display_name") or profile.get("name") or f"{pubkey[:8]}..."
    
    return templates.TemplateResponse("index.html", {
        **ctx,
        "events": events,
        "profile": profile,
        "pubkey": pubkey,
        "title": f"Profile: {display_name}",
        "next_until": next_until
    })

@app.get("/following")
async def following_page(request: Request):
    ctx = await get_context(request)
    if not ctx["logged_in"]:
        return RedirectResponse(url="/login", status_code=303)

    try:
        pubkey = ctx["user_pubkey"]
        following_pubkeys = await nostr_manager.get_following_list(pubkey)
        profiles = await nostr_manager.get_profiles(following_pubkeys)

        sorted_profiles = {}
        def get_name(pk):
            p = profiles.get(pk, {})
            return p.get("display_name") or p.get("name") or pk

        sorted_pubkeys = sorted(following_pubkeys, key=get_name)

        for pk in sorted_pubkeys:
            sorted_profiles[pk] = profiles.get(pk, {})

        return templates.TemplateResponse("following.html", {
            **ctx,
            "profiles": sorted_profiles,
            "following_count": len(following_pubkeys)
        })
    except Exception as e:
        return templates.TemplateResponse("following.html", {
            **ctx,
            "error": f"Error loading following list: {str(e)}",
            "profiles": {},
            "following_count": 0
        })

@app.get("/followers")
async def followers_page(request: Request):
    ctx = await get_context(request)
    if not ctx["logged_in"]:
        return RedirectResponse(url="/login", status_code=303)

    try:
        pubkey = ctx["user_pubkey"]
        follower_pubkeys = await nostr_manager.get_followers_list(pubkey)
        profiles = await nostr_manager.get_profiles(follower_pubkeys)

        sorted_profiles = {}
        def get_name(pk):
            p = profiles.get(pk, {})
            return p.get("display_name") or p.get("name") or pk

        sorted_pubkeys = sorted(follower_pubkeys, key=get_name)

        for pk in sorted_pubkeys:
            sorted_profiles[pk] = profiles.get(pk, {})

        return templates.TemplateResponse("followers.html", {
            **ctx,
            "profiles": sorted_profiles,
            "followers_count": len(follower_pubkeys)
        })
    except Exception as e:
        return templates.TemplateResponse("followers.html", {
            **ctx,
            "error": f"Error loading followers list: {str(e)}",
            "profiles": {},
            "followers_count": 0
        })

@app.get("/post")
async def post_page(request: Request):
    ctx = await get_context(request)
    return templates.TemplateResponse("post.html", {**ctx})

@app.post("/post")
async def post_submit(request: Request, content: str = Form(...), nsec: Optional[str] = Form(None)):
    user_nsec = nsec or request.cookies.get("user_nsec")

    if not user_nsec:
        ctx = await get_context(request)
        return templates.TemplateResponse("post.html", {
            **ctx,
            "error": "Private key (nsec) is required to post.",
        })

    try:
        keys = Keys.parse(user_nsec)
        await nostr_manager.publish_note(content, keys)
        return RedirectResponse(url="/", status_code=303)
    except Exception as e:
        ctx = await get_context(request)
        return templates.TemplateResponse("post.html", {
            **ctx,
            "error": f"Error publishing note: {str(e)}",
        })

@app.get("/post/{note_id}")
async def view_post(request: Request, note_id: str):
    ctx = await get_context(request)
    post, replies = await nostr_manager.get_post_with_replies(note_id)
    
    if not post:
        return templates.TemplateResponse("index.html", {
            **ctx,
            "events": [],
            "title": "Post Not Found",
            "error": "Could not find the requested post."
        })

    return templates.TemplateResponse("view_post.html", {
        **ctx,
        "post": post,
        "replies": replies,
        "title": "Post Detail"
    })

@app.post("/post/{note_id}/reply")
async def reply_submit(request: Request, note_id: str, content: str = Form(...), nsec: Optional[str] = Form(None)):
    user_nsec = nsec or request.cookies.get("user_nsec")

    if not user_nsec:
        return RedirectResponse(url="/login", status_code=303)

    try:
        keys = Keys.parse(user_nsec)
        await nostr_manager.publish_note(content, keys, reply_to_id=note_id)
        return RedirectResponse(url=f"/post/{note_id}", status_code=303)
    except Exception as e:
        print(f"Error publishing reply: {e}")
        return RedirectResponse(url=f"/post/{note_id}", status_code=303)

@app.get("/login")
async def login_page(request: Request):
    ctx = await get_context(request)
    return templates.TemplateResponse("login.html", {**ctx})

@app.post("/login")
async def login_submit(request: Request, nsec: str = Form(...)):
    try:
        Keys.parse(nsec)
        response = RedirectResponse(url="/", status_code=303)
        response.set_cookie(key="user_nsec", value=nsec, httponly=True, samesite="lax")
        return response
    except Exception as e:
        ctx = await get_context(request)
        return templates.TemplateResponse("login.html", {
            **ctx,
            "error": f"Invalid nsec: {str(e)}",
        })

@app.get("/logout")
async def logout():
    response = RedirectResponse(url="/", status_code=303)
    response.delete_cookie("user_nsec")
    return response