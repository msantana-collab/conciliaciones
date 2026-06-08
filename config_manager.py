"""
config_manager.py — Gestión de proveedores desde archivo JSON
Permite agregar/editar/eliminar proveedores sin tocar motor.py
"""
import json
import os

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "proveedores.json")

# Configuración base de Payvalida (se usa si no existe el JSON)
DEFAULT_CONFIG = {
    "Payvalida": {
        "col_id":     "PO",
        "col_monto":  " Valor Total",
        "col_fecha":  "Fecha Creación",
        "col_estado": "Estado",
        "encoding":   "utf-8-sig",
        "separator":  ","
    }
}


def cargar_proveedores() -> dict:
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return DEFAULT_CONFIG.copy()


def guardar_proveedores(proveedores: dict):
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(proveedores, f, ensure_ascii=False, indent=2)


def agregar_proveedor(nombre: str, config: dict):
    proveedores = cargar_proveedores()
    proveedores[nombre] = config
    guardar_proveedores(proveedores)


def eliminar_proveedor(nombre: str):
    proveedores = cargar_proveedores()
    if nombre in proveedores:
        del proveedores[nombre]
        guardar_proveedores(proveedores)
