"""
mover.py
copy discord messages into another channel via webhook

there is no true move
this copies
keeps author name/avatar
leaves the source alone until an explicit keep/archive/delete step after a full copy

forum modes:
  starter (default): one art post = thread starter + caption/link
  whole_thread: every message in the thread (library-of-x style posts)

link/embed art: discord often shows images via embeds (fiverr urls etc)
not file uploads
we pull embed image urls into the body so they survive
"""

from __future__ import annotations

import asyncio
import io
import json
import os
from dataclasses import dataclass, field
from pathlib import Path

import discord  # type: ignore


def split_content(text, limit=2000):
    """split a message body into chunks under the limit
    prefers newline breaks
    returns [] for empty text
    so a caption-less image just posts the file"""
    if not text:
        return []
    if len(text) <= limit:
        return [text]
    chunks, rest = [], text
    while len(rest) > limit:
        cut = rest.rfind("\n", 0, limit)
        if cut <= 0:
            cut = limit
        chunks.append(rest[:cut])
        rest = rest[cut:].lstrip("\n")
    if rest:
        chunks.append(rest)
    return chunks


def normalize_name(s):
    return " ".join((s or "").lower().split())


def name_matches(thread_name, targets):
    if not targets:
        return True
    n = normalize_name(thread_name)
    return any(n == normalize_name(t) or normalize_name(t) in n for t in targets)


def embed_image_urls(message):
    urls = []
    for e in getattr(message, "embeds", None) or []:
        for obj in (getattr(e, "image", None), getattr(e, "thumbnail", None)):
            u = getattr(obj, "url", None)
            if u:
                urls.append(u)
    return urls


def new_embed_urls(image_urls, content):
    """embed image urls that arent already in the message text"""
    c = content or ""
    out = []
    for u in image_urls:
        if u and u not in c and u not in out:
            out.append(u)
    return out


def build_body(content, jump_url, append_link, extra_urls=None, oversized_links=None, limit=2000):
    """caption + embed image urls + oversized att links + optional source link"""
    pieces = []
    if content:
        pieces.append(content)
    for u in (extra_urls or []):
        pieces.append(u)
    for u in (oversized_links or []):
        pieces.append(u)
    if append_link and jump_url:
        pieces.append(f"↳ from: {jump_url}")
    return split_content("\n".join(pieces), limit)


def has_media(message):
    return bool(message.attachments) or bool(getattr(message, "embeds", None))


def is_worth_moving(message):
    return bool((message.content or "").strip()) or has_media(message)


