import tkinter as tk
from app.interface.gui.main_window import SlicerLabApp

if __name__ == "__main__":
    root = tk.Tk()
    app = SlicerLabApp(root)
    root.mainloop()