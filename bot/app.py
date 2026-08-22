#!/usr/bin/env python3
"""
lazycatter
local control plane

a local web app bound to 127.0.0.1 that drives a private bot on demand
connect
upload a plan
look at the diff
run it slowly
kill it whenever you want

the bot has no inbound listener
it only reaches out to discord while a session is open
then disconnects when you stop it

    pip install -r requirements.txt
    export LAZYCATTER_UI_TOKEN="pick-any-local-secret"   # gates the local ui
    python app.py                                     # open http://127.0.0.1:8787

give the bot only Manage Channels + Manage Roles
kick it when youre done

three sections in here
  1. engine    load/validate plan snapshot diff build_actions apply_one
  2. executor  paced cancellable logged run of the diff
  3. server    fastapi endpoints and the static ui holding one session in memory
"""

import asyncio
import os
import re
import sys
import unicodedata
from datetime import datetime, timezone

from version import COPYRIGHT, DEVELOPER_GITHUB, PUBLISHER, VERSION

try:
    from roles import (
        apply_role_one,
        apply_role_reorders,
        build_role_actions,
        describe_role_action,
        preflight_role_check,
    )
except ImportError:
    from bot.roles import (  # type: ignore
        apply_role_one,
        apply_role_reorders,
        build_role_actions,
        describe_role_action,
        preflight_role_check,
    )

try:
    from mover import (
        JobLog,
        MoverConfig,
        dry_run as move_dry_run,
        joblog_path,
        list_forum_threads,
        list_move_channels,
        run_move,
    )
except ImportError:
    from bot.mover import (  # type: ignore
        JobLog,
        MoverConfig,
        dry_run as move_dry_run,
        joblog_path,
        list_forum_threads,
        list_move_channels,
        run_move,
    )

try:
    import discord
    import yaml
    from fastapi import FastAPI, Header, HTTPException, Request
    from fastapi.responses import HTMLResponse, JSONResponse
    import uvicorn
except ImportError:
    sys.exit("Missing deps. Run: pip install -r requirements.txt")

def _bundle_root():
    """repo root normally
    pyinstaller extract dir when frozen"""
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return sys._MEIPASS
    return os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def _bot_dir():
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return os.path.join(sys._MEIPASS, "bot")
    return os.path.dirname(os.path.abspath(__file__))


# reuse the exact validator the skill ships
# so bot and agent agree on whats valid
sys.path.insert(0, os.path.join(_bundle_root(), "skill", "lazycatter", "scripts"))
try:
    from validate_plan import validate as validate_plan  # type: ignore
except Exception:
    def validate_plan(plan):  # fallback minimal check
        if not isinstance(plan, dict) or "categories" not in plan:
            return ["Plan must be a mapping with 'categories'."]
        return []


# ===========================================================================
# 1. engine
# ===========================================================================

VALID_TYPES = {"text", "voice", "forum", "stage", "announcement"}


def channel_type_name(ch):
    if isinstance(ch, discord.TextChannel):
        return "announcement" if ch.is_news() else "text"
    if isinstance(ch, discord.VoiceChannel):
        return "voice"
    if isinstance(ch, discord.StageChannel):
        return "stage"
    if isinstance(ch, discord.ForumChannel):
        return "forum"
    return "unknown"


def snapshot(guild):
    """dump guild structure to plain data
    this is what export json used to be
    still handy for agents"""
    def describe(ch):
        return {"id": str(ch.id), "name": ch.name, "type": channel_type_name(ch),
                "position": ch.position, "topic": getattr(ch, "topic", None)}
    data = {"captured_at": datetime.now(timezone.utc).isoformat(),
            "guild": {"id": str(guild.id), "name": guild.name}, "categories": []}
    for cat in sorted(guild.categories, key=lambda c: c.position):
        data["categories"].append({
            "id": str(cat.id),
            "name": cat.name,
            "channels": [describe(c) for c in sorted(cat.channels, key=lambda c: c.position)],
        })
    uncategorized = [
        describe(c) for c in sorted(guild.channels, key=lambda c: c.position)
        if not isinstance(c, discord.CategoryChannel) and c.category is None
    ]
    if uncategorized:
        data["uncategorized"] = uncategorized
    return data


def guild_to_plan(guild, mode="restore"):
    """turn the live guild into an importable plan.yaml

    restore = match by snowflake ids
    undo on the SAME server
    template = match null everywhere
    recreate the look on another server
    """
    mode = (mode or "restore").strip().lower()
    if mode not in ("restore", "template"):
        raise ValueError("mode must be 'restore' or 'template'")

    plan = {
        "server_name": guild.name,
        "source_guild_id": str(guild.id),
        "plan_kind": mode,
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "archive_category": "ARCHIVE",
        "archive": [],
        "categories": [],
    }

    for cat in sorted(guild.categories, key=lambda c: c.position):
        cat_spec = {"name": cat.name, "channels": []}
        if mode == "restore":
            cat_spec["match"] = str(cat.id)
        # template: leave match off
        # so a missing name creates the category on the target
        for ch in sorted(cat.channels, key=lambda c: c.position):
            ctype = channel_type_name(ch)
            if ctype == "unknown":
                continue
            entry = {
                "match": str(ch.id) if mode == "restore" else None,
                "name": ch.name,
                "type": ctype,
            }
            topic = getattr(ch, "topic", None)
            if topic:
                entry["topic"] = topic
            cat_spec["channels"].append(entry)
        plan["categories"].append(cat_spec)

    # uncategorized channels
    # template only
    # dump them in a GENERAL bucket you can edit
    # restore skips them
    # so we dont force a category move
    if mode == "template":
        uncategorized = [
            c for c in sorted(guild.channels, key=lambda c: c.position)
            if not isinstance(c, discord.CategoryChannel) and c.category is None
            and channel_type_name(c) != "unknown"
        ]
        if uncategorized:
            bucket = {"name": "GENERAL", "channels": []}
            for ch in uncategorized:
                entry = {
                    "match": None,
                    "name": ch.name,
                    "type": channel_type_name(ch),
                }
                topic = getattr(ch, "topic", None)
                if topic:
                    entry["topic"] = topic
                bucket["channels"].append(entry)
            plan["categories"].insert(0, bucket)

    return plan


