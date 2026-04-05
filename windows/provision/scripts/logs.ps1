$logsPath = "C:\Users\Administrator\provision\logs"

if (!(Test-Path $logsPath)) {
  Write-Output "No logs directory found."
  exit 0
}

Get-ChildItem -Path $logsPath -File |
  Sort-Object Name |
  ForEach-Object {
    Write-Output ("==== " + $_.Name + " ====")
    Get-Content -Path $_.FullName
  }
