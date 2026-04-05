$ErrorActionPreference = 'Stop'

Write-Host "#########################################################"
Write-Host "### Start 02"
Write-Host "#########################################################"

. "$PSScriptRoot\..\lib\downloads.ps1"

Write-Host "Checking GPU driver..."

$nvidia = Get-CimInstance Win32_VideoController | Where-Object { $_.Name -like "*NVIDIA*" }

if ($nvidia) {
    Write-Host "NVIDIA driver already present."

    Write-Host "---------------------------------------------------------"
    Write-Host "END 02 - early exit"
    Write-Host "---------------------------------------------------------"
    Write-Host ""

    exit
}

# Write-Host "Installing NVIDIA driver..."

# $driverUrl  = "https://us.download.nvidia.com/tesla/latest/nvidia-driver.exe"
# $driverPath = "C:\Users\Administrator\provision\downloads\nvidia\nvidia-driver.exe"
# $rebootFlag = "C:\Users\Administrator\provision\state\reboot.flag"

# Download-File -Url $driverUrl -OutFile $driverPath -SkipIfExists
# Unblock-File $driverPath -ErrorAction SilentlyContinue

# $proc = Start-Process -FilePath $driverPath -ArgumentList "-s" -Wait -PassThru
# Write-Host "NVIDIA installer exit code: $($proc.ExitCode)"

# New-Item $rebootFlag -ItemType File -Force | Out-Null

Write-Host "---------------------------------------------------------"
Write-Host "END 02"
Write-Host "---------------------------------------------------------"
Write-Host ""
