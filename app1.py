import streamlit as st
import pandas as pd
import folium
from folium.plugins import HeatMap
from streamlit_folium import st_folium
from urllib.parse import quote
import traceback

# =========================
# CONFIG GENERAL (DEBE IR PRIMERO)
# =========================
st.set_page_config(page_title="SERUR | Mapa de Ventas", layout="wide")

LOGO_URL = "http://serur.geepok.com/n3xt/system/cxc/consulta/portal/logo-serur.png"
PASSWORD = "Serur2026*"   # <-- CAMBIA AQUÍ

# CLIENTES (BASE)
SHEET_ID_CLIENTES = "13MWoCG2_KIuhP7NPFYnudbRx99PNTwgynBbwkArewz0"
SHEET_TAB_CLIENTES = "Hoja1"

# VENTAS POR MES
VENTAS_MESES = {
    "ENERO": {"sheet_id": "1UpYQT6ErO3Xj3xdZ36IYJPRR9uDRQw-eYui9B_Y-JwU", "tab": "Hoja1"},
    "FEBRERO": {"sheet_id": "1cPgQEFUx-6oId3-y3DAVwmwjaZozKu9L10D9uZnR7bE", "tab": "Hoja1"},
}

# NEGADOS + LISTA DE PRECIOS
SHEET_ID_NEGADOS = "12kXQRhkKS1ea5H60YGIFcWEFJ_qcKSoXSl3p59Hk7ck"
SHEET_TAB_NEGADOS = "Hoja1"

SHEET_ID_PRECIOS = "1u-e_R3AH9Qs9eiiWwbB5gJEvNFSxmaBZmjrGFtqT_8o"
SHEET_TAB_PRECIOS = "Hoja1"

IVA_FACTOR = 1.16

# =========================
# HELPERS
# =========================
def gviz_csv_url(sheet_id: str, tab: str) -> str:
    return f"https://docs.google.com/spreadsheets/d/{sheet_id}/gviz/tq?tqx=out:csv&sheet={quote(tab)}"

def to_num(s):
    return pd.to_numeric(s, errors="coerce").fillna(0)

def ensure_col(df_, col, default=""):
    if col not in df_.columns:
        df_[col] = default
    return df_

def clean_text(x):
    return str(x).strip() if pd.notnull(x) else ""

def make_color_map(values):
    palette = [
        "red","blue","green","purple","orange","darkred","cadetblue","darkgreen",
        "darkblue","pink","gray","black","lightblue","lightgreen","beige",
        "lightgray","darkpurple","lightred"
    ]
    uniq = list(pd.Series(values).dropna().astype(str).unique())
    return {v: palette[i % len(palette)] for i, v in enumerate(uniq)}

def radius_from_sale(sale, min_r=4, max_r=18):
    sale = float(sale) if sale else 0.0
    if sale <= 0:
        return min_r
    r = 4 + (sale ** 0.5) * 0.08
    return float(max(min_r, min(max_r, r)))

def pick_sku_col(df: pd.DataFrame):
    candidates = ["codigo", "código", "sku", "clave", "clave_art", "cve_art", "producto", "articulo", "artículo"]
    cols = {c.lower().strip(): c for c in df.columns}
    for c in candidates:
        if c.lower().strip() in cols:
            return cols[c.lower().strip()]
    return None

def normalize_int_series(s):
    x = pd.to_numeric(pd.Series(s), errors="coerce")
    return x.round(0).astype("Int64")

def safe_image(url: str, width: int = 180):
    try:
        st.image(url, width=width)
    except Exception:
        st.write("")

# =========================
# LOADERS
# =========================
@st.cache_data(ttl=300)
def load_clientes():
    df = pd.read_csv(gviz_csv_url(SHEET_ID_CLIENTES, SHEET_TAB_CLIENTES))
    df.columns = df.columns.str.strip().str.lower()

    df = ensure_col(df, "cve_cte", "")
    df = ensure_col(df, "latitud", None)
    df = ensure_col(df, "longitud", None)

    df = ensure_col(df, "vendedor", "")
    df.rename(columns={"vendedor": "vendedor_cliente"}, inplace=True)

    posibles = ["nombre cliente", "nombre_cliente", "cliente", "nombre"]
    col_nombre = next((c for c in posibles if c in df.columns), None)
    df["nombre"] = df[col_nombre].astype(str).fillna("").str.strip() if col_nombre else ""

    df["cve_cte"] = df["cve_cte"].astype(str).str.strip()
    df["vendedor_cliente"] = df["vendedor_cliente"].astype(str).str.strip()
    df["latitud"] = pd.to_numeric(df["latitud"], errors="coerce")
    df["longitud"] = pd.to_numeric(df["longitud"], errors="coerce")

    df = df.dropna(subset=["latitud", "longitud"])
    return df

