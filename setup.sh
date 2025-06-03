echo -e "\e[1;36m+--------------------------------------------------+\e[0m"
echo -e "\e[1;36m|   Install Bot Manager DigitalOcean By Sanstore   |\e[0m"
echo -e "\e[1;36m+--------------------------------------------------+\e[0m"
read -p "Masukkan Token BOT : " bottoken
read -p "Masukkan ChatID : " chatid

sed -i "s/TOKEN_BOT/${bottoken}/" /opt/do-manager/do-manager.py
sed -i "s/CHATID/${chatid}/" /opt/do-manager/do-manager.py
