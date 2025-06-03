import telebot
from telebot import types
import sqlite3
import requests
import json
import threading
import time
import random
import string
from datetime import datetime
import zipfile
import io
import os

# Konfigurasi
BOT_TOKEN = 'TOKEN_BOT'
DO_BASE_URL = "https://api.digitalocean.com/v2/"
BACKUP_CHAT_ID = CHATID  # Chat ID untuk mengirim backup

# Inisialisasi bot
bot = telebot.TeleBot(BOT_TOKEN)

# Helper Functions
def generate_strong_password(length=16):
    characters = string.ascii_letters + string.digits + "!@#$%^&*()"
    while True:
        password = ''.join(random.choice(characters) for _ in range(length))
        if (any(c.isdigit() for c in password) and 
            any(c in "!@#$%^&*()" for c in password)):
            return password

# Inisialisasi database
conn = sqlite3.connect('bot.db', check_same_thread=False)
cursor = conn.cursor()

# Create tables if not exists
cursor.execute('''
    CREATE TABLE IF NOT EXISTS do_accounts (
        account_id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        account_name TEXT NOT NULL,
        api_token TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
''')

cursor.execute('''
    CREATE TABLE IF NOT EXISTS droplets (
        id INTEGER PRIMARY KEY,
        user_id INTEGER NOT NULL,
        account_id INTEGER NOT NULL,
        droplet_id INTEGER NOT NULL,
        name TEXT NOT NULL,
        ip_address TEXT,
        status TEXT,
        size_slug TEXT,
        password TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(user_id) REFERENCES do_accounts(user_id),
        FOREIGN KEY(account_id) REFERENCES do_accounts(account_id)
    )
''')
conn.commit()

# Backup Functions
def create_backup():
    # Create a zip file in memory
    backup_data = io.BytesIO()
    
    with zipfile.ZipFile(backup_data, 'w', zipfile.ZIP_DEFLATED) as zipf:
        # Add database file
        zipf.write('bot.db', arcname='bot.db')
        
        # You can add other files if needed
        # zipf.write('other_file.txt', arcname='other_file.txt')
    
    backup_data.seek(0)
    return backup_data

def auto_backup():
    while True:
        try:
            backup_data = create_backup()
            timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            backup_name = f"bot_backup_{timestamp}.zip"
            
            bot.send_document(
                BACKUP_CHAT_ID,
                (backup_name, backup_data),
                caption=f"🔄 Auto Backup Bot Database\n⏰ {timestamp}"
            )
        except Exception as e:
            print(f"Backup error: {e}")
        
        time.sleep(1 * 3600)  # Wait 1 Jam

def restore_database(file_info):
    try:
        # Download the file
        file = bot.get_file(file_info.file_id)
        downloaded_file = bot.download_file(file.file_path)
        
        # Extract the zip file
        with zipfile.ZipFile(io.BytesIO(downloaded_file), 'r') as zipf:
            # Close current connection
            global conn, cursor
            conn.close()
            
            # Extract and overwrite the database file
            zipf.extract('bot.db')
            
            # Reconnect to database
            conn = sqlite3.connect('bot.db', check_same_thread=False)
            cursor = conn.cursor()
            
            return True
    except Exception as e:
        print(f"Restore error: {e}")
        return False

# Start backup thread
backup_thread = threading.Thread(target=auto_backup, daemon=True)
backup_thread.start()

def get_user_accounts(user_id):
    cursor.execute("SELECT account_id, account_name, api_token FROM do_accounts WHERE user_id=?", (user_id,))
    return cursor.fetchall()

def get_account_token(account_id):
    cursor.execute("SELECT api_token FROM do_accounts WHERE account_id=?", (account_id,))
    result = cursor.fetchone()
    return result[0] if result else None

def add_account(user_id, account_name, api_token):
    cursor.execute("INSERT INTO do_accounts (user_id, account_name, api_token) VALUES (?, ?, ?)", 
                  (user_id, account_name, api_token))
    conn.commit()
    return cursor.lastrowid

