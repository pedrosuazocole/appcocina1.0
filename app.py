import streamlit as st
import pandas as pd
import os
from datetime import datetime
import ast  # Necesario para leer los detalles de la receta

# 1. CONFIGURACIÓN E INSTALACIÓN DE DATOS
st.set_page_config(page_title="Sistema Contable de Cocina", layout="wide")
FILE_NAME = 'control_cocina_total.xlsx'

def cargar_datos():
    cols_art  = ["Codigo", "Nombre", "Unidad"]
    cols_ing  = ["Codigo", "Ingrediente", "Unidad", "Stock", "Costo_Unitario"]
    cols_rec  = ["Plato", "Detalle_Receta", "Costo_Total_Plato", "Precio_Venta",
                 "Valor_Utilidad", "Margen_Utilidad", "Margen_Objetivo"]
    cols_hist = ["Fecha_Factura", "No_Factura", "Codigo", "Producto", "Cantidad", "Costo_Total"]
    cols_prod = ["Fecha", "ID", "Plato", "Cantidad", "Detalle"]  # CORRECCION BUG 1

    if os.path.exists(FILE_NAME):
        try:
            art  = pd.read_excel(FILE_NAME, sheet_name='Catalogo')
            ing  = pd.read_excel(FILE_NAME, sheet_name='Inventario')
            rec  = pd.read_excel(FILE_NAME, sheet_name='Recetas')
            hist = pd.read_excel(FILE_NAME, sheet_name='Historial')

            # CORRECCION BUG 1: Cargar la hoja de Produccion al iniciar
            try:
                prod = pd.read_excel(FILE_NAME, sheet_name='Produccion')
                prod = prod.drop_duplicates(subset='ID', keep='last').reset_index(drop=True)
            except Exception:
                prod = pd.DataFrame(columns=cols_prod)

            for col in cols_rec:
                if col not in rec.columns:
                    rec[col] = 0.0

            if 'Codigo' in art.columns:
                art['Codigo'] = art['Codigo'].astype(str).str.zfill(3)
            ing['Stock']          = pd.to_numeric(ing['Stock'],          errors='coerce').fillna(0.0).astype(float)
            ing['Costo_Unitario'] = pd.to_numeric(ing['Costo_Unitario'], errors='coerce').fillna(0.0).astype(float)

            return art, ing, rec, hist, prod  # devuelve prod tambien

        except Exception as e:
            st.error(f"Error al cargar el Excel: {e}")

    return (pd.DataFrame(columns=cols_art),
            pd.DataFrame(columns=cols_ing),
            pd.DataFrame(columns=cols_rec),
            pd.DataFrame(columns=cols_hist),
            pd.DataFrame(columns=cols_prod))

# CORRECCION BUG 1: Desempacar los 5 valores y poblar historial_prod
if 'catalogo' not in st.session_state:
    (st.session_state.catalogo,
     st.session_state.ingredientes,
     st.session_state.recetas,
     st.session_state.historial,
     st.session_state.historial_prod) = cargar_datos()

if 'factura_temporal' not in st.session_state:
    st.session_state.factura_temporal = []

def guardar():
    try:
        with pd.ExcelWriter(FILE_NAME) as writer:
            st.session_state.catalogo.to_excel(      writer, sheet_name='Catalogo',   index=False)
            st.session_state.ingredientes.to_excel(   writer, sheet_name='Inventario', index=False)
            st.session_state.recetas.to_excel(         writer, sheet_name='Recetas',    index=False)
            st.session_state.historial.to_excel(       writer, sheet_name='Historial',  index=False)
            # CORRECCION BUG 1: guardar tambien la hoja de Produccion
            if 'historial_prod' in st.session_state:
                st.session_state.historial_prod.to_excel(writer, sheet_name='Produccion', index=False)
    except Exception as e:
        st.error(f"No se pudo guardar. Cierra el Excel si esta abierto. Error: {e}")

