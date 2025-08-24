# app.py
# Versi: UI & struktur mirip "before" (dashboard pro, menu, approve table, dsb.)
# Backend: Supabase (tanpa file JSON/Sheets)
import os
import base64
from io import BytesIO
from datetime import datetime
import pandas as pd
import streamlit as st
# --- Hotfix: alias agar kode lama tetap jalan di Streamlit baru ---
try:
    if not hasattr(st, "experimental_rerun"):
        st.experimental_rerun = st.rerun
except Exception:
    pass


# Optional grafik (Altair) — sama seperti referensi
try:
    import altair as alt
    _ALT_OK = True
except Exception:
    _ALT_OK = False

from supabase import create_client, Client

# ================== KONFIGURASI & STYLING ==================
st.set_page_config(page_title="Inventory System", page_icon="🧰", layout="wide")

# --- Compat rerun untuk Streamlit lama/baru ---
def _safe_rerun():
    try:
        st.rerun()  # Streamlit baru
    except AttributeError:
        try:
            st.experimental_rerun()  # Streamlit lama
        except AttributeError:
            pass

# (opsional) tampilkan info runtime untuk diagnosis
# st.caption(f"🧩 Streamlit version: {st.__version__}")
# st.caption(f"📄 Running file: {__file__}")
# st.caption(f"📦 CWD: {os.getcwd()}")

# Branding & style mirip file "before"
BANNER_URL = "https://media.licdn.com/dms/image/v2/D563DAQFDri8xlKNIvg/image-scale_191_1128/image-scale_191_1128/0/1678337293506/pesona_inti_rasa_cover"
st.markdown("""
    <style>
    .main { background-color: #F8FAFC; }
    h1, h2, h3 { color: #0F172A; }
    .kpi-card {
        background: #ffffff; border: 1px solid #E2E8F0; border-radius: 14px; padding: 18px 18px 12px 18px;
        box-shadow: 0 1px 2px rgba(0,0,0,0.04);
    }
    .kpi-title { font-size: 12px; color: #64748B; letter-spacing: .06em; text-transform: uppercase; }
    .kpi-value { font-size: 26px; font-weight: 700; color: #16A34A; margin-top: 6px; }
    .kpi-sub { font-size: 12px; color: #64748B; margin-top: 2px; }
    .stButton>button {
        background-color: #0EA5E9; color: white; border-radius: 8px; height: 2.6em; width: 100%; border: none;
    }
    .stButton>button:hover { background-color: #0284C7; color: white; }
    .smallcap{ font-size:12px; color:#64748B;}
    .card {
        background: #ffffff; border: 1px solid #E2E8F0; border-radius: 14px; padding: 14px;
        box-shadow: 0 1px 2px rgba(0,0,0,0.04); height: 100%;
    }
    </style>
""", unsafe_allow_html=True)

# ================== SUPABASE ==================
SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# (Opsional) multi-brand seperti "before": set True & tambahkan kolom brand di semua tabel
ENABLE_BRAND = False
BRANDS = ["gulavit", "takokak"]

# ================== UTILITAS & NORMALISASI ==================
UPLOADS_DIR = "uploads"
os.makedirs(UPLOADS_DIR, exist_ok=True)

TRANS_TYPES = ["Support", "Penjualan"]
STD_REQ_COLS = ["date","code","item","qty","unit","event","trans_type","do_number","attachment","user","timestamp"]

def timestamp():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def _to_date_str(val):
    if val is None or str(val).strip() == "":
        return datetime.now().strftime("%Y-%m-%d")
    try:
        return pd.to_datetime(val, errors="coerce").strftime("%Y-%m-%d")
    except Exception:
        return datetime.now().strftime("%Y-%m-%d")

def _norm_event(s):
    return str(s).strip() if s is not None else "-"

def _norm_trans_type(s):
    s = "" if s is None else str(s).strip().lower()
    if s == "support": return "Support"
    if s == "penjualan": return "Penjualan"
    return None

def normalize_out_record(base: dict) -> dict:
    rec = {k: None for k in STD_REQ_COLS}
    rec.update({
        "date": _to_date_str(base.get("date")),
        "code": base.get("code", "-") or "-",
        "item": base.get("item", "-") or "-",
        "qty": int(pd.to_numeric(base.get("qty", 0), errors="coerce") or 0),
        "unit": base.get("unit", "-") or "-",
        "event": _norm_event(base.get("event", "-")),
        "trans_type": _norm_trans_type(base.get("trans_type")),
        "do_number": base.get("do_number", "-") or "-",
        "attachment": base.get("attachment"),
        "user": base.get("user", st.session_state.get("username", "-")),
        "timestamp": base.get("timestamp", timestamp()),
    })
    return rec

def normalize_return_record(base: dict) -> dict:
    rec = {k: None for k in STD_REQ_COLS}
    rec.update({
        "date": _to_date_str(base.get("date")),
        "code": base.get("code", "-") or "-",
        "item": base.get("item", "-") or "-",
        "qty": int(pd.to_numeric(base.get("qty", 0), errors="coerce") or 0),
        "unit": base.get("unit", "-") or "-",
        "event": _norm_event(base.get("event", "-")),
        "trans_type": None,
        "do_number": "-",
        "attachment": None,
        "user": base.get("user", st.session_state.get("username", "-")),
        "timestamp": base.get("timestamp", timestamp()),
    })
    return rec

def dataframe_to_excel_bytes(df: pd.DataFrame, sheet_name="Sheet1") -> bytes:
    output = BytesIO()
    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
        df.to_excel(writer, sheet_name=sheet_name, index=False)
    output.seek(0)
    return output.read()

# ================== SUPABASE: LOAD/SAVE WRAPPERS ==================
@st.cache_data(ttl=600)
def load_users():
    q = supabase.from_("users_gulavit").select("*")
    data = q.execute().data or []
    return {r["username"]: {"password": r["password"], "role": r["role"]} for r in data}

@st.cache_data(ttl=300)
def load_inventory(brand=None) -> pd.DataFrame:
    q = supabase.from_("inventory_gulavit").select("*")
    if ENABLE_BRAND and brand:
        q = q.eq("brand", brand)
    data = q.execute().data or []
    df = pd.DataFrame(data)
    if not df.empty:
        df.rename(columns={"item":"name","balance":"qty"}, inplace=True, errors="ignore")
        for c in ["code","name","unit","category"]:
            if c not in df.columns: df[c] = "-"
        if "qty" not in df.columns: df["qty"] = 0
        df["qty"] = pd.to_numeric(df["qty"], errors="coerce").fillna(0).astype(int)
    return df

