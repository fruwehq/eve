$ProvisionPath  = "C:\Users\Administrator\provision"
$ScriptsPath    = "$ProvisionPath\scripts"
$StatePath      = "$ProvisionPath\state"
$LogsPath       = "$ProvisionPath\logs"
$StateFile      = "$StatePath\state.json"
$StepsPath      = "$ScriptsPath\steps"
$LogFile        = "$LogsPath\provision.log"
$RebootFlag     = "$StatePath\reboot.flag"
$TranscriptFile = "$LogsPath\transcript.log"

function Log($msg) {
  $ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
  "$ts $msg" | Tee-Object -FilePath $LogFile -Append
}

if (!(Test-Path $LogsPath)) {
  throw "Logs directory not found: $LogsPath"
}

# Start full transcript logging to capture ALL output
Start-Transcript -Path $TranscriptFile -Append -Force

if (!(Test-Path $StateFile)) {
  throw "State file not found: $StateFile"
}

if (!(Test-Path $StepsPath)) {
  throw "Steps directory not found: $StepsPath"
}

try {

  while ($true) {

    $State = Get-Content $StateFile | ConvertFrom-Json
    $CurrentStep = [int]$State.currentStep

    $StepFiles = Get-ChildItem $StepsPath -Filter "*.ps1" | Sort-Object Name

    if ($StepFiles.Count -eq 0) {
        throw "No step files found in: $StepsPath"
    }

    if ($CurrentStep -ge $StepFiles.Count) {
        Log "Provisioning complete."
        Stop-Transcript
        exit 0
    }

    $Step = $StepFiles[$CurrentStep]

    Log "Running step [$CurrentStep/$($StepFiles.Count-1)] $($Step.Name)"

    & $Step.FullName 2>&1 | ForEach-Object { Log $_ }

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
