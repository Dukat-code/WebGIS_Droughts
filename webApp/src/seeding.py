import os
import requests
import psycopg2
import configparser

# Get the absolute path to config.ini
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
config_path = os.path.join(project_root, 'config', 'config.ini')

# Read the config file
config = configparser.ConfigParser()
config.read(config_path)

# GeoServer config from config.ini
GEOSERVER_URL = config.get('base', 'geoserver_url')
USERNAME = config.get('geoserver', 'username')
PASSWORD = config.get('geoserver', 'password')
GRIDSET_ID = "WebMercatorQuad"
FORMAT = "image/png"
THREAD_COUNT = 4

def get_dates_from_db(conn, layer):
    sql_query = f"SELECT DISTINCT date FROM {layer}_data ORDER BY date ASC"
    cursor = conn.cursor()
    cursor.execute(sql_query)
    dates = [row[0].strftime("%Y-%m-%d") for row in cursor.fetchall()]
    cursor.close()
    return dates

def seed_tiles_for_date(layer_name, date_str, zoom_start, zoom_stop):
    seed_request_xml = f"""
    <seedRequest>
      <name>{layer_name}</name>
      <gridSetId>{GRIDSET_ID}</gridSetId>
      <zoomStart>{zoom_start}</zoomStart>
      <zoomStop>{zoom_stop}</zoomStop>
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
        f"{GEOSERVER_URL}/gwc/rest/seed/{layer_name}.xml",
        auth=(USERNAME, PASSWORD),
        headers={"Content-Type": "text/xml"},
        data=seed_request_xml
    )
    if response.status_code == 200:
        print(f"Seeding init correctly for {date_str}")
    else:
        print(f"Error on seeding init for {date_str}: {response.status_code} - {response.text}")

def seed_layer_tiles(layer, zoom_start=3, zoom_stop=8):
    workspace = config.get('geoserver', 'workspace', fallback='droughts')
    layer_name = f"{workspace}:{layer}"
    conn = psycopg2.connect(**dict(config.items('database')))
    dates = get_dates_from_db(conn, layer)
    conn.close()
    for date_str in dates:
        seed_tiles_for_date(layer_name, date_str, zoom_start, zoom_stop)

# Example usage from API:
# from seeding import seed_layer_tiles
# seed_layer_tiles("era5_ecowas_spi1", zoom_start=3, zoom_stop=8)

if __name__ == "__main__":
    # For direct invocation, you can parse args or set defaults here
    seed_layer_tiles("era5_ecowas_spi1")