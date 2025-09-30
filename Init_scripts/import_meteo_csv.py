import psycopg2
import csv
import configparser
import os

# --- CONFIGURATION ---
CSV_FILE = 'ecowas_stations.csv'

# Map CSV columns to DB columns
COLUMN_MAP = {
    'latitude': 'latitude',
    'longitude': 'longitude',
    'station_name': 'station_name',
    'elevation': 'elevation',
    'year': 'year',
    'month': 'month',
    'tavg': 'tavg',    
    'tmax': 'tmax',    
    'tmin': 'tmin',    
    'prcp': 'prcp'     
}

TABLE = 'meteostation_month_data'

# Read DB config from config.ini
config = configparser.ConfigParser()
config_path = os.path.join(os.path.dirname(__file__), '..', 'config', 'config.ini')
config.read(config_path)
db_section = config['database']

# DB config
DB_CONFIG = {
    'host': db_section.get('host', 'localhost'),
    'port': db_section.getint('port', 5432),
    'dbname': db_section.get('name', 'droughts'),
    'user': db_section.get('user', 'postgres'),
    'password': db_section.get('password', '')
}
# DB config for OS user option
DB_CONN_STR = "dbname=postgres"

# Read table creation SQL from meteo_stations.sql
def create_table_if_not_exists(cur):
    sql_path = os.path.join(os.path.dirname(__file__), '..', 'DB_Scripts', 'meteo_stations.sql')
    with open(sql_path, 'r') as f:
        sql = f.read()
    cur.execute(sql)

def main(os_users=False):
    if os_users:
        conn = psycopg2.connect(DB_CONN_STR)
    else:
        conn = psycopg2.connect(**DB_CONFIG)
    
    cur = conn.cursor()

    # Create table if not exists
    create_table_if_not_exists(cur)
    conn.commit()

    with open(CSV_FILE, newline='') as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            # Build data dict for mandatory columns
            data = {
                'latitude': row[COLUMN_MAP['latitude']],
                'longitude': row[COLUMN_MAP['longitude']],
                'station_name': row[COLUMN_MAP['station_name']],
                'elevation': row[COLUMN_MAP['elevation']],
                'year': row[COLUMN_MAP['year']],
                'month': row[COLUMN_MAP['month']]
            }
            # Optional columns
            for col in ['tavg', 'tmax', 'tmin', 'prcp']:
                if COLUMN_MAP.get(col) and COLUMN_MAP[col] in row and row[COLUMN_MAP[col]] != '':
                    data[col] = row[COLUMN_MAP[col]]
                else:
                    data[col] = None

            # Geometry from lat/lon
            geom = f"SRID=4326;POINT({data['longitude']} {data['latitude']})"

            # Prepare insert
            sql = f"""
                INSERT INTO {TABLE} (geom, latitude, longitude, station_name, elevation, year, month, date, tavg, tmax, tmin, prcp)
                VALUES (ST_GeomFromText(%s, 4326), %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """
            values = (
                f"POINT({data['longitude']} {data['latitude']})",
                data['latitude'], data['longitude'], data['station_name'], data['elevation'],
                data['year'], data['month'], f"{int(data['year']):04d}-{int(data['month']):02d}-01",
                data['tavg'], data['tmax'], data['tmin'], data['prcp']
            )
            cur.execute(sql, values)

    conn.commit()
    cur.close()
    conn.close()
    print("Import completed.")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Import meteo CSV to database")
    parser.add_argument('--db_os_users', action='store_true', help="Use OS user configuration for DB connection")
    args = parser.parse_args()
    main(os_users=args.db_os_users)
