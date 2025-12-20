import tkinter as tk
from tkinter import filedialog, messagebox
from PIL import Image, ImageTk
import math
import os

# --- CONFIGURAÇÃO DE ALTA PERFORMANCE ---
Image.MAX_IMAGE_PIXELS = None 

class AppVisualizadorPro:
    def __init__(self, root):
        self.root = root
        self.root.title("Slicer Visual Scientific - Native Pillow Engine")
        self.root.geometry("1024x768")
        self.root.configure(bg="#1e1e1e")

        # --- Variáveis de Estado ---
        self.caminho_imagem = None
        self.imagem_original = None
        self.imagem_preview = None
        self.preview_scale = 1.0        
        self.tk_image = None            
        
        # Câmera e Zoom
        self.zoom_level = 1.0
        self.camera_x = 0  
        self.camera_y = 0
        
        # Estado do Mouse
        self.last_mouse_x = 0
        self.last_mouse_y = 0

        self.criar_interface()

    def criar_interface(self):
        # Barra de Ferramentas
        frame_topo = tk.Frame(self.root, bg="#2c3e50", height=50)
        frame_topo.pack(fill=tk.X)

        style_btn = {"bg": "#34495e", "fg": "white", "relief": "flat", "font": ("Arial", 10)}

        tk.Button(frame_topo, text="📂 Abrir Imagem", command=self.carregar_imagem, **style_btn).pack(side=tk.LEFT, padx=10, pady=10)
        
        tk.Label(frame_topo, text="Tamanho do Corte (px):", bg="#2c3e50", fg="white").pack(side=tk.LEFT)
        self.entry_grid = tk.Entry(frame_topo, width=8, justify="center")
        self.entry_grid.insert(0, "1000")
        self.entry_grid.pack(side=tk.LEFT, padx=5)
        
        tk.Button(frame_topo, text="🔄 Redesenhar", command=self.redesenhar, **style_btn).pack(side=tk.LEFT, padx=5)

        tk.Button(frame_topo, text="✂️ FATIAR AGORA", command=self.fatiar_nativo, bg="#e74c3c", fg="white", font=("Arial", 10, "bold")).pack(side=tk.RIGHT, padx=10)

        # Canvas
        self.canvas_frame = tk.Frame(self.root, bg="#000")
        self.canvas_frame.pack(fill=tk.BOTH, expand=True)
        
        self.canvas = tk.Canvas(self.canvas_frame, bg="#111", highlightthickness=0)
        self.canvas.pack(fill=tk.BOTH, expand=True)

        # Eventos
        self.canvas.bind("<ButtonPress-1>", self.clique_iniciar)
        self.canvas.bind("<B1-Motion>", self.clique_arrastar)
        self.canvas.bind("<MouseWheel>", self.zoom_windows)
        self.canvas.bind("<Button-4>", lambda e: self.zoom_linux(1))
        self.canvas.bind("<Button-5>", lambda e: self.zoom_linux(-1))
        self.canvas.bind("<Configure>", lambda e: self.redesenhar())

    def carregar_imagem(self):
        path = filedialog.askopenfilename(filetypes=[("Imagens", "*.jpg;*.png;*.tif;*.tiff;*.bmp")])
        if not path: return
        
        self.caminho_imagem = path
        try:
            self.imagem_original = Image.open(path)
            w_real, h_real = self.imagem_original.size
            
            max_preview_size = 2048
            if w_real > max_preview_size or h_real > max_preview_size:
                ratio = min(max_preview_size / w_real, max_preview_size / h_real)
                new_w = int(w_real * ratio)
                new_h = int(h_real * ratio)
                print(f"Gerando cache: {new_w}x{new_h}...")
                self.imagem_preview = self.imagem_original.resize((new_w, new_h), Image.Resampling.LANCZOS)
                self.preview_scale = w_real / new_w
            else:
                self.imagem_preview = self.imagem_original.copy()
                self.preview_scale = 1.0

            # Reset Camera
            w_tela = self.canvas.winfo_width()
            h_tela = self.canvas.winfo_height()
            self.zoom_level = min(w_tela/w_real, h_tela/h_real)
            self.camera_x = 0
            self.camera_y = 0
            
            self.redesenhar()
        except Exception as e:
            messagebox.showerror("Erro", str(e))

    def clique_iniciar(self, event):
        self.last_mouse_x = event.x
        self.last_mouse_y = event.y

    def clique_arrastar(self, event):
        if not self.imagem_original: return
        dx = event.x - self.last_mouse_x
        dy = event.y - self.last_mouse_y
        self.camera_x -= dx / self.zoom_level
        self.camera_y -= dy / self.zoom_level
        self.last_mouse_x = event.x
        self.last_mouse_y = event.y
        self.redesenhar()

    def zoom_windows(self, event):
        if event.delta > 0: self.aplicar_zoom(1.2, event.x, event.y)
        else: self.aplicar_zoom(0.8, event.x, event.y)

    def zoom_linux(self, direction):
        cx, cy = self.canvas.winfo_width()/2, self.canvas.winfo_height()/2
        if direction > 0: self.aplicar_zoom(1.2, cx, cy)
        else: self.aplicar_zoom(0.8, cx, cy)

    def aplicar_zoom(self, fator, mouse_x, mouse_y):
        if not self.imagem_original: return
        novo_zoom = self.zoom_level * fator
        if novo_zoom < 0.001: return 

        world_x = self.camera_x + (mouse_x / self.zoom_level)
        world_y = self.camera_y + (mouse_y / self.zoom_level)
        self.zoom_level = novo_zoom
        self.camera_x = world_x - (mouse_x / self.zoom_level)
        self.camera_y = world_y - (mouse_y / self.zoom_level)
        self.redesenhar()

    def redesenhar(self):
        if not self.imagem_original: return
        w_canvas = self.canvas.winfo_width()
        h_canvas = self.canvas.winfo_height()
        
        left = self.camera_x
        top = self.camera_y
        right = left + (w_canvas / self.zoom_level)
        bottom = top + (h_canvas / self.zoom_level)

        usar_preview = False
        if self.zoom_level < 0.5 and self.preview_scale > 1.0:
            usar_preview = True
        
        try:
            if usar_preview:
                p_left = int(left / self.preview_scale)
                p_top = int(top / self.preview_scale)
                p_right = int(right / self.preview_scale)
                p_bottom = int(bottom / self.preview_scale)
                region = self.imagem_preview.crop((p_left, p_top, p_right, p_bottom))
                img_display = region.resize((w_canvas, h_canvas), Image.Resampling.NEAREST)
            else:
                w_real, h_real = self.imagem_original.size
                c_left = max(0, int(left))
                c_top = max(0, int(top))
                c_right = min(w_real, int(right))
                c_bottom = min(h_real, int(bottom))
                
                if c_right > c_left and c_bottom > c_top:
                    region = self.imagem_original.crop((c_left, c_top, c_right, c_bottom))
                    final_img = Image.new("RGB", (w_canvas, h_canvas), (17, 17, 17))
                    paste_x = int((c_left - left) * self.zoom_level)
                    paste_y = int((c_top - top) * self.zoom_level)
                    paste_w = int((c_right - c_left) * self.zoom_level)
                    paste_h = int((c_bottom - c_top) * self.zoom_level)
                    if paste_w > 0 and paste_h > 0:
                        region_resized = region.resize((paste_w, paste_h), Image.Resampling.NEAREST)
                        final_img.paste(region_resized, (paste_x, paste_y))
                        img_display = final_img
                    else: img_display = final_img
                else: img_display = Image.new("RGB", (w_canvas, h_canvas), (17, 17, 17))

            self.tk_image = ImageTk.PhotoImage(img_display)
            self.canvas.delete("all")
            self.canvas.create_image(0, 0, image=self.tk_image, anchor="nw")
            self.desenhar_grid_otimizado(left, top, right, bottom, w_canvas, h_canvas)
        except Exception as e:
            print(f"Erro render: {e}")

    def desenhar_grid_otimizado(self, left, top, right, bottom, w_canvas, h_canvas):
        try:
            block_size = int(self.entry_grid.get())
        except: return
        
        if (right - left) / block_size > 200: return 

        start_x = (left // block_size) * block_size
        if start_x < left: start_x += block_size
        x = start_x
        while x < right:
            screen_x = (x - left) * self.zoom_level
            self.canvas.create_line(screen_x, 0, screen_x, h_canvas, fill="yellow", dash=(2, 4))
            x += block_size
            
        start_y = (top // block_size) * block_size
        if start_y < top: start_y += block_size
        y = start_y
        while y < bottom:
            screen_y = (y - top) * self.zoom_level
            self.canvas.create_line(0, screen_y, w_canvas, screen_y, fill="yellow", dash=(2, 4))
            y += block_size

    def fatiar_nativo(self):
        """SUBSTITUI O IMAGE-SLICER: Lógica manual usando Pillow"""
        if not self.imagem_original: return
        
        try:
            block_size = int(self.entry_grid.get())
            w_total, h_total = self.imagem_original.size
            
            cols = math.ceil(w_total / block_size)
            rows = math.ceil(h_total / block_size)
            total_files = cols * rows
            
            if not messagebox.askyesno("Confirmar Fatiamento", 
                f"Tamanho Original: {w_total}x{h_total}\n"
                f"Tamanho do Bloco: {block_size}x{block_size}\n"
                f"Arquivos a gerar: {total_files}\n\nContinuar?"):
                return

            output_dir = filedialog.askdirectory()
            if not output_dir: return

            count = 0
            
            progresso = tk.Toplevel(self.root)
            progresso.title("Processando...")
            progresso.geometry("300x100")
            lbl_prog = tk.Label(progresso, text="Iniciando...", font=("Arial", 12))
            lbl_prog.pack(pady=20, expand=True)
            self.root.update()

            for y in range(0, h_total, block_size):
                for x in range(0, w_total, block_size):

                    box = (
                        x, 
                        y, 
                        min(x + block_size, w_total), 
                        min(y + block_size, h_total)
                    )
                    
                    tile = self.imagem_original.crop(box)
                    

                    col_idx = x // block_size
                    row_idx = y // block_size
                    filename = f"fatia_lin{row_idx:03d}_col{col_idx:03d}.png"
                    save_path = os.path.join(output_dir, filename)
                    
                    tile.save(save_path)
                    
                    count += 1
                    if count % 10 == 0:
                        lbl_prog.config(text=f"Salvando {count}/{total_files}...")
                        progresso.update()

            progresso.destroy()
            messagebox.showinfo("Sucesso", f"Processo concluído!\n{count} imagens salvas em:\n{output_dir}")

        except Exception as e:
            messagebox.showerror("Erro Crítico", str(e))

if __name__ == "__main__":
    root = tk.Tk()
    app = AppVisualizadorPro(root)
    root.mainloop()