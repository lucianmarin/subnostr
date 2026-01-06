from datetime import datetime, timezone
import re
from nostr_sdk import Nip19Profile

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
    url_pattern = r'(https?://[^\s<>"]+?\.(?:jpg|jpeg|png|gif))'
    
    def replace_with_img(match):
        url = match.group(1)
        return f'<img src="{url}" class="embedded-image" loading="lazy">'

    return re.sub(url_pattern, replace_with_img, text, flags=re.IGNORECASE)

def linkify_urls(text: str) -> str:
    if not text:
        return ""
    # Match URLs but skip those already in src="..." or href="..."
    url_pattern = r'(?<!src=")(?<!href=")(https?://[^\s<>"]+)'
    
    def replace(match):
        url = match.group(1)
        clean_url = url.rstrip('.,;!?')
        trailing = url[len(clean_url):]
        return f'<a href="{clean_url}" target="_blank" rel="noopener noreferrer" class="note-link">{clean_url}</a>{trailing}'

    return re.sub(url_pattern, replace, text, flags=re.IGNORECASE)

def linkify_nostr(text: str) -> str:
    if not text:
        return ""
    
    # Match nostr:nevent1...
    text = re.sub(
        r'(?<!href=")(?<!src=")nostr:(nevent1[a-z0-9]+)', 
        lambda m: f'<a href="/post/{m.group(1)}" class="nostr-link">nostr:{m.group(1)}</a>', 
        text, 
        flags=re.IGNORECASE
    )

    # Match nostr:nprofile1...
    def replace_nprofile(match):
        bech32 = match.group(1)
        try:
            profile = Nip19Profile.from_bech32(bech32)
            pk = profile.public_key()
            npub = pk.to_bech32()
            pubkey = pk.to_hex()
            return f'<a href="/user/{pubkey}" class="nostr-link">nostr:{npub}</a>'
        except Exception:
            return f'<a href="/user/{bech32}" class="nostr-link">nostr:{bech32}</a>'

    text = re.sub(
        r'(?<!href=")(?<!src=")nostr:(nprofile1[a-z0-9]+)', 
        replace_nprofile, 
        text, 
        flags=re.IGNORECASE
    )

    return text
