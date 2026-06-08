# 🔄 Motor de Conciliaciones

Sistema de conciliación diaria: movimientos bancarios/proveedores vs. Salesforce.

---

## 📁 Estructura del proyecto

```
conciliaciones/
├── motor.py          ← Lógica de cruce (aquí se configuran los proveedores)
├── app.py            ← Dashboard Streamlit
├── requirements.txt  ← Librerías necesarias
├── data/
│   ├── payvalida/    ← CSVs del proveedor Payvalida
│   └── salesforce/   ← CSVs de Salesforce
└── output/           ← Resultados exportados
```

---

## 🛠 Instalación (primera vez)

### Paso 1 — Instalar Python
1. Ir a https://www.python.org/downloads/
2. Descargar **Python 3.11** (botón amarillo grande)
3. Ejecutar el instalador
4. ⚠️ **IMPORTANTE**: tildar la opción **"Add Python to PATH"** antes de instalar

### Paso 2 — Descargar el proyecto
Descargar y descomprimir la carpeta `conciliaciones` en tu computadora.
Por ejemplo en: `C:\Users\TuUsuario\conciliaciones\`

### Paso 3 — Instalar las librerías
1. Abrir **CMD** (buscá "cmd" en el menú de inicio)
2. Navegar a la carpeta del proyecto:
   ```
   cd C:\Users\TuUsuario\conciliaciones
   ```
3. Ejecutar:
   ```
   pip install -r requirements.txt
   ```

### Paso 4 — Ejecutar la aplicación
```
streamlit run app.py
```
Se va a abrir automáticamente en el navegador en http://localhost:8501

---

## 🌐 Publicar online (acceso para todo el equipo)

### Opción A — Streamlit Community Cloud (GRATIS)
1. Crear cuenta en https://github.com (gratis)
2. Subir la carpeta del proyecto a un repositorio de GitHub
3. Ir a https://share.streamlit.io
4. Conectar con GitHub y seleccionar el repositorio
5. Streamlit te da un **link público** para compartir con el equipo

### Opción B — Ejecutar en red local
Si todos están en la misma red de oficina, podés ejecutar:
```
streamlit run app.py --server.address 0.0.0.0 --server.port 8501
```
Y compartir la IP de tu máquina: `http://192.168.X.X:8501`

---

## ➕ Agregar un nuevo proveedor

Abrí `motor.py` y en la sección `PROVEEDORES` agregá:

```python
"NombreProveedor": {
    "col_id":     "nombre_columna_id_en_csv",
    "col_monto":  "nombre_columna_monto_en_csv",
    "col_fecha":  "nombre_columna_fecha_en_csv",
    "col_estado": "nombre_columna_estado_en_csv",
    "encoding":   "utf-8-sig",
    "separator":  ",",
},
```

Al reiniciar la app, el nuevo proveedor aparece automáticamente en el selector.

---

## ❓ Problemas frecuentes

| Problema | Solución |
|---|---|
| `streamlit: command not found` | Reinstalar con `pip install streamlit` |
| Error de encoding al leer CSV | Guardar el CSV como UTF-8 desde Excel (Guardar como → CSV UTF-8) |
| Columnas no detectadas | Verificar que el nombre exacto coincida con `motor.py` |
| Puerto ocupado | Cambiar puerto: `streamlit run app.py --server.port 8502` |