@st.cache_data(ttl=300)
def load_ventas(sheet_id: str, tab: str):
    df = pd.read_csv(gviz_csv_url(sheet_id, tab))
    df.columns = df.columns.str.strip().str.lower()

    df = ensure_col(df, "cve_cte", "")
    df = ensure_col(df, "vendedor", "")
    df = ensure_col(df, "cve_vnd", None)
    df = ensure_col(df, "fecha", "")
    df = ensure_col(df, "especie", "")
    df = ensure_col(df, "total", 0)
    df = ensure_col(df, "cantidad", 0)
    df = ensure_col(df, "importe", 0)

    df["cve_cte"] = df["cve_cte"].astype(str).str.strip()
    df["vendedor"] = df["vendedor"].astype(str).str.strip()
    df["especie"] = df["especie"].astype(str).str.strip()
    df["fecha"] = pd.to_datetime(df.get("fecha"), errors="coerce", dayfirst=True)

    if "cve_vnd" in df.columns:
        df["cve_vnd"] = normalize_int_series(df["cve_vnd"])

    total_num = to_num(df["total"])
    if (total_num != 0).any():
        df["venta_sin_iva"] = total_num / IVA_FACTOR
    else:
        df["cantidad"] = to_num(df["cantidad"])
        df["importe"] = to_num(df["importe"])
        df["venta_sin_iva"] = df["cantidad"] * df["importe"]

    return df

@st.cache_data(ttl=300)
def load_precios_serur():
    """
    PRECIOS:
      tip_pre | cve_art | descri | precio | codigo_sat
    """
    df = pd.read_csv(gviz_csv_url(SHEET_ID_PRECIOS, SHEET_TAB_PRECIOS))
    df.columns = df.columns.str.strip().str.lower()

    required = {"cve_art", "precio"}
    if not required.issubset(set(df.columns)):
        return None, "No encontré columnas cve_art/precio en PRECIOS."

    df["cve_art"] = df["cve_art"].astype(str).str.strip()
    df["precio"] = pd.to_numeric(df["precio"], errors="coerce").fillna(0)

    # tip_pre=1
    if "tip_pre" in df.columns:
        df["tip_pre"] = pd.to_numeric(df["tip_pre"], errors="coerce").fillna(0).astype(int)
        if (df["tip_pre"] == 1).any():
            df = df[df["tip_pre"] == 1].copy()

    # traer descri si existe
    if "descri" not in df.columns:
        df["descri"] = ""

    # max precio por cve_art (y una descri cualquiera)
    df = df.sort_values(["cve_art", "precio"], ascending=[True, False])
    df = df.drop_duplicates(subset=["cve_art"], keep="first")[["cve_art", "precio", "descri"]].copy()

    return df, None

@st.cache_data(ttl=300)
def load_negados_serur():
    """
    NEGADOS:
      cve_vnd | folio | cve_art | (expression) | cve_alm
    donde (expression) = cantidad negada
    """
    df = pd.read_csv(gviz_csv_url(SHEET_ID_NEGADOS, SHEET_TAB_NEGADOS))
    df.columns = df.columns.str.strip().str.lower()

    if "cve_art" not in df.columns:
        return None, "No encontré cve_art en NEGADOS."
    if "(expression)" not in df.columns:
        return None, "No encontré (expression) en NEGADOS (ahí debe venir la cantidad negada)."
    if "cve_vnd" not in df.columns:
        return None, "No encontré cve_vnd (número de vendedor) en NEGADOS."

    df["cve_art"] = df["cve_art"].astype(str).str.strip()
    df["cant_negada"] = pd.to_numeric(df["(expression)"], errors="coerce").fillna(0)
    df["cve_vnd"] = normalize_int_series(df["cve_vnd"])

    return df[["cve_vnd", "cve_art", "cant_negada"]].copy(), None

