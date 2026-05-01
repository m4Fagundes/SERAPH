# Estrutura do Projeto - Grid Image Analyzer

## 📦 Raiz (Limpa e Minimalista)

Apenas arquivos essenciais para rodar a aplicação:

- **main.py** - Ponto de entrada da aplicação
- **requirements.txt** - Dependências Python
- **pyproject.toml** - Configuração do projeto
- **config_template.json** - Template de configuração
- **README.md** - Documentação principal
- **AGENTS.md** - Instruções GitNexus para o projeto
- **CLAUDE.md** - Instruções do Claude/Copilot

---

## 📁 Estrutura de Diretórios

### `/app/` - Código-fonte principal
- `application/` - Serviços de aplicação
- `domain/` - Lógica de domínio e modelos
- `infrastructure/` - Acesso a dados, APIs, config
- `interface/` - Interface gráfica (Tkinter)
- `tools/` - Utilitários

### `/docs/` - Documentação completa
- `build/` - Especificações de build (PyInstaller)
  - `main.spec`, `main_release.spec`
  - `installer.iss` (inno Setup)
- `macos/` - Instruções específicas para macOS
  - `SETUP_MACOS.md`
  - `INSTRUCTIONS_MACOS_BUILD.py`
  - `MACOS_BUILD_SUMMARY.md`
- `optimization/` - Guias de otimização
  - `GPU_OPTIMIZATION.py`
- `BUILD_MACOS.md`, `CELLPOSE_EXPLORATION_REPORT.md`

### `/scripts/` - Scripts auxiliares e utilidades
- `run.sh` - Script de execução (shell)
- `segment_image_cellpose.py` - Utilitário de segmentação

### `/tests/` - Testes automatizados
- `application/` - Testes de serviços
- `domain/` - Testes de lógica
- `infrastructure/` - Testes de I/O
- `test_tile_analysis_script.py`

### `/build/`, `/build_installer/`, `/dist/`
- Saída de builds (ignorar no git)

### `/portable/`, `/hooks/`, `/skills/`
- Configuração de builds portáteis
- Hooks para PyInstaller
- Skills customizadas do Claude

---

## 🗑️ Limpeza Realizada

### ✅ Deletados (Testes/Diagnóstico obsoletos)
- `debug_dialog.py`
- `debug_nuclick.py`
- `diagnose_cellpose_image.py`
- `diagnose_gpu.py`
- `monitor_gpu.py`
- `test_cellpose_simple.py`
- `test_hardware_simple.py`
- `test_model_bundled.py`
- `test_model_download.py`
- `upload_nuclick.py`
- `fix_export.py`

### ✅ Movidos
- **Build/Setup** → `docs/build/` e `docs/macos/`
- **Otimização** → `docs/optimization/`
- **Scripts auxiliares** → `scripts/`

---

## 🚀 Como Usar

```bash
# Instalar dependências
pip install -r requirements.txt

# Rodar aplicação
python main.py

# Build (macOS)
python docs/macos/INSTRUCTIONS_MACOS_BUILD.py

# Build (Windows/Linux)
pyinstaller docs/build/main.spec
```

---

**Data:** 2026-05-01  
**Limpeza realizada com GitNexus impact analysis**