# FUNCION AUXILIAR: recalcula ingredientes desde historial + historial_prod
# CORRECCION BUG 2 / BUG 3: logica centralizada y siempre actualizada
def recalcular_ingredientes():
    """Reconstruye st.session_state.ingredientes a partir de entradas (Historial)
    y salidas (Produccion) para que el stock siempre sea coherente."""
    if st.session_state.historial.empty:
        st.session_state.ingredientes = pd.DataFrame(
            columns=['Codigo', 'Ingrediente', 'Unidad', 'Stock', 'Costo_Unitario'])
        return

    df_ent = st.session_state.historial.copy()
    df_ent['Codigo'] = df_ent['Codigo'].astype(str).str.zfill(3)
    df_ent[['Cantidad', 'Costo_Total']] = df_ent[['Cantidad', 'Costo_Total']].apply(pd.to_numeric, errors='coerce').fillna(0)

    resumen = df_ent.groupby(['Codigo', 'Producto', 'Unidad']).agg(
        {'Cantidad': 'sum', 'Costo_Total': 'sum'}).reset_index()
    resumen['Codigo'] = resumen['Codigo'].astype(str).str.zfill(3)
    resumen['Costo_Unitario'] = resumen.apply(
        lambda r: r['Costo_Total'] / r['Cantidad'] if r['Cantidad'] > 0 else 0, axis=1)

    # Calcular salidas desde historial_prod
    salidas = {}
    if 'historial_prod' in st.session_state and not st.session_state.historial_prod.empty:
        for _, fila in st.session_state.historial_prod.iterrows():
            try:
                insumos = ast.literal_eval(str(fila['Detalle']))
                for ins in insumos:
                    cod = str(ins['Codigo']).zfill(3)
                    salidas[cod] = salidas.get(cod, 0) + float(ins['Cantidad']) * float(fila['Cantidad'])
            except Exception:
                pass

    resumen['Salidas'] = resumen['Codigo'].map(salidas).fillna(0)
    resumen['Stock']   = resumen['Cantidad'] - resumen['Salidas']

    st.session_state.ingredientes = resumen[
        ['Codigo', 'Producto', 'Unidad', 'Stock', 'Costo_Unitario']
    ].rename(columns={'Producto': 'Ingrediente'})


# 2. MENU LATERAL
st.sidebar.header("MENU PRINCIPAL")
opciones_menu = {
    "cat":  "Lista de Articulos (Maestro)",
    "inv":  "Inventario/Compras (Facturas)",
    "rec":  "Crear Receta",
    "prod": "Produccion",
    "rep":  "Informes"
}
seleccion_texto = st.sidebar.radio("Ir a:", list(opciones_menu.values()))
opid = [k for k, v in opciones_menu.items() if v == seleccion_texto][0]

st.title(f"{seleccion_texto}")
st.markdown("---")

# 3. LOGICA DE PANTALLAS

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
                    guardar()
                    st.success(f"Creado: {nuevo_cod}")
                    st.rerun()
    with t2:
        if not st.session_state.catalogo.empty:
            art_m = st.selectbox("Seleccione articulo",
                                 [f"{r['Codigo']} - {r['Nombre']}" for _, r in st.session_state.catalogo.iterrows()])
            c_m  = art_m.split(" - ")[0]
            idx  = st.session_state.catalogo.index[st.session_state.catalogo['Codigo'] == c_m].tolist()[0]
            with st.form("f_edit_c"):
                n_n = st.text_input("Nuevo Nombre",  value=st.session_state.catalogo.at[idx, 'Nombre']).upper()
                n_u = st.selectbox("Nueva Unidad",   ["Unidad", "Libra", "Kg", "Litro", "Onza"],
                                   index=["Unidad", "Libra", "Kg", "Litro", "Onza"].index(
                                       st.session_state.catalogo.at[idx, 'Unidad']))
                if st.form_submit_button("Actualizar"):
                    st.session_state.catalogo.at[idx, 'Nombre'] = n_n
                    st.session_state.catalogo.at[idx, 'Unidad'] = n_u
                    guardar()
                    st.success("Actualizado")
                    st.rerun()
    st.dataframe(st.session_state.catalogo, use_container_width=True, hide_index=True)

