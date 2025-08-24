# app.py
import streamlit as st
import pandas as pd
from supabase import create_client, Client
import datetime

# --- Kredensial dan Inisialisasi Supabase ---
SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# --- Fungsi untuk Memuat Data dari Database ---
# Menggunakan st.cache_data untuk menghemat panggilan ke database
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
        st.experimental_rerun()
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

# --- Tampilan Utama Aplikasi Setelah Login ---
st.header(f"Selamat Datang, {st.session_state.role.capitalize()}!")
st.sidebar.title("Navigasi")

# Memuat data sekali dan menyimpannya di cache
_, inventory, pending, history = load_all_data()
df_inventory = pd.DataFrame(inventory)
df_pending = pd.DataFrame(pending)
df_history = pd.DataFrame(history)

# Sidebar
menu = ["Dashboard", "Manajemen Inventaris", "Permintaan & Persetujuan", "Laporan & Riwayat"]
choice = st.sidebar.selectbox("Pilih Halaman", menu)

# --- Fungsionalitas Halaman ---

if choice == "Dashboard":
    st.subheader("Ringkasan Data Inventaris")
    if not df_inventory.empty:
        st.dataframe(df_inventory, use_container_width=True)
    else:
        st.info("Belum ada data inventaris. Mohon hubungi admin untuk menginput data.")
    
    st.subheader("Daftar Permintaan Menunggu Persetujuan")
    if not df_pending.empty:
        st.dataframe(df_pending, use_container_width=True)
    else:
        st.info("Tidak ada permintaan yang menunggu.")

elif choice == "Manajemen Inventaris":
    if st.session_state.role in ["approver", "admin"]:
        # --- Fitur Tambah Barang Baru (Stock In Awal) ---
        st.subheader("Tambah Data Inventaris Baru")
        with st.form(key='inventory_form'):
            new_code = st.text_input("Kode Barang")
            new_item = st.text_input("Nama Barang")
            new_unit = st.text_input("Unit")
            new_balance = st.number_input("Kuantitas (Balance)", min_value=0, step=1)
            submit_button = st.form_submit_button(label='Tambah Barang')
        
        if submit_button:
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
                    st.experimental_rerun()
                except Exception as e:
                    st.error(f"Terjadi kesalahan: {e}")
            else:
                st.warning("Mohon lengkapi semua kolom.")

        st.markdown("---")
        
        # --- Fitur Catat Transaksi Stock In/Out ---
        st.subheader("Catat Transaksi Harian (Stock In/Out)")
        with st.form(key='transaksi_form'):
            if not df_inventory.empty:
                item_code = st.selectbox("Pilih Kode Barang", df_inventory['code'])
                trans_type = st.radio("Jenis Transaksi", ["Stock In", "Stock Out"])
                qty = st.number_input("Kuantitas", min_value=1, step=1)
                submit_button = st.form_submit_button("Catat Transaksi")

                if submit_button:
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
                            "date": datetime.datetime.now().isoformat(),
                            "code": item_code,
                            "item": selected_item['item'],
                            "qty": qty,
                            "unit": selected_item['unit'],
                            "trans_type": trans_type,
                            "event": f"{trans_type} oleh {st.session_state.username}",
                            "do_number": "",
                            "timestamp": datetime.datetime.now().isoformat()
                        }
                        supabase.from_("history_gulavit").insert(transaksi_data).execute()
                        st.success(f"Transaksi {trans_type} berhasil dicatat.")
                        st.experimental_rerun()
                    except Exception as e:
                        st.error(f"Gagal mencatat transaksi: {e}")
            else:
                st.info("Belum ada data inventaris untuk dicatat.")
    else:
        st.warning("Anda tidak memiliki izin untuk mengakses halaman ini.")

elif choice == "Permintaan & Persetujuan":
    # --- Fungsionalitas Pengguna Biasa (User) ---
    if st.session_state.role == "user":
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
                        "date": datetime.datetime.now().isoformat(),
                        "code": req_item_code,
                        "item": selected_item['item'],
                        "qty": req_qty,
                        "unit": selected_item['unit'],
                        "trans_type": "Stock Out",
                        "event": "Menunggu Persetujuan",
                        "timestamp": datetime.datetime.now().isoformat()
                    }
                    try:
                        supabase.from_("pending_gulavit").insert(req_data).execute()
                        st.success("Permintaan berhasil diajukan dan menunggu persetujuan.")
                        st.experimental_rerun()
                    except Exception as e:
                        st.error(f"Gagal mengajukan permintaan: {e}")
            else:
                st.info("Tidak ada barang yang tersedia untuk diminta.")
    
    # --- Fungsionalitas Approver/Admin ---
    elif st.session_state.role in ["approver", "admin"]:
        st.subheader("Daftar Permintaan Masuk")
        if not df_pending.empty:
            st.dataframe(df_pending, use_container_width=True)
            with st.form(key='approval_form'):
                req_id = st.selectbox("Pilih Permintaan untuk Aksi", df_pending['id'])
                action = st.radio("Aksi", ["Setujui", "Tolak"])
                approve_submit = st.form_submit_button("Proses Permintaan")
            
            if approve_submit:
                selected_request = df_pending[df_pending['id'] == req_id]
                if not selected_request.empty:
                    selected_request_dict = selected_request.iloc[0].to_dict()
                    try:
                        if action == "Setujui":
                            selected_item = df_inventory[df_inventory['code'] == selected_request_dict['code']].iloc[0]
                            new_balance = selected_item['balance'] - selected_request_dict['qty']
                            
                            supabase.from_("inventory_gulavit").update({"balance": new_balance}).eq("code", selected_item['code']).execute()
                            
                            supabase.from_("pending_gulavit").delete().eq("id", req_id).execute()
                            
                            selected_request_dict['event'] = "Disetujui"
                            supabase.from_("history_gulavit").insert(selected_request_dict).execute()
                            
                            st.success("Permintaan berhasil disetujui dan dicatat.")
                        else: # Tolak
                            supabase.from_("pending_gulavit").delete().eq("id", req_id).execute()
                            st.warning("Permintaan berhasil ditolak.")
                        
                        st.experimental_rerun()
                    except Exception as e:
                        st.error(f"Gagal memproses permintaan: {e}")
                else:
                    st.warning("Permintaan tidak ditemukan.")
        else:
            st.info("Tidak ada permintaan yang menunggu persetujuan.")
    else:
        st.warning("Anda tidak memiliki izin untuk mengakses halaman ini.")

elif choice == "Laporan & Riwayat":
    st.subheader("Riwayat Transaksi")
    if not df_history.empty:
        st.dataframe(df_history, use_container_width=True)
    else:
        st.info("Belum ada riwayat transaksi yang tercatat.")
