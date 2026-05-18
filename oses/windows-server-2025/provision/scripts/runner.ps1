$ProvisionPath  = "C:\Users\Administrator\provision"
$ScriptsPath    = "$ProvisionPath\scripts"
$StatePath      = "$ProvisionPath\state"
$LogsPath       = "$ProvisionPath\logs"
$StateFile      = "$StatePath\state.json"
$StepsPath      = "$ScriptsPath\steps"
$LogFile        = "$LogsPath\provision.log"
$RebootFlag     = "$StatePath\reboot.flag"
$TranscriptFile = "$LogsPath\transcript.log"
$StatusFile     = "$StatePath\provision-status.json"
$ManifestFile   = "$StatePath\provision-manifest.json"

function Log($msg) {
  $ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
  "$ts $msg" | Tee-Object -FilePath $LogFile -Append
}

function Get-IsoNow {
  (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
}

function Write-ProvisionStatus {
  param(
    [Parameter(Mandatory=$true)]$StatusObj
  )
  $StatusObj | ConvertTo-Json -Depth 10 | Set-Content $StatusFile
}

function Update-StepStatus {
  param(
    [Parameter(Mandatory=$true)][int]$StepIndex,
    [Parameter(Mandatory=$true)][string]$Phase,
    [int]$ExitCode = -1
  )
  if (-not (Test-Path $StatusFile)) {
    Log "ERROR: status file missing during update"
    throw "Status file missing during update: $StatusFile"
  }
  $s = Get-Content $StatusFile | ConvertFrom-Json
  $ts = Get-IsoNow
  $entry = $s.steps[$StepIndex]
  $entry.phase = $Phase
  if ($Phase -eq "running") { $entry.started_at = $ts }
  if ($Phase -in @("succeeded","failed")) { $entry.ended_at = $ts }
  if ($ExitCode -ge 0) { $entry.exit_code = $ExitCode } else { $entry.exit_code = $null }
  Write-ProvisionStatus $s
}

function Finish-ProvisionStatus {
  param(
    [Parameter(Mandatory=$true)][string]$FinalStatus
  )
  if (-not (Test-Path $StatusFile)) {
    Log "ERROR: status file missing during finish"
    throw "Status file missing during finish: $StatusFile"
  }
  $s = Get-Content $StatusFile | ConvertFrom-Json
  $s.status = $FinalStatus
  $s.finished_at = Get-IsoNow
  Write-ProvisionStatus $s
}

function Test-Manifest {
  if (-not (Test-Path $ManifestFile)) {
    Log "No provision manifest found - continuing with step discovery (compatibility mode)."
    return
  }
  Log "Validating provision manifest..."

  $manifest = Get-Content $ManifestFile | ConvertFrom-Json

  if ($manifest.api_version -ne 1) {
    Log "ERROR: manifest api_version is '$($manifest.api_version)', expected '1'"
    throw "Manifest api_version mismatch"
  }

  if ($manifest.os_family -ne "windows") {
    Log "ERROR: manifest os_family is '$($manifest.os_family)', expected 'windows'"
    throw "Manifest os_family mismatch"
  }

  $actualFiles = @(Get-ChildItem $StepsPath -Filter "*.ps1" | Sort-Object Name)
  if ($manifest.steps.Count -ne $actualFiles.Count) {
    Log "ERROR: manifest declares $($manifest.steps.Count) steps but $($actualFiles.Count) step files found"
    throw "Manifest step count mismatch"
  }

  for ($i = 0; $i -lt $manifest.steps.Count; $i++) {
    $expected = $manifest.steps[$i]
    if ($expected.order -ne $i) {
      Log "ERROR: manifest step[$i] has order $($expected.order), expected $i"
      throw "Manifest step order mismatch at index $i"
    }
    $actualName = $actualFiles[$i].Name
    if ($expected.name -ne $actualName) {
      Log "ERROR: manifest step[$i] is '$($expected.name)', but execution step is '$actualName'"
      throw "Manifest step name mismatch at index $i"
    }
    $stepPath = Join-Path $StepsPath $expected.name
    if (-not (Test-Path $stepPath)) {
      Log "ERROR: manifest step '$($expected.name)' (index $i) not found in $StepsPath"
      throw "Manifest step not found: $($expected.name)"
    }
    $actualHash = (Get-FileHash -Path $stepPath -Algorithm SHA256).Hash.ToLower()
    $expectedHash = $expected.sha256.ToLower()
    if ($actualHash -ne $expectedHash) {
      Log "ERROR: manifest hash mismatch for step '$($expected.name)' (expected $expectedHash, got $actualHash)"
      throw "Manifest hash mismatch: $($expected.name)"
    }
  }

  Log "Manifest validated: $($manifest.steps.Count) steps, all hashes match."
}

if (!(Test-Path $LogsPath)) {
  throw "Logs directory not found: $LogsPath"
}

Start-Transcript -Path $TranscriptFile -Append -Force

if (!(Test-Path $StateFile)) {
  throw "State file not found: $StateFile"
}

if (!(Test-Path $StepsPath)) {
  throw "Steps directory not found: $StepsPath"
}

try {

  $StepFiles = Get-ChildItem $StepsPath -Filter "*.ps1" | Sort-Object Name

  if ($StepFiles.Count -eq 0) {
      throw "No step files found in: $StepsPath"
  }

  if (Test-Path $StatusFile) {
    $existing = Get-Content $StatusFile | ConvertFrom-Json
    if ($existing.api_version -ne 1) {
      throw "Existing status file has api_version '$($existing.api_version)', expected '1'"
    }
    if ($existing.status -notin @("running","done","failed")) {
      throw "Existing status file has invalid status '$($existing.status)'"
    }
    if ($existing.steps.Count -ne $StepFiles.Count) {
      throw "Existing status file has $($existing.steps.Count) steps, expected $($StepFiles.Count)"
    }
    for ($i = 0; $i -lt $StepFiles.Count; $i++) {
      if ($existing.steps[$i].step -ne $StepFiles[$i].Name) {
        throw "Existing status file step[$i] is '$($existing.steps[$i].step)', expected '$($StepFiles[$i].Name)'"
      }
    }
    $existing.status = "running"
    $existing.finished_at = $null
    Write-ProvisionStatus $existing
    Log "Resuming provisioning - preserved prior step status from existing status file."
  } else {
    $StatusSteps = @()
    foreach ($sf in $StepFiles) {
      $StatusSteps += @{ step = $sf.Name; phase = "pending"; started_at = $null; ended_at = $null; exit_code = $null }
    }
    $StatusObj = @{
      api_version = 1
      os_family   = "windows"
      started_at  = Get-IsoNow
      finished_at = $null
      status      = "running"
      steps       = $StatusSteps
    }
    Write-ProvisionStatus $StatusObj
  }

  try {
    Test-Manifest
  } catch {
    Log "ERROR: $($_.Exception.Message)"
    Finish-ProvisionStatus "failed"
    Stop-Transcript
    exit 1
  }

  while ($true) {

    $State = Get-Content $StateFile | ConvertFrom-Json
    $CurrentStep = [int]$State.currentStep

    if ($CurrentStep -ge $StepFiles.Count) {
        Finish-ProvisionStatus "done"
        Log "Provisioning complete."
        Stop-Transcript
        exit 0
    }

    $Step = $StepFiles[$CurrentStep]

    Log "Running step [$CurrentStep/$($StepFiles.Count-1)] $($Step.Name)"
    Update-StepStatus -StepIndex $CurrentStep -Phase "running"

    $stepError = $null
    $stepExitCode = 0
    try {
      $LASTEXITCODE = 0
      $savedEAP = $ErrorActionPreference
      $ErrorActionPreference = 'Stop'
      & $Step.FullName 2>&1 | ForEach-Object { Log $_ }
      $nativeExitCode = $LASTEXITCODE
      $stepSucceeded = $?
      $ErrorActionPreference = $savedEAP
      if ($nativeExitCode -ne 0) {
        $stepExitCode = $nativeExitCode
      } elseif (-not $stepSucceeded) {
        $stepExitCode = 1
      }
    } catch {
      $ErrorActionPreference = $savedEAP
      $stepError = $_
      $stepExitCode = 1
    }

    if ($stepExitCode -ne 0) {
      $errorDetail = if ($stepError) { $stepError.ToString() } else { "Step exited with code $stepExitCode" }
      Update-StepStatus -StepIndex $CurrentStep -Phase "failed" -ExitCode $stepExitCode
      Finish-ProvisionStatus "failed"
      Log "ERROR: $errorDetail"
      if ($stepError) { Log $stepError.ScriptStackTrace }
      Stop-Transcript
      throw $errorDetail
    }

    Update-StepStatus -StepIndex $CurrentStep -Phase "succeeded" -ExitCode 0

    $State.currentStep = $CurrentStep + 1
    $State | ConvertTo-Json | Set-Content $StateFile

    if (Test-Path $RebootFlag) {

        Remove-Item $RebootFlag

        Log "Reboot requested. Restarting..."

        Restart-Computer -Force
        exit 0
    }

  }

}

catch {

  Log "ERROR: $($_.Exception.Message)"
  Log $_.ScriptStackTrace
  Stop-Transcript
  throw

}
