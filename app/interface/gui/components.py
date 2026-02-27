import tkinter as tk
from tkinter import ttk
import platform

class UIComponents:
    def __init__(self):
        self.is_mac = platform.system() == "Darwin"

    def create_button(self, parent, text, command, style_type="default", width=None, side=tk.LEFT, padx=2, pady=8, fill=None):
        """Create a button that works correctly on both macOS and Windows"""
        if self.is_mac:
            # Use ttk.Button on macOS (works well)
            if style_type == "accent":
                style = "Accent.TButton"
            elif style_type == "green":
                style = "Green.TButton"
            elif style_type == "zoom":
                style = "Zoom.TButton"
            elif style_type == "danger":
                style = "Danger.TButton"
            else:
                style = "Dark.TButton"
            
            btn = ttk.Button(parent, text=text, command=command, style=style)
            if width:
                btn.configure(width=width)
        else:
            # Use tk.Button on Windows (ttk has styling issues)
            if style_type == "accent":
                bg = "#007acc"
                active_bg = "#005a9e"
                font = ("Segoe UI", 9, "bold")
            elif style_type == "green":
                bg = "#27ae60"
                active_bg = "#2ecc71"
                font = ("Segoe UI", 10)
            elif style_type == "zoom":
                bg = "#444444"
                active_bg = "#555555"
                font = ("Segoe UI", 12, "bold")
            elif style_type == "danger":
                bg = "#c0392b"
                active_bg = "#e74c3c"
                font = ("Segoe UI", 9)
            else:
                bg = "#444444"
                active_bg = "#555555"
                font = ("Segoe UI", 10)
            
            btn = tk.Button(parent, text=text, command=command,
                           bg=bg, fg="white",
                           activebackground=active_bg, activeforeground="white",
                           relief="flat", font=font,
                           padx=10, pady=5,
                           cursor="hand2")
            if width:
                btn.configure(width=width)
        
        if fill:
            btn.pack(side=side, padx=padx, pady=pady, fill=fill)
        else:
            btn.pack(side=side, padx=padx, pady=pady)
        return btn

def setup_ttk_styles():
    """Configure ttk styles that work correctly on macOS"""
    style = ttk.Style()
    
    # Default button (gray)
    style.configure("Dark.TButton",
                    background="#444444",
                    foreground="#ffffff",
                    padding=(10, 5),
                    font=("Segoe UI", 10))
    style.map("Dark.TButton",
              background=[("active", "#555555"), ("pressed", "#333333")],
              foreground=[("active", "#ffffff"), ("pressed", "#ffffff")])
    
    # Accent button (blue)
    style.configure("Accent.TButton",
                    background="#007acc",
                    foreground="#ffffff",
                    padding=(10, 5),
                    font=("Segoe UI", 9, "bold"))
    style.map("Accent.TButton",
              background=[("active", "#005a9e"), ("pressed", "#004080")],
              foreground=[("active", "#ffffff"), ("pressed", "#ffffff")])
    
    # Green button
    style.configure("Green.TButton",
                    background="#27ae60",
                    foreground="#ffffff",
                    padding=(10, 5),
                    font=("Segoe UI", 10))
    style.map("Green.TButton",
              background=[("active", "#2ecc71"), ("pressed", "#1e8449")],
              foreground=[("active", "#ffffff"), ("pressed", "#ffffff")])
    
    # Zoom button (smaller)
    style.configure("Zoom.TButton",
                    background="#444444",
                    foreground="#ffffff",
                    padding=(5, 2),
                    font=("Segoe UI", 12, "bold"))
    style.map("Zoom.TButton",
              background=[("active", "#555555"), ("pressed", "#333333")],
              foreground=[("active", "#ffffff"), ("pressed", "#ffffff")])
    
    # Danger button (red)
    style.configure("Danger.TButton",
                    background="#c0392b",
                    foreground="#ffffff",
                    padding=(6, 3),
                    font=("Segoe UI", 9))
    style.map("Danger.TButton",
              background=[("active", "#e74c3c"), ("pressed", "#a93226")],
              foreground=[("active", "#ffffff"), ("pressed", "#ffffff")])
