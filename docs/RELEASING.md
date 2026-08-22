# Making a release (maintainers)

Output goes under `release/` which is gitignored on purpose. You upload the zip yourself. Nothing here pushes to GitHub.

## Steps

1. Bump `VERSION` and `CHANGELOG.md` (and `#define MyAppVersion` in `desktop/LazyCatter.iss` if you ship Setup.exe).
2. Optional signing: set `LAZYCATTER_CODESIGN_PFX` + password, see [SIGNING.md](SIGNING.md).
3. Run:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/make-release.ps1
```

4. Open `release\<version>\` and upload to a GitHub Release by hand:
   - `LazyCatter-windows-x64-<version>.zip` (this is the Download for Windows artefact)
   - `LazyCatter-Setup-<version>.exe` if Inno Setup built one
   - `SHA256SUMS.txt`
5. Release body can point at `docs/USER.md` and `SECURITY.md`, and Issues at https://github.com/ShahriarAHaque/LazyCatter/issues

## Hygiene check before tagging

- No `.env`, tokens, `*.pfx`, guild dumps, or `dist/` / `release/` in git
- README Download path does not tell end users to install Python
- Portable zip README.txt is inside the zip
