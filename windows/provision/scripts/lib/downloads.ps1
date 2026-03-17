function Download-File {
  param(
    [Parameter(Mandatory=$true)][string]$Url,
    [Parameter(Mandatory=$true)][string]$OutFile,
    [int]$Retries = 5,
    [int]$RetryDelaySeconds = 2,
    [string]$UserAgent = "Mozilla/5.0",
    [switch]$SkipIfExists
  )

  if (-not (Get-Command curl.exe -ErrorAction SilentlyContinue)) {
    throw "curl.exe not found. This script requires curl to be available."
  }

  if ($SkipIfExists -and (Test-Path $OutFile)) {
    Write-Host "File already downloaded: $OutFile"
    return
  }

  $outDir = Split-Path -Parent $OutFile
  if ($outDir -and -not (Test-Path $outDir)) {
    New-Item -ItemType Directory -Path $outDir -Force | Out-Null
  }

  Write-Host "Downloading $Url -> $OutFile"
  $oldEap = $ErrorActionPreference
  $ErrorActionPreference = 'Continue'
  & curl.exe -L --fail --retry $Retries --retry-delay $RetryDelaySeconds --silent --show-error -A $UserAgent -o "$OutFile" "$Url"
  $exit = $LASTEXITCODE
  $ErrorActionPreference = $oldEap

  if ($exit -ne 0) {
    throw "curl download failed ($exit): $Url"
  }
}
