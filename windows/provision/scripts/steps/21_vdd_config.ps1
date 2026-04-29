$ErrorActionPreference = 'Stop'

Write-Host "#########################################################"
Write-Host "### Start 21"
Write-Host "#########################################################"

. "$PSScriptRoot\..\lib\downloads.ps1"

$settingsDir = 'C:\VirtualDisplayDriver'
$settingsPath = "$settingsDir\vdd_settings.xml"
$templatePath = Join-Path $PSScriptRoot '..\templates\vdd_settings.xml'
$rebootFlag = 'C:\Users\Administrator\provision\state\reboot.flag'
$envFile = 'C:\Users\Administrator\provision\state\env.json'

$alreadyInstalled = $false
$changed = $false

# === Resolution config from env.json ===========================================
$DefaultDisplayResolution = '1920x1080'
if (Test-Path -LiteralPath $envFile) {
  $envData = Get-Content -LiteralPath $envFile -Raw | ConvertFrom-Json
  if ($envData.display_resolution) { $DefaultDisplayResolution = [string]$envData.display_resolution }
}

# Baseline list — 10 modes that Sunshine/Moonlight clients commonly request.
# Global refresh rates (30/60/120) below apply to all of them; the configured
# default is added if it falls outside the baseline.
$BaselineResolutions = @(
  '5120x1440',
  '4096x1152',
  '3008x846',
  '2560x1440',
  '2560x720',
  '1920x1080',
  '1680x1050',
  '1440x900',
  '1280x800',
  '1024x640'
)
$GlobalRefreshRates = @(30, 60, 120)
$PerResolutionRate = 60

$resolutions = New-Object System.Collections.Generic.List[object]
$seenRes = @{}
foreach ($r in (@($BaselineResolutions) + @($DefaultDisplayResolution))) {
  if ($seenRes.ContainsKey($r)) { continue }
  $seenRes[$r] = $true
  $parts = $r -split 'x'
  if ($parts.Count -ne 2) {
    Write-Host "WARNING: ignoring malformed resolution '$r' (expected WxH)"
    continue
  }
  $resolutions.Add(@{ Width = [int]$parts[0]; Height = [int]$parts[1] })
}

# === Install VDD if missing ====================================================
Write-Host "Installing Virtual Display Driver (VDD)..."

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
  try { [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12 } catch {}
  $headers = @{ "User-Agent" = "Mozilla/5.0"; "Accept" = "application/vnd.github+json" }
  $api = "https://api.github.com/repos/VirtualDrivers/Virtual-Display-Driver/releases/latest"

  $release = $null
  for ($i = 1; $i -le 5; $i++) {
    try { $release = Invoke-RestMethod -Uri $api -Headers $headers; break } catch {
      if ($i -eq 5) { throw }
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
      $changed = $true
    } else {
      Write-Host "WARNING: VDD installation could not be verified."
    }
  } catch {
    Write-Host "WARNING: Could not verify VDD installation."
  }
}

# === Render vdd_settings.xml from template =====================================
if (-not (Test-Path -LiteralPath $templatePath)) {
  throw "VDD settings template missing at $templatePath"
}

[xml]$xml = Get-Content -LiteralPath $templatePath -Raw

$globalNode = $xml.vdd_settings.global
foreach ($child in @($globalNode.ChildNodes)) { [void]$globalNode.RemoveChild($child) }
foreach ($rate in $GlobalRefreshRates) {
  $n = $xml.CreateElement('g_refresh_rate')
  $n.InnerText = [string]$rate
  [void]$globalNode.AppendChild($n)
}

$resolutionsNode = $xml.vdd_settings.resolutions
foreach ($child in @($resolutionsNode.ChildNodes)) { [void]$resolutionsNode.RemoveChild($child) }
foreach ($res in $resolutions) {
  $rNode = $xml.CreateElement('resolution')
  $w = $xml.CreateElement('width');        $w.InnerText  = [string]$res.Width;  [void]$rNode.AppendChild($w)
  $h = $xml.CreateElement('height');       $h.InnerText  = [string]$res.Height; [void]$rNode.AppendChild($h)
  $rr = $xml.CreateElement('refresh_rate'); $rr.InnerText = [string]$PerResolutionRate; [void]$rNode.AppendChild($rr)
  [void]$resolutionsNode.AppendChild($rNode)
}

$sw = New-Object System.IO.StringWriter
$writerSettings = New-Object System.Xml.XmlWriterSettings
$writerSettings.Indent = $true
$writerSettings.IndentChars = '    '
$writerSettings.OmitXmlDeclaration = $false
$writer = [System.Xml.XmlWriter]::Create($sw, $writerSettings)
$xml.Save($writer)
$writer.Close()
$desiredContent = $sw.ToString()

if (-not (Test-Path -LiteralPath $settingsDir)) {
  New-Item -ItemType Directory -Path $settingsDir -Force | Out-Null
}

$existingContent = $null
if (Test-Path -LiteralPath $settingsPath) {
  $existingContent = Get-Content -LiteralPath $settingsPath -Raw
}

if ($existingContent -ne $desiredContent) {
  Write-Host "Writing $settingsPath ($(($resolutions | Measure-Object).Count) resolutions, refresh rates: $($GlobalRefreshRates -join ', '))"
  Set-Content -LiteralPath $settingsPath -Value $desiredContent -Encoding utf8 -NoNewline
  $changed = $true
} else {
  Write-Host "$settingsPath already matches desired settings."
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
