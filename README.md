# Visual Slicer (Ferramenta de Análise de Imagens)

Ferramenta desenvolvida em Python para visualização e fatiamento de imagens de alta resolução (Gigapixel images), focada em superar limitações de memória RAM em computadores convencionais durante o processamento de dados científicos.

Este projeto faz parte da pesquisa de doutorado do [Seu Laboratório/Universidade].

## 🚀 Funcionalidades

- **Carregamento Otimizado:** Visualização de imagens gigantes (ex: satélite, microscopia) sem travar a interface.
- **Grid Dinâmico:** Visualização prévia das linhas de corte (1000x1000px ou personalizado).
- **Fatiamento Preciso:** Gera tiles (fatias) mantendo a resolução original usando a biblioteca `image-slicer`.
- **Interface Visual:** GUI construída com `tkinter` para facilitar o uso por pesquisadores sem conhecimento de código.

## 📋 Pré-requisitos

O projeto requer **Python 3.8+**. As dependências principais são:

- `tkinter` (Geralmente nativo no Python)
- `Pillow` (Processamento de imagem)
- `image-slicer` (Lógica de corte)

## 🔧 Instalação

1. Clone o repositório:
   ```bash
   git clone [https://github.com/m4Fagundes/grid-image-analyzer.git](https://github.com/m4Fagundes/grid-image-analyzer.git)
   cd seu-projeto

2. Instale as dependências:
   ```bash
   pip install image-slicer Pillow


3. Execute o script principal:
   ```bash
   python main.py
