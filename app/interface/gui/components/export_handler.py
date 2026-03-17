import logging
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import os
import threading

logger = logging.getLogger(__name__)


class ExportHandlerMixin:
    """Mixin for export functionality: tile export, slice-all, progress dialog."""

    def _setup_format_selector(self):
        f = tk.Frame(self.toolbar, bg=self.colors["toolbar"])
        f.pack(side=tk.LEFT, padx=3)
        
        self.format_var = tk.StringVar(value="PNG")
        format_names = [fmt[0] for fmt in self.EXPORT_FORMATS]
        
        self.format_dropdown = ttk.Combobox(f, textvariable=self.format_var, values=format_names, 
                                            state="readonly", width=5, font=("Segoe UI", 9))
        self.format_dropdown.pack(side=tk.LEFT, padx=2)
        self.format_dropdown.bind("<<ComboboxSelected>>", self._on_format_change)

    def _on_format_change(self, event=None):
        selected = self.format_var.get()
        for name, ext in self.EXPORT_FORMATS:
            if name == selected:
                self.export_format = ext
                break

    def save_selected_cells(self):
        s = self.current_session
        if not s or not s.tiles: 
            messagebox.showwarning("Warning", "No cells selected.")
            return
        
        n = len(s.tiles)
        msg = f"Save {n} tile(s) as {self.export_format.upper()[1:]}?"
        if not messagebox.askyesno("Confirm", msg): return
        
        out = filedialog.askdirectory(title="Select output folder")
        if not out:
            return

        self._run_export_with_progress(
            f"Exporting {n} tile(s)...",
            lambda cb: self.export_service.save_selected_cells(s, out, self.export_format, progress_callback=cb),
            lambda count: self._on_export_done(s, out, count, is_tile=True)
        )

    def _on_export_done(self, session, out, count, is_tile=False):
        """Called after export completes."""
        if is_tile:
            self.export_service.export_metadata(session, out)
            session.export_dir = out
            session.export_format = self.export_format
            self.trigger_modification()
            messagebox.showinfo("Done", f"{count} tile(s) saved as {self.export_format.upper()[1:]}.\nMetadata exported (CSV + JSON).")
        else:
            messagebox.showinfo("Done", f"{count} tiles saved to:\n{out}")

    def _run_export_with_progress(self, title, export_fn, on_done):
        """Run an export in a background thread with a modal progress dialog."""
        # Progress dialog
        dlg = tk.Toplevel(self.root)
        dlg.title(title)
        dlg.geometry("350x100")
        dlg.resizable(False, False)
        dlg.configure(bg="#2d2d2d")
        dlg.transient(self.root)
        dlg.grab_set()

        lbl = tk.Label(dlg, text="Preparing...", bg="#2d2d2d", fg="#ccc",
                       font=("Segoe UI", 10))
        lbl.pack(pady=(15, 5))

        bar = ttk.Progressbar(dlg, length=300, mode="determinate")
        bar.pack(pady=5)

        progress_data = {"current": 0, "total": 1, "result": None, "done": False}

        def progress_cb(current, total):
            progress_data["current"] = current
            progress_data["total"] = total

        def run():
            result = export_fn(progress_cb)
            progress_data["result"] = result
            progress_data["done"] = True

        t = threading.Thread(target=run, daemon=True)
        t.start()

        def poll():
            cur = progress_data["current"]
            tot = max(progress_data["total"], 1)
            pct = int(cur / tot * 100)
            bar["value"] = pct
            lbl.config(text=f"{cur} / {tot}  ({pct}%)")
            if progress_data["done"]:
                dlg.destroy()
                on_done(progress_data["result"])
            else:
                self.root.after(100, poll)

        self.root.after(100, poll)

    def _auto_reexport(self, session):
        """Re-export slices if session was previously exported."""
        if session.export_dir and session.export_format and session.tiles:
            try:
                if os.path.isdir(session.export_dir):
                    self.export_service.save_selected_cells(
                        session, session.export_dir, session.export_format)
                    self.status_bar.config(text=f"Auto-exported {len(session.tiles)} tile(s)")
            except Exception as e:
                logger.error("Auto-reexport error for session '%s': %s", session.name, e)

    def slice_all(self):
        s = self.current_session
        if not s: 
            messagebox.showwarning("Warning", "No image loaded.")
            return
        
        cols = (s.real_width + s.grid_w - 1) // s.grid_w
        rows = (s.real_height + s.grid_h - 1) // s.grid_h
        total = cols * rows
        
        msg = f"Split entire image into {total} tiles ({cols} cols x {rows} rows)?\n\n"
        msg += f"Grid: {s.grid_w}x{s.grid_h}px\n"
        msg += f"Image: {s.real_width}x{s.real_height}px\n"
        msg += f"Format: {self.export_format.upper()[1:]}"
        
        if not messagebox.askyesno("Confirm Tile All", msg): 
            return
        
        out = filedialog.askdirectory(title="Select output folder")
        if not out:
            return

        self._run_export_with_progress(
            f"Exporting {total} tiles...",
            lambda cb: self.export_service.slice_all(s, out, self.export_format, progress_callback=cb),
            lambda count: self._on_export_done(s, out, count, is_tile=False)
        )
