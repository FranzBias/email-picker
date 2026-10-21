# Changelog

## 2.1.0 — 2026-10-20
- **New app**, replacing the old `choose_email.py` dropdown: addresses in tabs from `emails.json`, global search, tray icon, global shortcut, 4 themes, remembered window geometry.
- Tray: uses AyatanaAppIndicatorGlib when installed, otherwise pystray with the "libayatana-appindicator is deprecated" warning silenced.
- Data in `~/.config/email-picker/` (or next to the script, portable mode).
- `install.sh` / `uninstall.sh` (no sudo); menu entry `email-picker.desktop`.
- `emails.example.json` with fictitious addresses; `emails.json` and `config.json` are git-ignored.
- Unselected tabs are readable in every theme.

## 1.x — 2025
- `choose_email.py`: one dropdown with addresses written in the script.
