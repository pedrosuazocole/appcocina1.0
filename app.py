import streamlit as st
import pandas as pd
import os
import ast
import hashlib
from datetime import datetime

# ── dependencias opcionales ──────────────────────────────────────────────────
try:
    import gspread
    from google.oauth2.service_account import Credentials
    GSPREAD_OK = True
except ImportError:
    GSPREAD_OK = False

# ════════════════════════════════════════════════════════════════════════════
# 1. CONFIGURACION GENERAL
# ════════════════════════════════════════════════════════════════════════════
st.set_page_config(page_title="Sistema Contable de Cocina", layout="wide")

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

# Nombre de cada hoja dentro del Google Spreadsheet
SHEETS = {
    "catalogo":   "Catalogo",
    "inventario": "Inventario",
    "recetas":    "Recetas",
    "historial":  "Historial",
    "produccion": "Produccion",
    "usuarios":   "Usuarios",
}

# Columnas por hoja
COLS = {
    "catalogo":   ["Codigo", "Nombre", "Unidad"],
    "inventario": ["Codigo", "Ingrediente", "Unidad", "Stock", "Costo_Unitario"],
    "recetas":    ["Plato", "Detalle_Receta", "Costo_Total_Plato", "Precio_Venta",
                   "Valor_Utilidad", "Margen_Utilidad", "Margen_Objetivo"],
    "historial":  ["Fecha_Factura", "No_Factura", "Codigo", "Producto", "Cantidad", "Costo_Total"],
    "produccion": ["Fecha", "ID", "Plato", "Cantidad", "Detalle"],
    "usuarios":   ["Usuario", "Password_Hash", "Rol", "Activo"],
}

# ════════════════════════════════════════════════════════════════════════════
# 2. AUTENTICACION GOOGLE SHEETS
# ════════════════════════════════════════════════════════════════════════════

def get_gspread_client():
    """Devuelve un cliente gspread autenticado con st.secrets."""
    if not GSPREAD_OK:
        return None
    try:
        creds = Credentials.from_service_account_info(
            st.secrets["gcp_service_account"], scopes=SCOPES
        )
        return gspread.authorize(creds)
    except Exception:
        return None

def get_spreadsheet():
    gc = get_gspread_client()
    if gc is None:
        return None
    try:
        return gc.open_by_key(st.secrets["spreadsheet_id"])
    except Exception:
        return None

def get_worksheet(sheet_key: str):
    """Devuelve la worksheet correspondiente, creándola si no existe."""
    ss = get_spreadsheet()
    if ss is None:
        return None
    nombre = SHEETS[sheet_key]
    try:
        return ss.worksheet(nombre)
    except gspread.WorksheetNotFound:
        ws = ss.add_worksheet(title=nombre, rows=1000, cols=20)
        ws.append_row(COLS[sheet_key])
        return ws

# ════════════════════════════════════════════════════════════════════════════
# 3. LEER / ESCRIBIR GOOGLE SHEETS
# ════════════════════════════════════════════════════════════════════════════

def leer_hoja(sheet_key: str) -> pd.DataFrame:
    ws = get_worksheet(sheet_key)
    if ws is None:
        return pd.DataFrame(columns=COLS[sheet_key])
    try:
        data = ws.get_all_records(expected_headers=COLS[sheet_key])
        if not data:
            return pd.DataFrame(columns=COLS[sheet_key])
        return pd.DataFrame(data)
    except Exception:
        return pd.DataFrame(columns=COLS[sheet_key])

def escribir_hoja(sheet_key: str, df: pd.DataFrame):
    ws = get_worksheet(sheet_key)
    if ws is None:
        return
    try:
        df_clean = df.fillna("").astype(str)
        ws.clear()
        ws.append_row(COLS[sheet_key])
        if not df_clean.empty:
            ws.append_rows(df_clean.values.tolist())
    except Exception as e:
        st.error(f"Error al guardar en Google Sheets ({sheet_key}): {e}")

# ════════════════════════════════════════════════════════════════════════════
# 4. UTILIDADES DE SEGURIDAD
# ════════════════════════════════════════════════════════════════════════════

def hash_password(pwd: str) -> str:
    return hashlib.sha256(pwd.strip().encode()).hexdigest()

def verificar_password(pwd: str, hash_stored: str) -> bool:
    return hash_password(pwd) == hash_stored

def crear_usuario_admin_defecto():
    """Crea el usuario admin por defecto si la hoja Usuarios está vacía."""
    df = st.session_state.get("usuarios", pd.DataFrame(columns=COLS["usuarios"]))
    if df.empty:
        nuevo = pd.DataFrame([{
            "Usuario": "admin",
            "Password_Hash": hash_password("admin123"),
            "Rol": "Administrador",
            "Activo": "True"
        }])
        st.session_state.usuarios = nuevo
        escribir_hoja("usuarios", nuevo)

# ════════════════════════════════════════════════════════════════════════════
# 5. PERMISOS POR ROL
# ════════════════════════════════════════════════════════════════════════════
PERMISOS = {
    "Administrador": ["cat", "inv", "rec", "prod", "rep", "usuarios"],
    "Supervisor":    ["cat", "inv", "rec", "prod", "rep"],
    "Cocina":        ["prod", "rep"],
}

# ════════════════════════════════════════════════════════════════════════════
# 6. PANTALLA DE LOGIN
# ════════════════════════════════════════════════════════════════════════════

