import streamlit as st
import pandas as pd
from urllib.parse import quote

# =========================
# LOGIN SIMPLE (PASSWORD)
# =========================
def check_password():
    PASSWORD = "Serur2026*"   # <-- CAMBIA AQUÍ LA CLAVE

    if "auth_ok" not in st.session_state:
        st.session_state.auth_ok = False

    if st.session_state.auth_ok:
        return True

    st.title("Acceso al Dashboard")
    st.caption("Ingresa la contraseña para continuar")

    pw = st.text_input("Contraseña", type="password")

    c1, c2 = st.columns([1, 5])
    with c1:
        entrar = st.button("Entrar")
    with c2:
        st.write("")

    if entrar:
        if pw == PASSWORD:
            st.session_state.auth_ok = True
            st.rerun()
        else:
            st.error("Contraseña incorrecta")

    return False

if not check_password():
    st.stop()

# =========================
# CONFIG (DESPUÉS DEL LOGIN)
# =========================
st.set_page_config(page_title="Margen Neto", layout="wide")

VENTAS_MESES = {
    "GENERAL": {
        "sheet_id": "1UpYQT6ErO3Xj3xdZ36IYJPRR9uDRQw-eYui9B_Y-JwU",
        "sheet_name": "Hoja1",
    },
    "ABRIL": {
        "sheet_id": "1O-3okgETzuLH-mBd9OoLPlA290GuAvmhOwKz3_T1dQ0",
        "sheet_name": "Hoja1",
    },
}

SHEET_ID_COMPRAS = "17X31u6slmVg--HSiL0AahdRSObvtVM0Q_KDd72EH-Ro"
SHEET_NAME_COMPRAS = "Hoja1"

# =========================
# HELPERS
# =========================
def to_num(s):
    return pd.to_numeric(s, errors="coerce").fillna(0)

def money_round(df_, cols, nd=2):
    for c in cols:
        if c in df_.columns:
            df_[c] = pd.to_numeric(df_[c], errors="coerce").fillna(0).round(nd)
    return df_

def int_round(df_, cols):
    for c in cols:
        if c in df_.columns:
            df_[c] = pd.to_numeric(df_[c], errors="coerce").fillna(0).round(0).astype(int)
    return df_

def ensure_col(df_, col, default=""):
    if col not in df_.columns:
        df_[col] = default
    return df_

def safe_unique(df_, col):
    if col not in df_.columns:
        return []
    return sorted([x for x in df_[col].dropna().unique().tolist() if str(x).strip() != ""])

# =========================
# LOADERS
# =========================
@st.cache_data(ttl=120)
def load_ventas(sheet_id, sheet_name):
    sheet = quote(sheet_name)
    url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/gviz/tq?tqx=out:csv&sheet={sheet}"
    df = pd.read_csv(url)
    df.columns = df.columns.str.strip().str.lower()

    df = ensure_col(df, "especie", "")
    df = ensure_col(df, "categoria", "")
    df = ensure_col(df, "articulo", "")

    df["fecha"] = pd.to_datetime(df.get("fecha"), errors="coerce", dayfirst=True)
    df["cantidad"] = to_num(df.get("cantidad"))
    df["importe"] = to_num(df.get("importe"))
    df["cos_rep"] = to_num(df.get("cos_rep"))

    df["venta_sin_iva"] = df["cantidad"] * df["importe"]
    df["costo"] = df["cantidad"] * df["cos_rep"]
    df["utilidad_neta"] = (df["venta_sin_iva"] - df["costo"]) * 0.93

    df = money_round(df, ["venta_sin_iva", "costo", "utilidad_neta"], 2)
    return df

@st.cache_data(ttl=120)
def load_compras():
    sheet = quote(SHEET_NAME_COMPRAS)
    url = f"https://docs.google.com/spreadsheets/d/{SHEET_ID_COMPRAS}/gviz/tq?tqx=out:csv&sheet={sheet}"
    c = pd.read_csv(url)
    c.columns = c.columns.str.strip().str.lower()

    c = ensure_col(c, "especie", "")
    c = ensure_col(c, "categoria", "")
    c = ensure_col(c, "articulo", "")
    c = ensure_col(c, "proveedor", "")

    c["fecha"] = pd.to_datetime(c.get("fecha"), errors="coerce", dayfirst=True)
    c["cantidad"] = to_num(c.get("cantidad"))
    c["importe"] = to_num(c.get("importe"))

    c["compras"] = c["cantidad"] * c["importe"]
    c = money_round(c, ["compras"], 2)
    return c

