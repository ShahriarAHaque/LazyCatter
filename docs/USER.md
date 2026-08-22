# Using LazyCatter (Windows)

This is the normal-user guide. You do not need Python, PowerShell, or to build anything from source.

Bugs and feature requests: https://github.com/ShahriarAHaque/LazyCatter/issues

Publisher: LilaNaCl. Dev / GitHub: ShahriarAHaque.

Licence is PolyForm Noncommercial 1.0.0. You can use LazyCatter for personal and hobby stuff, you cannot sell it or use it commercially. Full terms: [LICENSE](../LICENSE).

## Download for Windows

1. Grab the latest `LazyCatter-windows-x64-*.zip` from [Releases](https://github.com/ShahriarAHaque/LazyCatter/releases).
2. Unzip it somewhere you can find again (Desktop is fine).
3. Double-click `LazyCatter.exe`.
4. Windows may say the publisher is unknown until the build is signed. If you trust the release you downloaded from the official GitHub repo, choose More info → Run anyway.

That is the whole install. No installer required for the portable zip. If a `LazyCatter-Setup.exe` is attached to the same release, you can use that instead and it will put shortcuts on your Desktop / Start Menu.

## One-time Discord bot setup

You bring your own bot. LazyCatter does not ship a shared public bot.

1. Open https://discord.com/developers/applications
2. New Application → Bot → Reset Token → copy the token. Under Privileged Gateway Intents turn **Message Content Intent** on. The content mover needs it or copies come out empty.
3. OAuth2 → URL Generator → scope `bot` → tick View Channels, Manage Channels, Manage Roles, Read Message History, Send Messages, Embed Links, Attach Files, and Manage Webhooks → open the URL and invite the bot to your server.
4. Server Settings → Roles → drag the bot role above any role whose channels it has to edit.

Use a bot token only. Never a personal account token.

## First run checklist

1. Open LazyCatter.
2. Paste bot token + server ID (Developer Mode on Discord → right-click server → Copy Server ID).
3. Connect. The header should show the server name.
4. Before big changes, click **Save to restore** so you can undo.
5. Get a `plan.yaml` (from Claude with the LazyCatter skill, or edit an exported plan).
6. Upload and validate → Preview diff → read every warning.
7. Type `APPLY`, set how long to spread the changes, Execute.
8. Hit STOP if you need to bail. Disconnect when done, then kick the bot from the server if you are finished with it.

## Restore vs template

- **Save to restore**. ID based plan for the same server. Use this to undo.
- **Export template**. Create plan for cloning the look onto another server. Connect LazyCatter to the target server before you Apply a template.

## Common failures

- **Missing Access / 403**. Bot role is too low, or a channel has overrides the bot cannot beat. Raise the bot role.
- **Wrong server**. Check the server ID in the header.
- **Nothing matched**. Restore plans need IDs from that same server. Do not use a restore plan on a different guild.
- **Duplicates after a redesign**. `match:` must point at the channel that exists now (prefer IDs). Only `name:` is the new title.
- **Empty message copy**. Turn on Message Content Intent for the bot in the Developer Portal, then reconnect.

## Move content

Stage 3 in the UI (before Review & execute). Connect first, then pick source / threads / target from the live server list. Dry run first.

- **Source + threads**. After connect, channels load into dropdowns. Forums show their posts as checkboxes, tick what you want. Text channels with no threads just copy the channel body.
- **Starters only** (default). Each forum post's first message (art + caption/link + files).
- **Whole thread**. Every message in the post. Use this for library-of-x dumps that hold many arts in one thread.
- Link/embed images (fiverr etc) get written into the body so they still show after copy.
- Optional source link under each copy, optional age-restrict on the target.
- Source stays until you choose keep / archive / delete after a full copy. Delete asks twice.

There is also a one-shot CLI under `scripts/move_libraries_to_fanart.py` if you want the same job from a terminal (dry run by default, `--apply` to copy). Needs `DISCORD_TOKEN`, `GUILD_ID`, `SOURCE_FORUM_ID`, `TARGET_ID`, `POST_NAMES`, and Message Content intent. No server ids are baked in.

## Plans with Claude

Hand Claude the skill under `skill/lazycatter/` (or paste `docs/FOR_CLAUDE.md`), plus a screenshot or a saved plan, and what you want changed. Claude should only write `plan.yaml`. You run Apply yourself in LazyCatter.

## Privacy in one line

Bot token stays in memory for the session. UI token and saved plans stay on your PC. See [SECURITY.md](../SECURITY.md).
