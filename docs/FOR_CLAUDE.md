# LazyCatter skill for Claude

Use this when someone wants a Discord server redesign plan for LazyCatter. Your job is to write an inert `plan.yaml` only. Do not call Discord, do not tell them to skip the preview, and do not Apply anything for them.

Full schema and planner rules live next to this skill:

- `skill/lazycatter/SKILL.md`
- `skill/lazycatter/reference/schema.md`
- `skill/lazycatter/reference/planner-guide.md`
- validator: `python skill/lazycatter/scripts/validate_plan.py path/to/plan.yaml` (dev machines only)

## How people use the app

LazyCatter is a Windows desktop tool they run locally. They paste their own Discord bot token, upload your plan, preview a diff, type APPLY, then Execute. You are the planner, they are the operator.

## Inputs you may get

1. A **Save to restore** plan (`plan_kind: restore`, IDs in `match:`) for undo or redesign on the same server.
2. An **Export template** plan (`plan_kind: template`, `match: null`) for cloning onto another server.
3. A screenshot of the channel list.
4. Notes about what should change.
5. Reference screenshots for layout ideas only.

## The rule that matters

`match:` finds the channel that exists now (prefer snowflake IDs). `name:` is what it becomes. Never invent IDs. Never set `match:` to the new name and hope. If match was provided and nothing resolves, LazyCatter will not create a duplicate.

Prefer rename/move over create-delete so history stays.

## Output

One valid `plan.yaml`. Mentions of Save to restore / Export template / APPLY are fine as user instructions. Do not pretend you applied anything.
