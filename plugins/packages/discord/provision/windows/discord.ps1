$ErrorActionPreference = 'Stop'

Write-Host "#########################################################"
Write-Host "### discord (windows)"
Write-Host "#########################################################"

$discordRoot = Join-Path $env:LOCALAPPDATA 'Discord'
if (Test-Path $discordRoot) {
  Write-Host "Discord already installed at $discordRoot. Skipping."
  exit 0
}

Write-Host "Installing Discord via winget..."
winget install --id Discord.Discord --silent --accept-package-agreements --accept-source-agreements --scope user

if (-not (Test-Path $discordRoot)) {
  throw "Discord did not install. $discordRoot missing after winget install."
}

Write-Host "Discord installed at $discordRoot"