@st.cache_data(ttl=120)
def load_pending(brand=None) -> pd.DataFrame:
    q = supabase.from_("pending_gulavit").select("*")
    if ENABLE_BRAND and brand:
        q = q.eq("brand", brand)
    data = q.execute().data or []
    return pd.DataFrame(data)

@st.cache_data(ttl=120)
def load_history(brand=None) -> pd.DataFrame:
    q = supabase.from_("history_gulavit").select("*")
    if ENABLE_BRAND and brand:
        q = q.eq("brand", brand)
    data = q.execute().data or []
    return pd.DataFrame(data)

def inv_add_item(code, name, qty, unit="-", category="Uncategorized", brand=None):
    payload = {"code": code, "item": name, "qty": int(qty), "unit": unit or "-", "category": category or "Uncategorized"}
    if ENABLE_BRAND: payload["brand"] = brand or BRANDS[0]
    supabase.from_("inventory_gulavit").insert(payload).execute()
    st.cache_data.clear()

def inv_update_qty(code, new_qty):
    # Jika kolom di Supabase masih 'balance', update keduanya untuk aman
    supabase.from_("inventory_gulavit").update({"qty": int(new_qty), "balance": int(new_qty)}).eq("code", code).execute()
    st.cache_data.clear()

def pending_insert(rec_type, rec, brand=None):
    payload = {"type": rec_type, **rec}
    if ENABLE_BRAND: payload["brand"] = brand or BRANDS[0]
    supabase.from_("pending_gulavit").insert(payload).execute()
    st.cache_data.clear()

def pending_delete_by_id(row_id):
    supabase.from_("pending_gulavit").delete().eq("id", row_id).execute()
    st.cache_data.clear()

def history_insert(entry, brand=None):
    payload = {**entry}
    if ENABLE_BRAND: payload["brand"] = brand or BRANDS[0]
    supabase.from_("history_gulavit").insert(payload).execute()
    st.cache_data.clear()

# ================== DASHBOARD HELPERS (mirip before) ==================
def _prepare_history_df(df_hist_raw: pd.DataFrame) -> pd.DataFrame:
    df = df_hist_raw.copy()
    if df.empty: return df
    for c in ["qty","date","timestamp","action","item","event","trans_type","unit"]:
        if c not in df.columns: df[c] = None
    df["qty"] = pd.to_numeric(df["qty"], errors="coerce").fillna(0).astype(int)
    s_date = pd.to_datetime(df["date"], errors="coerce")
    s_ts = pd.to_datetime(df["timestamp"], errors="coerce")
    df["date_eff"] = s_date.fillna(s_ts).dt.floor("D")
    act = df.get("action","").astype(str).str.upper()
    df["type_norm"] = "-"
    df.loc[act.str.contains("APPROVE_IN"), "type_norm"] = "IN"
    df.loc[act.str.contains("APPROVE_OUT"), "type_norm"] = "OUT"
    df.loc[act.str.contains("APPROVE_RETURN"), "type_norm"] = "RETURN"
    df["event"] = df["event"].fillna("-").astype(str)
    df["trans_type"] = df["trans_type"].fillna("-").astype(str)
    df = df[df["type_norm"].isin(["IN","OUT","RETURN"])].copy()
    df = df.dropna(subset=["date_eff"])
    return df

def _kpi_card(title, value, change_text=None):
    st.markdown(f"""
        <div class="kpi-card">
            <div class="kpi-title">{title}</div>
            <div class="kpi-value">{value}</div>
            <div class="kpi-sub">{change_text or ""}</div>
        </div>
    """, unsafe_allow_html=True)

