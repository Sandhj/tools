#!/bin/bash

# Cek jika bot.sh sudah running
if pgrep -f "sc-installer.py" > /dev/null; then
    echo "Bot sudah berjalan. Keluar."
    exit 1
fi

python sc-installer.py
