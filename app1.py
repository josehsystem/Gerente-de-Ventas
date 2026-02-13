import streamlit as st
import pandas as pd
import folium
from folium.plugins import HeatMap
from streamlit_folium import st_folium
from urllib.parse import quote
import traceback

# =========================
# CONFIG GENERAL
# =========================
st.set_page_config(page_title="SERUR | Mapa de Ventas", layout="wide")

LOGO_URL = "https://serur.com.mx/wp-content/uploads/2025/11/SERUR-6.webp"
LOGO_FALLBACK = "https://serur.com.mx/wp-content/uploads/2025/11/SERUR-6.webp"
PASSWORD = "Serur2026*"

ACCENT = "#0d3b82"
ACCENT_HOVER = "#0b2f68"

# =========================
# CSS GLOBAL
# =========================
st.markdown(
    f"""
<style>
.block-container{{ padding-top: 1.2rem; padding-bottom: 2rem; }}

div[data-testid="stAppViewContainer"] h1,
div[data-testid="stAppViewContainer"] h2,
div[data-testid="stAppViewContainer"] h3,
div[data-testid="stAppViewContainer"] h4,
div[data-testid="stAppViewContainer"] h5,
div[data-testid="stAppViewContainer"] h6 {{
  color: {ACCENT} !important;
  font-weight: 900 !important;
}}

div[data-testid="stAppViewContainer"] .stCaption {{
  color: rgba(13, 59, 130, 0.85) !important;
}}

div.stButton > button {{
  background: {ACCENT} !important;
  color: #fff !important;
  font-weight: 700 !important;
  border: 1px solid rgba(255,255,255,0.12) !important;
  border-radius: 10px !important;
  height: 44px !important;
  width: 100% !important;
  transition: all .12s ease-in-out !important;
}}
div.stButton > button:hover {{
  background: {ACCENT_HOVER} !important;
  transform: translateY(-1px) !important;
}}
div.stButton > button:active {{
  transform: translateY(0px) !important;
}}

[data-testid="stTextInput"] input,
[data-testid="stNumberInput"] input {{
  border-radius: 10px !important;
}}

.card {{
  border: 1px solid rgba(0,0,0,0.08);
  border-radius: 14px;
  padding: 14px 14px 12px 14px;
  background: rgba(255,255,255,0.70);
  box-shadow: 0 10px 24px rgba(0,0,0,0.06);
  height: 128px;
  overflow: hidden;
}}
.card .title {{
  font-weight: 900;
  font-size: 14px;
  line-height: 1.2;
  margin-bottom: 6px;
}}
.card .money {{
  font-weight: 900;
  font-size: 20px;
  margin-bottom: 4px;
}}
.card .meta {{
  font-size: 12px;
  opacity: 0.85;
}}
.badge {{
  display: inline-block;
  font-weight: 800;
  font-size: 11px;
  padding: 3px 8px;
  border-radius: 999px;
  background: rgba(13,59,130,0.10);
  color: {ACCENT};
  border: 1px solid rgba(13,59,130,0.18);
}}
</style>
""",
    unsafe_allow_html=True,
)

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

def safe_logo(width=220):
    try:
        st.image(LOGO_URL, width=width)
    except Exception:
        st.image(LOGO_FALLBACK, width=width)

def pareto_80_by_especie(df_sales: pd.DataFrame, threshold=0.80):
    if df_sales.empty:
        return pd.DataFrame(columns=["especie", "venta_sin_iva", "pct", "cum_pct", "is_80"])

    x = df_sales.groupby("especie", as_index=False).agg(venta_sin_iva=("venta_sin_iva", "sum"))
    x = x.sort_values("venta_sin_iva", ascending=False).reset_index(drop=True)

    total = float(x["venta_sin_iva"].sum()) if not x.empty else 0.0
    if total <= 0:
        x["pct"] = 0.0
        x["cum_pct"] = 0.0
        x["is_80"] = False
        return x

    x["pct"] = x["venta_sin_iva"] / total
    x["cum_pct"] = x["pct"].cumsum()
    x["is_80"] = x["cum_pct"] <= float(threshold)

    if (~x["is_80"]).any():
        idx = x.index[~x["is_80"]][0]
        x.loc[idx, "is_80"] = True

    return x

