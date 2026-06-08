"""
gsheets.py — Sincronización del historial con Google Sheets
Escribe cada conciliación ejecutada en la hoja "Historial Conciliaciones"
"""
import os
import json
import gspread
from google.oauth2.service_account import Credentials

SHEET_ID = "1_mwuovkNagUR2R5e_XmUjTt7fgLLDAsJlU2g8g6tNlI"

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

COLUMNAS = [
    "fecha", "hora", "proveedor",
    "registros_banco", "registros_sf", "diferencia_registros",
    "monto_banco", "monto_sf", "diferencia_montos",
    "conciliados", "solo_banco", "solo_sf", "dif_monto",
    "tolerancia"
]


def _get_client(json_path: str):
    creds = Credentials.from_service_account_file(json_path, scopes=SCOPES)
    return gspread.authorize(creds)


def _find_json(carpeta: str) -> str:
    """Busca el archivo .json de credenciales en la carpeta del proyecto."""
    for f in os.listdir(carpeta):
        if f.endswith(".json") and f != "proveedores.json":
            return os.path.join(carpeta, f)
    raise FileNotFoundError("No se encontró el archivo JSON de credenciales en la carpeta.")


def sincronizar_fila(fila: dict):
    """
    Agrega una fila al Google Sheet.
    Si la hoja no tiene encabezados todavía, los crea primero.
    """
    try:
        carpeta = os.path.dirname(__file__)
        json_path = _find_json(carpeta)
        client = _get_client(json_path)
        sheet = client.open_by_key(SHEET_ID).sheet1

        # Crear encabezados si la hoja está vacía
        if sheet.row_count == 0 or sheet.cell(1, 1).value is None:
            sheet.append_row(COLUMNAS)

        # Agregar fila con los datos
        nueva_fila = [str(fila.get(col, "")) for col in COLUMNAS]
        sheet.append_row(nueva_fila)
        return True, None

    except Exception as e:
        return False, str(e)


def inicializar_hoja():
    """
    Verifica la conexión y crea los encabezados si la hoja está vacía.
    Retorna (True, email_bot) si OK, (False, error) si falla.
    """
    try:
        carpeta = os.path.dirname(__file__)
        json_path = _find_json(carpeta)
        client = _get_client(json_path)
        sheet = client.open_by_key(SHEET_ID).sheet1

        if sheet.row_count == 0 or sheet.cell(1, 1).value is None:
            sheet.append_row(COLUMNAS)

        # Leer email del bot desde el JSON
        with open(json_path) as f:
            email = json.load(f).get("client_email", "")

        return True, email

    except Exception as e:
        return False, str(e)
