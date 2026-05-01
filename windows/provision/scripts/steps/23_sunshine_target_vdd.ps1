$ErrorActionPreference = 'Stop'

Write-Host "#########################################################"
Write-Host "### Start 23"
Write-Host "#########################################################"

# After step 22, VDD is the only active display on the desktop.  NVIDIA's
# adapter stays present for NVENC encoding.  DXGI Desktop Duplication captures
# the entire virtual desktop — which is now VDD's resolution alone.  We just
# ensure Sunshine has no stale output_name override and restart it.

$confPath = 'C:\Program Files\Sunshine\config\sunshine.conf'
$exePath  = 'C:\Program Files\Sunshine\sunshine.exe'

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

$markerPath = 'C:\Users\Administrator\provision\state\display-config-done.flag'
if (-not (Test-Path $markerPath)) {
    Write-Host "Waiting for display-config marker ..."
    $deadline = (Get-Date).AddSeconds(120)
    while ((Get-Date) -lt $deadline -and -not (Test-Path $markerPath)) {
        Start-Sleep -Seconds 3
    }
    if (-not (Test-Path $markerPath)) {
        Write-Host "WARNING: display-config marker not found. Continuing anyway."
    } else {
        Write-Host "Display config: $((Get-Content $markerPath -Raw).Trim())"
    }
} else {
    Write-Host "Display config already done: $((Get-Content $markerPath -Raw).Trim())"
}

# Ensure config file exists
if (-not (Test-Path $confPath)) {
    $confDir = Split-Path $confPath -Parent
    if (-not (Test-Path $confDir)) { New-Item -ItemType Directory -Path $confDir -Force | Out-Null }
    New-Item -ItemType File -Path $confPath -Force | Out-Null
}

# Remove any stale output_name line.  With VDD as the sole desktop display,
# Sunshine captures the full virtual desktop at VDD's resolution via NVIDIA's
# DXGI adapter + NVENC encoder automatically.
$cfgLines = @(Get-Content -LiteralPath $confPath)
$filtered = @($cfgLines | Where-Object { $_ -notmatch '^\s*output_name\s*=' })
$desired  = ($filtered | Where-Object { $_.Trim() -ne '' }) -join "`r`n"
$existing = Get-Content -LiteralPath $confPath -Raw -ErrorAction SilentlyContinue

if ($existing -ne $desired) {
    Write-Host "Updating Sunshine config (removing output_name)."
    Set-Content -LiteralPath $confPath -Value $desired -NoNewline -Encoding ASCII
    Write-Host "Restarting Sunshine ..."
    Restart-Sunshine
} else {
    Write-Host "Sunshine config already correct (no output_name)."
}

Start-Sleep -Seconds 5
$svc = Get-Service -Name 'SunshineService' -ErrorAction SilentlyContinue
if ($svc) {
    Write-Host "Sunshine service: $($svc.Status)"
}

Write-Host "---------------------------------------------------------"
Write-Host "END 23"
Write-Host "---------------------------------------------------------"
Write-Host ""
