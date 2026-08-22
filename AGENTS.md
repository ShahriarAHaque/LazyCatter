# Agents.md

## Project overview

LazyCatter is a locally hosted Discord server shaper, agents (Claude preferred for the public skill path) write inert `plan.yaml` files under `skill/lazycatter/`. The FastAPI app in `bot/` imports those plans, shows a diff, and only then can rename/move stuff through a short lived discord.py client, the normal path for users is the Windows desktop app (`bot/launcher.py` + pywebview + PyInstaller). Docker is optional. Stack is Python 3.12, FastAPI, discord.py, PyYAML, pywebview. Single app repo: `bot/` + `skill/` + `desktop/`.

Publisher branding: LilaNaCl. GitHub / Issues: ShahriarAHaque/LazyCatter.

## Setup commands

- Desktop deps: `pip install -r bot/requirements-desktop.txt`
- Run desktop UI (dev): `python bot/launcher.py`
- Build Windows app: `powershell -ExecutionPolicy Bypass -File scripts/build-windows.ps1`
- Install + desktop shortcut (dev machine): `powershell -ExecutionPolicy Bypass -File desktop/install.ps1`
- One-shot local build+install: double-click `desktop/Install-LazyCatter.bat`
- Public release zip (gitignored output): `powershell -ExecutionPolicy Bypass -File scripts/make-release.ps1`
- Docker (optional): `cp .env.example .env`, set `LAZYCATTER_UI_TOKEN`, then `docker compose up --build`
- Validate a plan: `python skill/lazycatter/scripts/validate_plan.py path/to/plan.yaml`

## Development workflow

Prefer `python bot/launcher.py` while poking at the UI. Keep `bot/ui.html` looking like the original shaper panel (dark panels, accent buttons, kill switch). Branding text is LazyCatter, publisher LilaNaCl.

Packaging is `desktop/lazycatter.spec`. Rebuild after UI or engine changes before you tell anyone to install.

Desktop mode sets `LAZYCATTER_DESKTOP=1` and only stores the local UI gate under `%APPDATA%\LazyCatter\ui_token.txt`, Discord bot tokens stay in the UI session, never in files or git.

Plans can sit under `plans/` locally. That folder ignores yaml content on purpose.

End-user Download path is the portable zip from `scripts/make-release.ps1`, not Python from source. See `docs/USER.md` and `docs/RELEASING.md`.

## Testing

- Schema / plan validation: `python skill/lazycatter/scripts/validate_plan.py <plan.yaml>`
- Manual UI check: open the desktop window, confirm it still looks like `bot/ui.html`, connect needs a bot token, Execute needs APPLY typed in, first-run tip shows once.
- After a Windows build, run install.ps1 once and launch from the Desktop shortcut, or assemble `release/` and run the unzipped exe.
- Dont invent Discord live tests against production servers.

## Code style

Python 3, keep the three chunks in `bot/app.py` (engine, executor, server) unless theres a real reason to split. Small readable functions over new abstraction layers. YAML plans have to pass `skill/lazycatter/scripts/validate_plan.py`.

README is chat. Code comments are chat. The rest of the docs are casual. Licence text stays stock [PolyForm Noncommercial 1.0.0](https://polyformproject.org/licenses/noncommercial/1.0.0). Do not invent a custom licence.

## Build and deployment

- Desktop folder build: `dist/LazyCatter/` (gitignored)
- Manual release artefacts: `release/<version>/` (gitignored, upload by hand)
- Install location (dev install script): `%LOCALAPPDATA%\LazyCatter`
- Optional Inno Setup output: `installer-out/LazyCatter-Setup.exe`
- Docker stays loopback only on `127.0.0.1:8787`
- Do not bake Discord tokens into the image or exe
- Signing: `docs/SIGNING.md` (publisher LilaNaCl)

## Pull request guidelines

- Title format: `[component] Brief description` e.g. `[desktop] Add Windows installer shortcuts`
- Before review: plan validator still passes, and `.env`, tokens, `dist/`, `release/`, and certs are not in the diff
- Reject anything that adds Discord tokens, UI secrets, or server export dumps

## Hard rules for agents

- Never push to GitHub unless the user asks in that turn.
- Never connect to Discord, export a live guild, or execute a plan unless the user asks in that turn. Writing or validating `plan.yaml` is fine. Applying it is not.
- Never commit `.env`, bot tokens, personal account tokens, real guild dumps, or built `dist/` / `release/` binaries with secrets in them.
- Execute needs `confirm: "APPLY"`. Do not bypass that.
- Prefer rename/move via `match:` over create-delete. Keeping history is the whole point.

## Extra notes

- Shared validator path: `skill/lazycatter/scripts/validate_plan.py`
- `/api/desktop-bootstrap` only hands back the UI token when `LAZYCATTER_DESKTOP=1` and the client is loopback
- Archive moves retired channels into ARCHIVE and locks send/react for `@everyone`
- Pacing uses `duration_seconds` or per-action `delay` on `/api/execute`
- Kill switch cancels the run and closes the Discord client immediately
- **Save to restore** writes an ID based plan for undo on the same server
- **Export template** writes a create plan for cloning onto another server
- Plan `roles:` create/edit/reorder via same diff → APPLY flow (never delete roles)
- Content mover (`/api/move/*`) copies forum starters (art + caption) via webhook, Message Content intent on
- Bugs for humans: https://github.com/ShahriarAHaque/LazyCatter/issues
