# 🔬 Slicer Lab Pro

**Slicer Lab Pro** é uma ferramenta desktop de alta performance desenvolvida em **Python (Tkinter + Pillow)** para **visualização, anotação e fatiamento (slicing) de imagens de alta resolução**.

Ideal para **datasets de Machine Learning**, **imagens científicas**, **mapas** ou qualquer projeto que exija dividir grandes imagens em **tiles (blocos)** específicos.

---

## ✨ Funcionalidades Principais

### 🚀 Performance e Visualização
- **Suporte a Imagens Gigantes**  
  Carregamento otimizado de imagens de alta resolução (satélite, microscopia, etc.) sem travar a interface.

- **Sistema LOD (Level of Detail)**  
  Implementação de cache visual que renderiza previews em baixa resolução durante o zoom-out para manter a navegação fluida.

- **Navegação Intuitiva**  
  Zoom e Pan similares a softwares de CAD ou mapas (ex: Google Maps).

---

### 🛠️ Edição e Fatiamento
- **Grid Dinâmico**  
  Ajuste a largura e altura (W x H) da grade de corte em tempo real.

- **Seleção de Células**  
  Clique com o botão direito para selecionar/deselecionar áreas específicas para exportação.

- **Cores Personalizáveis**  
  Altere a cor da grade para melhor contraste com a imagem de fundo.

---

### 💾 Gerenciamento de Projetos
- **Múltiplas Sessões**  
  Trabalhe com várias imagens simultaneamente em abas laterais.

- **Persistência de Dados (JSON)**  
  Salve e carregue projetos inteiros (`.lab`).  
  O sistema preserva:
  - Grid  
  - Zoom  
  - Posição da câmera  
  - Seleções de cada imagem individualmente

- **Auto-Save Inteligente**  
  O projeto salva automaticamente após alterações, prevenindo perda de dados.

- **Exportação em Lote**  
  Exporte apenas os "quadrados" selecionados como arquivos de imagem individuais (`.png`, `.jpg`, etc.).

---

## 🎮 Atalhos e Controles

| Ação | Comando / Mouse |
|-----|----------------|
| Mover Câmera (Pan) | Clique e arraste com Botão Esquerdo |
| Zoom In / Out | `Ctrl + Scroll do Mouse` |
| Pan Vertical | `Scroll do Mouse` |
| Pan Horizontal | `Shift + Scroll do Mouse` |
| Selecionar Célula | Clique com Botão Direito |
| Limpar Seleção | Tecla `C` |
| Confirmar Dimensões | `Enter` ou clique fora dos campos W/H |

---

## 📦 Instalação e Execução

### Pré-requisitos
- Python **3.8** ou superior  
- Biblioteca **Pillow**

### Passo a Passo

Clone o repositório:
```bash
   git clone https://seu-repositorio/slicer-lab-pro.git
   cd slicer-lab-pro
```


Instale as dependências:
```bash
   pip install Pillow
```

Execute a aplicação:
```bash
   python main.py
```

## ⚙️ Detalhes Técnicos

### Arquitetura

O projeto segue uma separação clara entre Lógica de Dados e Interface Gráfica, evitando bugs de estado:

- Backend (SessaoImagem)
Classe responsável por manter o estado "puro" de cada imagem:

   - Dimensões reais

   - Caminhos

   - Configurações de grid

   - Lista de células selecionadas

Os dados permanecem na RAM, independentes da renderização.

- Frontend (AppScientificSlicer)
Interface Tkinter que lê os dados da sessão ativa e desenha no Canvas.

## Otimização de Imagem

Para lidar com o erro DecompressionBombError em imagens grandes:

```bash
   Image.MAX_IMAGE_PIXELS = None
```


### Utiliza Crop & Resize dinâmico:

- Apenas a porção visível da imagem (Viewport) é processada

- Redução significativa de uso de memória e CPU