# Subnostr

Subnostr is a small, lightweight web frontend for browsing and interacting with Nostr relays. It provides a simple timeline, user profiles, follow/unfollow management, posting, and basic thread/reply views.

Features
- View global feed and user feed
- View user profiles and posts
- Follow and unfollow users (contact lists)
- Post notes and reply to posts
- Delete your own posts (publishes Kind 5 deletion event)

Requirements
- Python 3.10+
- See `requirements.txt` for Python dependencies

Quick start (development)

1. Create and activate a virtual environment (recommended):

```bash
python -m venv .venv
source .venv/bin/activate
```

2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Start the development server with Uvicorn:

```bash
uvicorn main:app --reload
```

4. Open your browser at http://127.0.0.1:8000

Notes
- The app uses the `user_nsec` cookie to store a user's private key in nsec format for signing actions (posting, follow/unfollow, delete). Keep your keys safe — this demo stores them client-side and is not secure for production use.
- Deletions are published as Nostr Kind 5 events and rely on relays honoring them.

Contributing
- Pull requests and issues welcome. Run linters/tests before opening a PR.

License
- See the `LICENSE` file.
