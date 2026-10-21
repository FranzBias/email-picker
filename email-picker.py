#!/usr/bin/env python3
##########################################################
##                     Email Picker                     ##
##         Your email addresses, one click away         ##
##                 written in Python 3                  ##
##                          🍕                          ##
##    by FranzBias 2025-2026 · github.com/FranzBias     ##
##            Licensed under the MIT License            ##
##          See LICENSE file for full license.          ##
##########################################################
# SPDX-License-Identifier: MIT
"""
Email-Picker v2.1.1 — FranzBias / code-x.md

Why this exists:
    Franz uses many email addresses (personal, projects, services). Typing them
    by hand is slow and error-prone. Email Picker keeps them grouped in tabs
    (emails.json) and copies one to the clipboard with a single click, from a
    tray icon or a global shortcut.

What changed in 2.1:
    - Tray icon: uses the new AyatanaAppIndicatorGlib library when it is
      installed; otherwise falls back to pystray (AyatanaAppIndicator3) and
      silences its "libayatana-appindicator is deprecated" warning, which is
      harmless but noisy in the terminal.
    - Data files: next to the script if emails.json is there, otherwise in
      ~/.config/email-picker/ (where install.sh puts them).
    - Unselected tabs are readable in every theme (own colour per theme).
    - Comments translated to English.
"""

import json
import os
import sys
import signal
import threading
import subprocess
from pathlib import Path

import customtkinter as ctk
from pynput import keyboard as kb
from plyer import notification
from PIL import Image, ImageDraw

# ── Paths ───────────────────────────────────────────────────────────────────
BASE_DIR    = Path(__file__).resolve().parent
CONFIG_HOME = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "email-picker"
# Data lives next to the script when emails.json is there (portable setup);
# otherwise in ~/.config/email-picker (install.sh puts it there, and Lampo Mail
# looks for it there too).
DATA_DIR    = BASE_DIR if (BASE_DIR / "emails.json").exists() else CONFIG_HOME
EMAILS_FILE = DATA_DIR / "emails.json"
CONFIG_FILE = DATA_DIR / "config.json"
ICON_FILE   = BASE_DIR / "icon_check.png"
CACHE_DIR   = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "email-picker"

APP_ID = "email-picker"

# ── code-x.md brand themes ──────────────────────────────────────────────────
THEMES = {
    "dark": {
        "bg":       "#0d1117",
        "bg2":      "#161b22",
        "fg":       "#e6edf3",
        "accent":   "#86BE43",
        "accent2":  "#e8c84a",
        "btn_fg":   "#0d1117",
        "tab_sel":  "#86BE43",
        "tab_txt":  "#0d1117",
        "tab_unsel":"#8b949e",
        "search_bg":"#161b22",
        "entry_bg": "#21262d",
        "hover":    "#238636",
    },
    "light": {
        "bg":       "#ffffff",
        "bg2":      "#f0f0f0",
        "fg":       "#1a1a1a",
        "accent":   "#5a9e1a",
        "accent2":  "#c8a800",
        "btn_fg":   "#ffffff",
        "tab_sel":  "#5a9e1a",
        "tab_txt":  "#ffffff",
        "tab_unsel":"#6e6e6e",
        "search_bg":"#f0f0f0",
        "entry_bg": "#e0e0e0",
        "hover":    "#4a8a0a",
    },
    "mint": {
        "bg":       "#1e2b12",
        "bg2":      "#253515",
        "fg":       "#d4f0a0",
        "accent":   "#86BE43",
        "accent2":  "#e8c84a",
        "btn_fg":   "#1e2b12",
        "tab_sel":  "#86BE43",
        "tab_txt":  "#1e2b12",
        "tab_unsel":"#7d9a5a",
        "search_bg":"#253515",
        "entry_bg": "#2e4018",
        "hover":    "#6aa030",
    },
    "system": None,  # resolved at runtime
}


