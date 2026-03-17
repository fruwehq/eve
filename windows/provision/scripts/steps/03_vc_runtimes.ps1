$ErrorActionPreference = 'Stop'

. "$PSScriptRoot\..\lib\downloads.ps1"

Write-Host "Ensuring Visual C++ runtime is installed..."

$url  = "https://aka.ms/vs/17/release/vc_redist.x64.exe"
$file = "C:\Users\Administrator\provision\downloads\vc\vc_redist.x64.exe"

# Check if the VC++ runtime is already installed
$vcKey = "HKLM:\SOFTWARE\Microsoft\VisualStudio\14.0\VC\Runtimes\x64"
$installed = $false

if (Test-Path $vcKey) {
    try {
        $props = Get-ItemProperty -Path $vcKey
        if ($props.Installed -eq 1) {
            $installed = $true
        }
    } catch {}
}

if ($installed) {
    Write-Host "Visual C++ runtime already installed. Skipping."
    return
}

Write-Host "Visual C++ runtime not found. Installing..."

Download-File -Url $url -OutFile $file -SkipIfExists
Unblock-File $file -ErrorAction SilentlyContinue

$proc = Start-Process -FilePath $file -ArgumentList "/install /quiet /norestart" -Wait -PassThru
Write-Host "Installer exit code: $($proc.ExitCode)"