# =========================
# DATA SOURCES
# =========================
SHEET_ID_CLIENTES = "13MWoCG2_KIuhP7NPFYnudbRx99PNTwgynBbwkArewz0"
SHEET_TAB_CLIENTES = "Hoja1"

VENTAS_MESES = {
    "ENERO": {"sheet_id": "1UpYQT6ErO3Xj3xdZ36IYJPRR9uDRQw-eYui9B_Y-JwU", "tab": "Hoja1"},
    "FEBRERO": {"sheet_id": "1cPgQEFUx-6oId3-y3DAVwmwjaZozKu9L10D9uZnR7bE", "tab": "Hoja1"},
}

SHEET_ID_NEGADOS = "12kXQRhkKS1ea5H60YGIFcWEFJ_qcKSoXSl3p59Hk7ck"
SHEET_TAB_NEGADOS = "Hoja1"

SHEET_ID_PRECIOS = "1u-e_R3AH9Qs9eiiWwbB5gJEvNFSxmaBZmjrGFtqT_8o"
SHEET_TAB_PRECIOS = "Hoja1"

IVA_FACTOR = 1.16

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
    df = pd.read_csv(gviz_csv_url(SHEET_ID_PRECIOS, SHEET_TAB_PRECIOS))
    df.columns = df.columns.str.strip().str.lower()

    required = {"cve_art", "precio"}
    if not required.issubset(set(df.columns)):
        return None, "No encontré columnas cve_art/precio en PRECIOS."

    df["cve_art"] = df["cve_art"].astype(str).str.strip()
    df["precio"] = pd.to_numeric(df["precio"], errors="coerce").fillna(0)

    if "descri" not in df.columns:
        df["descri"] = ""

    if "tip_pre" in df.columns:
        df["tip_pre"] = pd.to_numeric(df["tip_pre"], errors="coerce").fillna(0).astype(int)
        if (df["tip_pre"] == 1).any():
            df = df[df["tip_pre"] == 1].copy()

    def pick_descri(s):
        s = s.astype(str).fillna("").str.strip()
        s = s[s != ""]
        return s.iloc[0] if len(s) else ""

    agg = df.groupby("cve_art", as_index=False).agg(
        precio=("precio", "max"),
        descri=("descri", pick_descri),
    )
    return agg, None

@st.cache_data(ttl=300)
def load_negados_serur():
    df = pd.read_csv(gviz_csv_url(SHEET_ID_NEGADOS, SHEET_TAB_NEGADOS))
    df.columns = df.columns.str.strip().str.lower()

    if "cve_art" not in df.columns:
        return None, "No encontré cve_art en NEGADOS."
    if "(expression)" not in df.columns:
        return None, "No encontré (expression) en NEGADOS."
    if "cve_vnd" not in df.columns:
        return None, "No encontré cve_vnd en NEGADOS."

    df["cve_art"] = df["cve_art"].astype(str).str.strip()
    df["cant_negada"] = pd.to_numeric(df["(expression)"], errors="coerce").fillna(0)
    df["cve_vnd"] = normalize_int_series(df["cve_vnd"])

    df = ensure_col(df, "folio", "")
    df = ensure_col(df, "cve_alm", "")

    return df[["cve_vnd", "cve_art", "cant_negada", "folio", "cve_alm"]].copy(), None

# =========================
# ESTADO
# =========================
if "auth_ok" not in st.session_state:
    st.session_state.auth_ok = False
if "view" not in st.session_state:
    st.session_state.view = "login"
if "mes" not in st.session_state:
    st.session_state.mes = "ENERO"
if "last_filters" not in st.session_state:
    st.session_state.last_filters = {}
