$ErrorActionPreference = 'Stop'

Write-Host "Applying Windows tuning..."

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
powercfg -change -monitor-timeout-ac 0
powercfg -change -standby-timeout-ac 0

# Disable hibernation
Set-ItemProperty `
  -Path "HKLM:\SYSTEM\CurrentControlSet\Control\Power" `
  -Name HibernateEnabled `
  -Value 0

# Disable requirement for Ctrl+Alt+Del at logon
Set-ItemProperty `
  -Path "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\System" `
  -Name DisableCAD `
  -Type DWord `
  -Value 1

# Disable lock screen
New-Item -Path "HKLM:\SOFTWARE\Policies\Microsoft\Windows\Personalization" -Force | Out-Null
Set-ItemProperty `
  -Path "HKLM:\SOFTWARE\Policies\Microsoft\Windows\Personalization" `
  -Name NoLockScreen `
  -Type DWord `
  -Value 1

# Configure Windows auto-logon for the local Administrator account
Set-ItemProperty "HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon" "AutoAdminLogon" -Value "1"
Set-ItemProperty "HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon" "DefaultUserName" -Value $User
Set-ItemProperty "HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon" "DefaultPassword" -Value $Pass
Set-ItemProperty "HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon" "DefaultDomainName" -Value "."

# Let runner.ps1 handle the actual reboot flow
New-Item $rebootFlag -ItemType File -Force | Out-Null
