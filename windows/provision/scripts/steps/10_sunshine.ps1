$ErrorActionPreference = 'Stop'

. "$PSScriptRoot\..\lib\downloads.ps1"

Write-Host "Installing Sunshine..."

$sunshineDir = "${env:ProgramFiles}\Sunshine"
if (Test-Path $sunshineDir) {
  Write-Host "Sunshine already installed at $sunshineDir. Skipping."
  exit
}

# Resolve latest Windows installer asset via GitHub API
$headers = @{ "User-Agent"="Mozilla/5.0"; "Accept"="application/vnd.github+json" }
$api = "https://api.github.com/repos/LizardByte/Sunshine/releases/latest"

$release = $null
for ($i = 1; $i -le 5; $i++) {
  try {
    $release = Invoke-RestMethod -Uri $api -Headers $headers
    break
  } catch {
    if ($i -eq 5) { throw }
    Start-Sleep -Seconds 2
  }
}

# Prefer the canonical Windows installer asset name used by Sunshine releases
$asset = $release.assets | Where-Object { $_.name -eq "Sunshine-Windows-AMD64-installer.exe" } | Select-Object -First 1

# Fallback (if naming changes slightly in the future)
if (-not $asset) {
  $asset = $release.assets | Where-Object { $_.name -match "^Sunshine-Windows-.*-installer\.exe$" } | Select-Object -First 1
}

if (-not $asset) {
  throw "Could not find a Windows installer asset in the latest Sunshine release. Assets: $($release.assets.name -join ', ')"
}

$url  = $asset.browser_download_url
$file = "C:\Users\Administrator\provision\downloads\sunshine\Sunshine-Windows-AMD64-installer.exe"

Write-Host "Downloading: $($asset.name)"
Download-File -Url $url -OutFile $file -SkipIfExists
Unblock-File $file -ErrorAction SilentlyContinue

Write-Host "Running Sunshine installer (silent)..."
$proc = Start-Process -FilePath $file -ArgumentList "/S" -Wait -PassThru
Write-Host "Sunshine installer exit code: $($proc.ExitCode)"

# Optionally set Sunshine Web UI credentials from the environment.
# Use a fixed username to keep provisioning simple and reproducible.
$sunshineExe = Join-Path $sunshineDir "sunshine.exe"
if ($env:EPHEMERAL_SUNSHINE_PASSWORD) {
  if (!(Test-Path $sunshineExe)) {
    throw "Sunshine executable not found at $sunshineExe"
  }

  Write-Host "Setting Sunshine credentials..."
  $credsProc = Start-Process -FilePath $sunshineExe -ArgumentList "--creds", "sunshine", $env:EPHEMERAL_SUNSHINE_PASSWORD -Wait -PassThru
  Write-Host "Sunshine credentials exit code: $($credsProc.ExitCode)"
}

# Optionally open Sunshine's web UI for initial configuration.
# Sunshine typically listens on https://localhost:47990 (self-signed cert).
if (-not $env:EPHEMERAL_SUNSHINE_PASSWORD -and $env:EPHEMERAL_OPEN_SUNSHINE_UI -ne "0") {
  Start-Sleep -Seconds 3
  try {
    Start-Process "https://localhost:47990"
  } catch {
    Write-Host "Could not open browser automatically. Please open https://localhost:47990 manually."
  }
}
