from flask import Flask, json, jsonify, render_template, Response
from flask_cors import CORS
import configparser
import os
import psycopg2
from src.get_layer_info import get_feature_data
from src.get_layer_info import get_feature_data_from_lat_lon

##############################################################################

# Load config.ini
config_path = os.path.join(os.path.dirname(__file__), '..', 'config', 'config.ini')
config = configparser.ConfigParser()
config.read(config_path)
def get_key_config(feat):
    """Return all feat config values as a dictionary."""
    if feat not in config:
        return {}
    return {key: config.get(feat, key) for key in config[feat]}

############################################################################### 
# Database connection functions 
###############################################################################
# DBConnection parameters PostgreSQL
DB_HOST = config.get('database', 'host')
DB_PORT = config.get('database', 'port')
DB_NAME = config.get('database', 'name')
DB_USER = config.get('database', 'user')
DB_PASSWORD = config.get('database', 'password')

def get_db_connection():
    conn = psycopg2.connect(
                database=DB_NAME,
                host=DB_HOST,
                user=DB_USER,
                password=DB_PASSWORD,
                port=DB_PORT
            )
    return conn

def close_db_connection(conn):
    if conn:
        conn.commit()
        conn.close()

###############################################################################
# Flask app
###############################################################################

app = Flask(__name__)
CORS(app)

@app.route('/get_data_from_lat_lon/<lat>/<lon>/<yearFrom>/<monthFrom>/<yearTo>/<monthTo>/<table>')
def get_data_from_latlon(lat, lon, yearFrom, monthFrom, yearTo, monthTo, table):
    conn = get_db_connection()
    feat_info = get_feature_data_from_lat_lon(table, lat, lon, int(yearFrom), int(monthFrom), int(yearTo), int(monthTo), conn)
    print(feat_info)
    close_db_connection(conn)
    return jsonify(feat_info)


@app.route('/get_feature_info/<layer>/<lat>/<lon>/<date>')
def get_feature_info(layer, lat, lon, date):
    table = get_key_config(layer).get('table')
    conn = get_db_connection()
    feat_info = get_feature_data(table, lat, lon, date, conn)
    close_db_connection(conn)
    return jsonify(feat_info)

@app.route('/get_product_info/<layer>')
def get_product_info(layer):
    products_path = os.path.join(os.path.dirname(__file__), '..', 'config', 'products.json')
    try:
        with open(products_path, 'r') as f:
            products = json.load(f)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    # Optionally, filter by layer if needed
    print(products)
    product_info = products.get(layer, {})
    return jsonify(product_info)

@app.route('/clim_chart/<layer>/<lat>/<lon>/<year_init>/<year_end>')
def clim_chart(layer, lat, lon, year_init, year_end):
    table = get_key_config(layer).get('table')
    return render_template('clim_chart.html',lat=lat,lon=lon,yearInit=year_init,yearEnd=year_end,table=table)

@app.route('/get_metadata/<layer>')
def get_metadata(layer):
    filename = f"{layer}.xml"
    xml_path = os.path.join(os.path.dirname(__file__), '..', 'metadata', filename)
    try:
        with open(xml_path, 'r') as f:
            xml_content = f.read()
        return Response(xml_content, mimetype='application/xml')
    except Exception as e:
        return Response(f"<error>{str(e)}</error>", mimetype='application/xml', status=404)

@app.route('/')
def main_map():
    map_config = get_key_config('map')

    # Get all layers config
    layers = {}
    layer_names = map_config["layers"].split(',')
    print(layer_names)
    for layer_name in layer_names:
        layer = get_key_config(layer_name)
        layers[layer_name] = layer
    
    map_config['layers'] = layers
    return render_template('main_map.html', map_config=map_config)

if __name__ == "__main__":
        app.run(host="0.0.0.0",debug=True)