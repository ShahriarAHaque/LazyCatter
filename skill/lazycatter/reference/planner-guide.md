# Planner guide

How to make a *good* plan, not just a valid one.

## Hard rules (never break)

- **Rename, don't recreate.** If a channel exists, `match:` it and change only
  `name:`. Deleting + recreating loses history, pins, and every posted link.
- **`match:` is the anchor.** Prefer the channel **ID** from a LazyCatter export.
  Otherwise use the **exact** current name, including every emoji and unicode
  decoration. Never write a stripped slug you "read as" the name.
- **Order = sidebar order.** List categories and channels top-to-bottom exactly
  as you want them to appear.
- **No type conversion.** Discord cannot convert a text channel to forum/voice or
  vice versa. If the user wants a forum where a text channel is, make a NEW forum
  (`match: null`) and, if they want the old discussions kept, archive the old text
  channel rather than "converting" it.
- **Ask, don't hallucinate.** If you can't tell what a channel is for, ask the
  user before naming it. A confident wrong name is worse than a question.
- **Export before baseline plans.** Prefer LazyCatter **Save layout as plan**
  (restore / ID matches) or **Save as template** (clone). Screenshot-only plans
  often drop decorative characters and cause match failures.
- **Undo = restore plan.** Save a restore plan before a risky Apply. Re-upload
  that file on the same server to put names/order back. History stays because
  matches are IDs, not deletes.
- **Clone = template plan.** Save as template on the source server, connect the
  bot to the target server, upload, preview, Apply. Expect creates (and possible
  reuse if same-named channels already exist).

## Design judgment

- **Theme in categories, clarity in channels.** A themed server can keep its
  flavour in *category* headers ("THE CATFE", "LAND OF SHADOWS") while making
  *channel* names literal so nobody has to guess: `#clips` not `#replays`,
  `#introductions` not `#new-tarnished`. This preserves identity and fixes
  clarity at the same time, usually the right default. Confirm the balance with
  the user, some want full theme, some want fully literal.
- **Fewer channels, not more.** Most activity happens in 3–4 channels. A lean
  server feels alive, a sprawling one feels like a ghost town. When cutting,
  archive rather than delete.
- **Put info/onboarding at the top.** The first visible channel is what new
  members land on. `#welcome`, `#rules`, `#roles`, `#announcements` belong first.
- **Match structure to purpose.** A friends-and-viewers hangout stays small and
  cosy. A creator/growth server needs an onboarding gate, go-live alerts, and a
  clips pipeline. Ask which one this is before deciding the shape.
- **Group voice channels together**, labelled by use (open / private / afk),
  not by lore alone if lore obscures function.

## Using reference images

Reference screenshots of other servers are for *patterns*, how they group
onboarding, how they separate community from staff, how they name for clarity.
Extract the pattern, never lift another server's exact names, branding, or
category text. The output must be the user's own server, improved.

## Handoff checklist

Before returning the plan:
- [ ] Every existing channel is `match:`ed to its real current name.
- [ ] Every new channel has `match: null`.
- [ ] No unclear channel was named by guessing (you asked instead).
- [ ] Categories and channels are in intended sidebar order.
- [ ] Any type change is handled as new-channel + archive, not conversion.
- [ ] `python scripts/validate_plan.py plan.yaml` passes.
- [ ] You told the user: upload plan → review diff → type APPLY → Execute in LazyCatter.
- [ ] You did not connect or execute against Discord unless the user asked for that.
