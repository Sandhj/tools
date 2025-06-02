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

# Konfigurasi
BOT_TOKEN = '7985231262:AAGSOK3YU2c9cxyPzukAGf64lBxXYYJGbL0'
DO_BASE_URL = "https://api.digitalocean.com/v2/"

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
    CREATE TABLE IF NOT EXISTS do_tokens (
        user_id INTEGER PRIMARY KEY,
        api_token TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
''')

cursor.execute('''
    CREATE TABLE IF NOT EXISTS droplets (
        id INTEGER PRIMARY KEY,
        user_id INTEGER NOT NULL,
        droplet_id INTEGER NOT NULL,
        name TEXT NOT NULL,
        ip_address TEXT,
        status TEXT,
        size_slug TEXT,
        password TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(user_id) REFERENCES do_tokens(user_id)
    )
''')
conn.commit()

def get_do_token(user_id):
    cursor.execute("SELECT api_token FROM do_tokens WHERE user_id=?", (user_id,))
    result = cursor.fetchone()
    return result[0] if result else None

def set_do_token(user_id, api_token):
    cursor.execute("REPLACE INTO do_tokens (user_id, api_token) VALUES (?, ?)", (user_id, api_token))
    conn.commit()

def save_droplet(user_id, droplet_id, name, ip_address=None, status='new', size_slug=None, password=None):
    cursor.execute('''
        INSERT INTO droplets (user_id, droplet_id, name, ip_address, status, size_slug, password)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (user_id, droplet_id, name, ip_address, status, size_slug, password))
    conn.commit()

def get_user_droplets(user_id):
    cursor.execute("SELECT droplet_id, name, ip_address, status, size_slug, password FROM droplets WHERE user_id=?", (user_id,))
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

# Menu Utama
def show_main_menu(chat_id, user_id):
    markup = types.InlineKeyboardMarkup()
    
    droplets = get_user_droplets(user_id)
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
        types.InlineKeyboardButton("🗂️ SET TOKEN", callback_data="set_token"),
        types.InlineKeyboardButton("🔍 CHECK TOKEN", callback_data="check_token")
    )

    welcome_msg = """Selamat datang di Bot Management Droplet DigitalOcean!

⚠️ PERINGATAN KEAMANAN:
- Password root digenerate otomatis dan aman
- Simpan password dengan baik
- Disarankan untuk menggunakan SSH key setelah setup"""
    
    bot.send_message(chat_id, welcome_msg, reply_markup=markup)

@bot.message_handler(commands=['start'])
def send_welcome(message):
    show_main_menu(message.chat.id, message.from_user.id)

# Callback Handler
@bot.callback_query_handler(func=lambda call: True)
def handle_callback(call):
    chat_id = call.message.chat.id
    user_id = call.from_user.id

    if call.data == "set_token":
        bot.send_message(chat_id, "Silakan kirim API token DigitalOcean Anda:")
        user_state.set(user_id, 'step', 'set_token')

    elif call.data == "check_token":
        token = get_do_token(user_id)
        if token:
            bot.send_message(chat_id, "✅ Token sudah tersimpan (3 karakter pertama: " + token[:3] + "***)")
        else:
            bot.send_message(chat_id, "❌ Belum ada token yang disimpan")

    elif call.data == "create_droplet":
        if not get_do_token(user_id):
            bot.send_message(chat_id, "Anda harus menyimpan API token terlebih dahulu dengan /settoken")
            return

        bot.send_message(chat_id, "Masukkan nama untuk Droplet:")
        user_state.set(user_id, 'step', 'name')

    elif call.data == "list_droplets":
        show_droplets_list(chat_id, user_id)

    elif call.data == "delete_droplet_menu":
        show_droplets_list(chat_id, user_id, action='delete')

    elif call.data == "resize_droplet_menu":
        show_droplets_list(chat_id, user_id, action='resize')

    elif call.data.startswith("os:"):
        _, os, name = call.data.split(":", 2)
        bot.answer_callback_query(call.id, f"Sistem operasi dipilih: {os}")
        show_size_selection(call.message.chat.id, call.from_user.id, os, name)

    elif call.data.startswith("size:"):
        _, size, os, name = call.data.split(":", 3)
        bot.answer_callback_query(call.id, f"Ukuran RAM dipilih: {size}")
        password = generate_strong_password()
        create_new_droplet(call.message.chat.id, call.from_user.id, name, os, size, password)

    elif call.data.startswith("delete_droplet:"):
        _, droplet_id = call.data.split(":", 1)
        confirm_delete_droplet(chat_id, user_id, droplet_id)

    elif call.data.startswith("confirm_delete:"):
        _, droplet_id = call.data.split(":", 1)
        delete_droplet(chat_id, user_id, droplet_id)

    elif call.data.startswith("resize_droplet:"):
        _, droplet_id = call.data.split(":", 1)
        show_resize_options(chat_id, user_id, droplet_id)

    elif call.data.startswith("confirm_resize:"):
        _, droplet_id, new_size = call.data.split(":", 2)
        resize_droplet(chat_id, user_id, droplet_id, new_size)

    elif call.data == "cancel_action":
        bot.delete_message(chat_id, call.message.message_id)
        show_main_menu(chat_id, user_id)

