#!/usr/bin/env bash
##########################################################
##               Email Picker - uninstall               ##
##            Remove the app, keep your list            ##
##                   written in Bash                    ##
##                          🍕                          ##
##    by FranzBias 2025-2026 · github.com/FranzBias     ##
##            Licensed under the MIT License            ##
##          See LICENSE file for full license.          ##
##########################################################
# SPDX-License-Identifier: MIT
# Email Picker — removes the app and the menu entry.
# Why: a clean way back. Your address list in ~/.config/email-picker is kept
# unless you pass --purge.
set -euo pipefail
DEST="${XDG_DATA_HOME:-$HOME/.local/share}/email-picker"
APPS="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
CONF="${XDG_CONFIG_HOME:-$HOME/.config}/email-picker"

rm -rf "$DEST"
rm -f "$APPS/email-picker.desktop"
command -v update-desktop-database >/dev/null && update-desktop-database "$APPS" 2>/dev/null || true
echo "✔ Email Picker removed."

if [ "${1:-}" = "--purge" ]; then
    rm -rf "$CONF"
    echo "✔ Data removed too: $CONF"
else
    echo "  Your data is still in $CONF (use --purge to remove it)."
fi
