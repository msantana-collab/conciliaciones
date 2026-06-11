import streamlit as st
import pandas as pd
import numpy as np
import io
from datetime import datetime
from motor import cargar_banco, cargar_salesforce, conciliar, SALESFORCE_CONFIG
from config_manager import cargar_proveedores, agregar_proveedor, eliminar_proveedor
from historial import guardar_conciliacion, cargar_historial, cargar_detalle
from gsheets import sincronizar_fila, inicializar_hoja, actualizar_nota

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
            filtro_desde = st.date_input("Desde", value=fecha_min, min_value=fecha_min)
        with col_f3:
            filtro_hasta = st.date_input("Hasta", value=fecha_max, min_value=fecha_min)

        # Aplicar filtros
        df_filtrado = df_hist.copy()
        if filtro_prov != "Todos":
            df_filtrado = df_filtrado[df_filtrado["proveedor"] == filtro_prov]
        df_filtrado = df_filtrado[
            (df_filtrado["fecha"].dt.date >= filtro_desde) &
            (df_filtrado["fecha"].dt.date <= filtro_hasta)
        ]

        if df_filtrado.empty:
            st.info("No hay conciliaciones para el período seleccionado.")
        else:
            # ── Selector de ejecución (mostrar la más reciente por defecto)
            opciones = df_filtrado.apply(
                lambda r: f"{r['fecha'].strftime('%d/%m/%Y')} — {r['proveedor']}",
                axis=1
            ).tolist()
            seleccion_idx = st.selectbox("📋 Conciliación", range(len(opciones)), format_func=lambda i: opciones[i])
            fila_sel = df_filtrado.iloc[seleccion_idx]

            st.markdown("---")

            # ── Resumen ejecutivo
            fecha_str = fila_sel["fecha"].strftime("%d/%m/%Y")
            prv_sel   = fila_sel["proveedor"]
            reg_banco = int(fila_sel["registros_banco"])
            reg_sf    = int(fila_sel["registros_sf"])
            dif_reg   = int(fila_sel["diferencia_registros"])
            monto_b   = float(fila_sel["monto_banco"])
            monto_s   = float(fila_sel["monto_sf"])
            dif_m     = float(fila_sel["diferencia_montos"])
            solo_b    = int(fila_sel["solo_banco"])
            solo_s    = int(fila_sel["solo_sf"])
            conc      = int(fila_sel["conciliados"])

            origen_sel = str(fila_sel.get("origen", "Payin")) if "origen" in fila_sel.index else "Payin"
            if origen_sel == "nan" or origen_sel == "":
                origen_sel = "Payin"
            st.markdown(f"### Conciliación {prv_sel} — {fecha_str}")
            st.caption(f"🏷 Origen: **{origen_sel}**")

            # ── Bloque 1: Totales
            st.markdown("#### 📊 Totales del día")
            c1, c2, c3 = st.columns(3)
            c1.metric("Transacciones banco",  f"{reg_banco:,}")
            c2.metric("Transacciones SF",     f"{reg_sf:,}")
            c3.metric("Conciliadas",          f"{conc:,}",
                      delta=f"{round(conc/max(reg_banco,1)*100,1)}% del total")

            st.markdown("")
            c4, c5, c6 = st.columns(3)
            c4.metric("Monto total banco",    fmt_monto(monto_b))
            c5.metric("Monto total SF",       fmt_monto(monto_s))
            c6.metric("Diferencia de montos", fmt_monto(dif_m),
                      delta="✅ Sin diferencia" if dif_m == 0 else f"⚠ {fmt_monto(dif_m)}",
                      delta_color="normal" if dif_m == 0 else "inverse")

            st.markdown("---")

            # ── Bloque 2: Estado de la diferencia
            st.markdown("#### 🔍 Análisis de diferencias")

            if dif_reg == 0 and dif_m == 0:
                st.success("✅ Conciliación perfecta — sin diferencias de registros ni de montos.")
            else:
                col_a, col_b = st.columns(2)

                with col_a:
                    st.markdown("**Órdenes de pago**")
                    if solo_b > 0:
                        st.error(f"🔴 {solo_b} orden{'es' if solo_b>1 else ''} presente{'s' if solo_b>1 else ''} en banco pero no en Salesforce")
                    else:
                        st.success("✅ Sin órdenes pendientes en banco")
                    if solo_s > 0:
                        st.warning(f"🟡 {solo_s} orden{'es' if solo_s>1 else ''} presente{'s' if solo_s>1 else ''} en Salesforce pero no en banco")
                    else:
                        st.success("✅ Sin órdenes pendientes en Salesforce")

                with col_b:
                    st.markdown("**Montos**")
                    if dif_m > 0:
                        carpeta_det = fila_sel["carpeta_detalle"]
                        df_sb = cargar_detalle(carpeta_det, "solo_banco")
                        monto_ordenes_faltantes = 0
                        if not df_sb.empty:
                            cfg = cargar_proveedores().get(prv_sel, {})
                            col_m = cfg.get("col_monto", "").strip()
                            if col_m in df_sb.columns:
                                from motor import limpiar_monto
                                monto_ordenes_faltantes = df_sb[col_m].apply(limpiar_monto).sum()

                        dif_centavos = round(abs(dif_m - monto_ordenes_faltantes), 2)

                        st.markdown(f"- Diferencia total identificada: **{fmt_monto(dif_m)}**")
                        if monto_ordenes_faltantes > 0:
                            st.markdown(f"- Monto de órdenes sin match: **{fmt_monto(monto_ordenes_faltantes)}**")
                        if dif_centavos > 0:
                            st.markdown(f"- Diferencia de centavos: **{fmt_monto(dif_centavos)}**")

                        dif_pendiente = round(abs(dif_m - monto_ordenes_faltantes - dif_centavos), 2)
                        if dif_pendiente == 0:
                            st.success(f"✅ Diferencia pendiente: **{fmt_monto(0)}** — Saldo exacto")
                        else:
                            st.error(f"⚠ Diferencia pendiente: **{fmt_monto(dif_pendiente)}**")
                    else:
                        st.success("✅ Sin diferencias de monto")

            st.markdown("---")

            # ── Bloque 3: Comentario del día
            st.markdown("#### 💬 Resumen del día")
            notas_key = f"notas_{prv_sel}_{fila_sel['fecha'].strftime('%Y%m%d')}"

            # Cargar nota guardada si existe
            import json, os
            notas_path = os.path.join(os.path.dirname(__file__) if '__file__' in dir() else ".", "output", "notas.json")
            try:
                with open(notas_path) as f:
                    todas_notas = json.load(f)
            except Exception:
                todas_notas = {}

            nota_actual = todas_notas.get(notas_key, "")
            nueva_nota = st.text_area(
                "Escribí un resumen de la conciliación del día (visible para todo el equipo)",
                value=nota_actual,
                height=100,
                placeholder="Ej: Conciliación del día sin novedades. Los 5 registros solo en banco corresponden a pagos del día anterior que aún no impactaron en Salesforce.",
                key=f"ta_{notas_key}"
            )
            if st.button("💾 Guardar resumen", key=f"btn_{notas_key}"):
                todas_notas[notas_key] = nueva_nota
                os.makedirs(os.path.dirname(notas_path), exist_ok=True)
                with open(notas_path, "w") as f:
                    json.dump(todas_notas, f, ensure_ascii=False, indent=2)
                # Sincronizar nota al Google Sheet
                ok, err = actualizar_nota(
                    fila_sel["fecha"].strftime("%Y-%m-%d"),
                    prv_sel,
                    nueva_nota
                )
                if ok:
                    st.success("✅ Resumen guardado y sincronizado con Google Sheets.")
                else:
                    st.success("✅ Resumen guardado localmente.")
                    st.caption(f"No se pudo sincronizar con Sheets: {err}")

            st.markdown("---")

            # ── Bloque 4: Detalle de registros
            st.markdown("#### 📂 Detalle de registros")
            carpeta_det = fila_sel["carpeta_detalle"]
            tab1, tab2, tab3, tab4 = st.tabs([
                f"✅ Conciliados ({conc:,})",
                f"🔴 Solo en banco ({solo_b:,})",
                f"🟡 Solo en SF ({solo_s:,})",
                f"🟠 Dif. de monto ({int(fila_sel['dif_monto']):,})",
            ])
            with tab1:
                mostrar_tabla(cargar_detalle(carpeta_det, "conciliados"),       f"hist_conc_{seleccion_idx}")
            with tab2:
                mostrar_tabla(cargar_detalle(carpeta_det, "solo_banco"),        f"hist_sb_{seleccion_idx}")
            with tab3:
                mostrar_tabla(cargar_detalle(carpeta_det, "solo_sf"),           f"hist_ssf_{seleccion_idx}")
            with tab4:
                mostrar_tabla(cargar_detalle(carpeta_det, "diferencias_monto"), f"hist_dm_{seleccion_idx}")

            st.markdown("---")
            # ── Exportar
            columnas_export = [
                "fecha", "hora", "origen", "proveedor",
                "registros_banco", "registros_sf", "diferencia_registros",
                "monto_banco", "monto_sf", "diferencia_montos",
                "conciliados", "solo_banco", "solo_sf", "dif_monto"
            ]
            st.download_button(
                label="⬇ Exportar historial filtrado (CSV)",
                data=df_to_csv_bytes(df_filtrado[columnas_export]),
                file_name=f"historial_{datetime.now().strftime('%Y%m%d')}.csv",
                mime="text/csv"
            )


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

    st.markdown("---")
    st.markdown("### 🗑 Administrar historial")
    st.markdown("Eliminá registros de prueba o conciliaciones incorrectas.")

    import os, shutil
    from historial import cargar_historial, OUTPUT_DIR, HISTORIAL_PATH

    df_admin = cargar_historial()

    if df_admin.empty:
        st.info("El historial está vacío.")
    else:
        opciones_admin = df_admin.apply(
            lambda r: f"{r['fecha'].strftime('%d/%m/%Y')} — {r['proveedor']}",
            axis=1
        ).tolist()

        sel_admin = st.selectbox(
            "Seleccioná el registro a eliminar",
            range(len(opciones_admin)),
            format_func=lambda i: opciones_admin[i],
            key="sel_admin"
        )

        fila_admin = df_admin.iloc[sel_admin]

        col_btn, col_info = st.columns([1, 3])
        with col_btn:
            confirmar = st.checkbox("Confirmar eliminación", key="confirm_del")
            if st.button("🗑 Eliminar registro", type="secondary", disabled=not confirmar):
                # 1. Eliminar del historial.csv local
                df_nuevo = df_admin.drop(df_admin.index[sel_admin]).reset_index(drop=True)
                df_nuevo.to_csv(HISTORIAL_PATH, index=False)

                # 2. Eliminar carpeta de detalle local
                carpeta = os.path.join(OUTPUT_DIR, fila_admin["carpeta_detalle"])
                if os.path.exists(carpeta):
                    shutil.rmtree(carpeta)

                # 3. Eliminar del Google Sheet
                try:
                    from gsheets import _get_client, SHEET_ID
                    client = _get_client()
                    sheet = client.open_by_key(SHEET_ID).sheet1
                    registros = sheet.get_all_values()
                    fecha_str = fila_admin["fecha"].strftime("%Y-%m-%d")
                    for i, row in enumerate(registros[1:], start=2):
                        if len(row) >= 3 and row[0] == fecha_str and row[2] == fila_admin["proveedor"]:
                            sheet.delete_rows(i)
                            break
                    st.success("✅ Registro eliminado del historial local y de Google Sheets.")
                except Exception as e:
                    st.success("✅ Registro eliminado del historial local.")
                    st.caption(f"No se pudo eliminar de Sheets: {e}")

                st.rerun()

        with col_info:
            st.caption(f"Fecha: **{fila_admin['fecha'].strftime('%d/%m/%Y')}** | Proveedor: **{fila_admin['proveedor']}** | Conciliados: **{int(fila_admin['conciliados']):,}**")
