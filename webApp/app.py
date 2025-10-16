from flask import Flask, json, jsonify, render_template, Response, request
from flask_cors import CORS
from waitress import serve
import configparser
import os
import psycopg2
from src.get_layer_info import get_feature_data, get_layer_time_bounds, get_meteo_stations_geojson, get_meteostation_month_data
from src.get_layer_info import get_feature_data_from_lat_lon
from src.get_layer_info import get_data_time_bounds
from src.get_layer_info import get_data_from_meteostation
from src.get_layer_info import get_station_time_bounds
from src.get_layer_info import get_station_data_from_lat_lon
from src.get_layer_info import export_table_to_netcdf

##############################################################################
# CONFIGURATION
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

def get_db_connection():
    conn = psycopg2.connect(**dict(config.items('database')))
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

@app.route('/get_data_from_lat_lon/<lat>/<lon>/<yearFrom>/<monthFrom>/<yearTo>/<monthTo>/<layer>')
def get_data_from_latlon(lat, lon, yearFrom, monthFrom, yearTo, monthTo, layer):
    conn = get_db_connection()
    feat_info = get_feature_data_from_lat_lon(layer, lat, lon, int(yearFrom), int(monthFrom), int(yearTo), int(monthTo), conn)
    close_db_connection(conn)
    return jsonify(feat_info)

@app.route('/get_data_station_from_lat_lon/<lat>/<lon>/<yearFrom>/<monthFrom>/<yearTo>/<monthTo>/<layer>/<variable>')
def get_data_station_from_latlon(lat, lon, yearFrom, monthFrom, yearTo, monthTo, layer, variable):
    conn = get_db_connection()
    feat_info = get_station_data_from_lat_lon(layer, variable, lat, lon, int(yearFrom), int(monthFrom), int(yearTo), int(monthTo), conn)
    close_db_connection(conn)
    return jsonify(feat_info)


@app.route('/get_feature_info/<layer>/<lat>/<lon>/<date>')
def get_feature_info(layer, lat, lon, date):
    conn = get_db_connection()
    feat_info = get_feature_data(layer, lat, lon, date, conn)
    close_db_connection(conn)
    return jsonify(feat_info)

@app.route('/get_all_meteostations')
def get_all_meteostations():
    conn = get_db_connection()
    feature_collection = get_meteo_stations_geojson(conn)
    close_db_connection(conn)
    return jsonify(feature_collection)

@app.route('/get_meteostation_info/<layer>/<lat>/<lon>/<date>')
def get_meteostation_info(layer, lat, lon, date):
    conn = get_db_connection()
    meteostation_info = get_meteostation_month_data(conn, lat, lon, date)
    close_db_connection(conn)
    return jsonify(meteostation_info)

@app.route('/get_data_from_station/<lat>/<lon>/', defaults={'date': None})
@app.route('/get_data_from_station/<lat>/<lon>/<date>')
def get_data_from_station(lat, lon, date):
    conn = get_db_connection()
    station_data = get_data_from_meteostation(conn, lat, lon, date)
    close_db_connection(conn)
    return jsonify(station_data)

@app.route('/get_product_info/<layer>')
def get_product_info(layer):
    products_path = os.path.join(os.path.dirname(__file__), '..', 'config', 'products.json')
    try:
        with open(products_path, 'r') as f:
            products = json.load(f)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    # Optionally, filter by layer if needed
    product_info = products.get(layer, {})
    return jsonify(product_info)

@app.route('/clim_chart/<layer>/<lat>/<lon>')
def clim_chart(layer, lat, lon):
    color_min = get_key_config(layer).get('chart_color_min')
    color_max = get_key_config(layer).get('chart_color_max')
    conn = get_db_connection()
    time_bounds = get_data_time_bounds(lat, lon, layer, conn)
    close_db_connection(conn)
    return render_template('clim_chart.html',lat=lat,lon=lon,layer=layer,year_init=time_bounds['min_year'],year_end=time_bounds['max_year'], color_min=color_min, color_max=color_max)

@app.route('/clim_station_chart/<layer>/<lat>/<lon>')
def clim_station_chart(layer, lat, lon):
    color_min = get_key_config(layer).get('chart_color_min')
    color_max = get_key_config(layer).get('chart_color_max')
    conn = get_db_connection()
    time_bounds = get_station_time_bounds(lat, lon, conn)
    close_db_connection(conn)
    return render_template('clim_station_chart.html',lat=lat,lon=lon,layer=layer,year_init=time_bounds['min_year'],year_end=time_bounds['max_year'], color_min=color_min, color_max=color_max)

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

@app.route('/export_table/<table_name>', methods=['POST'])
def export_table(table_name):
    init_date = request.json.get("init_date")
    end_date = request.json.get("end_date")
    bbox = request.json.get("bbox") 
    if bbox == {}:
        bbox = None
    output_filename = request.json.get("output_filename") or f"{table_name}_{init_date}_{end_date}.nc"
    print(f"Exporting table {table_name} from {init_date} to {end_date} with bbox {bbox} to {output_filename}")

    conn = get_db_connection()
    result = export_table_to_netcdf(conn, table_name, 'grid_025dd', 0.25, init_date, end_date, bbox, output_filename)
    close_db_connection(conn)
    return jsonify(result)

@app.route('/')
def main_map():
    map_config = get_key_config('map')

    # Get all layers config
    layers = {}
    layer_names = map_config["layers"].split(',')
    for layer_name in layer_names:
        layer = get_key_config(layer_name)
        conn = get_db_connection()
        time_bounds = get_layer_time_bounds(layer_name, conn)
        close_db_connection(conn)
        layer['time_bounds'] = time_bounds
        layers[layer_name] = layer
    
    map_config['layers'] = layers
    return render_template('main_map.html', map_config=map_config)

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="WebGIS Droughts Application")
    parser.add_argument('--development', action='store_true', help="Run in development mode")
    args = parser.parse_args()

        
    if args.development:
        app.run(host="0.0.0.0",debug=True)
    else:
        serve(app, host='0.0.0.0', port=5000)
        