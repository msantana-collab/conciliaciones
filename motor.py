import pandas as pd
import numpy as np
import re
from datetime import datetime


# ─────────────────────────────────────────────
#  CONFIGURACIÓN POR PROVEEDOR
#  Agregar nuevos proveedores aquí sin tocar el resto del código
# ─────────────────────────────────────────────
PROVEEDORES = {
    "Payvalida": {
        "col_id":     "PO",               # columna clave en archivo del banco/proveedor
        "col_monto":  " Valor Total",      # columna de monto en archivo del banco/proveedor
        "col_fecha":  "Fecha Creación",
        "col_estado": "Estado",
        "encoding":   "utf-8-sig",
        "separator":  ",",
    },
    # Plantilla para agregar nuevo proveedor:
    # "NombreProveedor": {
    #     "col_id":     "columna_id",
    #     "col_monto":  "columna_monto",
    #     "col_fecha":  "columna_fecha",
    #     "col_estado": "columna_estado",
    #     "encoding":   "utf-8-sig",
    #     "separator":  ",",
    # },
}

SALESFORCE_CONFIG = {
    "col_id":     "Id Unico de Pago",
    "col_monto":  "Monto",
    "col_remesa": "Remesa",
    "col_orden":  "Orden de Pago",
    "col_estado": "Estado de la Remesa",
    "col_fecha":  "Fecha de creación",
    "col_proveedor": "Nombre del proveedor",
    "encoding":   "utf-8-sig",
    "separator":  ",",
}


# ─────────────────────────────────────────────
#  UTILIDADES
# ─────────────────────────────────────────────
def limpiar_monto(valor) -> float:
    """Convierte cualquier formato de monto a float. Ej: '$ 19.842,00' → 19842.0"""
    if pd.isna(valor):
        return np.nan
    s = str(valor).strip()
    s = re.sub(r'[^\d,.\-]', '', s)  # quita $, espacios, etc.
    # Detectar formato colombiano: punto=miles, coma=decimal
    if ',' in s and '.' in s:
        s = s.replace('.', '').replace(',', '.')
    elif ',' in s and '.' not in s:
        s = s.replace(',', '.')
    try:
        return float(s)
    except ValueError:
        return np.nan


def cargar_banco(ruta: str, proveedor: str) -> pd.DataFrame:
    cfg = PROVEEDORES[proveedor]
    df = pd.read_csv(
        ruta,
        encoding=cfg["encoding"],
        sep=cfg["separator"],
        dtype=str
    )
    df.columns = df.columns.str.strip()
    col_id     = cfg["col_id"].strip()
    col_monto  = cfg["col_monto"].strip()

    df[col_id]    = df[col_id].str.strip().str.upper()
    df["_monto_banco"] = df[col_monto].apply(limpiar_monto)
    df["_proveedor"]   = proveedor
    df["_source"]      = "banco"
    return df


def cargar_salesforce(ruta: str) -> pd.DataFrame:
    cfg = SALESFORCE_CONFIG
    df = pd.read_csv(
        ruta,
        encoding=cfg["encoding"],
        sep=cfg["separator"],
        dtype=str
    )
    df.columns = df.columns.str.strip()
    col_id    = cfg["col_id"].strip()
    col_monto = cfg["col_monto"].strip()

    df[col_id]   = df[col_id].str.strip().str.upper()
    df["_monto_sf"] = df[col_monto].apply(limpiar_monto)
    df["_source"]   = "salesforce"
    return df


