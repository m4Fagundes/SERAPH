import tkinter as tk
from tkinter import filedialog, messagebox
import os
from app.domain.session import ImageSession


class ProjectManagerMixin:
    """Mixin for project management: new/open/save, sessions, autosave, undo/redo."""

    def _setup_project_menu(self):
        f = tk.Frame(self.toolbar, bg=self.colors["toolbar"])
        f.pack(side=tk.LEFT, padx=5)
        
        self.project_menubutton = tk.Menubutton(f, text="📁 Project ▾", 
                                                 bg="#444", fg="white", 
                                                 relief="flat", 
                                                 font=("Segoe UI", 10),
                                                 activebackground="#555",
                                                 activeforeground="white",
                                                 padx=10, pady=5)
        self.project_menubutton.pack(side=tk.LEFT)
        
        self.project_menu = tk.Menu(self.project_menubutton, tearoff=0,
                                    bg="#333", fg="white",
                                    activebackground="#007acc",
                                    activeforeground="white",
                                    font=("Segoe UI", 10))
        self.project_menubutton["menu"] = self.project_menu
        
        self.project_menu.add_command(label="📄 New Project", command=self.new_project)
        self.project_menu.add_command(label="📂 Open Project...", command=self.open_project)
        self.project_menu.add_separator()
        self.project_menu.add_command(label="💾 Save As...", command=self.save_project_as)

    def trigger_modification(self, event=None):
        if not self.current_project_path:
            self.save_status_label.config(text="* Unsaved")
            return

        self.save_status_label.config(text="Modified...")
        if self.autosave_timer:
            self.root.after_cancel(self.autosave_timer)
        self.autosave_timer = self.root.after(2000, self._execute_autosave)

    def _execute_autosave(self):
        if self.current_project_path:
            try:
                self._write_project_file(self.current_project_path)
                self.save_status_label.config(text="Auto-saved")
            except Exception as e:
                self.save_status_label.config(text="AutoSave Error")
                print(f"AutoSave Error: {e}")

    def _write_project_file(self, path):
        if self.current_session:
            try:
                self.current_session.grid_w = int(self.entry_w.get())
                self.current_session.grid_h = int(self.entry_h.get())
            except: pass

        self.project_service.save_project(path, self.sessions)

    def new_project(self):
        if self.sessions:
            if not messagebox.askyesno("New Project", "This will close the current project.\nUnsaved changes will be lost.\n\nContinue?"):
                return
        
        self._dismiss_welcome()
        self.sessions.clear()
        self.file_list.delete(0, tk.END)
        self.current_session = None
        self.current_project_path = None
        self.canvas.delete("all")
        self.undo_manager.clear()
        
        self.entry_w.delete(0, tk.END)
        self.entry_w.insert(0, "1000")
        self.entry_h.delete(0, tk.END)
        self.entry_h.insert(0, "1000")
        
        self.format_var.set("PNG")
        self.export_format = ".png"
        
        self.root.title("Tiles Grid Analyzer - New Project")
        self.save_status_label.config(text="")
        self.status_bar.config(text="New project created. Add an image to start.")
        self.zoom_label.config(text="100%")
        self._update_slice_previews()

    def save_project_as(self):
        if not self.sessions:
            messagebox.showwarning("Warning", "No images to save.")
            return
            
        f = filedialog.asksaveasfilename(defaultextension=".lab", filetypes=[("Lab Project", "*.lab")])
        if f:
            self.current_project_path = f
            self._write_project_file(f)
            self.root.title(f"Tiles Grid Analyzer - {os.path.basename(f)}")
            messagebox.showinfo("Success", "Project saved! AutoSave enabled.")

    def open_project(self):
        f = filedialog.askopenfilename(filetypes=[("Lab Project", "*.lab")])
        if not f: return
        
        try:
            sessions, missing = self.project_service.load_project(f)

            # Re-link missing images
            if missing:
                for entry in missing:
                    name = os.path.basename(entry["rel_path"])
                    answer = messagebox.askyesno(
                        "Image Not Found",
                        f"Image not found:\n  {entry['rel_path']}\n\n"
                        f"Would you like to locate \"{name}\" manually?")
                    if answer:
                        new_path = filedialog.askopenfilename(
                            title=f"Locate: {name}",
                            filetypes=[("All Supported", "*.jpg;*.jpeg;*.png;*.tif;*.tiff;*.bmp;*.webp;*.ndpi;*.svs;*.mrxs;*.scn;*.vms;*.vmu;*.bif")])
                        if new_path and os.path.exists(new_path):
                            # Build session from the item data with the new path
                            item = entry["item"]
                            try:
                                s = ImageSession(new_path)
                                s.grid_w = item.get("grid_w", 1000)
                                s.grid_h = item.get("grid_h", 1000)
                                s.zoom_level = item.get("zoom_level", 1.0)
                                s.camera_x = item.get("camera_x", 0)
                                s.camera_y = item.get("camera_y", 0)
                                sel = item.get("selected_regions", item.get("selected_cells", []))
                                if sel and isinstance(sel[0], (list, tuple)):
                                    if sel[0] and isinstance(sel[0][0], (list, tuple)):
                                        s.selected_cells = [set(tuple(r) for r in group) for group in sel]
                                    else:
                                        s.selected_cells = [{tuple(r)} for r in sel if len(r) == 4]
                                s.slice_metadata = item.get("slice_metadata", [])
                                raw_polys = item.get("selected_polygons", [])
                                s.selected_polygons = [
                                    [tuple(pt) for pt in poly] if poly else None
                                    for poly in raw_polys
                                ]
                                s.sync_metadata()
                                s.grid_color = item.get("grid_color", "#FFFF00")
                                s.export_dir = item.get("export_dir", None)
                                s.export_format = item.get("export_format", None)
                                sessions.append(s)
                            except Exception as ex:
                                messagebox.showwarning("Warning", f"Could not load image:\n{ex}")

            self.sessions = sessions

            self._dismiss_welcome()
            self.file_list.delete(0, tk.END)
            self.current_session = None
            self.canvas.delete("all")
            self.undo_manager.clear()
            
            for s in self.sessions:
                self.file_list.insert(tk.END, f" {s.name}")

            # All sessions are immediately ready (on-demand)
            if self.sessions:
                self._activate_session(self.sessions[0])
            
            self.current_project_path = f
            self.root.title(f"Tiles Grid Analyzer - {os.path.basename(f)}")
            self.save_status_label.config(text="Project Loaded")
            self._update_slice_previews()
            
        except Exception as e:
            messagebox.showerror("Error", f"Error opening project: {e}")
            print(e)

    def add_image_btn(self):
        path = filedialog.askopenfilename(filetypes=[("All Supported", "*.jpg;*.jpeg;*.png;*.tif;*.tiff;*.bmp;*.webp;*.ndpi;*.svs;*.mrxs;*.scn;*.vms;*.vmu;*.bif"), ("Images", "*.jpg;*.jpeg;*.png;*.tif;*.tiff;*.bmp;*.webp"), ("Whole-Slide Images", "*.ndpi;*.svs;*.mrxs;*.scn;*.vms;*.vmu;*.bif")])
        if path:
            self._add_session(path)
            self.trigger_modification()

    def _add_session(self, path):
        if self.current_session:
            try:
                self.current_session.grid_w = int(self.entry_w.get())
                self.current_session.grid_h = int(self.entry_h.get())
            except: pass

        try:
            new_session = ImageSession(path)
            self.sessions.append(new_session)
            self.file_list.insert(tk.END, f" {new_session.name}")
            self.file_list.selection_clear(0, tk.END)
            self.file_list.selection_set(tk.END)
            self._activate_session(new_session)
            self.status_bar.config(text=f"Loaded: {new_session.name} | {new_session.real_width:,}×{new_session.real_height:,} px")
        except Exception as e:
            messagebox.showerror("Error", str(e))

    def switch_image_tab(self, event):
        sel = self.file_list.curselection()
        if not sel: return
        idx = sel[0]
        if 0 <= idx < len(self.sessions):
            if self.current_session:
                try:
                    self.current_session.grid_w = int(self.entry_w.get())
                    self.current_session.grid_h = int(self.entry_h.get())
                except: pass
            
            self._activate_session(self.sessions[idx])

    def _activate_session(self, session):
        self.current_session = session
        
        self.entry_w.delete(0, tk.END)
        self.entry_w.insert(0, str(session.grid_w))
        self.entry_h.delete(0, tk.END)
        self.entry_h.insert(0, str(session.grid_h))
        
        if session.zoom_level == 1.0 and session.camera_x == 0:
            w_can = self.canvas.winfo_width()
            if w_can > 10:
                ratio = min(w_can/session.real_width, self.canvas.winfo_height()/session.real_height)
                session.zoom_level = ratio * 0.9

        self.status_bar.config(text=f"Image: {session.name} | Size: {session.real_width}x{session.real_height}px")
        self.redraw()
        self._update_zoom_label()

    def _undo(self):
        """Undo the last tile action."""
        session = self.undo_manager.undo()
        if session:
            self.redraw()
            self._update_slice_previews()
            self.trigger_modification()
            self.status_bar.config(text="Undo")

    def _redo(self):
        """Redo the last undone action."""
        session = self.undo_manager.redo()
        if session:
            self.redraw()
            self._update_slice_previews()
            self.trigger_modification()
            self.status_bar.config(text="Redo")

    def _save_shortcut(self):
        """Ctrl+S: save to current path or prompt Save As."""
        if self.current_project_path:
            self._write_project_file(self.current_project_path)
            self.save_status_label.config(text="Saved")
        else:
            self.save_project_as()
