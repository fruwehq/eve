$ErrorActionPreference = 'Stop'

Write-Host "#########################################################"
Write-Host "### Start 40"
Write-Host "#########################################################"

. "$PSScriptRoot\..\lib\downloads.ps1"

Write-Host "Installing RustDesk..."

$rustdeskDir = "${env:ProgramFiles}\RustDesk"
$rustdeskExe = Join-Path $rustdeskDir "RustDesk.exe"

if (-not (Test-Path $rustdeskExe)) {
  # Resolve the latest Windows x86_64 installer asset via the GitHub API
  # (mirrors the Sunshine step's pattern in 10_sunshine.ps1).
  $headers = @{ "User-Agent"="Mozilla/5.0"; "Accept"="application/vnd.github+json" }
  $api = "https://api.github.com/repos/rustdesk/rustdesk/releases/latest"
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

  $asset = $release.assets |
    Where-Object { $_.name -match '^rustdesk-.*-x86_64\.exe$' } |
    Select-Object -First 1
  if (-not $asset) {
    throw "Could not find a Windows x86_64 .exe in the latest RustDesk release. Assets: $($release.assets.name -join ', ')"
  }
  $url  = $asset.browser_download_url
  $file = "C:\Users\Administrator\provision\downloads\rustdesk\$($asset.name)"

  Write-Host "Downloading: $($asset.name) (RustDesk $($release.tag_name))"
  Download-File -Url $url -OutFile $file -SkipIfExists
  Unblock-File $file -ErrorAction SilentlyContinue

  # Use the NSIS-standard /S flag with -Wait so the installer blocks until file
  # copy is complete. RustDesk's own --silent-install flag returns immediately
  # after spawning the installer, which leaves the script racing the file copy.
  Write-Host "Running RustDesk installer (silent)..."
  $proc = Start-Process -FilePath $file -ArgumentList "/S" -Wait -PassThru
  if ($proc.ExitCode -ne 0) {
    throw "RustDesk installer failed with exit code $($proc.ExitCode)"
  }
  Write-Host "RustDesk installer exit code: $($proc.ExitCode)"

  if (-not (Test-Path $rustdeskExe)) {
    throw "RustDesk did not install. RustDesk.exe not found at $rustdeskExe"
  }
} else {
  Write-Host "RustDesk already installed at $rustdeskDir. Skipping installer."
}

# Put RustDesk on the system PATH so SSH-invoked clients can call `rustdesk` directly
# (the bare `rustdesk` lookup is what scripts/remote-rustdesk runs over SSH).
$systemPath = [Environment]::GetEnvironmentVariable("Path", "Machine")
if ($systemPath -notlike "*$rustdeskDir*") {
  Write-Host "Adding $rustdeskDir to system PATH"
  [Environment]::SetEnvironmentVariable("Path", "$systemPath;$rustdeskDir", "Machine")
  $env:Path = "$env:Path;$rustdeskDir"
}

# Provide a stable lower-case alias on PATH; the bare `rustdesk` token resolves via
# PATHEXT to RustDesk.exe on Windows, but some shells lowercase before lookup.
$rustdeskShim = Join-Path $rustdeskDir "rustdesk.exe"
if (-not (Test-Path $rustdeskShim)) {
  Copy-Item -Path $rustdeskExe -Destination $rustdeskShim -Force
}

# Read RustDesk config delivered via env.json (see scripts/provision).
$envFile = "C:\Users\Administrator\provision\state\env.json"
$rustdeskKey = $null
$rustdeskServer = $null
$rustdeskPassword = $null
if (Test-Path $envFile) {
  try {
    $envData = Get-Content $envFile | ConvertFrom-Json
    $rustdeskKey      = $envData.rustdesk_key
    $rustdeskServer   = $envData.rustdesk_server
    $rustdeskPassword = $envData.rustdesk_password
  } catch {
    Write-Warning "Failed to parse env file: $envFile"
  }
}

