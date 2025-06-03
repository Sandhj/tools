echo -e "\e[1;36m+--------------------------------------------------+\e[0m"
echo -e "\e[1;36m|   Install Bot Manager DigitalOcean By Sanstore   |\e[0m"
echo -e "\e[1;36m+--------------------------------------------------+\e[0m"
read -p "Masukkan Token BOT : " bottoken
read -p "Masukkan ChatID : " chatid

mkdir -p /opt/do-manager/
cd /opt/do-manager/

wget -q https://raw.githubusercontent.com/Sandhj/tools/main/do-manager.py

sed -i "s/TOKEN_BOT/${bottoken}/" /opt/do-manager/do-manager.py
sed -i "s/CHATID/${chatid}/" /opt/do-manager/do-manager.py
