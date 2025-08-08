
import io
import base64
import datetime as dt
from io import BytesIO
from typing import Tuple

import altair as alt
import numpy as np
import pandas as pd
import requests
import streamlit as st
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

st.set_page_config(page_title="Panamoving Dashboard", layout="wide", page_icon="📦")

# --- Branding ---
def load_logo_b64(path: str) -> str:
    try:
        with open(path, "rb") as f:
            return base64.b64encode(f.read()).decode()
    except Exception:
        return ""

LOGO_B64 = load_logo_b64("assets/logo.png")

st.markdown(
    (
        '<div style="display:flex;align-items:center;gap:12px;margin-bottom:10px">'
        + (f'<img src="data:image/png;base64,{LOGO_B64}" height="48"/>' if LOGO_B64 else '')
        + '<div><h2 style="margin:0">Panamoving · Dashboard de COMEX</h2>'
        + '<div style="color:#5b6b7b">Facturación · CxC · CxP · Rentabilidad · Clientes</div>'
        + '</div></div><hr/>'
    ),
    unsafe_allow_html=True,
)

# --- Data loader ---
st.sidebar.header("Datos")
data_source = st.sidebar.radio("¿Cómo cargar datos?", ["Subir Excel", "OneDrive / URL"], index=0)
sheet_name = st.sidebar.text_input("Nombre de la hoja", value="Facturacion")

df = None

def read_excel_bytes(b: bytes, sheet: str) -> pd.DataFrame:
    df = pd.read_excel(io.BytesIO(b), sheet_name=sheet, engine="openpyxl")
    return df

if data_source == "Subir Excel":
    up = st.sidebar.file_uploader("Subí el Excel (.xlsx)", type=["xlsx"])
    if up is not None:
        df = read_excel_bytes(up.read(), sheet_name)
else:
    url = st.sidebar.text_input("Pega el link público de OneDrive/SharePoint/Dropbox", "")
    if url:
        try:
            r = requests.get(url, timeout=30)
            r.raise_for_status()
            df = read_excel_bytes(r.content, sheet_name)
        except Exception as e:
            st.sidebar.error(f"Error al leer URL: {e}")

if df is None:
    st.info("Cargá el archivo para ver el dashboard.")

# --- Helpers / transforms ---
def coerce_date(s: pd.Series) -> pd.Series:
    return pd.to_datetime(s, errors="coerce", dayfirst=True)

def normalize(df: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame]:
    df = df.copy()
    cols = df.columns.tolist()
    def col(i, default):
        try:
            return cols[i]
        except Exception:
            return default

    mapping = {
        "factura": col(0,"A"), "operacion": col(1,"B"),
        "emision": col(2,"C"), "vencimiento": col(3,"D"),
        "cliente": col(4,"E"), "descripcion": col(5,"F"),
        "monto_fact": col(6,"G"),
        "mar_prov": col(7,"H"), "mar_nro": col(8,"I"), "mar_monto": col(9,"J"),
        "mar_status": col(10,"K"), "mar_recep": col(11,"L"), "mar_vto": col(12,"M"),
        "ter_prov": col(13,"N"), "ter_nro": col(14,"O"), "ter_monto": col(15,"P"),
        "ter_status": col(16,"Q"), "ter_recep": col(17,"R"), "ter_vto": col(18,"S"),
        "age_prov": col(19,"T"), "age_nro": col(20,"U"), "age_monto": col(21,"V"),
        "age_status": col(22,"W"), "age_recep": col(23,"X"), "age_vto": col(24,"Y"),
        "cargos_banc": col(25,"Z"), "otros_gastos": col(26,"AA"),
        "profit_share": col(27,"AB"), "estado_cli": col(28,"AC"), "fecha_cobro": col(29,"AD"),
    }
    d = df.rename(columns=mapping)

    for c in ["emision","vencimiento","mar_recep","mar_vto","ter_recep","ter_vto","age_recep","age_vto","fecha_cobro"]:
        d[c] = coerce_date(d.get(c))

    money_cols = ["monto_fact","mar_monto","ter_monto","age_monto","cargos_banc","otros_gastos","profit_share"]
    for c in money_cols:
        d[c] = pd.to_numeric(d.get(c), errors="coerce").fillna(0.0)

    # Normalized AP
    ap_rows = []
    today = pd.Timestamp.today().normalize()
    for tipo, prov_col, monto_col, status_col, vto_col in [
        ("Marítimo","mar_prov","mar_monto","mar_status","mar_vto"),
        ("Terrestre/Otros","ter_prov","ter_monto","ter_status","ter_vto"),
        ("Agente/Gs Ports/Otros","age_prov","age_monto","age_status","age_vto"),
    ]:
        temp = d[[
            "factura","operacion","emision","cliente","monto_fact","estado_cli",
            prov_col, monto_col, status_col, vto_col
        ]].copy()
        temp.columns = ["factura","operacion","emision","cliente","monto_fact","estado_cli","proveedor","monto","status","vencimiento"]
        temp["tipo_proveedor"] = tipo
        ap_rows.append(temp)
    ap = pd.concat(ap_rows, ignore_index=True)
    ap["vencido"] = (ap["vencimiento"].notna()) & (ap["vencimiento"] < today) & (ap["status"].str.lower().fillna("").str.contains("pend"))
    ap["pendiente"] = ap["status"].str.lower().fillna("").str.contains("pend")
    ap["pagada"] = ap["status"].str.lower().fillna("").str.contains("pag")

    d["cobrada"] = d["estado_cli"].str.lower().fillna("").str.contains("cob")
    d["vencida"] = (d["vencimiento"].notna()) & (d["vencimiento"] < today) & (~d["cobrada"])
    d["mes"] = d["emision"].dt.to_period("M").astype(str)
    return d, ap

