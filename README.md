# ephemeral-cloud-gaming

```bash
docker run -it mcr.microsoft.com/dotnet/sdk:9.0 pwsh

ssh vultr

ssh vultr 'Remove-Item -Recurse -Force C:\provision\*'
scp -r ~/src/personal/ephemeral-cloud-gaming/windows/provision/* vultr:/C:/provision/

ssh vultr "pwsh C:\provision\bootstrap.ps1"
```

## SSH config

```
Host vultr
  User Administrator
  HostName xxx.xxx.xxx.xxx
  UseKeychain yes
  AddKeysToAgent yes
  IdentityFile ~/.ssh/id_xxx
  ServerAliveInterval 10
```