def plan_to_yaml(plan):
    header = (
        f"# lazycatter plan ({plan.get('plan_kind', 'custom')})\n"
        f"# server: {plan.get('server_name', '')}\n"
        f"# source_guild_id: {plan.get('source_guild_id', '')}\n"
        f"# captured_at: {plan.get('captured_at', '')}\n"
        "#\n"
    )
    if plan.get("plan_kind") == "restore":
        header += (
            "# restore plan\n"
            "# match values are channel/category ids\n"
            "# re-upload on the SAME server to undo renames/moves in place\n"
            "# dont use this on a different server\n"
            "# those ids wont exist there\n"
            "#\n"
        )
    elif plan.get("plan_kind") == "template":
        header += (
            "# template plan\n"
            "# every match is null (create layout)\n"
            "# connect to the TARGET server\n"
            "# upload preview then APPLY\n"
            "# existing same-named channels may get reused instead of duplicated\n"
            "#\n"
        )
    body = yaml.safe_dump(
        plan,
        sort_keys=False,
        allow_unicode=True,
        default_flow_style=False,
        width=100,
    )
    return header + body


def _normalize_key(name):
    """smash decorated discord names down to a comparable core key

    '♛﹒roundtable-hold' and 'roundtable-hold' both become 'roundtable-hold'
    '[ℍ𝕀𝔻𝔼]. haligtree⌟' and '[HIDE]. haligtree ⌐' both become 'hidehaligtree'
    nfkc folds mathematical / fullwidth letters first
    then we keep letters numbers hyphen and underscore only
    """
    if name is None:
        return ""
    s = unicodedata.normalize("NFKC", str(name)).lower()
    out = []
    for ch in s:
        cat = unicodedata.category(ch)
        if cat.startswith("L") or cat.startswith("N") or ch in "-_":
            out.append(ch)
    return re.sub(r"[-_]+", "-", "".join(out)).strip("-_")


def _index(guild):
    by_id, by_name, by_norm = {}, {}, {}
    for ch in guild.channels:
        if isinstance(ch, discord.CategoryChannel):
            continue
        by_id[str(ch.id)] = ch
        by_name.setdefault(ch.name.lower(), ch)
        key = _normalize_key(ch.name)
        if key:
            by_norm.setdefault(key, []).append(ch)
    return by_id, by_name, by_norm


def _resolve(match, by_id, by_name, by_norm=None):
    """find a channel by id
    exact name
    or normalised decorative name"""
    if match is None:
        return None, None
    match = str(match)
    hit = by_id.get(match) or by_name.get(match.lower())
    if hit is not None:
        return hit, "exact"
    if by_norm is None:
        return None, None
    key = _normalize_key(match)
    if not key:
        return None, None
    candidates = by_norm.get(key) or []
    # prefer unique hits
    # caller filters claimed
    if len(candidates) == 1:
        return candidates[0], "normalized"
    if len(candidates) > 1:
        return None, "ambiguous"
    return None, None


def _resolve_unclaimed(match, by_id, by_name, by_norm, claimed):
    """resolve match
    skip channels already claimed by earlier plan rows"""
    if match is None:
        return None, None
    match = str(match)
    hit = by_id.get(match) or by_name.get(match.lower())
    if hit is not None:
        if str(hit.id) in claimed:
            return None, "claimed"
        return hit, "exact"

    key = _normalize_key(match)
    if not key:
        return None, None
    candidates = [c for c in (by_norm.get(key) or []) if str(c.id) not in claimed]
    if len(candidates) == 1:
        return candidates[0], "normalized"
    if len(candidates) > 1:
        return None, "ambiguous"
    return None, None


def _find_by_target(name, ctype, by_norm, claimed, guild):
    """before creating
    check if an unclaimed channel is already this target"""
    key = _normalize_key(name)
    if not key:
        return None
    for ch in guild.channels:
        if isinstance(ch, discord.CategoryChannel):
            continue
        if str(ch.id) in claimed:
            continue
        if channel_type_name(ch) != ctype:
            continue
        if _normalize_key(ch.name) == key:
            return ch
    return None


