# Changelog

## 2.2.0 — 2026-10-23
- **Edit mode** (✏️ next to the search bar): add, edit, delete and reorder addresses; add, rename, reorder and delete tabs. Duplicate and invalid addresses are refused; deleting a tab asks for confirmation and says how many addresses it holds.
- Safe saving (Lampo Mail writes the same file): emails.json is re-checked before every change and reloaded if another program changed it; a backup is kept before every save (last 20, in `~/.local/state/email-picker/backups/`); atomic write in the same layout Lampo Mail uses.
- Single instance: launching Email Picker again just shows the window already open.
- Search: clearing it keeps the original order; if the current tab has no match, it jumps to the first tab that has one.
- Two-line buttons aligned left.

## 2.1.1 — 2026-10-21
- Signature banner at the top of `email-picker.py`, `install.sh` and `uninstall.sh` (with SPDX licence tag). No change in behaviour.

## 2.1.0 — 2026-10-20
- **New app**, replacing the old `choose_email.py` dropdown: addresses in tabs from `emails.json`, global search, tray icon, global shortcut, 4 themes, remembered window geometry.
- Tray: uses AyatanaAppIndicatorGlib when installed, otherwise pystray with the "libayatana-appindicator is deprecated" warning silenced.
- Data in `~/.config/email-picker/` (or next to the script, portable mode).
- `install.sh` / `uninstall.sh` (no sudo); menu entry `email-picker.desktop`.
- `emails.example.json` with fictitious addresses; `emails.json` and `config.json` are git-ignored.
- Unselected tabs are readable in every theme.

## 1.x — 2025
- `choose_email.py`: one dropdown with addresses written in the script.
