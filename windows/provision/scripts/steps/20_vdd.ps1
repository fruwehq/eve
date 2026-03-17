$ErrorActionPreference = 'Stop'

# Avoid mojibake in logs (Runner writes UTF-8 timestamps)
try { [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new() } catch {}

. "$PSScriptRoot\..\lib\downloads.ps1"

Write-Host "Installing Virtual Display Driver (VDD) (driver-only)..."

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

Write-Host "Launching VDD Control to install drivers..."
Start-Process -FilePath $exe.FullName -ArgumentList "/install" -Wait -PassThru | Out-Null

Start-Sleep -Seconds 5

Write-Host "Verifying VDD driver package (best-effort)..."
pnputil.exe /enum-drivers | Select-String -Pattern "MttVDD|VirtualDisplay|Indirect" | ForEach-Object { $_.Line }

Write-Host "Verifying device presence (best-effort)..."
Get-PnpDevice -PresentOnly -ErrorAction SilentlyContinue |
  Where-Object { $_.InstanceId -like 'ROOT\\MTTVDD*' -or $_.FriendlyName -match 'Virtual Display|VDD|MttVDD' } |
  Select-Object Status, Class, FriendlyName, InstanceId

# 4) Ensure vdd_settings.xml contains 5120x1440@60
# VDD reads settings from: C:\VirtualDisplayDriver\vdd_settings.xml
# (README mentions this default location)
$settingsDir = "C:\VirtualDisplayDriver"
$settingsPath = Join-Path $settingsDir "vdd_settings.xml"

if (-not (Test-Path $settingsDir)) { New-Item -ItemType Directory -Path $settingsDir | Out-Null }

# Detect the primary GPU name (fallback to NVIDIA if detection fails)
$gpuName = (Get-CimInstance Win32_VideoController | Select-Object -First 1 -ExpandProperty Name)
if (-not $gpuName) { $gpuName = "NVIDIA" }

# If the file does not exist, create a minimal valid config.
# If it exists, only add the 5120x1440 entry if missing.
if (-not (Test-Path $settingsPath)) {
  $xml = @" 
<?xml version="1.0" encoding="UTF-8"?>
<vdd_settings>
  <monitors>
    <count>1</count>
  </monitors>
  <gpu>
    <friendlyname>$gpuName</friendlyname>
  </gpu>
  <global>
    <!--These are global refreshrates, any you add in here, will be replicated to all resolutions-->
    <g_refresh_rate>60</g_refresh_rate>
  </global>
  <resolutions>
    <resolution>
      <width>5120</width>
      <height>1440</height>
      <refresh_rate>60</refresh_rate>
    </resolution>
  </resolutions>
  <options>
    <CustomEdid>false</CustomEdid>
    <PreventSpoof>false</PreventSpoof>
    <EdidCeaOverride>false</EdidCeaOverride>
    <HardwareCursor>true</HardwareCursor>
    <SDR10bit>false</SDR10bit>
    <HDRPlus>false</HDRPlus>
    <logging>false</logging>
    <debuglogging>false</debuglogging>
  </options>
</vdd_settings>
"@
  Set-Content -Path $settingsPath -Value $xml -Encoding UTF8
  Write-Host "Created $settingsPath with 5120x1440@60."
} else {
  [xml]$doc = Get-Content $settingsPath

  # Ensure GPU friendly name is present
  if (-not $doc.vdd_settings.gpu) {
    $gpuNode = $doc.CreateElement('gpu')
    $fn = $doc.CreateElement('friendlyname')
    $fn.InnerText = $gpuName
    $gpuNode.AppendChild($fn) | Out-Null
    $doc.vdd_settings.AppendChild($gpuNode) | Out-Null
  } elseif (-not $doc.vdd_settings.gpu.friendlyname) {
    $fn = $doc.CreateElement('friendlyname')
    $fn.InnerText = $gpuName
    $doc.vdd_settings.gpu.AppendChild($fn) | Out-Null
  }

  if (-not $doc.vdd_settings.resolutions) {
    $resNode = $doc.CreateElement('resolutions')
    $doc.vdd_settings.AppendChild($resNode) | Out-Null
  }

  $exists = $false
  foreach ($r in $doc.vdd_settings.resolutions.resolution) {
    if ($r.width -eq '5120' -and $r.height -eq '1440') { $exists = $true; break }
  }

  if (-not $exists) {
    $r = $doc.CreateElement('resolution')
    $w = $doc.CreateElement('width'); $w.InnerText = '5120'
    $h = $doc.CreateElement('height'); $h.InnerText = '1440'
    $rr = $doc.CreateElement('refresh_rate'); $rr.InnerText = '60'
    $r.AppendChild($w) | Out-Null
    $r.AppendChild($h) | Out-Null
    $r.AppendChild($rr) | Out-Null
    $doc.vdd_settings.resolutions.AppendChild($r) | Out-Null

    $doc.Save($settingsPath)
    Write-Host "Added 5120x1440@60 to $settingsPath."
  } else {
    Write-Host "5120x1440 already present in $settingsPath."
  }
}

# 5) Reboot is usually a good idea after display driver installation
Write-Host "Requesting reboot..."
New-Item "C:\Users\Administrator\provision\state\reboot.flag" -ItemType File -Force | Out-Null
