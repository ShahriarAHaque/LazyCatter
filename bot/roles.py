"""
roles.py
role plan diff + apply for lazycatter

mirrors the channel engine
diff live roles against plan roles
return actions
apply one at a time
never deletes a role

match set + not found = skip create
same rule as channels
match null = create
reorder_role actions go in a final pass after creates/edits
"""

from __future__ import annotations

import discord  # type: ignore

PERM_MAP = {
    "administrator": "administrator",
    "manage_guild": "manage_guild",
    "manage_channels": "manage_channels",
    "manage_roles": "manage_roles",
    "manage_messages": "manage_messages",
    "kick_members": "kick_members",
    "ban_members": "ban_members",
    "moderate_members": "moderate_members",
    "move_members": "move_members",
    "mention_everyone": "mention_everyone",
    "manage_webhooks": "manage_webhooks",
    "view_audit_log": "view_audit_log",
    "view_channel": "view_channel",
    "send_messages": "send_messages",
    "embed_links": "embed_links",
    "attach_files": "attach_files",
    "add_reactions": "add_reactions",
    "use_external_emojis": "use_external_emojis",
    "connect": "connect",
    "speak": "speak",
}


def _perms_from_names(names):
    p = discord.Permissions.none()
    unknown = []
    for n in names or []:
        attr = PERM_MAP.get(str(n).strip().lower().replace(" ", "_"))
        if attr is None:
            unknown.append(n)
            continue
        setattr(p, attr, True)
    return p, unknown


def _colour_to_hex(colour):
    if colour is None:
        return None
    if isinstance(colour, discord.Colour):
        return f"#{int(colour.value):06x}"
    s = str(colour).strip()
    if not s:
        return None
    if not s.startswith("#"):
        s = "#" + s
    return s.lower()


def _colour_from_hex(h):
    hx = _colour_to_hex(h)
    if not hx:
        return None
    return discord.Colour(int(hx.lstrip("#"), 16))


def build_role_actions(guild, plan):
    """
    diff live roles vs plan roles
    returns actions and warnings
    pure

    plan role object has name match colour hoist mentionable permissions
    and optional position_above
    """
    actions, warnings = [], []
    roles = plan.get("roles")
    if roles is None:
        return actions, warnings
    if not isinstance(roles, list):
        warnings.append("'roles' must be a list — ignored.")
        return actions, warnings

    by_name = {r.name.lower(): r for r in guild.roles}
    by_id = {str(r.id): r for r in guild.roles}
    claimed = set()
    reorder_specs = []

    for spec in roles:
        if not isinstance(spec, dict):
            warnings.append("a role entry is not a mapping — skipped.")
            continue
        name = spec.get("name")
        if not name:
            warnings.append("a role in the plan has no 'name' — skipped.")
            continue

        m = spec.get("match")
        existing = None
        if m is not None:
            existing = by_id.get(str(m)) or by_name.get(str(m).lower())
            if existing is None:
                warnings.append(
                    f"role match {m!r} not found — skipped {name!r} "
                    f"(will not create a duplicate). Use match: null only for a new role."
                )
                continue
            if existing.managed or existing.is_default():
                warnings.append(
                    f"role {existing.name!r} is managed or @everyone — read only, skipped."
                )
                continue

        perms, unknown = _perms_from_names(spec.get("permissions"))
        for u in unknown:
            warnings.append(f"role {name!r}: unknown permission {u!r} ignored.")
        colour = _colour_from_hex(spec.get("colour"))
        colour_hex = _colour_to_hex(colour)
        above = spec.get("position_above")

        if existing is None:
            # match omitted / null only
            if "match" in spec and m is not None:
                continue
            actions.append({
                "kind": "create_role",
                "name": name,
                "colour": colour_hex,
                "hoist": bool(spec.get("hoist", False)),
                "mentionable": bool(spec.get("mentionable", False)),
                "permissions": perms.value if spec.get("permissions") is not None else None,
                "position_above": above,
            })
            if above:
                reorder_specs.append({"name": name, "above": above, "id": None})
            continue

        claimed.add(existing.id)
        changes = {}
        if existing.name != name:
            changes["name"] = name
        if colour is not None and existing.colour.value != colour.value:
            changes["colour"] = colour_hex
        if "hoist" in spec and existing.hoist != bool(spec["hoist"]):
            changes["hoist"] = bool(spec["hoist"])
        if "mentionable" in spec and existing.mentionable != bool(spec["mentionable"]):
            changes["mentionable"] = bool(spec["mentionable"])
        if spec.get("permissions") is not None and existing.permissions.value != perms.value:
            changes["permissions"] = perms.value
        if changes:
            actions.append({
                "kind": "edit_role",
                "id": str(existing.id),
                "from": existing.name,
                "changes": changes,
                "position_above": above,
            })
        if above:
            reorder_specs.append({"name": name, "above": above, "id": str(existing.id)})

    for rs in reorder_specs:
        actions.append({
            "kind": "reorder_role",
            "name": rs["name"],
            "above": rs["above"],
            "id": rs["id"],
        })

    untouched = [
        r.name for r in guild.roles
        if r.id not in claimed and not r.managed and not r.is_default()
    ]
    if roles and untouched:
        warnings.append("roles left untouched (not in plan): " + ", ".join(untouched))
    return actions, warnings