def build_actions(guild, plan):
    """diff the live guild against the plan
    hands back actions and warnings
    doesnt touch anything itself"""
    actions, warnings = [], []
    by_id, by_name, by_norm = _index(guild)
    claimed = set()
    existing_cats = {c.name.lower(): c for c in guild.categories}
    existing_cats_norm = {}
    for c in guild.categories:
        existing_cats_norm.setdefault(_normalize_key(c.name), []).append(c)

    def resolve_category(m, fallback_name):
        if m:
            cat = existing_cats.get(str(m).lower()) or \
                next((c for c in guild.categories if str(c.id) == str(m)), None)
            if cat is None:
                key = _normalize_key(m)
                opts = [c for c in (existing_cats_norm.get(key) or [])]
                if len(opts) == 1:
                    return opts[0], "normalized"
                if len(opts) > 1:
                    return None, "ambiguous"
                return None, None
            return cat, "exact"
        if fallback_name:
            cat = existing_cats.get(fallback_name.lower())
            if cat:
                return cat, "exact"
            key = _normalize_key(fallback_name)
            opts = existing_cats_norm.get(key) or []
            if len(opts) == 1:
                return opts[0], "normalized"
        return None, None

    for ci, cat_spec in enumerate(plan["categories"]):
        cat_name = cat_spec["name"]
        m = cat_spec.get("match")
        cat_obj, how = resolve_category(m, None if m else cat_name)

        if m and cat_obj is None and how == "ambiguous":
            warnings.append(
                f"Category match {m!r} is ambiguous after ignoring decorations, "
                f"fix match to the exact name or category ID."
            )
        elif m and cat_obj is None:
            warnings.append(
                f"Category match {m!r} not found, will not create a duplicate. "
                f"Fix match (exact name/ID) or omit match to create {cat_name!r}."
            )

        if cat_obj is None and not m:
            # new category
            # match was null/missing
            # and name not found
            actions.append({"kind": "create_category", "name": cat_name, "position": ci})
        elif cat_obj is None and m:
            # match was set but failed
            # dont create a category shell
            # channels under it might still resolve via normalised channel match
            pass
        else:
            if how == "normalized":
                warnings.append(
                    f"Category {m or cat_name!r} matched existing {cat_obj.name!r} "
                    f"by ignoring decorations."
                )
            if cat_obj.name != cat_name:
                actions.append({"kind": "rename_category", "id": str(cat_obj.id),
                                "from": cat_obj.name, "to": cat_name})
            if cat_obj.position != ci:
                actions.append({"kind": "move_category", "id": str(cat_obj.id),
                                "name": cat_name, "position": ci})

        for chi, ch in enumerate(cat_spec.get("channels", []) or []):
            target, ctype = ch["name"], ch.get("type", "text")
            topic = ch.get("topic")
            match_val = ch.get("match")
            existing, how = _resolve_unclaimed(match_val, by_id, by_name, by_norm, claimed)

            if how == "ambiguous":
                warnings.append(
                    f"Match {match_val!r} is ambiguous after ignoring decorations, "
                    f"skipped {target!r}. Use the exact name or channel ID."
                )
                continue

            if existing is None and match_val is not None:
                # match was set but nothing resolved
                # never create
                warnings.append(
                    f"No channel matched {match_val!r}, skipped {target!r} "
                    f"(will not create a duplicate). Use Export for exact names/IDs, "
                    f"or set match: null only for a genuinely new channel."
                )
                continue

            if existing is None and match_val is None:
                # real create request
                # still avoid double ups if target already exists
                existing = _find_by_target(target, ctype, by_norm, claimed, guild)
                if existing is not None:
                    warnings.append(
                        f"match was null but found existing #{existing.name} for "
                        f"{target!r}, editing in place instead of creating."
                    )
                    how = "normalized"

            if existing is None:
                actions.append({"kind": "create_channel", "name": target, "type": ctype,
                                "topic": topic, "category": cat_name, "position": chi})
                continue

            if how == "normalized":
                warnings.append(
                    f"Channel match {match_val!r} resolved to #{existing.name} "
                    f"by ignoring decorations."
                )

            claimed.add(str(existing.id))
            cur = channel_type_name(existing)
            if cur != ctype:
                warnings.append(f"#{existing.name} is {cur}, plan says {ctype}. "
                                f"Discord can't convert types, skipping type change.")
            changes = {}
            if existing.name != target:
                changes["name"] = target
            if topic is not None and getattr(existing, "topic", None) != topic:
                changes["topic"] = topic
            if cat_obj is None:
                if existing.category is None or existing.category.name != cat_name:
                    warnings.append(
                        f"#{existing.name} matched but category {cat_name!r} was not "
                        f"resolved, leaving its category unchanged."
                    )
            else:
                same_cat = existing.category is cat_obj
                if not same_cat:
                    changes["category"] = cat_name
            if existing.position != chi:
                changes["position"] = chi
            if changes:
                actions.append({"kind": "edit_channel", "id": str(existing.id),
                                "from": existing.name, "changes": changes,
                                "category": cat_name, "position": chi})

    for name in (plan.get("archive") or []):
        ch, how = _resolve_unclaimed(name, by_id, by_name, by_norm, claimed)
        if how == "ambiguous":
            warnings.append(f"Archive target {name!r} is ambiguous, skipped.")
        elif ch is None:
            warnings.append(f"Archive target {name!r} not found.")
        else:
            claimed.add(str(ch.id))
            actions.append({"kind": "archive_channel", "id": str(ch.id), "name": ch.name})

    untouched = [c.name for c in guild.channels
                 if not isinstance(c, discord.CategoryChannel) and str(c.id) not in claimed]
    if untouched:
        warnings.append("Left untouched (not in plan): " + ", ".join("#" + n for n in untouched))

    role_actions, role_warnings = build_role_actions(guild, plan)
    actions.extend(role_actions)
    warnings.extend(role_warnings)
    if guild.me is not None:
        warnings.extend(preflight_role_check(guild, guild.me))
    return actions, warnings