# =========================
# SELECTOR DE MES
# =========================
with st.sidebar:
    st.subheader("Origen de información")
    mes_sel = st.selectbox("Mes de ventas", list(VENTAS_MESES.keys()), index=0)

cfg_mes = VENTAS_MESES[mes_sel]

df = load_ventas(cfg_mes["sheet_id"], cfg_mes["sheet_name"])
dfc = load_compras()

# =========================
# HEADER + FILTRO FECHAS
# =========================
st.caption("Basado en información programa NEXT")
st.title("Utilidad y Margen NETO")
st.caption(f"Fuente de ventas seleccionada: {mes_sel}")

df_fechas = df.dropna(subset=["fecha"])

if df_fechas.empty:
    st.warning("La hoja de ventas seleccionada no trae fechas válidas.")
    st.stop()

min_d = df_fechas["fecha"].min().date()
max_d = df_fechas["fecha"].max().date()

c1, c2, _ = st.columns([2, 2, 6])
d_ini = c1.date_input("Desde", min_d, min_d, max_d)
d_fin = c2.date_input("Hasta", max_d, min_d, max_d)

df_f = df[(df["fecha"].dt.date >= d_ini) & (df["fecha"].dt.date <= d_fin)].copy()
dfc_f = dfc[(dfc["fecha"].dt.date >= d_ini) & (dfc["fecha"].dt.date <= d_fin)].copy()

# =========================
# FILTROS (SIDEBAR)
# =========================
with st.sidebar:
    st.subheader("Filtros")
    especies = safe_unique(df_f, "especie")
    especie_sel = st.selectbox("Especie", ["(Todas)"] + especies)

    categorias = safe_unique(df_f, "categoria")
    categoria_sel = st.selectbox("Categoría", ["(Todas)"] + categorias)

if especie_sel != "(Todas)":
    df_f = df_f[df_f["especie"] == especie_sel]
    dfc_f = dfc_f[dfc_f["especie"] == especie_sel]

if categoria_sel != "(Todas)":
    df_f = df_f[df_f["categoria"] == categoria_sel]
    dfc_f = dfc_f[dfc_f["categoria"] == categoria_sel]

st.divider()

# =========================
# KPIs
# =========================
venta = float(df_f["venta_sin_iva"].sum())
costo = float(df_f["costo"].sum())
util = float(df_f["utilidad_neta"].sum())
pzas = int(round(df_f["cantidad"].sum()))
margen = util / venta if venta else 0
compras = float(dfc_f["compras"].sum()) if "compras" in dfc_f.columns else 0.0

k1, k2, k3, k4, k5 = st.columns(5)
k1.metric("Venta sin IVA", f"${venta:,.2f}")
k2.metric("Costo", f"${costo:,.2f}")
k3.metric("Utilidad neta (-7%)", f"${util:,.2f}")
k4.metric("Margen neto %", f"{margen*100:,.2f}%")
k5.metric("Piezas", f"{pzas:,}")

b1, b2, b3, b4, b5 = st.columns(5)
b2.metric("Compras", f"${compras:,.2f}")

st.divider()

# =========================
# EXPLORADOR POR ESPECIE (CLICK -> DETALLE)
# =========================
if "especie_click" not in st.session_state:
    st.session_state.especie_click = None

st.subheader("Explorador por ESPECIE (clic para ver detalle)")

esp = (
    df_f.groupby("especie", as_index=False)
    .agg(
        utilidad=("utilidad_neta", "sum"),
        venta=("venta_sin_iva", "sum"),
        piezas=("cantidad", "sum"),
    )
)
esp["margen_pct"] = (esp["utilidad"] / esp["venta"]).fillna(0)
esp = money_round(esp, ["venta", "utilidad"], 2)
esp = int_round(esp, ["piezas"])
esp = esp.sort_values("utilidad", ascending=False).reset_index(drop=True)

cols = st.columns(5)
for pos, row in esp.iterrows():
    with cols[pos % 5]:
        label = (
            f"{row['especie']}\n\n"
            f"Margen: {row['margen_pct']*100:,.2f}%  "
            f"Utilidad: ${row['utilidad']:,.0f}"
        )
        if st.button(label, use_container_width=True, key=f"esp_{pos}"):
            st.session_state.especie_click = row["especie"]
            st.rerun()

c_clear, _ = st.columns([2, 8])
if c_clear.button("Limpiar selección", use_container_width=True):
    st.session_state.especie_click = None
    st.rerun()

