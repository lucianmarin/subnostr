from nostr_sdk import Client, Filter, Kind, Timestamp, Keys, NostrSigner, EventBuilder, RelayUrl, PublicKey, Tag
import asyncio
import json
from typing import List, Optional, Dict
from datetime import timedelta

class NostrManager:
    def __init__(self):
        # Initialize with no signer (read-only)
        self.client = Client(None)
        self.relays = [
            "wss://relay.damus.io",
            "wss://nos.lol",
            "wss://relay.primal.net",
            "wss://relay.snort.social",
            "wss://relay.current.fyi",
            "wss://relay.nostr.band"
        ]
        self.connected = False

    async def start(self):
        if not self.connected:
            for relay in self.relays:
                await self.client.add_relay(RelayUrl.parse(relay))
            await self.client.connect()
            self.connected = True

    def _event_to_dict(self, event):
        return {
            "id": event.id().to_hex(),
            "content": event.content(),
            "pubkey": event.author().to_hex(),
            "created_at": event.created_at().as_secs(),
            "timestamp": event.created_at().to_human_datetime() 
        }

    async def get_global_feed(self, limit: int = 20, until: Optional[int] = None):
        await self.start()
        # Filter for text notes (Kind 1)
        f = Filter().kind(Kind(1)).limit(limit)
        if until:
            f = f.until(Timestamp.from_secs(until))
            
        events = await self.client.fetch_events(f, timedelta(seconds=5))
        sorted_events = sorted(events.to_vec(), key=lambda x: x.created_at().as_secs(), reverse=True)
        return [self._event_to_dict(e) for e in sorted_events]
    
    async def get_following_list(self, pubkey_hex: str) -> List[str]:
        await self.start()
        try:
            print(f"Fetching contact list for {pubkey_hex}")
            pk = PublicKey.parse(pubkey_hex)

            # Fetch Kind 3 (Contact List) - remove limit to get all and find the latest
            f = Filter().kind(Kind(3)).author(pk)

            events = await self.client.fetch_events(f, timedelta(seconds=10))
            print(f"Found {events.len()} contact list events")

            if events.len() == 0:
                return []

            # Find the most recent contact list event
            latest_event = max(events.to_vec(), key=lambda e: e.created_at().as_secs())

            followed_pubkeys = set()

            # Extract 'p' tags from the latest event
            tags = latest_event.tags().to_vec()
            for tag in tags:
                t = tag.as_vec()
                # Check for "p" tag
                if len(t) >= 2 and t[0] == "p":
                    followed_pubkeys.add(t[1])

            print(f"Found {len(followed_pubkeys)} unique followed users")
            return list(followed_pubkeys)
        except Exception as e:
            print(f"Error fetching contact list: {e}")
            return []

    async def get_feed(self, authors: List[str], limit: int = 20, until: Optional[int] = None):
        await self.start()
        if not authors:
            return []
            
        # Limit authors to avoid filter too large errors
        # Many relays reject filters with more than a few hundred authors
        authors = authors[:250]

        public_keys = []
        for author in authors:
            try:
                public_keys.append(PublicKey.parse(author))
            except:
                continue
                
        if not public_keys:
            return []

        f = Filter().kind(Kind(1)).authors(public_keys).limit(limit)
        
        if until:
            f = f.until(Timestamp.from_secs(until))

        events = await self.client.fetch_events(f, timedelta(seconds=5))
        sorted_events = sorted(events.to_vec(), key=lambda x: x.created_at().as_secs(), reverse=True)
        return [self._event_to_dict(e) for e in sorted_events]

    async def publish_note(self, content: str, keys: Keys):
        # Create a new client with the signer for this operation
        # or we can try to use a ClientBuilder if available, but creating a Client is cheap enough if we reuse connection?
        # Actually, creating a new Client means new connection. 
        # Better: create a signer and a temporary client, or just use the existing client if we can attach signer.
        # But Client.signer is likely immutable or hard to change.
        # Let's try creating a separate client for publishing to ensure we have the correct signer.
        
        signer = NostrSigner.keys(keys)
        pub_client = Client(signer)
        for relay in self.relays:
            await pub_client.add_relay(RelayUrl.parse(relay))
        await pub_client.connect()
        
        builder = EventBuilder.text_note(content)
        await pub_client.send_event_builder(builder)
        # We might want to keep this client alive if we expect more posts, but for now close it or let it be collected.
        # Ideally we should maintain a persistent authenticated client if the user "logs in".

    async def get_followers_list(self, pubkey_hex: str) -> List[str]:
        await self.start()
        try:
            print(f"Fetching followers for {pubkey_hex}")
            pk = PublicKey.parse(pubkey_hex)

            # Fetch all Kind 3 events (contact lists)
            f = Filter().kind(Kind(3))

            events = await self.client.fetch_events(f, timedelta(seconds=10))
            print(f"Found {events.len()} contact list events")

            # Group events by author and find the latest for each
            author_events = {}
            for event in events.to_vec():
                author = event.author().to_hex()
                if author not in author_events:
                    author_events[author] = event
                else:
                    if event.created_at().as_secs() > author_events[author].created_at().as_secs():
                        author_events[author] = event

            followers = set()
            for author, event in author_events.items():
                # Check if the latest contact list has the user in p tags
                tags = event.tags().to_vec()
                for tag in tags:
                    t = tag.as_vec()
                    if len(t) >= 2 and t[0] == "p" and t[1] == pk.to_hex():
                        followers.add(author)
                        break

            print(f"Found {len(followers)} current followers")
            return list(followers)
        except Exception as e:
            print(f"Error fetching followers list: {e}")
            return []

    async def get_profiles(self, pubkeys: List[str]) -> Dict[str, dict]:
        await self.start()
        if not pubkeys:
            return {}

        # Limit to avoid huge filters
        pubkeys = pubkeys[:250]
        
        pks = []
        for pk in pubkeys:
            try:
                pks.append(PublicKey.parse(pk))
            except:
                continue
                
        if not pks:
            return {}

        # Kind 0 is Metadata
        f = Filter().kind(Kind(0)).authors(pks)
        
        # We don't need history, just latest, but relays might send multiples.
        # We can handle deduping in python.
        events = await self.client.fetch_events(f, timedelta(seconds=5))
        
        profiles = {}
        # Sort by created_at ascending so we overwrite with newer data
        sorted_events = sorted(events.to_vec(), key=lambda x: x.created_at().as_secs())
        
        for event in sorted_events:
            try:
                content = json.loads(event.content())
                profiles[event.author().to_hex()] = content
            except:
                continue
                
        return profiles

nostr_manager = NostrManager()
