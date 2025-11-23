import psycopg2
import csv
import configparser
import os

# --- CONFIGURATION ---
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

def load_config(config_path=None):
    if config_path is None:
        config_path = os.path.join(os.path.dirname(__file__), '..', 'config', 'config.ini')
    config = configparser.ConfigParser()
    config.read(config_path)
    return config

def create_table_if_not_exists(cur, sql_path=None):
    if sql_path is None:
        sql_path = os.path.join(os.path.dirname(__file__), '..', 'DB_Scripts', 'meteo_stations.sql')
    with open(sql_path, 'r') as f:
        sql = f.read()
    cur.execute(sql)

def import_meteo_csv(csv_file, config_path=None, sql_path=None):
    config = load_config(config_path)
    conn = psycopg2.connect(**dict(config.items('database')))
    cur = conn.cursor()

    # Create table if not exists
    create_table_if_not_exists(cur, sql_path)
    conn.commit()

    with open(csv_file, newline='') as csvfile:
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

def import_meteo_csv_stream(csv_file, config_path=None, sql_path=None, batch_size=5000):
    import time
    config = load_config(config_path)
    conn = psycopg2.connect(**dict(config.items('database')))
    cur = conn.cursor()

    # Create table if not exists
    create_table_if_not_exists(cur, sql_path)
    conn.commit()

    # Count total rows for progress
    with open(csv_file, newline='') as csvfile:
        total_rows = sum(1 for _ in csvfile) - 1  # minus header

    with open(csv_file, newline='') as csvfile:
        reader = csv.DictReader(csvfile)
        processed_rows = 0
        batch = []
        last_percent = -1.0
        start_time = time.time()
        for row in reader:
            data = {
                'latitude': row[COLUMN_MAP['latitude']],
                'longitude': row[COLUMN_MAP['longitude']],
                'station_name': row[COLUMN_MAP['station_name']],
                'elevation': row[COLUMN_MAP['elevation']],
                'year': row[COLUMN_MAP['year']],
                'month': row[COLUMN_MAP['month']]
            }
            for col in ['tavg', 'tmax', 'tmin', 'prcp']:
                if COLUMN_MAP.get(col) and COLUMN_MAP[col] in row and row[COLUMN_MAP[col]] != '':
                    data[col] = row[COLUMN_MAP[col]]
                else:
                    data[col] = None
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
            batch.append(values)
            processed_rows += 1
            if len(batch) >= batch_size:
                cur.executemany(sql, batch)
                conn.commit()
                batch = []
            percent = (processed_rows / total_rows) * 100
            elapsed = time.time() - start_time
            if percent > 0:
                estimated_total = elapsed / (percent / 100)
                remaining = estimated_total - elapsed
            else:
                remaining = 0
            if percent - last_percent >= 1 or processed_rows == total_rows:
                yield f"Processed {processed_rows}/{total_rows} rows... ({percent:.1f}%) Elapsed: {format_hms(elapsed)}, Remaining: {format_hms(remaining)}"
                last_percent = percent
        if batch:
            cur.executemany(sql, batch)
            conn.commit()
    cur.close()
    conn.close()
    yield "Import completed."

def format_hms(seconds):
    seconds = int(seconds)
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    return f"{h:02}:{m:02}:{s:02}"

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Import meteo CSV to database")
    parser.add_argument('--csv_file', type=str, required=True, help="Path to the CSV file to import")
    parser.add_argument('--config_path', type=str, default=None, help="Path to config.ini")
    parser.add_argument('--sql_path', type=str, default=None, help="Path to meteo_stations.sql")
    args = parser.parse_args()
    import_meteo_csv(args.csv_file, config_path=args.config_path, sql_path=args.sql_path)