# ─────────────────────────────────────────────
#  MOTOR DE CONCILIACIÓN
# ─────────────────────────────────────────────
def conciliar(df_banco: pd.DataFrame, df_sf: pd.DataFrame,
              proveedor: str, tolerancia: float = 1.0) -> dict:
    """
    Cruza banco vs Salesforce por ID único.
    tolerancia: diferencia de centavos aceptable (default $1)
    Retorna dict con DataFrames de resultados y métricas resumen.
    """
    cfg_banco = PROVEEDORES[proveedor]
    cfg_sf    = SALESFORCE_CONFIG

    col_id_banco = cfg_banco["col_id"].strip()
    col_id_sf    = cfg_sf["col_id"].strip()

    banco_ids = set(df_banco[col_id_banco].dropna())
    sf_ids    = set(df_sf[col_id_sf].dropna())

    # ── 1. Solo en banco (no están en SF)
    solo_banco_ids = banco_ids - sf_ids
    df_solo_banco  = df_banco[df_banco[col_id_banco].isin(solo_banco_ids)].copy()

    # ── 2. Solo en SF (no están en banco)
    solo_sf_ids = sf_ids - banco_ids
    df_solo_sf  = df_sf[df_sf[col_id_sf].isin(solo_sf_ids)].copy()

    # ── 3. En ambos → cruce para diferencias de monto
    comunes_ids = banco_ids & sf_ids
    df_banco_match = df_banco[df_banco[col_id_banco].isin(comunes_ids)].copy()
    df_sf_match    = df_sf[df_sf[col_id_sf].isin(comunes_ids)].copy()

    df_cruce = df_banco_match[[col_id_banco, "_monto_banco"]].merge(
        df_sf_match[[col_id_sf, "_monto_sf", cfg_sf["col_remesa"], cfg_sf["col_orden"]]],
        left_on=col_id_banco,
        right_on=col_id_sf,
        how="inner"
    )
    df_cruce["_diferencia"] = (df_cruce["_monto_banco"] - df_cruce["_monto_sf"]).abs()
    df_cruce["_tipo"] = np.where(
        df_cruce["_diferencia"] <= tolerancia, "Conciliado", "Diferencia de monto"
    )

    df_conciliados    = df_cruce[df_cruce["_tipo"] == "Conciliado"].copy()
    df_dif_monto      = df_cruce[df_cruce["_tipo"] == "Diferencia de monto"].copy()

    # ── Diferencias de centavos (monto banco sin decimales vs SF)
    df_cruce["_monto_banco_sin_dec"] = df_cruce["_monto_banco"].apply(lambda x: round(x) if pd.notna(x) else x)
    df_cruce["_dif_centavos"]        = (df_cruce["_monto_banco_sin_dec"] - df_cruce["_monto_sf"]).abs()

    # ── 4. Métricas resumen
    monto_total_banco = df_banco["_monto_banco"].sum()
    monto_total_sf    = df_sf["_monto_sf"].sum()

    metricas = {
        "proveedor":              proveedor,
        "fecha_ejecucion":        datetime.now().strftime("%Y-%m-%d %H:%M"),
        "total_registros_banco":  len(df_banco),
        "total_registros_sf":     len(df_sf),
        "monto_total_banco":      round(monto_total_banco, 2),
        "monto_total_sf":         round(monto_total_sf, 2),
        "diferencia_registros":   len(df_banco) - len(df_sf),
        "diferencia_montos":      round(abs(monto_total_banco - monto_total_sf), 2),
        "conciliados":            len(df_conciliados),
        "solo_banco":             len(df_solo_banco),
        "solo_sf":                len(df_solo_sf),
        "dif_monto":              len(df_dif_monto),
        "tolerancia_usada":       tolerancia,
    }

    return {
        "metricas":      metricas,
        "conciliados":   df_conciliados,
        "solo_banco":    df_solo_banco,
        "solo_sf":       df_solo_sf,
        "dif_monto":     df_dif_monto,
        "cruce_completo": df_cruce,
    }


def guardar_resultados(resultado: dict, carpeta_output: str = "output"):
    """Exporta cada tabla de resultados a CSV con fecha."""
    import os
    os.makedirs(carpeta_output, exist_ok=True)
    proveedor = resultado["metricas"]["proveedor"]
    fecha     = datetime.now().strftime("%Y%m%d")
    prefijo   = f"{carpeta_output}/{proveedor}_{fecha}"

    resultado["conciliados"].to_csv(f"{prefijo}_conciliados.csv", index=False)
    resultado["solo_banco"].to_csv(f"{prefijo}_solo_banco.csv", index=False)
    resultado["solo_sf"].to_csv(f"{prefijo}_solo_sf.csv", index=False)
    resultado["dif_monto"].to_csv(f"{prefijo}_diferencias_monto.csv", index=False)

    print(f"✅ Resultados guardados en {carpeta_output}/")
    print(f"   Conciliados:        {resultado['metricas']['conciliados']}")
    print(f"   Solo en banco:      {resultado['metricas']['solo_banco']}")
    print(f"   Solo en SF:         {resultado['metricas']['solo_sf']}")
    print(f"   Diferencia monto:   {resultado['metricas']['dif_monto']}")


# ─────────────────────────────────────────────
#  EJECUCIÓN DIRECTA (sin Streamlit)
# ─────────────────────────────────────────────
if __name__ == "__main__":
    import sys

    if len(sys.argv) < 3:
        print("Uso: python motor.py <archivo_banco.csv> <archivo_sf.csv> [proveedor] [tolerancia]")
        print("Ejemplo: python motor.py data/payvalida/banco.csv data/salesforce/sf.csv Payvalida 1.0")
        sys.exit(1)

    ruta_banco  = sys.argv[1]
    ruta_sf     = sys.argv[2]
    proveedor   = sys.argv[3] if len(sys.argv) > 3 else "Payvalida"
    tolerancia  = float(sys.argv[4]) if len(sys.argv) > 4 else 1.0

    df_banco = cargar_banco(ruta_banco, proveedor)
    df_sf    = cargar_salesforce(ruta_sf)
    resultado = conciliar(df_banco, df_sf, proveedor, tolerancia)

    print("\n📊 RESUMEN DE CONCILIACIÓN")
    print("=" * 45)
    for k, v in resultado["metricas"].items():
        print(f"  {k:<30} {v}")

    guardar_resultados(resultado)