def pantalla_login():
    col_c = st.columns([1, 2, 1])[1]
    with col_c:
        st.markdown("## 🍳 Sistema Contable de Cocina")
        st.markdown("### Iniciar Sesión")
        usuario = st.text_input("Usuario")
        password = st.text_input("Contraseña", type="password")
        if st.button("Ingresar", use_container_width=True, type="primary"):
            df_u = st.session_state.get("usuarios", pd.DataFrame(columns=COLS["usuarios"]))
            if df_u.empty:
                st.error("No hay usuarios registrados. Contacte al administrador.")
                return
            fila = df_u[
                (df_u["Usuario"].str.lower() == usuario.lower().strip()) &
                (df_u["Activo"].astype(str).str.lower() == "true")
            ]
            if fila.empty:
                st.error("Usuario no encontrado o inactivo.")
                return
            if not verificar_password(password, str(fila.iloc[0]["Password_Hash"])):
                st.error("Contraseña incorrecta.")
                return
            st.session_state.logueado = True
            st.session_state.usuario_actual = usuario.lower().strip()
            st.session_state.rol_actual = fila.iloc[0]["Rol"]
            st.rerun()

# ════════════════════════════════════════════════════════════════════════════
# 7. CARGAR TODOS LOS DATOS DESDE GOOGLE SHEETS
# ════════════════════════════════════════════════════════════════════════════

def cargar_todos():
    art  = leer_hoja("catalogo")
    ing  = leer_hoja("inventario")
    rec  = leer_hoja("recetas")
    hist = leer_hoja("historial")
    prod = leer_hoja("produccion")
    usu  = leer_hoja("usuarios")

    # Normalizar tipos
    if "Codigo" in art.columns:
        art["Codigo"] = art["Codigo"].astype(str).str.zfill(3)

    for col in ["Stock", "Costo_Unitario"]:
        if col in ing.columns:
            ing[col] = pd.to_numeric(ing[col], errors="coerce").fillna(0.0)

    for col in COLS["recetas"]:
        if col not in rec.columns:
            rec[col] = 0.0

    if not prod.empty and "ID" in prod.columns:
        prod = prod.drop_duplicates(subset="ID", keep="last").reset_index(drop=True)

    return art, ing, rec, hist, prod, usu

def guardar_todo():
    escribir_hoja("catalogo",   st.session_state.catalogo)
    escribir_hoja("inventario", st.session_state.ingredientes)
    escribir_hoja("recetas",    st.session_state.recetas)
    escribir_hoja("historial",  st.session_state.historial)
    if "historial_prod" in st.session_state:
        escribir_hoja("produccion", st.session_state.historial_prod)
    if "usuarios" in st.session_state:
        escribir_hoja("usuarios", st.session_state.usuarios)

def guardar_parcial(*sheet_keys):
    mapping = {
        "catalogo":   ("catalogo",   st.session_state.catalogo),
        "inventario": ("inventario", st.session_state.ingredientes),
        "recetas":    ("recetas",    st.session_state.recetas),
        "historial":  ("historial",  st.session_state.historial),
        "produccion": ("produccion", st.session_state.historial_prod),
        "usuarios":   ("usuarios",   st.session_state.usuarios),
    }
    for key in sheet_keys:
        if key in mapping:
            escribir_hoja(mapping[key][0], mapping[key][1])

# ════════════════════════════════════════════════════════════════════════════
# 8. INICIALIZAR SESSION STATE
# ════════════════════════════════════════════════════════════════════════════

if "datos_cargados" not in st.session_state:
    (st.session_state.catalogo,
     st.session_state.ingredientes,
     st.session_state.recetas,
     st.session_state.historial,
     st.session_state.historial_prod,
     st.session_state.usuarios) = cargar_todos()
    crear_usuario_admin_defecto()
    st.session_state.datos_cargados = True

if "factura_temporal" not in st.session_state:
    st.session_state.factura_temporal = []

if "logueado" not in st.session_state:
    st.session_state.logueado = False
    st.session_state.usuario_actual = ""
    st.session_state.rol_actual = ""

# ════════════════════════════════════════════════════════════════════════════
# 9. CONTROL DE ACCESO
# ════════════════════════════════════════════════════════════════════════════

if not st.session_state.logueado:
    pantalla_login()
    st.stop()

rol = st.session_state.rol_actual
permisos_rol = PERMISOS.get(rol, [])

# ════════════════════════════════════════════════════════════════════════════
# 10. FUNCIÓN AUXILIAR: recalcular ingredientes
# ════════════════════════════════════════════════════════════════════════════

def recalcular_ingredientes():
    if st.session_state.historial.empty:
        st.session_state.ingredientes = pd.DataFrame(columns=COLS["inventario"])
        return

    df_ent = st.session_state.historial.copy()
    df_ent["Codigo"] = df_ent["Codigo"].astype(str).str.zfill(3)
    df_ent[["Cantidad", "Costo_Total"]] = df_ent[["Cantidad", "Costo_Total"]].apply(
        pd.to_numeric, errors="coerce").fillna(0)

    resumen = df_ent.groupby(["Codigo", "Producto", "Unidad"]).agg(
        {"Cantidad": "sum", "Costo_Total": "sum"}).reset_index()
    resumen["Codigo"] = resumen["Codigo"].astype(str).str.zfill(3)
    resumen["Costo_Unitario"] = resumen.apply(
        lambda r: r["Costo_Total"] / r["Cantidad"] if r["Cantidad"] > 0 else 0, axis=1)

    salidas = {}
    if "historial_prod" in st.session_state and not st.session_state.historial_prod.empty:
        for _, fila in st.session_state.historial_prod.iterrows():
            try:
                insumos = ast.literal_eval(str(fila["Detalle"]))
                for ins in insumos:
                    cod = str(ins["Codigo"]).zfill(3)
                    salidas[cod] = salidas.get(cod, 0) + float(ins["Cantidad"]) * float(fila["Cantidad"])
            except Exception:
                pass

    resumen["Salidas"] = resumen["Codigo"].map(salidas).fillna(0)
    resumen["Stock"]   = resumen["Cantidad"] - resumen["Salidas"]

    st.session_state.ingredientes = resumen[
        ["Codigo", "Producto", "Unidad", "Stock", "Costo_Unitario"]
    ].rename(columns={"Producto": "Ingrediente"})