def compute_negados_detail(ventas: pd.DataFrame, modo: str, vend_sel_str: list[str]):
    """
    Regresa:
      negado_total_valor, faltan_precios, detalle_df
    detalle_df columnas: cve_art, codigo, descri, cant_negada, precio, valor, pct
    """
    negados_df, err_neg = load_negados_serur()
    precios_df, err_pre = load_precios_serur()

    if err_neg or err_pre or negados_df is None or precios_df is None:
        return 0.0, 0, pd.DataFrame(), err_neg, err_pre

    # cve_vnd seleccionados
    if modo == "Todos":
        selected_cve_vnd = None  # global
    else:
        if "cve_vnd" in ventas.columns and ventas["cve_vnd"].notna().any():
            map_df = ventas[["vendedor", "cve_vnd"]].dropna().copy()
            map_df["vendedor"] = map_df["vendedor"].astype(str).str.strip()
            map_df["cve_vnd"] = normalize_int_series(map_df["cve_vnd"])
            selected_cve_vnd = sorted(
                map_df[map_df["vendedor"].isin(vend_sel_str)]["cve_vnd"].dropna().unique().tolist()
            )
        else:
            selected_cve_vnd = sorted(normalize_int_series(vend_sel_str).dropna().unique().tolist())

    dfn = negados_df.copy()
    if selected_cve_vnd is not None:
        dfn = dfn[dfn["cve_vnd"].isin(selected_cve_vnd)].copy()

    # sum por articulo
    dfn = dfn.groupby("cve_art", as_index=False)["cant_negada"].sum()

    # merge precios + descri
    dfn = dfn.merge(precios_df, on="cve_art", how="left")
    dfn["precio"] = pd.to_numeric(dfn["precio"], errors="coerce").fillna(0)
    if "descri" not in dfn.columns:
        dfn["descri"] = ""

    dfn["valor"] = dfn["cant_negada"] * dfn["precio"]

    negado_total = float(dfn["valor"].sum()) if not dfn.empty else 0.0
    dfn["pct"] = (dfn["valor"] / negado_total * 100) if negado_total > 0 else 0.0

    faltan_precios = int(((dfn["cant_negada"] > 0) & (dfn["precio"] <= 0)).sum())

    # columnas pedidas:
    # clave=cve_art, codigo (lo mismo), descripcion=descri, valor, %
    dfn = dfn.sort_values("valor", ascending=False).reset_index(drop=True)
    dfn["codigo"] = dfn["cve_art"]  # por si quieres separar después

    detalle = dfn[["cve_art", "codigo", "descri", "cant_negada", "precio", "valor", "pct"]].copy()
    return negado_total, faltan_precios, detalle, None, None

# =========================
# ESTADO
# =========================
if "auth_ok" not in st.session_state:
    st.session_state.auth_ok = False
if "view" not in st.session_state:
    st.session_state.view = "login"
if "mes" not in st.session_state:
    st.session_state.mes = "ENERO"

# filtros persistentes
for k, v in {
    "modo": "Todos",
    "vendedor_sel": [],
    "especie_sel": [],
    "heat": False,
    "show_no_sales": False,
    "max_no_sales": 1500,
    "solo_top": 0,
    "gray_fake_sale": 5000,
}.items():
    if k not in st.session_state:
        st.session_state[k] = v

# datos de detalle negados (cache en sesión)
if "negados_detalle" not in st.session_state:
    st.session_state.negados_detalle = pd.DataFrame()
if "negados_total_valor" not in st.session_state:
    st.session_state.negados_total_valor = 0.0
if "negados_err_neg" not in st.session_state:
    st.session_state.negados_err_neg = None
if "negados_err_pre" not in st.session_state:
    st.session_state.negados_err_pre = None
if "negados_faltan_precios" not in st.session_state:
    st.session_state.negados_faltan_precios = 0

