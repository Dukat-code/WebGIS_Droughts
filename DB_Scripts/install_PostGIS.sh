#!/bin/bash

# Update package lists
sudo apt update

# Install PostgreSQL and PostGIS
sudo apt install -y postgresql postgresql-contrib postgis postgresql-15-postgis-3

# Restart PostgreSQL service
sudo systemctl restart postgresql