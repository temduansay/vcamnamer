"""
gui.py – Tkinter GUI for vcamnamer.

Layout
------
+--------------------------------------------------+
|  vcamnamer – OBS Virtual Camera Renamer          |
+--------------------------------------------------+
|  [Device Node] [Original Name] [Custom Name]     |
|  /dev/video0   Dummy video…    [OBS Studio Cam ] |
|  /dev/video2   Dummy video…    [Presentation   ] |
+--------------------------------------------------+
|  Status bar                                      |
+--------------------------------------------------+
|  [Refresh]  [Apply]  [Reset / Remove Rules]      |
+--------------------------------------------------+
"""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk
from typing import Dict, List, Optional

from vcamnamer.device_detector import VideoDevice, enumerate_devices
from vcamnamer.mapping_store import MappingStore, validate_name
from vcamnamer.rule_applier import apply_rules, remove_rules, rules_file_exists

# Column indices
_COL_NODE = 0
_COL_ORIG = 1
_COL_CUSTOM = 2

_COLUMNS = ("node", "original", "custom_name")
_HEADINGS = ("Device Node", "Original Name", "Custom Name")
_COL_WIDTHS = (140, 220, 220)


class VcamNamerApp(tk.Tk):
    """Main application window."""

    def __init__(self) -> None:
        super().__init__()
        self.title("vcamnamer – OBS Virtual Camera Renamer")
        self.resizable(True, True)
        self.minsize(640, 320)

        self._store = MappingStore()
        # {node: StringVar} for the edit fields
        self._custom_vars: Dict[str, tk.StringVar] = {}
        self._devices: List[VideoDevice] = []

        self._build_ui()
        self._refresh()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)

        # ── Main frame ──────────────────────────────────────────────────
        main = ttk.Frame(self, padding=8)
        main.grid(row=0, column=0, sticky="nsew")
        main.columnconfigure(0, weight=1)
        main.rowconfigure(1, weight=1)

        # ── Title ───────────────────────────────────────────────────────
        title_lbl = ttk.Label(
            main,
            text="Rename OBS / v4l2loopback Virtual Cameras",
            font=("TkDefaultFont", 11, "bold"),
        )
        title_lbl.grid(row=0, column=0, sticky="w", pady=(0, 6))

        # ── Device table (Treeview + scrollbar) ─────────────────────────
        table_frame = ttk.Frame(main)
        table_frame.grid(row=1, column=0, sticky="nsew")
        table_frame.columnconfigure(0, weight=1)
        table_frame.rowconfigure(0, weight=1)

        self._tree = ttk.Treeview(
            table_frame,
            columns=_COLUMNS,
            show="headings",
            selectmode="browse",
            height=8,
        )
        for col, heading, width in zip(_COLUMNS, _HEADINGS, _COL_WIDTHS):
            self._tree.heading(col, text=heading)
            self._tree.column(col, width=width, minwidth=80, stretch=True)
        self._tree.grid(row=0, column=0, sticky="nsew")

        vsb = ttk.Scrollbar(table_frame, orient="vertical", command=self._tree.yview)
        vsb.grid(row=0, column=1, sticky="ns")
        self._tree.configure(yscrollcommand=vsb.set)

        # ── Edit panel (shown when a row is selected) ───────────────────
        edit_frame = ttk.LabelFrame(main, text="Edit Custom Name", padding=6)
        edit_frame.grid(row=2, column=0, sticky="ew", pady=(6, 0))
        edit_frame.columnconfigure(1, weight=1)

        ttk.Label(edit_frame, text="Device:").grid(row=0, column=0, sticky="w")
        self._selected_node_lbl = ttk.Label(edit_frame, text="—", foreground="gray")
        self._selected_node_lbl.grid(row=0, column=1, sticky="w", padx=(4, 0))

        ttk.Label(edit_frame, text="Custom name:").grid(
            row=1, column=0, sticky="w", pady=(4, 0)
        )
        self._name_var = tk.StringVar()
        self._name_entry = ttk.Entry(edit_frame, textvariable=self._name_var, width=40)
        self._name_entry.grid(row=1, column=1, sticky="ew", padx=(4, 0), pady=(4, 0))
        self._name_entry.bind("<Return>", lambda _e: self._on_set_name())

        ttk.Button(edit_frame, text="Set Name", command=self._on_set_name).grid(
            row=1, column=2, padx=(4, 0), pady=(4, 0)
        )
        ttk.Button(edit_frame, text="Clear Name", command=self._on_clear_name).grid(
            row=1, column=3, padx=(4, 0), pady=(4, 0)
        )

        # ── Status bar ──────────────────────────────────────────────────
        self._status_var = tk.StringVar(value="Ready.")
        status_bar = ttk.Label(
            main,
            textvariable=self._status_var,
            relief="sunken",
            anchor="w",
            padding=(4, 2),
        )
        status_bar.grid(row=3, column=0, sticky="ew", pady=(6, 0))

        # ── Button bar ──────────────────────────────────────────────────
        btn_frame = ttk.Frame(main)
        btn_frame.grid(row=4, column=0, sticky="e", pady=(6, 0))

        ttk.Button(btn_frame, text="Refresh", command=self._refresh).pack(
            side="left", padx=4
        )
        ttk.Button(btn_frame, text="Apply Names", command=self._on_apply).pack(
            side="left", padx=4
        )
        ttk.Button(
            btn_frame,
            text="Reset / Remove Rules",
            command=self._on_reset,
        ).pack(side="left", padx=4)

        # Bind selection change
        self._tree.bind("<<TreeviewSelect>>", self._on_select)

    # ------------------------------------------------------------------
    # Data helpers
    # ------------------------------------------------------------------

    def _refresh(self) -> None:
        """Re-scan devices and reload the table."""
        self._store.load()
        self._devices = enumerate_devices()
        virtual = [d for d in self._devices if d.is_virtual]

        self._tree.delete(*self._tree.get_children())
        self._custom_vars.clear()

        if not virtual:
            self._set_status(
                "No virtual cameras detected. Is OBS / v4l2loopback loaded?",
                error=True,
            )
        else:
            for dev in virtual:
                custom = self._store.get(dev.node) or ""
                self._tree.insert(
                    "",
                    "end",
                    iid=dev.node,
                    values=(dev.node, dev.card, custom),
                )
            rules_note = " (rules applied)" if rules_file_exists() else ""
            self._set_status(
                f"Found {len(virtual)} virtual camera(s).{rules_note}"
            )

        # Reset edit panel
        self._selected_node_lbl.config(text="—", foreground="gray")
        self._name_var.set("")
        self._name_entry.config(state="disabled")

    def _selected_node(self) -> Optional[str]:
        sel = self._tree.selection()
        return sel[0] if sel else None

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------

    def _on_select(self, _event: object) -> None:
        node = self._selected_node()
        if node:
            self._selected_node_lbl.config(text=node, foreground="black")
            current_custom = self._store.get(node) or ""
            self._name_var.set(current_custom)
            self._name_entry.config(state="normal")
            self._name_entry.focus()

    def _on_set_name(self) -> None:
        node = self._selected_node()
        if not node:
            self._set_status("Select a device first.", error=True)
            return
        name = self._name_var.get()
        try:
            validate_name(name)
            self._store.set(node, name)
            self._store.save()
            self._tree.set(node, "custom_name", name.strip())
            self._set_status(f"Name set for {node}: '{name.strip()}'.")
        except ValueError as exc:
            self._set_status(str(exc), error=True)
            messagebox.showerror("Invalid name", str(exc), parent=self)

    def _on_clear_name(self) -> None:
        node = self._selected_node()
        if not node:
            self._set_status("Select a device first.", error=True)
            return
        self._store.remove(node)
        self._store.save()
        self._name_var.set("")
        self._tree.set(node, "custom_name", "")
        self._set_status(f"Custom name cleared for {node}.")

    def _on_apply(self) -> None:
        """Write udev rules and reload udev (requires root)."""
        mappings = self._store.all()
        if not mappings:
            self._set_status("No custom names set. Nothing to apply.", error=True)
            return
        try:
            apply_rules(mappings)
            self._set_status(
                f"udev rules applied for {len(mappings)} device(s). "
                "Symlinks are under /dev/vcam/."
            )
        except PermissionError as exc:
            self._set_status("Permission denied – see error dialog.", error=True)
            messagebox.showerror(
                "Permission denied",
                str(exc),
                parent=self,
            )
        except Exception as exc:  # noqa: BLE001
            self._set_status(f"Error: {exc}", error=True)
            messagebox.showerror("Error", str(exc), parent=self)

    def _on_reset(self) -> None:
        """Remove the app-generated udev rules file (rollback)."""
        if not rules_file_exists():
            self._set_status("No app-generated rules file found. Nothing to remove.")
            return
        if not messagebox.askyesno(
            "Remove rules?",
            "This will delete the vcamnamer udev rules file and remove all "
            "app-managed symlinks from /dev/vcam/.\n\nContinue?",
            parent=self,
        ):
            return
        try:
            remove_rules()
            self._set_status("Rules removed. App-managed symlinks have been cleaned up.")
        except PermissionError as exc:
            self._set_status("Permission denied – see error dialog.", error=True)
            messagebox.showerror("Permission denied", str(exc), parent=self)
        except Exception as exc:  # noqa: BLE001
            self._set_status(f"Error: {exc}", error=True)
            messagebox.showerror("Error", str(exc), parent=self)

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    def _set_status(self, msg: str, error: bool = False) -> None:
        self._status_var.set(msg)
        # We can't easily change ttk.Label foreground, so just log to console
        if error:
            print(f"[vcamnamer] ERROR: {msg}")
        else:
            print(f"[vcamnamer] {msg}")


def run_gui() -> None:
    """Launch the vcamnamer GUI (blocking call)."""
    app = VcamNamerApp()
    app.mainloop()
