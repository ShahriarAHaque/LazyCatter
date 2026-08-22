#!/usr/bin/env python3
"""
move_libraries_to_fanart.py

copy forum posts into another channel via webhook
reposted as the original author
optional source link under each copy
optional age-restrict on the target

link/embed art (urls with embedded images) is pulled into the body
plus any real attachments
not just uploaded files

copy only
the source posts are never touched
dry run is the default

    pip install -U discord.py
    export DISCORD_TOKEN="the bot token"
    export GUILD_ID="server snowflake"
    export SOURCE_FORUM_ID="forum channel snowflake"
    export TARGET_ID="target channel snowflake"
    export POST_NAMES="post one,post two"

    python move_libraries_to_fanart.py             # dry run
    python move_libraries_to_fanart.py --apply     # do it paced

needs: the message content privileged intent on
read message history on the forum
manage webhooks / send messages / attach files on the target
manage channels on the target if you want age-restrict

discord calls are marked VERIFY
run the dry run first and check the matched posts and counts
"""

import argparse
import asyncio
import io
import json
import os
import sys

try:
    import discord
except ImportError:
    sys.exit("Missing dependency. Run: pip install -U discord.py")

WEBHOOK_NAME = "lazycatter-mover"
JOBLOG_PATH = "move-joblog.json"


def _require_snowflake(name):
    raw = (os.environ.get(name) or "").strip()
    if not raw:
        sys.exit(f"Set {name} in your environment.")
    try:
        return int(raw)
    except ValueError:
        sys.exit(f"{name} must be a numeric snowflake.")


def _post_names():
    raw = (os.environ.get("POST_NAMES") or "").strip()
    if not raw:
        sys.exit("Set POST_NAMES to a comma-separated list of forum post names.")
    names = [p.strip() for p in raw.split(",") if p.strip()]
    if not names:
        sys.exit("POST_NAMES was empty after splitting.")
    return names


# ----------------------------- pure helpers (unit-tested) -----------------------------

def normalize(s):
    return " ".join((s or "").lower().split())

def name_matches(thread_name, targets):
    n = normalize(thread_name)
    return any(n == normalize(t) or normalize(t) in n for t in targets)

def split_content(text, limit=2000):
    if not text:
        return []
    if len(text) <= limit:
        return [text]
    chunks, rest = [], text
    while len(rest) > limit:
        cut = rest.rfind("\n", 0, limit)
        if cut <= 0:
            cut = limit
        chunks.append(rest[:cut]); rest = rest[cut:].lstrip("\n")
    if rest:
        chunks.append(rest)
    return chunks

def new_embed_urls(image_urls, content):
    """embed image urls that arent already present in the message text"""
    c = content or ""
    out = []
    for u in image_urls:
        if u and u not in c and u not in out:
            out.append(u)
    return out

def build_body(content, jump_url, append_link, extra_urls=None, limit=2000):
    """full message text: caption + extra image urls + source link
    split to <=limit"""
    pieces = []
    if content:
        pieces.append(content)
    for u in (extra_urls or []):
        pieces.append(u)
    if append_link and jump_url:
        pieces.append(f"\u21b3 from: {jump_url}")
    return split_content("\n".join(pieces), limit)


class JobLog:
    def __init__(self): self.moved = {}
    def done(self, sid): return str(sid) in self.moved
    def mark(self, sid, ids): self.moved[str(sid)] = [str(i) for i in ids]
    def save(self, path):
        with open(path, "w") as f: json.dump({"moved": self.moved}, f)
    @classmethod
    def load(cls, path):
        j = cls()
        try:
            with open(path) as f: j.moved = (json.load(f) or {}).get("moved", {})
        except FileNotFoundError:
            pass
        return j


# ----------------------------- discord i/o (VERIFY) -----------------------------

def embed_image_urls(message):
    urls = []
    for e in message.embeds:
        for obj in (getattr(e, "image", None), getattr(e, "thumbnail", None)):
            u = getattr(obj, "url", None)
            if u: urls.append(u)
    return urls

def has_media(message):
    return bool(message.attachments) or bool(message.embeds)

def is_worth_moving(message):
    """skip only truly empty messages
    no text no files no embeds"""
    return bool((message.content or "").strip()) or has_media(message)

async def collect_posts(forum, post_names):
    threads = list(getattr(forum, "threads", []))
    try:
        async for t in forum.archived_threads(limit=None):    # VERIFY
            threads.append(t)
    except Exception as e:
        print(f"  ! could not list archived posts: {e}")
    matched = [t for t in threads if name_matches(t.name, post_names)]
    matched.sort(key=lambda t: t.created_at)
    return matched

async def files_from(message, filesize_limit):
    files, skipped = [], []
    for att in message.attachments:
        if att.size and filesize_limit and att.size > filesize_limit:
            skipped.append(f"{att.filename} ({att.size}B) too large, its link stays in the body")
            continue
        try:
            data = await att.read()                            # VERIFY
            files.append(discord.File(io.BytesIO(data), filename=att.filename,
                                      spoiler=att.is_spoiler()))
        except Exception as e:
            skipped.append(f"{att.filename} failed: {e}")
    return files, skipped

async def ensure_webhook(target):
    for h in await target.webhooks():                          # VERIFY
        if h.name == WEBHOOK_NAME:
            return h
    return await target.create_webhook(name=WEBHOOK_NAME)


