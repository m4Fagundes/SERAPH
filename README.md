# Grid Image Analyzer (Scientific Slicer)

Ferramenta de alta performance desenvolvida em Python para visualização, navegação e fatiamento de imagens de ultra-resolução (Gigapixel/Heavy Data). 

Este projeto foi desenhado para superar as limitações de memória RAM (MemoryErrors) e travas de segurança (`DecompressionBombWarning`) comuns ao processar imagens de alta resolução

> **Contexto:** Projeto de apoio à pesquisa de doutorado.

## 🚀 Funcionalidades Avançadas

- **Navegação "Deep Zoom":** Interface estilo *Google Earth* ou *Canva*. Permite arrastar (Pan) e aproximar (Zoom) livremente pela imagem.
- **Arquitetura LOD (Level of Detail):** Sistema híbrido inteligente que alterna automaticamente entre um cache leve (para visão geral) e os dados RAW (para detalhes), garantindo 60 FPS mesmo em imagens de 1GB+.
- **Renderização por Viewport:** Apenas os pixels visíveis na tela são processados e renderizados, mantendo o consumo de RAM baixo independente do tamanho da imagem original.
- **Grid Dinâmico Otimizado:** As linhas de corte são calculadas matematicamente e só são desenhadas se visíveis, evitando poluição visual em escalas pequenas.


## 📋 Pré-requisitos

- **Python 3.9+**
- Bibliotecas: `tkinter` (interface), `Pillow` (motor gráfico).

## 🔧 Instalação

1. Clone o repositório:
   ```bash
   git clone [https://github.com/m4Fagundes/grid-image-analyzer.git](https://github.com/m4Fagundes/grid-image-analyzer.git)
   cd grid-image-analyzer

2. Instale as dependências:
   ```bash
   pip install image-slicer Pillow


3. Execute o script principal:
   ```bash
   python main.py
