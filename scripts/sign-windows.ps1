# sign windows binaries as publisher LilaNaCl when a code signing cert is available
# this does nothing useful without a real authenticode certificate
#
# expected env (do not commit these):
#   LAZYCATTER_CODESIGN_PFX      = full path to .pfx / .p12
#   LAZYCATTER_CODESIGN_PASSWORD = cert password
# optional:
#   LAZYCATTER_CODESIGN_TIMESTAMP = http://timestamp.digicert.com
#
# run after build before make-release:
#   powershell -ExecutionPolicy Bypass -File scripts/sign-windows.ps1

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Exe = Join-Path $Root "dist\LazyCatter\LazyCatter.exe"
$Publisher = "LilaNaCl"

$Pfx = $env:LAZYCATTER_CODESIGN_PFX
$Password = $env:LAZYCATTER_CODESIGN_PASSWORD
$Timestamp = $env:LAZYCATTER_CODESIGN_TIMESTAMP
if (-not $Timestamp) { $Timestamp = "http://timestamp.digicert.com" }

if (-not (Test-Path $Exe)) {
    Write-Error "Missing $Exe. Run scripts/build-windows.ps1 first."
}

if (-not $Pfx -or -not (Test-Path $Pfx)) {
    Write-Host "No LAZYCATTER_CODESIGN_PFX set (or file missing)."
    Write-Host "Leaving $Exe UNSIGNED. SmartScreen will warn until you sign as $Publisher."
    Write-Host "See docs/SIGNING.md"
    exit 0
}

$Signtool = $null
$kits = @(
    "${env:ProgramFiles(x86)}\Windows Kits\10\bin",
    "${env:ProgramFiles}\Windows Kits\10\bin"
)
foreach ($kit in $kits) {
    if (-not (Test-Path $kit)) { continue }
    $found = Get-ChildItem -Path $kit -Recurse -Filter signtool.exe -ErrorAction SilentlyContinue |
        Sort-Object FullName -Descending |
        Select-Object -First 1
    if ($found) { $Signtool = $found.FullName; break }
}
if (-not $Signtool) {
    $cmd = Get-Command signtool.exe -ErrorAction SilentlyContinue
    if ($cmd) { $Signtool = $cmd.Source }
}
if (-not $Signtool) {
    Write-Error "signtool.exe not found. Install Windows SDK Signing Tools, or sign on a machine that has them."
}

Write-Host "Signing $Exe as $Publisher with $Signtool"
& $Signtool sign /f $Pfx /p $Password /fd SHA256 /tr $Timestamp /td SHA256 /d "LazyCatter" /du "https://github.com/ShahriarAHaque/LazyCatter" $Exe
if ($LASTEXITCODE -ne 0) {
    Write-Error "signtool failed with exit $LASTEXITCODE"
}
& $Signtool verify /pa $Exe
Write-Host "Signed ok."