# ════════════════════════════════════════════════════════════════════════════
# 11. MENU LATERAL
# ════════════════════════════════════════════════════════════════════════════

OPCIONES_MENU = {
    "cat":      "Lista de Articulos (Maestro)",
    "inv":      "Inventario/Compras (Facturas)",
    "rec":      "Crear Receta",
    "prod":     "Produccion",
    "rep":      "Informes",
    "usuarios": "Gestion de Usuarios",
}

opciones_visibles = {k: v for k, v in OPCIONES_MENU.items() if k in permisos_rol}

st.sidebar.header("MENU PRINCIPAL")
st.sidebar.markdown(f"👤 **{st.session_state.usuario_actual}** ({rol})")

seleccion_texto = st.sidebar.radio("Ir a:", list(opciones_visibles.values()))
opid = [k for k, v in opciones_visibles.items() if v == seleccion_texto][0]

if st.sidebar.button("🚪 Cerrar Sesión", use_container_width=True):
    st.session_state.logueado = False
    st.session_state.usuario_actual = ""
    st.session_state.rol_actual = ""
    st.rerun()

st.title(seleccion_texto)
st.markdown("---")

# ════════════════════════════════════════════════════════════════════════════
# 12. MÓDULO: LISTA DE ARTÍCULOS
# ════════════════════════════════════════════════════════════════════════════

if opid == "cat":
    t1, t2 = st.tabs(["Registrar", "Modificar"])
    with t1:
        with st.form("f_cat", clear_on_submit=True):
            n_art = st.text_input("Nombre del Producto").upper()
            u_art = st.selectbox("Unidad", ["Unidad", "Libra", "Kg", "Litro", "Onza"])
            if st.form_submit_button("Guardar"):
                if n_art:
                    nuevo_cod = str(len(st.session_state.catalogo) + 1).zfill(3)
                    st.session_state.catalogo = pd.concat(
                        [st.session_state.catalogo,
                         pd.DataFrame([{"Codigo": nuevo_cod, "Nombre": n_art, "Unidad": u_art}])],
                        ignore_index=True)
                    guardar_parcial("catalogo")
                    st.success(f"Creado: {nuevo_cod}")
                    st.rerun()
    with t2:
        if not st.session_state.catalogo.empty:
            art_m = st.selectbox("Seleccione articulo",
                                 [f"{r['Codigo']} - {r['Nombre']}" for _, r in st.session_state.catalogo.iterrows()])
            c_m  = art_m.split(" - ")[0]
            idx  = st.session_state.catalogo.index[st.session_state.catalogo["Codigo"] == c_m].tolist()[0]
            with st.form("f_edit_c"):
                n_n = st.text_input("Nuevo Nombre", value=st.session_state.catalogo.at[idx, "Nombre"]).upper()
                n_u = st.selectbox("Nueva Unidad", ["Unidad", "Libra", "Kg", "Litro", "Onza"],
                                   index=["Unidad", "Libra", "Kg", "Litro", "Onza"].index(
                                       st.session_state.catalogo.at[idx, "Unidad"]))
                if st.form_submit_button("Actualizar"):
                    st.session_state.catalogo.at[idx, "Nombre"] = n_n
                    st.session_state.catalogo.at[idx, "Unidad"] = n_u
                    guardar_parcial("catalogo")
                    st.success("Actualizado")
                    st.rerun()
    st.dataframe(st.session_state.catalogo, use_container_width=True, hide_index=True)

# ════════════════════════════════════════════════════════════════════════════
# 13. MÓDULO: INVENTARIO / COMPRAS
# ════════════════════════════════════════════════════════════════════════════