Write-Host "Waiting for RustDesk service..."
for ($i = 1; $i -le 15; $i++) {
  $svc = Get-Service -Name "RustDesk" -ErrorAction SilentlyContinue
  if ($svc -and $svc.Status -eq "Running") { break }
  Start-Sleep -Seconds 2
}

# RustDesk on Windows runs as a service under LocalService (or SYSTEM in newer builds).
# `--option` and `--password` write to the *user* config; the daemon reads its *own*
# config dir. Write the TOML directly into every plausible service config location so
# whichever the running daemon uses gets the right rendezvous_server/key/password.
#
# Idempotency note: the password+salt hash gets a fresh salt every time `--password`
# runs, which invalidates whatever per-peer hash the local RustDesk client cached on
# its last successful connect -- meaning the local "Remember password" stops working
# and the user gets prompted again. So we only rewrite config / reset password when
# the desired settings actually differ from what's already on disk.
if ($rustdeskServer -or $rustdeskKey -or $rustdeskPassword) {
  $tomlBuilder = New-Object System.Text.StringBuilder
  if ($rustdeskServer) {
    [void]$tomlBuilder.AppendLine("rendezvous_server = '${rustdeskServer}:21116'")
  }
  [void]$tomlBuilder.AppendLine("")
  [void]$tomlBuilder.AppendLine("[options]")
  if ($rustdeskServer) {
    [void]$tomlBuilder.AppendLine("custom-rendezvous-server = '$rustdeskServer'")
    [void]$tomlBuilder.AppendLine("relay-server = '$rustdeskServer'")
  }
  if ($rustdeskKey) {
    [void]$tomlBuilder.AppendLine("key = '$rustdeskKey'")
  }
  if ($rustdeskPassword) {
    [void]$tomlBuilder.AppendLine("verification-method = 'use-permanent-password'")
    [void]$tomlBuilder.AppendLine("approve-mode = 'password'")
  }
  $toml = $tomlBuilder.ToString()

  $configDirs = @(
    "C:\Windows\ServiceProfiles\LocalService\AppData\Roaming\RustDesk\config",
    "C:\Windows\System32\config\systemprofile\AppData\Roaming\RustDesk\config",
    "$env:APPDATA\RustDesk\config"
  )

  $configChanged = $false
  foreach ($dir in $configDirs) {
    $cfgPath = Join-Path $dir "RustDesk2.toml"
    $existing = if (Test-Path $cfgPath) { Get-Content $cfgPath -Raw } else { "" }
    if ($existing -ne $toml) {
      $configChanged = $true
      break
    }
  }

  if ($configChanged) {
    Write-Host "Stopping RustDesk service to rewrite config..."
    Stop-Service -Name "RustDesk" -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 2

    foreach ($dir in $configDirs) {
      if (-not (Test-Path $dir)) {
        New-Item -ItemType Directory -Path $dir -Force | Out-Null
      }
      $cfgPath = Join-Path $dir "RustDesk2.toml"
      Write-Host "Writing $cfgPath"
      Set-Content -Path $cfgPath -Value $toml -Encoding UTF8 -NoNewline
    }

    Write-Host "Restarting RustDesk service..."
    Start-Service -Name "RustDesk" -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 3

    if ($rustdeskPassword) {
      # Setting the permanent password generates a fresh salt server-side, which
      # is why we only do this when the config changed (i.e. first install or a
      # genuine password rotation) -- not on every reprovision.
      Write-Host "Setting permanent password via CLI..."
      & $rustdeskExe --password $rustdeskPassword | Out-Null
    }
  } else {
    Write-Host "RustDesk config already matches desired state -- leaving password/salt intact."
  }
}

Write-Host "Resolving RustDesk ID..."
for ($i = 1; $i -le 15; $i++) {
  $id = (& $rustdeskExe --get-id 2>$null) -replace '\s', ''
  if ($id) {
    Write-Host "RustDesk ID: $id"
    break
  }
  Start-Sleep -Seconds 2
}

Write-Host "---------------------------------------------------------"
Write-Host "END 40"
Write-Host "---------------------------------------------------------"
Write-Host ""