# =========================
# DETALLE POR ESPECIE (PRODUCTOS)
# =========================
if st.session_state.especie_click:
    st.divider()
    esp_sel = st.session_state.especie_click
    st.subheader(f"Detalle de especie: {esp_sel}")

    dfx = df_f[df_f["especie"] == esp_sel].copy()

    prod = (
        dfx.groupby("articulo", as_index=False)
        .agg(
            piezas=("cantidad", "sum"),
            venta_sin_iva=("venta_sin_iva", "sum"),
            costo=("costo", "sum"),
            utilidad_neta=("utilidad_neta", "sum"),
        )
    )
    prod["margen_pct"] = (prod["utilidad_neta"] / prod["venta_sin_iva"]).fillna(0)

    prod = money_round(prod, ["venta_sin_iva", "costo", "utilidad_neta"], 2)
    prod = int_round(prod, ["piezas"])

    if not prod.empty:
        top_pzas = prod.sort_values("piezas", ascending=False).head(1)
        top_venta = prod.sort_values("venta_sin_iva", ascending=False).head(1)
        top_util = prod.sort_values("utilidad_neta", ascending=False).head(1)
        top_margen = prod.sort_values("margen_pct", ascending=False).head(1)

        cA, cB, cC, cD = st.columns(4)
        cA.metric("Más vendido (pzas)", str(top_pzas.iloc[0]["articulo"]), f'{int(top_pzas.iloc[0]["piezas"]):,} pzas')
        cB.metric("Mayor venta", str(top_venta.iloc[0]["articulo"]), f'${float(top_venta.iloc[0]["venta_sin_iva"]):,.2f}')
        cC.metric("Mayor utilidad", str(top_util.iloc[0]["articulo"]), f'${float(top_util.iloc[0]["utilidad_neta"]):,.2f}')
        cD.metric("Mejor margen %", str(top_margen.iloc[0]["articulo"]), f'{float(top_margen.iloc[0]["margen_pct"])*100:,.2f}%')

        st.divider()
        t1, t2, t3, t4 = st.tabs(["Top 20 por Utilidad", "Top 20 por Venta", "Top 20 por Piezas", "Tabla completa"])

        def show_table(data, h=560):
            st.data_editor(
                data,
                hide_index=True,
                disabled=True,
                height=h,
                column_config={
                    "piezas": st.column_config.NumberColumn("Piezas", format="%,.0f"),
                    "venta_sin_iva": st.column_config.NumberColumn("Venta sin IVA", format="$%,.2f"),
                    "costo": st.column_config.NumberColumn("Costo", format="$%,.2f"),
                    "utilidad_neta": st.column_config.NumberColumn("Utilidad neta", format="$%,.2f"),
                    "margen_pct": st.column_config.NumberColumn("Margen %", format="%.2f%%"),
                }
            )

        with t1:
            show_table(prod.sort_values("utilidad_neta", ascending=False).head(20))
        with t2:
            show_table(prod.sort_values("venta_sin_iva", ascending=False).head(20))
        with t3:
            show_table(prod.sort_values("piezas", ascending=False).head(20))
        with t4:
            show_table(prod.sort_values("utilidad_neta", ascending=False), h=650)
    else:
        st.info("No hay detalle para la especie seleccionada en el rango de fechas.")

# =========================
# MARGEN POR PROVEEDOR
# =========================
st.divider()
st.subheader("Margen por proveedor")

if "proveedor" not in dfc_f.columns or dfc_f["proveedor"].astype(str).str.strip().eq("").all():
    st.info("Para ver esta sección, tu hoja de COMPRAS debe traer una columna llamada 'proveedor'.")
else:
    prov = (
        dfc_f.groupby("proveedor", as_index=False)
        .agg(
            compras=("compras", "sum"),
            cantidad=("cantidad", "sum")
        )
    )
    prov = money_round(prov, ["compras"], 2)
    prov = int_round(prov, ["cantidad"])
    prov = prov.sort_values("compras", ascending=False).reset_index(drop=True)

    st.data_editor(
        prov,
        hide_index=True,
        disabled=True,
        height=420,
        column_config={
            "compras": st.column_config.NumberColumn("Compras", format="$%,.2f"),
            "cantidad": st.column_config.NumberColumn("Piezas compradas", format="%,.0f"),
        }
    )

# =========================
# REFRESH
# =========================
st.button("Actualizar ahora", on_click=st.cache_data.clear)
st.caption("Dashboard protegido con contraseña")
