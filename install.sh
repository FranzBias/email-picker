#!/usr/bin/env bash
##########################################################
##                Email Picker - install                ##
##        Install for the current user, no sudo         ##
##                   written in Bash                    ##
##                          🍕                          ##
##    by FranzBias 2025-2026 · github.com/FranzBias     ##
##            Licensed under the MIT License            ##
##          See LICENSE file for full license.          ##
##########################################################
# SPDX-License-Identifier: MIT
# Email Picker — installation for the current user only (no sudo).
# Why: one command puts the app in ~/.local/share/email-picker, your data in
# ~/.config/email-picker (never overwritten) and the menu entry
# email-picker.desktop (the name Lampo Mail looks for).
set -euo pipefail
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEST="${XDG_DATA_HOME:-$HOME/.local/share}/email-picker"
APPS="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
CONF="${XDG_CONFIG_HOME:-$HOME/.config}/email-picker"

mkdir -p "$DEST" "$APPS" "$CONF"
cp "$SRC/email-picker.py" "$DEST/"
chmod +x "$DEST/email-picker.py"

if [ ! -f "$CONF/emails.json" ]; then
    cp "$SRC/emails.example.json" "$CONF/emails.json"
    echo "✔ Example address list created: $CONF/emails.json (edit it!)"
else
    echo "✔ Your address list is untouched: $CONF/emails.json"
fi

sed -e "s|@APPDIR@|$DEST|g" "$SRC/email-picker.desktop.in" > "$APPS/email-picker.desktop"
command -v update-desktop-database >/dev/null && update-desktop-database "$APPS" 2>/dev/null || true

# find_spec only checks the packages exist: pystray/pynput need a display to import
if ! python3 -c "import importlib.util as u, sys; sys.exit(any(u.find_spec(m) is None for m in ('customtkinter','PIL','pynput','plyer','pystray')))" 2>/dev/null; then
    echo "⚠ Some Python packages are missing. Install them with:"
    echo "  python3 -m pip install --user -r \"$SRC/requirements.txt\""
    echo "  (on Debian 12+/LMDE/Mint 22 add --break-system-packages: it only writes to ~/.local)"
fi

echo "✔ Installed in $DEST"
echo "  Look for «Email Picker» in the menu, or run: python3 \"$DEST/email-picker.py\""
