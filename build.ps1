<#
Builds the release: dist\BloodHuntAFK\ (the exes, settings.py, the README, the profiles) and
dist\BloodHuntAFK-<version>.zip. Run it from this folder:

    powershell -ExecutionPolicy Bypass -File build.ps1              (version from git: the tag, or the commit)
    powershell -ExecutionPolicy Bypass -File build.ps1 -Version v1.0
    powershell -ExecutionPolicy Bypass -File build.ps1 -NoAdmin     (test build: the exes don't ask for admin)

It installs the requirements and PyInstaller into .venv (made if missing). Only these go in the zip:
settings.py, README.md, and each profile's profile.json and templates\ (NAME.png + NAME.json).
Never shots\, routines\, debug\ or bot.log: those show your in-game UID.
GitHub Actions runs this same script for releases (.github\workflows\release.yml).
#>
param([string]$Version = "", [switch]$NoAdmin)

Set-Location $PSScriptRoot
$py = ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) {
    python -m venv .venv
    if ($LASTEXITCODE) { throw "Couldn't make .venv (is Python installed?)" }
}
& $py -m pip install --disable-pip-version-check -q -r requirements.txt -r requirements-build.txt
if ($LASTEXITCODE) { throw "pip install failed" }

if (-not $Version) {
    $Version = git describe --tags --always --dirty 2>$null
    if ($LASTEXITCODE -or -not $Version) { $Version = "dev" }
}
$env:BLOODHUNT_NO_ADMIN = if ($NoAdmin) { "1" } else { "0" }

& $py -m PyInstaller --noconfirm --clean --log-level WARN BloodHuntAFK.spec
if ($LASTEXITCODE) { throw "PyInstaller failed" }

$out = "dist\BloodHuntAFK"
Copy-Item bloodhunt\settings.py "$out\settings.py" -ErrorAction Stop
Copy-Item README.md $out -ErrorAction Stop
foreach ($p in Get-ChildItem profiles -Directory) {
    if (-not (Test-Path "$($p.FullName)\profile.json")) { continue }
    $dst = "$out\profiles\$($p.Name)"
    New-Item -ItemType Directory -Force "$dst\templates" | Out-Null
    Copy-Item "$($p.FullName)\profile.json" $dst -ErrorAction Stop
    Get-ChildItem "$($p.FullName)\templates" -File -Include *.png, *.json -Recurse |
        Copy-Item -Destination "$dst\templates" -ErrorAction Stop
}

$zip = "dist\BloodHuntAFK-$Version.zip"
# Antivirus often scans the new files right after PyInstaller writes them, which locks them for a moment.
for ($try = 1; ; $try++) {
    if (Test-Path $zip) { Remove-Item $zip -ErrorAction Stop }
    try {
        Compress-Archive -Path $out -DestinationPath $zip -ErrorAction Stop
        break
    } catch {
        if ($try -ge 10) { throw }
        Write-Host "A file is still in use (antivirus scan?) - trying again in 3 s"
        Start-Sleep -Seconds 3
    }
}
Write-Host "Built $out and $zip"
