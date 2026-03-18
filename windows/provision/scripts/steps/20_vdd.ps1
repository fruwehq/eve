$ErrorActionPreference = 'Stop'

# Avoid mojibake in logs (Runner writes UTF-8 timestamps)
try { [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new() } catch {}

. "$PSScriptRoot\..\lib\downloads.ps1"


Write-Host "Installing Virtual Display Driver (VDD) (driver-only)..."

# --- Idempotency check: skip if VDD already installed ---
try {
  $existing = Get-PnpDevice -PresentOnly -ErrorAction SilentlyContinue |
    Where-Object { $_.InstanceId -like 'ROOT\\MTTVDD*' -or $_.FriendlyName -match 'Virtual Display|VDD|MttVDD' }

  if ($existing) {
    Write-Host "VDD already installed. Skipping installation."
    return
  }
} catch {
  Write-Host "Could not verify existing VDD installation. Continuing..."
}

# 1) Resolve latest release + find VDD.Control ZIP
try { [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12 } catch {}
$headers = @{ "User-Agent"="Mozilla/5.0"; "Accept"="application/vnd.github+json" }
$api = "https://api.github.com/repos/VirtualDrivers/Virtual-Display-Driver/releases/latest"

$release = $null
for ($i = 1; $i -le 5; $i++) {
  try { $release = Invoke-RestMethod -Uri $api -Headers $headers; break } catch {
    if ($i -eq 5) { throw }
    Start-Sleep -Seconds 2
  }
}

$asset = $release.assets |
  Where-Object { $_.name -match '^VDD\.Control\..*\.zip$' } |
  Select-Object -First 1

if (-not $asset) {
  throw "Could not find VDD.Control ZIP in latest release. Assets: $($release.assets.name -join ', ')"
}

$zipUrl  = $asset.browser_download_url
$zipPath = "C:\Users\Administrator\provision\downloads\vdd\vdd-control.zip"
$extract = "C:\Users\Administrator\provision\downloads\vdd\control"

Write-Host "Downloading VDD Control: $($asset.name)"
Download-File -Url $zipUrl -OutFile $zipPath -SkipIfExists

# 2) Extract
if (Test-Path $extract) { Remove-Item $extract -Recurse -Force }
New-Item -ItemType Directory -Path $extract | Out-Null
Expand-Archive -Path $zipPath -DestinationPath $extract -Force

# 3) Run VDD Control (installs drivers + panel)
$exe = Get-ChildItem -Path $extract -Recurse -Filter "VDD Control.exe" | Select-Object -First 1
if (-not $exe) {
  throw "VDD Control.exe not found in extracted archive"
}