if "next_view" not in st.session_state:
    st.session_state.next_view = "dashboard"  # a dónde ir después de elegir mes

# =========================
# LOGIN
# =========================
def login_screen():
    st.markdown(
        f"""
    <style>
    .login-card {{
        width: min(560px, 92vw);
        padding: 44px 42px 34px 42px;
        border-radius: 18px;
        background: rgba(255,255,255,0.06);
        border: 1px solid rgba(255,255,255,0.12);
        backdrop-filter: blur(8px);
        box-shadow: 0 18px 55px rgba(0,0,0,0.26);
        text-align: center;
        margin: 0 auto;
    }}
    .login-title {{
        font-size: 22px;
        font-weight: 900;
        margin-top: 12px;
        margin-bottom: 8px;
        color: {ACCENT};
    }}
    .login-sub {{
        opacity: 0.85;
        font-size: 13px;
        margin-bottom: 18px;
        color: rgba(13,59,130,0.85);
    }}
    .login-card [data-testid="stTextInput"] {{
        width: 100%;
    }}
    </style>
    """,
        unsafe_allow_html=True,
    )

    left, mid, right = st.columns([1.6, 1.0, 1.6])
    with mid:
        st.markdown('<div class="login-card">', unsafe_allow_html=True)
        safe_logo(width=240)
        st.markdown('<div class="login-title">Acceso al Dashboard de Ventas</div>', unsafe_allow_html=True)
        st.markdown('<div class="login-sub">Tradición • Confianza • Innovación</div>', unsafe_allow_html=True)

        pw = st.text_input("Contraseña", type="password", label_visibility="visible")

        if st.button("Ingresar"):
            if pw == PASSWORD:
                st.session_state.auth_ok = True
                st.session_state.view = "menu"
                st.rerun()
            else:
                st.error("Contraseña incorrecta")

        st.markdown("</div>", unsafe_allow_html=True)

# =========================
# MENU (solo vistas)
# =========================
def menu_screen():
    safe_logo(width=220)
    st.title("Menú principal")
    st.caption("Elige la vista. Después eliges el mes.")

    a, b, c = st.columns([1.3, 1.3, 1.1])
    with a:
        if st.button("📍 Mapa de ventas"):
            st.session_state.next_view = "dashboard"
            st.session_state.view = "pick_month"
            st.rerun()
    with b:
        if st.button("🧩 Ventas por especie"):
            st.session_state.next_view = "especies"
            st.session_state.view = "pick_month"
            st.rerun()
    with c:
        if st.button("🚪 Cerrar sesión"):
            st.session_state.auth_ok = False
            st.session_state.view = "login"
            st.rerun()

# =========================
# PANTALLA ELEGIR MES (para cualquier vista)
# =========================
def pick_month_screen():
    safe_logo(width=220)

    top = st.columns([1, 4])
    with top[0]:
        if st.button("⬅ Volver"):
            st.session_state.view = "menu"
            st.rerun()
    with top[1]:
        st.title("Elige el mes")
        st.caption("Selecciona el mes y te llevo a la vista.")

    col1, col2 = st.columns([1, 1])
    with col1:
        if st.button("📌 ENERO"):
            st.session_state.mes = "ENERO"
            st.session_state.view = st.session_state.next_view
            st.rerun()
    with col2:
        if st.button("📌 FEBRERO"):
            st.session_state.mes = "FEBRERO"
            st.session_state.view = st.session_state.next_view
            st.rerun()

