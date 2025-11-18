import telebot
import requests
import json
import re

# Konfigurasi
TELEGRAM_TOKEN = "8311291721:AAHBvptpUxGodw1-bntXbPonFAiGl3lhNdA"
CF_API_KEY = "ea6a937332a2f01d2d22d495dafdfbd187cd3"
CF_EMAIL = "hasdararysandhy@gmail.com"
ZONE_ID = "f7400aabacca20ee7f6227f716396fab"

# Inisialisasi bot
bot = telebot.TeleBot(TELEGRAM_TOKEN)

# Header untuk Cloudflare API
headers = {
    "X-Auth-Email": CF_EMAIL,
    "X-Auth-Key": CF_API_KEY,
    "Content-Type": "application/json"
}

# Dictionary untuk menyimpan state user
user_states = {}

def validate_ip(ip):
    """Validasi format IPv4"""
    pattern = r'^(\d{1,3}\.){3}\d{1,3}$'
    if not re.match(pattern, ip):
        return False
    
    parts = ip.split('.')
    for part in parts:
        if not 0 <= int(part) <= 255:
            return False
    return True

def get_dns_records(zone_id):
    """Mendapatkan semua DNS records"""
    url = f"https://api.cloudflare.com/client/v4/zones/{zone_id}/dns_records"
    
    try:
        response = requests.get(url, headers=headers)
        result = response.json()
        
        if result.get("success"):
            return True, result.get("result", [])
        else:
            return False, "Gagal mengambil data DNS records"
    
    except Exception as e:
        return False, f"Error: {str(e)}"

def create_dns_record(zone_id, record_name, ip_address, proxied=False):
    """Membuat DNS record A di Cloudflare"""
    url = f"https://api.cloudflare.com/client/v4/zones/{zone_id}/dns_records"
    
    data = {
        "type": "A",
        "name": record_name,
        "content": ip_address,
        "ttl": 1,  # Auto TTL
        "proxied": proxied  # No proxy
    }
    
    try:
        response = requests.post(url, headers=headers, data=json.dumps(data))
        result = response.json()
        
        if result.get("success"):
            return True, f"✅ DNS Record berhasil dibuat!\n\n📝 Nama: `{record_name}`\n📍 IP: `{ip_address}`\n🔓 Proxy: OFF\n🆔 ID: `{result['result']['id']}`"
        else:
            errors = result.get("errors", [])
            error_messages = [error.get('message', 'Unknown error') for error in errors]
            return False, f"❌ Gagal membuat DNS record: {', '.join(error_messages)}"
    
    except Exception as e:
        return False, f"❌ Error: {str(e)}"

def update_dns_record(zone_id, record_id, record_name, ip_address, proxied=False):
    """Update DNS record yang sudah ada"""
    url = f"https://api.cloudflare.com/client/v4/zones/{zone_id}/dns_records/{record_id}"
    
    data = {
        "type": "A",
        "name": record_name,
        "content": ip_address,
        "ttl": 1,
        "proxied": proxied
    }
    
    try:
        response = requests.put(url, headers=headers, data=json.dumps(data))
        result = response.json()
        
        if result.get("success"):
            return True, f"✅ DNS Record berhasil diupdate!\n\n📝 Nama: `{record_name}`\n📍 IP: `{ip_address}`\n🔓 Proxy: OFF\n🆔 ID: `{record_id}`"
        else:
            errors = result.get("errors", [])
            error_messages = [error.get('message', 'Unknown error') for error in errors]
            return False, f"❌ Gagal update DNS record: {', '.join(error_messages)}"
    
    except Exception as e:
        return False, f"❌ Error: {str(e)}"

def delete_dns_record(zone_id, record_id):
    """Hapus DNS record"""
    url = f"https://api.cloudflare.com/client/v4/zones/{zone_id}/dns_records/{record_id}"
    
    try:
        response = requests.delete(url, headers=headers)
        result = response.json()
        
        if result.get("success"):
            return True, "✅ DNS Record berhasil dihapus!"
        else:
            errors = result.get("errors", [])
            error_messages = [error.get('message', 'Unknown error') for error in errors]
            return False, f"❌ Gagal menghapus DNS record: {', '.join(error_messages)}"
    
    except Exception as e:
        return False, f"❌ Error: {str(e)}"

# Handler perintah start
@bot.message_handler(commands=['start'])
def send_welcome(message):
    welcome_text = """
🤖 **Bot DNS Manager**

Perintah yang tersedia:
• `/add_noproxy` - Tambah record A tanpa proxy
• `/list` - Lihat daftar records
• `/edit_record` - Edit record yang sudah ada
• `/delete` - Hapus record
• `/help` - Bantuan

Gunakan /help untuk info lengkap.
    """
    bot.reply_to(message, welcome_text, parse_mode='Markdown')


