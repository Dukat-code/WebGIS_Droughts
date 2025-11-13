#!/bin/bash

# Create PostGIS extension in the 'droughts' database
sudo -u postgres psql -d droughts -c "CREATE EXTENSION IF NOT EXISTS postgis;"