def resolve_system_theme():
    """Guess whether the desktop (Cinnamon/GTK) uses a dark or light theme."""
    try:
        out = subprocess.run(
            ["gsettings", "get", "org.cinnamon.desktop.interface", "gtk-theme"],
            capture_output=True, text=True, timeout=2
        )
        theme_name = out.stdout.strip().lower()
        if "dark" in theme_name:
            return THEMES["dark"]
        return THEMES["light"]
    except Exception:
        return THEMES["dark"]


def load_json(path, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def save_config(cfg):
    try:
        CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"[Email-Picker] cannot save config: {e}", file=sys.stderr)


def silence_appindicator_deprecation():
    """Drop the 'libayatana-appindicator is deprecated' GLib warning.

    The old AyatanaAppIndicator3 library (used by pystray) prints it once at
    startup. It is only a notice for developers; the tray works fine.
    Every other warning from that domain is still printed.
    """
    try:
        from gi.repository import GLib
    except Exception:
        return

    def _handler(domain, level, message, *_):
        if "is deprecated" in (message or ""):
            return
        GLib.log_default_handler(domain, level, message)

    try:
        GLib.log_set_handler("libayatana-appindicator",
                             GLib.LogLevelFlags.LEVEL_WARNING, _handler)
    except Exception:
        pass


DEFAULT_CONFIG = {
    "theme": "dark",
    "shortcut": "<ctrl>+<shift>+e",
    "search_position": "top",
    "window_x": None,
    "window_y": None,
    "window_width": 480,
    "window_height": 680,
}

DEFAULT_EMAILS = {"tabs": []}


