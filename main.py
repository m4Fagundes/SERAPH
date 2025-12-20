import tkinter as tk
from tkinter import filedialog, messagebox, colorchooser
from PIL import Image, ImageTk
import math
import os

# --- CONFIGURAÇÃO DE ALTA PERFORMANCE ---
Image.MAX_IMAGE_PIXELS = None 

class AppVisualizadorPro:
    def __init__(self, root):
        self.root = root
        self.root.title("Slicer Visual Scientific - Custom Grid & Quick Save")
        self.root.geometry("1280x800")
        self.root.configure(bg="#1e1e1e")

        # --- Variáveis de Estado ---
        self.caminho_imagem = None
        self.imagem_original = None     
        self.imagem_preview = None      
        self.preview_scale = 1.0        
        self.tk_image = None            
        
        self.grid_color = "#FFFF00"
        
        self.zoom_level = 1.0
        self.camera_x = 0  
        self.camera_y = 0
        
        self.last_mouse_x = 0
        self.last_mouse_y = 0

        self.criar_interface()

    def criar_interface(self):
        frame_topo = tk.Frame(self.root, bg="#2c3e50", height=60)
        frame_topo.pack(fill=tk.X)

        style_lbl = {"bg": "#2c3e50", "fg": "white", "font": ("Arial", 9)}
        style_btn = {"bg": "#34495e", "fg": "white", "relief": "flat", "font": ("Arial", 9)}

        tk.Button(frame_topo, text="📂 Abrir", command=self.carregar_imagem, **style_btn).pack(side=tk.LEFT, padx=5, pady=10)

        tk.Label(frame_topo, text="Largura (W):", **style_lbl).pack(side=tk.LEFT, padx=(10, 2))
        self.entry_w = tk.Entry(frame_topo, width=6, justify="center")
        self.entry_w.insert(0, "1000")
        self.entry_w.pack(side=tk.LEFT)

        tk.Label(frame_topo, text="Altura (H):", **style_lbl).pack(side=tk.LEFT, padx=(10, 2))
        self.entry_h = tk.Entry(frame_topo, width=6, justify="center")
        self.entry_h.insert(0, "1000")
        self.entry_h.pack(side=tk.LEFT)
        
        tk.Button(frame_topo, text="🎨 Cor Grid", command=self.escolher_cor, **style_btn).pack(side=tk.LEFT, padx=10)
        
        tk.Button(frame_topo, text="🔄 Atualizar", command=self.redesenhar, **style_btn).pack(side=tk.LEFT, padx=5)

        tk.Label(frame_topo, text="| Duplo-Clique na tela p/ salvar fatia única |", bg="#2c3e50", fg="#f1c40f", font=("Arial", 9, "bold")).pack(side=tk.LEFT, padx=15)

        tk.Button(frame_topo, text="✂️ FATIAR TUDO", command=self.fatiar_tudo, bg="#e74c3c", fg="white", font=("Arial", 10, "bold")).pack(side=tk.RIGHT, padx=10)

        self.canvas_frame = tk.Frame(self.root, bg="#000")
        self.canvas_frame.pack(fill=tk.BOTH, expand=True)
        
        self.canvas = tk.Canvas(self.canvas_frame, bg="#111", highlightthickness=0)
        self.canvas.pack(fill=tk.BOTH, expand=True)

        self.canvas.bind("<ButtonPress-1>", self.clique_iniciar)
        self.canvas.bind("<B1-Motion>", self.clique_arrastar)
        self.canvas.bind("<MouseWheel>", self.zoom_windows)
        self.canvas.bind("<Button-4>", lambda e: self.zoom_linux(1))
        self.canvas.bind("<Button-5>", lambda e: self.zoom_linux(-1))
        self.canvas.bind("<Configure>", lambda e: self.redesenhar())
        
        self.canvas.bind("<Double-Button-1>", self.salvar_clique)

    def escolher_cor(self):
        cor = colorchooser.askcolor(title="Escolha a cor do Grid")[1]
        if cor:
            self.grid_color = cor
            self.redesenhar()

    def get_dimensoes_grid(self):
        try:
            w = int(self.entry_w.get())
            h = int(self.entry_h.get())
            return w, h
        except:
            return 1000, 1000

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
                self.imagem_preview = self.imagem_original.resize((new_w, new_h), Image.Resampling.LANCZOS)
                self.preview_scale = w_real / new_w
            else:
                self.imagem_preview = self.imagem_original.copy()
                self.preview_scale = 1.0

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

    def salvar_clique(self, event):
        """Salva a fatia específica onde o usuário clicou duas vezes"""
        if not self.imagem_original: return
        
        click_screen_x = event.x
        click_screen_y = event.y
        
        real_x = self.camera_x + (click_screen_x / self.zoom_level)
        real_y = self.camera_y + (click_screen_y / self.zoom_level)
        
        w_block, h_block = self.get_dimensoes_grid()
        
        col_idx = int(real_x // w_block)
        row_idx = int(real_y // h_block)
        
        x1 = col_idx * w_block
        y1 = row_idx * h_block
        x2 = x1 + w_block
        y2 = y1 + h_block
        
        w_total, h_total = self.imagem_original.size
        
        if x1 >= w_total or y1 >= h_total or x1 < 0 or y1 < 0:
            return
            
        x2 = min(x2, w_total)
        y2 = min(y2, h_total)
        
        box = (x1, y1, x2, y2)
        try:
            img_corte = self.imagem_original.crop(box)
            
            default_name = f"fatia_lin{row_idx}_col{col_idx}.png"
            
            fpath = filedialog.asksaveasfilename(
                initialfile=default_name,
                defaultextension=".png",
                filetypes=[("PNG", "*.png"), ("JPG", "*.jpg"), ("TIFF", "*.tiff")]
            )
            
            if fpath:
                img_corte.save(fpath)
                messagebox.showinfo("Salvo", f"Fatia salva com sucesso!\n{os.path.basename(fpath)}")
                
        except Exception as e:
            messagebox.showerror("Erro ao salvar fatia", str(e))

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
        w_block, h_block = self.get_dimensoes_grid()
        
        if (right - left) / w_block > 300 or (bottom - top) / h_block > 300: 
            return 

        start_x = (left // w_block) * w_block
        if start_x < left: start_x += w_block
        x = start_x
        while x < right:
            screen_x = (x - left) * self.zoom_level
            self.canvas.create_line(screen_x, 0, screen_x, h_canvas, fill=self.grid_color, dash=(2, 4))
            x += w_block
            
        # Linhas Horizontais
        start_y = (top // h_block) * h_block
        if start_y < top: start_y += h_block
        y = start_y
        while y < bottom:
            screen_y = (y - top) * self.zoom_level
            self.canvas.create_line(0, screen_y, w_canvas, screen_y, fill=self.grid_color, dash=(2, 4))
            y += h_block

    def fatiar_tudo(self):
        if not self.imagem_original: return
        
        try:
            w_block, h_block = self.get_dimensoes_grid()
            w_total, h_total = self.imagem_original.size
            
            cols = math.ceil(w_total / w_block)
            rows = math.ceil(h_total / h_block)
            total_files = cols * rows
            
            if not messagebox.askyesno("Confirmar Fatiamento", 
                f"Grid: {w_block}x{h_block} px\n"
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

            for y in range(0, h_total, h_block):
                for x in range(0, w_total, w_block):
                    box = (x, y, min(x + w_block, w_total), min(y + h_block, h_total))
                    tile = self.imagem_original.crop(box)
                    
                    col_idx = x // w_block
                    row_idx = y // h_block
                    filename = f"fatia_lin{row_idx:03d}_col{col_idx:03d}.png"
                    
                    tile.save(os.path.join(output_dir, filename))
                    
                    count += 1
                    if count % 10 == 0: 
                        lbl_prog.config(text=f"Salvando {count}/{total_files}...")
                        progresso.update()

            progresso.destroy()
            messagebox.showinfo("Sucesso", f"Processo concluído!\n{count} imagens salvas.")

        except Exception as e:
            messagebox.showerror("Erro Crítico", str(e))

if __name__ == "__main__":
    root = tk.Tk()
    app = AppVisualizadorPro(root)
    root.mainloop()