def describe_action(a):
    k = a["kind"]
    if k in ("create_role", "edit_role", "reorder_role"):
        return describe_role_action(a)
    if k == "create_category":  return f"CREATE   category  {a['name']}"
    if k == "rename_category":  return f"RENAME   category  {a['from']} -> {a['to']}"
    if k == "move_category":    return f"MOVE     category  {a['name']} -> pos {a['position']}"
    if k == "create_channel":   return f"CREATE   {a['type']:<9} #{a['name']}  in [{a['category']}]"
    if k == "archive_channel":  return f"ARCHIVE  channel   #{a['name']}  (locked, history kept)"
    if k == "edit_channel":
        c = a["changes"]; bits = []
        if "name" in c:     bits.append(f"name -> #{c['name']}")
        if "category" in c: bits.append(f"category -> [{c['category']}]")
        if "topic" in c:    bits.append("topic updated")
        if "position" in c: bits.append(f"pos -> {c['position']}")
        return f"EDIT     channel   #{a['from']}: " + ", ".join(bits)
    return str(a)


async def apply_one(guild, a):
    """run one action against the live guild
    idempotent on purpose so re running is safe"""
    if a["kind"] in ("create_role", "edit_role"):
        await apply_role_one(guild, a)
        return
    if a["kind"] == "reorder_role":
        # final batch pass after paced create/edit
        return

    async def get_cat(name):
        cat = discord.utils.get(guild.categories, name=name)
        return cat or await guild.create_category(name)

    k = a["kind"]
    if k == "create_category":
        await guild.create_category(a["name"], position=a["position"])
    elif k == "rename_category":
        c = guild.get_channel(int(a["id"]))
        if c: await c.edit(name=a["to"])
    elif k == "move_category":
        c = guild.get_channel(int(a["id"]))
        if c: await c.edit(position=a["position"])
    elif k == "create_channel":
        cat = await get_cat(a["category"])
        t = a["type"]
        if t == "voice":
            await guild.create_voice_channel(a["name"], category=cat)
        elif t == "stage":
            await guild.create_stage_channel(a["name"], category=cat)
        elif t == "forum":
            await guild.create_forum(a["name"], category=cat, topic=a.get("topic") or None)
        else:
            ch = await guild.create_text_channel(a["name"], category=cat,
                                                 topic=a.get("topic") or None)
            if t == "announcement":
                try: await ch.edit(news=True)
                except discord.HTTPException: pass
    elif k == "edit_channel":
        c = guild.get_channel(int(a["id"]))
        if not c: return
        kw, ch = {}, a["changes"]
        if "name" in ch: kw["name"] = ch["name"]
        if "topic" in ch and hasattr(c, "topic"): kw["topic"] = ch["topic"]
        if "category" in ch: kw["category"] = await get_cat(ch["category"])
        if "position" in ch: kw["position"] = ch["position"]
        await c.edit(**kw)
    elif k == "archive_channel":
        c = guild.get_channel(int(a["id"]))
        if not c: return
        cat = await get_cat("ARCHIVE")
        ow = c.overwrites_for(guild.default_role)
        ow.send_messages = False
        ow.add_reactions = False
        await c.edit(category=cat)
        await c.set_permissions(guild.default_role, overwrite=ow)


# ===========================================================================
# 2. executor   paced cancellable logged
# ===========================================================================

class PacedExecutor:
    """
    runs the actions one at a time
    waits a bit between each
    checks the cancel flag before every one

    the engine is diff based
    so if you kill it mid run and start again
    it just finishes whats left
    nothing ends up half broken
    """
    def __init__(self, apply_fn, delay_seconds=3.0):
        self.apply_fn = apply_fn
        self.delay = max(0.0, float(delay_seconds))
        self.cancel = asyncio.Event()
        self.log = []
        self.done = 0
        self.total = 0
        self.running = False

    def request_cancel(self):
        self.cancel.set()

    def _record(self, status, action, detail=""):
        self.log.append({
            "at": datetime.now(timezone.utc).isoformat(),
            "status": status, "action": describe_action(action), "detail": detail,
        })

    async def run(self, actions):
        self.running = True
        self.total = len(actions)
        self.done = 0
        try:
            for a in actions:
                if self.cancel.is_set():
                    self._record("cancelled", a, "stopped before this action")
                    break
                try:
                    await self.apply_fn(a)
                    self._record("ok", a)
                except Exception as e:
                    self._record("error", a, f"{type(e).__name__}: {e}")
                    # keep going
                    # one failed rename shouldnt kill the whole run
                self.done += 1
                if self.done < self.total and not self.cancel.is_set():
                    # cancellable sleep
                    # wakes up straight away if cancel fires
                    try:
                        await asyncio.wait_for(self.cancel.wait(), timeout=self.delay)
                    except asyncio.TimeoutError:
                        pass
        finally:
            self.running = False
        return self.log

    @staticmethod
    def spacing_for_duration(n_actions, total_seconds):
        """delay per action to spread n actions across the time you asked for"""
        if n_actions <= 1:
            return 0.0
        return max(0.0, float(total_seconds) / (n_actions - 1))


