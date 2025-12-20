import tkinter as tk
from tkinter import filedialog, messagebox, colorchooser
from PIL import Image, ImageTk
import os
import json
import platform

Image.MAX_IMAGE_PIXELS = None 

# --- MODELO DE DADOS (SESSÃO) ---
class SessaoImagem:
    def __init__(self, caminho):
        self.caminho = caminho
        self.nome = os.path.basename(caminho)
        
        self.imagem_original = Image.open(caminho)
        self.w_real, self.h_real = self.imagem_original.size
        
        self.imagem_preview = None
        self.preview_scale = 1.0
        self._gerar_cache()
        
        self.zoom_level = 1.0
        self.camera_x = 0
        self.camera_y = 0
        
        self.grid_w = 1000
        self.grid_h = 1000
        self.grid_color = "#FFFF00"
        self.selected_cells = set()

    def _gerar_cache(self):
        try:
            max_size = 2048
            if self.w_real > max_size or self.h_real > max_size:
                ratio = min(max_size / self.w_real, max_size / self.h_real)
                new_w = int(self.w_real * ratio)
                new_h = int(self.h_real * ratio)
                self.imagem_preview = self.imagem_original.resize((new_w, new_h), Image.Resampling.LANCZOS)
                self.preview_scale = self.w_real / new_w
            else:
                self.imagem_preview = self.imagem_original.copy()
                self.preview_scale = 1.0
        except:
            self.imagem_preview = self.imagem_original.copy()
            self.preview_scale = 1.0

