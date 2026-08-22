# Signing Windows builds (LilaNaCl)

Publisher name on the binary / Setup wizard is **LilaNaCl**. The GitHub account that ships Releases is **ShahriarAHaque**.

This repo cannot invent a real Authenticode certificate. Without one, Windows SmartScreen will say the publisher is unknown, that is expected for an unsigned zip.

## What you need

1. A code signing certificate as a `.pfx` / `.p12` (bought from a CA, or whatever org process you use). Keep it off git. `*.pfx` is gitignored.
2. Windows SDK **signtool.exe** on the machine that signs.
3. Env vars for the signing session only:

```powershell
$env:LAZYCATTER_CODESIGN_PFX = "D:\path\to\LilaNaCl-codesign.pfx"
$env:LAZYCATTER_CODESIGN_PASSWORD = "your-cert-password"
# optional:
# $env:LAZYCATTER_CODESIGN_TIMESTAMP = "http://timestamp.digicert.com"
```

Then:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/build-windows.ps1
powershell -ExecutionPolicy Bypass -File scripts/sign-windows.ps1
powershell -ExecutionPolicy Bypass -File scripts/make-release.ps1 -SkipBuild
```

Or just `make-release.ps1`, which calls the signer when those env vars are set.

## Stuck without a cert?

Ship the portable zip unsigned for now. Say in the Release notes that SmartScreen may warn, and that people should only download from `https://github.com/ShahriarAHaque/LazyCatter/releases`. Add signing later when the `.pfx` exists. Do not commit the cert or the password.
