#!/usr/bin/env bash
set -euo pipefail
# shellcheck source=../lib/common.sh
. "$PROVISION_ROOT/scripts/lib/common.sh"

skip_unless_pkg macos-desktop-theme

log "### 49_macos_desktop_theme: installing macOS-like GNOME defaults"

apt_install \
  gnome-shell-extension-dashtodock \
  gnome-tweaks \
  papirus-icon-theme

mkdir -p "$HOME/.local/bin" "$HOME/.config/autostart"
cat >"$HOME/.local/bin/egame-gnome-macos-theme" <<'EOF'
#!/usr/bin/env sh
set -eu

if ! command -v gsettings >/dev/null 2>&1; then
  exit 0
fi

gsettings set org.gnome.desktop.interface gtk-theme 'Yaru-blue' 2>/dev/null || true
gsettings set org.gnome.desktop.interface icon-theme 'Papirus' 2>/dev/null || true
gsettings set org.gnome.desktop.interface color-scheme 'prefer-dark' 2>/dev/null || true
gsettings set org.gnome.desktop.wm.preferences button-layout 'close,minimize,maximize:' 2>/dev/null || true
gsettings set org.gnome.shell.extensions.dash-to-dock dock-position 'BOTTOM' 2>/dev/null || true
gsettings set org.gnome.shell.extensions.dash-to-dock extend-height false 2>/dev/null || true
gsettings set org.gnome.shell.extensions.dash-to-dock dash-max-icon-size 48 2>/dev/null || true
EOF
chmod +x "$HOME/.local/bin/egame-gnome-macos-theme"

cat >"$HOME/.config/autostart/egame-gnome-macos-theme.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Apply macOS-like GNOME defaults
Exec=$HOME/.local/bin/egame-gnome-macos-theme
Hidden=false
NoDisplay=true
X-GNOME-Autostart-enabled=true
EOF

log "### 49_macos_desktop_theme: done"
