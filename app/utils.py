from fastapi import Request
from app.client import nostr_manager
from nostr_sdk import Keys

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
        except Exception:
            pass
    return {
        "request": request,
        "logged_in": logged_in,
        "user_pubkey": user_pubkey,
        "user_profile": user_profile
    }
