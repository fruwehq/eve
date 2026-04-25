$ErrorActionPreference = 'Stop'

Write-Host "#########################################################"
Write-Host "### Start 35"
Write-Host "#########################################################"

. "$PSScriptRoot\..\lib\downloads.ps1"

Write-Host "Installing Xpra..."

$xpraDir = "${env:ProgramFiles}\Xpra"
$xpraExe = Join-Path $xpraDir "Xpra_cmd.exe"
$url  = "https://xpra.org/dists/windows/Xpra-x86_64_6.4.3-r0.msi"
$file = "C:\Users\Administrator\provision\downloads\xpra\Xpra-x86_64_6.4.3-r0.msi"

if (Test-Path $xpraExe) {
  Write-Host "Xpra already installed at $xpraDir. Skipping."

  Write-Host "---------------------------------------------------------"
  Write-Host "END 35 - early exit"
  Write-Host "---------------------------------------------------------"
  Write-Host ""

  exit 0
}

Download-File -Url $url -OutFile $file -SkipIfExists

Write-Host "Installing Xpra (silent MSI)..."
$proc = Start-Process -FilePath "msiexec.exe" -ArgumentList "/i", $file, "/qn", "/norestart" -Wait -PassThru
if ($proc.ExitCode -ne 0) {
  throw "Xpra MSI installer failed with exit code $($proc.ExitCode)"
}
Write-Host "Xpra installer exit code: $($proc.ExitCode)"

if (!(Test-Path $xpraExe)) {
  throw "Xpra did not install. Xpra_cmd.exe not found at $xpraExe"
}

Write-Host "Xpra installed at $xpraDir"

Write-Host "---------------------------------------------------------"
Write-Host "END 35"
Write-Host "---------------------------------------------------------"
Write-Host ""
