# Nostr Web Client Development Plan

This plan outlines the steps to build a Nostr web client using Python (FastAPI), Jinja2 templates, and standard HTML/CSS.

## Phase 1: Project Setup and Boilerplate
- [ ] **Initialize Project**: Set up the project directory and virtual environment.
- [ ] **Dependencies**: Create `requirements.txt` with `fastapi`, `uvicorn`, `jinja2`, and `nostr-sdk` (or compatible library).
- [ ] **Basic Structure**: Create the folder structure:
    - `app/` (application logic)
    - `templates/` (HTML templates)
    - `static/` (CSS, images)
    - `main.py` (entry point)
- [ ] **Hello World**: Create a basic FastAPI route returning a rendered template to ensure setup works.

## Phase 2: Nostr Backend Logic
- [ ] **Relay Manager**: Implement a Python module to handle connections to Nostr relays.
- [ ] **Event Fetching**: Create functions to query relays for text notes (Kind 1) and metadata (Kind 0).
- [ ] **Event Publishing**: Create functions to sign and publish events (requires key handling).

## Phase 3: User Interface (HTML/CSS)
- [ ] **Base Template**: Create `templates/base.html` with the standard HTML structure and CSS linking.
- [ ] **Styles**: Create `static/style.css` with a clean, responsive design.
- [x] **Login Page**: Create `templates/login.html` to accept a Public Key (npub) or Private Key (nsec) for the session.
- [ ] **Feed Page**: Create `templates/index.html` to display a list of events (notes) from the relays.
- [ ] **Post Page**: Create `templates/post.html` (or a modal/section) for composing new notes.

## Phase 4: Integration
- [ ] **Connect Feed**: Update the index route to fetch real Nostr events and render them in the template.
- [x] **Connect Login**: Implement session handling (simple cookie or memory) to store the user's keys/identity.
- [ ] **Connect Posting**: Implement the form submission handler to publish a signed event to relays.

## Phase 5: Refinement
- [ ] **Format Content**: Handle timestamps and basic content formatting (e.g., line breaks).
- [ ] **Error Handling**: Add basic error messages for failed connections or invalid keys.
- [ ] **Verification**: Test the full flow (Login -> View Feed -> Post).
