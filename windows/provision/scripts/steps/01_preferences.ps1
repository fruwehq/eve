Write-Host "Configuring Windows UI (dark mode + black background)..."

# --- 1) Enable dark mode (apps + system) ---
$personalize = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"

New-Item -Path $personalize -Force | Out-Null

# 0 = dark mode
Set-ItemProperty -Path $personalize -Name AppsUseLightTheme -Value 0 -Type DWord
Set-ItemProperty -Path $personalize -Name SystemUsesLightTheme -Value 0 -Type DWord

Write-Host "Dark mode enabled."

# --- 2) Create pure black wallpaper ---
$wallpaperPath = "$env:USERPROFILE\provision\black.jpg"

Add-Type -AssemblyName System.Drawing

$bmp = New-Object System.Drawing.Bitmap 1920,1080
$graphics = [System.Drawing.Graphics]::FromImage($bmp)
$graphics.Clear([System.Drawing.Color]::Black)
$bmp.Save($wallpaperPath, [System.Drawing.Imaging.ImageFormat]::Jpeg)

$graphics.Dispose()
$bmp.Dispose()

Write-Host "Black wallpaper created at $wallpaperPath"

# --- 3) Apply wallpaper ---
Add-Type @"
using System.Runtime.InteropServices;
public class Wallpaper {
  [DllImport("user32.dll", SetLastError = true)]
  public static extern bool SystemParametersInfo(int uAction, int uParam, string lpvParam, int fuWinIni);
}
"@

# 20 = SPI_SETDESKWALLPAPER
# 3  = update + broadcast change
[Wallpaper]::SystemParametersInfo(20, 0, $wallpaperPath, 3)

Write-Host "Wallpaper applied."

# --- 4) Optional: disable transparency (cleaner look on servers) ---
Set-ItemProperty -Path "HKCU:\Software\Microsoft\Windows\CurrentVersion\Themes\Personalize" `
  -Name EnableTransparency -Value 0 -Type DWord

Write-Host "Transparency disabled."

Write-Host "UI configuration complete."
