# app.py
import streamlit as st
import json
import os
from datetime import datetime
import pandas as pd
import base64
from io import BytesIO
from supabase import create_client, Client
import uuid

# --- Kredensial dan Inisialisasi Supabase ---
SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# --- Optional grafik ---
try:
    import altair as alt
    _ALT_OK = True
except Exception:
    _ALT_OK = False

# --- Konfigurasi ---
UPLOADS_DIR = "uploads"
BANNER_URL = "https://media.licdn.com/dms/image/v2/D563DAQFDri8xlKNIvg/image-scale_191_1128/image-scale_191_1128/0/1678337293506/pesona_inti_rasa_cover?e=2147483647&v=beta&t=vHi0xtyAZsT9clHb0yBYPE8M9IaO2dNY6Cb_Vs3Ddlo"
ICON_URL = "https://i.ibb.co/7C969s2/gulavit.png"

# --- Fungsi untuk Memuat Data dari Database ---
@st.cache_data(ttl=600)
def load_all_data():
    try:
        users_data = supabase.from_("users_gulavit").select("*").execute().data
        inventory_data = supabase.from_("inventory_gulavit").select("*").execute().data
        pending_data = supabase.from_("pending_gulavit").select("*").execute().data
        history_data = supabase.from_("history_gulavit").select("*").execute().data
        return users_data, inventory_data, pending_data, history_data
    except Exception as e:
        st.error(f"Gagal memuat data dari Supabase. Pastikan tabel sudah dibuat. Error: {e}")
        return [], [], [], []

# --- Fungsi Autentikasi Login ---
def check_login(username, password):
    users, _, _, _ = load_all_data()
    df_users = pd.DataFrame(users)
    user_match = df_users[(df_users['username'] == username) & (df_users['password'] == password)]
    
    if not user_match.empty:
        st.session_state.authenticated = True
        st.session_state.username = user_match.iloc[0]['username']
        st.session_state.role = user_match.iloc[0]['role']
        st.rerun()
    else:
        st.error("Username atau password salah.")

# --- Tampilan Halaman Login ---
if 'authenticated' not in st.session_state:
    st.session_state.authenticated = False

if not st.session_state.authenticated:
    st.title("Halaman Login Aplikasi Gudang Gulavit")
    with st.form("login_form"):
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        submit_button = st.form_submit_button("Login")
        if submit_button:
            check_login(username, password)
    st.stop()

# --- Logo & Header ---
col_logo, col_title = st.columns([1, 6])
with col_logo:
    st.image(ICON_URL)
with col_title:
    st.header("Sistem Manajemen Gudang Gulavit")
st.markdown("---")

# --- Logika Utama Aplikasi ---
_, inventory, pending, history = load_all_data()
df_inventory = pd.DataFrame(inventory)
df_pending = pd.DataFrame(pending)
df_history = pd.DataFrame(history)

# --- Tampilan Berdasarkan Peran Pengguna ---
st.sidebar.markdown(f"**Halo, {st.session_state.username}!**")
st.sidebar.markdown(f"**Peran:** {st.session_state.role.capitalize()}")

