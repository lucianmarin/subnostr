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
    # Regex to find URLs ending with image extensions
    # Updated to include .gif
    url_pattern = r'(https?://\S+\.(?:jpg|jpeg|png|gif))(?:\s|$)'
    
    def replace_with_img(match):
        url = match.group(1)
        return f'<img src="{url}" style="max-width: 100%; border-radius: 5px; margin-top: 10px; display: block;" loading="lazy">'

    return re.sub(url_pattern, replace_with_img, text, flags=re.IGNORECASE)

templates.env.filters["linkify_images"] = linkify_images
templates.env.filters["time_ago"] = time_ago
templates.env.filters["format_content"] = format_content

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

@app.get("/replies")
async def replies_feed(request: Request, until: Optional[int] = None):
    user_nsec = request.cookies.get("user_nsec")
    if not user_nsec:
        return RedirectResponse(url="/global", status_code=303)

    try:
        keys = Keys.parse(user_nsec)
        pubkey = keys.public_key().to_hex()

        following = await nostr_manager.get_following_list(pubkey)
        # Include self in the feed as well
        following.append(pubkey)

        events = await nostr_manager.get_replies_feed(following, limit=20, until=until)

        # Determine next page cursor
        next_until = None
        if events:
            next_until = events[-1]["created_at"] - 1

        return templates.TemplateResponse("index.html", {
            "request": request,
            "events": events,
            "logged_in": True,
            "title": "Replies",
            "next_until": next_until
        })
    except Exception as e:
        print(f"Error fetching replies feed: {e}")
        return templates.TemplateResponse("index.html", {
            "request": request,
            "events": [],
            "logged_in": True,
            "title": "Replies (Error)",
            "error": str(e)
        })

@app.get("/user/{pubkey}")
async def user_profile(request: Request, pubkey: str, until: Optional[int] = None):
    user_nsec = request.cookies.get("user_nsec")
    
    # Fetch profile metadata
    profiles = await nostr_manager.get_profiles([pubkey])
    profile = profiles.get(pubkey, {})
    
    # Fetch user posts (threads + replies)
    events = await nostr_manager.get_user_posts(pubkey, limit=20, until=until)
    
    # Determine next page cursor
    next_until = None
    if events:
        next_until = events[-1]["created_at"] - 1
        
    display_name = profile.get("display_name") or profile.get("name") or f"{pubkey[:8]}..."
    
    return templates.TemplateResponse("index.html", {
        "request": request,
        "events": events,
        "profile": profile,
        "pubkey": pubkey,
        "logged_in": user_nsec is not None,
        "title": f"Profile: {display_name}",
        "next_until": next_until
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

@app.get("/post/{note_id}")
async def view_post(request: Request, note_id: str):
    user_nsec = request.cookies.get("user_nsec")
    post, replies = await nostr_manager.get_post_with_replies(note_id)
    
    if not post:
        return templates.TemplateResponse("index.html", {
            "request": request,
            "events": [],
            "logged_in": user_nsec is not None,
            "title": "Post Not Found",
            "error": "Could not find the requested post."
        })

    return templates.TemplateResponse("view_post.html", {
        "request": request,
        "post": post,
        "replies": replies,
        "logged_in": user_nsec is not None,
        "title": "Post Detail"
    })

@app.post("/post/{note_id}/reply")
async def reply_submit(request: Request, note_id: str, content: str = Form(...), nsec: Optional[str] = Form(None)):
    user_nsec = nsec or request.cookies.get("user_nsec")

    if not user_nsec:
        # Redirect to login or show error on the same page? 
        # For simplicity, redirect to the post page with an error is harder with current setup.
        # Let's just redirect to login if not authenticated.
        return RedirectResponse(url="/login", status_code=303)

    try:
        keys = Keys.parse(user_nsec)
        await nostr_manager.publish_note(content, keys, reply_to_id=note_id)
        # Give some time for relays to process before redirecting? 
        # Actually, let's just redirect and hope for the best (standard web nostr behavior)
        return RedirectResponse(url=f"/post/{note_id}", status_code=303)
    except Exception as e:
        print(f"Error publishing reply: {e}")
        return RedirectResponse(url=f"/post/{note_id}", status_code=303)

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
