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


def _get_client():
    """
    Intenta conectarse usando Streamlit Secrets (Streamlit Cloud).
    Si no están disponibles, busca el archivo JSON local (Mac local).
    """
    try:
        import streamlit as st
        creds_dict = dict(st.secrets["gcp_service_account"])
        creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
        return gspread.authorize(creds)
    except Exception:
        # Fallback: archivo JSON local
        carpeta = os.path.dirname(__file__)
        for f in os.listdir(carpeta):
            if f.endswith(".json") and f != "proveedores.json":
                json_path = os.path.join(carpeta, f)
                creds = Credentials.from_service_account_file(json_path, scopes=SCOPES)
                return gspread.authorize(creds)
        raise FileNotFoundError("No se encontraron credenciales de Google.")


def sincronizar_fila(fila: dict):
    try:
        client = _get_client()
        sheet = client.open_by_key(SHEET_ID).sheet1
        if sheet.row_count == 0 or sheet.cell(1, 1).value is None:
            sheet.append_row(COLUMNAS)
        nueva_fila = [str(fila.get(col, "")) for col in COLUMNAS]
        sheet.append_row(nueva_fila)
        return True, None
    except Exception as e:
        return False, str(e)


def inicializar_hoja():
    try:
        client = _get_client()
        sheet = client.open_by_key(SHEET_ID).sheet1
        if sheet.row_count == 0 or sheet.cell(1, 1).value is None:
            sheet.append_row(COLUMNAS)
        # Intentar obtener email
        try:
            import streamlit as st
            email = st.secrets["gcp_service_account"].get("client_email", "")
        except Exception:
            email = "conciliaciones-bot@numeric-mile-498819-f7.iam.gserviceaccount.com"
        return True, email
    except Exception as e:
        return False, str(e)