# ===========================================================================
# 3. server   local control plane
# ===========================================================================

class Session:
    def __init__(self):
        self.client = None
        self.guild = None
        self.task = None          # discord client task
        self.ready = asyncio.Event()
        self.connect_error = None
        self.plan = None
        self.actions = None
        self.warnings = None
        self.executor = None
        self.status = "disconnected"
        # content mover
        # separate job from plan execute
        self.move_running = False
        self.move_cancel = asyncio.Event()
        self.move_done = 0
        self.move_total = 0
        self.move_notes = []
        self.move_task = None

    def reset_plan(self):
        self.plan = self.actions = self.warnings = None


S = Session()
UI_TOKEN = os.environ.get("LAZYCATTER_UI_TOKEN", "")
DESKTOP_MODE = os.environ.get("LAZYCATTER_DESKTOP", "").strip() in ("1", "true", "yes")
app = FastAPI(title="LazyCatter", version=VERSION)


def _auth(token):
    # simple gate
    # so no other local process can drive your bot
    if UI_TOKEN and token != UI_TOKEN:
        raise HTTPException(status_code=401, detail="Bad or missing UI token.")


def _client_is_loopback(request: Request) -> bool:
    host = (request.client.host if request.client else "") or ""
    return host in ("127.0.0.1", "::1", "localhost")


async def _drop_client():
    """close any discord session and clear session state
    used after failed connects so the next connect isnt stuck on already connected"""
    client = S.client
    task = S.task
    S.client = None
    S.guild = None
    S.task = None
    S.status = "disconnected"
    S.connect_error = None
    S.ready = asyncio.Event()
    if client is not None and not client.is_closed():
        try:
            await client.close()
        except Exception:
            pass
    if task is not None and not task.done():
        task.cancel()
        try:
            await task
        except (asyncio.CancelledError, Exception):
            pass


async def _start_client(bot_token, guild_id):
    intents = discord.Intents.default()
    intents.guilds = True
    # needed to read historical message text/attachments
    # for the content mover
    intents.message_content = True
    client = discord.Client(intents=intents)
    S.client = client
    S.ready = asyncio.Event()
    S.connect_error = None

    @client.event
    async def on_ready():
        g = client.get_guild(int(guild_id))
        if g is None:
            try:
                g = await client.fetch_guild(int(guild_id))
                await g.fetch_channels()
            except Exception as e:
                S.connect_error = f"guild lookup failed: {e}"
                g = None
        S.guild = g
        S.status = "connected" if g else "connected-no-guild"
        S.ready.set()

    async def _run():
        try:
            await client.start(bot_token)
        except discord.LoginFailure:
            S.connect_error = "Login failed — bad bot token."
            S.ready.set()
        except Exception as e:
            S.connect_error = f"Discord client died: {e}"
            S.ready.set()

    S.task = asyncio.create_task(_run())
    try:
        await asyncio.wait_for(S.ready.wait(), timeout=30)
    except asyncio.TimeoutError:
        await _drop_client()
        raise HTTPException(
            status_code=504,
            detail="Bot did not become ready (check token / invite / internet).",
        )

    if S.connect_error and S.guild is None:
        err = S.connect_error
        await _drop_client()
        raise HTTPException(status_code=401, detail=err)


@app.post("/api/connect")
async def connect(req: Request, x_ui_token: str = Header(default="")):
    _auth(x_ui_token)
    body = await req.json()
    bot_token = body.get("bot_token", "").strip()
    guild_id = str(body.get("guild_id", "")).strip()
    if not bot_token or not guild_id:
        raise HTTPException(status_code=400, detail="bot_token and guild_id required.")
    try:
        int(guild_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="guild_id must be a numeric server ID.")

    # half-failed sessions leave an open client
    # clear them instead of 409
    if S.client is not None:
        if (
            not S.client.is_closed()
            and S.guild is not None
            and S.status == "connected"
        ):
            raise HTTPException(
                status_code=409,
                detail="Already connected. Disconnect first.",
            )
        await _drop_client()

    # token handling
    # bot_token is a local variable and thats it
    # it goes straight into the discord client
    # never copied onto the session S
    # never written to disk or config
    # never logged
    #
    # while its connected the discord.py client keeps it in memory
    # to hold the gateway open
    # cant get around that for any live connection
    #
    # on disconnect or kill the client closes and gets dropped
    # and the token is gone from the process
    # theres nothing left to reuse
    # you just type it in again next session
    try:
        await _start_client(bot_token, guild_id)
    except HTTPException:
        raise
    except Exception as e:
        await _drop_client()
        raise HTTPException(status_code=502, detail=f"Connect blew up: {e}")
    finally:
        del bot_token  # drop our reference right away
        # only the client still has it (if connect worked)

    if not S.guild:
        await _drop_client()
        raise HTTPException(
            status_code=404,
            detail="Bot connected but is not in that guild. Invite it, then try again.",
        )
    # warm channel cache so the move picker has something to show
    channel_count = 0
    try:
        await S.guild.fetch_channels()
        channel_count = len(S.guild.channels)
    except Exception:
        channel_count = len(getattr(S.guild, "channels", []) or [])
    return {
        "status": S.status,
        "guild": S.guild.name,
        "channel_count": channel_count,
    }


