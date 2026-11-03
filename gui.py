"""Einfache CustomTkinter-Oberfläche für PyPack."""

from __future__ import annotations

import os
import json
from pathlib import Path
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import sys

try:
    import customtkinter as ctk
except ImportError as exc:
    raise SystemExit("CustomTkinter fehlt. Installiere es mit: python -m pip install -r requirements.txt") from exc

import pypack


class PyPackApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("PyPack — Dateikompressor")
        self.geometry("900x580")
        self.minsize(680, 440)
        self._set_window_icon(self)
        ctk.set_appearance_mode("System")
        ctk.set_default_color_theme("blue")
        self.settings_path = Path.home() / ".pypack" / "settings.json"
        self.settings = self._load_settings()
        self.appearance_var = tk.StringVar(value=self.settings.get("appearance", "System"))
        self.tree_picker_var = tk.BooleanVar(value=self.settings.get("tree_picker", True))
        self.gpu_var = tk.BooleanVar(value=self.settings.get("use_gpu", True))
        stored_mode = self.settings.get("compression_mode", "Schnell")
        self.mode_var = tk.StringVar(value="Maximale Kompression" if stored_mode in {"maximum", "Maximale Kompression"}
                                     else "Schnell")

        self.archive_path: Path | None = None
        self.entries: list[tuple[str, int]] = []
        self._build_ui()
        self._configure_ttk_style()
        self.after(100, self._open_archive_argument)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _open_archive_argument(self):
        """Open an archive passed by Windows file association."""
        if len(sys.argv) < 2:
            return
        candidate = Path(sys.argv[1])
        if candidate.suffix.lower() != ".pyp" or not candidate.is_file():
            return
        try:
            entries = pypack.list_archive(candidate)
            self.archive_path, self.entries = candidate.resolve(), entries
            self.archive_label.configure(text=str(self.archive_path))
            self._populate_tree(entries)
            total = sum(size for _, size in entries)
            self.status.configure(text=f"{len(entries)} Dateien · {self._format_size(total)} unkomprimiert")
        except Exception as exc:
            messagebox.showerror("Archivfehler", str(exc), parent=self)

    @staticmethod
    def _icon_path():
        return Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent)) / "icon.ico"

    @classmethod
    def _set_window_icon(cls, window):
        icon = cls._icon_path()
        if icon.is_file():
            try:
                window.iconbitmap(default=str(icon))
            except tk.TclError:
                pass

    def _on_close(self):
        """Close owned dialogs cleanly instead of leaving a stale top-level."""
        self.destroy()

    def _load_settings(self):
        try:
            data = json.loads(self.settings_path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except (OSError, json.JSONDecodeError):
            return {}

    def _save_settings(self):
        self.settings["appearance"] = self.appearance_var.get()
        self.settings["tree_picker"] = bool(self.tree_picker_var.get())
        self.settings["use_gpu"] = bool(self.gpu_var.get())
        self.settings["compression_mode"] = self.mode_var.get()
        self.settings.setdefault("compression_level", 6)
        try:
            self.settings_path.parent.mkdir(parents=True, exist_ok=True)
            self.settings_path.write_text(json.dumps(self.settings, indent=2), encoding="utf-8")
        except OSError as exc:
            messagebox.showwarning("Einstellung nicht gespeichert", str(exc), parent=self)

    def _configure_ttk_style(self):
        style = ttk.Style(self)
        mode = self.appearance_var.get()
        dark = mode == "Dark" or (mode == "System" and self._system_is_dark())
        if dark:
            bg, field, fg, select = "#242424", "#181818", "#f2f2f2", "#1f6aa5"
        else:
            bg, field, fg, select = "#f2f2f2", "#ffffff", "#202020", "#2d8cff"
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("Treeview", background=field, fieldbackground=field, foreground=fg,
                        bordercolor=bg, rowheight=27)
        style.map("Treeview", background=[("selected", select)], foreground=[("selected", "#ffffff")])
        style.configure("Treeview.Heading", background=bg, foreground=fg, relief="flat")
        style.map("Treeview.Heading", background=[("active", select)], foreground=[("active", "#ffffff")])
        style.configure("Vertical.TScrollbar", background=bg, troughcolor=field,
                        bordercolor=bg, arrowcolor=fg)

    @staticmethod
    def _system_is_dark():
        if os.name != "nt":
            return False
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                                r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize") as key:
                return winreg.QueryValueEx(key, "AppsUseLightTheme")[0] == 0
        except (OSError, ImportError):
            return False

    def _build_ui(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        header = ctk.CTkFrame(self, corner_radius=12)
        header.grid(row=0, column=0, padx=16, pady=(16, 8), sticky="ew")
        header.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(header, text="PyPack", font=ctk.CTkFont(size=23, weight="bold")).grid(
            row=0, column=0, padx=14, pady=12)
        self.archive_label = ctk.CTkLabel(header, text="Kein Archiv geöffnet", anchor="w")
        self.archive_label.grid(row=0, column=1, padx=8, sticky="ew")
        ctk.CTkButton(header, text="Archiv öffnen…", command=self.open_archive).grid(
            row=0, column=2, padx=12, pady=10)

        settings = ctk.CTkFrame(self, corner_radius=10)
        settings.grid(row=1, column=0, padx=16, pady=4, sticky="ew")
        ctk.CTkLabel(settings, text="Einstellungen", font=ctk.CTkFont(weight="bold")).pack(
            side="left", padx=(12, 6), pady=8)
        ctk.CTkLabel(settings, text="Darstellung").pack(side="left", padx=(8, 4))
        ctk.CTkOptionMenu(settings, values=["System", "Light", "Dark"], variable=self.appearance_var,
                          command=self._appearance_changed, width=110).pack(side="left", padx=(0, 12), pady=6)
        ctk.CTkSwitch(settings, text="Integrierter Dateibaum", variable=self.tree_picker_var,
                      command=self._save_settings).pack(side="left", padx=8, pady=6)
        ctk.CTkSwitch(settings, text="GPU automatisch nutzen", variable=self.gpu_var,
                      command=self._save_settings).pack(side="left", padx=8, pady=6)
        ctk.CTkLabel(settings, text="Kompression").pack(side="left", padx=(12, 4))
        ctk.CTkOptionMenu(settings, values=["Schnell", "Maximale Kompression"],
                          variable=self.mode_var, command=self._compression_mode_changed,
                          width=180).pack(side="left", padx=(0, 8), pady=6)

        toolbar = ctk.CTkFrame(self, fg_color="transparent")
        toolbar.grid(row=2, column=0, padx=16, pady=6, sticky="ew")
        ctk.CTkButton(toolbar, text="Archiv erstellen…", command=self.create_archive).pack(side="left", padx=(0, 8))
        ctk.CTkButton(toolbar, text="Ausgewählte entpacken…", command=self.extract_selected).pack(side="left", padx=8)
        ctk.CTkButton(toolbar, text="Alles entpacken…", command=self.extract_all).pack(side="left", padx=8)
        ctk.CTkButton(toolbar, text="Archiv prüfen", command=self.test_archive, fg_color="#555b66",
                      hover_color="#444953").pack(side="right", padx=(8, 0))

        body = ctk.CTkFrame(self, corner_radius=12)
        body.grid(row=3, column=0, padx=16, pady=8, sticky="nsew")
        body.grid_columnconfigure(0, weight=1)
        body.grid_rowconfigure(1, weight=1)
        ctk.CTkLabel(body, text="Inhalt des Archivs", font=ctk.CTkFont(size=16, weight="bold")).grid(
            row=0, column=0, padx=12, pady=(12, 4), sticky="w")

        table_frame = ctk.CTkFrame(body, fg_color="transparent")
        table_frame.grid(row=1, column=0, padx=12, pady=(4, 12), sticky="nsew")
        table_frame.grid_columnconfigure(0, weight=1)
        table_frame.grid_rowconfigure(0, weight=1)
        self.tree = ttk.Treeview(table_frame, columns=("size",), show="tree headings", selectmode="extended")
        self.tree.heading("#0", text="Datei / Pfad", anchor="w")
        self.tree.heading("size", text="Größe", anchor="e")
        self.tree.column("#0", stretch=True, width=560)
        self.tree.column("size", stretch=False, width=120, anchor="e")
        scrollbar = ttk.Scrollbar(table_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.tree.bind("<Double-1>", lambda _event: self.extract_selected())

        footer = ctk.CTkFrame(self, fg_color="transparent")
        footer.grid(row=4, column=0, padx=16, pady=(4, 14), sticky="ew")
        footer.grid_columnconfigure(0, weight=1)
        self.status = ctk.CTkLabel(footer, text="Bereit", anchor="w")
        self.status.grid(row=0, column=0, sticky="ew")
        self.progress = ctk.CTkProgressBar(footer, width=220, mode="determinate")
        self.progress.grid(row=0, column=1, padx=(12, 8))
        self.progress.set(0)
        self.eta_label = ctk.CTkLabel(footer, text="", width=130, anchor="e")
        self.eta_label.grid(row=0, column=2, padx=(0, 8))
        self.worker_label = ctk.CTkLabel(footer, text="Worker: 0", width=90, anchor="e")
        self.worker_label.grid(row=0, column=3, padx=(0, 8))
        self.cancel_button = ctk.CTkButton(footer, text="Abbrechen", width=92,
                                           command=self._cancel_operation,
                                           fg_color="#9b3030", hover_color="#762424",
                                           state="disabled")
        self.cancel_button.grid(row=0, column=4, padx=(0, 4))
        self._cancel_event = None

    def _appearance_changed(self, value):
        ctk.set_appearance_mode(value)
        self._configure_ttk_style()
        self._save_settings()

    def _compression_mode_changed(self, _value):
        self._save_settings()

    def _require_archive(self) -> bool:
        if self.archive_path is None:
            messagebox.showinfo("PyPack", "Öffne zuerst ein Archiv.", parent=self)
            return False
        return True

    def open_archive(self):
        selected = filedialog.askopenfilename(title="PyPack-Archiv öffnen",
                                              filetypes=[("PyPack-Archive", "*.pyp"), ("Alle Dateien", "*.*")])
        if not selected:
            return
        try:
            path = Path(selected)
            entries = pypack.list_archive(path)
        except Exception as exc:
            messagebox.showerror("Archivfehler", str(exc), parent=self)
            return
        self.archive_path, self.entries = path, entries
        self.archive_label.configure(text=str(path))
        self._populate_tree(entries)
        self.status.configure(text=f"{len(entries)} Dateien · {self._format_size(sum(size for _, size in entries))} unkomprimiert")

    def _populate_tree(self, entries):
        self.tree.delete(*self.tree.get_children())
        folders = {"": ""}
        for name, size in entries:
            parts = Path(name).parts
            parent = ""
            for part in parts[:-1]:
                current = f"{parent}/{part}" if parent else part
                if current not in folders:
                    iid = self.tree.insert(parent, "end", text=part, values=("",), open=True)
                    folders[current] = iid
                parent = current
            self.tree.insert(folders[parent], "end", text=parts[-1], values=(self._format_size(size),),
                             tags=("file",), iid=f"file:{name}")

    @staticmethod
    def _format_size(size):
        value = float(size)
        for unit in ("B", "KB", "MB", "GB", "TB"):
            if value < 1024 or unit == "TB":
                return f"{int(value)} B" if unit == "B" else f"{value:.1f} {unit}"
            value /= 1024

    def _selected_names(self):
        return {item[5:] for item in self.tree.selection() if item.startswith("file:")}

    def _run_background(self, label, operation, success, on_error=None):
        self._cancel_event = threading.Event()
        cancel_event = self._cancel_event
        self.status.configure(text=label)
        self.progress.set(0)
        self.eta_label.configure(text="Berechne…")
        self.worker_label.configure(text=f"Worker: {pypack.AdaptiveWorkers().current}")
        self.cancel_button.configure(state="normal")
        self.update_idletasks()

        def finish_success():
            self.cancel_button.configure(state="disabled")
            self.progress.set(0)
            self.eta_label.configure(text="")
            self.worker_label.configure(text="Worker: 0")
            self._cancel_event = None
            success()

        def work():
            try:
                operation(cancel_event)
            except Exception as exc:
                callback = on_error or self._finish_error
                self.after(0, lambda error=exc, callback=callback: callback(error))
            else:
                self.after(0, finish_success)
        threading.Thread(target=work, daemon=True).start()

    def _cancel_operation(self):
        if self._cancel_event is not None:
            self._cancel_event.set()
            self.status.configure(text="Abbruch wird ausgeführt…")
            self.cancel_button.configure(state="disabled")

    def _finish_error(self, error):
        self.progress.set(0)
        self.eta_label.configure(text="")
        self.worker_label.configure(text="Worker: 0")
        self.cancel_button.configure(state="disabled")
        self._cancel_event = None
        if isinstance(error, pypack.OperationCancelled):
            self.status.configure(text="Abgebrochen")
            return
        self.status.configure(text="Aktion fehlgeschlagen")
        messagebox.showerror("Fehler", str(error), parent=self)

    def create_archive(self):
        if getattr(self, "_create_archive_running", False):
            return
        sources = self._choose_sources()
        if not sources:
            return
        output = filedialog.asksaveasfilename(title="Archiv speichern", defaultextension=".pyp",
                                             initialfile=pypack.default_archive_name(sources).name,
                                             initialdir=str(pypack.default_archive_name(sources).parent),
                                             filetypes=[("PyPack-Archive", "*.pyp")])
        if not output:
            return
        compression_level = self._choose_compression_level()
        if compression_level is None:
            return
        self._create_archive_running = True
        def report(done, total, eta, current_name, worker_count):
            self.after(0, lambda: self._update_progress(done, total, eta, current_name, worker_count))

        def finished():
            self._create_archive_running = False
            self._created(Path(output))

        def failed(error):
            self._create_archive_running = False
            self.cancel_button.configure(state="disabled")
            self.worker_label.configure(text="Worker: 0")
            self.eta_label.configure(text="")
            self._finish_error(error)

        self._run_background("Archiv wird erstellt…",
                             lambda cancel: pypack.pack(sources, Path(output), level=compression_level, workers="auto",
                                                        progress_callback=report,
                                                        use_gpu=None if self.gpu_var.get() else False,
                                                        mode="maximum" if self.mode_var.get() == "Maximale Kompression" else "fast",
                                                        cancel_event=cancel),
                              finished, on_error=failed)

    def _choose_compression_level(self):
        dialog = ctk.CTkToplevel(self)
        dialog.title("Kompressionsstärke")
        self._set_window_icon(dialog)
        dialog.geometry("460x240")
        dialog.resizable(False, False)
        dialog.transient(self)
        dialog.grab_set()
        current = int(self.settings.get("compression_level", 6))
        level = tk.IntVar(value=max(1, min(9, current)))
        result = []

        ctk.CTkLabel(dialog, text="Kompressionsstärke wählen",
                     font=ctk.CTkFont(size=18, weight="bold")).pack(padx=20, pady=(20, 8), anchor="w")
        ctk.CTkLabel(dialog, text="Höhere Stufen können länger dauern; Stufe 1 ist am schnellsten.",
                     wraplength=420, justify="left").pack(padx=20, pady=(0, 10), anchor="w")
        value_label = ctk.CTkLabel(dialog, text=f"Stufe {level.get()}")
        value_label.pack(pady=(4, 0))

        def changed(value):
            level.set(int(float(value)))
            value_label.configure(text=f"Stufe {level.get()}")

        slider = ctk.CTkSlider(dialog, from_=1, to=9, number_of_steps=8, command=changed)
        slider.set(level.get())
        slider.pack(
            fill="x", padx=22, pady=(4, 14))
        buttons = ctk.CTkFrame(dialog, fg_color="transparent")
        buttons.pack(fill="x", padx=20, pady=(4, 16))

        def accept():
            selected = level.get()
            self.settings["compression_level"] = selected
            self._save_settings()
            result.append(selected)
            dialog.destroy()

        ctk.CTkButton(buttons, text="Abbrechen", command=dialog.destroy,
                      fg_color="#555b66", hover_color="#444953").pack(side="right", padx=(8, 0))
        ctk.CTkButton(buttons, text="Weiter", command=accept).pack(side="right")
        self.wait_window(dialog)
        return result[0] if result else None

    def _update_progress(self, done, total, eta, current_name, workers):
        fraction = done / total if total else 1.0
        self.progress.set(max(0.0, min(1.0, fraction)))
        remaining = "—" if eta is None else self._format_duration(eta)
        filename = Path(current_name).name if current_name else "Abschluss"
        self.status.configure(text=f"{filename} · {workers} Worker")
        self.eta_label.configure(text=f"{fraction:.0%} · noch {remaining}")
        self.worker_label.configure(text=f"Worker: {workers}")

    @staticmethod
    def _format_duration(seconds):
        seconds = max(0, int(seconds))
        if seconds < 60:
            return f"{seconds} s"
        minutes, sec = divmod(seconds, 60)
        if minutes < 60:
            return f"{minutes} min {sec:02d} s"
        hours, minutes = divmod(minutes, 60)
        return f"{hours} h {minutes:02d} min"

    def _choose_sources(self):
        """Allow selecting files and folders in one archive operation."""
        if self.tree_picker_var.get():
            return self._tree_source_picker()

        dialog = ctk.CTkToplevel(self)
        dialog.title("Dateien und Ordner auswählen")
        self._set_window_icon(dialog)
        dialog.geometry("520x330")
        dialog.transient(self)
        dialog.grab_set()
        selected: list[Path] = []
        ctk.CTkLabel(dialog, text="Füge Dateien und/oder ganze Ordner hinzu.",
                     font=ctk.CTkFont(size=16, weight="bold")).pack(padx=18, pady=(18, 8), anchor="w")
        ctk.CTkLabel(dialog, text="Alle hinzugefügten Einträge werden gemeinsam in ein Archiv gepackt.",
                     wraplength=470, justify="left").pack(padx=18, pady=(0, 10), anchor="w")
        list_frame = ctk.CTkFrame(dialog)
        list_frame.pack(fill="both", expand=True, padx=18, pady=8)
        list_frame.grid_columnconfigure(0, weight=1)
        list_frame.grid_rowconfigure(0, weight=1)
        box = tk.Listbox(list_frame, selectmode="extended", height=8)
        box.grid(row=0, column=0, sticky="nsew", padx=(6, 0), pady=6)
        scroll = ttk.Scrollbar(list_frame, orient="vertical", command=box.yview)
        scroll.grid(row=0, column=1, sticky="ns", padx=6, pady=6)
        box.configure(yscrollcommand=scroll.set)

        def add_path(path: str):
            candidate = Path(path).resolve()
            if candidate not in selected:
                selected.append(candidate)
                box.insert("end", f"📁 {candidate}" if candidate.is_dir() else f"📄 {candidate}")

        def add_files():
            for path in filedialog.askopenfilenames(parent=dialog, title="Dateien hinzufügen"):
                add_path(path)

        def add_folder():
            path = filedialog.askdirectory(parent=dialog, title="Ordner hinzufügen")
            if path:
                add_path(path)

        def remove_selected():
            indices = list(box.curselection())
            for index in reversed(indices):
                box.delete(index)
                selected.pop(index)

        actions = ctk.CTkFrame(dialog, fg_color="transparent")
        actions.pack(fill="x", padx=18, pady=(4, 0))
        ctk.CTkButton(actions, text="Dateien hinzufügen…", command=add_files).pack(side="left", padx=(0, 6))
        ctk.CTkButton(actions, text="Ordner hinzufügen…", command=add_folder).pack(side="left", padx=6)
        ctk.CTkButton(actions, text="Entfernen", command=remove_selected, fg_color="#555b66",
                      hover_color="#444953").pack(side="left", padx=6)

        result: list[Path] = []
        buttons = ctk.CTkFrame(dialog, fg_color="transparent")
        buttons.pack(fill="x", padx=18, pady=12)

        def accept():
            if not selected:
                messagebox.showinfo("Auswahl fehlt", "Füge mindestens eine Datei oder einen Ordner hinzu.", parent=dialog)
                return
            result.extend(selected)
            dialog.destroy()

        ctk.CTkButton(buttons, text="Abbrechen", command=dialog.destroy, fg_color="#555b66",
                      hover_color="#444953").pack(side="right", padx=(6, 0))
        ctk.CTkButton(buttons, text="Weiter", command=accept).pack(side="right", padx=6)
        self.wait_window(dialog)
        return result

    def _tree_source_picker(self):
        """Custom picker supporting mixed, multi-selected files and folders."""
        dialog = ctk.CTkToplevel(self)
        dialog.title("Dateien und Ordner auswählen")
        self._set_window_icon(dialog)
        dialog.geometry("760x560")
        dialog.minsize(600, 420)
        dialog.transient(self)
        dialog.grab_set()
        selected: set[Path] = set()
        path_var = tk.StringVar(value=str(Path.home()))
        result: list[Path] = []

        dialog.grid_columnconfigure(0, weight=1)
        dialog.grid_rowconfigure(1, weight=1)
        top = ctk.CTkFrame(dialog, fg_color="transparent")
        top.grid(row=0, column=0, padx=14, pady=(14, 6), sticky="ew")
        top.grid_columnconfigure(1, weight=1)
        ctk.CTkButton(top, text="Zurück", width=75,
                      command=lambda: navigate(Path(path_var.get()).parent)).grid(row=0, column=0, padx=(0, 8))
        path_entry = ctk.CTkEntry(top, textvariable=path_var, fg_color=("#ffffff", "#181818"),
                                  text_color=("#202020", "#f2f2f2"), border_color=("#cccccc", "#454545"))
        path_entry.grid(row=0, column=1, sticky="ew", padx=4)
        ctk.CTkButton(top, text="Öffnen", width=75,
                      command=lambda: navigate(Path(path_var.get()))).grid(row=0, column=2, padx=(8, 0))

        area = ctk.CTkFrame(dialog)
        area.grid(row=1, column=0, padx=14, pady=6, sticky="nsew")
        area.grid_columnconfigure(0, weight=1)
        area.grid_rowconfigure(0, weight=1)
        tree = ttk.Treeview(area, columns=("kind",), show="tree headings", selectmode="extended")
        tree.heading("#0", text="Name", anchor="w")
        tree.heading("kind", text="Typ", anchor="w")
        tree.column("#0", width=520, stretch=True)
        tree.column("kind", width=100, stretch=False)
        tree.grid(row=0, column=0, sticky="nsew", padx=(6, 0), pady=6)
        scroll = ttk.Scrollbar(area, orient="vertical", command=tree.yview)
        scroll.grid(row=0, column=1, sticky="ns", padx=6, pady=6)
        tree.configure(yscrollcommand=scroll.set)

        chosen = ctk.CTkFrame(dialog)
        chosen.grid(row=2, column=0, padx=14, pady=6, sticky="ew")
        chosen.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(chosen, text="Ausgewählt (Ordner werden vollständig aufgenommen):", anchor="w").grid(
            row=0, column=0, padx=8, pady=(6, 2), sticky="ew")
        chosen_text = ctk.CTkTextbox(chosen, height=76, wrap="none")
        chosen_text.grid(row=1, column=0, padx=8, pady=(2, 8), sticky="ew")
        chosen_text.configure(state="disabled")
        status = ctk.CTkLabel(dialog, text="Strg-/Umschalt-Klick für Mehrfachauswahl.", anchor="w")
        status.grid(row=3, column=0, padx=16, pady=2, sticky="ew")

        def refresh_selected():
            chosen_text.configure(state="normal")
            chosen_text.delete("1.0", "end")
            for path in sorted(selected, key=lambda p: str(p).casefold()):
                chosen_text.insert("end", str(path) + "\n")
            chosen_text.configure(state="disabled")

        def navigate(path: Path):
            path = path.expanduser().resolve()
            if not path.is_dir():
                messagebox.showerror("Ordner nicht gefunden", f"Kein lesbarer Ordner:\n{path}", parent=dialog)
                return
            try:
                children = sorted(path.iterdir(), key=lambda p: (not p.is_dir(), p.name.casefold()))
            except OSError as exc:
                messagebox.showerror("Zugriff fehlgeschlagen", str(exc), parent=dialog)
                return
            path_var.set(str(path))
            tree.delete(*tree.get_children())
            for child in children:
                try:
                    is_dir = child.is_dir()
                except OSError:
                    continue
                tree.insert("", "end", iid=str(child), text=child.name,
                            values=("Ordner" if is_dir else "Datei",))
            status.configure(text=f"{len(children)} Einträge in {path}")

        def accept():
            selected.update(Path(item).resolve() for item in tree.selection())
            if not selected:
                messagebox.showinfo("Auswahl fehlt", "Wähle Dateien und/oder Ordner aus.", parent=dialog)
                return
            result.extend(sorted(selected, key=lambda p: str(p).casefold()))
            dialog.destroy()

        def double_click(_event):
            item = tree.focus()
            if item:
                path = Path(item)
                if path.is_dir():
                    navigate(path)

        tree.bind("<Double-1>", double_click)
        path_entry.bind("<Return>", lambda _event: navigate(Path(path_var.get())))
        navigate(Path.home())
        bottom = ctk.CTkFrame(dialog, fg_color="transparent")
        bottom.grid(row=4, column=0, padx=14, pady=(6, 12), sticky="ew")
        ctk.CTkButton(bottom, text="Diesen Ordner auswählen",
                      command=lambda: (selected.add(Path(path_var.get()).resolve()), refresh_selected()),
                      fg_color="#555b66", hover_color="#444953").pack(side="left")
        ctk.CTkButton(bottom, text="Auswahl leeren",
                      command=lambda: (selected.clear(), refresh_selected()),
                      fg_color="#555b66", hover_color="#444953").pack(side="left", padx=8)
        ctk.CTkButton(bottom, text="Abbrechen", command=dialog.destroy,
                      fg_color="#555b66", hover_color="#444953").pack(side="right", padx=(8, 0))
        ctk.CTkButton(bottom, text="Zum Archiv hinzufügen", command=accept).pack(side="right")
        self.wait_window(dialog)
        return result

    def _created(self, path):
        self.progress.set(0)
        self.eta_label.configure(text="")
        self.status.configure(text="Archiv erstellt")
        self.archive_path = path
        self.entries = pypack.list_archive(path)
        self.archive_label.configure(text=str(path))
        self._populate_tree(self.entries)
        messagebox.showinfo("Fertig", f"Archiv erstellt:\n{path}", parent=self)

    def extract_selected(self):
        if not self._require_archive():
            return
        names = self._selected_names()
        if not names:
            messagebox.showinfo("Auswahl fehlt", "Wähle mindestens eine Datei in der Liste aus.", parent=self)
            return
        destination = filedialog.askdirectory(title="Zielordner auswählen")
        if not destination:
            return
        self._run_background("Auswahl wird entpackt…",
                             lambda cancel: pypack.extract_files(self.archive_path, Path(destination), names,
                                                                 workers="auto", cancel_event=cancel),
                             lambda: self._finished_extract(destination, len(names)))

    def extract_all(self):
        if not self._require_archive():
            return
        destination = filedialog.askdirectory(title="Zielordner auswählen")
        if not destination:
            return
        self._run_background("Archiv wird entpackt…",
                             lambda cancel: pypack.unpack(self.archive_path, Path(destination), workers="auto",
                                                          cancel_event=cancel),
                             lambda: self._finished_extract(destination, len(self.entries)))

    def _finished_extract(self, destination, count):
        self.progress.set(0)
        self.eta_label.configure(text="")
        self.status.configure(text=f"{count} Dateien entpackt")
        if messagebox.askyesno("Fertig", f"{count} Dateien nach {destination} entpackt.\nIm Explorer öffnen?", parent=self):
            os.startfile(destination)

    def test_archive(self):
        if not self._require_archive():
            return
        self._run_background("Archiv wird geprüft…",
                             lambda cancel: pypack.unpack(self.archive_path, Path("."), test_only=True,
                                                          workers="auto", cancel_event=cancel),
                             self._finished_test)

    def _finished_test(self):
        self.progress.set(0)
        self.eta_label.configure(text="")
        self.status.configure(text="Archivprüfung erfolgreich")
        messagebox.showinfo("Prüfung erfolgreich", "Alle Daten und Prüfsummen sind intakt.", parent=self)


if __name__ == "__main__":
    import multiprocessing
    multiprocessing.freeze_support()
    PyPackApp().mainloop()
