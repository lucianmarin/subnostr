from nostr_sdk import Client, Filter, Kind, Timestamp, Keys, NostrSigner, EventBuilder, RelayUrl
import asyncio
from typing import List
from datetime import timedelta

class NostrManager:
    def __init__(self):
        # Initialize with no signer (read-only)
        self.client = Client(None)
        self.relays = [
            "wss://relay.damus.io",
            "wss://nos.lol",
            "wss://relay.primal.net"
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

    async def get_global_feed(self, limit: int = 20):
        await self.start()
        # Filter for text notes (Kind 1)
        f = Filter().kind(Kind(1)).limit(limit)
        # Fetch events from relays (timeout of 5 seconds)
        # fetch_events takes (filter, timeout) - passing single filter
        events = await self.client.fetch_events(f, timedelta(seconds=5))
        # Sort by created_at descending
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
        
        builder = EventBuilder.text_note(content, [])
        await pub_client.send_event_builder(builder)
        # We might want to keep this client alive if we expect more posts, but for now close it or let it be collected.
        # Ideally we should maintain a persistent authenticated client if the user "logs in".

nostr_manager = NostrManager()