@app.post("/api/disconnect")
async def disconnect(x_ui_token: str = Header(default="")):
    """graceful stop
    cancel any run
    close the discord session
    forget the token"""
    _auth(x_ui_token)
    if S.executor and S.executor.running:
        S.executor.request_cancel()
    await _drop_client()
    return {"status": "disconnected"}


@app.post("/api/kill")
async def kill(x_ui_token: str = Header(default="")):
    """kill switch
    stop the running execution and drop the connection right now"""
    _auth(x_ui_token)
    if S.executor and S.executor.running:
        S.executor.request_cancel()
    if S.move_running:
        S.move_cancel.set()
    await _drop_client()
    S.status = "killed"
    return {"status": "killed", "message": "Execution cancelled and bot disconnected."}


@app.get("/api/export")
async def export(x_ui_token: str = Header(default="")):
    _auth(x_ui_token)
    if not S.guild:
        raise HTTPException(status_code=409, detail="Not connected.")
    return JSONResponse(snapshot(S.guild))


@app.get("/api/export-plan")
async def export_plan(mode: str = "restore", x_ui_token: str = Header(default="")):
    """save the connected server as an importable plan.yaml

    restore = id matches for undo on the same guild
    template = create style plan
    cloning the look onto another guild
    """
    _auth(x_ui_token)
    if not S.guild:
        raise HTTPException(status_code=409, detail="Not connected.")
    try:
        plan = guild_to_plan(S.guild, mode=mode)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    errors = validate_plan(plan)
    if errors:
        raise HTTPException(status_code=500, detail={"invalid": errors})
    text = plan_to_yaml(plan)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    kind = plan.get("plan_kind", mode)
    gid = plan.get("source_guild_id", "guild")
    filename = f"lazycatter-{kind}-{gid}-{stamp}.yaml"

    # also drop a copy under appdata/plans and downloads
    saved_to = None
    downloaded_to = None
    try:
        base = os.environ.get("APPDATA") or os.path.expanduser("~/.config")
        out_dir = os.path.join(base, "LazyCatter", "plans")
        os.makedirs(out_dir, exist_ok=True)
        saved_to = os.path.join(out_dir, filename)
        with open(saved_to, "w", encoding="utf-8") as fh:
            fh.write(text)
    except OSError:
        saved_to = None

    try:
        home = os.path.expanduser("~")
        downloads = os.path.join(home, "Downloads")
        if not os.path.isdir(downloads):
            downloads = home
        downloaded_to = os.path.join(downloads, filename)
        with open(downloaded_to, "w", encoding="utf-8") as fh:
            fh.write(text)
    except OSError:
        downloaded_to = None

    return {
        "ok": True,
        "mode": kind,
        "filename": filename,
        "saved_to": saved_to,
        "downloaded_to": downloaded_to,
        "guild_id": gid,
        "guild_name": plan.get("server_name"),
        "categories": len(plan.get("categories", [])),
        "yaml": text,
    }


@app.post("/api/plan")
async def upload_plan(req: Request, x_ui_token: str = Header(default="")):
    """importer
    take a YAML plan
    validate it
    store it"""
    _auth(x_ui_token)
    raw = (await req.body()).decode("utf-8")
    try:
        plan = yaml.safe_load(raw)
    except yaml.YAMLError as e:
        raise HTTPException(status_code=400, detail=f"YAML error: {e}")
    errors = validate_plan(plan)
    if errors:
        raise HTTPException(status_code=422, detail={"invalid": errors})
    S.plan = plan
    S.actions = S.warnings = None
    return {"ok": True, "server_name": plan.get("server_name"),
            "categories": len(plan.get("categories", []))}


@app.get("/api/diff")
async def diff(x_ui_token: str = Header(default="")):
    """work out the diff between the stored plan and the live server"""
    _auth(x_ui_token)
    if not S.guild:
        raise HTTPException(status_code=409, detail="Not connected.")
    if not S.plan:
        raise HTTPException(status_code=409, detail="No plan uploaded.")
    actions, warnings = build_actions(S.guild, S.plan)
    S.actions, S.warnings = actions, warnings
    return {"actions": [describe_action(a) for a in actions],
            "warnings": warnings, "count": len(actions)}


@app.post("/api/execute")
async def execute(req: Request, x_ui_token: str = Header(default="")):
    """run the diff paced out
    body needs confirm: "APPLY" plus either delay or duration_seconds
    nothing touches discord until that confirm phrase is present"""
    _auth(x_ui_token)
    if not S.guild:
        raise HTTPException(status_code=409, detail="Not connected.")
    if S.executor and S.executor.running:
        raise HTTPException(status_code=409, detail="Already executing.")
    if not S.plan:
        raise HTTPException(status_code=409, detail="No plan uploaded.")
    try:
        body = await req.json()
    except Exception:
        body = {}
    if not isinstance(body, dict):
        body = {}
    if body.get("confirm") != "APPLY":
        raise HTTPException(
            status_code=400,
            detail='Explicit confirmation required. Send {"confirm":"APPLY", ...}.',
        )
    if S.actions is None:
        actions, warnings = build_actions(S.guild, S.plan)
        S.actions, S.warnings = actions, warnings
    if not S.actions:
        return {"ok": True, "message": "Nothing to do, server already matches plan."}

    if "duration_seconds" in body:
        delay = PacedExecutor.spacing_for_duration(len(S.actions), body["duration_seconds"])
    else:
        delay = float(body.get("delay", 3.0))

    all_actions = list(S.actions)
    paced = [a for a in all_actions if a.get("kind") != "reorder_role"]
    reorders = [a for a in all_actions if a.get("kind") == "reorder_role"]

    S.executor = PacedExecutor(lambda a: apply_one(S.guild, a), delay_seconds=delay)

    async def _run_with_role_reorder():
        await S.executor.run(paced)
        if reorders and not S.executor.cancel.is_set() and S.guild is not None:
            try:
                await apply_role_reorders(S.guild, reorders)
                for a in reorders:
                    S.executor._record("ok", a, "batch reorder")
            except Exception as e:
                for a in reorders:
                    S.executor._record("error", a, f"{type(e).__name__}: {e}")

    asyncio.create_task(_run_with_role_reorder())
    return {"ok": True, "total": len(all_actions), "delay": delay}


