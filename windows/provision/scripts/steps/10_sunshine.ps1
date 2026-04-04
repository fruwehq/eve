$ErrorActionPreference = 'Stop'

. "$PSScriptRoot\..\lib\downloads.ps1"

Write-Host "Ensuring Sunshine is installed and configured..."

$sunshineDir = "${env:ProgramFiles}\Sunshine"
$sunshineExe = Join-Path $sunshineDir "sunshine.exe"
$configPath = Join-Path $sunshineDir "config\sunshine.conf"

$alreadyInstalled = Test-Path $sunshineDir
if ($alreadyInstalled) {
  Write-Host "Sunshine already installed at $sunshineDir. Skipping installer."
}

if (-not $alreadyInstalled) {
  # Resolve latest Windows installer asset via GitHub API
  $headers = @{ "User-Agent"="Mozilla/5.0"; "Accept"="application/vnd.github+json" }
  $api = "https://api.github.com/repos/LizardByte/Sunshine/releases/latest"

  $release = $null
  for ($i = 1; $i -le 5; $i++) {
    try {
      $release = Invoke-RestMethod -Uri $api -Headers $headers
      break
    } catch {
      if ($i -eq 5) { throw }
      Start-Sleep -Seconds 2
    }
  }

  # Prefer the canonical Windows installer asset name used by Sunshine releases
  $asset = $release.assets | Where-Object { $_.name -eq "Sunshine-Windows-AMD64-installer.exe" } | Select-Object -First 1

  # Fallback (if naming changes slightly in the future)
  if (-not $asset) {
    $asset = $release.assets | Where-Object { $_.name -match "^Sunshine-Windows-.*-installer\.exe$" } | Select-Object -First 1
  }

  if (-not $asset) {
    throw "Could not find a Windows installer asset in the latest Sunshine release. Assets: $($release.assets.name -join ', ')"
  }

  $url  = $asset.browser_download_url
  $file = "C:\Users\Administrator\provision\downloads\sunshine\Sunshine-Windows-AMD64-installer.exe"

  Write-Host "Downloading: $($asset.name)"
  Download-File -Url $url -OutFile $file -SkipIfExists
  Unblock-File $file -ErrorAction SilentlyContinue

  Write-Host "Running Sunshine installer (silent)..."
  $proc = Start-Process -FilePath $file -ArgumentList "/S" -Wait -PassThru
  if ($proc.ExitCode -ne 0) {
    throw "Sunshine installer failed with exit code $($proc.ExitCode)"
  }
  Write-Host "Sunshine installer exit code: $($proc.ExitCode)"
}

# Ensure the config file exists and allows remote access for this ephemeral instance.
if (!(Test-Path $configPath)) {
  New-Item -ItemType File -Path $configPath -Force | Out-Null
}

if (-not (Select-String -Path $configPath -Pattern "^\s*localhost_only\s*=" -Quiet)) {
  Add-Content -Path $configPath -Value "`nlocalhost_only = false`n"
}

# Set Sunshine Web UI credentials from the environment.
# Use a fixed username to keep provisioning simple and reproducible.
if (-not $env:EPHEMERAL_SUNSHINE_PASSWORD) {
  throw "EPHEMERAL_SUNSHINE_PASSWORD is required"
}

if (!(Test-Path $sunshineExe)) {
  throw "Sunshine executable not found at $sunshineExe"
}

Write-Host "Setting Sunshine credentials..."
$credsProc = Start-Process -FilePath $sunshineExe -ArgumentList $configPath, "--creds", "sunshine", $env:EPHEMERAL_SUNSHINE_PASSWORD -Wait -PassThru
if ($credsProc.ExitCode -ne 0) {
  throw "Sunshine credential setup failed with exit code $($credsProc.ExitCode)"
}
Write-Host "Sunshine credentials exit code: $($credsProc.ExitCode)"

Write-Host "Starting Sunshine..."
Start-Process -FilePath $sunshineExe -ArgumentList $configPath