# Handler untuk menambah record tanpa proxy
@bot.message_handler(commands=['add_noproxy'])
def start_add_record(message):
    chat_id = message.chat.id
    user_states[chat_id] = {'state': 'waiting_subdomain'}
    
    markup = telebot.types.ForceReply(selective=False)
    bot.send_message(chat_id, "📝 Masukkan nama subdomain:", reply_markup=markup)

# Handler untuk input subdomain (add)
@bot.message_handler(func=lambda message: user_states.get(message.chat.id, {}).get('state') == 'waiting_subdomain')
def get_subdomain(message):
    chat_id = message.chat.id
    subdomain = message.text.strip()
    
    # Tidak ada validasi subdomain
    user_states[chat_id] = {
        'state': 'waiting_ip',
        'subdomain': subdomain
    }
    
    markup = telebot.types.ForceReply(selective=False)
    bot.send_message(chat_id, "📍 Masukkan alamat IPv4 (contoh: 192.168.1.1):", reply_markup=markup)

# Handler untuk input IP (add)
@bot.message_handler(func=lambda message: user_states.get(message.chat.id, {}).get('state') == 'waiting_ip')
def get_ip_address(message):
    chat_id = message.chat.id
    ip_address = message.text.strip()
    
    if not validate_ip(ip_address):
        bot.send_message(chat_id, "❌ Format IP tidak valid! Gunakan format IPv4 seperti: 192.168.1.1")
        user_states[chat_id] = {'state': 'waiting_ip'}
        return
    
    subdomain = user_states[chat_id]['subdomain']
    
    # Hapus state user
    del user_states[chat_id]
    
    # Buat DNS record
    bot.send_message(chat_id, "⏳ Membuat DNS record...")
    success, result_message = create_dns_record(ZONE_ID, subdomain, ip_address, proxied=False)
    bot.send_message(chat_id, result_message, parse_mode='Markdown')

# Handler untuk melihat daftar records
@bot.message_handler(commands=['list'])
def list_records(message):
    chat_id = message.chat.id
    bot.send_message(chat_id, "⏳ Mengambil daftar DNS records...")
    
    success, records_data = get_dns_records(ZONE_ID)
    
    if not success:
        bot.send_message(chat_id, f"❌ {records_data}")
        return
    
    if not records_data:
        bot.send_message(chat_id, "📭 Tidak ada DNS records")
        return
    
    # Format tampilan sederhana
    message_text = "🧾 *List Record*\n\n"
    
    # Hanya tampilkan record A
    a_records = [r for r in records_data if r['type'] == 'A']
    
    for record in a_records:
        message_text += f"• `{record['name']}` (`{record['content']}`)\n"
    
    message_text += f"\n*Total: {len(a_records)} record A*"
    
    bot.send_message(chat_id, message_text, parse_mode='Markdown')

# Handler untuk edit record
@bot.message_handler(commands=['edit_record'])
def start_edit_record(message):
    chat_id = message.chat.id
    bot.send_message(chat_id, "⏳ Mengambil daftar records...")
    
    success, records_data = get_dns_records(ZONE_ID)
    
    if not success:
        bot.send_message(chat_id, f"❌ {records_data}")
        return
    
    # Filter hanya record A
    a_records = [r for r in records_data if r['type'] == 'A']
    
    if not a_records:
        bot.send_message(chat_id, "❌ Tidak ada record A yang bisa diedit")
        return
    
    # Buat keyboard inline untuk memilih record
    markup = telebot.types.InlineKeyboardMarkup()
    
    for record in a_records[:10]:  # Batasi 10 record pertama
        button_text = f"{record['name']} → {record['content']}"
        callback_data = f"edit_{record['id']}"
        markup.add(telebot.types.InlineKeyboardButton(button_text, callback_data=callback_data))
    
    bot.send_message(chat_id, "📝 Pilih record yang akan diedit:", reply_markup=markup)

# Handler untuk delete record
@bot.message_handler(commands=['delete'])
def start_delete_record(message):
    chat_id = message.chat.id
    bot.send_message(chat_id, "⏳ Mengambil daftar records...")
    
    success, records_data = get_dns_records(ZONE_ID)
    
    if not success:
        bot.send_message(chat_id, f"❌ {records_data}")
        return
    
    # Filter hanya record A
    a_records = [r for r in records_data if r['type'] == 'A']
    
    if not a_records:
        bot.send_message(chat_id, "❌ Tidak ada record A yang bisa dihapus")
        return
    
    # Buat keyboard inline untuk memilih record
    markup = telebot.types.InlineKeyboardMarkup()
    
    for record in a_records[:10]:  # Batasi 10 record pertama
        button_text = f"{record['name']} → {record['content']}"
        callback_data = f"delete_{record['id']}"
        markup.add(telebot.types.InlineKeyboardButton(button_text, callback_data=callback_data))
    
    bot.send_message(chat_id, "🗑️ Pilih record yang akan dihapus:", reply_markup=markup)