@app.post("/api/cancel")
async def cancel(x_ui_token: str = Header(default="")):
    """graceful stop of the run only
    stays connected so you can pick it back up"""
    _auth(x_ui_token)
    if S.executor and S.executor.running:
        S.executor.request_cancel()
        return {"ok": True, "message": "Cancelling after current action."}
    return {"ok": True, "message": "Nothing running."}


@app.get("/api/status")
async def status(x_ui_token: str = Header(default="")):
    _auth(x_ui_token)
    ex = S.executor
    return {
        "status": S.status,
        "guild": S.guild.name if S.guild else None,
        "running": bool(ex and ex.running),
        "progress": {"done": ex.done, "total": ex.total} if ex else None,
        "log": ex.log[-50:] if ex else [],
        "move_running": S.move_running,
        "move_progress": {"done": S.move_done, "total": S.move_total} if S.move_total else None,
    }


def _parse_id_list(raw):
    if raw is None or raw == "":
        return []
    if isinstance(raw, str):
        parts = [x.strip() for x in raw.split(",") if x.strip()]
    elif isinstance(raw, list):
        parts = [str(x).strip() for x in raw if str(x).strip()]
    else:
        return []
    out = []
    for p in parts:
        try:
            out.append(int(p))
        except (TypeError, ValueError):
            raise ValueError(f"bad id in list: {p!r}")
    return out


def _mover_config_from_body(body):
    """build MoverConfig from a json body
    raises ValueError on bad ids"""
    if not isinstance(body, dict):
        body = {}
    filters = body.get("thread_filters") or []
    if isinstance(filters, str):
        filters = [x.strip() for x in filters.split(",") if x.strip()]
    elif not isinstance(filters, list):
        filters = []
    else:
        filters = [str(x).strip() for x in filters if str(x).strip()]
    thread_ids = _parse_id_list(body.get("thread_ids"))
    try:
        source_id = int(str(body.get("source_id", "")).strip())
        target_id = int(str(body.get("target_id", "")).strip())
    except (TypeError, ValueError):
        raise ValueError("source_id and target_id must be channel snowflakes.")
    return MoverConfig(
        source_id=source_id,
        target_id=target_id,
        include_replies=bool(body.get("include_replies", False)),
        thread_ids=thread_ids,
        thread_filters=filters,
        append_source_link=bool(body.get("append_source_link", True)),
        age_restrict_target=bool(body.get("age_restrict_target", False)),
        source_after=str(body.get("source_after", "keep")),
        delay_seconds=float(body.get("delay", 2.0)),
        include_thread_titles=bool(body.get("include_thread_titles", True)),
    )


@app.get("/api/move/catalog")
async def move_catalog(x_ui_token: str = Header(default="")):
    """channels you can pick as source/target after connect"""
    _auth(x_ui_token)
    if not S.guild:
        raise HTTPException(status_code=409, detail="Not connected.")
    try:
        # refresh so newly created channels show up
        await S.guild.fetch_channels()
    except Exception as e:
        # fall back to whatever is already cached
        if not getattr(S.guild, "channels", None):
            raise HTTPException(
                status_code=502,
                detail=f"Could not load channels from Discord: {e}",
            )
    channels = list_move_channels(S.guild)
    return {
        "guild": S.guild.name,
        "channels": channels,
        "count": len(channels),
    }


@app.get("/api/move/threads")
async def move_threads(source_id: str = "", x_ui_token: str = Header(default="")):
    """forum posts or text-channel threads under a source channel"""
    _auth(x_ui_token)
    if not S.guild:
        raise HTTPException(status_code=409, detail="Not connected.")
    try:
        sid = int(str(source_id).strip())
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="source_id required.")
    ch = S.guild.get_channel(sid)
    if ch is None:
        raise HTTPException(status_code=404, detail="source channel not found.")
    if isinstance(ch, discord.ForumChannel):
        threads = await list_forum_threads(ch)
        return {"source_id": str(sid), "source_type": "forum", "threads": threads}
    if isinstance(ch, discord.TextChannel):
        threads = await list_forum_threads(ch)  # same active+archived walk
        return {"source_id": str(sid), "source_type": "text", "threads": threads}
    raise HTTPException(status_code=400, detail="pick a text or forum channel.")


