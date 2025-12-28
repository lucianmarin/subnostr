from nostr_sdk import Client, Filter, Kind, Timestamp, Keys, NostrSigner, EventBuilder, RelayUrl, PublicKey, Tag, EventId
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
            "wss://nostr.wine",
            "wss://relay.snort.social"
        ]
        self.connected = False
        self._profiles_cache = {}

    async def start(self):
        if not self.connected:
            for relay in self.relays:
                await self.client.add_relay(RelayUrl.parse(relay))
            await self.client.connect()
            self.connected = True

    def _event_to_dict(self, event):
        tags = []
        for tag in event.tags().to_vec():
            tags.append(tag.as_vec())

        return {
            "id": event.id().to_hex(),
            "content": event.content(),
            "pubkey": event.author().to_hex(),
            "created_at": event.created_at().as_secs(),
            "timestamp": event.created_at().to_human_datetime(),
            "tags": tags
        }

    async def _enrich_events(self, events_vec):
        sorted_events = sorted(events_vec, key=lambda x: x.created_at().as_secs(), reverse=True)

        # Enrich with profiles
        pubkeys = list(set([e.author().to_hex() for e in sorted_events]))
        profiles = await self.get_profiles(pubkeys)

        results = []
        for e in sorted_events:
            data = self._event_to_dict(e)
            author_pk = data["pubkey"]
            if author_pk in profiles:
                p = profiles[author_pk]
                data["author_name"] = p.get("display_name") or p.get("name")
                data["author_picture"] = p.get("picture")
            results.append(data)
        return results

    async def _enrich_with_reply_counts(self, results):
        if not results:
            return results

        event_ids = []
        for r in results:
            try:
                event_ids.append(EventId.parse(r["id"]))
            except:
                continue

        if not event_ids:
            return results

        # Fetch all Kind 1 events tagging these IDs
        f = Filter().kind(Kind(1)).events(event_ids)
        reply_events = await self.client.fetch_events(f, timedelta(seconds=5))

        # Count replies for each ID
        counts = {r["id"]: 0 for r in results}
        for e in reply_events.to_vec():
            # Check 'e' tags to see which event is being replied to
            for tag in e.tags().to_vec():
                t = tag.as_vec()
                if len(t) >= 2 and t[0] == "e":
                    target_id = t[1]
                    if target_id in counts:
                        counts[target_id] += 1
                        break # Count only once per event

        for r in results:
            r["reply_count"] = counts.get(r["id"], 0)

        return results

    async def get_global_feed(self, limit: int = 20, until: Optional[int] = None):
        await self.start()
        # Filter for text notes (Kind 1)
        f = Filter().kind(Kind(1)).limit(limit)
        if until:
            f = f.until(Timestamp.from_secs(until))

        events = await self.client.fetch_events(f, timedelta(seconds=5))
        enriched = await self._enrich_events(events.to_vec())
        return await self._enrich_with_reply_counts(enriched)

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

            # Build a map of followed pubkey -> most recent event timestamp where it appears
            followed_map = {}  # pubkey -> latest_created_at_secs
            for event in events.to_vec():
                ts = event.created_at().as_secs()
                for tag in event.tags().to_vec():
                    t = tag.as_vec()
                    if len(t) >= 2 and t[0] == "p":
                        pk = t[1]
                        # Keep the most recent timestamp for this followed pubkey
                        if pk not in followed_map or ts > followed_map[pk]:
                            followed_map[pk] = ts

            # Return followed pubkeys sorted by the most recent time they appeared (desc)
            sorted_followed = sorted(followed_map.items(), key=lambda x: x[1])
            followed_pubkeys = [pk for pk, _ in sorted_followed]

            print(f"Found {len(followed_pubkeys)} unique followed users")
            return followed_pubkeys
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

        # Filter out replies (events with 'e' tags)
        filtered_events = []
        for event in events.to_vec():
            has_e_tag = False
            for tag in event.tags().to_vec():
                t = tag.as_vec()
                if len(t) >= 1 and t[0] == "e":
                    has_e_tag = True
                    break
            if not has_e_tag:
                filtered_events.append(event)

        enriched = await self._enrich_events(filtered_events)
        return await self._enrich_with_reply_counts(enriched)

    async def get_events(self, event_ids: List[str]) -> Dict[str, dict]:
        await self.start()
        if not event_ids:
            return {}

        event_ids = list(set(event_ids))
        ids = []
        for eid in event_ids:
            try:
                ids.append(EventId.parse(eid))
            except:
                continue

        if not ids:
            return {}

        f = Filter().ids(ids)
        events = await self.client.fetch_events(f, timedelta(seconds=5))

        results = {}
        for e in events.to_vec():
            results[e.id().to_hex()] = self._event_to_dict(e)

        return results

    async def get_replies_feed(self, authors: List[str], limit: int = 20, until: Optional[int] = None):
        await self.start()
        if not authors:
            return []

        authors = authors[:250]
        public_keys = []
        for author in authors:
            try:
                public_keys.append(PublicKey.parse(author))
            except:
                continue

        if not public_keys:
            return []

        # Fetch more to account for filtering
        fetch_limit = limit * 4
        f = Filter().kind(Kind(1)).authors(public_keys).limit(fetch_limit)

        if until:
            f = f.until(Timestamp.from_secs(until))

        events = await self.client.fetch_events(f, timedelta(seconds=5))

        # Filter for replies (has 'e' tag)
        reply_events = []
        for event in events.to_vec():
            is_reply = False
            for tag in event.tags().to_vec():
                t = tag.as_vec()
                if len(t) >= 1 and t[0] == "e":
                    is_reply = True
                    break
            if is_reply:
                reply_events.append(event)

        # Enrich and return only the requested limit
        enriched = await self._enrich_events(reply_events)
        results = enriched[:limit]
        with_parents = await self._enrich_with_parents(results)
        return await self._enrich_with_reply_counts(with_parents)

    async def _enrich_with_parents(self, results):
        if not results:
            return results

        # Fetch parents
        parent_ids_map = {} # note_id -> parent_id
        all_parent_ids = set()

        for note in results:
            parent_id = None
            e_tags = [t for t in note.get('tags', []) if t[0] == 'e']

            # NIP-10 logic: prefer 'reply' marker, else last 'e' tag
            found_marker = False
            for t in e_tags:
                if len(t) >= 4 and t[3] == 'reply':
                    parent_id = t[1]
                    found_marker = True
                    break

            if not found_marker and e_tags:
                parent_id = e_tags[-1][1]

            if parent_id:
                parent_ids_map[note['id']] = parent_id
                all_parent_ids.add(parent_id)

        if all_parent_ids:
            parents = await self.get_events(list(all_parent_ids))

            # Fetch parent authors profiles
            parent_pubkeys = set()
            for p in parents.values():
                parent_pubkeys.add(p['pubkey'])

            if parent_pubkeys:
                parent_profiles = await self.get_profiles(list(parent_pubkeys))

                # Enrich parents with profiles
                for pid, p_data in parents.items():
                    p_pk = p_data['pubkey']
                    if p_pk in parent_profiles:
                        prof = parent_profiles[p_pk]
                        p_data["author_name"] = prof.get("display_name") or prof.get("name")
                        p_data["author_picture"] = prof.get("picture")

            # Attach to results
            for note in results:
                pid = parent_ids_map.get(note['id'])
                if pid and pid in parents:
                    note['parent_post'] = parents[pid]

        return results

    async def get_user_posts(self, pubkey_hex: str, limit: int = 20, until: Optional[int] = None):
        await self.start()
        try:
            pk = PublicKey.parse(pubkey_hex)
            f = Filter().kind(Kind(1)).author(pk).limit(limit)
            if until:
                f = f.until(Timestamp.from_secs(until))

            events = await self.client.fetch_events(f, timedelta(seconds=5))
            enriched = await self._enrich_events(events.to_vec())
            with_parents = await self._enrich_with_parents(enriched)
            return await self._enrich_with_reply_counts(with_parents)
        except Exception as e:
            print(f"Error fetching user posts: {e}")
            return []

    async def get_post_with_replies(self, event_id_hex: str):
        await self.start()
        # Fetch the main post
        main_events_dict = await self.get_events([event_id_hex])
        if not main_events_dict:
            return None, []

        main_post = main_events_dict[event_id_hex]

        # Enrich main post author
        profiles_to_fetch = [main_post["pubkey"]]

        # Find root ID to fetch the whole thread if possible
        root_id = event_id_hex
        e_tags = [t for t in main_post.get('tags', []) if t[0] == 'e']
        for t in e_tags:
            if len(t) >= 4 and t[3] == 'root':
                root_id = t[1]
                break
        if root_id == event_id_hex and e_tags:
            root_id = e_tags[0][1]

        # Fetch replies and potentially other thread participants
        try:
            eid = EventId.parse(event_id_hex)
            rid = EventId.parse(root_id)

            # Fetch events tagging either this post or the root
            f = Filter().kind(Kind(1)).events([eid, rid]).limit(500)
            thread_events_vec = await self.client.fetch_events(f, timedelta(seconds=5))
            thread_events = thread_events_vec.to_vec()

            # Enrich all authors
            for e in thread_events:
                profiles_to_fetch.append(e.author().to_hex())

            profiles = await self.get_profiles(list(set(profiles_to_fetch)))

            def enrich(data):
                pk = data["pubkey"]
                if pk in profiles:
                    prof = profiles[pk]
                    data["author_name"] = prof.get("display_name") or prof.get("name")
                    data["author_picture"] = prof.get("picture")
                data["replies"] = []
                return data

            enrich(main_post)
            await self._enrich_with_parents([main_post])

            # Convert all thread events to dicts and enrich
            nodes = {main_post["id"]: main_post}
            for e in thread_events:
                d = self._event_to_dict(e)
                if d["id"] not in nodes:
                    nodes[d["id"]] = enrich(d)

            # Build tree
            for node_id, node in nodes.items():
                if node_id == event_id_hex:
                    continue

                # Find parent
                parent_id = None
                node_e_tags = [t for t in node.get('tags', []) if t[0] == 'e']

                # NIP-10: prefer 'reply' marker
                for t in node_e_tags:
                    if len(t) >= 4 and t[3] == 'reply':
                        parent_id = t[1]
                        break

                if not parent_id and node_e_tags:
                    # Fallback: if only one e tag, it's the root/parent.
                    # If multiple, the last one is the reply.
                    parent_id = node_e_tags[-1][1]

                if parent_id in nodes:
                    nodes[parent_id]["replies"].append(node)

            # Sort replies by time
            for node in nodes.values():
                node["replies"].sort(key=lambda x: x["created_at"])

            # Enrich all collected nodes with reply counts
            all_nodes = list(nodes.values())
            await self._enrich_with_reply_counts(all_nodes)

            return main_post, main_post["replies"]

        except Exception as e:
            print(f"Error building thread tree: {e}")
            # Fallback to basic enrichment if tree building fails
            profiles = await self.get_profiles([main_post["pubkey"]])
            if main_post["pubkey"] in profiles:
                p = profiles[main_post["pubkey"]]
                main_post["author_name"] = p.get("display_name") or p.get("name")
                main_post["author_picture"] = p.get("picture")

            await self._enrich_with_reply_counts([main_post])
            return main_post, []

    async def publish_note(self, content: str, keys: Keys, reply_to_id: Optional[str] = None):
        signer = NostrSigner.keys(keys)
        pub_client = Client(signer)
        for relay in self.relays:
            await pub_client.add_relay(RelayUrl.parse(relay))
        try:
            await pub_client.connect()
        except Exception as e:
            raise Exception(f"Failed to connect to relays: {e}")

        tags = []
        if reply_to_id:
            try:
                parent_id = EventId.parse(reply_to_id)
                # Fetch parent to find root and author
                f = Filter().id(parent_id)
                events = await self.client.fetch_events(f, timedelta(seconds=5))
                if events.len() > 0:
                    parent_event = events.to_vec()[0]
                    parent_tags = parent_event.tags().to_vec()

                    root_id = None
                    for tag in parent_tags:
                        t = tag.as_vec()
                        if len(t) >= 2 and t[0] == "e":
                            # If there's already an 'e' tag, it might be the root
                            # NIP-10: first 'e' tag is root, last is reply
                            if not root_id:
                                root_id = t[1]

                    if root_id:
                        # Add root tag
                        tags.append(Tag.parse(["e", root_id, "", "root"]))
                        # Add reply tag
                        tags.append(Tag.parse(["e", reply_to_id, "", "reply"]))
                    else:
                        # Parent is the root
                        tags.append(Tag.parse(["e", reply_to_id, "", "root"]))

                    # Add 'p' tag for the author we are replying to
                    tags.append(Tag.parse(["p", parent_event.author().to_hex()]))
            except Exception as e:
                print(f"Error preparing reply tags: {e}")

        event = EventBuilder.text_note(content).tags(tags).sign_with_keys(keys)
        try:
            event_id = await pub_client.send_event(event)
            print("Published note")
        except Exception as e:
            await pub_client.disconnect()
            raise Exception(f"Failed to send event: {e}")
        await pub_client.disconnect()

    async def follow(self, keys: Keys, follow_pubkey_hex: str):
        await self.start()
        print(f"Follow request for {follow_pubkey_hex}")
        # 1. Fetch current contact list
        user_pubkey = keys.public_key().to_hex()
        pk = PublicKey.parse(user_pubkey)
        f = Filter().kind(Kind(3)).author(pk)
        events = await self.client.fetch_events(f, timedelta(seconds=10))

        tags = []
        content = ""
        if events.len() > 0:
            latest_event = max(events.to_vec(), key=lambda e: e.created_at().as_secs())
            tags = latest_event.tags().to_vec()
            content = latest_event.content()
            print(f"Found existing contact list with {len(tags)} tags")
        else:
            print("No existing contact list found")

        # Check if already following
        already_following = False
        for tag in tags:
            t = tag.as_vec()
            if len(t) >= 2 and t[0] == "p" and t[1] == follow_pubkey_hex:
                already_following = True
                break

        if not already_following:
            tags.append(Tag.parse(["p", follow_pubkey_hex]))
            print(f"Added p-tag for {follow_pubkey_hex}")

            # Publish updated contact list
            # Publish updated contact list
            signer = NostrSigner.keys(keys)
            pub_client = Client(signer)
            for relay in self.relays:
                await pub_client.add_relay(RelayUrl.parse(relay))
            await pub_client.connect()

            event = EventBuilder(Kind(3), content).tags(tags).sign_with_keys(keys)
            await pub_client.send_event(event)
            print("Published follow event")
            await pub_client.disconnect()
        else:
            print(f"Already following {follow_pubkey_hex} and self is included")

    async def unfollow(self, keys: Keys, unfollow_pubkey_hex: str):
        await self.start()
        print(f"Unfollow request for {unfollow_pubkey_hex}")
        # 1. Fetch current contact list
        user_pubkey = keys.public_key().to_hex()
        pk = PublicKey.parse(user_pubkey)
        f = Filter().kind(Kind(3)).author(pk)
        events = await self.client.fetch_events(f, timedelta(seconds=10))

        if events.len() == 0:
            print("No contact list found to unfollow from")
            return # Nothing to unfollow from

        latest_event = max(events.to_vec(), key=lambda e: e.created_at().as_secs())
        old_tags = latest_event.tags().to_vec()
        content = latest_event.content()
        print(f"Found existing contact list with {len(old_tags)} tags")

        new_tags = []
        found = False
        for tag in old_tags:
            t = tag.as_vec()
            if len(t) >= 2 and t[0] == "p" and t[1] == unfollow_pubkey_hex:
                found = True
                continue
            new_tags.append(tag)

        if found:
            print(f"Removed p-tag for {unfollow_pubkey_hex}")
            # Publish updated contact list
            signer = NostrSigner.keys(keys)
            pub_client = Client(signer)
            for relay in self.relays:
                await pub_client.add_relay(RelayUrl.parse(relay))
            await pub_client.connect()

            event = EventBuilder(Kind(3), content).tags(new_tags).sign_with_keys(keys)
            await pub_client.send_event(event)
            print("Published unfollow event")
            await pub_client.disconnect()
        else:
            print(f"Not following {unfollow_pubkey_hex}")

    async def get_followers_list(self, pubkey_hex: str) -> List[str]:
        await self.start()
        try:
            print(f"Fetching followers for {pubkey_hex}")
            pk = PublicKey.parse(pubkey_hex)

            # Fetch Kind 3 events (contact lists) that tag this user
            f = Filter().kind(Kind(3)).pubkey(pk).limit(500) # Limit to 500 followers for performance

            events = await self.client.fetch_events(f, timedelta(seconds=10))
            print(f"Found {events.len()} potential follower contact list events")

            # Group events by author and find the latest for each
            author_events = {}
            for event in events.to_vec():
                author = event.author().to_hex()
                if author not in author_events:
                    author_events[author] = event
                else:
                    if event.created_at().as_secs() > author_events[author].created_at().as_secs():
                        author_events[author] = event

            # Now we have the latest contact list for each person who followed this user.
            # We still need to verify if that latest list STILL contains the user.
            # (Because relay might have returned an older version if the new one doesn't match the filter)

            followers = []
            for author, event in author_events.items():
                tags = event.tags().to_vec()
                for tag in tags:
                    t = tag.as_vec()
                    if len(t) >= 2 and t[0] == "p" and t[1] == pubkey_hex:
                        # include tuple of (author, timestamp)
                        followers.append((author, event.created_at().as_secs()))
                        break

            # Sort followers by their latest contact-list event time (desc) and return authors only
            followers.sort(key=lambda x: x[1])
            sorted_followers = [a for a, _ in followers]

            print(f"Found {len(sorted_followers)} verified current followers")
            return sorted_followers
        except Exception as e:
            print(f"Error fetching followers list: {e}")
            return []

    async def get_profiles(self, pubkeys: List[str]) -> Dict[str, dict]:
        await self.start()
        if not pubkeys:
            return {}

        results = {}
        missing_pks = []

        for pk in pubkeys:
            if pk in self._profiles_cache:
                results[pk] = self._profiles_cache[pk]
            else:
                missing_pks.append(pk)

        if not missing_pks:
            return results

        # Limit to avoid huge filters
        missing_pks = missing_pks[:250]

        pks = []
        for pk in missing_pks:
            try:
                pks.append(PublicKey.parse(pk))
            except:
                continue

        if not pks:
            return results

        # Kind 0 is Metadata
        f = Filter().kind(Kind(0)).authors(pks)

        # We don't need history, just latest, but relays might send multiples.
        events = await self.client.fetch_events(f, timedelta(seconds=5))

        # Sort by created_at ascending so we overwrite with newer data
        sorted_events = sorted(events.to_vec(), key=lambda x: x.created_at().as_secs())

        for event in sorted_events:
            try:
                author = event.author().to_hex()
                content = json.loads(event.content())
                self._profiles_cache[author] = content
                results[author] = content
            except:
                continue

        return results

nostr_manager = NostrManager()
