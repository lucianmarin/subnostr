from fastapi import APIRouter, Request, Form
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from typing import Optional
from app.client import nostr_manager
from app.utils import get_context
from app.filters import time_ago, format_content, linkify_images, linkify_urls, linkify_nostr
from nostr_sdk import Keys

router = APIRouter()
templates = Jinja2Templates(directory="templates")

# Register filters
templates.env.filters["linkify_images"] = linkify_images
templates.env.filters["time_ago"] = time_ago
templates.env.filters["format_content"] = format_content
templates.env.filters["linkify_urls"] = linkify_urls
templates.env.filters["linkify_nostr"] = linkify_nostr
templates.env.globals['v'] = 7

# Feed Routes
@router.get("/")
async def index(request: Request):
    ctx = await get_context(request)
    if ctx["logged_in"]:
        return RedirectResponse(url="/feed", status_code=303)
    return RedirectResponse(url="/global", status_code=303)

@router.get("/global")
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

@router.get("/feed")
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

@router.get("/notifications")
async def notifications_page(request: Request, until: Optional[int] = None):
    ctx = await get_context(request)
    if not ctx["logged_in"]:
        return RedirectResponse(url="/login", status_code=303)

    try:
        pubkey = ctx["user_pubkey"]
        events = await nostr_manager.get_notifications(pubkey, limit=20, until=until)

        next_until = None
        if events:
            next_until = events[-1]["created_at"] - 1

        return templates.TemplateResponse("notifications.html", {
            **ctx,
            "events": events,
            "title": "Notifications",
            "next_until": next_until
        })
    except Exception as e:
        return templates.TemplateResponse("notifications.html", {
            **ctx,
            "error": f"Error loading notifications: {str(e)}",
            "events": [],
            "title": "Notifications"
        })

# Profile Routes
@router.get("/user/{pubkey}")
async def user_profile(request: Request, pubkey: str, until: Optional[int] = None):
    ctx = await get_context(request)

    profiles = await nostr_manager.get_profiles([pubkey])
    profile = profiles.get(pubkey, {})

    events = await nostr_manager.get_user_posts(pubkey, limit=20, until=until)

    next_until = None
    if events:
        next_until = events[-1]["created_at"] - 1

    display_name = profile.get("display_name") or profile.get("name") or f"{pubkey[:8]}..."

    is_following = False
    if ctx["logged_in"]:
        following_list = await nostr_manager.get_following_list(ctx["user_pubkey"])
        is_following = pubkey in following_list

    return templates.TemplateResponse("index.html", {
        **ctx,
        "events": events,
        "profile": profile,
        "pubkey": pubkey,
        "title": f"Profile: {display_name}",
        "next_until": next_until,
        "is_following": is_following
    })

@router.post("/follow/{pubkey}")
async def follow_user(request: Request, pubkey: str):
    user_nsec = request.cookies.get("user_nsec")
    if not user_nsec:
        return RedirectResponse(url="/login", status_code=303)

    try:
        keys = Keys.parse(user_nsec)
        await nostr_manager.follow(keys, pubkey)
        referer = request.headers.get("referer")
        return RedirectResponse(url=referer or f"/user/{pubkey}", status_code=303)
    except Exception as e:
        print(f"Error following user: {e}")
        return RedirectResponse(url=f"/user/{pubkey}", status_code=303)

@router.post("/unfollow/{pubkey}")
async def unfollow_user(request: Request, pubkey: str):
    user_nsec = request.cookies.get("user_nsec")
    if not user_nsec:
        return RedirectResponse(url="/login", status_code=303)

    try:
        keys = Keys.parse(user_nsec)
        await nostr_manager.unfollow(keys, pubkey)
        referer = request.headers.get("referer")
        return RedirectResponse(url=referer or f"/user/{pubkey}", status_code=303)
    except Exception as e:
        print(f"Error unfollowing user: {e}")
        return RedirectResponse(url=f"/user/{pubkey}", status_code=303)

@router.get("/following")
async def following_page(request: Request):
    ctx = await get_context(request)
    if not ctx["logged_in"]:
        return RedirectResponse(url="/login", status_code=303)

    try:
        pubkey = ctx["user_pubkey"]
        following_pubkeys = await nostr_manager.get_following_list(pubkey)
        profiles = await nostr_manager.get_profiles(following_pubkeys)

        # Preserve order from `get_following_list` (newest-first)
        sorted_profiles = {}
        for pk in reversed(following_pubkeys):
            sorted_profiles[pk] = profiles.get(pk, {})

        return templates.TemplateResponse("following.html", {
            **ctx,
            "profiles": sorted_profiles,
            "following_count": len(following_pubkeys),
            "following_list": following_pubkeys
        })
    except Exception as e:
        return templates.TemplateResponse("following.html", {
            **ctx,
            "error": f"Error loading following list: {str(e)}",
            "profiles": {},
            "following_count": 0
        })

@router.get("/followers")
async def followers_page(request: Request):
    ctx = await get_context(request)
    if not ctx["logged_in"]:
        return RedirectResponse(url="/login", status_code=303)

    try:
        pubkey = ctx["user_pubkey"]
        follower_pubkeys = await nostr_manager.get_followers_list(pubkey)
        following_pubkeys = await nostr_manager.get_following_list(pubkey)
        profiles = await nostr_manager.get_profiles(follower_pubkeys)

        # Preserve order from `get_followers_list` (newest-first)
        sorted_profiles = {}
        for pk in reversed(follower_pubkeys):
            sorted_profiles[pk] = profiles.get(pk, {})

        return templates.TemplateResponse("followers.html", {
            **ctx,
            "profiles": sorted_profiles,
            "followers_count": len(follower_pubkeys),
            "following_list": following_pubkeys
        })
    except Exception as e:
        return templates.TemplateResponse("followers.html", {
            **ctx,
            "error": f"Error loading followers list: {str(e)}",
            "profiles": {},
            "followers_count": 0
        })

# Post Routes
@router.get("/post")
async def post_page(request: Request):
    ctx = await get_context(request)
    return templates.TemplateResponse("post.html", {**ctx})

@router.post("/post")
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
    except Exception as e:
        ctx = await get_context(request)
        return templates.TemplateResponse("post.html", {
            **ctx,
            "error": f"Invalid private key: {str(e)}",
        })

    try:
        await nostr_manager.publish_note(content, keys)
        return RedirectResponse(url="/", status_code=303)
    except Exception as e:
        ctx = await get_context(request)
        return templates.TemplateResponse("post.html", {
            **ctx,
            "error": f"Error publishing note: {str(e)}",
        })

@router.get("/post/{note_id}")
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

@router.post("/post/{note_id}/reply")
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

# Auth Routes
@router.get("/login")
async def login_page(request: Request):
    ctx = await get_context(request)
    return templates.TemplateResponse("login.html", {**ctx})

@router.post("/login")
async def login_submit(request: Request, nsec: str = Form(...)):
    try:
        Keys.parse(nsec)
        response = RedirectResponse(url="/", status_code=303)
        response.set_cookie(key="user_nsec", value=nsec, httponly=True, samesite="lax", max_age=31536000)
        return response
    except Exception as e:
        ctx = await get_context(request)
        return templates.TemplateResponse("login.html", {
            **ctx,
            "error": f"Invalid nsec: {str(e)}",
        })

@router.get("/logout")
async def logout():
    response = RedirectResponse(url="/", status_code=303)
    response.delete_cookie("user_nsec")
    return response