# =========================
# DETALLE NEGADOS
# =========================
def negados_detail_screen():
    safe_logo(width=190)

    top = st.columns([1, 4, 1])
    with top[0]:
        if st.button("⬅ Volver"):
            st.session_state.view = "dashboard"
            st.rerun()
    with top[1]:
        st.title("Detalle de Negados")
        st.caption("Ordenado de mayor a menor valor. Respeta filtros (vendedor/especie).")

    filtros = st.session_state.last_filters or {}

    negados_df, err_neg = load_negados_serur()
    precios_df, err_pre = load_precios_serur()

    if err_neg:
        st.error(f"NEGADOS: {err_neg}")
        return
    if err_pre:
        st.error(f"PRECIOS: {err_pre}")
        return

    dfn = negados_df.copy()

    selected_cve_vnd = filtros.get("selected_cve_vnd", None)
    if selected_cve_vnd is not None:
        dfn = dfn[dfn["cve_vnd"].isin(selected_cve_vnd)].copy()

    include_negative = filtros.get("include_negative", False)
    if not include_negative:
        dfn = dfn[dfn["cant_negada"] > 0].copy()

    dfn = dfn.merge(precios_df, on="cve_art", how="left")
    dfn["precio"] = pd.to_numeric(dfn["precio"], errors="coerce").fillna(0)
    dfn["descri"] = dfn.get("descri", "").astype(str).fillna("").str.strip()
    dfn["valor"] = dfn["cant_negada"] * dfn["precio"]

    det = dfn.groupby(["cve_art", "descri"], as_index=False).agg(
        cant_negada=("cant_negada", "sum"),
        precio=("precio", "max"),
        valor=("valor", "sum"),
    )

    total = float(det["valor"].sum()) if not det.empty else 0.0
    det["pct_total"] = (det["valor"] / total * 100) if total > 0 else 0.0
    det = det.sort_values("valor", ascending=False)

    st.subheader("Resumen")
    c1, c2, c3 = st.columns([1.5, 1.2, 1.2])
    c1.metric("Total negado (valor)", f"${total:,.2f}")
    c2.metric("Artículos", f"{len(det):,}")
    faltan = int((det["precio"] <= 0).sum()) if not det.empty else 0
    c3.metric("Sin precio (precio=0)", f"{faltan:,}")

    st.divider()
    st.subheader("Detalle")

    st.dataframe(
        det,
        use_container_width=True,
        hide_index=True,
        column_config={
            "cant_negada": st.column_config.NumberColumn("cant_negada", format="%0.2f"),
            "precio": st.column_config.NumberColumn("precio", format="$ %0.2f"),
            "valor": st.column_config.NumberColumn("valor", format="$ %0.2f"),
            "pct_total": st.column_config.NumberColumn("% del total", format="%0.2f"),
        },
    )

