import streamlit as st
import pandas as pd
import numpy as np
import io
from datetime import datetime
from motor import cargar_banco, cargar_salesforce, conciliar, SALESFORCE_CONFIG
from config_manager import cargar_proveedores, agregar_proveedor, eliminar_proveedor
from historial import guardar_conciliacion, cargar_historial, cargar_detalle
from gsheets import sincronizar_fila, inicializar_hoja

# ─────────────────────────────────────────────
#  CONFIGURACIÓN DE PÁGINA
# ─────────────────────────────────────────────
st.set_page_config(
    page_title="Motor de Conciliaciones",
    page_icon="🔄",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
    div[data-testid="stMetric"] {
        border-radius: 10px;
        padding: 12px 16px;
        border: 1px solid rgba(128,128,128,0.2);
    }
    div[data-testid="stMetricValue"] > div { font-size: 1.3rem !important; }
</style>
""", unsafe_allow_html=True)


# ─────────────────────────────────────────────
#  SIDEBAR
# ─────────────────────────────────────────────
with st.sidebar:
    st.title("🔄 Conciliaciones")
    st.markdown("---")

    pagina = st.radio(
        "Navegación",
        ["▶ Conciliar", "📅 Historial", "⚙ Proveedores"],
        label_visibility="collapsed"
    )

    if pagina == "▶ Conciliar":
        st.markdown("---")
        PROVEEDORES = cargar_proveedores()

        if not PROVEEDORES:
            st.warning("No hay proveedores configurados.")
            proveedor = None
        else:
            proveedor = st.selectbox("Proveedor", options=list(PROVEEDORES.keys()))

        tolerancia = st.number_input(
            "Tolerancia de centavos ($)",
            min_value=0.0, max_value=100.0,
            value=1.0, step=0.5,
        )

        from datetime import date, timedelta
        fecha_conciliacion = st.date_input(
            "📅 Fecha de la conciliación",
            value=date.today() - timedelta(days=1),
            help="Seleccioná la fecha de los datos que estás cargando, no la de hoy"
        )

        st.markdown("---")
        st.markdown("#### Carga de archivos")
        archivo_banco = st.file_uploader("📁 Archivo proveedor (banco)", type=["csv"], key="banco")
        archivo_sf    = st.file_uploader("📁 Archivo Salesforce",        type=["csv"], key="sf")
        ejecutar      = st.button("▶ Ejecutar conciliación", use_container_width=True, type="primary")

    st.markdown("---")
    st.caption(f"🕐 {datetime.now().strftime('%d/%m/%Y %H:%M')}")


# ─────────────────────────────────────────────
#  FUNCIONES AUXILIARES
# ─────────────────────────────────────────────
def fmt_monto(n):
    if pd.isna(n) or n is None:
        return "—"
    return f"$ {n:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

def df_to_csv_bytes(df):
    return df.to_csv(index=False).encode("utf-8-sig")

def mostrar_tabla(df, key):
    if df.empty:
        st.info("Sin registros en esta categoría. ✅")
        return
    cols = [c for c in df.columns if not c.startswith("_")]
    st.dataframe(df[cols], use_container_width=True, hide_index=True)
    st.download_button(
        label="⬇ Descargar CSV",
        data=df_to_csv_bytes(df[cols]),
        file_name=f"{key}_{datetime.now().strftime('%Y%m%d')}.csv",
        mime="text/csv",
        key=f"dl_{key}"
    )

def mostrar_resultado(resultado, prv):
    metricas = resultado["metricas"]

    col_t, col_f = st.columns([3, 1])
    with col_t:
        st.title(f"🔄 Conciliación — {prv}")
    with col_f:
        st.caption(f"Ejecutado: {metricas['fecha_ejecucion']}")

    st.markdown("### Resumen")
    c1, c2, c3, c4, c5, c6 = st.columns(6)
    c1.metric("Registros banco", f"{metricas['total_registros_banco']:,}")
    c2.metric("Registros SF",    f"{metricas['total_registros_sf']:,}")
    c3.metric("Dif. registros",  f"{abs(metricas['diferencia_registros']):,}",
              delta=f"{metricas['diferencia_registros']:+}" if metricas["diferencia_registros"] != 0 else None)
    c4.metric("Monto banco",     fmt_monto(metricas["monto_total_banco"]))
    c5.metric("Monto SF",        fmt_monto(metricas["monto_total_sf"]))
    c6.metric("Dif. montos",     fmt_monto(metricas["diferencia_montos"]),
              delta="⚠ Revisar" if metricas["diferencia_montos"] > 0 else None)

    st.markdown("---")
    col_ok, col_sb, col_ssf, col_dm = st.columns(4)
    pct = round(metricas["conciliados"] / max(metricas["total_registros_banco"], 1) * 100, 1)
    col_ok.metric("✅ Conciliados",    f"{metricas['conciliados']:,}", f"{pct}%")
    col_sb.metric("🔴 Solo en banco",  f"{metricas['solo_banco']:,}",
                  delta="OK" if metricas["solo_banco"] == 0 else "Revisar",
                  delta_color="normal" if metricas["solo_banco"] == 0 else "inverse")
    col_ssf.metric("🟡 Solo en SF",    f"{metricas['solo_sf']:,}",
                   delta="OK" if metricas["solo_sf"] == 0 else "Revisar",
                   delta_color="normal" if metricas["solo_sf"] == 0 else "inverse")
    col_dm.metric("🟠 Dif. de monto",  f"{metricas['dif_monto']:,}",
                  delta="OK" if metricas["dif_monto"] == 0 else "Revisar",
                  delta_color="normal" if metricas["dif_monto"] == 0 else "inverse")

    st.markdown("---")
    dif_identificada = metricas["diferencia_montos"]
    dif_encontrada   = resultado["dif_monto"]["_diferencia"].sum() if not resultado["dif_monto"].empty else 0
    dif_pendiente    = round(abs(dif_identificada - dif_encontrada), 2)

    col_r1, col_r2, col_r3 = st.columns(3)
    col_r1.metric("Diferencia identificada", fmt_monto(dif_identificada))
    col_r2.metric("Diferencia encontrada",   fmt_monto(dif_encontrada))
    if dif_pendiente == 0:
        col_r3.success(f"✅ Diferencia pendiente: {fmt_monto(dif_pendiente)} — OK")
    else:
        col_r3.error(f"⚠ Diferencia pendiente: {fmt_monto(dif_pendiente)}")

    st.markdown("---")
    tab1, tab2, tab3, tab4 = st.tabs([
        f"✅ Conciliados ({metricas['conciliados']:,})",
        f"🔴 Solo en banco ({metricas['solo_banco']:,})",
        f"🟡 Solo en SF ({metricas['solo_sf']:,})",
        f"🟠 Dif. de monto ({metricas['dif_monto']:,})",
    ])
    with tab1:
        st.caption("Registros que cruzaron correctamente dentro de la tolerancia.")
        mostrar_tabla(resultado["conciliados"], "conciliados")
    with tab2:
        st.caption("Registros en banco pero no encontrados en Salesforce.")
        mostrar_tabla(resultado["solo_banco"], "solo_banco")
    with tab3:
        st.caption("Registros en Salesforce pero no encontrados en banco.")
        mostrar_tabla(resultado["solo_sf"], "solo_sf")
    with tab4:
        st.caption("Registros que cruzaron pero con diferencia de monto superior a la tolerancia.")
        if not resultado["dif_monto"].empty:
            df_dm = resultado["dif_monto"].copy()
            df_dm["Monto banco"] = df_dm["_monto_banco"].apply(fmt_monto)
            df_dm["Monto SF"]    = df_dm["_monto_sf"].apply(fmt_monto)
            df_dm["Diferencia"]  = df_dm["_diferencia"].apply(fmt_monto)
            mostrar_tabla(df_dm, "diferencias_monto")
        else:
            st.success("Sin diferencias de monto. ✅")

    st.markdown("---")
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        for hoja, df in {
            "Conciliados":       resultado["conciliados"],
            "Solo_Banco":        resultado["solo_banco"],
            "Solo_SF":           resultado["solo_sf"],
            "Diferencias_Monto": resultado["dif_monto"],
        }.items():
            cols = [c for c in df.columns if not c.startswith("_")]
            df[cols].to_excel(writer, sheet_name=hoja, index=False)
        pd.DataFrame([metricas]).T.reset_index().rename(
            columns={"index": "Métrica", 0: "Valor"}
        ).to_excel(writer, sheet_name="Resumen", index=False)

    st.download_button(
        label="⬇ Descargar Excel completo",
        data=buffer.getvalue(),
        file_name=f"conciliacion_{prv}_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )


# ─────────────────────────────────────────────
#  PÁGINA: CONCILIAR
# ─────────────────────────────────────────────
if pagina == "▶ Conciliar":
    if "resultado" not in st.session_state:
        st.session_state.resultado = None

    PROVEEDORES = cargar_proveedores()

    if ejecutar:
        if not proveedor:
            st.error("Primero configurá un proveedor en ⚙ Proveedores.")
        elif not archivo_banco or not archivo_sf:
            st.error("Cargá los dos archivos antes de ejecutar.")
        else:
            with st.spinner("Procesando conciliación..."):
                try:
                    import motor as m
                    m.PROVEEDORES = PROVEEDORES
                    df_banco   = cargar_banco(archivo_banco, proveedor)
                    df_sf_data = cargar_salesforce(archivo_sf)
                    resultado  = conciliar(df_banco, df_sf_data, proveedor, tolerancia)
                    fila = guardar_conciliacion(resultado, fecha_override=fecha_conciliacion.strftime("%Y-%m-%d"))
                    # Sincronizar con Google Sheets
                    ok, err = sincronizar_fila(fila)
                    if ok:
                        st.success(f"✅ Conciliación del {fecha_conciliacion.strftime('%d/%m/%Y')} guardada y sincronizada con Google Sheets.")
                    else:
                        st.warning(f"✅ Guardada localmente, pero no se pudo sincronizar con Google Sheets: {err}")
                    st.session_state.resultado = resultado
                    st.session_state.proveedor = proveedor
                except Exception as e:
                    st.error(f"Error al procesar: {e}")
                    st.exception(e)

    if st.session_state.resultado is None:
        st.title("🔄 Motor de Conciliaciones")
        st.markdown("""
        ### Bienvenido
        Usá el panel lateral para:
        1. Seleccionar el **proveedor**
        2. Cargar el **archivo del proveedor** (CSV)
        3. Cargar el **archivo de Salesforce** (CSV)
        4. Hacer click en **Ejecutar conciliación**

        El resultado se guarda automáticamente en el historial.
        """)
        if PROVEEDORES:
            st.info(f"Proveedores configurados: **{', '.join(PROVEEDORES.keys())}**")
        else:
            st.warning("No hay proveedores configurados. Ir a ⚙ Proveedores.")
    else:
        mostrar_resultado(st.session_state.resultado, st.session_state.proveedor)


# ─────────────────────────────────────────────
#  PÁGINA: HISTORIAL
# ─────────────────────────────────────────────
elif pagina == "📅 Historial":
    st.title("📅 Historial de conciliaciones")

    df_hist = cargar_historial()

    if df_hist.empty:
        st.info("Todavía no hay conciliaciones guardadas. Ejecutá la primera desde ▶ Conciliar.")
    else:
        # ── Filtros
        col_f1, col_f2, col_f3 = st.columns(3)
        with col_f1:
            proveedores_hist = ["Todos"] + sorted(df_hist["proveedor"].unique().tolist())
            filtro_prov = st.selectbox("Proveedor", proveedores_hist)
        with col_f2:
            fecha_min = df_hist["fecha"].min().date()
            fecha_max = df_hist["fecha"].max().date()
            filtro_desde = st.date_input("Desde", value=fecha_min, min_value=fecha_min, max_value=fecha_max)
        with col_f3:
            filtro_hasta = st.date_input("Hasta", value=fecha_max, min_value=fecha_min, max_value=fecha_max)

        # Aplicar filtros
        df_filtrado = df_hist.copy()
        if filtro_prov != "Todos":
            df_filtrado = df_filtrado[df_filtrado["proveedor"] == filtro_prov]
        df_filtrado = df_filtrado[
            (df_filtrado["fecha"].dt.date >= filtro_desde) &
            (df_filtrado["fecha"].dt.date <= filtro_hasta)
        ]

        st.markdown(f"**{len(df_filtrado)} conciliaciones** encontradas")
        st.markdown("---")

        # ── Métricas resumen del período
        if not df_filtrado.empty:
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Total ejecuciones",      len(df_filtrado))
            c2.metric("Promedio conciliados",   f"{df_filtrado['conciliados'].mean():,.0f}")
            c3.metric("Total solo en banco",    f"{df_filtrado['solo_banco'].sum():,}")
            c4.metric("Total dif. de monto",    f"{df_filtrado['dif_monto'].sum():,}")
            st.markdown("---")

        # ── Tabla de historial
        columnas_mostrar = [
            "fecha", "hora", "proveedor",
            "registros_banco", "registros_sf", "diferencia_registros",
            "monto_banco", "monto_sf", "diferencia_montos",
            "conciliados", "solo_banco", "solo_sf", "dif_monto"
        ]
        df_vista = df_filtrado[columnas_mostrar].copy()
        df_vista["fecha"]         = df_vista["fecha"].dt.strftime("%d/%m/%Y")
        df_vista["monto_banco"]   = df_vista["monto_banco"].apply(fmt_monto)
        df_vista["monto_sf"]      = df_vista["monto_sf"].apply(fmt_monto)
        df_vista["diferencia_montos"] = df_vista["diferencia_montos"].apply(fmt_monto)

        st.dataframe(df_vista, use_container_width=True, hide_index=True)

        # ── Exportar historial filtrado
        st.download_button(
            label="⬇ Exportar historial (CSV)",
            data=df_to_csv_bytes(df_filtrado[columnas_mostrar]),
            file_name=f"historial_{datetime.now().strftime('%Y%m%d')}.csv",
            mime="text/csv"
        )

        st.markdown("---")

        # ── Ver detalle de una ejecución específica
        st.markdown("### 🔍 Ver detalle de una ejecución")
        opciones = df_filtrado.apply(
            lambda r: f"{r['fecha'].strftime('%d/%m/%Y')} {r['hora']} — {r['proveedor']}",
            axis=1
        ).tolist()

        if opciones:
            seleccion_idx = st.selectbox("Seleccioná una ejecución", range(len(opciones)), format_func=lambda i: opciones[i])
            fila_sel = df_filtrado.iloc[seleccion_idx]
            carpeta_det = fila_sel["carpeta_detalle"]

            tab1, tab2, tab3, tab4 = st.tabs([
                f"✅ Conciliados ({int(fila_sel['conciliados']):,})",
                f"🔴 Solo banco ({int(fila_sel['solo_banco']):,})",
                f"🟡 Solo SF ({int(fila_sel['solo_sf']):,})",
                f"🟠 Dif. monto ({int(fila_sel['dif_monto']):,})",
            ])
            with tab1:
                mostrar_tabla(cargar_detalle(carpeta_det, "conciliados"),      f"hist_conc_{seleccion_idx}")
            with tab2:
                mostrar_tabla(cargar_detalle(carpeta_det, "solo_banco"),       f"hist_sb_{seleccion_idx}")
            with tab3:
                mostrar_tabla(cargar_detalle(carpeta_det, "solo_sf"),          f"hist_ssf_{seleccion_idx}")
            with tab4:
                mostrar_tabla(cargar_detalle(carpeta_det, "diferencias_monto"),f"hist_dm_{seleccion_idx}")


# ─────────────────────────────────────────────
#  PÁGINA: PROVEEDORES
# ─────────────────────────────────────────────
elif pagina == "⚙ Proveedores":
    st.title("⚙ Gestión de proveedores")
    st.markdown("Configurá las columnas de cada proveedor para el cruce de datos.")

    PROVEEDORES = cargar_proveedores()

    if PROVEEDORES:
        st.markdown("### Proveedores configurados")
        df_prov = pd.DataFrame(PROVEEDORES).T.reset_index()
        df_prov.columns = ["Proveedor", "Col. ID", "Col. Monto", "Col. Fecha", "Col. Estado", "Encoding", "Separador"]
        st.dataframe(df_prov, use_container_width=True, hide_index=True)

        with st.expander("🗑 Eliminar proveedor"):
            prov_del = st.selectbox("Seleccioná el proveedor a eliminar", list(PROVEEDORES.keys()), key="del_prov")
            if st.button("Eliminar", type="secondary"):
                eliminar_proveedor(prov_del)
                st.success(f"Proveedor '{prov_del}' eliminado.")
                st.rerun()
    else:
        st.info("No hay proveedores configurados todavía.")

    st.markdown("---")
    st.markdown("### ➕ Agregar nuevo proveedor")
    st.markdown("Completá los nombres de columna **exactamente como aparecen** en el CSV del proveedor.")

    col1, col2 = st.columns(2)
    with col1:
        nuevo_nombre    = st.text_input("Nombre del proveedor",  placeholder="Ej: Bancolombia")
        nuevo_col_id    = st.text_input("Columna ID / PO",        placeholder="Ej: PO")
        nuevo_col_monto = st.text_input("Columna monto",          placeholder="Ej: Valor Total")
    with col2:
        nuevo_col_fecha  = st.text_input("Columna fecha",  placeholder="Ej: Fecha Creación")
        nuevo_col_estado = st.text_input("Columna estado", placeholder="Ej: Estado")
        nuevo_sep = st.selectbox("Separador del CSV", [",", ";"], index=0)

    if st.button("➕ Agregar proveedor", type="primary"):
        if not nuevo_nombre or not nuevo_col_id or not nuevo_col_monto:
            st.error("Completá al menos: nombre, columna ID y columna monto.")
        elif nuevo_nombre in PROVEEDORES:
            st.error(f"Ya existe un proveedor con el nombre '{nuevo_nombre}'.")
        else:
            agregar_proveedor(nuevo_nombre, {
                "col_id":     nuevo_col_id,
                "col_monto":  nuevo_col_monto,
                "col_fecha":  nuevo_col_fecha,
                "col_estado": nuevo_col_estado,
                "encoding":   "utf-8-sig",
                "separator":  nuevo_sep,
            })
            st.success(f"✅ Proveedor '{nuevo_nombre}' agregado correctamente.")
            st.rerun()

    st.markdown("---")
    st.markdown("### Configuración Salesforce (fija para todos los proveedores)")
    st.dataframe(pd.DataFrame([SALESFORCE_CONFIG]), use_container_width=True, hide_index=True)

    st.markdown("---")
    st.markdown("### 🔗 Conexión con Google Sheets")
    st.markdown("El historial se sincroniza automáticamente al ejecutar cada conciliación.")
    if st.button("🔍 Verificar conexión"):
        with st.spinner("Verificando..."):
            ok, msg = inicializar_hoja()
        if ok:
            st.success(f"✅ Conexión exitosa. Bot: `{msg}`")
        else:
            st.error(f"❌ Error de conexión: {msg}")
