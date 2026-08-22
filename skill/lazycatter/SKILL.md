---
name: lazycatter
description: >
  Produce a Discord server restructuring plan (plan.yaml) that LazyCatter
  can import and apply. Use when the user wants to redesign, rename, reorganise,
  or clean up a Discord server's categories and channels and hands over any of:
  a screenshot of the current channel list, an exported structure JSON from
  LazyCatter, a saved restore/template plan.yaml from LazyCatter, a description
  of how they want it to change, or reference screenshots of other servers for
  inspiration. Trigger on requests like "redesign my Discord", "reorganize these
  channels", "make a plan for my server", "turn this into a plan.yaml", "undo
  from this saved plan", "clone this server layout", or when a server screenshot
  is shared alongside change notes. Built for Claude (Projects, Claude Code, or
  pasted skill text). LazyCatter itself is a local Windows app the user runs.
---

# LazyCatter plan skill

Turn a picture (or export) of a Discord server plus the user's intent into a
valid `plan.yaml` that LazyCatter applies by renaming and moving existing
channels in place, which keeps message history, pins, and channel IDs.

You are the planner. The user is the operator in the LazyCatter Windows app.
They upload your plan, preview a diff, type APPLY, then Execute.

## What you produce

A single `plan.yaml` conforming to `reference/schema.md`. Nothing else executes.
The plan is inert text. LazyCatter re-checks it against the live server and shows
a diff before anything changes.

**Never apply a plan yourself.** Do not call Discord APIs, do not press Execute,
and do not instruct the bot to run until the user explicitly asks for that step
in the same message.

## Inputs you may be given

1. **A LazyCatter saved plan** from the UI:
   - **Save to restore** → `plan_kind: restore` with channel/category **IDs** in
     `match:`. Use to undo on the **same** `source_guild_id`.
   - **Export template** → `plan_kind: template` with `match: null`. Use to
     recreate the look on a **different** server.
2. **Exported structure JSON** if they still have one. Prefer IDs from it.
3. **A screenshot** of the channel list. Copy glyphs/emoji exactly if you must
   use names instead of IDs.
4. **A change description**. What should differ from the saved/current layout.
5. **Reference screenshots of other servers**. Patterns only, never wholesale
   branding copy unless the user owns both and asks to clone.

## Restore vs template vs redesign

| Goal | What to start from | `match:` | Notes |
|------|--------------------|----------|-------|
| Undo after a bad apply | Saved **restore** plan from before the change | Channel/category IDs | Same server only |
| Copy look to another server | Saved **template** plan from the source | `null` (creates) | Connect bot to the **target** guild |
| Redesign in place | Restore plan or export JSON + user intent | IDs of channels that exist now | Only change `name:` / order / archive |

When editing a restore plan into a redesign: **keep** each `match:` ID, only
change `name:`, order, topics, or move channels between categories. That is
what preserves history.

When building a clone: start from a template plan (or convert restore → template
by setting every channel `match: null` and removing category `match` keys). Tell
the user to connect LazyCatter to the **target** server before Apply.

## The one rule that matters most

Every channel has two fields: `match:` finds the existing channel, `name:` is
what it becomes. **`match:` must identify the channel that exists NOW (exact
current name, or snowflake ID). Only `name:` carries the new value.**

```yaml
# best: id from a restore plan or export json
- match: "123456789012345678"
  name: general
  type: text

# template / brand-new channel
- match: null
  name: rules
  type: text
```

**Never strip decorations in name-based `match:` values.** Prefer IDs.

## Process

1. Read `reference/planner-guide.md` and `reference/schema.md`.
2. Prefer a LazyCatter **saved plan** over a screenshot.
3. If any channel purpose is unclear, STOP and ask before renaming.
4. Draft `plan.yaml`. Set `plan_kind` / `source_guild_id` when you know them.
5. If a validator is available: `python skill/lazycatter/scripts/validate_plan.py plan.yaml`
6. Hand the user the plan and tell them: upload → preview diff → type APPLY →
   Execute. For clones, remind them the bot must be in the **target** server.

## Do not

- Do not apply a **restore** plan to a different guild (IDs will not match).
- Do not turn a restore plan into creates unless the user asked to clone.
- Do not delete-and-recreate to "rename".
- Do not fabricate match IDs or names you did not see.
- Do not execute against Discord unless the user asked in this turn.
