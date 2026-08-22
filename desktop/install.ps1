# install lazycatter for the current user and make desktop + start menu shortcuts
# expects a built app at dist/LazyCatter (from scripts/build-windows.ps1)
# run:
#   powershell -ExecutionPolicy Bypass -File desktop/install.ps1

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Built = Join-Path $Root "dist\LazyCatter"
$ExeName = "LazyCatter.exe"

if (-not (Test-Path (Join-Path $Built $ExeName))) {
    Write-Error "Built app not found at $Built\$ExeName. Run scripts/build-windows.ps1 first."
}

$InstallDir = Join-Path $env:LOCALAPPDATA "LazyCatter"
Write-Host "Installing to $InstallDir ..."

if (Test-Path $InstallDir) {
    Get-Process -Name "LazyCatter" -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
    Start-Sleep -Milliseconds 400
    Remove-Item $InstallDir -Recurse -Force
}

New-Item -ItemType Directory -Path $InstallDir -Force | Out-Null
Copy-Item -Path (Join-Path $Built "*") -Destination $InstallDir -Recurse -Force

$Target = Join-Path $InstallDir $ExeName

function New-AppShortcut {
    param(
        [string]$ShortcutPath,
        [string]$TargetPath,
        [string]$WorkingDir,
        [string]$Description = "LazyCatter Discord server plan importer"
    )
    $shell = New-Object -ComObject WScript.Shell
    $sc = $shell.CreateShortcut($ShortcutPath)
    $sc.TargetPath = $TargetPath
    $sc.WorkingDirectory = $WorkingDir
    $sc.WindowStyle = 1
    $sc.Description = $Description
    $sc.Save()
}

$Desktop = [Environment]::GetFolderPath("Desktop")
$StartMenu = Join-Path ([Environment]::GetFolderPath("StartMenu")) "Programs\LazyCatter"
New-Item -ItemType Directory -Path $StartMenu -Force | Out-Null

New-AppShortcut -ShortcutPath (Join-Path $Desktop "LazyCatter.lnk") -TargetPath $Target -WorkingDir $InstallDir
New-AppShortcut -ShortcutPath (Join-Path $StartMenu "LazyCatter.lnk") -TargetPath $Target -WorkingDir $InstallDir

$Uninstall = Join-Path $InstallDir "Uninstall-LazyCatter.ps1"
$uninstallBody = @"
`$ErrorActionPreference = 'Stop'
Get-Process -Name 'LazyCatter' -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Remove-Item '$(Join-Path $Desktop "LazyCatter.lnk")' -Force -ErrorAction SilentlyContinue
Remove-Item '$StartMenu' -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item '$InstallDir' -Recurse -Force
Write-Host 'LazyCatter removed.'
"@
Set-Content -Path $Uninstall -Value $uninstallBody -Encoding UTF8

$shell = New-Object -ComObject WScript.Shell
$usc = $shell.CreateShortcut((Join-Path $StartMenu "Uninstall LazyCatter.lnk"))
$usc.TargetPath = "powershell.exe"
$usc.Arguments = "-ExecutionPolicy Bypass -File `"$Uninstall`""
$usc.WorkingDirectory = $InstallDir
$usc.Description = "Remove LazyCatter"
$usc.Save()

Write-Host ""
Write-Host "Installed."
Write-Host "Desktop shortcut: $(Join-Path $Desktop 'LazyCatter.lnk')"
Write-Host "App folder:       $InstallDir"
Write-Host "Double-click LazyCatter on your desktop to open the UI."
