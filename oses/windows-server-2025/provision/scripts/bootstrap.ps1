$ProvisionPath = "C:\Users\Administrator\provision"
$ScriptsPath   = "$ProvisionPath\scripts"
$StatePath     = "$ProvisionPath\state"
$LogsPath      = "$ProvisionPath\logs"
$StateFile     = "$StatePath\state.json"

Write-Host "Initializing provisioning system..."

# Ensure we are running from the expected scripts directory
$SourcePath = $PSScriptRoot.TrimEnd('\\')
$ExpectedPath = $ScriptsPath.TrimEnd('\\')

if ($SourcePath -ne $ExpectedPath) {
    throw "bootstrap.ps1 must be executed from $ExpectedPath, but was run from $SourcePath"
}

# Initialize state file if it does not exist
if (!(Test-Path $StateFile)) {
    @{ currentStep = 0 } | ConvertTo-Json | Set-Content $StateFile
}

# Register Scheduled Task (idempotent)
$Action  = New-ScheduledTaskAction -Execute "PowerShell.exe" -Argument "-NoProfile -ExecutionPolicy Bypass -File C:\Users\Administrator\provision\scripts\runner.ps1"
$Trigger = New-ScheduledTaskTrigger -AtStartup

Register-ScheduledTask `
  -TaskName "EphemeralGamingProvision" `
  -Action $Action `
  -Trigger $Trigger `
  -User "SYSTEM" `
  -RunLevel Highest `
  -Force | Out-Null

Write-Host "Provisioning task registered/updated."

# Kick off provisioning now
PowerShell -NoProfile -ExecutionPolicy Bypass -File "C:\Users\Administrator\provision\scripts\runner.ps1"
