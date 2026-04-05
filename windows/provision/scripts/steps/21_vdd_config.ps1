$ErrorActionPreference = 'Stop'

Write-Host "#########################################################"
Write-Host "### Start 21"
Write-Host "#########################################################"

. "$PSScriptRoot\..\lib\downloads.ps1"

# Add only these custom resolutions if they are not already present.
# Do not overwrite existing entries.
$DesiredVddResolutions = @(
  @{ Width = 5120; Height = 1440; RefreshRate = 120 }
)

$settingsPath = 'C:\VirtualDisplayDriver\vdd_settings.xml'
$rebootFlag = 'C:\Users\Administrator\provision\state\reboot.flag'
$alreadyInstalled = $false
$changed = $false

Write-Host "Installing Virtual Display Driver (VDD)..."

function Add-VddResolutionIfMissing {
  param(
    [Parameter(Mandatory = $true)]
    [string]$SettingsPath,

    [Parameter(Mandatory = $true)]
    [int]$Width,

    [Parameter(Mandatory = $true)]
    [int]$Height,

    [Parameter(Mandatory = $true)]
    [int]$RefreshRate
  )

  if (-not (Test-Path -LiteralPath $SettingsPath)) {
    Write-Host "VDD settings file not found at $SettingsPath. Skipping custom resolution injection."
    return $false
  }

  [xml]$xml = Get-Content -LiteralPath $SettingsPath -Raw

  if (-not $xml.vdd_settings) {
    throw "Unexpected VDD settings format: missing <vdd_settings> root element."
  }

  $root = $xml.vdd_settings
  $resolutionsNode = $root.resolutions
  if (-not $resolutionsNode) {
    $resolutionsNode = $xml.CreateElement('resolutions')
    [void]$root.AppendChild($resolutionsNode)
  }

  $existing = @($resolutionsNode.resolution) | Where-Object {
    [int]$_.width -eq $Width -and
    [int]$_.height -eq $Height -and
    [int]$_.refresh_rate -eq $RefreshRate
  }

  if ($existing.Count -gt 0) {
    Write-Host "VDD resolution ${Width}x${Height}@${RefreshRate} already present. Leaving settings unchanged."
    return $false
  }

  $resolutionNode = $xml.CreateElement('resolution')

  $widthNode = $xml.CreateElement('width')
  $widthNode.InnerText = [string]$Width
  [void]$resolutionNode.AppendChild($widthNode)

  $heightNode = $xml.CreateElement('height')
  $heightNode.InnerText = [string]$Height
  [void]$resolutionNode.AppendChild($heightNode)

  $refreshNode = $xml.CreateElement('refresh_rate')
  $refreshNode.InnerText = [string]$RefreshRate
  [void]$resolutionNode.AppendChild($refreshNode)

  [void]$resolutionsNode.AppendChild($resolutionNode)
  $xml.Save($SettingsPath)

  Write-Host "Added VDD resolution ${Width}x${Height}@${RefreshRate} to $SettingsPath"
  return $true
}

function Add-DesiredVddResolutions {
  param(
    [Parameter(Mandatory = $true)]
    [string]$SettingsPath,

    [Parameter(Mandatory = $true)]
    [object[]]$DesiredResolutions
  )

  $updated = $false

  foreach ($resolution in $DesiredResolutions) {
    $added = Add-VddResolutionIfMissing `
      -SettingsPath $SettingsPath `
      -Width ([int]$resolution.Width) `
      -Height ([int]$resolution.Height) `
      -RefreshRate ([int]$resolution.RefreshRate)

    if ($added) {
      $updated = $true
    }
  }

  return $updated
}

# --- Idempotency check: skip install if VDD already installed, but still ensure desired resolutions exist ---
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

if (-not $alreadyInstalled) {
  # --- Download VDD Control ZIP (GUI tool for later manual inspection/troubleshooting) ---
  try { [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12 } catch {}
  $headers = @{ "User-Agent" = "Mozilla/5.0"; "Accept" = "application/vnd.github+json" }
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

  $scriptPath = Get-ChildItem -Path $repoExtractPath -Recurse -Filter 'silent-install.ps1' |
    Where-Object { $_.FullName -match 'Community Scripts' } |
    Select-Object -First 1 -ExpandProperty FullName

  if (-not $scriptPath) {
    throw "Could not find Community Scripts\\silent-install.ps1 in extracted repository archive."
  }

  # --- Execute script ---
  Write-Host "Executing silent install script from repository archive..."
  & $scriptPath

  Start-Sleep -Seconds 5

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
}

# --- Add desired resolutions without overwriting any existing entries ---
try {
  $settingsChanged = Add-DesiredVddResolutions -SettingsPath $settingsPath -DesiredResolutions $DesiredVddResolutions
  if ($settingsChanged) {
    Write-Host 'VDD settings were updated with additional custom resolutions.'
    $changed = $true
  } else {
    Write-Host 'No custom resolution changes were necessary.'
  }
} catch {
  Write-Host "WARNING: Failed to update VDD settings: $($_.Exception.Message)"
}

if ($changed) {
  Write-Host 'VDD installation/settings change requires reboot. Requesting reboot...'
  New-Item $rebootFlag -ItemType File -Force | Out-Null
} else {
  Write-Host 'No reboot required.'
}

Write-Host 'VDD setup complete.'

Write-Host "---------------------------------------------------------"
Write-Host "END 21"
Write-Host "---------------------------------------------------------"
Write-Host ""