# --- APLICAÇÃO PRINCIPAL ---
class AppScientificSlicer:
    def __init__(self, root):
        self.root = root
        self.is_mac = platform.system() == "Darwin" # Detecção do SO
        
        self.root.title(f"Slicer Lab Pro - {'macOS Mode' if self.is_mac else 'Windows Mode'}")
        self.root.geometry("1400x900")
        self.root.configure(bg="#1e1e1e")

        self.sessoes = []
        self.sessao_atual = None
        self.caminho_projeto_atual = None
        self.timer_autosave = None
        
        self.tk_image = None
        self.last_mouse_x = 0
        self.last_mouse_y = 0

        self._setup_ui()

    def _setup_ui(self):
        self.colors = {"bg": "#1e1e1e", "sidebar": "#252526", "toolbar": "#333333", "accent": "#007acc", "text": "#cccccc"}
        
        main = tk.Frame(self.root, bg=self.colors["bg"])
        main.pack(fill=tk.BOTH, expand=True)

        self.sidebar = tk.Frame(main, width=250, bg=self.colors["sidebar"])
        self.sidebar.pack(side=tk.LEFT, fill=tk.Y)
        self.sidebar.pack_propagate(False)
        
        tk.Label(self.sidebar, text="PROJECT / IMAGES", bg=self.colors["sidebar"], fg="#888", font=("Segoe UI", 8, "bold"), anchor="w").pack(fill=tk.X, padx=10, pady=(10,5))
        self.lista_arquivos = tk.Listbox(self.sidebar, bg=self.colors["sidebar"], fg=self.colors["text"], selectbackground="#37373d", selectforeground="white", bd=0, highlightthickness=0, font=("Segoe UI", 10), activestyle="none")
        self.lista_arquivos.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        self.lista_arquivos.bind("<<ListboxSelect>>", self.trocar_aba_imagem)
        
        tk.Button(self.sidebar, text="+ ADD IMAGE", command=self.add_imagem_btn, bg=self.colors["accent"], fg="white", relief="flat", font=("Segoe UI", 9, "bold")).pack(fill=tk.X, padx=10, pady=10)

        # 2. Main Area
        content = tk.Frame(main, bg=self.colors["bg"])
        content.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)

        self.toolbar = tk.Frame(content, bg=self.colors["toolbar"], height=50)
        self.toolbar.pack(fill=tk.X)
        
        self._setup_inputs_grid()
        self._btn_toolbar("🎨 Color", self.escolher_cor)
        tk.Frame(self.toolbar, width=1, bg="#555").pack(side=tk.LEFT, fill=tk.Y, padx=10, pady=5)
        
        # Botões de Projeto
        self.lbl_status_save = tk.Label(self.toolbar, text="", bg=self.colors["toolbar"], fg="#aaa", font=("Segoe UI", 8, "italic"))
        self.lbl_status_save.pack(side=tk.RIGHT, padx=10)
        
        self._btn_toolbar("💾 Save As...", self.salvar_projeto_como)
        self._btn_toolbar("📂 Open Project", self.abrir_projeto)
        self._btn_toolbar("✂️ Slice Selection", self.salvar_selecionados, bg="#27ae60")

        # Canvas
        self.canvas_area = tk.Frame(content, bg="black")
        self.canvas_area.pack(fill=tk.BOTH, expand=True)
        self.canvas = tk.Canvas(self.canvas_area, bg="#111", highlightthickness=0)
        self.canvas.pack(fill=tk.BOTH, expand=True)
        
        self.status_bar = tk.Label(content, text="Ready.", bg=self.colors["accent"], fg="white", anchor="w", font=("Segoe UI", 8))
        self.status_bar.pack(fill=tk.X)

        self._setup_binds()

    def _setup_inputs_grid(self):
        f = tk.Frame(self.toolbar, bg=self.colors["toolbar"])
        f.pack(side=tk.LEFT, padx=10)
        tk.Label(f, text="W:", bg=self.colors["toolbar"], fg="white").pack(side=tk.LEFT)
        self.entry_w = tk.Entry(f, width=5, justify="center", bg="#444", fg="white", relief="flat")
        self.entry_w.insert(0, "1000")
        self.entry_w.pack(side=tk.LEFT, padx=2)
        tk.Label(f, text="H:", bg=self.colors["toolbar"], fg="white").pack(side=tk.LEFT, padx=(5,0))
        self.entry_h = tk.Entry(f, width=5, justify="center", bg="#444", fg="white", relief="flat")
        self.entry_h.insert(0, "1000")
        self.entry_h.pack(side=tk.LEFT, padx=2)
        
        self.entry_w.bind("<KeyRelease>", lambda e: self.trigger_modificacao())
        self.entry_h.bind("<KeyRelease>", lambda e: self.trigger_modificacao())
        self.entry_w.bind("<FocusOut>", lambda e: self.redesenhar())
        self.entry_h.bind("<FocusOut>", lambda e: self.redesenhar())

    def _btn_toolbar(self, txt, cmd, bg="#444"):
        tk.Button(self.toolbar, text=txt, command=cmd, bg=bg, fg="white", relief="flat", padx=10).pack(side=tk.LEFT, padx=5, pady=8)

    def _setup_binds(self):
        c = self.canvas
        c.bind("<ButtonPress-1>", self.on_pan_start)
        c.bind("<B1-Motion>", self.on_pan_move)
        
        c.bind("<Button-3>", self.on_right_click) 
        if self.is_mac:
            c.bind("<Button-2>", self.on_right_click)
            c.bind("<Control-Button-1>", self.on_right_click)
        
        c.bind("<MouseWheel>", self.on_scroll_win)
        c.bind("<Shift-MouseWheel>", self.on_shift_scroll_win)
        c.bind("<Control-MouseWheel>", self.on_zoom_win)
        
        
        c.bind("<Configure>", self.on_resize)
        self.root.bind("<c>", self.limpar_selecao)

    def _get_scroll_delta(self, event):
        """Normaliza a velocidade do scroll entre sistemas"""
        if self.is_mac:
            return event.delta * 10 
        else:
            return (event.delta / 120) * 30

    def trigger_modificacao(self, event=None):
        if not self.caminho_projeto_atual:
            self.lbl_status_save.config(text="* Não salvo")
            return

        self.lbl_status_save.config(text="Modificado...")
        if self.timer_autosave:
            self.root.after_cancel(self.timer_autosave)
        self.timer_autosave = self.root.after(2000, self._executar_autosave)

    def _executar_autosave(self):
        if self.caminho_projeto_atual:
            try:
                self._gravar_arquivo(self.caminho_projeto_atual)
                self.lbl_status_save.config(text="Salvo Automaticamente")
            except Exception as e:
                self.lbl_status_save.config(text="Erro no AutoSave")
                print(f"Erro AutoSave: {e}")

    def _gravar_arquivo(self, caminho):
        if self.sessao_atual:
            try:
                self.sessao_atual.grid_w = int(self.entry_w.get())
                self.sessao_atual.grid_h = int(self.entry_h.get())
            except: pass

        dados_projeto = {
            "versao": "2.1",
            "plataforma_origem": platform.system(),
            "indice_ativo": self.sessoes.index(self.sessao_atual) if self.sessao_atual in self.sessoes else 0,
            "imagens": []
        }

        for sessao in self.sessoes:
            dados_sessao = {
                "caminho": sessao.caminho,
                "grid_w": sessao.grid_w,
                "grid_h": sessao.grid_h,
                "grid_color": sessao.grid_color,
                "zoom_level": sessao.zoom_level,
                "camera_x": sessao.camera_x,
                "camera_y": sessao.camera_y,
                "selecao": list(sessao.selected_cells)
            }
            dados_projeto["imagens"].append(dados_sessao)

        with open(caminho, 'w', encoding='utf-8') as f:
            json.dump(dados_projeto, f, indent=4)

    def salvar_projeto_como(self):
        if not self.sessoes:
            messagebox.showwarning("Warn", "No images to save.")
            return
            
        f = filedialog.asksaveasfilename(defaultextension=".lab", filetypes=[("Projeto Lab", "*.lab")])
        if f:
            self.caminho_projeto_atual = f
            self._gravar_arquivo(f)
            self.root.title(f"Slicer Lab - {os.path.basename(f)}")
            messagebox.showinfo("Success", "Project saved! AutoSave enabled.")

    def abrir_projeto(self):
        f = filedialog.askopenfilename(filetypes=[("Projeto Lab", "*.lab")])
        if not f: return
        
        try:
            with open(f, 'r', encoding='utf-8') as arquivo:
                dados = json.load(arquivo)

            self.sessoes.clear()
            self.lista_arquivos.delete(0, tk.END)
            self.sessao_atual = None
            self.canvas.delete("all")
            
            self.entry_w.delete(0, tk.END)
            self.entry_h.delete(0, tk.END)

            lista_imgs = dados.get("imagens", [])
            if isinstance(dados, list): lista_imgs = dados

            for img_data in lista_imgs:
                path = img_data.get("caminho", img_data.get("path"))
                
                if not os.path.exists(path):
                    nome_arq = os.path.basename(path)
                    pasta_proj = os.path.dirname(f)
                    tentativa = os.path.join(pasta_proj, nome_arq)
                    if os.path.exists(tentativa):
                        path = tentativa
                
                if path and os.path.exists(path):
                    nova_sessao = SessaoImagem(path)
                    
                    nova_sessao.grid_w = img_data.get("grid_w", img_data.get("gw", 1000))
                    nova_sessao.grid_h = img_data.get("grid_h", img_data.get("gh", 1000))
                    nova_sessao.grid_color = img_data.get("grid_color", img_data.get("color", "#FFFF00"))
                    nova_sessao.zoom_level = img_data.get("zoom_level", 1.0)
                    nova_sessao.camera_x = img_data.get("camera_x", 0)
                    nova_sessao.camera_y = img_data.get("camera_y", 0)
                    
                    sel_raw = img_data.get("selecao", img_data.get("sel", []))
                    nova_sessao.selected_cells = set(tuple(x) for x in sel_raw)
                    
                    self.sessoes.append(nova_sessao)
                    self.lista_arquivos.insert(tk.END, f" {nova_sessao.nome}")

            idx_ativo = dados.get("indice_ativo", 0)
            
            if not self.sessoes:
                messagebox.showwarning("Warning", "Images not found. If you moved the project to another PC, place the images in the same folder as the .lab file.")
                return

            if idx_ativo >= len(self.sessoes): idx_ativo = 0
                
            self.lista_arquivos.selection_clear(0, tk.END)
            self.lista_arquivos.selection_set(idx_ativo)
            self._ativar_sessao(self.sessoes[idx_ativo])
            
            self.caminho_projeto_atual = f
            self.root.title(f"Slicer Lab - {os.path.basename(f)}")
            self.lbl_status_save.config(text="Project Loaded")
            
        except Exception as e:
            messagebox.showerror("Error", f"Error opening: {e}")
            print(e)

    def add_imagem_btn(self):
        path = filedialog.askopenfilename(filetypes=[("Imagens", "*.jpg;*.png;*.tif;*.tiff;*.bmp")])
        if path:
            self._adicionar_sessao_logica(path)
            self.trigger_modificacao()

    def _adicionar_sessao_logica(self, path):
        if self.sessao_atual:
            try:
                self.sessao_atual.grid_w = int(self.entry_w.get())
                self.sessao_atual.grid_h = int(self.entry_h.get())
            except: pass

        try:
            nova = SessaoImagem(path)
            self.sessoes.append(nova)
            self.lista_arquivos.insert(tk.END, f" {nova.nome}")
            self.lista_arquivos.selection_clear(0, tk.END)
            self.lista_arquivos.selection_set(tk.END)
            self._ativar_sessao(nova)
        except Exception as e:
            messagebox.showerror("Erro", str(e))

    def trocar_aba_imagem(self, event):
        sel = self.lista_arquivos.curselection()
        if not sel: return
        idx = sel[0]
        if 0 <= idx < len(self.sessoes):
            if self.sessao_atual:
                try:
                    self.sessao_atual.grid_w = int(self.entry_w.get())
                    self.sessao_atual.grid_h = int(self.entry_h.get())
                except: pass
            
            self._ativar_sessao(self.sessoes[idx])

    def _ativar_sessao(self, sessao):
        self.sessao_atual = sessao
        
        self.entry_w.delete(0, tk.END)
        self.entry_w.insert(0, str(sessao.grid_w))
        self.entry_h.delete(0, tk.END)
        self.entry_h.insert(0, str(sessao.grid_h))
        
        if sessao.zoom_level == 1.0 and sessao.camera_x == 0:
            w_can = self.canvas.winfo_width()
            if w_can > 10:
                ratio = min(w_can/sessao.w_real, self.canvas.winfo_height()/sessao.h_real)
                sessao.zoom_level = ratio * 0.9

        self.status_bar.config(text=f"Imagem: {sessao.nome} | Dim: {sessao.w_real}x{sessao.h_real}")
        self.redesenhar()

    def on_resize(self, event):
        if self.sessao_atual: self.redesenhar()

    def redesenhar(self):
        s = self.sessao_atual
        if not s: return

        try:
            s.grid_w = max(10, int(self.entry_w.get()))
            s.grid_h = max(10, int(self.entry_h.get()))
        except: pass

        w_can = self.canvas.winfo_width()
        h_can = self.canvas.winfo_height()
        
        l = s.camera_x
        t = s.camera_y
        r = l + (w_can / s.zoom_level)
        b = t + (h_can / s.zoom_level)

        self.canvas.delete("all")

        use_preview = (s.zoom_level < 0.5 and s.preview_scale > 1.0)
        
        try:
            if use_preview:
                pl = int(l / s.preview_scale)
                pt = int(t / s.preview_scale)
                pr = int(r / s.preview_scale)
                pb = int(b / s.preview_scale)
                img = s.imagem_preview.crop((pl, pt, pr, pb))
                img = img.resize((w_can, h_can), Image.Resampling.NEAREST)
            else:
                cl = max(0, int(l))
                ct = max(0, int(t))
                cr = min(s.w_real, int(r))
                cb = min(s.h_real, int(b))
                if cr > cl and cb > ct:
                    crop = s.imagem_original.crop((cl, ct, cr, cb))
                    img = Image.new("RGB", (w_can, h_can), (20,20,20))
                    px = int((cl - l) * s.zoom_level)
                    py = int((ct - t) * s.zoom_level)
                    pw = int((cr - cl) * s.zoom_level)
                    ph = int((cb - ct) * s.zoom_level)
                    if pw>0 and ph>0:
                        crop = crop.resize((pw, ph), Image.Resampling.NEAREST)
                        img.paste(crop, (px, py))
                else: img = Image.new("RGB", (w_can, h_can), (20,20,20))

            self.tk_image = ImageTk.PhotoImage(img)
            self.canvas.create_image(0, 0, image=self.tk_image, anchor="nw")
            
            if (r-l)/s.grid_w < 400: 
                sc, ec = int(l//s.grid_w), int(r//s.grid_w)+1
                sr, er = int(t//s.grid_h), int(b//s.grid_h)+1
                
                for (c, ro) in s.selected_cells:
                    if sc <= c <= ec and sr <= ro <= er:
                        x1 = (c*s.grid_w - l)*s.zoom_level
                        y1 = (ro*s.grid_h - t)*s.zoom_level
                        x2 = x1 + (s.grid_w*s.zoom_level)
                        y2 = y1 + (s.grid_h*s.zoom_level)
                        
                        if self.is_mac:
                            self.canvas.create_rectangle(x1, y1, x2, y2, outline="cyan", width=2)
                        else:
                            self.canvas.create_rectangle(x1, y1, x2, y2, fill="cyan", outline=s.grid_color, stipple="gray25")
                
                cx = (sc * s.grid_w)
                if cx < l: cx += s.grid_w
                while cx < r:
                    sx = (cx - l) * s.zoom_level
                    self.canvas.create_line(sx, 0, sx, h_can, fill=s.grid_color, dash=(2, 4))
                    cx += s.grid_w
                cy = (sr * s.grid_h)
                if cy < t: cy += s.grid_h
                while cy < b:
                    sy = (cy - t) * s.zoom_level
                    self.canvas.create_line(0, sy, w_can, sy, fill=s.grid_color, dash=(2, 4))
                    cy += s.grid_h

        except Exception as e: pass

    def on_pan_start(self, e):
        self.last_mouse_x = e.x
        self.last_mouse_y = e.y
        
    def on_pan_move(self, e):
        if self.sessao_atual:
            dx = e.x - self.last_mouse_x
            dy = e.y - self.last_mouse_y
            self.sessao_atual.camera_x -= dx / self.sessao_atual.zoom_level
            self.sessao_atual.camera_y -= dy / self.sessao_atual.zoom_level
            self.last_mouse_x = e.x
            self.last_mouse_y = e.y
            self.redesenhar()

    def on_right_click(self, e):
        s = self.sessao_atual
        if not s: return
        rx = s.camera_x + (e.x / s.zoom_level)
        ry = s.camera_y + (e.y / s.zoom_level)
        if 0 <= rx <= s.w_real and 0 <= ry <= s.h_real:
            col = int(rx // s.grid_w)
            row = int(ry // s.grid_h)
            k = (col, row)
            if k in s.selected_cells: s.selected_cells.remove(k)
            else: s.selected_cells.add(k)
            self.redesenhar()
            self.trigger_modificacao()

    def aplicar_zoom(self, f, mx, my):
        s = self.sessao_atual
        if not s: return
        nz = s.zoom_level * f
        if nz < 0.001: return
        wx = s.camera_x + (mx / s.zoom_level)
        wy = s.camera_y + (my / s.zoom_level)
        s.zoom_level = nz
        s.camera_x = wx - (mx / nz)
        s.camera_y = wy - (my / nz)
        self.redesenhar()

    def on_scroll_win(self, e): 
        if self.sessao_atual: 
            # Correção de velocidade
            delta = self._get_scroll_delta(e)
            self.sessao_atual.camera_y -= delta / self.sessao_atual.zoom_level
            self.redesenhar()
            
    def on_shift_scroll_win(self, e):
        if self.sessao_atual: 
            delta = self._get_scroll_delta(e)
            self.sessao_atual.camera_x -= delta / self.sessao_atual.zoom_level
            self.redesenhar()
            
    def on_zoom_win(self, e):
        fator = 1.2 if e.delta > 0 else 0.8
        self.aplicar_zoom(fator, e.x, e.y)

    def escolher_cor(self):
        if self.sessao_atual:
            c = colorchooser.askcolor()[1]
            if c: 
                self.sessao_atual.grid_color = c
                self.redesenhar()
                self.trigger_modificacao()

    def limpar_selecao(self, e=None):
        if self.sessao_atual:
            self.sessao_atual.selected_cells.clear()
            self.redesenhar()
            self.trigger_modificacao()

    def salvar_selecionados(self):
        s = self.sessao_atual
        if not s or not s.selected_cells: return
        
        msg = f"Salvar {len(s.selected_cells)} fatias?"
        if not messagebox.askyesno("Confirmar", msg): return
        
        out = filedialog.askdirectory()
        if out:
            count = 0
            for (c, r) in s.selected_cells:
                x1 = c * s.grid_w
                y1 = r * s.grid_h
                x2 = min(x1 + s.grid_w, s.w_real)
                y2 = min(y1 + s.grid_h, s.h_real)
                
                nome_arquivo = f"{s.nome}_L{r}_C{c}.png"
                caminho_final = os.path.join(out, nome_arquivo)
                
                s.imagem_original.crop((x1, y1, x2, y2)).save(caminho_final)
                count += 1
            messagebox.showinfo("End", f"{count} slices saved.")

if __name__ == "__main__":
    root = tk.Tk()
    app = AppScientificSlicer(root)
    root.mainloop()