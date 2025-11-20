#!/bin/bash

# Usage: sudo bash create_ftp_server.sh /path/to/ftp_folder ftpuser PUBLIC_IP

FTP_FOLDER="$1"
FTP_USER="$2"
PASV_ADDRESS="$3"

if [ -z "$FTP_FOLDER" ] || [ -z "$FTP_USER" ] || [ -z "$PASV_ADDRESS" ]; then
    echo "Usage: sudo bash create_ftp_server.sh /path/to/ftp_folder ftpuser PUBLIC_IP"
    exit 1
fi

# Install vsftpd if not present
if ! dpkg -l | grep -qw vsftpd; then
    apt update
    apt install -y vsftpd
fi

# Create FTP user if not exists, and set home directory to FTP_FOLDER
if ! id "$FTP_USER" &>/dev/null; then
    adduser --disabled-password --gecos "" --home "$FTP_FOLDER" "$FTP_USER"
    echo "Set password for $FTP_USER:"
    passwd "$FTP_USER"
else
    # Change home directory if needed
    usermod -d "$FTP_FOLDER" "$FTP_USER"
fi

# Set folder ownership and permissions for FTP user
chown "$FTP_USER":"$FTP_USER" "$FTP_FOLDER"
chmod 755 "$FTP_FOLDER"

# Backup vsftpd.conf
cp /etc/vsftpd.conf /etc/vsftpd.conf.bak

# Configure vsftpd
cat <<EOF > /etc/vsftpd.conf
listen=YES
anonymous_enable=NO
local_enable=YES
write_enable=YES
chroot_local_user=YES
user_sub_token=\$USER
local_root=$FTP_FOLDER
allow_writeable_chroot=YES
pasv_min_port=40000
pasv_max_port=40100
pasv_address=$PASV_ADDRESS
EOF

# Open FTP and passive ports in firewall
if command -v ufw &>/dev/null; then
    ufw allow 21/tcp
    ufw allow 40000:40100/tcp
    ufw reload
fi

# Restart vsftpd
systemctl restart vsftpd

echo "FTP setup complete. FTP user '$FTP_USER' can access $FTP_FOLDER. Passive mode IP: $PASV_ADDRESS"