def render_dashboard_pro(df_hist_raw: pd.DataFrame, df_inv: pd.DataFrame, brand_label: str, allow_download=True):
    df_hist = _prepare_history_df(df_hist_raw)
    st.markdown(f"## Dashboard — {brand_label}")
    st.caption("Semua metrik berbasis jumlah (qty). *Sales* = OUT dengan tipe **Penjualan**.")
    st.divider()

    # Filter periode
    today = pd.Timestamp.today().normalize()
    default_start = (today - pd.DateOffset(months=11)).replace(day=1)
    colF1, colF2 = st.columns(2)
    start_date = colF1.date_input("Tanggal mulai", value=default_start.date())
    end_date   = colF2.date_input("Tanggal akhir", value=today.date())

    # Range
    if not df_hist.empty:
        mask = (df_hist["date_eff"] >= pd.Timestamp(start_date)) & (df_hist["date_eff"] <= pd.Timestamp(end_date))
        df_range = df_hist.loc[mask].copy()
    else:
        df_range = pd.DataFrame(columns=["date_eff","type_norm","qty","item","event","trans_type"])

    # KPI
    df_inv_view = pd.DataFrame([{"Kode": r["code"], "Nama Barang": r["name"], "Current Stock": int(r["qty"]), "Unit": r.get("unit","-")}
                                for _, r in df_inv.iterrows()]) if not df_inv.empty else pd.DataFrame()
    total_sku = int(len(df_inv_view)) if not df_inv_view.empty else 0
    total_qty = int(df_inv_view["Current Stock"].sum()) if not df_inv_view.empty else 0
    tot_in  = int(df_range.loc[df_range["type_norm"]=="IN", "qty"].sum()) if not df_range.empty else 0
    tot_out = int(df_range.loc[df_range["type_norm"]=="OUT", "qty"].sum()) if not df_range.empty else 0
    tot_ret = int(df_range.loc[df_range["type_norm"]=="RETURN", "qty"].sum()) if not df_range.empty else 0

    k1, k2, k3, k4 = st.columns(4)
    _kpi_card("Total SKU", f"{total_sku:,}", f"Brand {brand_label}")
    _kpi_card("Total Qty (Stock)", f"{total_qty:,}", f"Per {pd.Timestamp(end_date).strftime('%d %b %Y')}")
    _kpi_card("Total IN (periode)", f"{tot_in:,}", None)
    _kpi_card("Total OUT / Retur", f"{tot_out:,} / {tot_ret:,}", None)

    st.divider()

    # Agregasi bulanan
    def month_agg(df, tipe):
        d = df[df["type_norm"]==tipe].copy()
        if d.empty:
            return pd.DataFrame({"month": [], "qty": [], "Periode": [], "idx": []})
        d["month"] = d["date_eff"].dt.to_period("M").dt.to_timestamp()
        g = d.groupby("month", as_index=False)["qty"].sum().sort_values("month")
        g["Periode"] = g["month"].dt.strftime("%b %Y")
        g["idx"] = g["month"].dt.year.astype(int) * 12 + g["month"].dt.month.astype(int)
        return g

    g_in  = month_agg(df_range, "IN")
    g_out = month_agg(df_range, "OUT")
    g_ret = month_agg(df_range, "RETURN")

    c1, c2, c3 = st.columns(3)
    def _month_bar(container, dfm, title, color="#0EA5E9"):
        with container:
            st.markdown(f'<div class="card"><div class="smallcap">{title}</div>', unsafe_allow_html=True)
            if _ALT_OK and not dfm.empty:
                chart = (
                    alt.Chart(dfm)
                    .mark_bar(size=28)
                    .encode(
                        x=alt.X("Periode:O",
                                sort=alt.SortField(field="idx", order="ascending"),
                                title="Periode"),
                        y=alt.Y("qty:Q", title="Qty"),
                        tooltip=[alt.Tooltip("month:T", title="Periode", format="%b %Y"), "qty:Q"],
                        color=alt.value(color)
                    ).properties(height=320)
                )
                st.altair_chart(chart, use_container_width=True)
            else:
                if dfm.empty: st.info("Belum ada data.")
                else: st.bar_chart(dfm.set_index("Periode")["qty"])
            st.markdown("</div>", unsafe_allow_html=True)

    _month_bar(c1, g_in,  "IN per Month",    "#22C55E")
    _month_bar(c2, g_out, "OUT per Month",   "#EF4444")
    _month_bar(c3, g_ret, "RETURN per Month", "#0EA5E9")

    st.divider()

    # Top 10 current stock
    t1, t2 = st.columns([1,1])
    with t1:
        st.markdown('<div class="card"><div class="smallcap">Top 10 Items (Current Stock)</div>', unsafe_allow_html=True)
        if not df_inv_view.empty:
            top10 = df_inv_view.sort_values("Current Stock", ascending=False).head(10)
            if _ALT_OK:
                chart = (
                    alt.Chart(top10)
                    .mark_bar(size=22)
                    .encode(
                        y=alt.Y("Nama Barang:N", sort="-x", title=None),
                        x=alt.X("Current Stock:Q", title="Qty"),
                        tooltip=["Nama Barang","Current Stock"]
                    ).properties(height=360)
                )
                st.altair_chart(chart, use_container_width=True)
            else:
                st.dataframe(top10, use_container_width=True, hide_index=True)
        else:
            st.info("Inventory kosong.")
        st.markdown("</div>", unsafe_allow_html=True)

    # Top 5 event OUT
    with t2:
        st.markdown('<div class="card"><div class="smallcap">Top 5 Event by OUT Qty</div>', unsafe_allow_html=True)
        df_ev = df_range[(df_range["type_norm"]=="OUT") & (df_range["event"].notna())].copy()
        df_ev = df_ev[df_ev["event"].astype(str).str.strip().ne("-")]
        ev_top = (df_ev.groupby("event", as_index=False)["qty"].sum()
                  .sort_values("qty", ascending=False).head(5))
        if _ALT_OK and not ev_top.empty:
            chart = (
                alt.Chart(ev_top)
                .mark_bar(size=22)
                .encode(
                    y=alt.Y("event:N", sort="-x", title="Event"),
                    x=alt.X("qty:Q", title="Qty"),
                    tooltip=["event","qty"]
                ).properties(height=360)
            )
            st.altair_chart(chart, use_container_width=True)
        else:
            if ev_top.empty: st.info("Belum ada OUT pada rentang ini.")
            else: st.dataframe(ev_top.rename(columns={"event":"Event","qty":"Qty"}),
                               use_container_width=True, hide_index=True)
        st.markdown("</div>", unsafe_allow_html=True)

# ================== SESSION STATE ==================
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.username = ""
    st.session_state.role = ""
    st.session_state.current_brand = BRANDS[0]

if "req_in_items" not in st.session_state: st.session_state.req_in_items = []
if "req_out_items" not in st.session_state: st.session_state.req_out_items = []
if "req_ret_items" not in st.session_state: st.session_state.req_ret_items = []
if "notification" not in st.session_state: st.session_state.notification = None

# ================== LOGIN PAGE (mirip before) ==================
if not st.session_state.logged_in:
    st.image(BANNER_URL, use_container_width=True)
    st.markdown("<div style='text-align:center;'><h1 style='margin-top:10px;'>Inventory Management System</h1></div>", unsafe_allow_html=True)
    st.subheader("Silakan Login untuk Mengakses Sistem")
    username = st.text_input("Username", placeholder="Masukkan username")
    password = st.text_input("Password", type="password", placeholder="Masukkan password")
    if st.button("Login"):
        users = load_users()
        user = users.get(username)
        if user and user["password"] == password:
            st.session_state.logged_in = True
            st.session_state.username = username
            st.session_state.role = user["role"]
            st.success(f"Login berhasil sebagai {user['role'].upper()}")
            _safe_rerun()
        else:
            st.error("❌ Username atau password salah.")
    st.stop()

# ================== MAIN APP ==================
role = st.session_state.role
st.image(BANNER_URL, use_container_width=True)

# Sidebar (mirip before)
st.sidebar.markdown(f"### 👋 Halo, {st.session_state.username}")
st.sidebar.caption(f"Role: **{role.upper()}**")
st.sidebar.divider()

if ENABLE_BRAND:
    brand_choice = st.sidebar.selectbox("Pilih Brand", BRANDS, format_func=lambda x: x.capitalize())
    st.session_state.current_brand = brand_choice
else:
    st.session_state.current_brand = BRANDS[0]
brand = st.session_state.current_brand if ENABLE_BRAND else None

if st.sidebar.button("🚪 Logout"):
    st.session_state.logged_in = False
    st.session_state.username = ""
    st.session_state.role = ""
    st.session_state.current_brand = BRANDS[0]
    _safe_rerun()

st.sidebar.divider()

if st.session_state.notification:
    nt = st.session_state.notification
    (st.success if nt["type"]=="success" else st.warning if nt["type"]=="warning" else st.error)(nt["message"])
    st.session_state.notification = None

# Muat data dari Supabase (cached)
df_inv = load_inventory(brand=brand)
df_hist = load_history(brand=brand)
df_pending = load_pending(brand=brand)