elif opid == "inv":
    # CORRECCION BUG 2: usar la funcion centralizada
    recalcular_ingredientes()

    tab1, tab2, tab3 = st.tabs(["Registrar/Editar Compra",
                                 "Gestionar Historial/Inventario",
                                 "Kardex Detallado"])

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
                u_act = df_cat.iloc[0]['Unidad']
                nom_p = df_cat.iloc[0]['Nombre']

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
                    st.session_state.historial['No_Factura'] != f_num]
                for it in st.session_state.factura_temporal:
                    nueva_f = pd.DataFrame([{**it, "Fecha_Factura": f_fecha, "No_Factura": f_num}])
                    st.session_state.historial = pd.concat(
                        [st.session_state.historial, nueva_f], ignore_index=True)
                guardar()
                st.session_state.factura_temporal = []
                st.success(f"Exito! La Factura {f_num} ha sido agregada al inventario correctamente.")
                st.rerun()

            if col_b2.button("Cancelar Factura", use_container_width=True):
                st.session_state.factura_temporal = []
                st.rerun()

    with tab2:
        st.markdown("### Inventario Fisico Real")
        if not st.session_state.ingredientes.empty:
            df_vis = st.session_state.ingredientes.copy()
            df_vis['Valor_Total'] = df_vis['Stock'] * df_vis['Costo_Unitario']
            st.dataframe(df_vis.rename(columns={'Costo_Unitario': 'Costo Prom.'}),
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
                df_hist = df_hist[df_hist['No_Factura'].astype(str).str.contains(busq_n, case=False)]
            if busq_f:
                df_hist = df_hist[pd.to_datetime(df_hist['Fecha_Factura']).dt.date == busq_f]

            for n_f, grp in df_hist.groupby("No_Factura"):
                with st.expander(
                    f"Factura: {n_f} | Fecha: {grp.iloc[0]['Fecha_Factura']} | "
                    f"Total: L. {grp['Costo_Total'].sum():.2f}"):
                    st.dataframe(grp[['Codigo', 'Producto', 'Cantidad', 'Costo_Unitario', 'Costo_Total']],
                                 hide_index=True)
                    c_ed1, c_ed2, c_ed3 = st.columns([0.3, 0.4, 0.3])

                    if c_ed1.button(f"Modificar", key=f"mod_{n_f}"):
                        st.session_state.factura_temporal = grp[
                            ['Codigo', 'Producto', 'Unidad', 'Cantidad', 'Costo_Unitario', 'Costo_Total']
                        ].to_dict('records')
                        st.info("Cargado en 'Registrar'. Haga sus cambios y guarde.")

                    confirmar = c_ed2.checkbox(f"Confirmar eliminar {n_f}", key=f"chk_{n_f}")
                    if c_ed3.button(f"ELIMINAR", key=f"del_{n_f}",
                                    type="secondary", disabled=not confirmar):
                        st.session_state.historial = st.session_state.historial[
                            st.session_state.historial['No_Factura'] != n_f]
                        guardar()
                        st.rerun()

    with tab3:
        st.subheader("Kardex Detallado por Producto")
        # CORRECCION BUG 3: op_p definido localmente para evitar error de variable no definida
        op_p_k = ["SELECCIONE PRODUCTO"] + [f"{r['Codigo']} - {r['Nombre']}"
                                              for _, r in st.session_state.catalogo.iterrows()]
        insumo_k = st.selectbox("Seleccione Producto:", op_p_k, key="k_p_sel")

        if insumo_k != "SELECCIONE PRODUCTO":
            c_k   = insumo_k.split(" - ")[0].zfill(3)
            # Obtener unidad del catalogo directamente
            df_cat_k = st.session_state.catalogo[
                st.session_state.catalogo['Codigo'].astype(str).str.zfill(3) == c_k]
            u_kardex = df_cat_k.iloc[0]['Unidad'] if not df_cat_k.empty else "---"

            m_ent = st.session_state.historial[
                st.session_state.historial['Codigo'].astype(str).str.zfill(3) == c_k].copy()

            m_sal = pd.DataFrame()
            if 'historial_prod' in st.session_state and not st.session_state.historial_prod.empty:
                sal_rows = []
                for _, fila_prod in st.session_state.historial_prod.iterrows():
                    try:
                        insumos = ast.literal_eval(str(fila_prod['Detalle']))
                        for ins in insumos:
                            if str(ins['Codigo']).zfill(3) == c_k:
                                sal_rows.append({
                                    'Fecha': fila_prod['Fecha'],
                                    'Ref':   f"PROD {fila_prod['ID']} - {fila_prod['Plato']}",
                                    'Cantidad':      float(ins['Cantidad']) * float(fila_prod['Cantidad']),
                                    'Costo_Unitario': float(ins.get('Costo_U', 0))
                                })
                    except Exception:
                        pass
                if sal_rows:
                    m_sal = pd.DataFrame(sal_rows)

            k_list = []
            for _, r in m_ent.iterrows():
                k_list.append({'Fecha': r['Fecha_Factura'],
                                'Ref': f"Fact: {r['No_Factura']}",
                                'E': float(r['Cantidad']),
                                'S': 0.0,
                                'Total': float(r['Costo_Total'])})
            for _, r in m_sal.iterrows():
                k_list.append({'Fecha': r['Fecha'],
                                'Ref':  r['Ref'],
                                'E':    0.0,
                                'S':    float(r['Cantidad']),
                                'Total': -(float(r['Cantidad']) * float(r.get('Costo_Unitario', 0)))})

            if k_list:
                df_k = pd.DataFrame(k_list)
                # CORRECCION: normalizar fechas a datetime para poder ordenar
                # (Historial guarda Timestamp, Produccion guarda string)
                df_k['Fecha'] = pd.to_datetime(df_k['Fecha'], errors='coerce')
                df_k = df_k.sort_values('Fecha')
                stock_a, valor_a, filas = 0.0, 0.0, []
                for _, m in df_k.iterrows():
                    stock_a += (m['E'] - m['S'])
                    valor_a += m['Total']
                    filas.append({
                        'Fecha':     m['Fecha'],
                        'Ref':       m['Ref'],
                        'Unidad':    u_kardex,
                        'Entrada':   m['E'],
                        'Salida':    m['S'],
                        'Existencia': stock_a,
                        'C. Prom':   valor_a / stock_a if stock_a > 0 else 0,
                        'V. Total':  valor_a
                    })

                final_k = pd.DataFrame(filas)
                st.dataframe(final_k, hide_index=True, use_container_width=True)

                import io
                output = io.BytesIO()
                with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                    final_k.to_excel(writer, index=False, sheet_name='Kardex')
                st.download_button("Descargar Kardex a Excel", output.getvalue(), f"Kardex_{c_k}.xlsx")
            else:
                st.info("No hay movimientos registrados para este producto.")

elif opid == "rec":
    t_crear, t_ver = st.tabs(["Crear / Editar Receta", "Ver Recetario"])

    if 'edit_rec_data' not in st.session_state:
        st.session_state.edit_rec_data = None

    with t_crear:
        st.subheader("Configuracion de Plato")
        val_nombre, val_precio, val_margen, val_insumos = "", 0.0, 70.0, []

        if st.session_state.edit_rec_data:
            val_nombre = st.session_state.edit_rec_data['Plato']
            val_precio = float(st.session_state.edit_rec_data['Precio_Venta'])
            val_margen = float(st.session_state.edit_rec_data['Margen_Objetivo'] * 100)
            try:
                items_edit = ast.literal_eval(st.session_state.edit_rec_data['Detalle_Receta'])
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
                            items_e = ast.literal_eval(st.session_state.edit_rec_data['Detalle_Receta'])
                            for ie in items_e:
                                if str(ie['Codigo']).zfill(3) == str(datos['Codigo']).zfill(3):
                                    val_cant = float(ie['Cantidad'])
                        except Exception:
                            pass

                    col1, col2, col3, col4 = st.columns(4)
                    with col1: st.markdown(f"**{datos['Ingrediente']}**")
                    with col2: cant_rec = st.number_input(f"Cant ({datos['Unidad']})",
                                                           min_value=0.01, step=0.1,
                                                           value=val_cant,
                                                           key=f"q_{datos['Codigo']}")
                    with col3: st.write(f"Costo P: L.{datos['Costo_Unitario']:.2f}")
                    with col4:
                        subt = cant_rec * datos['Costo_Unitario']
                        st.write(f"Sub: L.{subt:.2f}")
                    costo_materia_prima += subt
                    detalle_final.append({"Codigo": datos['Codigo'], "Nombre": datos['Ingrediente'],
                                          "Cantidad": cant_rec, "Costo_U": datos['Costo_Unitario'],
                                          "Subtotal": subt})

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
                                st.session_state.recetas['Plato'] != n_plato]
                        nueva_rec = pd.DataFrame([{
                            "Plato": n_plato, "Detalle_Receta": str(detalle_final),
                            "Costo_Total_Plato": costo_materia_prima,
                            "Precio_Venta": p_venta, "Valor_Utilidad": val_utilidad,
                            "Margen_Utilidad": porc_utilidad, "Margen_Objetivo": m_objetivo
                        }])
                        st.session_state.recetas = pd.concat(
                            [st.session_state.recetas, nueva_rec], ignore_index=True)
                        guardar()
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
                    items = ast.literal_eval(r['Detalle_Receta'])
                    st.table(pd.DataFrame(items)[['Nombre', 'Cantidad', 'Costo_U', 'Subtotal']])

                    st.markdown(f"""
                    **RESUMEN:** Precio Venta: **L.{r['Precio_Venta']:.2f}** |
                    Costo Total: **L.{r['Costo_Total_Plato']:.2f}** |
                    Utilidad: **L.{r['Valor_Utilidad']:.2f}** |
                    Margen Real: **{r['Margen_Utilidad']*100:.1f}%** |
                    Margen Obj: **{r['Margen_Objetivo']*100:.1f}%**
                    """)

                    st.write("---")
                    c1, c2 = st.columns(2)

                    if c1.button(f"Editar {r['Plato']}", key=f"btn_edit_{idx}"):
                        st.session_state.edit_rec_data = r.to_dict()
                        st.success(f"Datos de '{r['Plato']}' cargados. "
                                   "Por favor, regrese a la pestana 'Crear / Editar Receta'.")

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
                            guardar()
                            st.session_state[f"confirm_del_rec_{idx}"] = False
                            st.rerun()
                        if col_no.button("Cancelar", key=f"conf_no_rec_{idx}"):
                            st.session_state[f"confirm_del_rec_{idx}"] = False
                            st.rerun()
        else:
            st.info("No hay recetas registradas.")