# =========================
# VISTA: VENTAS POR ESPECIE
# =========================
def especies_screen(mes: str):
    cfg = VENTAS_MESES[mes]
    ventas = load_ventas(cfg["sheet_id"], cfg["tab"])

    safe_logo(width=190)
    topbar1, topbar2 = st.columns([1, 3])
    with topbar1:
        if st.button("⬅ Regresar"):
            st.session_state.view = "pick_month"
            st.rerun()
    with topbar2:
        st.title(f"Ventas por Especie | {mes}")
        st.caption("Tarjetas ordenadas + Pareto 80/20 + ‘este compa no está vendiendo esto’.")

    vendedores = sorted([v for v in ventas["vendedor"].dropna().unique().tolist() if clean_text(v) != ""])
    if not vendedores:
        st.error("No se encontraron vendedores en VENTAS.")
        return

    c1, c2, c3 = st.columns([2.1, 1.2, 1.7])
    with c1:
        vendedor_sel = st.selectbox("Vendedor", options=vendedores, index=0)
    with c2:
        umbral = st.slider("Pareto", 0.60, 0.95, 0.80, 0.05)
    with c3:
        min_no_vende = st.number_input("‘No vende’ si $ <=", min_value=0, value=0, step=100)

    dfv = ventas[ventas["vendedor"] == str(vendedor_sel).strip()].copy()
    if dfv.empty:
        st.warning("Ese vendedor no tiene ventas en este mes.")
        return

    by_esp = dfv.groupby("especie", as_index=False).agg(
        venta_sin_iva=("venta_sin_iva", "sum"),
        clientes=("cve_cte", lambda s: pd.Series(s).astype(str).nunique()),
        renglones=("especie", "count"),
    ).sort_values("venta_sin_iva", ascending=False).reset_index(drop=True)

    total_vnd = float(by_esp["venta_sin_iva"].sum()) if not by_esp.empty else 0.0
    by_esp["pct_vnd"] = (by_esp["venta_sin_iva"] / total_vnd * 100) if total_vnd > 0 else 0.0

    p_vnd = pareto_80_by_especie(dfv, threshold=float(umbral))
    p_glb = pareto_80_by_especie(ventas, threshold=float(umbral))

    set_80_vnd = set(p_vnd[p_vnd["is_80"]]["especie"].astype(str).tolist())
    especies_80_global = p_glb[p_glb["is_80"]]["especie"].astype(str).tolist()

    map_vnd = dict(zip(by_esp["especie"].astype(str), by_esp["venta_sin_iva"].astype(float)))
    faltantes = []
    for esp in especies_80_global:
        v = float(map_vnd.get(str(esp), 0.0))
        if v <= float(min_no_vende):
            faltantes.append([esp, v])

    k1, k2, k3, k4 = st.columns([2, 1.2, 1.2, 2])
    k1.metric("Venta sin IVA", f"${total_vnd:,.2f}")
    k2.metric("Especies", f"{by_esp['especie'].nunique():,}")
    k3.metric("Clientes", f"{dfv['cve_cte'].astype(str).nunique():,}")
    k4.metric(f"Especies en {int(umbral*100)}% (vendedor)", f"{len(set_80_vnd):,}")

    st.divider()

    st.subheader("Este compa NO está vendiendo esto (especies clave del mes)")
    if not faltantes:
        st.success("✅ Bien: sí trae venta en todas (o casi todas) las especies del 80/20 global.")
    else:
        df_f = pd.DataFrame(faltantes, columns=["especie", "venta_vendedor"])
        st.dataframe(
            df_f.sort_values("venta_vendedor", ascending=True),
            use_container_width=True,
            hide_index=True,
            column_config={"venta_vendedor": st.column_config.NumberColumn("Venta vendedor", format="$ %0.2f")},
        )

    st.divider()

    st.subheader("Tarjetas por especie (ordenadas por venta)")
    color_map = make_color_map(by_esp["especie"].astype(str))

    cols = st.columns(4)
    for i, r in by_esp.iterrows():
        esp = clean_text(r.get("especie", ""))
        val = float(r.get("venta_sin_iva", 0) or 0.0)
        pct = float(r.get("pct_vnd", 0) or 0.0)
        cli = int(r.get("clientes", 0) or 0)
        is80 = esp in set_80_vnd

        border = color_map.get(esp, ACCENT)
        badge = '<span class="badge">⭐ 80/20</span>' if is80 else ""

        html = f"""
        <div class="card" style="border-left: 10px solid {border};">
          <div class="title">{esp} {badge}</div>
          <div class="money">${val:,.2f}</div>
          <div class="meta">{pct:,.1f}% del vendedor • {cli:,} clientes</div>
        </div>
        """
        with cols[i % 4]:
            st.markdown(html, unsafe_allow_html=True)

    st.divider()
    st.subheader("Tabla (por si la ocupas)")
    st.dataframe(
        by_esp,
        use_container_width=True,
        hide_index=True,
        column_config={
            "venta_sin_iva": st.column_config.NumberColumn("Venta sin IVA", format="$ %0.2f"),
            "pct_vnd": st.column_config.NumberColumn("% del vendedor", format="%0.2f"),
            "clientes": st.column_config.NumberColumn("Clientes", format="%d"),
            "renglones": st.column_config.NumberColumn("Renglones", format="%d"),
        },
    )