class JobLog:
    """tracks which source message ids have already been copied"""

    def __init__(self):
        self.moved = {}

    def done(self, source_id):
        return str(source_id) in self.moved

    def mark(self, source_id, new_ids):
        self.moved[str(source_id)] = [str(n) for n in new_ids]

    def to_json(self):
        return json.dumps({"moved": self.moved})

    @classmethod
    def from_json(cls, s):
        j = cls()
        j.moved = (json.loads(s) or {}).get("moved", {})
        return j

    def save(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.to_json(), encoding="utf-8")

    @classmethod
    def load(cls, path: Path):
        if not path.is_file():
            return cls()
        try:
            return cls.from_json(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return cls()


@dataclass
class MoverConfig:
    source_id: int
    target_id: int
    preserve_author: bool = True
    include_thread_titles: bool = True
    # false = starter only
    # true = every message in the forum thread
    include_replies: bool = False
    # only these forum thread ids (preferred over name filters)
    thread_ids: list = field(default_factory=list)
    # only forum threads whose names match (substring / exact ignore case)
    thread_filters: list = field(default_factory=list)
    append_source_link: bool = True
    age_restrict_target: bool = False
    source_after: str = "keep"
    delay_seconds: float = 2.0

    def validate(self):
        errs = []
        if self.source_id == self.target_id:
            errs.append("source and target must differ.")
        if self.source_after not in ("keep", "archive", "delete"):
            errs.append("source_after must be keep, archive, or delete.")
        return errs


def joblog_path(source_id, target_id) -> Path:
    base = os.environ.get("APPDATA") or os.path.expanduser("~/.config")
    return Path(base) / "LazyCatter" / "move-jobs" / f"{source_id}_{target_id}.json"


async def iter_source_units(guild, source, cfg: MoverConfig):
    """
    yield units oldest first
    each unit is one message to copy (flattened)
    forum / text with threads: thread_ids wins if set else thread_filters else all
    plain text with no thread pick: channel history
    """
    id_set = {str(i) for i in (cfg.thread_ids or [])}
    use_threads = isinstance(source, discord.ForumChannel) or (
        isinstance(source, discord.TextChannel) and (id_set or cfg.thread_filters)
    )
    if use_threads:
        for t in await _collect_threads(source):
            if id_set:
                if str(t.id) not in id_set:
                    continue
            elif cfg.thread_filters and not name_matches(t.name, cfg.thread_filters):
                continue
            msgs = [m async for m in t.history(limit=None, oldest_first=True)]
            if not msgs:
                continue
            unit_msgs = msgs if cfg.include_replies else msgs[:1]
            for m in unit_msgs:
                if not is_worth_moving(m):
                    continue
                yield {"title": t.name, "messages": [m], "jump": m.jump_url}
        return

    async for m in source.history(limit=None, oldest_first=True):
        if not is_worth_moving(m):
            continue
        yield {"title": None, "messages": [m], "jump": m.jump_url}


async def _collect_threads(channel, archived_limit=200):
    """active threads plus a capped archived list
    avoids hanging forever"""
    threads = list(getattr(channel, "threads", []) or [])
    seen = {t.id for t in threads}
    try:
        async for t in channel.archived_threads(limit=archived_limit):
            if t.id in seen:
                continue
            seen.add(t.id)
            threads.append(t)
    except (discord.Forbidden, AttributeError, discord.HTTPException):
        pass
    threads.sort(key=lambda t: t.created_at or discord.utils.utcnow())
    return threads


async def list_forum_threads(channel):
    """active + archived posts/threads under a forum or text channel
    oldest first"""
    out = []
    for t in await _collect_threads(channel):
        out.append({
            "id": str(t.id),
            "name": t.name,
            "archived": bool(getattr(t, "archived", False)),
            "created_at": t.created_at.isoformat() if t.created_at else None,
        })
    return out


def list_move_channels(guild):
    """text / announcement / forum channels the mover can use"""
    rows = []
    for ch in guild.channels:
        try:
            if isinstance(ch, discord.CategoryChannel):
                continue
            if isinstance(ch, discord.ForumChannel):
                kind = "forum"
            elif isinstance(ch, discord.TextChannel):
                try:
                    kind = "announcement" if ch.is_news() else "text"
                except Exception:
                    kind = "text"
            else:
                continue
            cat = ch.category
            rows.append({
                "id": str(ch.id),
                "name": ch.name,
                "type": kind,
                "category": cat.name if cat else None,
                "nsfw": bool(getattr(ch, "nsfw", False)),
                "position": ch.position,
                "category_position": cat.position if cat else -1,
            })
        except Exception:
            continue
    rows.sort(key=lambda r: (r["category_position"], r["position"], r["name"].lower()))
    return rows


async def ensure_webhook(target):
    hooks = await target.webhooks()
    for h in hooks:
        if h.name == "lazycatter-mover":
            return h
    return await target.create_webhook(name="lazycatter-mover", reason="LazyCatter content mover")


async def _files_from(message, filesize_limit):
    files, skipped, link_bits = [], [], []
    for att in (message.attachments or []):
        if att.size and filesize_limit and att.size > filesize_limit:
            skipped.append(f"{att.filename} ({att.size} bytes) too large for re-upload")
            link_bits.append(att.url)
            continue
        try:
            data = await att.read()
            files.append(discord.File(
                io.BytesIO(data),
                filename=att.filename,
                spoiler=att.is_spoiler(),
            ))
        except Exception as e:
            skipped.append(f"{att.filename} failed: {e}")
            if att.url:
                link_bits.append(att.url)
    return files, skipped, link_bits


async def _webhook_send(webhook, *, content=None, files=None, **author_kw):
    """discord.py treats files=None as an explicit empty iterable and blows up
    so only pass files when we actually have some"""
    kwargs = dict(author_kw)
    kwargs["wait"] = True
    if content:
        kwargs["content"] = content
    if files:
        kwargs["files"] = files
    return await webhook.send(**kwargs)


async def repost_unit(webhook, unit, cfg: MoverConfig):
    new_ids, notes = [], []
    m = unit["messages"][0]
    header = f"**{unit['title']}**" if (cfg.include_thread_titles and unit.get("title")) else None

    author_kw = {}
    if cfg.preserve_author and m.author is not None:
        author_kw = {
            "username": (m.author.display_name or m.author.name or "unknown")[:80],
            "avatar_url": getattr(getattr(m.author, "display_avatar", None), "url", None),
        }
        # drop null avatar so discord.py doesnt get a weird kw
        if not author_kw.get("avatar_url"):
            author_kw.pop("avatar_url", None)
    limit = getattr(webhook.guild, "filesize_limit", None) if webhook.guild else None
    files, skipped, oversized_links = await _files_from(m, limit)
    notes += skipped

    extra = new_embed_urls(embed_image_urls(m), m.content)
    body_parts = build_body(
        m.content,
        unit.get("jump") or m.jump_url,
        cfg.append_source_link,
        extra_urls=extra,
        oversized_links=oversized_links,
    )
    if header:
        if body_parts:
            body_parts[0] = header + "\n" + body_parts[0]
        else:
            body_parts = [header]

    if not body_parts and not files:
        notes.append(f"skipped empty message {m.id}")
        return new_ids, notes

    if not body_parts and files:
        msg = await _webhook_send(webhook, files=files, **author_kw)
        new_ids.append(msg.id)
    else:
        for j, part in enumerate(body_parts):
            send_files = files if j == len(body_parts) - 1 else None
            msg = await _webhook_send(
                webhook,
                content=part,
                files=send_files,
                **author_kw,
            )
            new_ids.append(msg.id)
    return new_ids, notes


async def dry_run(guild, cfg: MoverConfig):
    source = guild.get_channel(cfg.source_id)
    target = guild.get_channel(cfg.target_id)
    if source is None or target is None:
        return {"error": "source or target channel not found."}
    units = 0
    messages = 0
    oversized = []
    matched_threads = []
    embeds = 0
    limit = getattr(guild, "filesize_limit", None)
    async for unit in iter_source_units(guild, source, cfg):
        units += 1
        messages += 1
        if unit.get("title") and unit["title"] not in matched_threads:
            matched_threads.append(unit["title"])
        for m in unit["messages"]:
            if embed_image_urls(m):
                embeds += 1
            for att in (m.attachments or []):
                if att.size and limit and att.size > limit:
                    oversized.append(att.filename)
    mode = "whole thread" if cfg.include_replies else "starters only"
    if cfg.thread_ids:
        filt = f"{len(cfg.thread_ids)} selected post(s)"
    elif cfg.thread_filters:
        filt = ", ".join(cfg.thread_filters)
    else:
        filt = "(all threads in source)"
    note = (
        f"copy only. source untouched unless you pick archive/delete after. "
        f"forum mode: {mode}. selection: {filt}. "
        f"embed/link images are pulled into the body so fiverr-style art still shows."
    )
    return {
        "source": source.name,
        "target": target.name,
        "units": units,
        "messages": messages,
        "oversized": oversized,
        "embeds_with_images": embeds,
        "matched_threads": matched_threads,
        "include_replies": cfg.include_replies,
        "thread_ids": [str(i) for i in (cfg.thread_ids or [])],
        "thread_filters": cfg.thread_filters,
        "target_nsfw": bool(getattr(target, "nsfw", False)),
        "note": note,
    }


async def run_move(guild, cfg: MoverConfig, joblog: JobLog, should_cancel, on_progress):
    source = guild.get_channel(cfg.source_id)
    target = guild.get_channel(cfg.target_id)
    if source is None or target is None:
        raise RuntimeError("source or target channel not found.")

    notes = []
    if cfg.age_restrict_target and hasattr(target, "nsfw") and not target.nsfw:
        try:
            await target.edit(nsfw=True, reason="LazyCatter content mover")
            notes.append(f"set #{target.name} age-restricted (18+)")
        except Exception as e:
            notes.append(f"could not set age-restriction: {e}")

    webhook = await ensure_webhook(target)

    units = [u async for u in iter_source_units(guild, source, cfg)]
    total = len(units)
    done = 0

    for unit in units:
        if should_cancel():
            break
        anchor = unit["messages"][0].id if unit["messages"] else None
        if anchor and joblog.done(anchor):
            done += 1
            on_progress(done, total, "skip (already copied)")
            continue
        try:
            new_ids, unit_notes = await repost_unit(webhook, unit, cfg)
            if anchor:
                joblog.mark(anchor, new_ids)
                joblog.save(joblog_path(cfg.source_id, cfg.target_id))
            notes += unit_notes
            on_progress(done + 1, total, "ok")
        except Exception as e:
            on_progress(done + 1, total, f"error: {e}")
            notes.append(str(e))
        done += 1
        if done < total and not should_cancel():
            await asyncio.sleep(cfg.delay_seconds)

    if not should_cancel() and done >= total and cfg.source_after != "keep":
        await _retire_source(guild, source, cfg.source_after)
    return {"done": done, "total": total, "notes": notes}


async def _retire_source(guild, source, mode):
    if mode == "archive":
        cat = discord.utils.get(guild.categories, name="ARCHIVE") or \
            await guild.create_category("ARCHIVE")
        ow = source.overwrites_for(guild.default_role)
        ow.send_messages = False
        ow.add_reactions = False
        await source.edit(category=cat)
        await source.set_permissions(guild.default_role, overwrite=ow)
    elif mode == "delete":
        await source.delete(reason="content moved by LazyCatter, confirmed by operator")
