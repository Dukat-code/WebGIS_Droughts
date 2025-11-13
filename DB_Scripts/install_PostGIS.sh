#!/bin/bash

# Update package lists
sudo apt update

# Install PostgreSQL 14 and PostGIS 3
sudo apt install -y postgresql-14 postgresql-contrib postgis postgresql-14-postgis-3

# Restart PostgreSQL service
sudo systemctl restart postgresql