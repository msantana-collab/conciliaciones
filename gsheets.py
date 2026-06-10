"""
gsheets.py — Sincronización del historial con Google Sheets
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
    "tolerancia", "nota"
]


def _get_client():
    try:
        import streamlit as st
        creds_dict = dict(st.secrets["gcp_service_account"])
        creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
        return gspread.authorize(creds)
    except Exception:
        carpeta = os.path.dirname(__file__)
        for f in os.listdir(carpeta):
            if f.endswith(".json") and f != "proveedores.json":
                json_path = os.path.join(carpeta, f)
                creds = Credentials.from_service_account_file(json_path, scopes=SCOPES)
                return gspread.authorize(creds)
        raise FileNotFoundError("No se encontraron credenciales de Google.")


def _find_row(sheet, fecha: str, proveedor: str) -> int:
    """Busca la fila que coincide con fecha y proveedor. Retorna número de fila (1-based) o -1."""
    try:
        registros = sheet.get_all_values()
        for i, row in enumerate(registros[1:], start=2):  # saltar encabezado
            if len(row) >= 3 and row[0] == fecha and row[2] == proveedor:
                return i
        return -1
    except Exception:
        return -1


def sincronizar_fila(fila: dict):
    try:
        client = _get_client()
        sheet = client.open_by_key(SHEET_ID).sheet1
        # Crear encabezados si la hoja está vacía
        if not sheet.get_all_values():
            sheet.append_row(COLUMNAS)
        nueva_fila = [str(fila.get(col, "")) for col in COLUMNAS]
        sheet.append_row(nueva_fila)
        return True, None
    except Exception as e:
        return False, str(e)


def actualizar_nota(fecha: str, proveedor: str, nota: str):
    """Actualiza la columna 'nota' de la fila correspondiente en el Sheet."""
    try:
        client = _get_client()
        sheet = client.open_by_key(SHEET_ID).sheet1
        fila_num = _find_row(sheet, fecha, proveedor)
        if fila_num == -1:
            return False, "No se encontró la fila en el Sheet."
        col_nota = COLUMNAS.index("nota") + 1  # gspread usa índice 1-based
        sheet.update_cell(fila_num, col_nota, nota)
        return True, None
    except Exception as e:
        return False, str(e)


def inicializar_hoja():
    try:
        client = _get_client()
        sheet = client.open_by_key(SHEET_ID).sheet1
        if not sheet.get_all_values():
            sheet.append_row(COLUMNAS)
        try:
            import streamlit as st
            email = st.secrets["gcp_service_account"].get("client_email", "")
        except Exception:
            email = "conciliaciones-bot@numeric-mile-498819-f7.iam.gserviceaccount.com"
        return True, email
    except Exception as e:
        return False, str(e)