def show_droplets_list(chat_id, user_id, action=None):
    droplets = get_user_droplets(user_id)
    if not droplets:
        bot.send_message(chat_id, "Anda belum memiliki droplet.")
        return
    
    if action == 'delete':
        message = "🗑️ Pilih droplet yang ingin dihapus:\n\n"
    elif action == 'resize':
        message = "🔄 Pilih droplet yang ingin diubah ukurannya:\n\n"
    else:
        message = "📋 Daftar Droplet Anda:\n\n"
    
    markup = types.InlineKeyboardMarkup()
    
    for droplet in droplets:
        droplet_id, name, ip_address, status, size_slug, _ = droplet
        message += f"🔹 {name}\n"
        message += f"ID: {droplet_id}\n"
        message += f"Status: {status}\n"
        if ip_address:
            message += f"IP: {ip_address}\n"
        if size_slug:
            message += f"Size: {size_slug}\n"
        message += "\n"
        
        if action == 'delete':
            markup.add(types.InlineKeyboardButton(f"❌ {name}", callback_data=f"delete_droplet:{droplet_id}"))
        elif action == 'resize':
            markup.add(types.InlineKeyboardButton(f"🔄 {name}", callback_data=f"resize_droplet:{droplet_id}"))
    
    if not action:
        bot.send_message(chat_id, message)
    else:
        markup.row(types.InlineKeyboardButton("❌ Batal", callback_data="cancel_action"))
        bot.send_message(chat_id, message, reply_markup=markup)

def confirm_delete_droplet(chat_id, user_id, droplet_id):
    droplet_info = get_droplet_info(user_id, droplet_id)
    if not droplet_info:
        bot.send_message(chat_id, "Droplet tidak ditemukan.")
        return
    
    name, ip_address, status, size_slug, _ = droplet_info
    
    markup = types.InlineKeyboardMarkup()
    markup.row(
        types.InlineKeyboardButton("✅ Ya, Hapus", callback_data=f"confirm_delete:{droplet_id}"),
        types.InlineKeyboardButton("❌ Batal", callback_data="cancel_action")
    )
    
    message = f"⚠️ Anda yakin ingin menghapus droplet ini?\n\n"
    message += f"🔹 {name}\n"
    message += f"ID: {droplet_id}\n"
    message += f"Status: {status}\n"
    if ip_address:
        message += f"IP: {ip_address}\n"
    if size_slug:
        message += f"Size: {size_slug}\n"
    
    bot.send_message(chat_id, message, reply_markup=markup)

