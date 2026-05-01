#!/bin/bash

# Navega para o diretório do script (caso seja executado de outro lugar)
cd "$(dirname "$0")"

# Ativa o ambiente virtual
source .venv/bin/activate

# Executa o projeto
python3 main.py