def aging_bucket(days: float) -> str:
    if pd.isna(days):
        return "Sin fecha"
    if days <= 0:
        return "No vencido"
    if days <= 30:
        return "1–30"
    if days <= 60:
        return "31–60"
    if days <= 90:
        return "61–90"
    return "90+"

if df is not None:
    d, ap = normalize(df)

    # Sidebar filters
    st.sidebar.header("Filtros")
    date_from, date_to = st.sidebar.date_input(
        "Rango de emisión (C)",
        value=(d["emision"].min() if pd.notna(d["emision"].min()) else dt.date.today().replace(month=1, day=1),
               d["emision"].max() if pd.notna(d["emision"].max()) else dt.date.today())
    )

    clientes = sorted([x for x in d["cliente"].dropna().unique()])
    sel_clientes = st.sidebar.multiselect("Cliente", clientes, default=None)

    all_prov = sorted([x for x in ap["proveedor"].dropna().unique()])
    sel_prov = st.sidebar.multiselect("Proveedor", all_prov, default=None)

    tipo_map = ["Marítimo","Terrestre/Otros","Agente/Gs Ports/Otros"]
    sel_tipo = st.sidebar.multiselect("Tipo proveedor", tipo_map, default=tipo_map)

    estados_cli = ["Emitir","Enviada","Cobrada"]
    sel_estado_cli = st.sidebar.multiselect("Estado factura cliente", estados_cli, default=estados_cli)

    sel_status_prov = st.sidebar.multiselect("Status proveedor", ["Pendiente","Pagada"], default=["Pendiente","Pagada"])

    only_vencidos_ar = st.sidebar.checkbox("Sólo CxC vencidas (cliente)")
    only_vencidos_ap = st.sidebar.checkbox("Sólo CxP vencidas (proveedor)")

    # Apply filters
    mask = (d["emision"].dt.date >= date_from) & (d["emision"].dt.date <= date_to)
    if sel_clientes:
        mask &= d["cliente"].isin(sel_clientes)
    if sel_estado_cli:
        mask &= d["estado_cli"].isin(sel_estado_cli)
    if only_vencidos_ar:
        mask &= d["vencida"]

    d_f = d[mask].copy()

    ap_mask = ap["factura"].isin(d_f["factura"])
    if sel_prov:
        ap_mask &= ap["proveedor"].isin(sel_prov)
    if sel_tipo:
        ap_mask &= ap["tipo_proveedor"].isin(sel_tipo)
    if sel_status_prov:
        ap_mask &= ap["status"].str.title().fillna("").isin(sel_status_prov)
    if only_vencidos_ap:
        ap_mask &= ap["vencido"]

    ap_f = ap[ap_mask].copy()

    # KPIs
    total_revenue = d_f["monto_fact"].sum()
    collected = d_f.loc[d_f["cobrada"], "monto_fact"].sum()
    ar_outstanding = d_f.loc[~d_f["cobrada"], "monto_fact"].sum()

    ap_outstanding = ap_f.loc[ap_f["pendiente"], "monto"].sum()
    bank_fees = d_f["cargos_banc"].sum()
    otros = d_f["otros_gastos"].sum()

    profit_ab = d_f["profit_share"].sum()

    costs_recorded = ap_f["monto"].sum() + bank_fees + otros
    profit_recalc = total_revenue - costs_recorded

    col1, col2, col3, col4, col5, col6 = st.columns(6)
    col1.metric("Ingresos (filtrado)", f"${total_revenue:,.2f}")
    col2.metric("Cobrado", f"${collected:,.2f}")
    col3.metric("CxC Pendiente", f"${ar_outstanding:,.2f}")
    col4.metric("CxP Pendiente", f"${ap_outstanding:,.2f}")
    col5.metric("Profit (AB)", f"${profit_ab:,.2f}")
    col6.metric("Profit (Recalc.)", f"${profit_recalc:,.2f}")

    st.caption("Nota: Profit (Recalc.) descuenta sólo costos registrados en el filtro actual. AB es el valor de la columna cargada.")

    # Charts
    st.subheader("Indicadores")
    d_f["month"] = d_f["emision"].dt.to_period("M").astype(str)
    rev_by_month = d_f.groupby("month", as_index=False).agg(revenue=("monto_fact","sum"))
    # cobrado mensual
    cobrado_m = d_f[d_f["cobrada"]].groupby("month", as_index=False).agg(cobrado=("monto_fact","sum"))
    rev_by_month = rev_by_month.merge(cobrado_m, on="month", how="left").fillna(0)

    chart_rev = alt.Chart(rev_by_month).mark_bar().encode(
        x=alt.X("month:N", title="Mes"),
        y=alt.Y("revenue:Q", title="Facturado")
    ).properties(height=250)
    chart_cob = alt.Chart(rev_by_month).mark_line(point=True).encode(
        x="month:N", y=alt.Y("cobrado:Q", title="Cobrado")
    )
    st.altair_chart(chart_rev + chart_cob, use_container_width=True)

    # Profit por mes
    prof_df = d_f.groupby("month", as_index=False).agg(profit_ab=("profit_share","sum"))
    ap_f["month"] = ap_f["factura"].map(d_f.set_index("factura")["month"])
    prof_recalc = (d_f.groupby("month")["monto_fact"].sum()
                   - ap_f.groupby("month")["monto"].sum().reindex(d_f["month"].unique(), fill_value=0)
                   - d_f.groupby("month")["cargos_banc"].sum()
                   - d_f.groupby("month")["otros_gastos"].sum())
    prof_df["profit_recalc"] = prof_df["month"].map(prof_recalc).fillna(0)

    chart_prof = alt.Chart(prof_df).transform_fold(
        ["profit_ab","profit_recalc"],
        as_=["Tipo","Monto"]
    ).mark_line(point=True).encode(
        x="month:N", y="Monto:Q", color=alt.Color("Tipo:N", title="Tipo")
    ).properties(height=250)
    st.altair_chart(chart_prof, use_container_width=True)

    # Top clientes
    top_clientes = d_f.groupby("cliente", as_index=False).agg(revenue=("monto_fact","sum"),
                                                              profit_ab=("profit_share","sum"))
    top_clientes = top_clientes.sort_values("revenue", ascending=False).head(10)
    chart_clients = alt.Chart(top_clientes).transform_fold(
        ["revenue","profit_ab"], as_=["Tipo","Monto"]
    ).mark_bar().encode(
        x=alt.X("cliente:N", sort="-y", title="Cliente"),
        y=alt.Y("Monto:Q", title="USD"),
        color=alt.Color("Tipo:N", title="Métrica")
    ).properties(height=300)
    st.altair_chart(chart_clients, use_container_width=True)

    # Customer growth
    first_inv = d_f.groupby("cliente")["emision"].min().dropna()
    first_inv = first_inv.dt.to_period("M").astype(str).value_counts().sort_index()
    cg = pd.DataFrame({"month": first_inv.index, "new_clients": first_inv.values})
    chart_cg = alt.Chart(cg).mark_line(point=True).encode(x="month:N", y="new_clients:Q",)
    st.altair_chart(chart_cg.properties(height=250), use_container_width=True)

    # Tabs
    tab1, tab2, tab3 = st.tabs(["📄 Facturación (CxC)", "📦 Proveedores (CxP)", "📊 Rentabilidad"])

    with tab1:
        today = pd.Timestamp.today().normalize()
        d_f["days_past_due"] = np.where(d_f["vencimiento"].notna(), (today - d_f["vencimiento"]).dt.days, np.nan)
        d_f["aging"] = d_f["days_past_due"].apply(aging_bucket)
        st.dataframe(d_f[[
            "factura","operacion","emision","vencimiento","cliente","descripcion",
            "monto_fact","estado_cli","fecha_cobro","vencida","aging"
        ]].sort_values(["vencida","vencimiento","cliente"], ascending=[False, True, True]), use_container_width=True)

    with tab2:
        today = pd.Timestamp.today().normalize()
        ap_f["days_past_due"] = np.where(ap_f["vencimiento"].notna(), (today - ap_f["vencimiento"]).dt.days, np.nan)
        ap_f["aging"] = ap_f["days_past_due"].apply(aging_bucket)
        st.dataframe(ap_f[[
            "factura","operacion","tipo_proveedor","proveedor","monto","status","vencimiento","pendiente","vencido","aging"
        ]].sort_values(["pendiente","vencido","vencimiento"], ascending=[False, False, True]), use_container_width=True)

    with tab3:
        st.dataframe(top_clientes, use_container_width=True)

    # Exports
    st.subheader("Exportar")
    def to_excel_bytes(df_dict: dict) -> bytes:
        bio = io.BytesIO()
        with pd.ExcelWriter(bio, engine="openpyxl") as writer:
            for name, dset in df_dict.items():
                dset.to_excel(writer, index=False, sheet_name=name[:31])
        return bio.getvalue()

    excel_bytes = to_excel_bytes({
        "Facturacion_filtrada": d_f,
        "Proveedores_filtrado": ap_f,
        "Top_clientes": top_clientes,
        "Profit_mensual": prof_df,
    })
    st.download_button("⬇️ Descargar Excel (vistas filtradas)",
                    data=excel_bytes, file_name="panamoving_export.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

    def build_pdf_summary() -> bytes:
        buf = BytesIO()
        c = canvas.Canvas(buf, pagesize=A4)
        W, H = A4
        y = H - 40
        c.setFont("Helvetica-Bold", 14)
        c.drawString(40, y, "Panamoving - Resumen")
        y -= 20
        c.setFont("Helvetica", 10)
        lines = [
            f"Periodo: {date_from} a {date_to}",
            f"Ingresos: ${total_revenue:,.2f}",
            f"Cobrado: ${collected:,.2f}",
            f"CxC Pendiente: ${ar_outstanding:,.2f}",
            f"CxP Pendiente: ${ap_outstanding:,.2f}",
            f"Profit (AB): ${profit_ab:,.2f}",
            f"Profit (Recalc.): ${profit_recalc:,.2f}",
            f"Clientes únicos: {d_f['cliente'].nunique()}",
            f"Proveedores únicos (filtrados): {ap_f['proveedor'].nunique()}",
        ]
        for ln in lines:
            c.drawString(40, y, ln); y -= 16
        c.showPage()
        c.save()
        return buf.getvalue()

    pdf_bytes = build_pdf_summary()
    st.download_button("⬇️ Descargar PDF (resumen)",
                    data=pdf_bytes, file_name="panamoving_resumen.pdf", mime="application/pdf")

    st.caption("Hecho con ❤️ para Panamoving — Gratis para desplegar en Streamlit Cloud.")
