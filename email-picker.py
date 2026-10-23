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
Email-Picker v2.2.0 — FranzBias / code-x.md

Why this exists:
    Franz uses many email addresses (personal, projects, services). Typing them
    by hand is slow and error-prone. Email Picker keeps them grouped in tabs
    (emails.json) and copies one to the clipboard with a single click, from a
    tray icon or a global shortcut.

What changed in 2.2.0:
    - Edit mode (✏️ next to the search bar): add, edit, delete and reorder
      addresses; add, rename, reorder and delete tabs. Without editing the
      JSON file by hand.
    - Safe saving, because Lampo Mail writes the same file: the file is
      re-checked before every change, backed up before every save, written
      atomically and in the same layout Lampo Mail uses.
    - Single instance: launching it again only shows the window already open.
    - Search: clearing it keeps the original order; if the current tab has no
      match, it jumps to the first tab that has one.

Earlier (2.1): AyatanaAppIndicatorGlib tray with pystray fallback; data in
~/.config/email-picker/ unless emails.json sits next to the script.
"""

import json
import os
import re
import sys
import time
import shutil
import signal
import socket
import threading
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path
from tkinter import messagebox

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
BACKUP_DIR  = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local" / "state")) / "email-picker" / "backups"
BACKUPS_KEPT = 20

APP_ID = "email-picker"
SOCKET_NAME = f"\0{APP_ID}-{os.getuid()}"   # abstract Unix socket: no file left behind
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

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
        "danger":   "#e5534b",
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
        "danger":   "#c62828",
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
        "danger":   "#e5534b",
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


# ── emails.json: read, normalise, write ─────────────────────────────────────
def normalise_emails(data):
    """Always return {"tabs": [...]} with tabs sorted by 'order' and an 'entries' list each."""
    if not isinstance(data, dict):
        data = {"tabs": []}
    tabs = [t for t in data.get("tabs", []) if isinstance(t, dict)]
    for t in tabs:
        if not isinstance(t.get("entries"), list):
            t["entries"] = []
    tabs.sort(key=lambda t: t.get("order", 0))
    data["tabs"] = tabs
    return data


def dump_emails(data):
    """Serialise emails.json in the layout Lampo Mail also writes
    (indent 2, one address per line), so the two apps never fight over style.
    Same logic as _dump_email_picker() in Lampo Mail (by FranzBias)."""
    lines = ["{", '  "tabs": [']
    tabs = data.get("tabs", [])
    for ti, tab in enumerate(tabs):
        lines.append("    {")
        for k in ("id", "label", "order"):
            if k in tab:
                lines.append(f'      {json.dumps(k)}: {json.dumps(tab[k], ensure_ascii=False)},')
        for k, v in tab.items():
            if k not in ("id", "label", "order", "entries"):
                lines.append(f'      {json.dumps(k)}: {json.dumps(v, ensure_ascii=False)},')
        lines.append('      "entries": [')
        ents = tab.get("entries", [])
        for ei, e in enumerate(ents):
            comma = "," if ei < len(ents) - 1 else ""
            lines.append("        " + json.dumps(e, ensure_ascii=False) + comma)
        lines.append("      ]")
        lines.append("    }" + ("," if ti < len(tabs) - 1 else ""))
    lines.append("  ]")
    lines.append("}")
    return "\n".join(lines) + "\n"


def file_signature(path):
    """(mtime, size) of a file, or None: enough to notice that someone else wrote it."""
    try:
        st = os.stat(path)
        return (st.st_mtime_ns, st.st_size)
    except OSError:
        return None


def backup_emails(path):
    """Copy emails.json into the backup folder and keep only the newest copies."""
    if not path.exists():
        return
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")   # microseconds: quick saves never collide
    shutil.copy2(path, BACKUP_DIR / f"emails-{stamp}.json")
    old = sorted(BACKUP_DIR.glob("emails-*.json"))[:-BACKUPS_KEPT]
    for f in old:
        try:
            f.unlink()
        except OSError:
            pass


def write_emails_atomic(path, data):
    """Write to a temporary file in the same folder, then rename it over the
    original: the file is never left half-written, and keeps its permissions."""
    path.parent.mkdir(parents=True, exist_ok=True)
    mode = (os.stat(path).st_mode & 0o777) if path.exists() else 0o600
    fd, tmp = tempfile.mkstemp(prefix=".emails-", suffix=".json", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(dump_emails(data))
            f.flush()
            os.fsync(f.fileno())
        os.chmod(tmp, mode)
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def slugify(text):
    s = re.sub(r"[^a-z0-9]+", "", text.lower())
    return s or "tab"


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


# ── Single instance ─────────────────────────────────────────────────────────
def claim_single_instance():
    """Return a listening socket if we are the first Email Picker of this user.
    Otherwise ask the running one to show its window and return None."""
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        sock.bind(SOCKET_NAME)
    except OSError:
        sock.close()
        try:
            client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            client.settimeout(2)
            client.connect(SOCKET_NAME)
            client.sendall(b"show")
            client.close()
        except OSError:
            pass
        return None
    sock.listen(2)
    return sock


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


class FormDialog(ctk.CTkToplevel):
    """Small modal form: one or more text fields, Salva / Annulla.

    fields:   list of (key, label, initial value)
    validate: function(values) -> error text, or None if the values are fine
    """

    def __init__(self, master, theme, title, fields, validate=None, ok_text="Salva"):
        super().__init__(master)
        self.master_window = master
        self.validate = validate
        self.result = None
        self.entries = {}
        t = theme

        self.title(title)
        self.configure(fg_color=t["bg"])
        self.resizable(False, False)
        self.transient(master)

        for key, label, initial in fields:
            ctk.CTkLabel(self, text=label, text_color=t["fg"], anchor="w").pack(
                fill="x", padx=18, pady=(12, 2))
            entry = ctk.CTkEntry(self, width=330, fg_color=t["entry_bg"], text_color=t["fg"],
                                 border_color=t["accent"])
            entry.insert(0, initial or "")
            entry.pack(padx=18)
            self.entries[key] = entry

        self.error = ctk.CTkLabel(self, text="", text_color=t["danger"], anchor="w")
        self.error.pack(fill="x", padx=18, pady=(6, 0))

        buttons = ctk.CTkFrame(self, fg_color="transparent")
        buttons.pack(fill="x", padx=18, pady=(6, 16))
        ctk.CTkButton(buttons, text=ok_text, width=110, fg_color=t["accent"],
                      text_color=t["btn_fg"], hover_color=t["hover"],
                      command=self._ok).pack(side="right")
        ctk.CTkButton(buttons, text="Annulla", width=110, fg_color=t["entry_bg"],
                      text_color=t["fg"], hover_color=t["bg2"],
                      command=self._cancel).pack(side="right", padx=(0, 8))

        self.bind("<Return>", lambda e: self._ok())
        self.bind("<KP_Enter>", lambda e: self._ok())
        self.bind("<Escape>", lambda e: self._cancel())
        self.protocol("WM_DELETE_WINDOW", self._cancel)

        self._center_on_master()
        self.after(120, self._focus_first)

    def _center_on_master(self):
        self.update_idletasks()
        m = self.master_window
        x = m.winfo_rootx() + max(0, (m.winfo_width() - self.winfo_reqwidth()) // 2)
        y = m.winfo_rooty() + max(0, (m.winfo_height() - self.winfo_reqheight()) // 3)
        self.geometry(f"+{x}+{y}")

    def _focus_first(self):
        try:
            self.grab_set()
        except Exception:
            pass
        self.lift()
        first = next(iter(self.entries.values()), None)
        if first is not None:
            first.focus_force()

    def _ok(self):
        values = {k: e.get().strip() for k, e in self.entries.items()}
        error = self.validate(values) if self.validate else None
        if error:
            self.error.configure(text=error)
            return
        self.result = values
        self._close()

    def _cancel(self):
        self.result = None
        self._close()

    def _close(self):
        try:
            self.grab_release()
        except Exception:
            pass
        self.destroy()

    def show(self):
        self.master_window.wait_window(self)
        return self.result


class EmailPickerApp:
    def __init__(self):
        self.config = {**DEFAULT_CONFIG, **load_json(CONFIG_FILE, DEFAULT_CONFIG)}
        self.data = normalise_emails(load_json(EMAILS_FILE, DEFAULT_EMAILS))
        self.file_sig = file_signature(EMAILS_FILE)

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
        self.instance_sock = None    # single-instance listener

        self.edit_mode = False
        self.tabview = None
        self.tab_labels = []         # display label of each tab, same order as self.data["tabs"]
        self.tab_rows = []           # per tab: (scroll frame, [(name, email, row)], add button)

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
        self.edit_button = ctk.CTkButton(
            search_frame, text="✏️", width=40,
            fg_color=t["entry_bg"], text_color=t["fg"], hover_color=t["hover"],
            command=self.toggle_edit_mode,
        )
        self.edit_button.pack(side="right", padx=(0, 10), pady=8)
        self.search_entry = ctk.CTkEntry(
            search_frame, textvariable=self.search_var,
            placeholder_text="🔎 Cerca email o nome…",
            fg_color=t["entry_bg"], text_color=t["fg"],
            border_color=t["accent"],
        )
        self.search_entry.pack(side="left", fill="x", expand=True, padx=10, pady=8)
        self.search_var.trace_add("write", lambda *_: self._on_search())

        pos = self.config.get("search_position", "top")
        search_frame.pack(fill="x", side="top" if pos == "top" else "bottom")

        self.body = ctk.CTkFrame(self.app, fg_color="transparent")
        self.body.pack(fill="both", expand=True)

        # Tab toolbar: only visible in edit mode
        self.tab_toolbar = ctk.CTkFrame(self.body, fg_color="transparent")
        for text, cmd, width in (
            ("➕ Scheda", self._add_tab, 90),
            ("✎ Rinomina", self._rename_tab, 90),
            ("◀", lambda: self._move_tab(-1), 32),
            ("▶", lambda: self._move_tab(+1), 32),
            ("🗑", self._delete_tab, 32),
        ):
            ctk.CTkButton(self.tab_toolbar, text=text, width=width,
                          fg_color=t["entry_bg"], text_color=t["fg"], hover_color=t["hover"],
                          command=cmd).pack(side="left", padx=(0, 4))

        self._build_tabs()

    def _build_tabs(self, select=None):
        """(Re)build every tab from self.data. Called after each change."""
        t = self.theme
        if self.tabview is not None:
            self.tabview.destroy()
        self.tab_rows = []

        self.tabview = ctk.CTkTabview(
            self.body, fg_color=t["bg2"],
            segmented_button_selected_color=t["tab_sel"],
            segmented_button_selected_hover_color=t["hover"],
            # Unselected tabs need their own colour: tab_txt is dark on dark
            # themes (and white on light), so on bg2 it was almost invisible.
            segmented_button_unselected_color=t["tab_unsel"],
            segmented_button_unselected_hover_color=t["hover"],
            text_color=t["tab_txt"],
        )
        self.tabview.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        tabs = self.data["tabs"]
        self.tab_labels = self._unique_labels(tabs)
        if not tabs:
            empty = "Nessuna scheda"
            self.tabview.add(empty)
            hint = ("Nessuna scheda.\nPremi ✏️ e poi «➕ Scheda» per crearne una."
                    if not self.edit_mode else "Premi «➕ Scheda» per crearne una.")
            ctk.CTkLabel(self.tabview.tab(empty), text=hint, text_color=t["fg"]).pack(pady=30)
            return

        for ti, tab in enumerate(tabs):
            label = self.tab_labels[ti]
            self.tabview.add(label)
            scroll = ctk.CTkScrollableFrame(self.tabview.tab(label), fg_color="transparent")
            scroll.pack(fill="both", expand=True)
            self._populate_tab(scroll, ti)

        self.tabview.set(select if select in self.tab_labels else self.tab_labels[0])
        self._on_search()

    @staticmethod
    def _unique_labels(tabs):
        """CTkTabview needs unique names: add ' (2)', ' (3)'… to repeated labels."""
        seen, labels = {}, []
        for i, tab in enumerate(tabs):
            base = (tab.get("label") or tab.get("id") or f"Scheda {i + 1}").strip() or f"Scheda {i + 1}"
            n = seen.get(base, 0) + 1
            seen[base] = n
            labels.append(base if n == 1 else f"{base} ({n})")
        return labels

    def _populate_tab(self, frame, ti):
        t = self.theme
        rows = []
        for ei, entry in enumerate(self.data["tabs"][ti]["entries"]):
            name = entry.get("name", "")
            email = entry.get("email", "")
            row = ctk.CTkFrame(frame, fg_color="transparent")
            if self.edit_mode:
                for sym, cmd, colour in (
                    ("🗑", lambda i=ti, j=ei: self._delete_entry(i, j), t["danger"]),
                    ("✎", lambda i=ti, j=ei: self._edit_entry(i, j), t["entry_bg"]),
                    ("▼", lambda i=ti, j=ei: self._move_entry(i, j, +1), t["entry_bg"]),
                    ("▲", lambda i=ti, j=ei: self._move_entry(i, j, -1), t["entry_bg"]),
                ):
                    ctk.CTkButton(row, text=sym, width=30, fg_color=colour, text_color=t["fg"],
                                  hover_color=t["hover"], command=cmd).pack(side="right", padx=(3, 0))
                command = lambda i=ti, j=ei: self._edit_entry(i, j)
            else:
                command = lambda e=email, n=name: self._copy(e, n)
            btn = ctk.CTkButton(
                row, text=f"{name}\n{email}" if name else email,
                fg_color=t["accent"], text_color=t["btn_fg"],
                hover_color=t["hover"], command=command, anchor="w",
            )
            try:
                btn._text_label.configure(justify="left")   # two-line text aligned left, like the anchor
            except Exception:
                pass
            btn.pack(side="left", fill="x", expand=True)
            rows.append((name, email, row))

        add_button = None
        if self.edit_mode:
            add_button = ctk.CTkButton(
                frame, text="➕ Aggiungi indirizzo", fg_color="transparent",
                border_width=1, border_color=t["accent"], text_color=t["fg"],
                hover_color=t["entry_bg"], command=lambda i=ti: self._add_entry(i),
            )
        self.tab_rows.append((frame, rows, add_button))

    # ── Global search ────────────────────────────────────────────────────
    def _on_search(self):
        """Show only matching rows. Rows are re-packed in their original order,
        so clearing the search never shuffles them."""
        query = self.search_var.get().strip().lower()
        first_tab_with_match = None
        current_has_match = False
        current = self.tabview.get() if self.tabview is not None else None

        for ti, (frame, rows, add_button) in enumerate(self.tab_rows):
            for _, _, row in rows:
                row.pack_forget()
            if add_button is not None:
                add_button.pack_forget()
            matches = 0
            for name, email, row in rows:
                if not query or query in name.lower() or query in email.lower():
                    row.pack(fill="x", pady=3, padx=4)
                    matches += 1
            if add_button is not None:
                add_button.pack(fill="x", padx=4, pady=(8, 4))
            if matches and first_tab_with_match is None:
                first_tab_with_match = ti
            if matches and ti < len(self.tab_labels) and self.tab_labels[ti] == current:
                current_has_match = True

        if query and not current_has_match and first_tab_with_match is not None:
            self.tabview.set(self.tab_labels[first_tab_with_match])

    # ── Edit mode ────────────────────────────────────────────────────────
    def toggle_edit_mode(self):
        t = self.theme
        self.edit_mode = not self.edit_mode
        self.edit_button.configure(
            fg_color=t["accent"] if self.edit_mode else t["entry_bg"],
            text_color=t["btn_fg"] if self.edit_mode else t["fg"],
        )
        if self.edit_mode:
            self.tab_toolbar.pack(fill="x", padx=10, pady=(8, 4), before=self.tabview)
        else:
            self.tab_toolbar.pack_forget()
        self._build_tabs(select=self._current_label())

    def _current_label(self):
        try:
            return self.tabview.get()
        except Exception:
            return None

    def _current_tab_index(self):
        label = self._current_label()
        return self.tab_labels.index(label) if label in self.tab_labels else None

    def _file_changed(self):
        return file_signature(EMAILS_FILE) != self.file_sig

    def _reload(self, select=None):
        self.data = normalise_emails(load_json(EMAILS_FILE, DEFAULT_EMAILS))
        self.file_sig = file_signature(EMAILS_FILE)
        self._build_tabs(select=select or self._current_label())

    def _begin_change(self):
        """Before any change: if emails.json was written by someone else
        (e.g. Lampo Mail), reload it and stop, so nothing is overwritten."""
        if not self._file_changed():
            return True
        self._reload()
        messagebox.showinfo(
            "Email Picker",
            "emails.json è stato cambiato da un altro programma (forse Lampo Mail).\n"
            "Ho ricaricato la lista: ripeti l'operazione.",
            parent=self.app,
        )
        return False

    def _commit(self, select=None):
        """Renumber the tabs, back up, write atomically, rebuild the UI."""
        for i, tab in enumerate(self.data["tabs"]):
            tab["order"] = i
        try:
            backup_emails(EMAILS_FILE)
            write_emails_atomic(EMAILS_FILE, self.data)
            self.file_sig = file_signature(EMAILS_FILE)
        except Exception as e:
            messagebox.showerror("Email Picker", f"Non riesco a salvare emails.json:\n{e}", parent=self.app)
            self._reload()
            return
        self._build_tabs(select=select)

    def _ask(self, title, fields, validate, ok_text="Salva"):
        return FormDialog(self.app, self.theme, title, fields, validate, ok_text).show()

    # ── Addresses ────────────────────────────────────────────────────────
    def _entry_validator(self, ti, skip_index=None):
        def validate(values):
            email = values.get("email", "")
            if not EMAIL_RE.match(email):
                return "Indirizzo non valido (esempio: nome@dominio.it)."
            for j, e in enumerate(self.data["tabs"][ti]["entries"]):
                if j != skip_index and e.get("email", "").lower() == email.lower():
                    return "Questo indirizzo c'è già in questa scheda."
            return None
        return validate

    def _add_entry(self, ti):
        if not self._begin_change():
            return
        res = self._ask("Nuovo indirizzo",
                        [("email", "Indirizzo email", ""), ("name", "Nome (facoltativo)", "")],
                        self._entry_validator(ti), ok_text="Aggiungi")
        if res is None or not self._begin_change():
            return
        self.data["tabs"][ti]["entries"].append({"name": res["name"], "email": res["email"]})
        self._commit(select=self.tab_labels[ti])

    def _edit_entry(self, ti, ei):
        if not self._begin_change():
            return
        entry = self.data["tabs"][ti]["entries"][ei]
        res = self._ask("Modifica indirizzo",
                        [("email", "Indirizzo email", entry.get("email", "")),
                         ("name", "Nome (facoltativo)", entry.get("name", ""))],
                        self._entry_validator(ti, skip_index=ei))
        if res is None or not self._begin_change():
            return
        entry["name"], entry["email"] = res["name"], res["email"]   # other keys stay as they are
        self._commit(select=self.tab_labels[ti])

    def _delete_entry(self, ti, ei):
        if not self._begin_change():
            return
        entry = self.data["tabs"][ti]["entries"][ei]
        shown = entry.get("email", "") + (f"  ({entry['name']})" if entry.get("name") else "")
        if not messagebox.askyesno("Elimina indirizzo", f"Eliminare questo indirizzo?\n\n{shown}",
                                   parent=self.app):
            return
        del self.data["tabs"][ti]["entries"][ei]
        self._commit(select=self.tab_labels[ti])

    def _move_entry(self, ti, ei, delta):
        entries = self.data["tabs"][ti]["entries"]
        new = ei + delta
        if not 0 <= new < len(entries) or not self._begin_change():
            return
        entries[ei], entries[new] = entries[new], entries[ei]
        self._commit(select=self.tab_labels[ti])

    # ── Tabs ─────────────────────────────────────────────────────────────
    def _tab_validator(self, skip_index=None):
        def validate(values):
            label = values.get("label", "")
            if not label:
                return "Scrivi un nome per la scheda."
            for i, tab in enumerate(self.data["tabs"]):
                if i != skip_index and (tab.get("label") or "").strip().lower() == label.lower():
                    return "C'è già una scheda con questo nome."
            return None
        return validate

    def _add_tab(self):
        if not self._begin_change():
            return
        res = self._ask("Nuova scheda", [("label", "Nome della scheda", "")],
                        self._tab_validator(), ok_text="Crea")
        if res is None or not self._begin_change():
            return
        used = {tab.get("id") for tab in self.data["tabs"]}
        base = slugify(res["label"])
        tab_id, n = base, 2
        while tab_id in used:                    # ids must stay unique: Lampo Mail uses them
            tab_id, n = f"{base}{n}", n + 1
        self.data["tabs"].append({"id": tab_id, "label": res["label"],
                                  "order": len(self.data["tabs"]), "entries": []})
        self._commit(select=res["label"])

    def _rename_tab(self):
        ti = self._current_tab_index()
        if ti is None or not self._begin_change():
            return
        tab = self.data["tabs"][ti]
        res = self._ask("Rinomina scheda", [("label", "Nuovo nome", tab.get("label", ""))],
                        self._tab_validator(skip_index=ti))
        if res is None or not self._begin_change():
            return
        tab["label"] = res["label"]              # the id stays: Lampo Mail refers to it
        self._commit(select=res["label"])

    def _move_tab(self, delta):
        ti = self._current_tab_index()
        tabs = self.data["tabs"]
        if ti is None:
            return
        new = ti + delta
        if not 0 <= new < len(tabs) or not self._begin_change():
            return
        label = self.tab_labels[ti]
        tabs[ti], tabs[new] = tabs[new], tabs[ti]
        self._commit(select=label)

    def _delete_tab(self):
        ti = self._current_tab_index()
        if ti is None or not self._begin_change():
            return
        label = self.tab_labels[ti]
        n = len(self.data["tabs"][ti]["entries"])
        text = f"Eliminare la scheda «{label}»?"
        if n:
            text += (f"\n\nContiene {n} indirizz{'o' if n == 1 else 'i'}, "
                     f"che verr{'à' if n == 1 else 'anno'} cancellat{'o' if n == 1 else 'i'} con lei.")
        text += f"\n\nUna copia del file resta comunque in:\n{BACKUP_DIR}"
        if not messagebox.askyesno("Elimina scheda", text, icon="warning", parent=self.app):
            return
        del self.data["tabs"][ti]
        neighbours = self.tab_labels[:ti] + self.tab_labels[ti + 1:]
        self._commit(select=neighbours[max(0, ti - 1)] if neighbours else None)

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
        if self._file_changed():                 # e.g. Lampo Mail added an address meanwhile
            self._reload()
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

    # ── Single instance: answer "show" from a second launch ──────────────
    def start_instance_listener(self, sock):
        self.instance_sock = sock

        def _loop():
            while True:
                try:
                    conn, _ = sock.accept()
                except OSError:
                    return                       # socket closed on quit
                with conn:
                    try:
                        msg = conn.recv(16)
                    except OSError:
                        msg = b""
                if msg.startswith(b"show"):
                    self.show_window()

        threading.Thread(target=_loop, daemon=True).start()

    # ── Clean shutdown ───────────────────────────────────────────────────
    def quit_app(self):
        self._save_geometry()
        if self.tray_icon:
            self.tray_icon.stop()
        if self.glib_loop:
            self.glib_loop.quit()
        if self.hotkey_listener:
            self.hotkey_listener.stop()
        if self.instance_sock:
            try:
                self.instance_sock.close()
            except OSError:
                pass
        self.app.after(0, self.app.destroy)

    def run(self):
        self.start_tray()
        self.start_hotkey()
        self.app.bind("<Escape>", lambda e: self.hide_window())
        signal.signal(signal.SIGINT, lambda *_: self.quit_app())
        signal.signal(signal.SIGTERM, lambda *_: self.quit_app())
        self.app.mainloop()


if __name__ == "__main__":
    instance_sock = claim_single_instance()
    if instance_sock is None:
        print("[Email-Picker] already running: showing its window.", file=sys.stderr)
        sys.exit(0)
    picker = EmailPickerApp()
    picker.start_instance_listener(instance_sock)
    picker.run()
