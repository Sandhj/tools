import telebot
import subprocess
import os
import re

# Ganti dengan token bot Telegram Anda
BOT_TOKEN = "8176151908:AAHwzLjCCFdoXOJJYIV22bLsN1Ew45o1nHo"
bot = telebot.TeleBot(BOT_TOKEN)

# Dictionary untuk menyimpan data sementara user
user_data = {}

class VPSData:
    def __init__(self):
        self.ip = None
        self.password = None
        self.domain = None

@bot.message_handler(commands=['start'])
def send_welcome(message):
    chat_id = message.chat.id
    user_data[chat_id] = VPSData()
    
    bot.send_message(chat_id, "🤖 **Selamat datang di Bot Setup VPS**\n\n"
                             "Saya akan membantu Anda setup VPS secara otomatis.\n"
                             "Silakan masukkan **IP Address VPS** Anda:",
                             parse_mode='Markdown')

@bot.message_handler(func=lambda message: True)
def handle_messages(message):
    chat_id = message.chat.id
    
    # Jika user belum memulai dengan /start
    if chat_id not in user_data:
        send_welcome(message)
        return
    
    user = user_data[chat_id]
    
    # Step 1: Minta IP Address
    if user.ip is None:
        ip = message.text.strip()
        
        # Validasi format IP
        if not is_valid_ip(ip):
            bot.send_message(chat_id, "❌ Format IP tidak valid! Silakan masukkan IP Address yang benar:")
            return
        
        user.ip = ip
        bot.send_message(chat_id, "✅ IP Address diterima!\n"
                                 "Sekarang silakan masukkan **Password Root** VPS Anda:",
                                 parse_mode='Markdown')
    
    # Step 2: Minta Password Root
    elif user.password is None:
        user.password = message.text.strip()
        bot.send_message(chat_id, "✅ Password diterima!\n"
                                 "Sekarang silakan masukkan **Domain** yang akan digunakan:",
                                 parse_mode='Markdown')
    
    # Step 3: Minta Domain
    elif user.domain is None:
        domain = message.text.strip()
        
        # Validasi domain
        if not is_valid_domain(domain):
            bot.send_message(chat_id, "❌ Format domain tidak valid! Silakan masukkan domain yang benar (contoh: example.com):")
            return
        
        user.domain = domain
        process_vps_setup(message)

def is_valid_ip(ip):
    """Validasi format IP Address"""
    pattern = r'^(\d{1,3}\.){3}\d{1,3}$'
    if not re.match(pattern, ip):
        return False
    
    # Cek setiap octet
    octets = ip.split('.')
    for octet in octets:
        if not (0 <= int(octet) <= 255):
            return False
    
    return True

def is_valid_domain(domain):
    """Validasi format domain"""
    pattern = r'^[a-zA-Z0-9]([a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?(\.[a-zA-Z]{2,})+$'
    return re.match(pattern, domain) is not None

def process_vps_setup(message):
    chat_id = message.chat.id
    user = user_data[chat_id]
    
    bot.send_message(chat_id, "🔄 **Memulai proses setup VPS...**\n"
                             f"IP: `{user.ip}`\n"
                             f"Domain: `{user.domain}`\n\n"
                             "Proses mungkin memakan waktu beberapa menit...",
                             parse_mode='Markdown')
    
    # Jalankan setup dalam thread terpisah agar tidak blocking
    thread = Thread(target=run_vps_setup, args=(chat_id, user))
    thread.start()

def run_vps_setup(chat_id, user):
    try:
        # Step 1: Simpan domain ke file lokal dan transfer ke VPS
        bot.send_message(chat_id, "📁 Menyimpan domain ke file...")
        
        # Buat file domain sementara
        with open(f"/tmp/domain_{chat_id}.txt", "w") as f:
            f.write(user.domain)
        
        # Step 2: Transfer file domain ke VPS dan jalankan script
        bot.send_message(chat_id, "🔗 Menghubungkan ke VPS...")
        
        # Command untuk menyalin domain file ke VPS dan menyimpannya
        save_domain_cmd = f"""
        echo '{user.domain}' | sshpass -p '{user.password}' ssh -o StrictHostKeyChecking=no root@{user.ip} 'cat > /tmp/domain_temp.txt && 
        sudo mkdir -p /usr/local/etc/xray/dns/ && 
        sudo cp /tmp/domain_temp.txt /usr/local/etc/xray/dns/domain && 
        sudo mkdir -p /var/lib/ && 
        sudo cp /tmp/domain_temp.txt /var/lib/dnsvps.conf &&
        echo "Domain berhasil disimpan"'
        """
        
        result = subprocess.run(save_domain_cmd, shell=True, capture_output=True, text=True)
        
        if result.returncode != 0:
            bot.send_message(chat_id, f"❌ Gagal menyimpan domain ke VPS:\n{result.stderr}")
            return
        
        bot.send_message(chat_id, "✅ Domain berhasil disimpan di VPS!")
        
        # Step 3: Download dan jalankan script install
        bot.send_message(chat_id, "📥 Mengunduh dan menjalankan script install...")
        
        install_script_cmd = f"""
        sshpass -p '{user.password}' ssh -o StrictHostKeyChecking=no root@{user.ip} '
        wget -q https://raw.githubusercontent.com/Sandhj/ST/main/install_bot.sh && 
        chmod +x install_bot.sh && 
        ./install_bot.sh'
        """
        
        # Jalankan dengan timeout 10 menit (600 detik)
        result = subprocess.run(install_script_cmd, shell=True, capture_output=True, text=True, timeout=600)
        
        if result.returncode == 0:
            bot.send_message(chat_id, "🎉 **Setup VPS berhasil diselesaikan!**\n\n"
                                     "✅ Cek Notifikasi Berhasil Dari File Setup\n"
                                     "✅ Setelah Notifikasi Selesai\n"
                                     "✅ VPS siap digunakan")
        else:
            if "Timeout" in str(result):
                bot.send_message(chat_id, "⏰ Proses install timeout. Script mungkin masih berjalan di VPS.")
            else:
                bot.send_message(chat_id, f"⚠️ Terjadi error saat menjalankan script:\n{result.stderr}")
    
    except subprocess.TimeoutExpired:
        bot.send_message(chat_id, "⏰ Proses install timeout (lebih dari 10 menit). Script mungkin masih berjalan di VPS.")
    
    except Exception as e:
        bot.send_message(chat_id, f"❌ **Error tidak terduga:**\n{str(e)}")
    
    finally:
        # Bersihkan file temporary
        try:
            if os.path.exists(f"/tmp/domain_{chat_id}.txt"):
                os.remove(f"/tmp/domain_{chat_id}.txt")
        except:
            pass
        
        # Hapus data user
        if chat_id in user_data:
            del user_data[chat_id]

def cleanup_temp_files():
    """Bersihkan file temporary yang tersisa"""
    import glob
    temp_files = glob.glob("/tmp/domain_*.txt")
    for file in temp_files:
        try:
            os.remove(file)
        except:
            pass

# Jalankan cleanup saat start
cleanup_temp_files()

if __name__ == "__main__":
    print("Bot sedang berjalan...")
    bot.polling(none_stop=True)