def delete_droplet(chat_id, user_id, droplet_id):
    token = get_do_token(user_id)
    if not token:
        bot.send_message(chat_id, "Token tidak ditemukan.")
        return
    
    try:
        response = do_api_request('DELETE', f"droplets/{droplet_id}", token)
        
        if response.status_code == 204:
            delete_droplet_from_db(droplet_id)
            bot.send_message(chat_id, f"✅ Droplet dengan ID {droplet_id} berhasil dihapus!")
        else:
            error_msg = response.json().get('message', 'Unknown error')
            bot.send_message(chat_id, f"❌ Gagal menghapus droplet: {error_msg}")
    except Exception as e:
        bot.send_message(chat_id, f"❌ Error: {str(e)}")

def show_resize_options(chat_id, user_id, droplet_id):
    droplet_info = get_droplet_info(user_id, droplet_id)
    if not droplet_info:
        bot.send_message(chat_id, "Droplet tidak ditemukan.")
        return
    
    name, ip_address, status, current_size, _ = droplet_info
    
    size_options = {
        "💲 1GB RAM, 1vCPU": "s-1vcpu-1gb",
        "💲💲 2GB RAM, 2vCPU": "s-2vcpu-2gb",
        "💲💲💲 4GB RAM, 2vCPU": "s-2vcpu-4gb",
        "💲💲💲💲 8GB RAM, 4vCPU": "s-4vcpu-8gb"
    }

    markup = types.InlineKeyboardMarkup()
    for label, value in size_options.items():
        if value != current_size:
            markup.add(types.InlineKeyboardButton(label, callback_data=f"confirm_resize:{droplet_id}:{value}"))
    
    markup.row(types.InlineKeyboardButton("❌ Batal", callback_data="cancel_action"))
    
    message = f"🔄 Pilih ukuran baru untuk droplet:\n\n"
    message += f"🔹 {name}\n"
    message += f"ID: {droplet_id}\n"
    message += f"Ukuran saat ini: {current_size}\n"
    
    bot.send_message(chat_id, message, reply_markup=markup)

def resize_droplet(chat_id, user_id, droplet_id, new_size):
    token = get_do_token(user_id)
    if not token:
        bot.send_message(chat_id, "Token tidak ditemukan.")
        return
    
    try:
        power_off_response = do_api_request('POST', f"droplets/{droplet_id}/actions", token, {
            "type": "power_off"
        })
        
        if power_off_response.status_code != 201:
            error_msg = power_off_response.json().get('message', 'Unknown error')
            bot.send_message(chat_id, f"❌ Gagal mematikan droplet: {error_msg}")
            return
        
        time.sleep(5)
        
        resize_response = do_api_request('POST', f"droplets/{droplet_id}/actions", token, {
            "type": "resize",
            "size": new_size,
            "disk": True
        })
        
        if resize_response.status_code == 201:
            update_droplet_status(droplet_id, 'resizing', size_slug=new_size)
            
            do_api_request('POST', f"droplets/{droplet_id}/actions", token, {
                "type": "power_on"
            })
            
            bot.send_message(chat_id, f"⏳ Droplet sedang diubah ukurannya ke {new_size}...")
            
            threading.Thread(target=monitor_droplet_resize, 
                          args=(chat_id, user_id, droplet_id, token)).start()
        else:
            error_msg = resize_response.json().get('message', 'Unknown error')
            bot.send_message(chat_id, f"❌ Gagal mengubah ukuran droplet: {error_msg}")
    except Exception as e:
        bot.send_message(chat_id, f"❌ Error: {str(e)}")

def monitor_droplet_resize(chat_id, user_id, droplet_id, token):
    while True:
        time.sleep(10)
        
        try:
            response = do_api_request('GET', f"droplets/{droplet_id}", token)
            if response.status_code == 200:
                droplet_info = response.json()['droplet']
                status = droplet_info['status']
                size_slug = droplet_info['size_slug']
                
                update_droplet_status(droplet_id, status, size_slug=size_slug)
                
                if status == 'active':
                    bot.send_message(chat_id, 
                                  f"✅ Ukuran droplet berhasil diubah!\n"
                                  f"ID: {droplet_id}\n"
                                  f"Ukuran baru: {size_slug}")
                    break
                elif status == 'off':
                    bot.send_message(chat_id, 
                                  f"⚠️ Droplet berhasil diubah ukurannya tapi dalam status mati\n"
                                  f"ID: {droplet_id}\n"
                                  f"Ukuran baru: {size_slug}")
                    break
                elif status == 'error':
                    bot.send_message(chat_id, 
                                    f"❌ Gagal mengubah ukuran droplet\n"
                                    f"ID: {droplet_id}\n"
                                    f"Status: {status}")
                    break
            else:
                error_msg = response.json().get('message', 'Unknown error')
                bot.send_message(chat_id, f"❌ Error memeriksa status droplet: {error_msg}")
                break
        except Exception as e:
            bot.send_message(chat_id, f"❌ Error: {str(e)}")
            break