elif opid == "prod":
    t_orden, t_hist_prod = st.tabs(["Generar Orden de Produccion", "Historial de Produccion"])

    # historial_prod ya se carga en cargar_datos(); este bloque es solo fallback
    if 'historial_prod' not in st.session_state:
        st.session_state.historial_prod = pd.DataFrame(columns=["Fecha", "ID", "Plato", "Cantidad", "Detalle"])

    with t_orden:
        st.subheader("Nueva Orden de Produccion")
        if st.session_state.recetas.empty:
            st.warning("No hay recetas creadas. Vaya al modulo 'Crear Receta' primero.")
        else:
            # Recalcular stock antes de mostrar disponibilidad
            recalcular_ingredientes()

            with st.container(border=True):
                c_p1, c_p2 = st.columns(2)
                lista_platos = st.session_state.recetas['Plato'].tolist()
                plato_p = c_p1.selectbox("Seleccione el Plato a Producir", [""] + lista_platos)
                cant_p  = c_p2.number_input("Cantidad de Platos/Porciones", min_value=1, step=1)

            if plato_p:
                receta_info    = st.session_state.recetas[st.session_state.recetas['Plato'] == plato_p].iloc[0]
                insumos_receta = ast.literal_eval(receta_info['Detalle_Receta'])

                resumen_descuento = []
                puede_procesar    = True

                for ins in insumos_receta:
                    total_necesario = float(ins['Cantidad']) * float(cant_p)
                    idx_inv    = st.session_state.ingredientes[
                        st.session_state.ingredientes['Codigo'] == ins['Codigo']].index
                    stock_actual = float(st.session_state.ingredientes.at[idx_inv[0], 'Stock']) \
                                   if not idx_inv.empty else 0.0

                    if stock_actual < total_necesario:
                        puede_procesar = False
                    resumen_descuento.append({
                        "Insumo":       ins['Nombre'],
                        "Necesario":    round(total_necesario, 4),
                        "Stock Actual": round(stock_actual, 4),
                        "Estado":       "OK" if stock_actual >= total_necesario else "Sin Stock"
                    })

                st.table(pd.DataFrame(resumen_descuento))

                if st.button("PROCESAR PRODUCCION", type="primary",
                             disabled=not puede_procesar, use_container_width=True):
                    id_prod   = f"PROD-{datetime.now().strftime('%H%M%S%f')[:13]}"
                    fecha_hoy = datetime.now().strftime("%Y-%m-%d %H:%M")

                    # 1. DESCONTAR STOCK EN TABLA MAESTRA
                    st.session_state.ingredientes['Stock'] = \
                        st.session_state.ingredientes['Stock'].astype(float)
                    for ins in insumos_receta:
                        total_n = float(ins['Cantidad']) * float(cant_p)
                        idx_i   = st.session_state.ingredientes[
                            st.session_state.ingredientes['Codigo'] == ins['Codigo']].index
                        if not idx_i.empty:
                            st.session_state.ingredientes.at[idx_i[0], 'Stock'] -= total_n

                    # 2. REGISTRAR EN HISTORIAL DE PRODUCCION
                    nueva_fila_prod = pd.DataFrame([{
                        "Fecha":    fecha_hoy,
                        "ID":       id_prod,
                        "Plato":    plato_p,
                        "Cantidad": cant_p,
                        "Detalle":  str(insumos_receta)
                    }])
                    st.session_state.historial_prod = pd.concat(
                        [st.session_state.historial_prod, nueva_fila_prod], ignore_index=True)

                    # 3. GUARDAR TODO (guardar() ya incluye la hoja Produccion)
                    guardar()
                    st.success(f"Produccion registrada. ID: {id_prod}")
                    st.balloons()
                    st.rerun()

    with t_hist_prod:
        st.subheader("Registro de Producciones")
        if not st.session_state.historial_prod.empty:
            busq = st.text_input("Buscar por plato:").upper()
            df_h = st.session_state.historial_prod.copy()
            if busq:
                df_h = df_h[df_h['Plato'].str.contains(busq)]

            for idx, row in df_h.iterrows():
                with st.expander(f"{row['Fecha']} | {row['Plato']} | Cant: {row['Cantidad']}"):
                    st.write(f"ID Operacion: {row['ID']}")

                    if st.button(f"Eliminar y Revertir Stock", key=f"del_p_{row['ID']}"):
                        ins_rev = ast.literal_eval(str(row['Detalle']))
                        for i_r in ins_rev:
                            total_r = float(i_r['Cantidad']) * float(row['Cantidad'])
                            idx_inv = st.session_state.ingredientes[
                                st.session_state.ingredientes['Codigo'] == i_r['Codigo']].index
                            if not idx_inv.empty:
                                st.session_state.ingredientes.at[idx_inv[0], 'Stock'] += total_r

                        st.session_state.historial_prod = \
                            st.session_state.historial_prod.drop(idx).reset_index(drop=True)
                        guardar()
                        st.warning("Produccion eliminada y stock restaurado.")
                        st.rerun()
        else:
            st.info("No hay registros de produccion.")

