"""
historial.py — Guarda y carga el historial de conciliaciones
Estructura de carpetas:
  output/
  ├── historial.csv               ← índice global de todas las ejecuciones
  ├── Payvalida/
  │   ├── 2026-06-01/
  │   │   ├── conciliados.csv
  │   │   ├── solo_banco.csv
  │   │   ├── solo_sf.csv
  │   │   └── diferencias_monto.csv
  │   └── 2026-06-02/
  ├── Bancolombia/
  │   └── 2026-06-01/
  └── ...
"""
import os
import pandas as pd
from datetime import datetime

OUTPUT_DIR    = os.path.join(os.path.dirname(__file__), "output")
HISTORIAL_PATH = os.path.join(OUTPUT_DIR, "historial.csv")


def guardar_conciliacion(resultado: dict, fecha_override: str = None):
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    metricas   = resultado["metricas"]
    proveedor  = metricas["proveedor"]
    fecha_eje  = datetime.now()
    fecha_dia  = fecha_override if fecha_override else fecha_eje.strftime("%Y-%m-%d")
    hora_str   = fecha_eje.strftime("%H:%M:%S")

    # ── Carpeta por proveedor y fecha
    carpeta = os.path.join(OUTPUT_DIR, proveedor, fecha_dia)
    os.makedirs(carpeta, exist_ok=True)

    # ── Guardar archivos de detalle
    for nombre, df in {
        "conciliados":        resultado["conciliados"],
        "solo_banco":         resultado["solo_banco"],
        "solo_sf":            resultado["solo_sf"],
        "diferencias_monto":  resultado["dif_monto"],
    }.items():
        cols = [c for c in df.columns if not c.startswith("_")]
        df[cols].to_csv(os.path.join(carpeta, f"{nombre}.csv"), index=False, encoding="utf-8-sig")

    # ── Guardar fila en historial.csv global
    fila = {
        "fecha":                fecha_dia,
        "hora":                 hora_str,
        "proveedor":            proveedor,
        "registros_banco":      metricas["total_registros_banco"],
        "registros_sf":         metricas["total_registros_sf"],
        "diferencia_registros": metricas["diferencia_registros"],
        "monto_banco":          metricas["monto_total_banco"],
        "monto_sf":             metricas["monto_total_sf"],
        "diferencia_montos":    metricas["diferencia_montos"],
        "conciliados":          metricas["conciliados"],
        "solo_banco":           metricas["solo_banco"],
        "solo_sf":              metricas["solo_sf"],
        "dif_monto":            metricas["dif_monto"],
        "tolerancia":           metricas["tolerancia_usada"],
        "carpeta_detalle":      os.path.join(proveedor, fecha_dia),
    }

    df_nueva = pd.DataFrame([fila])
    if os.path.exists(HISTORIAL_PATH):
        df_hist = pd.read_csv(HISTORIAL_PATH)
        df_hist = pd.concat([df_hist, df_nueva], ignore_index=True)
    else:
        df_hist = df_nueva
    df_hist.to_csv(HISTORIAL_PATH, index=False)

    return fila


def cargar_historial() -> pd.DataFrame:
    if not os.path.exists(HISTORIAL_PATH):
        return pd.DataFrame()
    df = pd.read_csv(HISTORIAL_PATH)
    df["fecha"] = pd.to_datetime(df["fecha"])
    return df.sort_values("fecha", ascending=False).reset_index(drop=True)


def cargar_detalle(carpeta_detalle: str, tipo: str) -> pd.DataFrame:
    path = os.path.join(OUTPUT_DIR, carpeta_detalle, f"{tipo}.csv")
    if os.path.exists(path):
        return pd.read_csv(path)
    return pd.DataFrame()