elif opid == "inv":
    recalcular_ingredientes()
    tab1, tab2, tab3 = st.tabs(["Registrar/Editar Compra", "Gestionar Historial/Inventario", "Kardex Detallado"])

    with tab1:
        st.markdown("### Datos de la Factura")
        c_f1, c_f2 = st.columns(2)
        f_fecha = c_f1.date_input("Fecha de Emision", key="f_fecha_reg")
        f_num   = c_f2.text_input("No. Factura", placeholder="Ej: FAC-123")

        op_p  = ["SELECCIONE PRODUCTO"] + [f"{r['Codigo']} - {r['Nombre']}"
                                            for _, r in st.session_state.catalogo.iterrows()]
        p_sel = st.selectbox("Buscar Insumo", op_p)

        u_act, nom_p, cod_s = "---", "", ""
        if p_sel != "SELECCIONE PRODUCTO":
            cod_s  = p_sel.split(" - ")[0].zfill(3)
            df_cat = st.session_state.catalogo[
                st.session_state.catalogo["Codigo"].astype(str).str.zfill(3) == cod_s]
            if not df_cat.empty:
                u_act = df_cat.iloc[0]["Unidad"]
                nom_p = df_cat.iloc[0]["Nombre"]

        c1, c2, c3, c4 = st.columns(4)
        c1.text_input("Unidad", value=u_act, disabled=True)
        p_cant = c2.number_input("Cantidad",           min_value=0.0, step=0.01)
        p_tot  = c3.number_input("Costo Total (L.)",   min_value=0.0, step=1.0)
        c_u    = p_tot / p_cant if p_cant > 0 else 0.0
        c4.metric("Costo Unit.", f"L. {c_u:.2f}")

        if st.button("Agregar Producto a Detalle"):
            if p_sel != "SELECCIONE PRODUCTO" and p_cant > 0 and f_num:
                st.session_state.factura_temporal.append({
                    "Codigo": cod_s, "Producto": nom_p, "Unidad": u_act,
                    "Cantidad": p_cant, "Costo_Unitario": c_u, "Costo_Total": p_tot
                })
                st.rerun()
            else:
                st.warning("Complete No. Factura, Producto y Cantidad.")

        if st.session_state.factura_temporal:
            st.markdown("---")
            df_temp = pd.DataFrame(st.session_state.factura_temporal)
            st.table(df_temp)
            st.subheader(f"Total Factura: L. {df_temp['Costo_Total'].sum():.2f}")

            col_b1, col_b2 = st.columns(2)
            if col_b1.button("PROCESAR FACTURA E INVENTARIO", type="primary", use_container_width=True):
                st.session_state.historial = st.session_state.historial[
                    st.session_state.historial["No_Factura"] != f_num]
                for it in st.session_state.factura_temporal:
                    nueva_f = pd.DataFrame([{**it, "Fecha_Factura": str(f_fecha), "No_Factura": f_num}])
                    st.session_state.historial = pd.concat(
                        [st.session_state.historial, nueva_f], ignore_index=True)
                guardar_parcial("historial")
                st.session_state.factura_temporal = []
                st.success(f"Exito! La Factura {f_num} ha sido agregada al inventario.")
                st.rerun()

            if col_b2.button("Cancelar Factura", use_container_width=True):
                st.session_state.factura_temporal = []
                st.rerun()

    with tab2:
        st.markdown("### Inventario Fisico Real")
        if not st.session_state.ingredientes.empty:
            df_vis = st.session_state.ingredientes.copy()
            df_vis["Valor_Total"] = pd.to_numeric(df_vis["Stock"], errors="coerce") * pd.to_numeric(df_vis["Costo_Unitario"], errors="coerce")
            st.dataframe(df_vis.rename(columns={"Costo_Unitario": "Costo Prom."}),
                         hide_index=True, use_container_width=True)
            st.info(f"Valor Total de Inversion en Bodega: L. {df_vis['Valor_Total'].sum():.2f}")

        st.markdown("---")
        st.markdown("### Buscador de Facturas")
        c_busq1, c_busq2 = st.columns(2)
        busq_n = c_busq1.text_input("Buscar por No. Factura")
        busq_f = c_busq2.date_input("Filtrar por Fecha", value=None)

        if not st.session_state.historial.empty:
            df_hist = st.session_state.historial.copy()
            if busq_n:
                df_hist = df_hist[df_hist["No_Factura"].astype(str).str.contains(busq_n, case=False)]
            if busq_f:
                df_hist = df_hist[pd.to_datetime(df_hist["Fecha_Factura"], errors="coerce").dt.date == busq_f]

            for n_f, grp in df_hist.groupby("No_Factura"):
                with st.expander(
                    f"Factura: {n_f} | Fecha: {grp.iloc[0]['Fecha_Factura']} | "
                    f"Total: L. {pd.to_numeric(grp['Costo_Total'], errors='coerce').sum():.2f}"):
                    st.dataframe(grp[["Codigo", "Producto", "Cantidad", "Costo_Unitario", "Costo_Total"]],
                                 hide_index=True)
                    c_ed1, c_ed2, c_ed3 = st.columns([0.3, 0.4, 0.3])

                    if c_ed1.button(f"Modificar", key=f"mod_{n_f}"):
                        st.session_state.factura_temporal = grp[
                            ["Codigo", "Producto", "Unidad", "Cantidad", "Costo_Unitario", "Costo_Total"]
                        ].to_dict("records")
                        st.info("Cargado en 'Registrar'. Haga sus cambios y guarde.")

                    confirmar = c_ed2.checkbox(f"Confirmar eliminar {n_f}", key=f"chk_{n_f}")
                    if c_ed3.button(f"ELIMINAR", key=f"del_{n_f}", type="secondary", disabled=not confirmar):
                        st.session_state.historial = st.session_state.historial[
                            st.session_state.historial["No_Factura"] != n_f]
                        guardar_parcial("historial")
                        st.rerun()

    with tab3:
        st.subheader("Kardex Detallado por Producto")
        op_p_k = ["SELECCIONE PRODUCTO"] + [f"{r['Codigo']} - {r['Nombre']}"
                                              for _, r in st.session_state.catalogo.iterrows()]
        insumo_k = st.selectbox("Seleccione Producto:", op_p_k, key="k_p_sel")

        if insumo_k != "SELECCIONE PRODUCTO":
            c_k   = insumo_k.split(" - ")[0].zfill(3)
            df_cat_k = st.session_state.catalogo[
                st.session_state.catalogo["Codigo"].astype(str).str.zfill(3) == c_k]
            u_kardex = df_cat_k.iloc[0]["Unidad"] if not df_cat_k.empty else "---"

            m_ent = st.session_state.historial[
                st.session_state.historial["Codigo"].astype(str).str.zfill(3) == c_k].copy()

            m_sal = pd.DataFrame()
            if "historial_prod" in st.session_state and not st.session_state.historial_prod.empty:
                sal_rows = []
                for _, fila_prod in st.session_state.historial_prod.iterrows():
                    try:
                        insumos = ast.literal_eval(str(fila_prod["Detalle"]))
                        for ins in insumos:
                            if str(ins["Codigo"]).zfill(3) == c_k:
                                sal_rows.append({
                                    "Fecha": fila_prod["Fecha"],
                                    "Ref":   f"PROD {fila_prod['ID']} - {fila_prod['Plato']}",
                                    "Cantidad": float(ins["Cantidad"]) * float(fila_prod["Cantidad"]),
                                    "Costo_Unitario": float(ins.get("Costo_U", 0))
                                })
                    except Exception:
                        pass
                if sal_rows:
                    m_sal = pd.DataFrame(sal_rows)

            k_list = []
            for _, r in m_ent.iterrows():
                k_list.append({"Fecha": r["Fecha_Factura"],
                                "Ref": f"Fact: {r['No_Factura']}",
                                "E": float(r["Cantidad"]) if str(r["Cantidad"]).replace(".","").isdigit() else 0,
                                "S": 0.0,
                                "Total": float(r["Costo_Total"]) if str(r["Costo_Total"]).replace(".","").isdigit() else 0})
            for _, r in m_sal.iterrows():
                k_list.append({"Fecha": r["Fecha"],
                                "Ref":  r["Ref"],
                                "E":    0.0,
                                "S":    float(r["Cantidad"]),
                                "Total": -(float(r["Cantidad"]) * float(r.get("Costo_Unitario", 0)))})

            if k_list:
                df_k = pd.DataFrame(k_list)
                df_k["Fecha"] = pd.to_datetime(df_k["Fecha"], errors="coerce")
                df_k = df_k.sort_values("Fecha")
                stock_a, valor_a, filas = 0.0, 0.0, []
                for _, m in df_k.iterrows():
                    stock_a += (m["E"] - m["S"])
                    valor_a += m["Total"]
                    filas.append({
                        "Fecha":      m["Fecha"],
                        "Ref":        m["Ref"],
                        "Unidad":     u_kardex,
                        "Entrada":    m["E"],
                        "Salida":     m["S"],
                        "Existencia": stock_a,
                        "C. Prom":    valor_a / stock_a if stock_a > 0 else 0,
                        "V. Total":   valor_a
                    })
                final_k = pd.DataFrame(filas)
                st.dataframe(final_k, hide_index=True, use_container_width=True)

                import io
                output = io.BytesIO()
                with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
                    final_k.to_excel(writer, index=False, sheet_name="Kardex")
                st.download_button("Descargar Kardex a Excel", output.getvalue(), f"Kardex_{c_k}.xlsx")
            else:
                st.info("No hay movimientos registrados para este producto.")

