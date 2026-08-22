# assemble a local release folder for manual github upload
# output lands in release/ (gitignored) so it cannot be committed by mistake
#
#   powershell -ExecutionPolicy Bypass -File scripts/make-release.ps1
#   powershell -ExecutionPolicy Bypass -File scripts/make-release.ps1 -SkipBuild
#
# optional Setup.exe if inno setup 6 is installed.

param(
    [switch]$SkipBuild,
    [switch]$SkipSign
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$Version = (Get-Content (Join-Path $Root "VERSION") -Raw).Trim()
if (-not $Version) { Write-Error "VERSION file is empty" }

$DistExe = Join-Path $Root "dist\LazyCatter\LazyCatter.exe"

# stop a running app so files are not locked while we copy/zip
Get-Process -Name "LazyCatter" -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep -Milliseconds 500

if (-not $SkipBuild -or -not (Test-Path $DistExe)) {
    Write-Host "Building desktop app..."
    & powershell -ExecutionPolicy Bypass -File (Join-Path $Root "scripts\build-windows.ps1")
    if ($LASTEXITCODE -ne 0) { Write-Error "build-windows.ps1 failed" }
}

if (-not (Test-Path $DistExe)) {
    Write-Error "Missing $DistExe after build"
}

if (-not $SkipSign) {
    & powershell -ExecutionPolicy Bypass -File (Join-Path $Root "scripts\sign-windows.ps1")
}

$OutDir = Join-Path $Root "release\$Version"
$StageName = "LazyCatter-windows-x64-$Version"
$Stage = Join-Path $OutDir $StageName
$ZipPath = Join-Path $OutDir "$StageName.zip"

if (Test-Path $OutDir) {
    Remove-Item $OutDir -Recurse -Force
}
New-Item -ItemType Directory -Path $Stage -Force | Out-Null

Write-Host "Staging portable folder -> $Stage"
Copy-Item -Path (Join-Path $Root "dist\LazyCatter\*") -Destination $Stage -Recurse -Force
Copy-Item (Join-Path $Root "LICENSE") $Stage -Force
Copy-Item (Join-Path $Root "SECURITY.md") $Stage -Force
Copy-Item (Join-Path $Root "CHANGELOG.md") $Stage -Force
Copy-Item (Join-Path $Root "docs\USER.md") (Join-Path $Stage "USER.md") -Force
Copy-Item (Join-Path $Root "VERSION") $Stage -Force

$Readme = @"
LazyCatter $Version
Publisher: LilaNaCl
Copyright: LilaNaCl (Shahriar Haque)
Dev / GitHub: ShahriarAHaque

Download for Windows (this zip)
1. Unzip this folder
2. Double-click LazyCatter.exe
3. No Python or PowerShell needed

If Windows SmartScreen warns about an unknown publisher, that means this build was not Authenticode-signed (or the cert is not trusted yet). Only continue if you got this zip from https://github.com/ShahriarAHaque/LazyCatter/releases

User guide: USER.md
Security: SECURITY.md
Licence: LICENSE (PolyForm Noncommercial 1.0.0)
Personal and hobby use is fine, selling it or using it commercially is not.
Bugs: https://github.com/ShahriarAHaque/LazyCatter/issues
"@
Set-Content -Path (Join-Path $Stage "README.txt") -Value $Readme -Encoding UTF8

if (Test-Path $ZipPath) { Remove-Item $ZipPath -Force }
Write-Host "Zipping $ZipPath"
# compress-archive can fail on locked nested zips under _internal
# use .NET ZipFile instead
Add-Type -AssemblyName System.IO.Compression.FileSystem
if (Test-Path $ZipPath) { Remove-Item $ZipPath -Force }
[System.IO.Compression.ZipFile]::CreateFromDirectory($Stage, $ZipPath, [System.IO.Compression.CompressionLevel]::Optimal, $false)

# optional inno setup wizard
$IsccCandidates = @(
    "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
    "${env:ProgramFiles}\Inno Setup 6\ISCC.exe",
    "${env:LocalAppData}\Programs\Inno Setup 6\ISCC.exe"
)
$Iscc = $IsccCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1
$SetupOut = $null
if ($Iscc) {
    Write-Host "Compiling Setup.exe with Inno Setup..."
    $InstallerOut = Join-Path $Root "installer-out"
    New-Item -ItemType Directory -Path $InstallerOut -Force | Out-Null
    & $Iscc (Join-Path $Root "desktop\LazyCatter.iss")
    $BuiltSetup = Join-Path $InstallerOut "LazyCatter-Setup.exe"
    if (Test-Path $BuiltSetup) {
        $SetupOut = Join-Path $OutDir "LazyCatter-Setup-$Version.exe"
        Copy-Item $BuiltSetup $SetupOut -Force
        if (-not $SkipSign -and $env:LAZYCATTER_CODESIGN_PFX) {
            $env:LAZYCATTER_SIGN_EXTRA = $SetupOut
        }
    }
} else {
    Write-Host "Inno Setup 6 not found, skipping Setup.exe (portable zip is enough for Downloads)."
}

# checksums
$Sums = Join-Path $OutDir "SHA256SUMS.txt"
$lines = @()
Get-ChildItem $OutDir -File | Where-Object { $_.Name -match '\.(zip|exe)$' } | ForEach-Object {
    $hash = (Get-FileHash $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
    $lines += "$hash  $($_.Name)"
}
Set-Content -Path $Sums -Value ($lines -join "`n") -Encoding ASCII

$Manifest = @"
LazyCatter release $Version
publisher: LilaNaCl
developer_github: ShahriarAHaque
issues: https://github.com/ShahriarAHaque/LazyCatter/issues
created_utc: $((Get-Date).ToUniversalTime().ToString("o"))
portable_zip: $(Split-Path $ZipPath -Leaf)
setup_exe: $(if ($SetupOut) { Split-Path $SetupOut -Leaf } else { "(not built)" })
signed: $(if ($env:LAZYCATTER_CODESIGN_PFX) { "attempted via sign-windows.ps1" } else { "no" })

Upload these files manually to a GitHub Release. Do not commit the release/ folder.
"@
Set-Content -Path (Join-Path $OutDir "MANIFEST.txt") -Value $Manifest -Encoding UTF8

Write-Host ""
Write-Host "Release ready (gitignored): $OutDir"
Get-ChildItem $OutDir | Format-Table Name, Length
Write-Host "Upload the zip (and Setup.exe if present) to GitHub Releases by hand."