# ================== MENU ADMIN ==================
if role == "admin":
    admin_options = [
        "Dashboard",
        "Lihat Stok Barang",
        "Stock Card",
        "Tambah Master Barang",
        "Approve Request",
        "Riwayat Lengkap",
        "Export Laporan ke Excel",
        "Reset Database"
    ]
    menu = st.sidebar.radio("📌 Menu Admin", admin_options)

    # Dashboard
    if menu == "Dashboard":
        render_dashboard_pro(df_hist, df_inv, brand_label=st.session_state.current_brand.capitalize(), allow_download=False)

    elif menu == "Lihat Stok Barang":
        st.markdown(f"## Stok Barang - Brand {st.session_state.current_brand.capitalize()}")
        st.divider()
        if not df_inv.empty:
            df_inventory_full = df_inv.rename(columns={"name":"Nama Barang","qty":"Qty","code":"Kode","unit":"Satuan"})
            if "category" not in df_inventory_full.columns: df_inventory_full["category"]="Uncategorized"
            df_inventory_full.rename(columns={"category":"Kategori"}, inplace=True)

            unique_categories = ["Semua Kategori"] + sorted(df_inventory_full["Kategori"].unique())
            selected_category = st.selectbox("Pilih Kategori", unique_categories)
            search_query = st.text_input("Cari berdasarkan Nama atau Kode")

            df_filtered = df_inventory_full.copy()
            if selected_category != "Semua Kategori":
                df_filtered = df_filtered[df_filtered["Kategori"] == selected_category]
            if search_query:
                df_filtered = df_filtered[
                    df_filtered["Nama Barang"].str.contains(search_query, case=False) |
                    df_filtered["Kode"].str.contains(search_query, case=False)
                ]
            st.dataframe(df_filtered, use_container_width=True, hide_index=True)
        else:
            st.info("Belum ada barang di inventory.")

    elif menu == "Stock Card":
        st.markdown(f"## Stock Card Barang - Brand {st.session_state.current_brand.capitalize()}")
        st.divider()
        if df_hist.empty or df_inv.empty:
            st.info("Belum ada riwayat transaksi atau master barang.")
        else:
            item_names = sorted(df_inv["name"].unique().tolist())
            selected_item_name = st.selectbox("Pilih Barang", item_names)
            if selected_item_name:
                filtered_history = df_hist[df_hist["item"] == selected_item_name]
                filtered_history = filtered_history[
                    filtered_history["action"].astype(str).str.startswith(("APPROVE","ADD"))
                ].copy()
                if filtered_history.empty:
                    st.info("Tidak ada riwayat transaksi yang disetujui untuk barang ini.")
                else:
                    stock_card_data = []
                    current_balance = 0
                    for _, h in filtered_history.sort_values("timestamp").iterrows():
                        transaction_in = 0
                        transaction_out = 0
                        keterangan = "N/A"
                        act = str(h["action"])
                        if act == "ADD_ITEM":
                            transaction_in = h["qty"]; current_balance += transaction_in
                            keterangan = "Initial Stock"
                        elif act == "APPROVE_IN":
                            transaction_in = h["qty"]; current_balance += transaction_in
                            keterangan = f"Request IN by {h['user']}"
                            do_number = h.get('do_number', '-')
                            if pd.notna(do_number) and do_number != '-': keterangan += f" (No. DO: {do_number})"
                        elif act == "APPROVE_OUT":
                            transaction_out = h["qty"]; current_balance -= transaction_out
                            tipe = h.get("trans_type","-")
                            keterangan = f"Request OUT ({tipe}) by {h['user']} for event: {h.get('event', '-')}"
                        elif act == "APPROVE_RETURN":
                            transaction_in = h["qty"]; current_balance += transaction_in
                            keterangan = f"Retur by {h['user']} for event: {h.get('event', '-')}"
                        else:
                            continue
                        stock_card_data.append({
                            "Tanggal": h.get("date", h["timestamp"]),
                            "Keterangan": keterangan,
                            "Masuk (IN)": transaction_in if transaction_in > 0 else "-",
                            "Keluar (OUT)": transaction_out if transaction_out > 0 else "-",
                            "Saldo Akhir": current_balance
                        })
                    st.dataframe(pd.DataFrame(stock_card_data), use_container_width=True, hide_index=True)

    elif menu == "Tambah Master Barang":
        st.markdown(f"## Tambah Master Barang - Brand {st.session_state.current_brand.capitalize()}")
        st.divider()
        tab1, tab2 = st.tabs(["Input Manual", "Upload Excel"])

        with tab1:
            code_input = st.text_input("Kode Barang (unik & wajib)", placeholder="Misal: ITM-0001")
            name = st.text_input("Nama Barang")
            unit = st.text_input("Satuan (misal: pcs, box, liter)")
            qty = st.number_input("Jumlah Stok Awal", min_value=0, step=1)
            category = st.text_input("Kategori Barang", placeholder="Misal: Minuman, Makanan")
            if st.button("Tambah Barang Manual"):
                if not code_input.strip():
                    st.error("Kode Barang wajib diisi.")
                elif (not df_inv.empty) and (code_input in df_inv["code"].tolist()):
                    st.error(f"Kode Barang '{code_input}' sudah ada.")
                elif not name.strip():
                    st.error("Nama barang wajib diisi.")
                else:
                    inv_add_item(code_input, name.strip(), qty, unit.strip() or "-", category.strip() or "Uncategorized", brand=brand)
                    history_insert({
                        "action":"ADD_ITEM","item":name.strip(),"qty":int(qty),"stock":int(qty),
                        "unit":unit.strip() or "-", "user":st.session_state.username,
                        "event":"-","timestamp":timestamp()
                    }, brand=brand)
                    st.success(f"Barang '{name}' berhasil ditambahkan dengan kode {code_input}")
                    _safe_rerun()

        with tab2:
            st.info("Format Excel: **Kode Barang | Nama Barang | Qty | Satuan | Kategori**")
            # Template minimal
            tmpl = pd.DataFrame([{
                "Kode Barang":"ITM-0001","Nama Barang":"Contoh Produk","Qty":10,"Satuan":"pcs","Kategori":"Umum"
            }])
            def _template_bytes(df, sheet="Template Master"):
                bio = BytesIO()
                with pd.ExcelWriter(bio, engine="xlsxwriter") as w:
                    df.to_excel(w, sheet_name=sheet, index=False)
                bio.seek(0)
                return bio.read()
            st.download_button(
                "📥 Unduh Template Master Excel",
                data=_template_bytes(tmpl, "Template Master"),
                file_name=f"Template_Master_{st.session_state.current_brand.capitalize()}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
            fu = st.file_uploader("Upload File Excel Master", type=["xlsx"])
            if fu and st.button("Tambah dari Excel (Master)"):
                try:
                    df_new = pd.read_excel(fu, engine="openpyxl")
                    required = ["Kode Barang","Nama Barang","Qty","Satuan","Kategori"]
                    miss = [c for c in required if c not in df_new.columns]
                    if miss:
                        st.error(f"Kolom kurang: {', '.join(miss)}")
                    else:
                        errors, added = [], 0
                        existing_codes = set(df_inv["code"].tolist()) if not df_inv.empty else set()
                        for i, row in df_new.iterrows():
                            code = str(row["Kode Barang"]).strip() if pd.notna(row["Kode Barang"]) else ""
                            name = str(row["Nama Barang"]).strip() if pd.notna(row["Nama Barang"]) else ""
                            if not code or not name:
                                errors.append(f"Baris {i+2}: Kode/Nama wajib."); continue
                            if code in existing_codes:
                                errors.append(f"Baris {i+2}: Kode '{code}' sudah ada."); continue
                            qty  = int(pd.to_numeric(row["Qty"], errors="coerce") or 0)
                            unit = str(row["Satuan"]).strip() if pd.notna(row["Satuan"]) else "-"
                            cat  = str(row["Kategori"]).strip() if pd.notna(row["Kategori"]) else "Uncategorized"
                            inv_add_item(code, name, qty, unit, cat, brand=brand)
                            history_insert({
                                "action":"ADD_ITEM","item":name,"qty":qty,"stock":qty,"unit":unit,
                                "user":st.session_state.username,"event":"-","timestamp":timestamp()
                            }, brand=brand)
                            added += 1
                        if added: st.success(f"{added} item master berhasil ditambahkan.")
                        if errors: st.warning("Beberapa baris dilewati:\n- " + "\n- ".join(errors))
                        _safe_rerun()
                except Exception as e:
                    st.error(f"Gagal membaca Excel: {e}")

    elif menu == "Approve Request":
        st.markdown(f"## Approve / Reject Request Barang - Brand {st.session_state.current_brand.capitalize()}")
        st.divider()
        df_p = df_pending.copy()
        if df_p.empty:
            st.info("Tidak ada pending request.")
        else:
            # Pastikan kolom lengkap
            for k in ["attachment","trans_type","do_number","event","unit","user","date","code","item","qty","timestamp","type","id"]:
                if k not in df_p.columns: df_p[k] = None
            df_p["Lampiran"] = df_p["attachment"].apply(lambda x: "Ada" if x else "Tidak Ada")

            # Checkbox column seperti before
            if "approve_select_flags" not in st.session_state or len(st.session_state.approve_select_flags) != len(df_p):
                st.session_state.approve_select_flags = [False]*len(df_p)

            csel1, csel2 = st.columns([1,1])
            if csel1.button("Pilih semua"): st.session_state.approve_select_flags = [True]*len(df_p)
            if csel2.button("Kosongkan pilihan"): st.session_state.approve_select_flags = [False]*len(df_p)

            df_show = df_p.copy()
            df_show["Pilih"] = st.session_state.approve_select_flags
            col_cfg = {"Pilih": st.column_config.CheckboxColumn("Pilih", default=False)}
            for c in df_show.columns:
                if c != "Pilih": col_cfg[c] = st.column_config.TextColumn(c, disabled=True)
            edited_df = st.data_editor(df_show, key="editor_admin_approve", use_container_width=True, hide_index=True, column_config=col_cfg)
            st.session_state.approve_select_flags = edited_df["Pilih"].fillna(False).tolist()
            selected_rows = df_show[edited_df["Pilih"].fillna(False)].copy()

            col1, col2 = st.columns(2)
            if col1.button("Approve Selected"):
                if selected_rows.empty:
                    st.session_state.notification = {"type":"warning","message":"Pilih setidaknya satu item untuk di-approve."}
                    _safe_rerun()
                approved = 0
                # muat inventori terbaru
                cur_inv = load_inventory(brand=brand)
                by_code = {r["code"]: r for _, r in cur_inv.iterrows()}
                for _, req in selected_rows.iterrows():
                    rtype = str(req["type"]).upper()  # IN/OUT/RETURN
                    code  = req.get("code")
                    qty   = int(pd.to_numeric(req.get("qty",0), errors="coerce") or 0)
                    if code in by_code:
                        item_row = by_code[code]
                        new_stock = int(item_row["qty"])
                        if rtype == "IN": new_stock += qty
                        elif rtype == "OUT": new_stock -= qty
                        elif rtype == "RETURN": new_stock += qty
                        inv_update_qty(code, new_stock)
                        history_insert({
                            "action": f"APPROVE_{rtype}",
                            "item": req.get("item","-"),
                            "qty": qty,
                            "stock": new_stock,
                            "unit": req.get("unit","-"),
                            "user": req.get("user","-"),
                            "event": req.get("event","-"),
                            "do_number": req.get("do_number","-"),
                            "attachment": req.get("attachment"),
                            "date": req.get("date"),
                            "code": code,
                            "trans_type": req.get("trans_type"),
                            "timestamp": timestamp()
                        }, brand=brand)
                        if pd.notna(req.get("id")):
                            pending_delete_by_id(req["id"])
                        approved += 1
                st.session_state.notification = {"type":"success","message": f"{approved} request di-approve."}
                _safe_rerun()

            if col2.button("Reject Selected"):
                if selected_rows.empty:
                    st.session_state.notification = {"type":"warning","message":"Pilih setidaknya satu item untuk di-reject."}
                    _safe_rerun()
                rejected = 0
                for _, req in selected_rows.iterrows():
                    history_insert({
                        "action": f"REJECT_{str(req.get('type','-')).upper()}",
                        "item": req.get("item","-"),
                        "qty": int(pd.to_numeric(req.get("qty",0), errors="coerce") or 0),
                        "stock": "-",
                        "unit": req.get("unit","-"),
                        "user": req.get("user","-"),
                        "event": req.get("event","-"),
                        "do_number": req.get("do_number","-"),
                        "attachment": req.get("attachment"),
                        "date": req.get("date"),
                        "code": req.get("code"),
                        "trans_type": req.get("trans_type"),
                        "timestamp": timestamp()
                    }, brand=brand)
                    if pd.notna(req.get("id")):
                        pending_delete_by_id(req["id"])
                    rejected += 1
                st.session_state.notification = {"type":"success","message": f"{rejected} request di-reject."}
                _safe_rerun()

    elif menu == "Riwayat Lengkap":
        st.markdown(f"## Riwayat Lengkap - Brand {st.session_state.current_brand.capitalize()}")
        st.divider()
        if df_hist.empty:
            st.info("Belum ada riwayat.")
        else:
            all_keys = ["action","item","qty","stock","unit","user","event","do_number","attachment","timestamp","date","code","trans_type"]
            for k in all_keys:
                if k not in df_hist.columns: df_hist[k] = None
            df_hist['date_only'] = pd.to_datetime(df_hist['date'].fillna(df_hist['timestamp']), errors="coerce").dt.date

            def get_download_link(path):
                if path and isinstance(path,str) and os.path.exists(path):
                    with open(path, "rb") as f:
                        bytes_data = f.read()
                    b64 = base64.b64encode(bytes_data).decode()
                    return f'<a href="data:application/pdf;base64,{b64}" download="{os.path.basename(path)}">Unduh</a>'
                return 'Tidak Ada'
            df_hist['Lampiran'] = df_hist['attachment'].apply(get_download_link)

            col1, col2 = st.columns(2)
            start_date = col1.date_input("Tanggal Mulai", value=df_hist['date_only'].min())
            end_date = col2.date_input("Tanggal Akhir", value=df_hist['date_only'].max())

            col3, col4, col5 = st.columns(3)
            users = ["Semua Pengguna"] + sorted(df_hist["user"].dropna().astype(str).unique())
            selected_user = col3.selectbox("Filter Pengguna", users)
            actions = ["Semua Tipe"] + sorted(df_hist["action"].dropna().astype(str).unique())
            selected_action = col4.selectbox("Filter Tipe Aksi", actions)
            search_item = col5.text_input("Cari Nama Barang")

            df_filtered = df_hist.copy()
            df_filtered = df_filtered[(df_filtered['date_only'] >= start_date) & (df_filtered['date_only'] <= end_date)]
            if selected_user != "Semua Pengguna":
                df_filtered = df_filtered[df_filtered["user"].astype(str) == selected_user]
            if selected_action != "Semua Tipe":
                df_filtered = df_filtered[df_filtered["action"].astype(str) == selected_action]
            if search_item:
                df_filtered = df_filtered[df_filtered["item"].astype(str).str.contains(search_item, case=False, na=False)]

            show_cols = ["action","date","code","item","qty","unit","stock","trans_type","user","event","do_number","timestamp","Lampiran"]
            show_cols = [c for c in show_cols if c in df_filtered.columns]
            st.markdown(df_filtered[show_cols].to_html(escape=False, index=False), unsafe_allow_html=True)

    elif menu == "Export Laporan ke Excel":
        st.markdown(f"## Filter dan Unduh Laporan - Brand {st.session_state.current_brand.capitalize()}")
        st.divider()
        if df_inv.empty:
            st.info("Tidak ada data untuk diexport.")
        else:
            df_inventory_full = df_inv.rename(columns={"name":"Nama Barang","qty":"Qty","code":"Kode","unit":"Satuan"})
            if "category" not in df_inventory_full.columns: df_inventory_full["category"]="Uncategorized"
            df_inventory_full.rename(columns={"category":"Kategori"}, inplace=True)

            unique_categories = ["Semua Kategori"] + sorted(df_inventory_full["Kategori"].unique())
            selected_category = st.selectbox("Pilih Kategori", unique_categories)
            search_query = st.text_input("Cari berdasarkan Nama atau Kode")

            df_filtered = df_inventory_full.copy()
            if selected_category != "Semua Kategori":
                df_filtered = df_filtered[df_filtered["Kategori"] == selected_category]
            if search_query:
                df_filtered = df_filtered[
                    df_filtered["Nama Barang"].str.contains(search_query, case=False) |
                    df_filtered["Kode"].str.contains(search_query, case=False)
                ]

            st.markdown("### Preview Laporan")
            st.dataframe(df_filtered, use_container_width=True, hide_index=True)

            if not df_filtered.empty:
                @st.cache_data
                def to_excel_bytes(df):
                    return dataframe_to_excel_bytes(df, "Stok Barang Filtered")
                excel_data = to_excel_bytes(df_filtered)
                st.download_button(
                    label="Unduh Laporan Excel",
                    data=excel_data,
                    file_name=f"Laporan_Inventori_{st.session_state.current_brand.capitalize()}_Filter.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
            else:
                st.warning("Tidak ada data yang cocok dengan filter yang dipilih.")

    elif menu == "Reset Database":
        st.markdown(f"## Reset Database - Brand {st.session_state.current_brand.capitalize()}")
        st.divider()
        st.warning("Aksi ini tidak dapat dibatalkan. Pending & riwayat akan dikosongkan (inventori aman).")
        confirm = st.text_input("Ketik RESET untuk konfirmasi")
        if st.button("Reset Database") and confirm == "RESET":
            if ENABLE_BRAND:
                supabase.from_("pending_gulavit").delete().eq("brand", brand).execute()
                supabase.from_("history_gulavit").delete().eq("brand", brand).execute()
            else:
                supabase.from_("pending_gulavit").delete().neq("id", -1).execute()
                supabase.from_("history_gulavit").delete().neq("id", -1).execute()
            st.cache_data.clear()
            st.success("✅ Pending dan Riwayat berhasil direset!")
            _safe_rerun()

# ================== MENU USER ==================
elif role == "user":
    user_options = [
        "Dashboard",
        "Stock Card",
        "Request Barang IN",
        "Request Barang OUT",
        "Request Retur",
        "Lihat Riwayat"
    ]
    menu = st.sidebar.radio("📌 Menu User", user_options)

    if menu == "Dashboard":
        render_dashboard_pro(df_hist, df_inv, brand_label=st.session_state.current_brand.capitalize(), allow_download=True)

    elif menu == "Stock Card":
        st.markdown(f"## Stock Card Barang - Brand {st.session_state.current_brand.capitalize()}")
        st.divider()
        if df_hist.empty or df_inv.empty:
            st.info("Belum ada riwayat transaksi atau master barang.")
        else:
            item_names = sorted(df_inv["name"].unique().tolist())
            selected_item_name = st.selectbox("Pilih Barang", item_names)
            if selected_item_name:
                filtered_history = df_hist[df_hist["item"] == selected_item_name]
                filtered_history = filtered_history[
                    filtered_history["action"].astype(str).str.startswith(("APPROVE","ADD"))
                ].copy()
                if filtered_history.empty:
                    st.info("Tidak ada riwayat transaksi yang disetujui untuk barang ini.")
                else:
                    stock_card_data = []
                    current_balance = 0
                    for _, h in filtered_history.sort_values("timestamp").iterrows():
                        transaction_in = 0
                        transaction_out = 0
                        keterangan = "N/A"
                        act = str(h["action"])
                        if act == "ADD_ITEM":
                            transaction_in = h["qty"]; current_balance += transaction_in
                            keterangan = "Initial Stock"
                        elif act == "APPROVE_IN":
                            transaction_in = h["qty"]; current_balance += transaction_in
                            keterangan = f"Request IN by {h['user']}"
                            do_number = h.get('do_number', '-')
                            if pd.notna(do_number) and do_number != '-': keterangan += f" (No. DO: {do_number})"
                        elif act == "APPROVE_OUT":
                            transaction_out = h["qty"]; current_balance -= transaction_out
                            tipe = h.get("trans_type","-")
                            keterangan = f"Request OUT ({tipe}) by {h['user']} for event: {h.get('event', '-')}"
                        elif act == "APPROVE_RETURN":
                            transaction_in = h["qty"]; current_balance += transaction_in
                            keterangan = f"Retur by {h['user']} for event: {h.get('event', '-')}"
                        else:
                            continue
                        stock_card_data.append({
                            "Tanggal": h.get("date", h["timestamp"]),
                            "Keterangan": keterangan,
                            "Masuk (IN)": transaction_in if transaction_in > 0 else "-",
                            "Keluar (OUT)": transaction_out if transaction_out > 0 else "-",
                            "Saldo Akhir": current_balance
                        })
                    st.dataframe(pd.DataFrame(stock_card_data), use_container_width=True, hide_index=True)

    elif menu == "Request Barang IN":
        st.markdown(f"## Request Barang Masuk (Manual) - Brand {st.session_state.current_brand.capitalize()}")
        st.divider()
        if df_inv.empty:
            st.info("Belum ada master barang. Silakan hubungi admin.")
        else:
            items = df_inv.to_dict(orient="records")
            col1, col2 = st.columns(2)
            idx = col1.selectbox(
                "Pilih Barang", range(len(items)),
                format_func=lambda x: f"{items[x]['name']} ({items[x]['qty']} {items[x].get('unit', '-')})"
            )
            qty = col2.number_input("Jumlah", min_value=1, step=1)

            if st.button("Tambah Item IN"):
                st.session_state.req_in_items.append({
                    "item": items[idx]["name"],
                    "code": items[idx]["code"],
                    "qty": int(qty),
                    "unit": items[idx].get("unit","-"),
                    "event": "-"
                })
                st.success("Item IN ditambahkan ke daftar.")

            if st.session_state.req_in_items:
                st.subheader("Daftar Item Request IN")
                if "in_select_flags" not in st.session_state or len(st.session_state.in_select_flags) != len(st.session_state.req_in_items):
                    st.session_state.in_select_flags = [False]*len(st.session_state.req_in_items)

                cA, cB = st.columns([1,1])
                if cA.button("Pilih semua", key="in_sel_all"):
                    st.session_state.in_select_flags = [True]*len(st.session_state.req_in_items)
                if cB.button("Kosongkan pilihan", key="in_sel_none"):
                    st.session_state.in_select_flags = [False]*len(st.session_state.req_in_items)

                df_in = pd.DataFrame(st.session_state.req_in_items)
                df_in["Pilih"] = st.session_state.in_select_flags
                edited_df_in = st.data_editor(df_in, key="editor_in", use_container_width=True, hide_index=True)
                st.session_state.in_select_flags = edited_df_in["Pilih"].fillna(False).tolist()

                st.divider()
                st.subheader("Informasi Wajib")
                do_number = st.text_input("Nomor Surat Jalan (wajib)", placeholder="Masukkan Nomor Surat Jalan")
                uploaded_file = st.file_uploader("Upload PDF Delivery Order / Surat Jalan (wajib)", type=["pdf"])

                if st.button("Ajukan Request IN Terpilih"):
                    mask = st.session_state.in_select_flags
                    if not any(mask):
                        st.warning("Pilih setidaknya satu item untuk diajukan.")
                    elif not do_number.strip():
                        st.error("Nomor Surat Jalan wajib diisi.")
                    elif not uploaded_file:
                        st.error("PDF Surat Jalan wajib diupload.")
                    else:
                        timestamp_str = datetime.now().strftime("%Y%m%d%H%M%S")
                        file_ext = uploaded_file.name.split(".")[-1]
                        attachment_path = os.path.join(UPLOADS_DIR, f"{st.session_state.username}_{timestamp_str}.{file_ext}")
                        with open(attachment_path, "wb") as f:
                            f.write(uploaded_file.getbuffer())

                        submit_count = 0
                        new_state, new_flags = [], []
                        for selected, rec in zip(mask, st.session_state.req_in_items):
                            if selected:
                                base = {
                                    "date": None,
                                    "code": rec["code"],
                                    "item": rec["item"],
                                    "qty": int(rec["qty"]),
                                    "unit": rec.get("unit","-"),
                                    "event": "-",
                                    "trans_type": None,
                                    "do_number": do_number.strip(),
                                    "attachment": attachment_path,
                                    "user": st.session_state.username,
                                    "timestamp": timestamp(),
                                }
                                norm = normalize_out_record(base)
                                pending_insert("IN", norm, brand=brand)
                                submit_count += 1
                            else:
                                new_state.append(rec); new_flags.append(False)
                        st.session_state.req_in_items = new_state
                        st.session_state.in_select_flags = new_flags
                        st.success(f"{submit_count} request IN diajukan & menunggu approval.")
                        _safe_rerun()

    elif menu == "Request Barang OUT":
        st.markdown(f"## Request Barang Keluar (Multi Item) - Brand {st.session_state.current_brand.capitalize()}")
        st.divider()
        if df_inv.empty:
            st.info("Belum ada master barang. Silakan hubungi admin.")
        else:
            items = df_inv.to_dict(orient="records")
            col1, col2 = st.columns(2)
            idx = col1.selectbox(
                "Pilih Barang", range(len(items)),
                format_func=lambda x: f"{items[x]['name']} (Stok: {items[x]['qty']} {items[x].get('unit','-')})"
            )
            max_qty = int(pd.to_numeric(items[idx].get("qty",0), errors="coerce") or 0)
            if max_qty < 1:
                qty = 0
                col2.number_input("Jumlah", min_value=0, max_value=0, step=1, value=0, disabled=True)
                st.warning("Stok item ini 0. Tidak bisa menambah request OUT.")
            else:
                qty = col2.number_input("Jumlah", min_value=1, max_value=max_qty, step=1)

            tipe = st.selectbox("Tipe Transaksi (wajib)", TRANS_TYPES, index=0)
            event_manual = st.text_input("Nama Event (wajib)", placeholder="Misal: Pameran, Acara Kantor")

            if st.button("Tambah Item OUT (Manual)"):
                if max_qty < 1:
                    st.error("Stok 0 — tidak bisa menambah OUT untuk item ini.")
                elif not event_manual.strip():
                    st.error("Event wajib diisi.")
                elif qty < 1:
                    st.error("Jumlah harus minimal 1.")
                else:
                    base = {
                        "date": datetime.now().strftime("%Y-%m-%d"),
                        "code": items[idx]["code"],
                        "item": items[idx]["name"],
                        "qty": int(qty),
                        "unit": items[idx].get("unit","-"),
                        "event": event_manual.strip(),
                        "trans_type": tipe,
                        "user": st.session_state.username,
                    }
                    st.session_state.req_out_items.append(normalize_out_record(base))
                    st.success("Item OUT (manual) ditambahkan ke daftar.")

            if st.session_state.req_out_items:
                st.subheader("Daftar Item Request OUT")
                df_out = pd.DataFrame(st.session_state.req_out_items)
                pref = [c for c in ["date","code","item","qty","unit","event","trans_type"] if c in df_out.columns]
                df_out = df_out[pref]

                if "out_select_flags" not in st.session_state or len(st.session_state.out_select_flags) != len(st.session_state.req_out_items):
                    st.session_state.out_select_flags = [False]*len(st.session_state.req_out_items)

                c1, c2 = st.columns([1,1])
                if c1.button("Pilih semua", key="out_sel_all"): st.session_state.out_select_flags = [True]*len(st.session_state.req_out_items)
                if c2.button("Kosongkan pilihan", key="out_sel_none"): st.session_state.out_select_flags = [False]*len(st.session_state.req_out_items)

                df_out["Pilih"] = st.session_state.out_select_flags
                edited_df_out = st.data_editor(df_out, key="editor_out", use_container_width=True, hide_index=True)
                st.session_state.out_select_flags = edited_df_out["Pilih"].fillna(False).tolist()

                if st.button("Hapus Item Terpilih", key="delete_out"):
                    mask = st.session_state.out_select_flags
                    if any(mask):
                        st.session_state.req_out_items = [rec for rec, keep in zip(st.session_state.req_out_items, [not x for x in mask]) if keep]
                        st.session_state.out_select_flags = [False]*len(st.session_state.req_out_items)
                        _safe_rerun()
                    else:
                        st.info("Tidak ada baris yang dipilih.")

                st.divider()
                if st.button("Ajukan Request OUT Terpilih"):
                    mask = st.session_state.out_select_flags
                    if not any(mask):
                        st.warning("Pilih setidaknya satu item untuk diajukan.")
                    else:
                        submitted = 0
                        new_state, new_flags = [], []
                        for selected, rec in zip(mask, st.session_state.req_out_items):
                            if selected:
                                norm = normalize_out_record({**rec, "user": st.session_state.username})
                                pending_insert("OUT", norm, brand=brand)
                                submitted += 1
                            else:
                                new_state.append(rec); new_flags.append(False)
                        st.session_state.req_out_items = new_state
                        st.session_state.out_select_flags = new_flags
                        st.success(f"{submitted} request OUT diajukan & menunggu approval.")
                        _safe_rerun()

    elif menu == "Request Retur":
        st.markdown(f"## Request Retur - Brand {st.session_state.current_brand.capitalize()}")
        st.divider()
        if df_inv.empty:
            st.info("Belum ada master barang.")
        else:
            items = df_inv.to_dict(orient="records")
            col1, col2 = st.columns(2)
            idx = col1.selectbox(
                "Pilih Barang", range(len(items)),
                format_func=lambda x: f"{items[x]['name']} (Stok: {items[x]['qty']} {items[x].get('unit','-')})"
            )
            qty = col2.number_input("Jumlah Retur", min_value=1, step=1)
            event_ret = st.text_input("Keterangan Retur / Event", placeholder="Misal: Sisa Event X")

            if st.button("Tambah Item Retur"):
                base = {
                    "date": datetime.now().strftime("%Y-%m-%d"),
                    "code": items[idx]["code"],
                    "item": items[idx]["name"],
                    "qty": int(qty),
                    "unit": items[idx].get("unit","-"),
                    "event": event_ret or "-",
                    "user": st.session_state.username,
                }
                st.session_state.req_ret_items.append(normalize_return_record(base))
                st.success("Item Retur ditambahkan ke daftar.")

            if st.session_state.req_ret_items:
                st.subheader("Daftar Item Retur")
                df_ret = pd.DataFrame(st.session_state.req_ret_items)
                if "ret_select_flags" not in st.session_state or len(st.session_state.ret_select_flags) != len(st.session_state.req_ret_items):
                    st.session_state.ret_select_flags = [False]*len(st.session_state.req_ret_items)

                c1, c2 = st.columns([1,1])
                if c1.button("Pilih semua", key="ret_sel_all"): st.session_state.ret_select_flags = [True]*len(st.session_state.req_ret_items)
                if c2.button("Kosongkan pilihan", key="ret_sel_none"): st.session_state.ret_select_flags = [False]*len(st.session_state.req_ret_items)

                df_ret["Pilih"] = st.session_state.ret_select_flags
                edited_df_ret = st.data_editor(df_ret, key="editor_ret", use_container_width=True, hide_index=True)
                st.session_state.ret_select_flags = edited_df_ret["Pilih"].fillna(False).tolist()

                st.divider()
                if st.button("Ajukan Request Retur Terpilih"):
                    mask = st.session_state.ret_select_flags
                    if not any(mask):
                        st.warning("Pilih setidaknya satu item untuk diajukan.")
                    else:
                        submitted = 0
                        new_state, new_flags = [], []
                        for selected, rec in zip(mask, st.session_state.req_ret_items):
                            if selected:
                                pending_insert("RETURN", rec, brand=brand)
                                submitted += 1
                            else:
                                new_state.append(rec); new_flags.append(False)
                        st.session_state.req_ret_items = new_state
                        st.session_state.ret_select_flags = new_flags
                        st.success(f"{submitted} request Retur diajukan & menunggu approval.")
                        _safe_rerun()

    elif menu == "Lihat Riwayat":
        st.markdown(f"## Riwayat - Brand {st.session_state.current_brand.capitalize()}")
        st.divider()
        if df_hist.empty:
            st.info("Belum ada riwayat.")
        else:
            cols_show = ["action","date","code","item","qty","unit","stock","trans_type","user","event","do_number","timestamp"]
            for c in cols_show:
                if c not in df_hist.columns: df_hist[c] = None
            st.dataframe(df_hist[cols_show].sort_values("timestamp", ascending=False), use_container_width=True, hide_index=True)