# ════════════════════════════════════════════════════════════════════════════
# 14. MÓDULO: RECETAS
# ════════════════════════════════════════════════════════════════════════════

elif opid == "rec":
    t_crear, t_ver = st.tabs(["Crear / Editar Receta", "Ver Recetario"])

    if "edit_rec_data" not in st.session_state:
        st.session_state.edit_rec_data = None

    with t_crear:
        st.subheader("Configuracion de Plato")
        val_nombre, val_precio, val_margen, val_insumos = "", 0.0, 70.0, []

        if st.session_state.edit_rec_data:
            val_nombre = st.session_state.edit_rec_data["Plato"]
            val_precio = float(st.session_state.edit_rec_data["Precio_Venta"])
            val_margen = float(st.session_state.edit_rec_data["Margen_Objetivo"]) * 100
            try:
                items_edit = ast.literal_eval(str(st.session_state.edit_rec_data["Detalle_Receta"]))
                val_insumos = [f"{i['Codigo']} - {i['Nombre']}" for i in items_edit]
            except Exception:
                pass

        with st.container(border=True):
            c_r1, c_r2, c_r3 = st.columns(3)
            n_plato   = c_r1.text_input("Nombre del Plato",       value=val_nombre).upper()
            p_venta   = c_r2.number_input("Precio de Venta (Lps)", min_value=0.0, step=5.0, value=val_precio)
            m_objetivo = c_r3.number_input("Margen Obj. (%)",       value=val_margen) / 100

        st.write("### Ingredientes de la Receta")
        if not st.session_state.ingredientes.empty:
            opciones_i = {f"{r['Codigo']} - {r['Ingrediente']}": r
                          for _, r in st.session_state.ingredientes.iterrows()}
            val_insumos_validos = [v for v in val_insumos if v in opciones_i]
            insumos_sel = st.multiselect("Seleccione los productos:",
                                          list(opciones_i.keys()),
                                          default=val_insumos_validos)

            detalle_final, costo_materia_prima = [], 0.0

            if insumos_sel:
                for s in insumos_sel:
                    datos    = opciones_i[s]
                    val_cant = 0.1
                    if st.session_state.edit_rec_data:
                        try:
                            items_e = ast.literal_eval(str(st.session_state.edit_rec_data["Detalle_Receta"]))
                            for ie in items_e:
                                if str(ie["Codigo"]).zfill(3) == str(datos["Codigo"]).zfill(3):
                                    val_cant = float(ie["Cantidad"])
                        except Exception:
                            pass

                    col1, col2, col3, col4 = st.columns(4)
                    with col1: st.markdown(f"**{datos['Ingrediente']}**")
                    with col2:
                        cant_rec = st.number_input(f"Cant ({datos['Unidad']})",
                                                   min_value=0.01, step=0.1, value=val_cant,
                                                   key=f"q_{datos['Codigo']}")
                    cu = float(datos["Costo_Unitario"]) if str(datos["Costo_Unitario"]).replace(".","").isdigit() else 0.0
                    with col3: st.write(f"Costo P: L.{cu:.2f}")
                    subt = cant_rec * cu
                    with col4: st.write(f"Sub: L.{subt:.2f}")
                    costo_materia_prima += subt
                    detalle_final.append({"Codigo": datos["Codigo"], "Nombre": datos["Ingrediente"],
                                          "Cantidad": cant_rec, "Costo_U": cu, "Subtotal": subt})

                st.divider()
                val_utilidad  = p_venta - costo_materia_prima
                porc_utilidad = (val_utilidad / p_venta) if p_venta > 0 else 0

                if p_venta > 0:
                    if porc_utilidad < m_objetivo:
                        st.error("Margen bajo el objetivo.")
                    else:
                        st.success("Margen optimo.")

                m1, m2, m3 = st.columns(3)
                m1.metric("Costo Total",  f"L. {costo_materia_prima:.2f}")
                m2.metric("Utilidad",     f"L. {val_utilidad:.2f}")
                m3.metric("Margen Real",  f"{porc_utilidad*100:.1f}%")

                if st.button("GUARDAR RECETA", type="primary", use_container_width=True):
                    if n_plato and p_venta > 0 and detalle_final:
                        if not st.session_state.recetas.empty:
                            st.session_state.recetas = st.session_state.recetas[
                                st.session_state.recetas["Plato"] != n_plato]
                        nueva_rec = pd.DataFrame([{
                            "Plato": n_plato, "Detalle_Receta": str(detalle_final),
                            "Costo_Total_Plato": costo_materia_prima,
                            "Precio_Venta": p_venta, "Valor_Utilidad": val_utilidad,
                            "Margen_Utilidad": porc_utilidad, "Margen_Objetivo": m_objetivo
                        }])
                        st.session_state.recetas = pd.concat(
                            [st.session_state.recetas, nueva_rec], ignore_index=True)
                        guardar_parcial("recetas")
                        st.session_state.edit_rec_data = None
                        st.success("Receta guardada")
                        st.rerun()

        if st.session_state.edit_rec_data:
            if st.button("Cancelar Edicion"):
                st.session_state.edit_rec_data = None
                st.rerun()

    with t_ver:
        if not st.session_state.recetas.empty:
            for idx, r in st.session_state.recetas.iterrows():
                with st.expander(f"Plato: {r['Plato']} | L.{r['Precio_Venta']}"):
                    try:
                        items = ast.literal_eval(str(r["Detalle_Receta"]))
                        st.table(pd.DataFrame(items)[["Nombre", "Cantidad", "Costo_U", "Subtotal"]])
                    except Exception:
                        st.write(r["Detalle_Receta"])
                    st.markdown(f"""
                    **RESUMEN:** Precio Venta: **L.{float(r['Precio_Venta']):.2f}** |
                    Costo Total: **L.{float(r['Costo_Total_Plato']):.2f}** |
                    Utilidad: **L.{float(r['Valor_Utilidad']):.2f}** |
                    Margen Real: **{float(r['Margen_Utilidad'])*100:.1f}%** |
                    Margen Obj: **{float(r['Margen_Objetivo'])*100:.1f}%**
                    """)
                    st.write("---")
                    c1, c2 = st.columns(2)
                    if c1.button(f"Editar {r['Plato']}", key=f"btn_edit_{idx}"):
                        st.session_state.edit_rec_data = r.to_dict()
                        st.success(f"Datos de '{r['Plato']}' cargados. Regrese a 'Crear / Editar Receta'.")

                    if f"confirm_del_rec_{idx}" not in st.session_state:
                        st.session_state[f"confirm_del_rec_{idx}"] = False

                    if not st.session_state[f"confirm_del_rec_{idx}"]:
                        if c2.button(f"Eliminar {r['Plato']}", key=f"btn_pre_del_{idx}"):
                            st.session_state[f"confirm_del_rec_{idx}"] = True
                            st.rerun()
                    else:
                        st.warning(f"Desea eliminar la receta de {r['Plato']}?")
                        col_si, col_no = st.columns(2)
                        if col_si.button("Confirmar", key=f"conf_si_rec_{idx}"):
                            st.session_state.recetas = st.session_state.recetas.drop(idx)
                            guardar_parcial("recetas")
                            st.session_state[f"confirm_del_rec_{idx}"] = False
                            st.rerun()
                        if col_no.button("Cancelar", key=f"conf_no_rec_{idx}"):
                            st.session_state[f"confirm_del_rec_{idx}"] = False
                            st.rerun()
        else:
            st.info("No hay recetas registradas.")