def delete_account(account_id):
    cursor.execute("DELETE FROM do_accounts WHERE account_id=?", (account_id,))
    cursor.execute("DELETE FROM droplets WHERE account_id=?", (account_id,))
    conn.commit()

def save_droplet(user_id, account_id, droplet_id, name, ip_address=None, status='new', size_slug=None, password=None):
    cursor.execute('''
        INSERT INTO droplets (user_id, account_id, droplet_id, name, ip_address, status, size_slug, password)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', (user_id, account_id, droplet_id, name, ip_address, status, size_slug, password))
    conn.commit()

def get_user_droplets(user_id, account_id=None):
    if account_id:
        cursor.execute("SELECT droplet_id, name, ip_address, status, size_slug, password FROM droplets WHERE user_id=? AND account_id=?", 
                     (user_id, account_id))
    else:
        cursor.execute("SELECT droplet_id, name, ip_address, status, size_slug, password FROM droplets WHERE user_id=?", 
                     (user_id,))
    return cursor.fetchall()

def get_droplet_info(user_id, droplet_id):
    cursor.execute("SELECT name, ip_address, status, size_slug, password FROM droplets WHERE user_id=? AND droplet_id=?", 
                  (user_id, droplet_id))
    return cursor.fetchone()

def update_droplet_status(droplet_id, status, ip_address=None, size_slug=None):
    if ip_address and size_slug:
        cursor.execute("UPDATE droplets SET status=?, ip_address=?, size_slug=? WHERE droplet_id=?", 
                      (status, ip_address, size_slug, droplet_id))
    elif ip_address:
        cursor.execute("UPDATE droplets SET status=?, ip_address=? WHERE droplet_id=?", 
                      (status, ip_address, droplet_id))
    elif size_slug:
        cursor.execute("UPDATE droplets SET status=?, size_slug=? WHERE droplet_id=?", 
                      (status, size_slug, droplet_id))
    else:
        cursor.execute("UPDATE droplets SET status=? WHERE droplet_id=?", 
                      (status, droplet_id))
    conn.commit()

def delete_droplet_from_db(droplet_id):
    cursor.execute("DELETE FROM droplets WHERE droplet_id=?", (droplet_id,))
    conn.commit()

def do_api_request(method, endpoint, token, data=None):
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}"
    }
    
    url = f"{DO_BASE_URL}{endpoint}"
    
    if method == 'GET':
        response = requests.get(url, headers=headers)
    elif method == 'POST':
        response = requests.post(url, headers=headers, data=json.dumps(data))
    elif method == 'DELETE':
        response = requests.delete(url, headers=headers)
    elif method == 'PUT':
        response = requests.put(url, headers=headers, data=json.dumps(data))
    else:
        raise ValueError("Unsupported HTTP method")
    
    return response

# States
class UserState:
    def __init__(self):
        self.data = {}

    def set(self, user_id, key, value):
        if user_id not in self.data:
            self.data[user_id] = {}
        self.data[user_id][key] = value

    def get(self, user_id, key):
        return self.data.get(user_id, {}).get(key)

    def clear(self, user_id):
        if user_id in self.data:
            del self.data[user_id]

user_state = UserState()

# Account Selection
def show_account_selection(chat_id, user_id, message_id=None, message_text="Pilih akun DigitalOcean yang ingin Kamu Operasikan:", action=None):
    accounts = get_user_accounts(user_id)
    
    if not accounts:
        # No accounts found, ask to add one
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("➕ Tambah Akun Baru", callback_data="add_new_account"))
        
        if message_id:
            bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text="Anda belum memiliki akun DigitalOcean. Silakan tambahkan akun terlebih dahulu:",
                reply_markup=markup
            )
        else:
            bot.send_message(chat_id, "Anda belum memiliki akun DigitalOcean. Silakan tambahkan akun terlebih dahulu:", reply_markup=markup)
        return
    
    markup = types.InlineKeyboardMarkup()
    
    for account_id, account_name, api_token in accounts:
        if action == "delete_account":
            btn_text = f"❌ {account_name} ({api_token[:3]}...)"
            callback_data = f"confirm_delete_account:{account_id}"
        else:
            btn_text = f"{account_name} ({api_token[:3]}...)"
            callback_data = f"select_account:{account_id}"
        
        markup.add(types.InlineKeyboardButton(btn_text, callback_data=callback_data))
    
    if action == "delete_account":
        markup.row(types.InlineKeyboardButton("❌ Batal", callback_data="cancel_action"))
    else:
        markup.row(
            types.InlineKeyboardButton("➕ Tambah Akun Baru", callback_data="add_new_account"),
            types.InlineKeyboardButton("🗑️ Hapus Akun", callback_data="delete_account")
        )
    
    if message_id:
        bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=message_text,
            reply_markup=markup
        )
    else:
        bot.send_message(chat_id, message_text, reply_markup=markup)

# Menu Utama
def show_main_menu(chat_id, user_id, account_id=None, message_id=None):
    if account_id is None:
        show_account_selection(chat_id, user_id, message_id)
        return
    
    markup = types.InlineKeyboardMarkup()
    
    droplets = get_user_droplets(user_id, account_id)
    has_droplets = len(droplets) > 0
    
    markup.row(
        types.InlineKeyboardButton("➕ CREATE DROPLET", callback_data="create_droplet")
    )
    
    if has_droplets:
        markup.row(
            types.InlineKeyboardButton("📋 LIST DROPLETS", callback_data="list_droplets"),
            types.InlineKeyboardButton("❌ DELETE DROPLET", callback_data="delete_droplet_menu")
        )
        markup.row(
            types.InlineKeyboardButton("🔄 RESIZE DROPLET", callback_data="resize_droplet_menu")
        )
    
    markup.row(
        types.InlineKeyboardButton("🗂️ KELOLA AKUN", callback_data="manage_accounts"),
        types.InlineKeyboardButton("🔍 CHECK TOKEN", callback_data="check_token")
    )

    welcome_msg = """🔮Bot Management Droplet DigitalOcean!

⚠️ PERINGATAN KEAMANAN:
- Password Akan Digenerate Otomatis
- Simpan password dengan baik
- Pastikan Kamu mengganti Password Setelah Berhasil Login

❗❗ Bot Ini 100% Free, Tidak Untuk Di sewakan. Jika Kamu Sedang Menyewa Bot Ini Berarti Kamu Kena Scam

Bot Create By : SAN (Owner SanStore)
Kamu Bisa Donate Kalo kamu Lagi Kaya😁
Gopay/Dana : 082292615651"""
    
    if message_id:
        bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=welcome_msg,
            reply_markup=markup
        )
    else:
        bot.send_message(chat_id, welcome_msg, reply_markup=markup)

@bot.message_handler(commands=['start'])
def send_welcome(message):
    show_account_selection(message.chat.id, message.from_user.id)

@bot.message_handler(content_types=['document'])
def handle_document(message):
    if message.document.mime_type == 'application/zip' or message.document.file_name.endswith('.zip'):
        bot.reply_to(message, "⏳ Memproses file backup...")
        
        if restore_database(message.document):
            bot.reply_to(message, "✅ Database berhasil direstore dari backup!")
            show_account_selection(message.chat.id, message.from_user.id)
        else:
            bot.reply_to(message, "❌ Gagal merestore database. Pastikan file backup valid.")
    else:
        bot.reply_to(message, "❌ Format file tidak didukung. Harap unggah file ZIP.")

# Callback Handler
@bot.callback_query_handler(func=lambda call: True)
def handle_callback(call):
    chat_id = call.message.chat.id
    user_id = call.from_user.id
    message_id = call.message.message_id

    if call.data == "add_new_account":
        bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text="Masukkan nama untuk akun DigitalOcean ini (contoh: Akun Utama, Akun Bisnis):"
        )
        user_state.set(user_id, 'step', 'new_account_name')

    elif call.data == "delete_account":
        show_account_selection(chat_id, user_id, message_id, "Pilih akun yang ingin dihapus:", action="delete_account")

    elif call.data.startswith("confirm_delete_account:"):
        _, account_id = call.data.split(":", 1)
        delete_account(account_id)
        bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text="✅ Akun berhasil dihapus!"
        )
        show_account_selection(chat_id, user_id)

    elif call.data.startswith("select_account:"):
        _, account_id = call.data.split(":", 1)
        user_state.set(user_id, 'current_account', account_id)  # Store selected account
        show_main_menu(chat_id, user_id, account_id, message_id)

    elif call.data == "manage_accounts":
        show_account_selection(chat_id, user_id, message_id)

    elif call.data == "check_token":
        accounts = get_user_accounts(user_id)
        if not accounts:
            bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text="❌ Belum ada akun yang ditambahkan"
            )
            return
        
        message = "🔑 Daftar Token Akun Anda:\n\n"
        for account_id, account_name, api_token in accounts:
            message += f"🔹 {account_name}\n"
            message += f"Token: {api_token[:3]}...\n\n"
        
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("🔙 Kembali", callback_data="cancel_action"))
        
        bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=message,
            reply_markup=markup
        )

    elif call.data == "create_droplet":
        account_id = user_state.get(user_id, 'current_account')
        if not account_id:
            bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text="Silakan pilih akun terlebih dahulu"
            )
            return

        bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text="Masukkan nama untuk Droplet:"
        )
        user_state.set(user_id, 'step', 'name')

    elif call.data == "list_droplets":
        account_id = user_state.get(user_id, 'current_account')
        if not account_id:
            bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text="Silakan pilih akun terlebih dahulu"
            )
            return
        show_droplets_list(chat_id, user_id, account_id, message_id)

    elif call.data == "delete_droplet_menu":
        account_id = user_state.get(user_id, 'current_account')
        if not account_id:
            bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text="Silakan pilih akun terlebih dahulu"
            )
            return
        show_droplets_list(chat_id, user_id, account_id, message_id, action='delete')

    elif call.data == "resize_droplet_menu":
        account_id = user_state.get(user_id, 'current_account')
        if not account_id:
            bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text="Silakan pilih akun terlebih dahulu"
            )
            return
        show_droplets_list(chat_id, user_id, account_id, message_id, action='resize')

    elif call.data.startswith("os:"):
        _, os, name = call.data.split(":", 2)
        bot.answer_callback_query(call.id, f"Sistem operasi dipilih: {os}")
        show_size_selection(call.message.chat.id, call.from_user.id, os, name, message_id)

    elif call.data.startswith("size:"):
        _, size, os, name = call.data.split(":", 3)
        bot.answer_callback_query(call.id, f"Ukuran RAM dipilih: {size}")
        account_id = user_state.get(user_id, 'current_account')
        password = generate_strong_password()
        create_new_droplet(call.message.chat.id, call.from_user.id, account_id, name, os, size, password, message_id)

    elif call.data.startswith("delete_droplet:"):
        _, droplet_id = call.data.split(":", 1)
        confirm_delete_droplet(chat_id, user_id, droplet_id, message_id)

    elif call.data.startswith("confirm_delete:"):
        _, droplet_id = call.data.split(":", 1)
        delete_droplet(chat_id, user_id, droplet_id, message_id)

    elif call.data.startswith("resize_droplet:"):
        _, droplet_id = call.data.split(":", 1)
        show_resize_options(chat_id, user_id, droplet_id, message_id)

    elif call.data.startswith("confirm_resize:"):
        _, droplet_id, new_size = call.data.split(":", 2)
        resize_droplet(chat_id, user_id, droplet_id, new_size, message_id)

    elif call.data == "cancel_action":
        account_id = user_state.get(user_id, 'current_account')
        show_main_menu(chat_id, user_id, account_id, message_id)

def show_droplets_list(chat_id, user_id, account_id, message_id=None, action=None):
    droplets = get_user_droplets(user_id, account_id)
    if not droplets:
        bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text="Anda belum memiliki droplet."
        )
        return
    
    if action == 'delete':
        message = "🗑️ Pilih droplet yang ingin dihapus:\n"
    elif action == 'resize':
        message = "🔄 Pilih droplet yang ingin diubah ukurannya:\n"
    else:
        message = "📋 Daftar Droplet Anda:\n"
    
    markup = types.InlineKeyboardMarkup()
    
    for droplet in droplets:
        droplet_id, name, ip_address, status, size_slug, _ = droplet
        message += f"🟢 {name}\n"
        message += f"ID: {droplet_id}\n"
        message += f"Status: {status}\n"
        if ip_address:
            message += f"IP: {ip_address}\n"
        if size_slug:
            message += f"Size: {size_slug}\n"
        message += "\n"
        
        if action == 'delete':
            markup.add(types.InlineKeyboardButton(f"🗑️ {name}", callback_data=f"delete_droplet:{droplet_id}"))
        elif action == 'resize':
            markup.add(types.InlineKeyboardButton(f"🔄 {name}", callback_data=f"resize_droplet:{droplet_id}"))
    
    if not action:
        bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=message
        )
    else:
        markup.row(types.InlineKeyboardButton("❌ Batal", callback_data="cancel_action"))
        
        bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=message,
            reply_markup=markup
        )

def confirm_delete_droplet(chat_id, user_id, droplet_id, message_id):
    droplet_info = get_droplet_info(user_id, droplet_id)
    if not droplet_info:
        bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text="Droplet tidak ditemukan."
        )
        return
    
    name, ip_address, status, size_slug, _ = droplet_info
    
    markup = types.InlineKeyboardMarkup()
    markup.row(
        types.InlineKeyboardButton("✅ Ya, Hapus", callback_data=f"confirm_delete:{droplet_id}"),
        types.InlineKeyboardButton("❌ Batal", callback_data="cancel_action")
    )
    
    message = f"⚠️ Anda yakin ingin menghapus droplet ini?\n\n"
    message += f"🟢 {name}\n"
    message += f"ID: {droplet_id}\n"
    message += f"Status: {status}\n"
    if ip_address:
        message += f"IP: {ip_address}\n"
    if size_slug:
        message += f"Size: {size_slug}\n"
    
    bot.edit_message_text(
        chat_id=chat_id,
        message_id=message_id,
        text=message,
        reply_markup=markup
    )

def delete_droplet(chat_id, user_id, droplet_id, message_id):
    account_id = user_state.get(user_id, 'current_account')
    if not account_id:
        bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text="Akun tidak ditemukan."
        )
        return
    
    token = get_account_token(account_id)
    if not token:
        bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text="Token tidak ditemukan."
        )
        return
    
    try:
        response = do_api_request('DELETE', f"droplets/{droplet_id}", token)
        
        if response.status_code == 204:
            delete_droplet_from_db(droplet_id)
            bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=f"✅ Droplet dengan ID {droplet_id} berhasil dihapus!"
            )
        else:
            error_msg = response.json().get('message', 'Unknown error')
            bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=f"❌ Gagal menghapus droplet: {error_msg}"
            )
    except Exception as e:
        bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=f"❌ Error: {str(e)}"
        )

def show_resize_options(chat_id, user_id, droplet_id, message_id):
    droplet_info = get_droplet_info(user_id, droplet_id)
    if not droplet_info:
        bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text="Droplet tidak ditemukan."
        )
        return
    
    name, ip_address, status, current_size, _ = droplet_info
    
    size_options = {
        "🔮 1GB RAM, 1vCPU": "s-1vcpu-1gb",
        "🔮 2GB RAM, 2vCPU": "s-2vcpu-2gb",
        "🔮 4GB RAM, 2vCPU": "s-2vcpu-4gb",
        "🔮 8GB RAM, 4vCPU": "s-4vcpu-8gb"
    }

    markup = types.InlineKeyboardMarkup()
    for label, value in size_options.items():
        if value != current_size:
            markup.add(types.InlineKeyboardButton(label, callback_data=f"confirm_resize:{droplet_id}:{value}"))
    
    markup.row(types.InlineKeyboardButton("❌ Batal", callback_data="cancel_action"))
    
    message = f"🔄 Pilih ukuran baru untuk droplet:\n\n"
    message += f"🟢 {name}\n"
    message += f"ID: {droplet_id}\n"
    message += f"Ukuran saat ini: {current_size}\n"
    message += f"Tunggu Beberapa Saat Setelah Memili Size"    
    
    bot.edit_message_text(
        chat_id=chat_id,
        message_id=message_id,
        text=message,
        reply_markup=markup
    )

def resize_droplet(chat_id, user_id, droplet_id, new_size, message_id):
    account_id = user_state.get(user_id, 'current_account')
    if not account_id:
        bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text="Akun tidak ditemukan."
        )
        return
    
    token = get_account_token(account_id)
    if not token:
        bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text="Token tidak ditemukan."
        )
        return
    
    try:
        # Power off the droplet
        power_off_response = do_api_request('POST', f"droplets/{droplet_id}/actions", token, {
            "type": "power_off"
        })
        
        if power_off_response.status_code != 201:
            error_msg = power_off_response.json().get('message', 'Unknown error')
            bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=f"❌ Gagal mematikan droplet: {error_msg}"
            )
            return
        
        # Wait for power off to complete
        time.sleep(15)
        
        # Resize the droplet
        resize_response = do_api_request('POST', f"droplets/{droplet_id}/actions", token, {
            "type": "resize",
            "size": new_size,
            "disk": True
        })
        
        if resize_response.status_code == 201:
            update_droplet_status(droplet_id, 'resizing', size_slug=new_size)
            
            # Wait for resize to complete
            time.sleep(20)
            
            # Power on the droplet
            power_on_response = do_api_request('POST', f"droplets/{droplet_id}/actions", token, {
                "type": "power_on"
            })
            
            if power_on_response.status_code == 201:
                bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=message_id,
                    text=f"⏳ Droplet sedang diubah ukurannya ke {new_size} ..."
                )
            else:
                bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=message_id,
                    text=f"⚠️ Droplet berhasil diubah ukurannya tapi gagal dinyalakan. Silakan nyalakan manual."
                )
            
            threading.Thread(target=monitor_droplet_resize, 
                          args=(chat_id, user_id, droplet_id, token, message_id)).start()
        else:
            error_msg = resize_response.json().get('message', 'Unknown error')
            bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=f"❌ Gagal mengubah ukuran droplet: {error_msg}"
            )
    except Exception as e:
        bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=f"❌ Error: {str(e)}"
        )

def monitor_droplet_resize(chat_id, user_id, droplet_id, token, message_id):
    while True:
        time.sleep(15)
        
        try:
            response = do_api_request('GET', f"droplets/{droplet_id}", token)
            if response.status_code == 200:
                droplet_info = response.json()['droplet']
                status = droplet_info['status']
                size_slug = droplet_info['size_slug']
                
                update_droplet_status(droplet_id, status, size_slug=size_slug)
                
                if status == 'active':
                    bot.edit_message_text(
                        chat_id=chat_id,
                        message_id=message_id,
                        text=f"✅ Ukuran droplet berhasil diubah\n"
                        f"ID: {droplet_id}\n"
                        f"Ukuran baru: {size_slug}"
                    )
                    break
                elif status == 'off':
                    bot.edit_message_text(
                        chat_id=chat_id,
                        message_id=message_id,
                        text=f"⚠️ Droplet berhasil diubah ukurannya tapi dalam status mati\n"
                        f"ID: {droplet_id}\n"
                        f"Ukuran baru: {size_slug}"
                    )
                    break
                elif status == 'error':
                    bot.edit_message_text(
                        chat_id=chat_id,
                        message_id=message_id,
                        text=f"❌ Gagal mengubah ukuran droplet\n"
                        f"ID: {droplet_id}\n"
                        f"Status: {status}"
                    )
                    break
            else:
                error_msg = response.json().get('message', 'Unknown error')
                bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=message_id,
                    text=f"❌ Error memeriksa status droplet: {error_msg}"
                )
                break
        except Exception as e:
            bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=f"❌ Error: {str(e)}"
            )
            break

# Message Handler
@bot.message_handler(func=lambda message: True)
def handle_messages(message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    step = user_state.get(user_id, 'step')

    if step == 'new_account_name':
        account_name = message.text.strip()
        user_state.set(user_id, 'account_name', account_name)
        user_state.set(user_id, 'step', 'new_account_token')
        bot.send_message(chat_id, f"Masukkan API token untuk akun '{account_name}':")

    elif step == 'new_account_token':
        account_name = user_state.get(user_id, 'account_name')
        api_token = message.text.strip()
        
        # Verify the token by making a simple API call
        try:
            response = do_api_request('GET', 'account', api_token)
            if response.status_code == 200:
                account_id = add_account(user_id, account_name, api_token)
                bot.send_message(chat_id, f"✅ Akun '{account_name}' berhasil ditambahkan!")
                user_state.clear(user_id)
                user_state.set(user_id, 'current_account', account_id)
                show_main_menu(chat_id, user_id, account_id)
            else:
                error_msg = response.json().get('message', 'Token tidak valid')
                bot.send_message(chat_id, f"❌ Gagal memverifikasi token: {error_msg}\nSilakan coba lagi.")
        except Exception as e:
            bot.send_message(chat_id, f"❌ Error: {str(e)}\nSilakan coba lagi.")

    elif step == 'name':
        name = message.text.strip()
        user_state.set(user_id, 'name', name)
        user_state.set(user_id, 'step', None)
        show_os_selection(chat_id, user_id, name)

# OS Selection
def show_os_selection(chat_id, user_id, name):
    os_options = {
        "Ubuntu 20.04 LTS": "ubuntu-20-04-x64",
        "Ubuntu 22.04 LTS": "ubuntu-22-04-x64",
        "Ubuntu 24.04 LTS": "ubuntu-24-04-x64",
        "Debian 11": "debian-11-x64",
        "Debian 12": "debian-12-x64"
    }

    markup = types.InlineKeyboardMarkup()
    for label, value in os_options.items():
        markup.add(types.InlineKeyboardButton(label, callback_data=f"os:{value}:{name}"))

    bot.send_message(chat_id, "Pilih sistem operasi:", reply_markup=markup)

# Size Selection
def show_size_selection(chat_id, user_id, os, name, message_id=None):
    size_options = {
        "🔮 1GB RAM, 1vCPU": "s-1vcpu-1gb",
        "🔮 2GB RAM, 2vCPU": "s-2vcpu-2gb",
        "🔮 4GB RAM, 2vCPU": "s-2vcpu-4gb",
        "🔮 8GB RAM, 4vCPU": "s-4vcpu-8gb"
    }

    markup = types.InlineKeyboardMarkup()
    for label, value in size_options.items():
        markup.add(types.InlineKeyboardButton(label, callback_data=f"size:{value}:{os}:{name}"))

    if message_id:
        bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text="Pilih ukuran RAM dan CPU:",
            reply_markup=markup
        )
    else:
        bot.send_message(chat_id, "Pilih ukuran RAM dan CPU:", reply_markup=markup)

# Create Droplet
def create_new_droplet(chat_id, user_id, account_id, name, image, size, password, message_id=None):
    token = get_account_token(account_id)
    if not token:
        if message_id:
            bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text="Token tidak ditemukan."
            )
        else:
            bot.send_message(chat_id, "Token tidak ditemukan.")
        return

    user_data_script = f"""#!/bin/bash
echo "root:{password}" | chpasswd
sed -i 's/^PasswordAuthentication no/PasswordAuthentication yes/' /etc/ssh/sshd_config
systemctl restart sshd
"""

    data = {
        "name": name,
        "region": "sgp1",
        "size": size,
        "image": image,
        "ssh_keys": None,
        "backups": False,
        "ipv6": True,
        "user_data": user_data_script,
        "private_networking": None,
        "monitoring": True,
        "tags": ["telegram-bot-created"],
        "volume_ids": [],
        "password": password
    }

    try:
        response = do_api_request('POST', "droplets", token, data)
        
        if response.status_code == 202:
            droplet_id = response.json()['droplet']['id']
            save_droplet(user_id, account_id, droplet_id, name, size_slug=size, password=password)
            
            threading.Thread(target=monitor_droplet_creation, 
                          args=(chat_id, user_id, droplet_id, name, token, message_id)).start()
            
            msg = f"⏳ Droplet '{name}' sedang dibuat (ID: {droplet_id})...\n\n"
            msg += f"🔑 Password root yang digenerate:\n<code>{password}</code>\n\n"
            msg += "⚠️ Simpan password ini dengan aman!"
            
            if message_id:
                bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=message_id,
                    text=msg,
                    parse_mode='HTML'
                )
            else:
                bot.send_message(chat_id, msg, parse_mode='HTML')
        else:
            error_msg = response.json().get('message', 'Unknown error')
            if message_id:
                bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=message_id,
                    text=f"❌ Gagal membuat droplet: {error_msg}"
                )
            else:
                bot.send_message(chat_id, f"❌ Gagal membuat droplet: {error_msg}")
    except Exception as e:
        if message_id:
            bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=f"❌ Error: {str(e)}"
            )
        else:
            bot.send_message(chat_id, f"❌ Error: {str(e)}")

# Monitor droplet creation
def monitor_droplet_creation(chat_id, user_id, droplet_id, name, token, message_id=None):
    cursor.execute("SELECT password FROM droplets WHERE droplet_id=?", (droplet_id,))
    result = cursor.fetchone()
    password = result[0] if result else "[password tidak tersimpan]"
    
    while True:
        time.sleep(10)
        try:
            response = do_api_request('GET', f"droplets/{droplet_id}", token)
            if response.status_code == 200:
                droplet_info = response.json()['droplet']
                status = droplet_info['status']
                ip_address = None
                size_slug = droplet_info['size_slug']
                
                if droplet_info['networks']['v4']:
                    ip_address = droplet_info['networks']['v4'][0]['ip_address']
                
                update_droplet_status(droplet_id, status, ip_address, size_slug)
                
                if status == 'active':
                    login_info = f"""
✅ Droplet '{name}' siap digunakan!

📋 Informasi Login:
IP: <code>{ip_address}</code>
Username: root
Password: <code>{password}</code>

Perintah Login Terminal:
<code>root@{ip_address}</code>

⚠️ Disarankan Untuk Mengganti Password!
"""
                    if message_id:
                        bot.edit_message_text(
                            chat_id=chat_id,
                            message_id=message_id,
                            text=login_info,
                            parse_mode='HTML'
                        )
                    else:
                        bot.send_message(chat_id, login_info, parse_mode='HTML')
                    break
                elif status == 'off':
                    msg = f"⚠️ Droplet '{name}' dibuat tapi dalam status mati\n" \
                          f"ID: {droplet_id}\n" \
                          f"IP: {ip_address}\n" \
                          f"Size: {size_slug}\n" \
                          f"Status: {status}"
                    if message_id:
                        bot.edit_message_text(
                            chat_id=chat_id,
                            message_id=message_id,
                            text=msg
                        )
                    else:
                        bot.send_message(chat_id, msg)
                    break
                elif status == 'error':
                    msg = f"❌ Gagal membuat droplet '{name}'\n" \
                          f"ID: {droplet_id}\n" \
                          f"Status: {status}"
                    if message_id:
                        bot.edit_message_text(
                            chat_id=chat_id,
                            message_id=message_id,
                            text=msg
                        )
                    else:
                        bot.send_message(chat_id, msg)
                    break
            else:
                error_msg = response.json().get('message', 'Unknown error')
                msg = f"❌ Error memeriksa status droplet: {error_msg}"
                if message_id:
                    bot.edit_message_text(
                        chat_id=chat_id,
                        message_id=message_id,
                        text=msg
                    )
                else:
                    bot.send_message(chat_id, msg)
                break
        except Exception as e:
            msg = f"❌ Error: {str(e)}"
            if message_id:
                bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=message_id,
                    text=msg
                )
            else:
                bot.send_message(chat_id, msg)
            break

# Jalankan bot
print("Bot sedang berjalan...")
bot.polling(none_stop=True)
