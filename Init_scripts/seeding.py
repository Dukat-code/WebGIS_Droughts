import os
import requests
import psycopg2

# Configuración de conexión a la base de datos PostgreSQL
DB_HOST = "127.0.0.1"
DB_PORT = "5432"
DB_NAME = "droughts"
DB_USER = "postgres"
DB_PASSWORD = "postgres"
# DB config for OS user option
DB_CONN_STR = "dbname=postgres"

# Configuración de GeoServer
GEOSERVER_URL = "http://localhost:8080/geoserver"
USERNAME = "admin"
PASSWORD = "geoserver"
LAYER_NAME = "droughts:era5_ecowas_temp"
GRIDSET_ID = "WebMercatorQuad"
FORMAT = "image/png"
ZOOM_START = 3
ZOOM_STOP = 8
THREAD_COUNT = 4

# Consulta SQL para obtener las fechas
SQL_QUERY = "SELECT DISTINCT date FROM era5_ecowas ORDER BY date ASC"

def get_dates_from_db(conn):
    cursor = conn.cursor()
    cursor.execute(SQL_QUERY)
    dates = [row[0].strftime("%Y-%m-%d") for row in cursor.fetchall()]
    cursor.close()
    return dates

def seed_tiles_for_date(date_str):
    seed_request_xml = f"""
    <seedRequest>
      <name>{LAYER_NAME}</name>
      <gridSetId>{GRIDSET_ID}</gridSetId>
      <zoomStart>{ZOOM_START}</zoomStart>
      <zoomStop>{ZOOM_STOP}</zoomStop>
      <format>{FORMAT}</format>
      <type>seed</type>
      <threadCount>{THREAD_COUNT}</threadCount>
      <parameters>
        <entry>
          <string>TIME</string>
          <string>{date_str}</string>
        </entry>
      </parameters>
    </seedRequest>
    """
    response = requests.post(
        f"{GEOSERVER_URL}/gwc/rest/seed/{LAYER_NAME}.xml",
        auth=(USERNAME, PASSWORD),
        headers={"Content-Type": "text/xml"},
        data=seed_request_xml
    )
    if response.status_code == 200:
        print(f"Seeding init correctly for {date_str}")
    else:
        print(f"Error on seeding init for {date_str}: {response.status_code} - {response.text}")

def main(os_users=False):
    if os_users:
        conn = psycopg2.connect(DB_CONN_STR)
    else:
        conn = psycopg2.connect(
            host=DB_HOST,
            port=DB_PORT,
            dbname=DB_NAME,
            user=DB_USER,
            password=DB_PASSWORD
        )
    #dates = get_dates_from_db(conn)
    dates = [
                "1991-01-01",
                "1991-06-01",
                "2001-01-01",
                "2001-06-01",
                "2011-01-01",
                "2011-06-01",
                "2020-01-01",
                "2011-06-01",
                "2025-01-01",
                "2025-06-01"
            ] # Example dates for testing
    conn.close()

    for date_str in dates:
        seed_tiles_for_date(date_str)

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Import meteo CSV to database")
    parser.add_argument('--os_users', action='store_true', help="Use OS user configuration for DB connection")
    args = parser.parse_args()
    main(os_users=args.os_users)
