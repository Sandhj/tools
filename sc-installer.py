import telebot
import paramiko
from threading import Lock

# Token bot Telegram
BOT_TOKEN = "8255110757:AAFGiEMmjP8LWPbcArK2QDafxq12j7NKPkc"
bot = telebot.TeleBot(BOT_TOKEN)

# Dictionary untuk menyimpan data sementara user
user_data = {}
user_lock = Lock()

@bot.message_handler(commands=['install'])
def start_message(message):
    markup = telebot.types.ReplyKeyboardRemove()
    bot.send_message(message.chat.id, 
                    "🤖 **Bot Management VPS**\n\n"
                    "Silakan masukkan **IP Address VPS**:", 
                    parse_mode='Markdown', 
                    reply_markup=markup)
    
    with user_lock:
        user_data[message.chat.id] = {'step': 'ip'}

@bot.message_handler(func=lambda message: True)
def handle_message(message):
    chat_id = message.chat.id
    
    with user_lock:
        if chat_id not in user_data:
            user_data[chat_id] = {'step': 'ip'}
            bot.send_message(chat_id, "🌐 **Masukkan IP Address VPS:**", parse_mode='Markdown')
            return
        
        current_step = user_data[chat_id].get('step')
        
        if current_step == 'ip':
            user_data[chat_id]['ip'] = message.text.strip()
            user_data[chat_id]['step'] = 'password'
            bot.send_message(chat_id, "🔐 **Masukkan Password root VPS:**", parse_mode='Markdown')
        
        elif current_step == 'password':
            user_data[chat_id]['password'] = message.text.strip()
            user_data[chat_id]['step'] = 'domain'
            bot.send_message(chat_id, "📝 **Masukkan Domain:**\nContoh: example.com", parse_mode='Markdown')
        
        elif current_step == 'domain':
            user_data[chat_id]['domain'] = message.text.strip()
            
            ip = user_data[chat_id]['ip']
            domain = user_data[chat_id]['domain']
            
            confirm_text = f"""
✅ **Konfirmasi Data**

🌐 **IP VPS:** `{ip}`
📝 **Domain:** `{domain}`

Apakah data sudah benar?
            """
            
            markup = telebot.types.InlineKeyboardMarkup()
            markup.row(
                telebot.types.InlineKeyboardButton("✅ Ya, Lanjutkan", callback_data=f"proceed_{chat_id}"),
                telebot.types.InlineKeyboardButton("❌ Batal", callback_data=f"cancel_{chat_id}")
            )
            
            bot.send_message(chat_id, confirm_text, parse_mode='Markdown', reply_markup=markup)

@bot.callback_query_handler(func=lambda call: True)
def handle_callback(call):
    chat_id = call.message.chat.id
    
    if call.data.startswith("proceed_"):
        target_chat_id = int(call.data.replace("proceed_", ""))
        process_vps_configuration(call, target_chat_id)
    
    elif call.data.startswith("cancel_"):
        target_chat_id = int(call.data.replace("cancel_", ""))
        cancel_operation(call, target_chat_id)

def process_vps_configuration(call, chat_id):
    try:
        bot.answer_callback_query(call.id, "⏳ Menghubungkan ke VPS...")
        
        with user_lock:
            if chat_id not in user_data:
                bot.edit_message_text("❌ Data tidak ditemukan", chat_id, call.message.message_id)
                return
            
            data = user_data[chat_id]
            ip = data['ip']
            password = data['password']
            domain = data['domain']
        
        # Update pesan
        bot.edit_message_text(
            f"⏳ **Sedang memproses...**\n\n"
            f"🌐 Menghubungkan ke: `{ip}`\n"
            f"📝 Mengatur domain: `{domain}`",
            chat_id, call.message.message_id, parse_mode='Markdown'
        )
        
        # Eksekusi perintah di VPS
        success = execute_on_vps(ip, password, domain)
        
        if success:
            success_text = f"""
✅ **Berhasil Diatur!**

🌐 **VPS:** `{ip}`
📝 **Domain:** `{domain}`

✅ Domain berhasil diatur dan script dijalankan.
"""
            bot.edit_message_text(success_text, chat_id, call.message.message_id, parse_mode='Markdown')
        else:
            error_text = f"""
❌ **Gagal!**

🌐 **VPS:** `{ip}`
📝 **Domain:** `{domain}`

Gagal terhubung atau menjalankan perintah.
Periksa IP dan password Anda.
"""
            bot.edit_message_text(error_text, chat_id, call.message.message_id, parse_mode='Markdown')
        
        # Hapus data user setelah selesai
        with user_lock:
            if chat_id in user_data:
                del user_data[chat_id]
                
    except Exception as e:
        bot.edit_message_text("❌ Terjadi error saat memproses", chat_id, call.message.message_id)
        with user_lock:
            if chat_id in user_data:
                del user_data[chat_id]

def cancel_operation(call, chat_id):
    bot.answer_callback_query(call.id, "❌ Dibatalkan")
    bot.edit_message_text("❌ Operasi dibatalkan", chat_id, call.message.message_id)
    
    with user_lock:
        if chat_id in user_data:
            del user_data[chat_id]

def execute_on_vps(ip, password, domain):
    """
    Menjalankan perintah di VPS menggunakan SSH
    """
    try:
        # Buat koneksi SSH
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        
        # Koneksi ke VPS
        ssh.connect(ip, port=22, username='root', password=password, timeout=30)
        
        commands = [
            # Buat directory jika belum ada
            "mkdir -p /usr/local/etc/xray/dns",
            
            # Simpan domain ke file
            f"echo '{domain}' > /usr/local/etc/xray/dns/domain",
            f"echo 'DNS={domain}' > /var/lib/dnsvps.conf",
            
            # Download script
            "wget -q https://raw.githubusercontent.com/Sandhj/ST/main/install_bot.sh -O /tmp/install_bot.sh",
            
            # Beri permission execute
            "chmod +x /tmp/install_bot.sh",
            
            # Jalankan script
            "/tmp/install_bot.sh"
        ]
        
        for cmd in commands:
            stdin, stdout, stderr = ssh.exec_command(cmd)
            exit_status = stdout.channel.recv_exit_status()
            
            if exit_status != 0:
                return False
        
        ssh.close()
        return True
        
    except Exception as e:
        return False

@bot.message_handler(commands=['cancel'])
def cancel_command(message):
    chat_id = message.chat.id
    with user_lock:
        if chat_id in user_data:
            del user_data[chat_id]
    bot.send_message(chat_id, "✅ Operasi dibatalkan. Ketik /start untuk memulai lagi.")

if __name__ == "__main__":
    print("🤖 Bot VPS Management sedang berjalan...")
    bot.polling()
