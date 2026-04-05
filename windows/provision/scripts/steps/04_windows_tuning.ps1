$ErrorActionPreference = 'Stop'

Write-Host "#########################################################"
Write-Host "### Start 04"
Write-Host "#########################################################"

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

# Configure Japanese keyboard layout for the user session and the logon/default session.
$desiredInputTip = "0411:00000411"
$needsLanguageUpdate = $false
Write-Host "Desired input tip: $desiredInputTip"

try {
  $currentLanguageList = Get-WinUserLanguageList
  $languageSummary = $currentLanguageList | ForEach-Object {
    "$($_.LanguageTag) [tips=$($_.InputMethodTips -join ', ')]"
  }
  Write-Host "Current user language list: $($languageSummary -join ' | ')"

  $jpEntry = $currentLanguageList | Where-Object { $_.LanguageTag -eq "ja" -or $_.LanguageTag -eq "ja-JP" -or $_.LanguageTag -like "ja-*" } | Select-Object -First 1
  if (-not $jpEntry) {
    Write-Host "Japanese language entry not found. Language update required."
    $needsLanguageUpdate = $true
  } else {
    Write-Host "Japanese language entry found: $($jpEntry.LanguageTag)"
    Write-Host "Current Japanese input tips: $($jpEntry.InputMethodTips -join ', ')"
    Write-Host "Not using InputMethodTips as a hard requirement because Windows may report Japanese IME tips in GUID form."
  }
} catch {
  Write-Host "Failed to inspect current user language list: $($_.Exception.Message)"
  $needsLanguageUpdate = $true
}

try {
  $preload1 = (Get-ItemProperty -Path "HKCU:\Keyboard Layout\Preload" -ErrorAction Stop)."1"
  Write-Host "HKCU keyboard preload slot 1: $preload1"
  if ($preload1 -ne "00000411") {
    Write-Host "HKCU keyboard preload slot 1 is not Japanese. Language update required."
    $needsLanguageUpdate = $true
  } else {
    Write-Host "HKCU keyboard preload slot 1 already set to Japanese."
  }
} catch {
  Write-Host "Failed to inspect HKCU keyboard preload slot 1: $($_.Exception.Message)"
  $needsLanguageUpdate = $true
}

Write-Host "needsLanguageUpdate = $needsLanguageUpdate"
if ($needsLanguageUpdate) {
  Write-Host "Applying Japanese language/input method update..."
  $languageList = New-WinUserLanguageList -Language "ja-JP"
  Set-WinUserLanguageList -LanguageList $languageList -Force -WarningAction SilentlyContinue
  Set-WinDefaultInputMethodOverride -InputTip $desiredInputTip
  $changed = $true
}

Set-RegistryValueIfNeeded `
  -Path "HKCU:\Keyboard Layout\Preload" `
  -Name "1" `
  -Value "00000411"

Set-RegistryValueIfNeeded `
  -Path "Registry::HKEY_USERS\.DEFAULT\Keyboard Layout\Preload" `
  -Name "1" `
  -Value "00000411"

# Force the Japanese 106/109 keyboard layout DLL so RDP scan codes map like a JP keyboard.
Set-RegistryValueIfNeeded `
  -Path "HKLM:\SYSTEM\CurrentControlSet\Control\Keyboard Layouts\00000411" `
  -Name "Layout File" `
  -Value "kbd106.dll"

if ($changed) {
  Write-Host "Windows tuning changed system settings. Requesting reboot..."
  New-Item $rebootFlag -ItemType File -Force | Out-Null
} else {
  Write-Host "Windows tuning already in desired state. No reboot requested."
}

Write-Host "---------------------------------------------------------"
Write-Host "END 04"
Write-Host "---------------------------------------------------------"
Write-Host ""