# ════════════════════════════════════════════════════════════════════════════
# 15. MÓDULO: PRODUCCIÓN
# ════════════════════════════════════════════════════════════════════════════

elif opid == "prod":
    t_orden, t_hist_prod = st.tabs(["Generar Orden de Produccion", "Historial de Produccion"])

    if "historial_prod" not in st.session_state:
        st.session_state.historial_prod = pd.DataFrame(columns=COLS["produccion"])

    with t_orden:
        st.subheader("Nueva Orden de Produccion")
        if st.session_state.recetas.empty:
            st.warning("No hay recetas creadas. Vaya al modulo 'Crear Receta' primero.")
        else:
            recalcular_ingredientes()
            with st.container(border=True):
                c_p1, c_p2 = st.columns(2)
                lista_platos = st.session_state.recetas["Plato"].tolist()
                plato_p = c_p1.selectbox("Seleccione el Plato a Producir", [""] + lista_platos)
                cant_p  = c_p2.number_input("Cantidad de Platos/Porciones", min_value=1, step=1)

            if plato_p:
                receta_info    = st.session_state.recetas[st.session_state.recetas["Plato"] == plato_p].iloc[0]
                insumos_receta = ast.literal_eval(str(receta_info["Detalle_Receta"]))
                resumen_descuento = []
                puede_procesar    = True

                for ins in insumos_receta:
                    total_necesario = float(ins["Cantidad"]) * float(cant_p)
                    idx_inv = st.session_state.ingredientes[
                        st.session_state.ingredientes["Codigo"] == ins["Codigo"]].index
                    stock_actual = float(st.session_state.ingredientes.at[idx_inv[0], "Stock"]) \
                                   if not idx_inv.empty else 0.0
                    if stock_actual < total_necesario:
                        puede_procesar = False
                    resumen_descuento.append({
                        "Insumo":       ins["Nombre"],
                        "Necesario":    round(total_necesario, 4),
                        "Stock Actual": round(stock_actual, 4),
                        "Estado":       "OK" if stock_actual >= total_necesario else "Sin Stock"
                    })

                st.table(pd.DataFrame(resumen_descuento))

                if st.button("PROCESAR PRODUCCION", type="primary",
                             disabled=not puede_procesar, use_container_width=True):
                    id_prod   = f"PROD-{datetime.now().strftime('%H%M%S%f')[:13]}"
                    fecha_hoy = datetime.now().strftime("%Y-%m-%d %H:%M")

                    st.session_state.ingredientes["Stock"] = st.session_state.ingredientes["Stock"].astype(float)
                    for ins in insumos_receta:
                        total_n = float(ins["Cantidad"]) * float(cant_p)
                        idx_i = st.session_state.ingredientes[
                            st.session_state.ingredientes["Codigo"] == ins["Codigo"]].index
                        if not idx_i.empty:
                            st.session_state.ingredientes.at[idx_i[0], "Stock"] -= total_n

                    nueva_fila_prod = pd.DataFrame([{
                        "Fecha": fecha_hoy, "ID": id_prod,
                        "Plato": plato_p, "Cantidad": cant_p,
                        "Detalle": str(insumos_receta)
                    }])
                    st.session_state.historial_prod = pd.concat(
                        [st.session_state.historial_prod, nueva_fila_prod], ignore_index=True)

                    guardar_parcial("produccion", "inventario")
                    st.success(f"Produccion registrada. ID: {id_prod}")
                    st.balloons()
                    st.rerun()

    with t_hist_prod:
        st.subheader("Registro de Producciones")
        if not st.session_state.historial_prod.empty:
            busq = st.text_input("Buscar por plato:").upper()
            df_h = st.session_state.historial_prod.copy()
            if busq:
                df_h = df_h[df_h["Plato"].str.contains(busq)]

            for idx, row in df_h.iterrows():
                with st.expander(f"{row['Fecha']} | {row['Plato']} | Cant: {row['Cantidad']}"):
                    st.write(f"ID Operacion: {row['ID']}")
                    if st.button(f"Eliminar y Revertir Stock", key=f"del_p_{row['ID']}"):
                        ins_rev = ast.literal_eval(str(row["Detalle"]))
                        for i_r in ins_rev:
                            total_r = float(i_r["Cantidad"]) * float(row["Cantidad"])
                            idx_inv = st.session_state.ingredientes[
                                st.session_state.ingredientes["Codigo"] == i_r["Codigo"]].index
                            if not idx_inv.empty:
                                st.session_state.ingredientes.at[idx_inv[0], "Stock"] += total_r

                        st.session_state.historial_prod = \
                            st.session_state.historial_prod.drop(idx).reset_index(drop=True)
                        guardar_parcial("produccion", "inventario")
                        st.warning("Produccion eliminada y stock restaurado.")
                        st.rerun()
        else:
            st.info("No hay registros de produccion.")

