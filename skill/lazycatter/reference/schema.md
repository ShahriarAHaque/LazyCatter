# plan.yaml schema

A plan is a YAML mapping. Top-level keys:

| key                | required | type   | meaning                                                        |
|--------------------|----------|--------|----------------------------------------------------------------|
| `server_name`      | no       | string | Cosmetic label, shown in LazyCatter. Not applied to the server. |
| `source_guild_id`  | no       | string | Guild ID the plan was saved from. Cosmetic / for agents.       |
| `plan_kind`        | no       | string | `restore` (ID matches, same server undo) or `template` (clone). |
| `captured_at`      | no       | string | ISO timestamp when LazyCatter saved the layout.                |
| `categories`       | yes      | list   | Ordered list of category objects. Order = sidebar order.       |
| `archive`          | no       | list   | Channel names/IDs to retire (move to archive, lock read-only). |
| `archive_category` | no       | string | Category to hold archived channels. Default `"ARCHIVE"`.       |
| `roles`            | no       | list   | Role objects to create/edit/reorder. Never deletes roles.      |

## Role object

| key              | required | type         | meaning |
|------------------|----------|--------------|---------|
| `name`           | yes      | string       | Desired role name. |
| `match`          | yes*     | string/null  | Current role name or ID. `null` = create. *Key must be present. |
| `colour`         | no       | string       | Hex colour like `#f0324f`. |
| `hoist`          | no       | bool         | Show separately in member list. |
| `mentionable`    | no       | bool         | Allow @mention. |
| `permissions`    | no       | list         | Friendly names, e.g. `manage_messages`, `kick_members`. |
| `position_above` | no       | string       | Name/ID of the role this one should sit above. |

## Category object

| key        | required | type   | meaning                                                              |
|------------|----------|--------|---------------------------------------------------------------------|
| `name`     | yes      | string | Desired category name.                                              |
| `match`    | no       | string | Current category name or ID to rename in place. Omit to match `name`, or create fresh if none exists. |
| `channels` | no       | list   | Ordered list of channel objects.                                   |

## Channel object

| key     | required | type    | meaning                                                                     |
|---------|----------|---------|-----------------------------------------------------------------------------|
| `name`  | yes      | string  | Desired channel name.                                                       |
| `match` | yes*     | string/null | Current name or ID of the channel to rename/move in place. Prefer snowflake `id` from a LazyCatter export. If using a name, it must be the exact current name (emoji/unicode included). `null` = create new. *The key must be present, its value may be null. |
| `type`  | no       | string  | One of `text`, `voice`, `forum`, `stage`, `announcement`. Default `text`.   |
| `topic` | no       | string  | Channel topic/description (text/forum/announcement only).                   |

## Rules the validator enforces

1. `categories` exists and is a list.
2. Every channel has a non-empty `name`.
3. Every channel has a `match` key present (value may be `null`).
4. `type`, where given, is one of the five valid values.
5. No two channels share the same (`type`, `name`) pair.
6. No two channels reuse the same non-null `match` value.
7. `archive`, where given, is a list of strings.
8. `roles`, where given, is a list, each role has `name` and a `match` key.

## Minimal example

```yaml
server_name: "My Server"
archive_category: "ARCHIVE"

categories:
  - name: "START HERE"
    match: "THE LANDS BETWEEN"     # existing category renamed
    channels:
      # prefer ids from export when names are decorated
      - match: "123456789012345678"
        name: general
        type: text
      - match: "♛﹒roundtable-hold"  # exact current name if not using id
        name: general-chat
        type: text
      - match: null                 # brand new channel
        name: rules
        type: text
        topic: "Read before posting."

  - name: "VOICE"
    channels:
      - match: "[OPEN]. summon sign ⌟"
        name: "general-vc"
        type: voice

archive:
  - keepsake                        # retired not deleted

roles:
  - match: Meowderator
    name: Meowderator
    colour: "#f0324f"
    hoist: true
    permissions: [manage_messages, kick_members, moderate_members]
    position_above: Friend
```