if st.session_state.role == "admin":
    # --- Tampilan Admin ---
    st.subheader("Dashboard Admin")
    st.markdown("### Ringkasan")
    st.metric("Total Barang", len(df_inventory))
    st.metric("Permintaan Menunggu", len(df_pending))
    
    # ... Anda bisa menambahkan tabel dan grafik di sini
    
    st.markdown("### Manajemen Inventaris")
    # --- Input Barang Baru ---
    st.markdown("#### Input Barang Baru")
    with st.form(key='add_item_form'):
        new_code = st.text_input("Kode Barang")
        new_item = st.text_input("Nama Barang")
        new_unit = st.text_input("Unit")
        new_balance = st.number_input("Kuantitas Awal", min_value=0, step=1)
        add_item_button = st.form_submit_button("Tambah Barang")

    if add_item_button:
        if new_code and new_item and new_unit:
            new_data = {
                "code": new_code,
                "item": new_item,
                "unit": new_unit,
                "balance": new_balance
            }
            try:
                supabase.from_("inventory_gulavit").insert(new_data).execute()
                st.success("Barang berhasil ditambahkan!")
                st.rerun()
            except Exception as e:
                st.error(f"Terjadi kesalahan: {e}")
        else:
            st.warning("Mohon lengkapi semua kolom.")

    # --- Catat Transaksi ---
    st.markdown("#### Catat Transaksi")
    with st.form(key='admin_transaksi_form'):
        if not df_inventory.empty:
            item_code = st.selectbox("Pilih Kode Barang", df_inventory['code'])
            trans_type = st.radio("Jenis Transaksi", ["Stock In", "Stock Out"])
            qty = st.number_input("Kuantitas", min_value=1, step=1)
            admin_submit = st.form_submit_button("Catat Transaksi")
            
            if admin_submit:
                selected_item = df_inventory[df_inventory['code'] == item_code].iloc[0]
                current_balance = selected_item['balance']
                
                if trans_type == "Stock In":
                    new_balance = current_balance + qty
                elif trans_type == "Stock Out":
                    if qty > current_balance:
                        st.warning("Kuantitas stock out melebihi ketersediaan.")
                        st.stop()
                    new_balance = current_balance - qty
                
                try:
                    # Update inventaris
                    supabase.from_("inventory_gulavit").update({"balance": new_balance}).eq("code", item_code).execute()
                    # Tambahkan ke riwayat
                    transaksi_data = {
                        "date": datetime.now().isoformat(),
                        "code": item_code,
                        "item": selected_item['item'],
                        "qty": qty,
                        "unit": selected_item['unit'],
                        "trans_type": trans_type,
                        "event": f"{trans_type} oleh {st.session_state.username}",
                        "do_number": "",
                        "timestamp": datetime.now().isoformat()
                    }
                    supabase.from_("history_gulavit").insert(transaksi_data).execute()
                    st.success(f"Transaksi {trans_type} berhasil dicatat.")
                    st.rerun()
                except Exception as e:
                    st.error(f"Gagal mencatat transaksi: {e}")
        else:
            st.info("Belum ada data inventaris untuk dicatat.")

    # --- Persetujuan Permintaan ---
    st.markdown("### Permintaan Menunggu Persetujuan")
    if not df_pending.empty:
        st.dataframe(df_pending, use_container_width=True)
        with st.form(key='admin_approval_form'):
            req_id = st.selectbox("Pilih Permintaan", df_pending['id'])
            action = st.radio("Aksi", ["Setujui", "Tolak"])
            approve_submit = st.form_submit_button("Proses Permintaan")
        
        if approve_submit:
            selected_request = df_pending[df_pending['id'] == req_id].iloc[0]
            try:
                if action == "Setujui":
                    selected_item = df_inventory[df_inventory['code'] == selected_request['code']].iloc[0]
                    new_balance = selected_item['balance'] - selected_request['qty']
                    
                    supabase.from_("inventory_gulavit").update({"balance": new_balance}).eq("code", selected_item['code']).execute()
                    
                    supabase.from_("pending_gulavit").delete().eq("id", req_id).execute()
                    
                    selected_request_dict = selected_request.to_dict()
                    selected_request_dict['event'] = "Disetujui"
                    supabase.from_("history_gulavit").insert(selected_request_dict).execute()
                    
                    st.success("Permintaan berhasil disetujui dan dicatat.")
                else: # Tolak
                    supabase.from_("pending_gulavit").delete().eq("id", req_id).execute()
                    st.warning("Permintaan berhasil ditolak.")
                
                st.rerun()
            except Exception as e:
                st.error(f"Gagal memproses permintaan: {e}")
    else:
        st.info("Tidak ada permintaan yang menunggu persetujuan.")


elif st.session_state.role == "approver":
    # --- Tampilan Approver ---
    st.markdown("### Permintaan Menunggu Persetujuan")
    if not df_pending.empty:
        st.dataframe(df_pending, use_container_width=True)
        with st.form(key='approver_approval_form'):
            req_id = st.selectbox("Pilih Permintaan", df_pending['id'])
            action = st.radio("Aksi", ["Setujui", "Tolak"])
            approve_submit = st.form_submit_button("Proses Permintaan")
        
        if approve_submit:
            selected_request = df_pending[df_pending['id'] == req_id].iloc[0]
            try:
                if action == "Setujui":
                    selected_item = df_inventory[df_inventory['code'] == selected_request['code']].iloc[0]
                    new_balance = selected_item['balance'] - selected_request['qty']
                    
                    supabase.from_("inventory_gulavit").update({"balance": new_balance}).eq("code", selected_item['code']).execute()
                    
                    supabase.from_("pending_gulavit").delete().eq("id", req_id).execute()
                    
                    selected_request_dict = selected_request.to_dict()
                    selected_request_dict['event'] = "Disetujui"
                    supabase.from_("history_gulavit").insert(selected_request_dict).execute()
                    
                    st.success("Permintaan berhasil disetujui dan dicatat.")
                else: # Tolak
                    supabase.from_("pending_gulavit").delete().eq("id", req_id).execute()
                    st.warning("Permintaan berhasil ditolak.")
                
                st.rerun()
            except Exception as e:
                st.error(f"Gagal memproses permintaan: {e}")
    else:
        st.info("Tidak ada permintaan yang menunggu persetujuan.")

elif st.session_state.role == "user":
    # --- Tampilan User ---
    st.subheader("Ajukan Permintaan Barang")
    with st.form(key='request_form'):
        if not df_inventory.empty:
            req_item_code = st.selectbox("Pilih Kode Barang", df_inventory['code'])
            req_qty = st.number_input("Kuantitas yang Diminta", min_value=1, step=1)
            req_submit = st.form_submit_button("Ajukan Permintaan")

            if req_submit:
                selected_item = df_inventory[df_inventory['code'] == req_item_code].iloc[0]
                req_data = {
                    "user": st.session_state.username,
                    "type": "Permintaan",
                    "date": datetime.now().isoformat(),
                    "code": req_item_code,
                    "item": selected_item['item'],
                    "qty": req_qty,
                    "unit": selected_item['unit'],
                    "trans_type": "Stock Out",
                    "event": "Menunggu Persetujuan",
                    "timestamp": datetime.now().isoformat()
                }
                try:
                    supabase.from_("pending_gulavit").insert(req_data).execute()
                    st.success("Permintaan berhasil diajukan dan menunggu persetujuan.")
                    st.rerun()
                except Exception as e:
                    st.error(f"Gagal mengajukan permintaan: {e}")
        else:
            st.info("Tidak ada barang yang tersedia untuk diminta.")

st.sidebar.markdown("---")
if st.sidebar.button("Logout"):
    st.session_state.authenticated = False
    st.rerun()