# ════════════════════════════════════════════════════════════════════════════
# 16. MÓDULO: INFORMES
# ════════════════════════════════════════════════════════════════════════════

elif opid == "rep":
    st.subheader("Panel de Control y Analisis")
    recalcular_ingredientes()

    c1, c2, c3 = st.columns(3)
    with c1:
        total_inv = (pd.to_numeric(st.session_state.ingredientes["Stock"], errors="coerce") *
                     pd.to_numeric(st.session_state.ingredientes["Costo_Unitario"], errors="coerce")).sum() \
                    if not st.session_state.ingredientes.empty else 0
        st.metric("Inversion en Bodega", f"L. {total_inv:,.2f}")
    with c2:
        st.metric("Recetas Activas", len(st.session_state.recetas))
    with c3:
        margen_prom = pd.to_numeric(st.session_state.recetas["Margen_Utilidad"], errors="coerce").mean() * 100 \
                      if not st.session_state.recetas.empty else 0
        st.metric("Margen Promedio", f"{margen_prom:.1f}%")

    st.markdown("---")
    col_izq, col_der = st.columns(2)

    with col_izq:
        st.write("### Alertas de Reabastecimiento")
        bajo_stock = st.session_state.ingredientes[
            pd.to_numeric(st.session_state.ingredientes["Stock"], errors="coerce") < 5].copy()

        if not bajo_stock.empty:
            st.warning(f"Hay {len(bajo_stock)} insumos por agotarse.")
            st.dataframe(bajo_stock[["Ingrediente", "Stock", "Unidad"]], hide_index=True, use_container_width=True)
        else:
            st.success("Todos los insumos tienen stock suficiente.")

        if not st.session_state.ingredientes.empty:
            import io
            buf_rep = io.BytesIO()
            df_descarga = bajo_stock if not bajo_stock.empty \
                else st.session_state.ingredientes[["Ingrediente", "Stock", "Unidad"]]
            with pd.ExcelWriter(buf_rep, engine="xlsxwriter") as writer:
                df_descarga.to_excel(writer, index=False, sheet_name="Reporte_Inventario")

            st.download_button(
                label="Descargar Reporte de Inventario (Excel)",
                data=buf_rep.getvalue(),
                file_name=f"Reporte_Stock_{datetime.now().strftime('%d_%m_%Y')}.xlsx",
                mime="application/vnd.ms-excel",
                use_container_width=True
            )

    with col_der:
        st.write("### Top 5 Platos mas Rentables")
        if not st.session_state.recetas.empty:
            top_platos = st.session_state.recetas.copy()
            top_platos["Valor_Utilidad"] = pd.to_numeric(top_platos["Valor_Utilidad"], errors="coerce")
            top_platos = top_platos.nlargest(5, "Valor_Utilidad")
            st.bar_chart(data=top_platos, x="Plato", y="Valor_Utilidad", color="#2ecc71")
        else:
            st.info("No hay datos de recetas disponibles.")

    st.markdown("---")
    if not st.session_state.recetas.empty:
        with st.expander("Ver Detalle de Costeo"):
            df_rep_rec = st.session_state.recetas[
                ["Plato", "Costo_Total_Plato", "Precio_Venta", "Valor_Utilidad", "Margen_Utilidad"]
            ].copy()
            df_rep_rec["Margen %"] = (pd.to_numeric(df_rep_rec["Margen_Utilidad"], errors="coerce") * 100).round(2)
            st.dataframe(
                df_rep_rec[["Plato", "Costo_Total_Plato", "Precio_Venta", "Valor_Utilidad", "Margen %"]],
                hide_index=True, use_container_width=True)

