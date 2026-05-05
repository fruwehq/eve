$ErrorActionPreference = 'Stop'

Write-Host "#########################################################"
Write-Host "### Start 31"
Write-Host "#########################################################"

. "$PSScriptRoot\..\lib\downloads.ps1"
. "$PSScriptRoot\..\lib\sunshine.ps1"

# Sunshine needs a virtual audio sink to stream audio from a headless
# Windows VM. Sunshine's default is "Steam Streaming Speakers" but that
# .inf only ships inside a fully-bootstrapped Steam install, which couples
# audio to Steam being present and updated.
#
# We use VB-CABLE instead: signed by VB-Audio (no test signing needed),
# small (~1 MB), and independent of Steam. After installing the driver we
# set Sunshine's virtual_sink to the VB-CABLE playback device and disable
# Sunshine's Steam-driver auto-install path.

$cableZipUrl   = 'https://download.vb-audio.com/Download_CABLE/VBCABLE_Driver_Pack45.zip'
$downloadDir   = 'C:\Users\Administrator\provision\downloads\vb-cable'
$cableZipPath  = Join-Path $downloadDir 'VBCABLE_Driver_Pack45.zip'
$cableExtract  = Join-Path $downloadDir 'extracted'

$sunshineConf  = 'C:\Program Files\Sunshine\config\sunshine.conf'
$cableSinkName = 'CABLE Input (VB-Audio Virtual Cable)'

function Find-CableDevice {
  Get-PnpDevice -PresentOnly -ErrorAction SilentlyContinue |
    Where-Object { $_.FriendlyName -eq 'CABLE Input (VB-Audio Virtual Cable)' } |
    Select-Object -First 1
}

function Set-SunshineConfigEntry {
  param([string]$Path, [string]$Key, [string]$Value)

  $line     = "$Key = $Value"
  $existing = if (Test-Path $Path) { @(Get-Content -LiteralPath $Path) } else { @() }
  $hit      = $false
  $updated  = foreach ($l in $existing) {
    if ($l -match "^\s*$([regex]::Escape($Key))\s*=") {
      $hit = $true
      $line
    } else {
      $l
    }
  }
  if (-not $hit) {
    $updated = @($updated) + $line
  }
  Set-Content -LiteralPath $Path -Value (($updated -join "`r`n") + "`r`n") -NoNewline -Encoding ASCII
}

$device          = Find-CableDevice
$installedDriver = $false

if ($device) {
  Write-Host "VB-CABLE already installed: $($device.InstanceId)"
} else {
  Write-Host "Downloading VB-CABLE driver pack..."
  if (-not (Test-Path $downloadDir)) {
    New-Item -ItemType Directory -Path $downloadDir -Force | Out-Null
  }
  Download-File -Url $cableZipUrl -OutFile $cableZipPath -SkipIfExists

  if (Test-Path $cableExtract) {
    Remove-Item $cableExtract -Recurse -Force
  }
  Expand-Archive -Path $cableZipPath -DestinationPath $cableExtract -Force

  $infs = Get-ChildItem -Path $cableExtract -Recurse -Filter '*.inf'
  if ($infs.Count -eq 0) {
    throw "Could not find VB-CABLE INF in extracted archive at $cableExtract."
  }
  # Pack may ship multiple INFs (x86 / x64 / ARM64). These Windows VMs are
  # AMD64; prefer the 64-bit INF, fall back to the only one if single-arch.
  $inf = ($infs | Where-Object { $_.Name -match '64' } | Select-Object -First 1).FullName
  if (-not $inf) { $inf = $infs[0].FullName }

  Write-Host "Installing VB-CABLE driver from $inf..."
  $proc = Start-Process -FilePath 'pnputil.exe' `
    -ArgumentList '/add-driver', "`"$inf`"", '/install' `
    -Wait -PassThru -NoNewWindow
  if ($proc.ExitCode -ne 0) {
    throw "pnputil /add-driver failed with exit code $($proc.ExitCode)"
  }

  $deadline = (Get-Date).AddSeconds(30)
  while ((Get-Date) -lt $deadline -and -not $device) {
    Start-Sleep -Seconds 2
    $device = Find-CableDevice
  }
  if (-not $device) {
    throw "VB-CABLE device did not appear in Device Manager after install."
  }
  Write-Host "VB-CABLE installed: $($device.InstanceId)"
  $installedDriver = $true
}

if (-not (Test-Path $sunshineConf)) {
  throw "Sunshine config not found at $sunshineConf"
}

$confBefore = Get-Content -LiteralPath $sunshineConf -Raw
Set-SunshineConfigEntry -Path $sunshineConf -Key 'virtual_sink'                -Value $cableSinkName
Set-SunshineConfigEntry -Path $sunshineConf -Key 'install_steam_audio_drivers' -Value 'disabled'
$confAfter = Get-Content -LiteralPath $sunshineConf -Raw

if ($installedDriver -or $confBefore -ne $confAfter) {
  if ($confBefore -ne $confAfter) {
    Write-Host "Updated Sunshine config (virtual_sink, install_steam_audio_drivers)."
  }
  Write-Host "Restarting Sunshine..."
  Restart-Sunshine
}

Write-Host "---------------------------------------------------------"
Write-Host "END 31"
Write-Host "---------------------------------------------------------"
Write-Host ""
