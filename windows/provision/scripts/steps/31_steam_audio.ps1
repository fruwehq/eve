$ErrorActionPreference = 'Stop'

Write-Host "#########################################################"
Write-Host "### Start 31"
Write-Host "#########################################################"

. "$PSScriptRoot\..\lib\sunshine.ps1"

# Sunshine's default virtual audio sink is "Steam Streaming Speakers". The
# matching driver ships inside the Steam install at:
#   %CommonProgramFiles(x86)%\Steam\drivers\Windows10\x64\SteamStreamingSpeakers.inf
# Sunshine can self-install it (config: install_steam_audio_drivers, default
# true) but only at startup when Steam is already present. Our flow installs
# Sunshine in step 10 and Steam in step 30, so Sunshine never gets a chance
# to install the driver. This step closes that gap explicitly.

$steamRoot = "${env:CommonProgramFiles(x86)}\Steam"
$driverInf = Join-Path $steamRoot 'drivers\Windows10\x64\SteamStreamingSpeakers.inf'

if (-not (Test-Path $driverInf)) {
  throw "Steam Streaming Speakers driver INF not found at $driverInf. Step 30 (Steam install) must have completed."
}

function Find-SteamSpeakersDevice {
  Get-PnpDevice -PresentOnly -ErrorAction SilentlyContinue |
    Where-Object { $_.FriendlyName -eq 'Steam Streaming Speakers' } |
    Select-Object -First 1
}

$device = Find-SteamSpeakersDevice

if ($device) {
  Write-Host "Steam Streaming Speakers already installed: $($device.InstanceId)"
} else {
  Write-Host "Installing Steam Streaming Speakers driver from $driverInf..."
  $proc = Start-Process -FilePath 'pnputil.exe' `
    -ArgumentList '/add-driver', "`"$driverInf`"", '/install' `
    -Wait -PassThru -NoNewWindow
  if ($proc.ExitCode -ne 0) {
    throw "pnputil /add-driver failed with exit code $($proc.ExitCode)"
  }

  $deadline = (Get-Date).AddSeconds(30)
  while ((Get-Date) -lt $deadline -and -not $device) {
    Start-Sleep -Seconds 2
    $device = Find-SteamSpeakersDevice
  }
  if (-not $device) {
    throw "Steam Streaming Speakers driver did not appear in Device Manager after install."
  }
  Write-Host "Steam Streaming Speakers installed: $($device.InstanceId)"

  Write-Host "Restarting Sunshine..."
  Restart-Sunshine
}

Write-Host "---------------------------------------------------------"
Write-Host "END 31"
Write-Host "---------------------------------------------------------"
Write-Host ""