# =========================
# DASHBOARD (MAPA) - COMO LO TENÍAS
# =========================
def dashboard_screen(mes: str):
    cfg = VENTAS_MESES[mes]
    ventas = load_ventas(cfg["sheet_id"], cfg["tab"])
    clientes = load_clientes()

    negados_df, err_neg = load_negados_serur()
    precios_df, err_pre = load_precios_serur()

    safe_logo(width=190)

    topbar1, topbar2 = st.columns([1, 3])
    with topbar1:
        if st.button("⬅ Regresar"):
            st.session_state.view = "pick_month"
            st.rerun()
    with topbar2:
        st.title(f"Mapa de Ventas | {mes}")

    vendedores = sorted([v for v in ventas["vendedor"].dropna().unique().tolist() if clean_text(v) != ""])
    if not vendedores:
        st.error("No se encontraron vendedores en VENTAS.")
        st.stop()

    especies = sorted([e for e in ventas["especie"].dropna().unique().tolist() if clean_text(e) != ""])

    c1, c2, c3, c4, c5 = st.columns([2.2, 2.6, 1.3, 2.8, 2.1])
    with c1:
        modo = st.radio("Vendedores", ["Todos", "Elegir"], horizontal=True)
    with c2:
        especie_sel = st.multiselect("Especie(s) (opcional)", options=especies, default=[])
    with c3:
        heat = st.checkbox("Heatmap", value=False)
    with c4:
        show_no_sales = st.checkbox("Mostrar clientes sin compra (del vendedor)", value=False)
    with c5:
        max_no_sales = st.slider("Máx sin compra", 0, 10000, 1500, 250, disabled=not show_no_sales)

    vendedor_sel = vendedores if modo == "Todos" else st.multiselect("Vendedor(es)", options=vendedores, default=vendedores)
    solo_top = st.number_input("Top clientes con venta (0=todos)", min_value=0, value=0, step=50)

    GRAY_FAKE_SALE = st.number_input(
        "Tamaño de gris (monto ficticio)",
        min_value=1000, value=5000, step=500,
        disabled=not show_no_sales
    )

    include_negative = st.checkbox("Incluir negados en negativo (ajustes/devoluciones)", value=False)

    vend_sel_str = [str(x).strip() for x in vendedor_sel]
    dfv = ventas[ventas["vendedor"].isin(vend_sel_str)].copy()
    if especie_sel:
        dfv = dfv[dfv["especie"].isin([str(x) for x in especie_sel])]

    sku_unicos = None
    if not dfv.empty:
        sku_col = pick_sku_col(dfv)
        if sku_col:
            sku_unicos = int(dfv[sku_col].astype(str).str.strip().replace("", pd.NA).dropna().nunique())

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

    if solo_top and solo_top > 0 and not df_sales.empty:
        df_sales = df_sales.sort_values("venta_sin_iva", ascending=False).head(int(solo_top))

    ventas_ctes = set(df_sales["cve_cte"].astype(str).tolist()) if not df_sales.empty else set()

    clientes_scope = clientes.copy() if modo == "Todos" else clientes[clientes["vendedor_cliente"].isin(vend_sel_str)].copy()
    df_no_sales_all = clientes_scope[~clientes_scope["cve_cte"].astype(str).isin(ventas_ctes)].copy()
    df_no_sales = df_no_sales_all
    if show_no_sales and max_no_sales > 0 and len(df_no_sales) > max_no_sales:
        df_no_sales = df_no_sales.head(int(max_no_sales))

    venta_total = float(df_sales["venta_sin_iva"].sum()) if not df_sales.empty else 0.0
    clientes_con_venta = int(df_sales["cve_cte"].nunique()) if not df_sales.empty else 0
    ticket_prom = (venta_total / clientes_con_venta) if clientes_con_venta else 0.0
    clientes_asignados = int(clientes_scope["cve_cte"].nunique())
    cobertura = (clientes_con_venta / clientes_asignados * 100) if clientes_asignados else 0.0

    negado_valor = 0.0
    faltan_precios = 0
    selected_cve_vnd = None

    if modo == "Todos":
        selected_cve_vnd = None
    else:
        if "cve_vnd" in ventas.columns and ventas["cve_vnd"].notna().any():
            map_df = ventas[["vendedor", "cve_vnd"]].dropna().copy()
            map_df["vendedor"] = map_df["vendedor"].astype(str).str.strip()
            map_df["cve_vnd"] = normalize_int_series(map_df["cve_vnd"])
            selected_cve_vnd = sorted(map_df[map_df["vendedor"].isin(vend_sel_str)]["cve_vnd"].dropna().unique().tolist())
        else:
            selected_cve_vnd = sorted(normalize_int_series(vend_sel_str).dropna().unique().tolist())

    if err_neg is None and err_pre is None and negados_df is not None and precios_df is not None:
        dfn = negados_df.copy()
        if selected_cve_vnd is not None:
            dfn = dfn[dfn["cve_vnd"].isin(selected_cve_vnd)].copy()
        if not include_negative:
            dfn = dfn[dfn["cant_negada"] > 0].copy()

        dfn = dfn.merge(precios_df, on="cve_art", how="left")
        dfn["precio"] = pd.to_numeric(dfn["precio"], errors="coerce").fillna(0)

        negado_valor = float((dfn["cant_negada"] * dfn["precio"]).sum())
        faltan_precios = int(((dfn["cant_negada"] > 0) & (dfn["precio"] <= 0)).sum())

    pct_negado_vs_vendido = (negado_valor / venta_total * 100) if venta_total > 0 else 0.0

    st.session_state.last_filters = {
        "selected_cve_vnd": selected_cve_vnd,
        "include_negative": include_negative,
        "mes": mes,
        "modo": modo,
        "vendedor_sel": vend_sel_str,
        "especie_sel": especie_sel,
    }

    r1 = st.columns([2.2, 1.6, 1.6, 1.6, 1.5])
    r1[0].metric("Venta sin IVA", f"${venta_total:,.2f}")
    r1[1].metric("Clientes con venta", f"{clientes_con_venta:,}")
    r1[2].metric("Ticket prom.", f"${ticket_prom:,.2f}")
    r1[3].metric("Cobertura", f"{cobertura:,.1f}%")
    r1[4].metric("SKUs únicos (vendidos)", "N/D" if sku_unicos is None else f"{sku_unicos:,}")

    r2 = st.columns([2.2, 1.6, 1.6, 1.6, 1.5])
    r2[0].metric("$ Negado", f"${negado_valor:,.2f}")
    r2[1].metric("% Negado vs Vendido", f"{pct_negado_vs_vendido:,.2f}%")
    r2[2].metric("Negados sin precio", f"{faltan_precios:,}")
    with r2[4]:
        if st.button("📋 Ver detalle"):
            st.session_state.view = "negados"
            st.rerun()

    st.divider()

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

    if show_no_sales and not df_no_sales.empty:
        gray_radius = radius_from_sale(GRAY_FAKE_SALE, min_r=7, max_r=16)
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

    if heat and not df_sales.empty:
        heat_data = df_sales[["latitud","longitud","venta_sin_iva"]].dropna()
        HeatMap(heat_data.values.tolist(), radius=18, blur=15, max_zoom=13).add_to(layer_heat)
        layer_heat.add_to(m)

    folium.LayerControl(collapsed=True).add_to(m)

    st.subheader("Mapa")
    st_folium(m, width="stretch", height=650)

# =========================
# ROUTER
# =========================
try:
    if not st.session_state.auth_ok:
        st.session_state.view = "login"

    if st.session_state.view == "login":
        login_screen()
    elif st.session_state.view == "menu":
        menu_screen()
    elif st.session_state.view == "pick_month":
        pick_month_screen()
    elif st.session_state.view == "dashboard":
        dashboard_screen(st.session_state.mes)
    elif st.session_state.view == "especies":
        especies_screen(st.session_state.mes)
    elif st.session_state.view == "negados":
        negados_detail_screen()
    else:
        st.session_state.view = "menu"
        st.rerun()

except Exception:
    st.error("Tronó la app. Aquí está el error para corregirlo rápido:")
    st.code(traceback.format_exc())