@app.post("/api/move/dryrun")
async def move_dryrun(req: Request, x_ui_token: str = Header(default="")):
    _auth(x_ui_token)
    if not S.guild:
        raise HTTPException(status_code=409, detail="Not connected.")
    body = await req.json()
    try:
        cfg = _mover_config_from_body(body)
    except (TypeError, ValueError) as e:
        raise HTTPException(status_code=400, detail=str(e) or "bad move request")
    errs = cfg.validate()
    if errs:
        raise HTTPException(status_code=400, detail="; ".join(errs))
    result = await move_dry_run(S.guild, cfg)
    if result.get("error"):
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@app.post("/api/move/start")
async def move_start(req: Request, x_ui_token: str = Header(default="")):
    _auth(x_ui_token)
    if not S.guild:
        raise HTTPException(status_code=409, detail="Not connected.")
    if S.move_running:
        raise HTTPException(status_code=409, detail="A content move is already running.")
    if S.executor and S.executor.running:
        raise HTTPException(status_code=409, detail="Plan execute is running. Wait or cancel it first.")
    body = await req.json()
    after = str(body.get("source_after", "keep"))
    if after == "delete" and body.get("confirm_delete") != "DELETE":
        raise HTTPException(
            status_code=400,
            detail='Delete requires confirm_delete: "DELETE" after the UI confirm dialog.',
        )
    try:
        cfg = _mover_config_from_body(body)
    except (TypeError, ValueError) as e:
        raise HTTPException(status_code=400, detail=str(e) or "bad move request")
    errs = cfg.validate()
    if errs:
        raise HTTPException(status_code=400, detail="; ".join(errs))

    joblog = JobLog.load(joblog_path(cfg.source_id, cfg.target_id))
    S.move_cancel = asyncio.Event()
    S.move_running = True
    S.move_done = 0
    S.move_total = 0
    S.move_notes = []

    def on_progress(done, total, note):
        S.move_done = done
        S.move_total = total
        S.move_notes.append(f"{done}/{total} {note}")

    async def _job():
        try:
            result = await run_move(
                S.guild,
                cfg,
                joblog,
                should_cancel=lambda: S.move_cancel.is_set(),
                on_progress=on_progress,
            )
            S.move_notes.extend(result.get("notes") or [])
            S.move_notes.append(
                f"finished {result.get('done')}/{result.get('total')} "
                f"(source_after={cfg.source_after})"
            )
        except Exception as e:
            S.move_notes.append(f"error: {type(e).__name__}: {e}")
        finally:
            S.move_running = False

    S.move_task = asyncio.create_task(_job())
    mode = "whole thread" if cfg.include_replies else "starters only"
    return {
        "ok": True,
        "message": f"Copy started ({mode}). Embed/link images are included.",
        "source_after": cfg.source_after,
    }


@app.post("/api/move/cancel")
async def move_cancel(x_ui_token: str = Header(default="")):
    _auth(x_ui_token)
    if S.move_running:
        S.move_cancel.set()
        return {"ok": True, "message": "Cancelling after the current item."}
    return {"ok": True, "message": "Nothing running."}


@app.get("/api/move/status")
async def move_status(x_ui_token: str = Header(default="")):
    _auth(x_ui_token)
    return {
        "running": S.move_running,
        "progress": {"done": S.move_done, "total": S.move_total},
        "notes": S.move_notes[-40:],
    }


@app.get("/api/version")
async def version_info():
    return {
        "name": "LazyCatter",
        "version": VERSION,
        "publisher": PUBLISHER,
        "copyright": COPYRIGHT,
        "developer": DEVELOPER_GITHUB,
        "issues": f"https://github.com/{DEVELOPER_GITHUB}/LazyCatter/issues",
    }


@app.get("/api/desktop-bootstrap")
async def desktop_bootstrap(request: Request):
    """desktop app only
    hand the ui token to the window on loopback
    never returns the token outside desktop mode or off localhost"""
    if not DESKTOP_MODE or not _client_is_loopback(request):
        return {"desktop": False, "version": VERSION, "publisher": PUBLISHER}
    return {
        "desktop": True,
        "ui_token": UI_TOKEN,
        "version": VERSION,
        "publisher": PUBLISHER,
    }


@app.get("/", response_class=HTMLResponse)
async def index():
    path = os.path.join(_bot_dir(), "ui.html")
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def run_server(host=None, port=None, on_error=None):
    """serve the fastapi app
    safe to call from a background thread

    pyinstaller windowed builds leave stdout/stderr as None which blows up
    uvicorns colourised logging (isatty)
    so we kill that logging and drive
    Server.serve() on an explicit event loop
    """
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w", encoding="utf-8")
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w", encoding="utf-8")

    if not UI_TOKEN:
        print("WARNING: LAZYCATTER_UI_TOKEN not set, the local UI is ungated.")
    host = host or os.environ.get("HOST", "127.0.0.1")
    port = int(port or os.environ.get("PORT", "8787"))
    try:
        config = uvicorn.Config(
            app,
            host=host,
            port=port,
            log_level="warning",
            access_log=False,
            log_config=None,
            lifespan="on",
            http="h11",
        )
        server = uvicorn.Server(config)
        # non-main threads cant install signal handlers on windows
        server.install_signal_handlers = False

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(server.serve())
        finally:
            try:
                loop.run_until_complete(loop.shutdown_asyncgens())
            except Exception:
                pass
            loop.close()
    except Exception as exc:
        if on_error is not None:
            try:
                on_error(exc)
            except Exception:
                pass
        raise


if __name__ == "__main__":
    run_server()
