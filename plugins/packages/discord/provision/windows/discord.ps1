$ErrorActionPreference = 'Stop'

Write-Host "#########################################################"
Write-Host "### discord (windows)"
Write-Host "#########################################################"

# The provisioning runner executes as SYSTEM via the Scheduled Task that
# bootstrap.ps1 registers. Discord is a per-user app installed by an
# NSIS installer that writes to %LOCALAPPDATA%. Under SYSTEM that
# resolves to C:\Windows\System32\config\systemprofile\AppData\Local --
# the wrong place. winget --scope user under SYSTEM is similarly nonsense.
#
# Pattern (mirrors plugins/packages/rustdesk/provision/windows/rustdesk.ps1):
# read the windows password from env.json and schedule a one-shot task
# under the Administrator user, then wait for it to finish and verify
# the install landed in the Administrator profile.

$adminDiscordRoot = "C:\Users\Administrator\AppData\Local\Discord"
$adminUpdateExe   = Join-Path $adminDiscordRoot 'Update.exe'

if (Test-Path $adminUpdateExe) {
  Write-Host "Discord already installed at $adminDiscordRoot. Skipping."
  exit 0
}

$envFile = "C:\Users\Administrator\provision\state\env.json"
if (-not (Test-Path $envFile)) {
  throw "env.json not found at $envFile; cannot resolve Administrator password for user-context install"
}

$envData = Get-Content -Path $envFile -Raw | ConvertFrom-Json
$windowsPassword = $envData.windows_password
if (-not $windowsPassword) {
  throw "windows_password missing from env.json; cannot run Discord install as Administrator"
}

# Wait for winget to be available. After a fresh boot the AppX/MSIX
# stack can take a beat to settle.
$wingetCmd = $null
for ($attempt = 1; $attempt -le 30; $attempt++) {
  $wingetCmd = Get-Command winget -ErrorAction SilentlyContinue
  if ($wingetCmd) { break }
  Write-Host "winget not available yet (attempt $attempt/30). Sleeping 5s..."
  Start-Sleep -Seconds 5
}
if (-not $wingetCmd) {
  throw "winget did not become available; cannot install Discord"
}

$taskName = 'EveDiscordInstall'
$installCommand = 'winget install --id Discord.Discord --silent --accept-package-agreements --accept-source-agreements --scope user'
$taskCommand = "powershell.exe -NoProfile -ExecutionPolicy Bypass -Command `"$installCommand`""

# Drop any leftover task from a previous attempt.
& schtasks.exe /Delete /TN $taskName /F 2>$null | Out-Null

$runAt = (Get-Date).AddSeconds(15).ToString("HH:mm")
Write-Host "Scheduling Discord install under Administrator (runs in ~15s)..."
& schtasks.exe /Create /TN $taskName /SC ONCE /ST $runAt /RU "Administrator" /RP $windowsPassword /RL HIGHEST /IT /TR $taskCommand /F | Out-Null
& schtasks.exe /Run /TN $taskName | Out-Null

# Poll until Discord appears or the install gives up.
$maxWaitSeconds = 600
$elapsed = 0
$installed = $false
while ($elapsed -lt $maxWaitSeconds) {
  Start-Sleep -Seconds 10
  $elapsed += 10
  if (Test-Path $adminUpdateExe) {
    $installed = $true
    break
  }
  Write-Host "Waiting for Discord install to complete... (${elapsed}s/${maxWaitSeconds}s)"
}

# Cleanup the one-shot task regardless of outcome.
& schtasks.exe /Delete /TN $taskName /F 2>$null | Out-Null

if (-not $installed) {
  throw "Discord did not install within ${maxWaitSeconds}s. $adminUpdateExe missing."
}

Write-Host "Discord installed at $adminDiscordRoot"