# ════════════════════════════════════════════════════════════════════════════
# 17. MÓDULO: GESTIÓN DE USUARIOS (solo Administrador)
# ════════════════════════════════════════════════════════════════════════════

elif opid == "usuarios":
    if rol != "Administrador":
        st.error("Acceso denegado.")
        st.stop()

    st.subheader("👥 Gestión de Usuarios")

    tab_nuevo, tab_lista = st.tabs(["Agregar Usuario", "Ver / Gestionar Usuarios"])

    with tab_nuevo:
        st.markdown("### Crear nuevo usuario")
        with st.form("f_nuevo_usuario", clear_on_submit=True):
            nu_user = st.text_input("Nombre de usuario").lower().strip()
            nu_pass = st.text_input("Contraseña", type="password")
            nu_pass2 = st.text_input("Confirmar contraseña", type="password")
            nu_rol  = st.selectbox("Rol", ["Administrador", "Supervisor", "Cocina"])

            if st.form_submit_button("Crear Usuario"):
                if not nu_user or not nu_pass:
                    st.error("Complete todos los campos.")
                elif nu_pass != nu_pass2:
                    st.error("Las contraseñas no coinciden.")
                elif nu_user in st.session_state.usuarios["Usuario"].str.lower().tolist():
                    st.error("Ese nombre de usuario ya existe.")
                else:
                    nuevo_u = pd.DataFrame([{
                        "Usuario": nu_user,
                        "Password_Hash": hash_password(nu_pass),
                        "Rol": nu_rol,
                        "Activo": "True"
                    }])
                    st.session_state.usuarios = pd.concat(
                        [st.session_state.usuarios, nuevo_u], ignore_index=True)
                    guardar_parcial("usuarios")
                    st.success(f"Usuario '{nu_user}' creado con rol {nu_rol}.")
                    st.rerun()

    with tab_lista:
        st.markdown("### Usuarios registrados")
        df_u = st.session_state.usuarios.copy()

        if df_u.empty:
            st.info("No hay usuarios.")
        else:
            for idx, row in df_u.iterrows():
                es_actual = row["Usuario"].lower() == st.session_state.usuario_actual.lower()
                estado = "✅ Activo" if str(row["Activo"]).lower() == "true" else "❌ Inactivo"
                with st.expander(f"👤 {row['Usuario']} | {row['Rol']} | {estado}"):
                    col_a, col_b, col_c = st.columns(3)

                    # Cambiar contraseña
                    with col_a:
                        with st.form(f"cambiar_pwd_{idx}"):
                            nueva_pwd = st.text_input("Nueva contraseña", type="password", key=f"np_{idx}")
                            if st.form_submit_button("Cambiar Contraseña"):
                                if nueva_pwd:
                                    st.session_state.usuarios.at[idx, "Password_Hash"] = hash_password(nueva_pwd)
                                    guardar_parcial("usuarios")
                                    st.success("Contraseña actualizada.")
                                    st.rerun()

                    # Cambiar rol
                    with col_b:
                        with st.form(f"cambiar_rol_{idx}"):
                            roles = ["Administrador", "Supervisor", "Cocina"]
                            rol_actual_u = row["Rol"] if row["Rol"] in roles else "Cocina"
                            nuevo_rol = st.selectbox("Cambiar Rol", roles,
                                                     index=roles.index(rol_actual_u),
                                                     key=f"nr_{idx}")
                            if st.form_submit_button("Actualizar Rol"):
                                st.session_state.usuarios.at[idx, "Rol"] = nuevo_rol
                                guardar_parcial("usuarios")
                                st.success("Rol actualizado.")
                                st.rerun()

                    # Activar/Desactivar/Eliminar
                    with col_c:
                        if not es_actual:
                            activo_actual = str(row["Activo"]).lower() == "true"
                            lbl_toggle = "Desactivar" if activo_actual else "Activar"
                            if st.button(lbl_toggle, key=f"tog_{idx}"):
                                st.session_state.usuarios.at[idx, "Activo"] = str(not activo_actual)
                                guardar_parcial("usuarios")
                                st.rerun()

                            if f"conf_del_u_{idx}" not in st.session_state:
                                st.session_state[f"conf_del_u_{idx}"] = False

                            if not st.session_state[f"conf_del_u_{idx}"]:
                                if st.button("🗑️ Eliminar", key=f"pre_del_u_{idx}", type="secondary"):
                                    st.session_state[f"conf_del_u_{idx}"] = True
                                    st.rerun()
                            else:
                                st.warning("¿Confirma eliminar este usuario?")
                                c_si, c_no = st.columns(2)
                                if c_si.button("Sí, eliminar", key=f"si_del_u_{idx}"):
                                    st.session_state.usuarios = st.session_state.usuarios.drop(idx).reset_index(drop=True)
                                    guardar_parcial("usuarios")
                                    st.session_state[f"conf_del_u_{idx}"] = False
                                    st.rerun()
                                if c_no.button("Cancelar", key=f"no_del_u_{idx}"):
                                    st.session_state[f"conf_del_u_{idx}"] = False
                                    st.rerun()
                        else:
                            st.info("(usuario actual)")