# =========================
# LOGIN
# =========================
def login_screen():
    st.markdown(
        """
        <style>
        .login-box{
            max-width:360px; margin:10vh auto 0 auto; padding:22px 22px 26px 22px;
            border-radius:14px; background:rgba(255,255,255,0.05);
            border:1px solid rgba(255,255,255,0.12); text-align:center;
        }
        .login-box img{max-width:180px; margin:0 auto 14px auto;}
        .login-title{font-size:16px; font-weight:600; margin-bottom:6px;}
        .login-sub{font-size:13px; opacity:0.75; margin-bottom:16px;}
        </style>
        """,
        unsafe_allow_html=True
    )
    st.markdown('<div class="login-box">', unsafe_allow_html=True)
    safe_image(LOGO_URL, width=180)
    st.markdown('<div class="login-title">Dashboard de Ventas</div>', unsafe_allow_html=True)
    st.markdown('<div class="login-sub">Acceso con contraseña</div>', unsafe_allow_html=True)

    pw = st.text_input("Contraseña", type="password", label_visibility="collapsed", placeholder="Contraseña")

    if st.button("Entrar", width="stretch"):
        if pw == PASSWORD:
            st.session_state.auth_ok = True
            st.session_state.view = "menu"
            st.rerun()
        else:
            st.error("Contraseña incorrecta")

    st.markdown("</div>", unsafe_allow_html=True)

# =========================
# MENU
# =========================
def menu_screen():
    safe_image(LOGO_URL, width=200)
    st.title("Menú principal")
    st.caption("Elige el mes para ver el mapa y KPIs.")

    col1, col2, col3 = st.columns([1, 1, 2])
    with col1:
        if st.button("📌 ENERO", width="stretch"):
            st.session_state.mes = "ENERO"
            st.session_state.view = "dashboard"
            st.rerun()
    with col2:
        if st.button("📌 FEBRERO", width="stretch"):
            st.session_state.mes = "FEBRERO"
            st.session_state.view = "dashboard"
            st.rerun()
    with col3:
        if st.button("🚪 Cerrar sesión", width="stretch"):
            st.session_state.auth_ok = False
            st.session_state.view = "login"
            st.rerun()

# =========================
# VISTA DETALLE NEGADOS
# =========================
def negados_screen():
    safe_image(LOGO_URL, width=170)
    top1, top2 = st.columns([1, 3])
    with top1:
        if st.button("⬅ Regresar al dashboard", width="stretch"):
            st.session_state.view = "dashboard"
            st.rerun()
    with top2:
        st.title(f"Detalle de Negados | {st.session_state.mes}")

    total = float(st.session_state.get("negados_total_valor", 0.0))
    faltan = int(st.session_state.get("negados_faltan_precios", 0))
    errn = st.session_state.get("negados_err_neg")
    errp = st.session_state.get("negados_err_pre")

    c1, c2 = st.columns([1, 2])
    with c1:
        st.metric("Total Negado", f"${total:,.2f}")
    with c2:
        if faltan > 0:
            st.caption(f"⚠️ {faltan:,} renglones negados quedaron sin precio (precio=0).")

    if errn:
        st.error(f"NEGADOS: {errn}")
    if errp:
        st.error(f"PRECIOS: {errp}")

    df = st.session_state.get("negados_detalle", pd.DataFrame()).copy()
    if df is None or df.empty:
        st.warning("No hay detalle para mostrar con los filtros actuales.")
        return

    st.divider()

    bus = st.text_input("Buscar (clave/código/descri)", value="", placeholder="Ej: 715 o CERRADURA")
    dff = df.copy()
    if bus.strip():
        b = bus.strip().lower()
        dff = dff[
            dff["cve_art"].astype(str).str.lower().str.contains(b, na=False) |
            dff["codigo"].astype(str).str.lower().str.contains(b, na=False) |
            dff["descri"].astype(str).str.lower().str.contains(b, na=False)
        ].copy()

    # salida pedida: clave, codigo, descripcion, valor, % del total (y ordenado)
    out = dff.sort_values("valor", ascending=False).copy()
    out = out.rename(columns={"cve_art": "clave", "descri": "descripcion", "pct": "%_del_total"})
    out["%_del_total"] = out["%_del_total"].fillna(0)

    st.dataframe(
        out[["clave", "codigo", "descripcion", "valor", "%_del_total"]].head(5000),
        width="stretch",
        hide_index=True,
        column_config={
            "valor": st.column_config.NumberColumn("valor", format="$ %0.2f"),
            "%_del_total": st.column_config.NumberColumn("% del total", format="%0.2f"),
        },
    )