# Message Handler
@bot.message_handler(func=lambda message: True)
def handle_messages(message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    step = user_state.get(user_id, 'step')

    if step == 'set_token':
        token = message.text.strip()
        set_do_token(user_id, token)
        bot.send_message(chat_id, "Token berhasil disimpan!")
        user_state.clear(user_id)
        show_main_menu(chat_id, user_id)

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
def show_size_selection(chat_id, user_id, os, name):
    size_options = {
        "💲 1GB RAM, 1vCPU": "s-1vcpu-1gb",
        "💲💲 2GB RAM, 2vCPU": "s-2vcpu-2gb",
        "💲💲💲 4GB RAM, 2vCPU": "s-2vcpu-4gb",
        "💲💲💲💲 8GB RAM, 4vCPU": "s-4vcpu-8gb"
    }

    markup = types.InlineKeyboardMarkup()
    for label, value in size_options.items():
        markup.add(types.InlineKeyboardButton(label, callback_data=f"size:{value}:{os}:{name}"))

    bot.send_message(chat_id, "Pilih ukuran RAM dan CPU:", reply_markup=markup)

# Create Droplet
def create_new_droplet(chat_id, user_id, name, image, size, password):
    token = get_do_token(user_id)
    if not token:
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
            save_droplet(user_id, droplet_id, name, size_slug=size, password=password)
            
            threading.Thread(target=monitor_droplet_creation, 
                          args=(chat_id, user_id, droplet_id, name, token)).start()
            
            msg = f"⏳ Droplet '{name}' sedang dibuat (ID: {droplet_id})...\n\n"
            msg += f"🔑 Password root yang digenerate:\n<code>{password}</code>\n\n"
            msg += "⚠️ Simpan password ini dengan aman!"
            bot.send_message(chat_id, msg, parse_mode='HTML')
        else:
            error_msg = response.json().get('message', 'Unknown error')
            bot.send_message(chat_id, f"❌ Gagal membuat droplet: {error_msg}")
    except Exception as e:
        bot.send_message(chat_id, f"❌ Error: {str(e)}")

# Monitor droplet creation
def monitor_droplet_creation(chat_id, user_id, droplet_id, name, token):
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
IP: {ip_address}
Username: root
Password: <code>{password}</code>

Perintah SSH:
<code>ssh root@{ip_address}</code>

⚠️ Simpan informasi ini dengan aman!
"""
                    bot.send_message(chat_id, login_info, parse_mode='HTML')
                    break
                elif status == 'off':
                    bot.send_message(chat_id, 
                                   f"⚠️ Droplet '{name}' dibuat tapi dalam status mati\n"
                                   f"ID: {droplet_id}\n"
                                   f"IP: {ip_address}\n"
                                   f"Size: {size_slug}\n"
                                   f"Status: {status}")
                    break
                elif status == 'error':
                    bot.send_message(chat_id, 
                                    f"❌ Gagal membuat droplet '{name}'\n"
                                    f"ID: {droplet_id}\n"
                                    f"Status: {status}")
                    break
            else:
                error_msg = response.json().get('message', 'Unknown error')
                bot.send_message(chat_id, f"❌ Error memeriksa status droplet: {error_msg}")
                break
        except Exception as e:
            bot.send_message(chat_id, f"❌ Error: {str(e)}")
            break

# Jalankan bot
print("Bot sedang berjalan...")
bot.polling(none_stop=True)