elif opid == "rep":
    st.subheader("Panel de Control y Analisis")

    # Asegurar stock actualizado antes de mostrar reportes
    recalcular_ingredientes()

    c1, c2, c3 = st.columns(3)
    with c1:
        total_inv = (st.session_state.ingredientes['Stock'] *
                     st.session_state.ingredientes['Costo_Unitario']).sum() \
                    if not st.session_state.ingredientes.empty else 0
        st.metric("Inversion en Bodega", f"L. {total_inv:,.2f}")
    with c2:
        st.metric("Recetas Activas", len(st.session_state.recetas))
    with c3:
        margen_prom = st.session_state.recetas['Margen_Utilidad'].mean() * 100 \
                      if not st.session_state.recetas.empty else 0
        st.metric("Margen Promedio", f"{margen_prom:.1f}%")

    st.markdown("---")
    col_izq, col_der = st.columns(2)

    with col_izq:
        st.write("### Alertas de Reabastecimiento")
        bajo_stock = st.session_state.ingredientes[
            st.session_state.ingredientes['Stock'] < 5].copy()

        if not bajo_stock.empty:
            st.warning(f"Hay {len(bajo_stock)} insumos por agotarse.")
            st.dataframe(bajo_stock[['Ingrediente', 'Stock', 'Unidad']],
                         hide_index=True, use_container_width=True)
        else:
            st.success("Todos los insumos tienen stock suficiente.")

        if not st.session_state.ingredientes.empty:
            import io
            buf_rep = io.BytesIO()
            df_descarga = bajo_stock if not bajo_stock.empty \
                else st.session_state.ingredientes[['Ingrediente', 'Stock', 'Unidad']]
            with pd.ExcelWriter(buf_rep, engine='xlsxwriter') as writer:
                df_descarga.to_excel(writer, index=False, sheet_name='Reporte_Inventario')

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
            top_platos = st.session_state.recetas.nlargest(5, 'Valor_Utilidad')
            st.bar_chart(data=top_platos, x="Plato", y="Valor_Utilidad", color="#2ecc71")
        else:
            st.info("No hay datos de recetas disponibles.")

    st.markdown("---")
    if not st.session_state.recetas.empty:
        with st.expander("Ver Detalle de Costeo"):
            df_rep_rec = st.session_state.recetas[
                ['Plato', 'Costo_Total_Plato', 'Precio_Venta', 'Valor_Utilidad', 'Margen_Utilidad']
            ].copy()
            df_rep_rec['Margen %'] = (df_rep_rec['Margen_Utilidad'] * 100).round(2)
            st.dataframe(
                df_rep_rec[['Plato', 'Costo_Total_Plato', 'Precio_Venta', 'Valor_Utilidad', 'Margen %']],
                hide_index=True, use_container_width=True)