# =========================
# DASHBOARD
# =========================
def dashboard_screen(mes: str):
    cfg = VENTAS_MESES[mes]

    with st.spinner("Cargando datos..."):
        ventas = load_ventas(cfg["sheet_id"], cfg["tab"])
        clientes = load_clientes()

    safe_image(LOGO_URL, width=170)
    topbar1, topbar2 = st.columns([1, 3])
    with topbar1:
        if st.button("⬅ Regresar al menú", width="stretch"):
            st.session_state.view = "menu"
            st.rerun()
    with topbar2:
        st.title(f"Mapa de Ventas | {mes}")

    vendedores = sorted([v for v in ventas["vendedor"].dropna().unique().tolist() if clean_text(v) != ""])
    if not vendedores:
        st.error("No se encontraron vendedores en VENTAS.")
        st.stop()

    especies = sorted([e for e in ventas["especie"].dropna().unique().tolist() if clean_text(e) != ""])

    c1, c2, c3, c4, c5 = st.columns([2.4, 2.8, 1.6, 2.6, 2.0])
    with c1:
        st.session_state.modo = st.radio("Vendedores", ["Todos", "Elegir"], horizontal=True, index=0 if st.session_state.modo=="Todos" else 1)
    with c2:
        st.session_state.especie_sel = st.multiselect("Especie(s) (opcional)", options=especies, default=st.session_state.especie_sel)
    with c3:
        st.session_state.heat = st.checkbox("Heatmap", value=st.session_state.heat)
    with c4:
        st.session_state.show_no_sales = st.checkbox("Mostrar clientes sin compra (del vendedor)", value=st.session_state.show_no_sales)
    with c5:
        st.session_state.max_no_sales = st.slider("Máx sin compra", 0, 10000, int(st.session_state.max_no_sales), 250, disabled=not st.session_state.show_no_sales)

    if st.session_state.modo == "Todos":
        st.session_state.vendedor_sel = vendedores
    else:
        # asegura defaults válidos
        default_v = st.session_state.vendedor_sel if st.session_state.vendedor_sel else vendedores
        st.session_state.vendedor_sel = st.multiselect("Vendedor(es)", options=vendedores, default=default_v)

    st.session_state.solo_top = st.number_input("Top clientes con venta (0=todos)", min_value=0, value=int(st.session_state.solo_top), step=50)

    st.session_state.gray_fake_sale = st.number_input(
        "Tamaño de gris (monto ficticio)",
        min_value=1000, value=int(st.session_state.gray_fake_sale), step=500,
        disabled=not st.session_state.show_no_sales
    )

    vend_sel_str = [str(x).strip() for x in st.session_state.vendedor_sel]
    dfv = ventas[ventas["vendedor"].isin(vend_sel_str)].copy()
    if st.session_state.especie_sel:
        dfv = dfv[dfv["especie"].isin([str(x) for x in st.session_state.especie_sel])]

    # SKUs únicos (solo 1 vendedor seleccionado)
    sku_unicos = None
    mostrar_skus = (st.session_state.modo == "Elegir" and isinstance(st.session_state.vendedor_sel, list) and len(st.session_state.vendedor_sel) == 1)
    if mostrar_skus and not dfv.empty:
        sku_col = pick_sku_col(dfv)
        if sku_col:
            sku_unicos = int(dfv[sku_col].astype(str).str.strip().replace("", pd.NA).dropna().nunique())

    # Agregación para mapa
    if not dfv.empty:
        grp = dfv.groupby(["cve_cte", "vendedor"], as_index=False).agg(
            venta_sin_iva=("venta_sin_iva", "sum"),
            especies=("especie", lambda s: ", ".join(sorted(pd.Series(s).astype(str).unique().tolist())[:10])),
            renglones=("especie", "count"),
        )
    else:
        grp = pd.DataFrame(columns=["cve_cte","vendedor","venta_sin_iva","especies","renglones"])

    df_sales = grp.merge(clientes, on="cve_cte", how="left").dropna(subset=["latitud","longitud"])

    if "vendedor" not in df_sales.columns:
        if "vendedor_x" in df_sales.columns:
            df_sales.rename(columns={"vendedor_x": "vendedor"}, inplace=True)
        elif "vendedor_y" in df_sales.columns:
            df_sales.rename(columns={"vendedor_y": "vendedor"}, inplace=True)

    if st.session_state.solo_top and st.session_state.solo_top > 0 and not df_sales.empty:
        df_sales = df_sales.sort_values("venta_sin_iva", ascending=False).head(int(st.session_state.solo_top))

    ventas_ctes = set(df_sales["cve_cte"].astype(str).tolist()) if not df_sales.empty else set()

    # Clientes scope (sin compra)
    clientes_scope = clientes.copy() if st.session_state.modo == "Todos" else clientes[clientes["vendedor_cliente"].isin(vend_sel_str)].copy()

    df_no_sales_all = clientes_scope[~clientes_scope["cve_cte"].astype(str).isin(ventas_ctes)].copy()
    df_no_sales = df_no_sales_all
    if st.session_state.show_no_sales and st.session_state.max_no_sales > 0 and len(df_no_sales) > st.session_state.max_no_sales:
        df_no_sales = df_no_sales.head(int(st.session_state.max_no_sales))

    # KPIs ventas
    venta_total = float(df_sales["venta_sin_iva"].sum()) if not df_sales.empty else 0.0
    clientes_con_venta = int(df_sales["cve_cte"].nunique()) if not df_sales.empty else 0
    ticket_prom = (venta_total / clientes_con_venta) if clientes_con_venta else 0.0
    clientes_asignados = int(clientes_scope["cve_cte"].nunique())
    cobertura = (clientes_con_venta / clientes_asignados * 100) if clientes_asignados else 0.0

    # NEGADOS + detalle
    negado_valor, faltan_precios, detalle, err_neg, err_pre = compute_negados_detail(
        ventas=ventas,
        modo=st.session_state.modo,
        vend_sel_str=vend_sel_str
    )
    pct_negado_vs_vendido = (negado_valor / venta_total * 100) if venta_total > 0 else 0.0

    # guarda detalle en sesión para vista aparte
    st.session_state.negados_detalle = detalle
    st.session_state.negados_total_valor = float(negado_valor)
    st.session_state.negados_faltan_precios = int(faltan_precios)
    st.session_state.negados_err_neg = err_neg
    st.session_state.negados_err_pre = err_pre

    # KPIs (negados con botón "Ver detalle")
    if mostrar_skus:
        k1, k2, k3, k4, k5 = st.columns(5)
        k1.metric("Venta sin IVA", f"${venta_total:,.2f}")
        k2.metric("Clientes con venta", f"{clientes_con_venta:,}")
        k3.metric("Ticket prom.", f"${ticket_prom:,.2f}")
        k4.metric("Cobertura", f"{cobertura:,.1f}%")
        k5.metric("SKUs únicos (vendidos)", "N/D" if sku_unicos is None else f"{sku_unicos:,}")
    else:
        k1, k2, k3, k4 = st.columns(4)
        k1.metric("Venta sin IVA", f"${venta_total:,.2f}")
        k2.metric("Clientes con venta", f"{clientes_con_venta:,}")
        k3.metric("Ticket prom.", f"${ticket_prom:,.2f}")
        k4.metric("Cobertura", f"{cobertura:,.1f}%")

    n1, n2, n3 = st.columns([1.2, 1.2, 1.0])
    with n1:
        st.metric("$ Negado", f"${negado_valor:,.2f}")
    with n2:
        st.metric("% Negado vs Vendido", f"{pct_negado_vs_vendido:,.2f}%")
    with n3:
        if st.button("📋 Ver detalle", width="stretch"):
            st.session_state.view = "negados"
            st.rerun()

    if err_neg:
        st.caption(f"⚠️ NEGADOS: {err_neg}")
    if err_pre:
        st.caption(f"⚠️ PRECIOS: {err_pre}")
    if faltan_precios > 0:
        st.caption(f"⚠️ {faltan_precios:,} renglones negados quedaron sin precio (precio=0). Revisa lista de precios.")

    st.divider()

    # MAPA
    base_for_center = df_sales if not df_sales.empty else clientes_scope if not clientes_scope.empty else clientes
    center = [base_for_center["latitud"].mean(), base_for_center["longitud"].mean()]
    m = folium.Map(location=center, zoom_start=11, tiles="OpenStreetMap")

    layer_sales = folium.FeatureGroup(name="Clientes con venta")
    layer_gray = folium.FeatureGroup(name="Clientes sin compra (del vendedor)")
    layer_heat = folium.FeatureGroup(name="Heatmap")

    color_map = make_color_map(df_sales["vendedor"]) if not df_sales.empty else {}

    if not df_sales.empty:
        for _, r in df_sales.iterrows():
            vend = clean_text(r.get("vendedor", ""))
            venta = float(r.get("venta_sin_iva", 0) or 0.0)
            lat = float(r["latitud"]); lon = float(r["longitud"])
            cve = clean_text(r.get("cve_cte",""))
            nombre = clean_text(r.get("nombre",""))
            label = f"{cve} - {nombre}" if nombre else f"{cve} - SIN NOMBRE"

            popup_html = f"""
            <b>Cliente:</b> {label}<br>
            <b>Vendedor:</b> {vend}<br>
            <b>Venta sin IVA:</b> ${venta:,.2f}
            """

            folium.CircleMarker(
                location=[lat, lon],
                radius=radius_from_sale(venta),
                color=color_map.get(vend, "blue"),
                fill=True,
                fill_opacity=0.75,
                popup=folium.Popup(popup_html, max_width=420),
                tooltip=folium.Tooltip(label, sticky=True),
            ).add_to(layer_sales)

    layer_sales.add_to(m)

    if st.session_state.show_no_sales and not df_no_sales.empty:
        gray_radius = radius_from_sale(st.session_state.gray_fake_sale, min_r=7, max_r=16)
        for _, r in df_no_sales.iterrows():
            lat = float(r["latitud"]); lon = float(r["longitud"])
            cve = clean_text(r.get("cve_cte",""))
            nombre = clean_text(r.get("nombre",""))
            label = f"{cve} - {nombre}" if nombre else f"{cve} - SIN NOMBRE"
            popup_html = f"<b>Cliente:</b> {label}<br><b>Sin compra</b> con los filtros actuales."

            folium.CircleMarker(
                location=[lat, lon],
                radius=gray_radius,
                color="gray",
                fill=True,
                fill_opacity=0.35,
                tooltip=folium.Tooltip(label, sticky=True),
                popup=folium.Popup(popup_html, max_width=360),
            ).add_to(layer_gray)

        layer_gray.add_to(m)

    if st.session_state.heat and not df_sales.empty:
        heat_data = df_sales[["latitud","longitud","venta_sin_iva"]].dropna()
        HeatMap(heat_data.values.tolist(), radius=18, blur=15, max_zoom=13).add_to(layer_heat)
        layer_heat.add_to(m)

    folium.LayerControl(collapsed=True).add_to(m)

    st.subheader("Mapa")
    st_folium(m, width="stretch", height=650)

    # TABLAS
    st.divider()

    st.subheader("Top clientes con venta (según filtros)")
    top_clientes = (
        df_sales.groupby(["cve_cte", "nombre"], as_index=False)["venta_sin_iva"]
        .sum()
        .sort_values("venta_sin_iva", ascending=False)
    )
    st.dataframe(
        top_clientes[["cve_cte", "nombre", "venta_sin_iva"]].head(200),
        width="stretch",
        hide_index=True,
        column_config={
            "venta_sin_iva": st.column_config.NumberColumn("venta_sin_iva", format="$ %0.2f"),
        }
    )

    st.subheader("Clientes sin compra (del vendedor filtrado)")
    bus = st.text_input("Buscar (nombre o clave)", value="", placeholder="Ej: FERNANDO o 7405")
    df_nc = df_no_sales_all.copy()

    if bus.strip():
        b = bus.strip().lower()
        df_nc = df_nc[
            df_nc["nombre"].astype(str).str.lower().str.contains(b, na=False) |
            df_nc["cve_cte"].astype(str).str.lower().str.contains(b, na=False)
        ]

    st.caption(f"Mostrando {len(df_nc):,} clientes sin compra (antes de limitar por mapa).")

    st.dataframe(
        df_nc[["cve_cte", "nombre", "vendedor_cliente", "latitud", "longitud"]].head(5000),
        width="stretch",
        hide_index=True,
        column_config={
            "latitud": st.column_config.NumberColumn("latitud", format="%0.6f"),
            "longitud": st.column_config.NumberColumn("longitud", format="%0.6f"),
        }
    )

# =========================
# ROUTER + PROTECCIÓN (evita pantalla negra)
# =========================
def main():
    if not st.session_state.auth_ok:
        st.session_state.view = "login"

    if st.session_state.view == "login":
        login_screen()
    elif st.session_state.view == "menu":
        menu_screen()
    elif st.session_state.view == "negados":
        negados_screen()
    else:
        dashboard_screen(st.session_state.mes)

try:
    main()
except Exception as e:
    st.error("Se cayó la app. Aquí está el error real:")
    st.code(traceback.format_exc())
