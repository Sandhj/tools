import telebot
import paramiko
import os
from threading import Lock

# Ganti dengan token bot Telegram Anda
BOT_TOKEN = "8255110757:AAFGiEMmjP8LWPbcArK2QDafxq12j7NKPkc"
bot = telebot.TeleBot(BOT_TOKEN)

# Dictionary untuk menyimpan data sementara user
user_data = {}
user_lock = Lock()

@bot.message_handler(commands=['start'])
def start_message(message):
    markup = telebot.types.ReplyKeyboardRemove()
    bot.send_message(message.chat.id, 
                    "🤖 **Bot Management VPS**\n\n"
                    "Saya akan membantu mengatur domain di VPS Anda.\n\n"
                    "Silakan masukkan **IP Address VPS**:", 
                    parse_mode='Markdown', 
                    reply_markup=markup)

@bot.message_handler(func=lambda message: True)
def handle_message(message):
    chat_id = message.chat.id
    
    with user_lock:
        # Step 1: Minta IP VPS
        if chat_id not in user_data:
            user_data[chat_id] = {'step': 'ip'}
            bot.send_message(chat_id, "🌐 **Masukkan IP Address VPS:**", parse_mode='Markdown')
            return
        
        current_step = user_data[chat_id].get('step')
        
        # Step 2: Simpan IP dan minta password
        if current_step == 'ip':
            user_data[chat_id]['ip'] = message.text.strip()
            user_data[chat_id]['step'] = 'password'
            bot.send_message(chat_id, "🔐 **Masukkan Password root VPS:**", parse_mode='Markdown')
        
        # Step 3: Simpan password dan minta domain
        elif current_step == 'password':
            user_data[chat_id]['password'] = message.text.strip()
            user_data[chat_id]['step'] = 'domain'
            bot.send_message(chat_id, "📝 **Masukkan Domain:**\nContoh: example.com", parse_mode='Markdown')
        
        # Step 4: Simpan domain dan proses ke VPS
        elif current_step == 'domain':
            user_data[chat_id]['domain'] = message.text.strip()
            
            # Konfirmasi data
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
            f"⏳ **Menghubungkan ke VPS...**\n\n"
            f"🌐 IP: `{ip}`\n"
            f"📝 Domain: `{domain}`",
            chat_id, call.message.message_id, parse_mode='Markdown'
        )
        
        # Eksekusi perintah di VPS
        result = execute_on_vps(ip, password, domain)
        
        if result['success']:
            success_text = f"""
✅ **Berhasil!**

🌐 **VPS:** `{ip}`
📝 **Domain:** `{domain}`

✅ Domain berhasil diatur dan script dijalankan.

**Output:**
```{result['output']}```
            """
            bot.edit_message_text(success_text, chat_id, call.message.message_id, parse_mode='Markdown')
        else:
            error_text = f"""
❌ **Gagal!**

🌐 **VPS:** `{ip}`
📝 **Domain:** `{domain}`

**Error:** {result['error']}
            """
            bot.edit_message_text(error_text, chat_id, call.message.message_id, parse_mode='Markdown')
        
        # Hapus data user setelah selesai
        with user_lock:
            if chat_id in user_data:
                del user_data[chat_id]
                
    except Exception as e:
        bot.edit_message_text(f"❌ Error: {str(e)}", chat_id, call.message.message_id)
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
        
        output_lines = []
        
        for cmd in commands:
            stdin, stdout, stderr = ssh.exec_command(cmd)
            exit_status = stdout.channel.recv_exit_status()
            
            if exit_status != 0:
                error_msg = stderr.read().decode().strip()
                return {
                    'success': False,
                    'error': f"Command failed: {cmd}\nError: {error_msg}"
                }
            
            cmd_output = stdout.read().decode().strip()
            if cmd_output:
                output_lines.append(f"$ {cmd}\n{cmd_output}")
        
        ssh.close()
        
        return {
            'success': True,
            'output': '\n'.join(output_lines[-3:])  # Tampilkan 3 output terakhir
        }
        
    except paramiko.AuthenticationException:
        return {'success': False, 'error': 'Authentication failed - Password salah'}
    except paramiko.SSHException as e:
        return {'success': False, 'error': f'SSH error: {str(e)}'}
    except Exception as e:
        return {'success': False, 'error': f'Connection error: {str(e)}'}

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