# Handler untuk callback query (pilihan record edit)
@bot.callback_query_handler(func=lambda call: call.data.startswith('edit_'))
def handle_edit_selection(call):
    chat_id = call.message.chat.id
    record_id = call.data.replace('edit_', '')
    
    # Dapatkan detail record
    url = f"https://api.cloudflare.com/client/v4/zones/{ZONE_ID}/dns_records/{record_id}"
    
    try:
        response = requests.get(url, headers=headers)
        result = response.json()
        
        if result.get("success"):
            record = result['result']
            user_states[chat_id] = {
                'state': 'editing_subdomain',  # Ubah state menjadi editing_subdomain
                'record_id': record_id,
                'current_name': record['name'],
                'current_ip': record['content']
            }
            
            markup = telebot.types.ForceReply(selective=False)
            bot.send_message(chat_id, 
                           f"✏️ **Edit Record**\n\nCurrent:\n📝 Nama: `{record['name']}`\n📍 IP: `{record['content']}`\n\nMasukkan nama subdomain baru:", 
                           reply_markup=markup, parse_mode='Markdown')
        else:
            bot.send_message(chat_id, "❌ Gagal mengambil detail record")
    
    except Exception as e:
        bot.send_message(chat_id, f"❌ Error: {str(e)}")

# Handler untuk input subdomain baru (edit)
@bot.message_handler(func=lambda message: user_states.get(message.chat.id, {}).get('state') == 'editing_subdomain')
def get_edit_subdomain(message):
    chat_id = message.chat.id
    new_subdomain = message.text.strip()
    
    # Update state untuk menunggu IP baru
    user_states[chat_id]['state'] = 'editing_ip'
    user_states[chat_id]['new_subdomain'] = new_subdomain
    
    markup = telebot.types.ForceReply(selective=False)
    bot.send_message(chat_id, "📍 Masukkan alamat IPv4 baru:", reply_markup=markup)

# Handler untuk input IP baru (edit)
@bot.message_handler(func=lambda message: user_states.get(message.chat.id, {}).get('state') == 'editing_ip')
def get_edit_ip(message):
    chat_id = message.chat.id
    user_data = user_states[chat_id]
    new_ip = message.text.strip()
    
    if not validate_ip(new_ip):
        bot.send_message(chat_id, "❌ Format IP tidak valid! Gunakan format IPv4 seperti: 192.168.1.1")
        return
    
    # Update record
    record_id = user_data['record_id']
    new_subdomain = user_data['new_subdomain']
    
    bot.send_message(chat_id, "⏳ Mengupdate DNS record...")
    success, result_message = update_dns_record(ZONE_ID, record_id, new_subdomain, new_ip, proxied=False)
    
    # Hapus state user
    del user_states[chat_id]
    
    bot.send_message(chat_id, result_message, parse_mode='Markdown')

# Handler untuk callback query (pilihan record delete)
@bot.callback_query_handler(func=lambda call: call.data.startswith('delete_'))
def handle_delete_selection(call):
    chat_id = call.message.chat.id
    record_id = call.data.replace('delete_', '')
    
    # Konfirmasi penghapusan
    markup = telebot.types.InlineKeyboardMarkup()
    markup.add(
        telebot.types.InlineKeyboardButton("✅ Ya, Hapus", callback_data=f"confirm_delete_{record_id}"),
        telebot.types.InlineKeyboardButton("❌ Batal", callback_data="cancel_delete")
    )
    
    bot.send_message(chat_id, "⚠️ Apakah Anda yakin ingin menghapus record ini?", reply_markup=markup)

# Handler untuk konfirmasi delete
@bot.callback_query_handler(func=lambda call: call.data.startswith('confirm_delete_'))
def handle_confirm_delete(call):
    chat_id = call.message.chat.id
    record_id = call.data.replace('confirm_delete_', '')
    
    bot.send_message(chat_id, "⏳ Menghapus DNS record...")
    success, result_message = delete_dns_record(ZONE_ID, record_id)
    
    bot.send_message(chat_id, result_message)

# Handler untuk batal delete
@bot.callback_query_handler(func=lambda call: call.data == 'cancel_delete')
def handle_cancel_delete(call):
    chat_id = call.message.chat.id
    bot.send_message(chat_id, "❌ Penghapusan dibatalkan.")

# Handler untuk pesan tidak dikenal
@bot.message_handler(func=lambda message: True)
def handle_unknown(message):
    bot.reply_to(message, "❌ Perintah tidak dikenali. Gunakan /help untuk melihat perintah yang tersedia.")

# Jalankan bot
if __name__ == "__main__":
    bot.polling(none_stop=True)
