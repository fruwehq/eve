$ErrorActionPreference = 'Stop'

Write-Host "#########################################################"
Write-Host "### Start 40"
Write-Host "#########################################################"

. "$PSScriptRoot\..\lib\downloads.ps1"

Write-Host "Installing RustDesk..."

# The provisioning runner executes as SYSTEM via Scheduled Task, so
# %LOCALAPPDATA% expands to systemprofile\AppData\Local. RustDesk's NSIS
# installer also writes to the invoking user's LOCALAPPDATA. Discover the
# actual install path from the running process after install rather than
# hardcoding a per-user path.

# Candidate install locations: SYSTEM profile (Scheduled Task context) and
# the Administrator user profile (interactive session context).
$candidateDirs = @(
  "${env:LOCALAPPDATA}\rustdesk",
  "C:\Users\Administrator\AppData\Local\rustdesk"
)

$rustdeskDir = $null
$rustdeskExe = $null

# Check if already installed in any candidate location.
foreach ($dir in $candidateDirs) {
  $candidate = Join-Path $dir "rustdesk.exe"
  if (Test-Path $candidate) {
    $rustdeskDir = $dir
    $rustdeskExe = $candidate
    break
  }
}

# Also check via the running process (covers non-standard paths).
if (-not $rustdeskExe) {
  $proc = Get-Process rustdesk -ErrorAction SilentlyContinue | Select-Object -First 1
  if ($proc -and $proc.Path) {
    $rustdeskExe = $proc.Path
    $rustdeskDir = Split-Path $rustdeskExe
  }
}

if (-not $rustdeskExe) {
  # Resolve the latest Windows x86_64 installer asset via the GitHub API
  # (mirrors the Sunshine step's pattern in sunshine.ps1).
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

  # RustDesk's NSIS /S installer spawns a child and the parent exits quickly,
  # but Start-Process -Wait can block forever if the child inherits the handle.
  # Launch without -Wait and poll for the running process, which indicates the
  # install is fully complete. RustDesk 1.4+ does not register a Windows
  # service; it runs as a user process.
  Write-Host "Running RustDesk installer (silent)..."
  Start-Process -FilePath $file -ArgumentList "/S"

  $installTimeout = 120
  $installStart = Get-Date
  while (((Get-Date) - $installStart).TotalSeconds -lt $installTimeout) {
    $proc = Get-Process rustdesk -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($proc -and $proc.Path) {
      $rustdeskExe = $proc.Path
      $rustdeskDir = Split-Path $rustdeskExe
      Write-Host "RustDesk process running after $([int]((Get-Date) - $installStart).TotalSeconds)s"
      break
    }
    Start-Sleep -Seconds 2
  }

  if (-not $rustdeskExe) {
    throw "RustDesk did not install. No rustdesk process detected after ${installTimeout}s"
  }

  Write-Host "RustDesk installed at $rustdeskDir"
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

Write-Host "Waiting for RustDesk process..."
for ($i = 1; $i -le 15; $i++) {
  $proc = Get-Process rustdesk -ErrorAction SilentlyContinue | Select-Object -First 1
  if ($proc) { break }
  Start-Sleep -Seconds 2
}

# RustDesk 1.4+ runs as a user process (not a Windows service). `--option`
# and `--password` write to the *user* config; the daemon reads its *own*
# config dir. Write the TOML directly into every plausible config location so
# whichever the running process uses gets the right rendezvous_server/key/password.
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
    "C:\Users\Administrator\AppData\Roaming\RustDesk\config",
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
    Write-Host "Stopping RustDesk to rewrite config..."
    Get-Process rustdesk -ErrorAction SilentlyContinue | Stop-Process -Force
    Start-Sleep -Seconds 2

    foreach ($dir in $configDirs) {
      if (-not (Test-Path $dir)) {
        New-Item -ItemType Directory -Path $dir -Force | Out-Null
      }
      $cfgPath = Join-Path $dir "RustDesk2.toml"
      Write-Host "Writing $cfgPath"
      Set-Content -Path $cfgPath -Value $toml -Encoding UTF8 -NoNewline
    }

    Write-Host "Restarting RustDesk..."
    Start-Process -FilePath $rustdeskExe -WindowStyle Hidden
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
