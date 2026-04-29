$ErrorActionPreference = 'Stop'

Write-Host "#########################################################"
Write-Host "### Start 23"
Write-Host "#########################################################"

# Sunshine couples capture to the encoding GPU (NVIDIA NVENC) and by default
# captures NVIDIA's adapter output rather than VDD. Force capture to VDD by
# writing output_name to sunshine.conf using the GDI display name Sunshine
# itself reports in its log (the JSON "Currently available display devices"
# block, which includes friendly_name and EDID).
#
# This requires Sunshine to be running so it has emitted the display list.

$confPath = 'C:\Program Files\Sunshine\config\sunshine.conf'
$logPath = 'C:\Program Files\Sunshine\config\sunshine.log'
$exePath = 'C:\Program Files\Sunshine\sunshine.exe'

function Restart-Sunshine {
  $svc = Get-Service -Name 'SunshineService' -ErrorAction SilentlyContinue
  if ($svc) {
    Restart-Service -Name 'SunshineService' -Force
    return
  }
  Get-Process -Name 'sunshine' -ErrorAction SilentlyContinue | Stop-Process -Force
  Start-Sleep -Seconds 2
  Start-Process -FilePath $exePath -WindowStyle Hidden
}

function Get-VddDisplayName {
  if (-not (Test-Path -LiteralPath $logPath)) { return $null }
  $log = Get-Content -LiteralPath $logPath -Raw
  # Match all "Currently available display devices:\n[...]" JSON arrays.
  $rx = [regex]::new('(?ms)Currently available display devices:\s*\r?\n(\[.*?\])\r?\n')
  $matches = $rx.Matches($log)
  if ($matches.Count -eq 0) { return $null }
  $jsonText = $matches[$matches.Count - 1].Groups[1].Value
  $displays = $jsonText | ConvertFrom-Json
  $vdd = $displays | Where-Object {
    ($_.friendly_name -and $_.friendly_name -match 'VDD') -or
    ($_.edid -and $_.edid.manufacturer_id -eq 'MTT')
  } | Select-Object -First 1
  if ($vdd) { return [string]$vdd.display_name }
  return $null
}

# Force Sunshine to emit a fresh display list, then poll for it.
Restart-Sunshine

$timeoutSeconds = 60
$start = Get-Date
$vddDisplayName = $null
while (((Get-Date) - $start).TotalSeconds -lt $timeoutSeconds) {
  Start-Sleep -Seconds 2
  $vddDisplayName = Get-VddDisplayName
  if ($vddDisplayName) { break }
}

if (-not $vddDisplayName) {
  throw "Could not determine VDD's display_name from Sunshine log within $timeoutSeconds seconds. Inspect $logPath."
}

Write-Host "VDD display: $vddDisplayName"

# Update sunshine.conf — drop any existing output_name lines, append the new one.
$cfgLines = if (Test-Path -LiteralPath $confPath) { Get-Content -LiteralPath $confPath } else { @() }
$filtered = $cfgLines | Where-Object { $_ -notmatch '^\s*output_name\s*=' }
$desiredLines = @($filtered) + @("output_name = $vddDisplayName")
$desiredContent = ($desiredLines -join "`r`n") + "`r`n"

$existingContent = if (Test-Path -LiteralPath $confPath) { (Get-Content -LiteralPath $confPath -Raw) } else { '' }
if ($existingContent -ne $desiredContent) {
  Write-Host "Writing output_name = $vddDisplayName to $confPath"
  Set-Content -LiteralPath $confPath -Value $desiredContent -NoNewline -Encoding ASCII
  Restart-Sunshine
} else {
  Write-Host "$confPath already targets $vddDisplayName."
}

Write-Host "---------------------------------------------------------"
Write-Host "END 23"
Write-Host "---------------------------------------------------------"
Write-Host ""
