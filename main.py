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
        self.root.title("Slicer Visual Scientific - Notebook Touchpad Support")
        self.root.geometry("1280x800")
        self.root.configure(bg="#1e1e1e")

        # --- Variáveis de Estado ---
        self.caminho_imagem = None
        self.imagem_original = None     
        self.imagem_preview = None      
        self.preview_scale = 1.0        
        self.tk_image = None            
        
        # Grid e Seleção
        self.grid_color = "#FFFF00"
        self.selected_cells = set() 
        
        # Câmera e Zoom
        self.zoom_level = 1.0
        self.camera_x = 0  
        self.camera_y = 0
        
        # Mouse (Arrastar)
        self.last_mouse_x = 0
        self.last_mouse_y = 0

        self.criar_interface()

    def criar_interface(self):
        # Barra de Ferramentas
        frame_topo = tk.Frame(self.root, bg="#2c3e50", height=60)
        frame_topo.pack(fill=tk.X)

        style_lbl = {"bg": "#2c3e50", "fg": "white", "font": ("Arial", 9)}
        style_btn = {"bg": "#34495e", "fg": "white", "relief": "flat", "font": ("Arial", 9)}

        # Controles
        tk.Button(frame_topo, text="📂 Abrir", command=self.carregar_imagem, **style_btn).pack(side=tk.LEFT, padx=5, pady=10)

        tk.Label(frame_topo, text="Largura (W):", **style_lbl).pack(side=tk.LEFT, padx=(10, 2))
        self.entry_w = tk.Entry(frame_topo, width=5, justify="center")
        self.entry_w.insert(0, "1000")
        self.entry_w.pack(side=tk.LEFT)

        tk.Label(frame_topo, text="Altura (H):", **style_lbl).pack(side=tk.LEFT, padx=(10, 2))
        self.entry_h = tk.Entry(frame_topo, width=5, justify="center")
        self.entry_h.insert(0, "1000")
        self.entry_h.pack(side=tk.LEFT)
        
        tk.Button(frame_topo, text="🎨 Cor", command=self.escolher_cor, **style_btn).pack(side=tk.LEFT, padx=5)
        tk.Button(frame_topo, text="🔄 Atualizar", command=self.redesenhar, **style_btn).pack(side=tk.LEFT, padx=5)

        tk.Label(frame_topo, text="| Scroll: Mover | Ctrl+Scroll: Zoom |", bg="#2c3e50", fg="#f1c40f", font=("Arial", 9, "bold")).pack(side=tk.LEFT, padx=15)

        tk.Button(frame_topo, text="💾 SALVAR SELEÇÃO", command=self.salvar_selecionados, bg="#3498db", fg="white", font=("Arial", 9, "bold")).pack(side=tk.RIGHT, padx=5)
        tk.Button(frame_topo, text="✂️ SALVAR TUDO", command=self.fatiar_tudo, bg="#e74c3c", fg="white", font=("Arial", 9, "bold")).pack(side=tk.RIGHT, padx=5)

        # Canvas
        self.canvas_frame = tk.Frame(self.root, bg="#000")
        self.canvas_frame.pack(fill=tk.BOTH, expand=True)
        
        self.canvas = tk.Canvas(self.canvas_frame, bg="#111", highlightthickness=0)
        self.canvas.pack(fill=tk.BOTH, expand=True)

        # --- BINDINGS (CONTROLES) ATUALIZADOS PARA NOTEBOOK ---
        
        # 1. Clique e Arrastar (Mãozinha)
        self.canvas.bind("<ButtonPress-1>", self.clique_iniciar)
        self.canvas.bind("<B1-Motion>", self.clique_arrastar)
        
        # 2. Seleção (Botão Direito)
        self.canvas.bind("<Button-3>", self.toggle_selecao)
        
        # 3. WINDOWS: Scroll do Touchpad
        # Sem Modifier -> PAN (Mover Vertical)
        self.canvas.bind("<MouseWheel>", self.scroll_vertical_windows)
        # Shift -> PAN (Mover Horizontal)
        self.canvas.bind("<Shift-MouseWheel>", self.scroll_horizontal_windows)
        # Control -> ZOOM
        self.canvas.bind("<Control-MouseWheel>", self.zoom_windows)
        
        # 4. LINUX: Scroll (Button 4/5 = Vertical, Shift+... = Horizontal)
        self.canvas.bind("<Button-4>", self.scroll_linux_up)
        self.canvas.bind("<Button-5>", self.scroll_linux_down)
        self.canvas.bind("<Control-Button-4>", lambda e: self.aplicar_zoom(1.1, e.x, e.y))
        self.canvas.bind("<Control-Button-5>", lambda e: self.aplicar_zoom(0.9, e.x, e.y))
        self.canvas.bind("<Shift-Button-4>", self.scroll_linux_left)
        self.canvas.bind("<Shift-Button-5>", self.scroll_linux_right)

        # 5. Geral
        self.canvas.bind("<Configure>", lambda e: self.redesenhar())
        self.root.bind("<c>", self.limpar_selecao)
        self.root.bind("<C>", self.limpar_selecao)

    # --- Lógica de Scroll e Pan (Touchpad) ---
    
    def scroll_vertical_windows(self, event):
        """Touchpad 2 dedos para cima/baixo -> Move Vertical"""
        if not self.imagem_original: return
        # Sensibilidade do touchpad (ajuste o divisor se ficar muito rápido)
        speed = 20 
        delta = -1 * (event.delta / 120) * speed 
        self.camera_y += delta / self.zoom_level
        self.redesenhar()

    def scroll_horizontal_windows(self, event):
        """Touchpad Shift + 2 dedos -> Move Horizontal"""
        if not self.imagem_original: return
        speed = 20
        delta = -1 * (event.delta / 120) * speed
        self.camera_x += delta / self.zoom_level
        self.redesenhar()

    def scroll_linux_up(self, event):
        # Linux Button-4 é "Roda pra cima"
        if not self.imagem_original: return
        self.camera_y -= 50 / self.zoom_level
        self.redesenhar()

    def scroll_linux_down(self, event):
        # Linux Button-5 é "Roda pra baixo"
        if not self.imagem_original: return
        self.camera_y += 50 / self.zoom_level
        self.redesenhar()

    def scroll_linux_left(self, event):
        if not self.imagem_original: return
        self.camera_x -= 50 / self.zoom_level
        self.redesenhar()

    def scroll_linux_right(self, event):
        if not self.imagem_original: return
        self.camera_x += 50 / self.zoom_level
        self.redesenhar()

    # --- Lógica de Zoom (Apenas com CTRL) ---
    def zoom_windows(self, event):
        """Só dá zoom se segurar CTRL"""
        # Verifica se o CTRL está pressionado (state 4 ou 12 geralmente) ou via bind direto
        if event.delta > 0: self.aplicar_zoom(1.2, event.x, event.y)
        else: self.aplicar_zoom(0.8, event.x, event.y)

    # ... RESTANTE DO CÓDIGO PERMANECE IGUAL ...
    
    def get_dimensoes_grid(self):
        try:
            w = int(self.entry_w.get())
            h = int(self.entry_h.get())
            return max(10, w), max(10, h)
        except: return 1000, 1000

    def carregar_imagem(self):
        path = filedialog.askopenfilename(filetypes=[("Imagens", "*.jpg;*.png;*.tif;*.tiff;*.bmp")])
        if not path: return
        
        self.caminho_imagem = path
        self.selected_cells.clear()
        
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

    def toggle_selecao(self, event):
        if not self.imagem_original: return
        real_x = self.camera_x + (event.x / self.zoom_level)
        real_y = self.camera_y + (event.y / self.zoom_level)
        w_block, h_block = self.get_dimensoes_grid()
        col = int(real_x // w_block)
        row = int(real_y // h_block)
        w_img, h_img = self.imagem_original.size
        if real_x < 0 or real_y < 0 or real_x > w_img or real_y > h_img: return

        key = (col, row)
        if key in self.selected_cells: self.selected_cells.remove(key)
        else: self.selected_cells.add(key)
        self.redesenhar()

    def limpar_selecao(self, event=None):
        self.selected_cells.clear()
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
        if self.zoom_level < 0.5 and self.preview_scale > 1.0: usar_preview = True
        
        try:
            self.canvas.delete("all")
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
            self.canvas.create_image(0, 0, image=self.tk_image, anchor="nw")
            self.desenhar_overlays(left, top, right, bottom, w_canvas, h_canvas)
        except Exception as e: print(f"Erro render: {e}")

    def desenhar_overlays(self, left, top, right, bottom, w_canvas, h_canvas):
        w_block, h_block = self.get_dimensoes_grid()
        start_col = int(left // w_block)
        end_col = int(right // w_block) + 1
        start_row = int(top // h_block)
        end_row = int(bottom // h_block) + 1

        for key in self.selected_cells:
            col, row = key
            if start_col <= col <= end_col and start_row <= row <= end_row:
                x1_world = col * w_block
                y1_world = row * h_block
                x2_world = x1_world + w_block
                y2_world = y1_world + h_block
                x1_screen = (x1_world - left) * self.zoom_level
                y1_screen = (y1_world - top) * self.zoom_level
                x2_screen = (x2_world - left) * self.zoom_level
                y2_screen = (y2_world - top) * self.zoom_level
                self.canvas.create_rectangle(x1_screen, y1_screen, x2_screen, y2_screen,
                                           fill="cyan", outline=self.grid_color, stipple="gray25", width=2)

        if (right - left) / w_block > 300: return
        start_x = (left // w_block) * w_block
        if start_x < left: start_x += w_block
        x = start_x
        while x < right:
            sx = (x - left) * self.zoom_level
            self.canvas.create_line(sx, 0, sx, h_canvas, fill=self.grid_color, dash=(2, 4))
            x += w_block
        start_y = (top // h_block) * h_block
        if start_y < top: start_y += h_block
        y = start_y
        while y < bottom:
            sy = (y - top) * self.zoom_level
            self.canvas.create_line(0, sy, w_canvas, sy, fill=self.grid_color, dash=(2, 4))
            y += h_block

    def escolher_cor(self):
        cor = colorchooser.askcolor(title="Cor do Grid")[1]
        if cor:
            self.grid_color = cor
            self.redesenhar()

    def fatiar_tudo(self):
        if not self.imagem_original: return
        w_block, h_block = self.get_dimensoes_grid()
        w_total, h_total = self.imagem_original.size
        total_files = math.ceil(w_total/w_block) * math.ceil(h_total/h_block)
        if not messagebox.askyesno("Confirmar", f"Isso vai gerar {total_files} arquivos.\nDeseja continuar?"): return
        self._processar_salvamento(todas=True)

    def salvar_selecionados(self):
        if not self.imagem_original: return
        if not self.selected_cells:
            messagebox.showwarning("Atenção", "Nenhum quadrado selecionado.")
            return
        if not messagebox.askyesno("Confirmar", f"Salvar {len(self.selected_cells)} fatias selecionadas?"): return
        self._processar_salvamento(todas=False)

    def _processar_salvamento(self, todas=False):
        output_dir = filedialog.askdirectory()
        if not output_dir: return
        w_block, h_block = self.get_dimensoes_grid()
        w_total, h_total = self.imagem_original.size
        count = 0
        lista_tarefas = []
        if todas:
            for y in range(0, h_total, h_block):
                for x in range(0, w_total, w_block):
                    lista_tarefas.append((x, y))
        else:
            for (col, row) in self.selected_cells:
                x = col * w_block
                y = row * h_block
                lista_tarefas.append((x, y))
        progresso = tk.Toplevel(self.root)
        progresso.title("Salvando...")
        progresso.geometry("300x100")
        lbl_prog = tk.Label(progresso, text="Iniciando...", font=("Arial", 12))
        lbl_prog.pack(pady=20, expand=True)
        self.root.update()
        try:
            for (x, y) in lista_tarefas:
                x2 = min(x + w_block, w_total)
                y2 = min(y + h_block, h_total)
                if x >= w_total or y >= h_total: continue
                tile = self.imagem_original.crop((x, y, x2, y2))
                col_idx = x // w_block
                row_idx = y // h_block
                filename = f"fatia_lin{row_idx:03d}_col{col_idx:03d}.png"
                tile.save(os.path.join(output_dir, filename))
                count += 1
                if count % 5 == 0:
                    lbl_prog.config(text=f"Salvando {count}/{len(lista_tarefas)}...")
                    progresso.update()
            messagebox.showinfo("Sucesso", f"{count} fatias salvas!")
        except Exception as e: messagebox.showerror("Erro", str(e))
        finally: progresso.destroy()

if __name__ == "__main__":
    root = tk.Tk()
    app = AppVisualizadorPro(root)
    root.mainloop()