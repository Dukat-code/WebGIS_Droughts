#!/bin/bash

# Usage: sudo bash setup_ftp.sh /path/to/ftp_folder ftpuser

FTP_FOLDER="$1"
FTP_USER="$2"

if [ -z "$FTP_FOLDER" ] || [ -z "$FTP_USER" ]; then
    echo "Usage: sudo bash setup_ftp.sh /path/to/ftp_folder ftpuser"
    exit 1
fi

# Install vsftpd if not present
if ! dpkg -l | grep -qw vsftpd; then
    apt update
    apt install -y vsftpd
fi

# Create FTP user if not exists
if ! id "$FTP_USER" &>/dev/null; then
    adduser --disabled-password --gecos "" "$FTP_USER"
    echo "Set password for $FTP_USER:"
    passwd "$FTP_USER"
fi

# Set folder ownership and permissions for all users
chown "$FTP_USER":"$FTP_USER" "$FTP_FOLDER"
chmod 777 "$FTP_FOLDER"

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
EOF

# Restart vsftpd
systemctl restart vsftpd

echo "FTP setup complete. Any user can access $FTP_FOLDER. Connect with user: $FTP_USER"