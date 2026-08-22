# Security

Publisher name on Windows builds is LilaNaCl. Legal copyright is LilaNaCl (Shahriar Haque). Development and the GitHub repo sit under ShahriarAHaque.

LazyCatter runs on your machine only, it binds to loopback (127.0.0.1). It is not a hosted Discord bot and it does not send your stuff to us.

## What lives where

| Thing | Where | Leaves the machine? |
|---|---|---|
| Discord bot token | Typed into the UI each session, held in memory by discord.py while connected | Only goes to Discord when you Connect. Never written to disk, never put in the installer, never logged on purpose |
| Local UI token | `%APPDATA%\LazyCatter\ui_token.txt` in desktop mode (or `LAZYCATTER_UI_TOKEN` in `.env` for Docker) | No. This only gates the local UI so other programs on your PC cannot drive the app |
| Saved plans | Plan box, Downloads, and `%APPDATA%\LazyCatter\plans\` | No, unless you upload or share those files yourself |
| Move job log | `%APPDATA%\LazyCatter\move-jobs\` (source→copied message ids) | No. Used so a killed copy can resume without duplicating |
| Desktop log | `%APPDATA%\LazyCatter\desktop.log` | No. Startup errors only, not your bot token |

## Message Content intent

The desktop bot turns on Discord's **Message Content** privileged intent so the content mover can read historical text and attachments, meaning while connected the bot can read message bodies in channels it can see. Connect, move, disconnect. Turn the intent on in the Developer Portal for your bot application or history reads come back empty.

## Bot token vs UI token

The **bot token** is from the Discord Developer Portal. That is what talks to Discord. Treat it like a password for the bot account.

The **UI token** is a random local secret LazyCatter invents (or you set in Docker). It is not a Discord credential. Desktop mode creates and fills it for you.

Never paste a personal Discord account token. Automating a user account is against Discord rules and can get the account banned, use a bot application token only.

## What we do not do

- We do not host your bot
- We do not collect telemetry in this build
- We do not need your Discord password
- Preview and validate never mutate the server. Execute only runs after you type APPLY

## Reporting a security issue

If you find something that leaks tokens or lets another process drive the UI without the local gate, open a private note via GitHub Issues on the repo and mark it clearly, or email the maintainer listed on the GitHub profile. Do not paste live bot tokens into a public issue.
