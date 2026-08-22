# -*- mode: python ; coding: utf-8 -*-
# pyinstaller spec for the lazycatter desktop app
# build:  pyinstaller desktop/lazycatter.spec
# from repo root

import sys
from pathlib import Path

ROOT = Path(SPECPATH).resolve().parent
BOT = ROOT / "bot"
SKILL = ROOT / "skill" / "lazycatter"

block_cipher = None

a = Analysis(
    [str(BOT / "launcher.py")],
    pathex=[str(BOT), str(ROOT)],
    binaries=[],
    datas=[
        (str(BOT / "ui.html"), "bot"),
        (str(SKILL), "skill/lazycatter"),
        (str(ROOT / "VERSION"), "."),
        (str(ROOT / "LICENSE"), "."),
    ],
    hiddenimports=[
        "app",
        "version",
        "uvicorn.logging",
        "uvicorn.loops",
        "uvicorn.loops.auto",
        "uvicorn.protocols",
        "uvicorn.protocols.http",
        "uvicorn.protocols.http.auto",
        "uvicorn.protocols.websockets",
        "uvicorn.protocols.websockets.auto",
        "uvicorn.lifespan",
        "uvicorn.lifespan.on",
        "discord",
        "yaml",
        "webview",
        "validate_plan",
        "roles",
        "mover",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="LazyCatter",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,  # no command prompt window for end users
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="LazyCatter",
)
