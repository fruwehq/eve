$ErrorActionPreference = 'Stop'

Write-Host "#########################################################"
Write-Host "### Start 10"
Write-Host "#########################################################"

. "$PSScriptRoot\..\lib\downloads.ps1"

Write-Host "Ensuring Sunshine is installed and configured..."

$sunshineDir = "${env:ProgramFiles}\Sunshine"
$sunshineExe = Join-Path $sunshineDir "sunshine.exe"
$configPath = Join-Path $sunshineDir "config\sunshine.conf"
$secretsFile = "C:\Users\Administrator\provision\state\secrets.json"
$sunshinePassword = $env:EPHEMERAL_SUNSHINE_PASSWORD

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


if (-not (Select-String -Path $configPath -Pattern "^\s*origin_web_ui_allowed\s*=" -Quiet)) {
  Add-Content -Path $configPath -Value "`norigin_web_ui_allowed = wan`n"
}

# Set Sunshine Web UI credentials from the environment or secrets file.
# Use a fixed username to keep provisioning simple and reproducible.
if (-not $sunshinePassword -and (Test-Path $secretsFile)) {
  try {
    $secrets = Get-Content $secretsFile | ConvertFrom-Json
    $sunshinePassword = $secrets.sunshine_password
  } catch {
    throw "Failed to read Sunshine password from $secretsFile"
  }
}

if (-not $sunshinePassword) {
  throw "Sunshine password not provided. Set EPHEMERAL_SUNSHINE_PASSWORD or create $secretsFile with a sunshine_password field."
}

if (!(Test-Path $sunshineExe)) {
  throw "Sunshine executable not found at $sunshineExe"
}

Write-Host "Setting Sunshine credentials..."
$credsProc = Start-Process -FilePath $sunshineExe -ArgumentList $configPath, "--creds", "sunshine", $sunshinePassword -Wait -PassThru
if ($credsProc.ExitCode -ne 0) {
  throw "Sunshine credential setup failed with exit code $($credsProc.ExitCode)"
}
Write-Host "Sunshine credentials exit code: $($credsProc.ExitCode)"

Write-Host "Starting Sunshine process..."
Start-Process -FilePath $sunshineExe

# Wait for Sunshine Web UI port to become available
Write-Host "Waiting for Sunshine API..."
$maxAttempts = 10
$attempt = 0
$ready = $false
$lastWaitError = $null

while (-not $ready -and $attempt -lt $maxAttempts) {
  $attempt++
  $client = $null
  try {
    Write-Host "Sunshine wait attempt $attempt/$maxAttempts..."
    $client = New-Object System.Net.Sockets.TcpClient
    $async = $client.BeginConnect("127.0.0.1", 47990, $null, $null)
    if (-not $async.AsyncWaitHandle.WaitOne(2000, $false)) {
      throw "TCP connect timed out"
    }
    $client.EndConnect($async)
    Write-Host "Sunshine TCP port is reachable."
    $ready = $true
    break
  } catch {
    $lastWaitError = $_.Exception.Message
    Write-Host "Sunshine wait attempt $attempt failed: $lastWaitError"
  } finally {
    if ($client) {
      $client.Close()
    }
  }
  Start-Sleep -Seconds 2
}

if (-not $ready) {
  if ($lastWaitError) {
    Write-Warning "Sunshine API did not become ready in time. Last error: $lastWaitError. Skipping auto pairing."
  } else {
    Write-Warning "Sunshine API did not become ready in time. Skipping auto pairing."
  }
} else {
  Write-Host "Sunshine API ready. Sending pairing PIN..."

  $pairBody = @{ pin = "1234"; name = "ephemeral-client" } | ConvertTo-Json -Compress

  try {
    $pairResponseFile = Join-Path $env:TEMP "sunshine-pair-response.json"
    if (Test-Path $pairResponseFile) {
      Remove-Item $pairResponseFile -Force -ErrorAction SilentlyContinue
    }

    $httpCode = & curl.exe -sS -k -u "sunshine:$sunshinePassword" -H "Content-Type: application/json" -d $pairBody -o $pairResponseFile -w "%{http_code}" "https://127.0.0.1:47990/api/pin"
    $curlExitCode = $LASTEXITCODE
    $responseBody = if (Test-Path $pairResponseFile) { Get-Content -Path $pairResponseFile -Raw } else { "" }

    if ($curlExitCode -ne 0) {
      throw "curl exited with code $curlExitCode. Response: $responseBody"
    }

    if ($httpCode -notmatch "^2") {
      throw "Sunshine pairing API returned HTTP $httpCode. Response: $responseBody"
    }

    Write-Host "Pairing PIN submitted successfully."
    if ($responseBody) {
      Write-Host $responseBody
    }
  } catch {
    Write-Warning "Failed to submit pairing PIN: $($_.Exception.Message)"
  }
}

Write-Host "---------------------------------------------------------"
Write-Host "END 10"
Write-Host "---------------------------------------------------------"
Write-Host ""
