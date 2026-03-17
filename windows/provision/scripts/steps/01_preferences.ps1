$ErrorActionPreference = 'Stop'

Write-Host "Configuring Windows UI (dark mode + black background)..."

$targetUser = "Administrator"
$userProfile = "C:\Users\$targetUser"
$ntUserDat = Join-Path $userProfile "NTUSER.DAT"
$hiveName = "TempAdminProfile"
$loadedHere = $false

if (!(Test-Path $ntUserDat)) {
    throw "User profile hive not found: $ntUserDat"
}

# Prefer the real loaded user hive if the Administrator profile is already loaded.
# This avoids reg.exe load failures like "file is being used by another process".
$user = Get-CimInstance Win32_UserAccount -Filter "Name='$targetUser' AND LocalAccount=True" | Select-Object -First 1
if (-not $user -or -not $user.SID) {
    throw "Could not determine SID for local user $targetUser"
}

$realHiveRoot = "Registry::HKEY_USERS\$($user.SID)"
if (Test-Path $realHiveRoot) {
    Write-Host "Using already loaded hive for $targetUser ($($user.SID))..."
    $hiveRoot = $realHiveRoot
} else {
    $hiveRoot = "Registry::HKEY_USERS\$hiveName"
    Write-Host "Loading user hive for $targetUser..."
    & reg.exe load "HKU\$hiveName" "$ntUserDat" | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to load user hive: $ntUserDat"
    }
    $loadedHere = $true
}

try {
    # --- 1) Enable dark mode (apps + system) for the Administrator profile ---
    $personalize = "$hiveRoot\Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"
    New-Item -Path $personalize -Force | Out-Null

    # 0 = dark mode
    Set-ItemProperty -Path $personalize -Name AppsUseLightTheme -Value 0 -Type DWord
    Set-ItemProperty -Path $personalize -Name SystemUsesLightTheme -Value 0 -Type DWord
    Set-ItemProperty -Path $personalize -Name EnableTransparency -Value 0 -Type DWord

    Write-Host "Dark mode enabled for $targetUser."

    # --- 2) Set a solid black background directly in the user profile ---
    # No wallpaper image is needed; Windows supports solid colors via registry.
    $desktop = "$hiveRoot\Control Panel\Desktop"
    $colors = "$hiveRoot\Control Panel\Colors"

    New-Item -Path $desktop -Force | Out-Null
    New-Item -Path $colors -Force | Out-Null

    Set-ItemProperty -Path $desktop -Name Wallpaper -Value ""
    Set-ItemProperty -Path $desktop -Name WallpaperStyle -Value "0"
    Set-ItemProperty -Path $desktop -Name TileWallpaper -Value "0"
    Set-ItemProperty -Path $colors -Name Background -Value "0 0 0"

    Write-Host "Solid black background configured for $targetUser."

    Write-Host "UI configuration complete. Changes will apply to the Administrator desktop session."
}
finally {
    if ($loadedHere) {
        Write-Host "Unloading user hive for $targetUser..."
        & reg.exe unload "HKU\$hiveName" | Out-Null
    }
}