class EmailPickerApp:
    def __init__(self):
        self.config = {**DEFAULT_CONFIG, **load_json(CONFIG_FILE, DEFAULT_CONFIG)}
        self.data = load_json(EMAILS_FILE, DEFAULT_EMAILS)
        self.tabs_data = sorted(self.data.get("tabs", []), key=lambda t: t.get("order", 0))

        theme_name = self.config.get("theme", "dark")
        self.theme = resolve_system_theme() if theme_name == "system" else THEMES.get(theme_name, THEMES["dark"])

        ctk.set_appearance_mode("dark" if theme_name != "light" else "light")
        self.app = ctk.CTk()
        self.app.title("Email Picker — code-x.md")
        self._apply_geometry()
        self.app.configure(fg_color=self.theme["bg"])
        self.app.protocol("WM_DELETE_WINDOW", self.hide_window)

        self.tray_icon = None        # pystray backend
        self.glib_indicator = None   # AyatanaAppIndicatorGlib backend
        self.glib_loop = None
        self.hotkey_listener = None
        self.entry_buttons = []  # (name, email, tab_label, widget) for global search

        self._build_ui()

    # ── Window geometry ──────────────────────────────────────────────────
    def _apply_geometry(self):
        w = self.config.get("window_width", 480)
        h = self.config.get("window_height", 680)
        x = self.config.get("window_x")
        y = self.config.get("window_y")
        if x is not None and y is not None:
            self.app.geometry(f"{w}x{h}+{x}+{y}")
        else:
            self.app.geometry(f"{w}x{h}")

    def _save_geometry(self):
        try:
            self.config["window_width"] = self.app.winfo_width()
            self.config["window_height"] = self.app.winfo_height()
            self.config["window_x"] = self.app.winfo_x()
            self.config["window_y"] = self.app.winfo_y()
            save_config(self.config)
        except Exception:
            pass

    # ── UI ───────────────────────────────────────────────────────────────
    def _build_ui(self):
        t = self.theme

        search_frame = ctk.CTkFrame(self.app, fg_color=t["search_bg"])
        self.search_var = ctk.StringVar()
        self.search_entry = ctk.CTkEntry(
            search_frame, textvariable=self.search_var,
            placeholder_text="🔎 Cerca email o nome…",
            fg_color=t["entry_bg"], text_color=t["fg"],
            border_color=t["accent"],
        )
        self.search_entry.pack(fill="x", padx=10, pady=8)
        self.search_var.trace_add("write", lambda *_: self._on_search())

        pos = self.config.get("search_position", "top")
        if pos == "top":
            search_frame.pack(fill="x", side="top")
        else:
            search_frame.pack(fill="x", side="bottom")

        self.tabview = ctk.CTkTabview(
            self.app, fg_color=t["bg2"],
            segmented_button_selected_color=t["tab_sel"],
            segmented_button_selected_hover_color=t["hover"],
            # Unselected tabs need their own colour: tab_txt is dark on dark
            # themes (and white on light), so on bg2 it was almost invisible.
            segmented_button_unselected_color=t["tab_unsel"],
            segmented_button_unselected_hover_color=t["hover"],
            text_color=t["tab_txt"],
        )
        self.tabview.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        if not self.tabs_data:
            self.tabview.add("Nessuna email")
            ctk.CTkLabel(
                self.tabview.tab("Nessuna email"),
                text="Nessuna email configurata.\nModifica emails.json per aggiungerne.",
                text_color=t["fg"],
            ).pack(pady=30)
            return

        self.tab_frames = {}
        for tab in self.tabs_data:
            label = tab.get("label", tab.get("id", "Tab"))
            self.tabview.add(label)
            scroll = ctk.CTkScrollableFrame(self.tabview.tab(label), fg_color="transparent")
            scroll.pack(fill="both", expand=True)
            self.tab_frames[label] = scroll
            self._populate_tab(scroll, tab.get("entries", []), label)

        first_label = self.tabs_data[0].get("label", self.tabs_data[0].get("id"))
        self.tabview.set(first_label)

    def _populate_tab(self, frame, entries, tab_label):
        t = self.theme
        for entry in entries:
            name = entry.get("name", "")
            email = entry.get("email", "")
            row = ctk.CTkFrame(frame, fg_color="transparent")
            row.pack(fill="x", pady=3, padx=4)
            btn = ctk.CTkButton(
                row, text=f"{name}\n{email}" if name else email,
                fg_color=t["accent"], text_color=t["btn_fg"],
                hover_color=t["hover"],
                command=lambda e=email, n=name: self._copy(e, n),
                anchor="w",
            )
            btn.pack(fill="x")
            self.entry_buttons.append((name, email, tab_label, btn))

    # ── Global search ────────────────────────────────────────────────────
    def _on_search(self):
        query = self.search_var.get().strip().lower()
        if not query:
            for _, _, _, btn in self.entry_buttons:
                btn.master.pack(fill="x", pady=3, padx=4)
            return
        for name, email, _, btn in self.entry_buttons:
            match = query in name.lower() or query in email.lower()
            if match:
                btn.master.pack(fill="x", pady=3, padx=4)
            else:
                btn.master.pack_forget()

    # ── Copy to clipboard ────────────────────────────────────────────────
    def _copy(self, email, name=""):
        self.app.clipboard_clear()
        self.app.clipboard_append(email)
        self.app.update()
        try:
            notification.notify(
                title="Email copiata",
                message=email,
                app_name="Email Picker",
                timeout=3,
            )
        except Exception:
            pass
        self.hide_window()

    # ── Show / hide window ───────────────────────────────────────────────
    def hide_window(self):
        self._save_geometry()
        self.app.withdraw()

    def show_window(self):
        self.app.after(0, self._show_window_main_thread)

    def _show_window_main_thread(self):
        self.app.deiconify()
        self._apply_geometry()
        self.app.lift()
        self.app.focus_force()
        self.search_entry.focus_set()

    def toggle_window(self):
        self.app.after(0, self._toggle_main_thread)

    def _toggle_main_thread(self):
        if self.app.state() == "withdrawn":
            self._show_window_main_thread()
        else:
            self.hide_window()

    # ── System tray ──────────────────────────────────────────────────────
    def _make_icon_image(self):
        if ICON_FILE.exists():
            try:
                return Image.open(ICON_FILE)
            except Exception:
                pass
        img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        draw.ellipse((4, 4, 60, 60), fill=self.theme["accent"])
        return img

    def _icon_path(self):
        """AppIndicator wants an icon name or a file path: write a PNG to the cache."""
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        path = CACHE_DIR / "tray-icon.png"
        self._make_icon_image().save(path)
        return path

    def _start_glib_indicator(self):
        """Tray icon through the new AyatanaAppIndicatorGlib (GMenu + GActions).

        Returns True on success, False if the library is not installed
        (Debian 13 does not ship it yet) or anything else goes wrong.
        """
        try:
            import gi
            gi.require_version("AyatanaAppIndicatorGlib", "2.0")
            from gi.repository import AyatanaAppIndicatorGlib as AIG, Gio, GLib
        except Exception:
            return False
        try:
            ind = AIG.Indicator.new(APP_ID, str(self._icon_path()),
                                    AIG.IndicatorCategory.APPLICATION_STATUS)
            actions = Gio.SimpleActionGroup()
            for action_name, callback in (("show", self.show_window), ("quit", self.quit_app)):
                action = Gio.SimpleAction.new(action_name, None)
                action.connect("activate", lambda *_a, cb=callback: cb())
                actions.add_action(action)
            menu = Gio.Menu()
            menu.append("Mostra", "indicator.show")
            menu.append("Esci", "indicator.quit")
            ind.set_actions(actions)
            ind.set_menu(menu)
            ind.set_status(AIG.IndicatorStatus.ACTIVE)

            self.glib_indicator = ind
            self.glib_loop = GLib.MainLoop()
            threading.Thread(target=self.glib_loop.run, daemon=True).start()
            return True
        except Exception as e:
            print(f"[Email-Picker] AyatanaAppIndicatorGlib failed, using pystray: {e}", file=sys.stderr)
            self.glib_indicator = None
            return False

    def _tray_show(self, icon, item):
        self.show_window()

    def _tray_quit(self, icon, item):
        self.quit_app()

    def _start_pystray(self):
        silence_appindicator_deprecation()
        try:
            import pystray
        except Exception as e:
            print(f"[Email-Picker] tray not available (the app still works): {e}", file=sys.stderr)
            return
        menu = pystray.Menu(
            pystray.MenuItem("Mostra", self._tray_show, default=True),
            pystray.MenuItem("Esci", self._tray_quit),
        )
        self.tray_icon = pystray.Icon(APP_ID, self._make_icon_image(), "Email Picker", menu)

        def _run_tray_safe():
            try:
                self.tray_icon.run()
            except Exception as e:
                print(f"[Email-Picker] tray not available (the app still works): {e}", file=sys.stderr)

        threading.Thread(target=_run_tray_safe, daemon=True).start()

    def start_tray(self):
        if not self._start_glib_indicator():
            self._start_pystray()

    # ── Global shortcut ──────────────────────────────────────────────────
    def start_hotkey(self):
        shortcut = self.config.get("shortcut", "<ctrl>+<shift>+e")
        try:
            self.hotkey_listener = kb.GlobalHotKeys({shortcut: self.toggle_window})
            self.hotkey_listener.start()
        except Exception as e:
            print(f"[Email-Picker] global shortcut not available: {e}", file=sys.stderr)

    # ── Clean shutdown ───────────────────────────────────────────────────
    def quit_app(self):
        self._save_geometry()
        if self.tray_icon:
            self.tray_icon.stop()
        if self.glib_loop:
            self.glib_loop.quit()
        if self.hotkey_listener:
            self.hotkey_listener.stop()
        self.app.after(0, self.app.destroy)

    def run(self):
        self.start_tray()
        self.start_hotkey()
        self.app.bind("<Escape>", lambda e: self.hide_window())
        signal.signal(signal.SIGINT, lambda *_: self.quit_app())
        signal.signal(signal.SIGTERM, lambda *_: self.quit_app())
        self.app.mainloop()


if __name__ == "__main__":
    picker = EmailPickerApp()
    picker.run()
