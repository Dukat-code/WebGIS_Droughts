#!/bin/bash

# Script to execute a SQL script to create grids in a PostgreSQL/PostGIS database
# Usage: ./grids_creation.sh <sql_script.sql> <db_name> <db_user> [<db_host>] [<db_port>]
# Example: ./grids_creation.sh ingest_data.sql droughts postgres localhost 5432
# Note: to use it do not forget chmod +x grids_creation.sh

SQL_SCRIPT="$1"
DB_NAME="$2"
DB_USER="$3"
DB_HOST="${4:-localhost}"
DB_PORT="${5:-5432}"

if [ -z "$SQL_SCRIPT" ] || [ -z "$DB_NAME" ] || [ -z "$DB_USER" ]; then
  echo "Usage: $0 <sql_script.sql> <db_name> <db_user> [<db_host>] [<db_port>]"
  exit 1
fi

psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -f "$SQL_SCRIPT"