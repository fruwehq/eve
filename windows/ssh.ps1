# Install OpenSSH Server
Write-Host "Installing OpenSSH Server..."
#
# --- Install user's SSH public key ---
# Replace the value below with your actual public key
$PublicKey = "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABAQCYc/2dMdwNt2Dy0loZRhGGFYIHF2aITaLD2Bb442pjiDZrx+7/h5Av0FRu5CMvI24x1K69LiiUfKLeQMrrdp/JPbWi1b47i/J9tNKmZMs7u6Arni8o+vdKERO+y6GIPDnXDkBTr2qYo1NqWX8CKnE2Tg0Gun4kWuSO9EcUJvI5KRagoQGrCf1NrOLjrc9gnVDjSW1n+VRO4nV4pJYvh0yBMhDSKvNisxHj714WCZl/cwO8uKw9MevVsKqQCS1UU03NYy12vmv75kgkVc6L4lOhxEZ2nOj4gHjnGaMal1C5WF9ZOtZTA9OTewvmnaAkHu4QKv9DcmZg3iwdR/7Ewn1Z chris@fruwe.com"

$adminAuthKeys = "C:\ProgramData\ssh\administrators_authorized_keys"

Write-Host "Installing SSH authorized_keys..."

if (-not (Test-Path "C:\ProgramData\ssh")) {
    New-Item -ItemType Directory -Path "C:\ProgramData\ssh" -Force | Out-Null
}

if (-not (Test-Path $adminAuthKeys)) {
    New-Item -ItemType File -Path $adminAuthKeys -Force | Out-Null
}

if (-not (Select-String -Path $adminAuthKeys -Pattern ([regex]::Escape($PublicKey)) -Quiet -ErrorAction SilentlyContinue)) {
    Add-Content -Path $adminAuthKeys -Value $PublicKey
}

icacls $adminAuthKeys /inheritance:r | Out-Null
icacls $adminAuthKeys /grant "Administrators:F" | Out-Null
icacls $adminAuthKeys /grant "SYSTEM:F" | Out-Null

Add-WindowsCapability -Online -Name OpenSSH.Server~~~~0.0.1.0

# Enable and start the SSH service
Write-Host "Starting SSH service..."
Start-Service sshd
Set-Service -Name sshd -StartupType Automatic

# Open firewall port
Write-Host "Opening firewall port 22..."
if (Get-NetFirewallRule -Name "OpenSSH-Server-In-TCP" -ErrorAction SilentlyContinue) {
    Remove-NetFirewallRule -Name "OpenSSH-Server-In-TCP"
}

New-NetFirewallRule `
  -Name "OpenSSH-Server-In-TCP" `
  -DisplayName "OpenSSH SSH Server (sshd)" `
  -Enabled True `
  -Direction Inbound `
  -Protocol TCP `
  -Action Allow `
  -LocalPort 22 `
  -Profile Any | Out-Null

# Ensure sshd_config allows PowerShell
$config = "C:\ProgramData\ssh\sshd_config"

if (Test-Path $config) {
    if (-not (Select-String -Path $config -Pattern "^PubkeyAuthentication\s+yes" -Quiet)) {
        Add-Content $config "`nPubkeyAuthentication yes"
    }

    # Ensure the administrator Match block exists for key authentication
    if (-not (Select-String -Path $config -Pattern "Match Group administrators" -Quiet)) {
        Add-Content $config "`nMatch Group administrators"
        Add-Content $config "    AuthorizedKeysFile __PROGRAMDATA__/ssh/administrators_authorized_keys"
    }

    if (-not (Select-String -Path $config -Pattern "Subsystem\s+powershell" -Quiet)) {
        Add-Content $config "`nSubsystem powershell C:/Program Files/PowerShell/7/pwsh.exe -sshs -NoLogo"
    }
}

# Install PowerShell 7 if it is not already present
if (-not (Test-Path "C:\Program Files\PowerShell\7\pwsh.exe")) {
    Write-Host "Installing PowerShell 7..."
    winget install --id Microsoft.PowerShell --source winget --accept-package-agreements --accept-source-agreements
}

# Configure PowerShell profile for nicer SSH behavior
$profileDir = "C:\Users\Administrator\Documents\PowerShell"
$profilePath = Join-Path $profileDir "Microsoft.PowerShell_profile.ps1"

if (-not (Test-Path $profileDir)) {
    New-Item -ItemType Directory -Path $profileDir -Force | Out-Null
}

if (-not (Test-Path $profilePath)) {
    New-Item -ItemType File -Path $profilePath -Force | Out-Null
}

$ctrlDLine = 'Set-PSReadLineKeyHandler -Key Ctrl+d -Function DeleteCharOrExit'
if (-not (Select-String -Path $profilePath -Pattern ([regex]::Escape($ctrlDLine)) -Quiet -ErrorAction SilentlyContinue)) {
    Add-Content -Path $profilePath -Value $ctrlDLine
}

New-ItemProperty `
  -Path "HKLM:\SOFTWARE\OpenSSH" `
  -Name DefaultShell `
  -Value "C:\Program Files\PowerShell\7\pwsh.exe" `
  -PropertyType String `
  -Force

# Enable ANSI colors for PowerShell over SSH (match normal PowerShell colors)
New-ItemProperty `
  -Path "HKCU:\Console" `
  -Name VirtualTerminalLevel `
  -Value 1 `
  -PropertyType DWORD `
  -Force | Out-Null

# Add SFTP subsystem if missing
if (-not (Select-String -Path $config -Pattern '^\s*Subsystem\s+sftp\s+' -Quiet)) {
    Add-Content $config "`nSubsystem sftp sftp-server.exe"
}

# Restart SSH service
Restart-Service sshd

Write-Host "SSH setup complete."
Write-Host "You can now connect using:"
Write-Host "ssh Administrator@<SERVER_IP>"
