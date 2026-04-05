$ErrorActionPreference = 'Stop'

Write-Host "#########################################################"
Write-Host "### Start 20"
Write-Host "#########################################################"

# Avoid mojibake in logs (Runner writes UTF-8 timestamps)
try { [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new() } catch {}

. "$PSScriptRoot\..\lib\downloads.ps1"

Write-Host "Installing Virtual Display Driver (VDD)..."

# --- Idempotency check: skip if VDD already installed ---
try {
  $existing = Get-PnpDevice -PresentOnly -ErrorAction SilentlyContinue |
    Where-Object { $_.InstanceId -like 'ROOT\\MTTVDD*' -or $_.FriendlyName -match 'Virtual Display|VDD|MttVDD' }

  if ($existing) {
    Write-Host "VDD already installed. Skipping installation."

    Write-Host "---------------------------------------------------------"
    Write-Host "END 20 - early exit"
    Write-Host "---------------------------------------------------------"
    Write-Host ""

    return
  }
} catch {
  Write-Host "Could not verify existing VDD installation. Continuing..."
}

# --- Download VDD Control ZIP (GUI tool for later manual inspection/troubleshooting) ---
try { [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12 } catch {}
$headers = @{ "User-Agent"="Mozilla/5.0"; "Accept"="application/vnd.github+json" }
$api = "https://api.github.com/repos/VirtualDrivers/Virtual-Display-Driver/releases/latest"

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

$controlAsset = $release.assets |
  Where-Object { $_.name -match '^VDD\.Control\..*\.zip$' } |
  Select-Object -First 1

if (-not $controlAsset) {
  throw "Could not find VDD.Control ZIP in latest release. Assets: $($release.assets.name -join ', ')"
}

$controlZipPath = "C:\Users\Administrator\provision\downloads\vdd\$($controlAsset.name)"
$controlExtractPath = "C:\Users\Administrator\provision\downloads\vdd\control"
Write-Host "Downloading VDD Control: $($controlAsset.name)"
Download-File -Url $controlAsset.browser_download_url -OutFile $controlZipPath -SkipIfExists
if (Test-Path $controlExtractPath) { Remove-Item $controlExtractPath -Recurse -Force }
New-Item -ItemType Directory -Path $controlExtractPath | Out-Null
Expand-Archive -Path $controlZipPath -DestinationPath $controlExtractPath -Force


# --- Download full Virtual-Display-Driver repository archive ---
$repoZipPath = "C:\Users\Administrator\provision\downloads\vdd\Virtual-Display-Driver-master.zip"
$repoExtractPath = "C:\Users\Administrator\provision\downloads\vdd\repo"
$repoUrl = "https://github.com/VirtualDrivers/Virtual-Display-Driver/archive/refs/heads/master.zip"

Write-Host "Downloading Virtual-Display-Driver repository archive..."
Download-File -Url $repoUrl -OutFile $repoZipPath -SkipIfExists

if (Test-Path $repoExtractPath) {
  Remove-Item -Recurse -Force $repoExtractPath
}
New-Item -ItemType Directory -Path $repoExtractPath -Force | Out-Null
Expand-Archive -Path $repoZipPath -DestinationPath $repoExtractPath -Force

$scriptPath = Get-ChildItem -Path $repoExtractPath -Recurse -Filter "silent-install.ps1" |
  Where-Object { $_.FullName -match "Community Scripts" } |
  Select-Object -First 1 -ExpandProperty FullName

if (-not $scriptPath) {
  throw "Could not find Community Scripts\\silent-install.ps1 in extracted repository archive."
}

# --- Execute script ---
Write-Host "Executing silent install script from repository archive..."
& $scriptPath

Start-Sleep -Seconds 5
$rebootFlag = "C:\Users\Administrator\provision\state\reboot.flag"
$changed = $false

# --- Verify installation ---
try {
  $installed = Get-PnpDevice -PresentOnly -ErrorAction SilentlyContinue |
    Where-Object { $_.InstanceId -like 'ROOT\\MTTVDD*' -or $_.FriendlyName -match 'Virtual Display|VDD|MttVDD' }

  if ($installed) {
    Write-Host "VDD installation successful."
    $changed = $true
  } else {
    Write-Host "WARNING: VDD installation could not be verified."
  }
} catch {
  Write-Host "WARNING: Could not verify VDD installation."
}

if ($changed) {
  Write-Host "VDD installation requires reboot. Requesting reboot..."
  New-Item $rebootFlag -ItemType File -Force | Out-Null
} else {
  Write-Host "No reboot required."
}

Write-Host "VDD setup complete."

Write-Host "---------------------------------------------------------"
Write-Host "END 20"
Write-Host "---------------------------------------------------------"
Write-Host ""
