# lazycatter

local windows app that drives your own discord bot to reshape a server from a `plan.yaml`
channels get renamed and moved in place
so history pins and ids stay
nothing gets deleted and remade just to look different

publisher: **LilaNaCl**
dev / github: [ShahriarAHaque](https://github.com/ShahriarAHaque)

bugs: [GitHub Issues](https://github.com/ShahriarAHaque/LazyCatter/issues)

## download for windows

1. open [Releases](https://github.com/ShahriarAHaque/LazyCatter/releases)
2. download `LazyCatter-windows-x64-*.zip`
3. unzip
4. double-click `LazyCatter.exe`

no python
no powershell
no building from source
if windows smartscreen complains about an unknown publisher that is expected on unsigned builds
use more info → run anyway only if you got the zip from this repos releases

full walkthrough: [docs/USER.md](docs/USER.md)
what is stored where: [SECURITY.md](SECURITY.md)
licence: [LICENSE](LICENSE) (polyform noncommercial 1.0.0)
personal and hobby use is fine
selling it or using it commercially is not

## what you need

your own discord bot (developer portal)

invite it with these permissions (oauth2 → url generator → scope `bot`):
- View Channels
- Manage Channels
- Manage Roles
- Read Message History
- Send Messages
- Embed Links
- Attach Files
- Manage Webhooks

then in the developer portal turn **Message Content Intent** on
bot → privileged gateway intents → Message Content Intent
without that the content mover copies empty messages

role dragged high enough to edit what you care about
bot token only
never a personal account token

## first run (short)

connect with bot token + server id
**save to restore** before big edits
upload a plan
preview diff
type APPLY
execute
STOP cancels
disconnect when you are done

## plans with claude

lazycatter does not invent the redesign for you
hand claude the [Skill](skill/lazycatter/SKILL.md)
(or [docs/FOR_CLAUDE.md](docs/FOR_CLAUDE.md))
plus a screenshot or exported plan
and what you want changed
claude writes `plan.yaml`
you apply it in the app

## for developers

agent / contributor notes: [AGENTS.md](AGENTS.md)
building installers and release zips from this repo is a separate path from the download for windows zip above

```powershell
pip install -r bot/requirements-desktop.txt
python bot/launcher.py
```

optional docker: copy `.env.example` to `.env`
set `LAZYCATTER_UI_TOKEN`
then `docker compose up --build`
and open http://127.0.0.1:8787
