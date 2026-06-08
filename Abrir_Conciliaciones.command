#!/bin/bash
# Ir a la carpeta donde está este archivo
cd "$(dirname "$0")"

# Abrir la app en el navegador
python3 -m streamlit run app.py
