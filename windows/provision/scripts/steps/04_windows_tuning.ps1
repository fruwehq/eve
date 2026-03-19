$ErrorActionPreference = 'Stop'

Write-Host "Applying Windows tuning..."

$changed = $false

function Set-RegistryValueIfNeeded {
  param(
    [Parameter(Mandatory=$true)][string]$Path,
    [Parameter(Mandatory=$true)][string]$Name,
    [Parameter(Mandatory=$true)]$Value,
    [string]$Type = "String"
  )

  $currentExists = $false
  $currentValue = $null

  if (Test-Path $Path) {
    try {
      $props = Get-ItemProperty -Path $Path -ErrorAction Stop
      $currentValue = $props.$Name
      $currentExists = $true
    } catch {}
  }

  if (-not $currentExists -or $currentValue -ne $Value) {
    if (!(Test-Path $Path)) {
      New-Item -Path $Path -Force | Out-Null
    }
    Set-ItemProperty -Path $Path -Name $Name -Value $Value -Type $Type
    $script:changed = $true
  }
}

$rebootFlag = "C:\Users\Administrator\provision\state\reboot.flag"
$User       = "Administrator"
$SecretsFile = "C:\Users\Administrator\provision\state\secrets.json"
$Pass = $env:EPHEMERAL_WINDOWS_PASSWORD

if (-not $Pass -and (Test-Path $SecretsFile)) {
  try {
    $Secrets = Get-Content $SecretsFile | ConvertFrom-Json
    $Pass = $Secrets.windows_password
  } catch {
    throw "Failed to read Windows password from $SecretsFile"
  }
}

if (-not $Pass) {
  throw "Windows password not provided. Set EPHEMERAL_WINDOWS_PASSWORD or create $SecretsFile with a windows_password field."
}

# Prevent display sleep / system standby while on AC power
$powerOutputBefore = @(
  & powercfg /query SCHEME_CURRENT SUB_VIDEO VIDEOIDLE 2>$null
  & powercfg /query SCHEME_CURRENT SUB_SLEEP STANDBYIDLE 2>$null
) | Out-String
powercfg -change -monitor-timeout-ac 0
powercfg -change -standby-timeout-ac 0
$powerOutputAfter = @(
  & powercfg /query SCHEME_CURRENT SUB_VIDEO VIDEOIDLE 2>$null
  & powercfg /query SCHEME_CURRENT SUB_SLEEP STANDBYIDLE 2>$null
) | Out-String
if ($powerOutputBefore -ne $powerOutputAfter) {
  $changed = $true
}

# Disable hibernation
Set-RegistryValueIfNeeded `
  -Path "HKLM:\SYSTEM\CurrentControlSet\Control\Power" `
  -Name HibernateEnabled `
  -Value 0 `
  -Type DWord

# Disable requirement for Ctrl+Alt+Del at logon
Set-RegistryValueIfNeeded `
  -Path "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\System" `
  -Name DisableCAD `
  -Type DWord `
  -Value 1

# Disable lock screen
Set-RegistryValueIfNeeded `
  -Path "HKLM:\SOFTWARE\Policies\Microsoft\Windows\Personalization" `
  -Name NoLockScreen `
  -Type DWord `
  -Value 1

# Configure Windows auto-logon for the local Administrator account
Set-RegistryValueIfNeeded -Path "HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon" -Name AutoAdminLogon -Value "1"
Set-RegistryValueIfNeeded -Path "HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon" -Name DefaultUserName -Value $User
Set-RegistryValueIfNeeded -Path "HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon" -Name DefaultPassword -Value $Pass
Set-RegistryValueIfNeeded -Path "HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon" -Name DefaultDomainName -Value "."

if ($changed) {
  Write-Host "Windows tuning changed system settings. Requesting reboot..."
  New-Item $rebootFlag -ItemType File -Force | Out-Null
} else {
  Write-Host "Windows tuning already in desired state. No reboot requested."
}
