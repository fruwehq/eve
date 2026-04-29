$ErrorActionPreference = 'Stop'

Write-Host "#########################################################"
Write-Host "### Start 22"
Write-Host "#########################################################"

# Step 23 sets Sunshine's output_name to capture VDD specifically. This step
# also disables non-VDD Monitor-class children and the Microsoft Basic Display
# Adapter, so the only "live" desktop on this VM is VDD's.
# (NVIDIA A40-4Q stays enabled — Sunshine needs it for NVENC encoding.)

$keepMonitorPattern = '^DISPLAY\\MTT'
$disableAdapterIds = @(
  # Microsoft Basic Display Adapter (vGA fallback exposing a 1280x800 desktop
  # that Sunshine would otherwise capture).
  'PCI\VEN_1234&DEV_1111&SUBSYS_11001AF4&REV_02\3&11583659&0&08'
)

$disabled = 0

$monitors = @(Get-PnpDevice -Class Monitor -PresentOnly -ErrorAction SilentlyContinue)
foreach ($m in $monitors) {
  if ($m.InstanceId -match $keepMonitorPattern) {
    Write-Host "Keeping VDD monitor: $($m.FriendlyName) [$($m.InstanceId)]"
    continue
  }
  if ($m.ConfigManagerErrorCode -eq 'CM_PROB_DISABLED') {
    Write-Host "Already disabled: $($m.FriendlyName) [$($m.InstanceId)]"
    continue
  }
  Write-Host "Disabling monitor: $($m.FriendlyName) [$($m.InstanceId)]"
  Disable-PnpDevice -InstanceId $m.InstanceId -Confirm:$false
  $disabled++
}

foreach ($id in $disableAdapterIds) {
  $dev = Get-PnpDevice -InstanceId $id -ErrorAction SilentlyContinue
  if (-not $dev) {
    Write-Host "Adapter not present (skipping): $id"
    continue
  }
  if ($dev.ConfigManagerErrorCode -eq 'CM_PROB_DISABLED') {
    Write-Host "Already disabled: $($dev.FriendlyName) [$id]"
    continue
  }
  Write-Host "Disabling adapter: $($dev.FriendlyName) [$id]"
  Disable-PnpDevice -InstanceId $id -Confirm:$false
  $disabled++
}

if ($disabled -eq 0) {
  Write-Host "No devices to disable."
} else {
  Write-Host "Disabled $disabled device(s) to leave VDD as the sole active display."
}

Write-Host "---------------------------------------------------------"
Write-Host "END 22"
Write-Host "---------------------------------------------------------"
Write-Host ""
