$ErrorActionPreference = 'Stop'

Write-Host "#########################################################"
Write-Host "### Start 20"
Write-Host "#########################################################"

. "$PSScriptRoot\..\lib\downloads.ps1"

$rebootFlag = 'C:\Users\Administrator\provision\state\reboot.flag'

$alreadyInstalled = $false

# === Check existing VDD installation ==========================================
Write-Host "Checking Virtual Display Driver (VDD)..."

try {
  $existing = Get-PnpDevice -PresentOnly -ErrorAction SilentlyContinue |
    Where-Object { $_.InstanceId -like 'ROOT\\MTTVDD*' -or $_.FriendlyName -match 'Virtual Display|VDD|MttVDD' }
  if ($existing) {
    Write-Host "VDD already installed. Skipping installation step."
    $alreadyInstalled = $true
  }
} catch {
  Write-Host "Could not verify existing VDD installation. Continuing..."
}

# === Download VDD Control =====================================================
try { [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12 } catch {}
$headers = @{ "User-Agent" = "Mozilla/5.0"; "Accept" = "application/vnd.github+json" }
$api = "https://api.github.com/repos/VirtualDrivers/Virtual-Display-Driver/releases/latest"

$release = $null
for ($i = 1; $i -le 5; $i++) {
  try { $release = Invoke-RestMethod -Uri $api -Headers $headers; break } catch {
    if ($i -eq 5) { throw "Failed to fetch VDD releases from GitHub API after 5 attempts: $_" }
    Start-Sleep -Seconds 2
  }
}

$controlAsset = $release.assets | Where-Object { $_.name -match '^VDD\.Control\..*\.zip$' } | Select-Object -First 1
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

# === Install VDD driver if missing ============================================
if (-not $alreadyInstalled) {
  $repoZipPath = "C:\Users\Administrator\provision\downloads\vdd\Virtual-Display-Driver-master.zip"
  $repoExtractPath = "C:\Users\Administrator\provision\downloads\vdd\repo"
  $repoUrl = "https://github.com/VirtualDrivers/Virtual-Display-Driver/archive/refs/heads/master.zip"

  Write-Host "Downloading Virtual-Display-Driver repository archive..."
  Download-File -Url $repoUrl -OutFile $repoZipPath -SkipIfExists

  if (Test-Path $repoExtractPath) { Remove-Item -Recurse -Force $repoExtractPath }
  New-Item -ItemType Directory -Path $repoExtractPath -Force | Out-Null
  Expand-Archive -Path $repoZipPath -DestinationPath $repoExtractPath -Force

  $scriptPath = Get-ChildItem -Path $repoExtractPath -Recurse -Filter 'silent-install.ps1' |
    Where-Object { $_.FullName -match 'Community Scripts' } |
    Select-Object -First 1 -ExpandProperty FullName
  if (-not $scriptPath) {
    throw "Could not find Community Scripts\\silent-install.ps1 in extracted repository archive."
  }

  Write-Host "Executing silent install script from repository archive..."
  & $scriptPath
  Start-Sleep -Seconds 5

  try {
    $installed = Get-PnpDevice -PresentOnly -ErrorAction SilentlyContinue |
      Where-Object { $_.InstanceId -like 'ROOT\\MTTVDD*' -or $_.FriendlyName -match 'Virtual Display|VDD|MttVDD' }
    if ($installed) {
      Write-Host "VDD installation successful."
      New-Item $rebootFlag -ItemType File -Force | Out-Null
    } else {
      Write-Host "WARNING: VDD installation could not be verified."
    }
  } catch {
    Write-Host "WARNING: Could not verify VDD installation."
  }
}

# === Install VDD Control GUI to permanent location + desktop shortcut =========
$controlInstallDir = 'C:\Program Files\VDD Control'
$controlExe = Join-Path $controlInstallDir 'VDD Control.exe'
$controlSourceExe = Join-Path $controlExtractPath 'VDD Control.exe'

if (-not (Test-Path -LiteralPath $controlSourceExe)) {
  Write-Host "WARNING: VDD Control.exe missing from extracted ZIP at $controlExtractPath"
} else {
  $sourceSize = (Get-Item -LiteralPath $controlSourceExe).Length
  $needsInstall = $true
  if (Test-Path -LiteralPath $controlExe) {
    $installedSize = (Get-Item -LiteralPath $controlExe).Length
    if ($installedSize -eq $sourceSize) { $needsInstall = $false }
  }
  if ($needsInstall) {
    Write-Host "Installing VDD Control to $controlInstallDir"
    if (Test-Path -LiteralPath $controlInstallDir) { Remove-Item -LiteralPath $controlInstallDir -Recurse -Force }
    New-Item -ItemType Directory -Path $controlInstallDir -Force | Out-Null
    Copy-Item -Path (Join-Path $controlExtractPath '*') -Destination $controlInstallDir -Recurse -Force
  } else {
    Write-Host "VDD Control already installed at $controlInstallDir (matching size)."
  }

  $shortcutPath = 'C:\Users\Public\Desktop\VDD Control.lnk'
  if (-not (Test-Path -LiteralPath $shortcutPath)) {
    Write-Host "Creating desktop shortcut: $shortcutPath"
    $shell = New-Object -ComObject WScript.Shell
    $sc = $shell.CreateShortcut($shortcutPath)
    $sc.TargetPath = $controlExe
    $sc.WorkingDirectory = $controlInstallDir
    $sc.Description = 'Virtual Display Driver Control'
    $sc.Save()
  }
}

Write-Host "---------------------------------------------------------"
Write-Host "END 20"
Write-Host "---------------------------------------------------------"
Write-Host ""