def run(apply, delay, images_only, append_link, set_age):
    guild_id = _require_snowflake("GUILD_ID")
    source_forum_id = _require_snowflake("SOURCE_FORUM_ID")
    target_id = _require_snowflake("TARGET_ID")
    post_names = _post_names()

    intents = discord.Intents.default()
    intents.guilds = True
    intents.message_content = True          # privileged: enable in the portal
    client = discord.Client(intents=intents)

    @client.event
    async def on_ready():
        try:
            guild = client.get_guild(guild_id) or await client.fetch_guild(guild_id)
            forum = guild.get_channel(source_forum_id)
            target = guild.get_channel(target_id)
            if forum is None or target is None:
                print("Could not find the source forum or the target channel."); return
            if not isinstance(forum, discord.ForumChannel):
                print(f"#{forum.name} is not a forum, aborting to be safe."); return

            gated = getattr(target, "nsfw", False)
            print(f"Server : {guild.name}")
            print(f"From   : #{forum.name}  ->  To: #{target.name}")
            print(f"#{target.name} age-restricted: {'yes' if gated else 'NO'}")
            print(f"Mode   : {'APPLY' if apply else 'DRY RUN'}\n")

            posts = await collect_posts(forum, post_names)
            if not posts:
                print("No posts matched", post_names,
                      "\n(check the exact post names in POST_NAMES)"); return
            print("Matched posts:", ", ".join(f'"{t.name}"' for t in posts), "\n")

            # age-restrict the target
            if set_age and not gated:
                if apply:
                    try:
                        await target.edit(nsfw=True)           # VERIFY (needs manage channels)
                        print(f"Set #{target.name} to age-restricted (18+).\n")
                    except Exception as e:
                        print(f"  ! could not set age-restriction: {e}\n")
                else:
                    print(f"Would set #{target.name} to age-restricted (18+).\n")

            joblog = JobLog.load(JOBLOG_PATH)
            limit = getattr(guild, "filesize_limit", None)
            webhook = None
            considered = 0; moved = 0; notes = []

            for t in posts:
                msgs = [m async for m in t.history(limit=None, oldest_first=True)]  # VERIFY
                for m in msgs:
                    if not is_worth_moving(m):
                        continue
                    if images_only and not has_media(m):
                        continue
                    considered += 1
                    kind = []
                    if m.attachments: kind.append(f"{len(m.attachments)} file")
                    if m.embeds:      kind.append(f"{len(m.embeds)} embed")
                    if (m.content or '').strip(): kind.append("text")
                    tag = f'["{t.name}"] {m.author.display_name} ({", ".join(kind) or "empty"})'

                    if not apply:
                        print(f"  would copy  {tag}"); continue
                    if joblog.done(m.id):
                        print(f"  skip (done) {tag}"); continue
                    if webhook is None:
                        webhook = await ensure_webhook(target)

                    files, skipped = await files_from(m, limit); notes += skipped
                    extra = new_embed_urls(embed_image_urls(m), m.content)
                    body = build_body(m.content, m.jump_url, append_link, extra)
                    author = {"username": m.author.display_name}
                    av = getattr(getattr(m.author, "display_avatar", None), "url", None)
                    if av:
                        author["avatar_url"] = av
                    new_ids = []
                    if not body and files:
                        r = await webhook.send(files=files, wait=True, **author); new_ids.append(r.id)
                    else:
                        for k, part in enumerate(body):
                            kwargs = {"content": part or None, "wait": True, **author}
                            if k == len(body) - 1 and files:
                                kwargs["files"] = files
                            r = await webhook.send(**kwargs)  # VERIFY
                            new_ids.append(r.id)
                    joblog.mark(m.id, new_ids); joblog.save(JOBLOG_PATH); moved += 1
                    print(f"  copied      {tag}")
                    await asyncio.sleep(delay)

            print()
            if apply:
                print(f"Done. Copied {moved} message(s). Source posts untouched.")
                if notes:
                    print("Notes:"); [print("  -", n) for n in notes]
                print("\nCheck the target channel. If it's right, archive the source posts by hand "
                      "(don't delete them, or the 'from:' links break).")
            else:
                print(f"Dry run: {considered} message(s) would copy. Re-run with --apply to do it.")
        except discord.Forbidden as e:
            print(f"Permission denied: {e}. Need Read Message History on the forum and "
                  f"Manage Webhooks / Send Messages / Attach Files / Manage Channels on the target.")
        except Exception as e:
            print(f"Stopped: {type(e).__name__}: {e}")
        finally:
            await client.close()

    token = os.environ.get("DISCORD_TOKEN")
    if not token:
        sys.exit("Set DISCORD_TOKEN in your environment.")
    client.run(token, log_handler=None)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Copy forum posts into another channel via webhook.")
    ap.add_argument("--apply", action="store_true", help="actually copy (default is a dry run)")
    ap.add_argument("--delay", type=float, default=2.0, help="seconds between reposts")
    ap.add_argument("--images-only", action="store_true",
                    help="only messages that carry an image/embed (default: everything in the posts)")
    ap.add_argument("--no-link", action="store_true", help="don't append the source link")
    ap.add_argument("--no-age-restrict", action="store_true",
                    help="don't set the target channel to age-restricted")
    a = ap.parse_args()
    run(apply=a.apply, delay=a.delay, images_only=a.images_only,
        append_link=not a.no_link, set_age=not a.no_age_restrict)