def describe_role_action(a):
    k = a["kind"]
    if k == "create_role":
        return f"CREATE   role      {a['name']}"
    if k == "edit_role":
        return f"EDIT     role      {a['from']}: " + ", ".join(a["changes"].keys())
    if k == "reorder_role":
        return f"REORDER  role      {a['name']} above {a['above']}"
    return str(a)


def preflight_role_check(guild, me):
    """
    warn about anything the bot physically cannot do before running
    me is guild.me
    a bot cannot edit or reorder any role at or above its top role
    """
    warnings = []
    if me is None:
        warnings.append("bot member not available — cannot preflight role hierarchy.")
        return warnings
    top = me.top_role
    for r in guild.roles:
        if r >= top and not r.is_default():
            warnings.append(
                f"role {r.name!r} sits at/above the bot's top role — "
                f"the bot can't modify or reorder it. Drag the bot's role higher."
            )
    if not me.guild_permissions.manage_roles:
        warnings.append("bot is missing Manage Roles — role actions will fail.")
    if not me.guild_permissions.administrator:
        warnings.append(
            "bot does not have Administrator. Plans that grant administrator "
            "to a role will fail unless the bot has it."
        )
    return warnings


async def apply_role_one(guild, a):
    """execute one role action
    reorder_role is a no-op here
    use apply_role_reorders for that"""
    k = a["kind"]
    if k == "create_role":
        kw = {
            "name": a["name"],
            "hoist": a.get("hoist", False),
            "mentionable": a.get("mentionable", False),
        }
        if a.get("permissions") is not None:
            kw["permissions"] = discord.Permissions(a["permissions"])
        if a.get("colour"):
            kw["colour"] = _colour_from_hex(a["colour"])
        await guild.create_role(**kw, reason="LazyCatter plan")
    elif k == "edit_role":
        role = guild.get_role(int(a["id"]))
        if not role:
            return
        c = a["changes"]
        kw = {}
        if "name" in c:
            kw["name"] = c["name"]
        if "hoist" in c:
            kw["hoist"] = c["hoist"]
        if "mentionable" in c:
            kw["mentionable"] = c["mentionable"]
        if "colour" in c:
            kw["colour"] = _colour_from_hex(c["colour"])
        if "permissions" in c:
            kw["permissions"] = discord.Permissions(c["permissions"])
        if kw:
            await role.edit(**kw, reason="LazyCatter plan")
    elif k == "reorder_role":
        return


async def apply_role_reorders(guild, actions):
    """
    final pass
    apply all reorder_role actions via edit_role_positions
    discord positions: higher number = higher in the list
    above means this role should sit immediately above that role
    """
    reorders = [a for a in actions if a.get("kind") == "reorder_role"]
    if not reorders:
        return

    by_name = {r.name.lower(): r for r in guild.roles}
    by_id = {str(r.id): r for r in guild.roles}
    positions = {}

    for a in reorders:
        role = None
        if a.get("id"):
            role = by_id.get(str(a["id"]))
        if role is None:
            role = by_name.get(str(a["name"]).lower())
        above_key = a.get("above")
        above = by_id.get(str(above_key)) or by_name.get(str(above_key).lower())
        if role is None or above is None:
            continue
        # sit just above `above`
        # position = above.position + 1
        # then discord renumbers
        positions[role] = above.position + 1

    if positions:
        await guild.edit_role_positions(positions=positions, reason="LazyCatter plan")
