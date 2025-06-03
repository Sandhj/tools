echo -e "\e[1;36m+--------------------------------------------------+\e[0m"
echo -e "\e[1;36m|   Install Bot Manager DigitalOcean By Sanstore   |\e[0m"
echo -e "\e[1;36m+--------------------------------------------------+\e[0m"
read -p "Masukkan Token BOT : " bottoken
read -p "Masukkan ChatID : " chatid

mkdir -p /opt/do-manager/
cd /opt/do-manager/

# Buat venv untuk Bot
# Fungsi untuk deteksi OS dan versi
OS=$(grep -Ei '^(NAME|VERSION_ID)=' /etc/os-release | cut -d= -f2 | tr -d '"')

# Ekstrak nama distro dan versi
DISTRO=$(echo "$OS" | head -n1)
VERSION=$(echo "$OS" | tail -n1)

# Cek apakah Debian 12
if [[ "$DISTRO" == "Debian GNU/Linux" && "$VERSION" == "12" ]]; then
    echo "OS Terdeteksi: Debian 12"
    apt update && apt install python3.11-venv -y

# Cek apakah Ubuntu 24.04 LTS
elif [[ "$DISTRO" == "Ubuntu" && "$VERSION" == "24.04" ]]; then
    echo "OS Terdeteksi: Ubuntu 24.04 LTS"
    apt update && apt install python3.12-venv -y

# Jika bukan salah satu dari di atas
else
    echo "OS Tidak Didukung!"
    echo "Distro: $DISTRO"
    echo "Versi: $VERSION"
    exit 1
fi


python3 -m venv bot
source bot/bin/activate

apt-get install -y python3-pip

# Instal modul Python yang diperlukan
pip3 install requests
pip3 install schedule
pip3 install pyTelegramBotAPI

cat <<EOL > run.sh
#!/bin/bash
source /opt/do-manager/bot/bin/activate
python3 /opt/do-manager/do-manager.py
EOL

wget -q https://raw.githubusercontent.com/Sandhj/tools/main/do-manager.py
sed -i "s/TOKEN_BOT/${bottoken}/" /opt/do-manager/do-manager.py
sed -i "s/CHATID/${chatid}/" /opt/do-manager/do-manager.py

# Buat file service systemd
cat <<EOF > /etc/systemd/system/do-manager.service
[Unit]
Description=Do Manager Bot Service
After=network.target

[Service]
ExecStart=/usr/bin/bash /opt/do-manager/run.sh
WorkingDirectory=/opt/do-manager
StandardOutput=inherit
StandardError=inherit
Restart=always
User=root

[Install]
WantedBy=multi-user.target
EOF

# Reload systemd dan mulai service
systemctl daemon-reload
systemctl enable do-manager
systemctl start do-manager
